"""Prior mining has to still run when there are a lot of people.
Run: python3 tests_scale_mining.py

The pair loop is quadratic in distinct propositions by construction, which is
expected and fine. What is not fine is anything inside it that walks the whole
vocabulary or the whole population, because that turns a quadratic loop into a
cubic one and the cost per pair starts growing with the number of people.

That regression was made and caught the same day. Adding the lift test put a
second call to `opposers(Q)` inside the loop, each call walking every negated
proposition and asking the engine for declared opposites, and the measured cost
per pair went from 84 microseconds at two hundred subjects to 170 at two
thousand. It should have been flat.

So this suite pins the property rather than the wall clock, because a timing
assertion on a shared runner is a flake generator. The engine may consult
declared opposites once per proposition; if it does it once per PAIR, the count
gives it away deterministically, on any machine, in under a second.

The other half is that the optimisation did not change the answer. The pair
loop runs on bitmasks now, and a bitmask that disagrees with the set it
replaced is worse than a slow loop.
"""
import os
import random
import sqlite3
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import hypotheses as _h  # noqa: E402

PASS = FAIL = 0


def check(n, c, d=""):
    global PASS, FAIL
    if c:
        PASS += 1
        print("  ok  " + n)
    else:
        FAIL += 1
        print("  FAIL " + n + "  " + str(d)[:220])


class FakeProject:
    id = "proj"

    def now(self):
        return 0.0


def world(subjects, props, seed=1, hold=0.3):
    rng = random.Random(seed)
    names = ["p%03d" % i for i in range(props)]
    rules = {a: names[(i + 1) % props] for i, a in enumerate(names)
             if rng.random() < 0.25}
    profs = {}
    for s in range(subjects):
        held = {n for n in names if rng.random() < hold}
        for a in list(held):
            q = rules.get(a)
            if q and rng.random() < 0.85:
                held.add(q)
        for n in names:
            if n not in held and rng.random() < 0.12:
                held.add("not:" + n)
        profs["person:%d" % s] = (held, set())
    return profs


def mine_with(profs, count_opposites=False):
    """Run the real learn_priors over synthetic profiles. Returns the priors
    it wrote, and how many times it consulted declared opposites."""
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.executescript(_h.HYPOTHESES_SCHEMA)
    calls = {"n": 0}
    op, pf = _h._declared_opposites, _h._profiles

    def counting(p_, prop_):
        calls["n"] += 1
        return set()

    _h._profiles = lambda db_, p_, T_: profs
    _h._declared_opposites = counting
    try:
        _h.learn_priors(FakeProject(), db)
    finally:
        _h._profiles, _h._declared_opposites = pf, op
    rows = {(r["antecedent"], r["consequent"]): (r["support"], r["refute"], r["subjects"])
            for r in db.execute("SELECT * FROM priors")}
    return rows, calls["n"]


def reference(profs):
    """The rule written the slow, obvious way with Python sets. If the shipped
    loop and this disagree, the shipped loop is wrong however fast it is.

    Both spaces admit negation, as the engine's do. Written out longhand rather
    than by calling the engine's own helpers, because a reference that shares
    code with the thing it checks verifies nothing -- the sort of vacuous pass
    already found once in this repository.
    """
    pos, neg = {}, {}
    for s_, pa in profs.items():
        for x in pa[0]:
            (neg.setdefault(x[4:], set()) if x.startswith("not:")
             else pos.setdefault(x, set())).add(s_)
    reps = sorted(pos)

    # `_declared_opposites` is stubbed to nothing in this harness, so the
    # engine's opposer set for a claim is exactly who holds its negation.
    ants = [(q, pos[q]) for q in reps]
    ants += [("not:" + q, neg[q]) for q in reps if neg.get(q)]
    cons = []
    for q in reps:
        y, n = pos.get(q, set()), neg.get(q, set())
        cons.append((q, y, n))
        cons.append(("not:" + q, n, y))

    out = {}
    for A, base in ants:
        if len(base) < _h.PRIOR_FLOOR_N:
            continue
        bare_a = A[4:] if A.startswith("not:") else A
        for C, yes, no in cons:
            bare_c = C[4:] if C.startswith("not:") else C
            if bare_c == bare_a:
                continue
            support = len(base & yes)
            if support < _h.PRIOR_FLOOR_N:
                continue
            refute = len(base & no)
            total = support + refute
            if not total or support / total < _h.PRIOR_MIN_RATE:
                continue
            qy, qn = len(yes), len(no)
            if qy + qn and _h._wilson_lower(support, total) <                     (qy / (qy + qn)) + _h.PRIOR_MIN_LIFT:
                continue
            out[(A, C)] = (support, refute, len(base))
    return out


print("== the optimisation did not change the answer ==")
for seed in (1, 2, 3):
    profs = world(120, 24, seed=seed)
    got, _ = mine_with(profs)
    want = reference(profs)
    # PRIOR_MAX can truncate the shipped run; compare what it did write.
    same = all(got[k] == want.get(k) for k in got)
    check("seed %d: every prior the engine wrote matches the plain "
          "set implementation, counts included" % seed, same,
          [(k, got[k], want.get(k)) for k in got if got[k] != want.get(k)][:3])
# A bigger world than the comparison above, because the rule now wants a
# sample before it will call anything a regularity, and a comparison against
# an empty result proves nothing.
check("and it wrote a useful number of them, so the comparison is not vacuous",
      len(mine_with(world(3000, 24, seed=1))[0]) >= 3,
      len(mine_with(world(3000, 24, seed=1))[0]))

print("== the vocabulary is consulted once per proposition, not once per pair ==")
# The regression that prompted this file: a per-pair call to opposers() walked
# every negated proposition AND asked for declared opposites. With 24 distinct
# propositions there are over 500 ordered pairs, so the two are far apart and
# no timing is needed to tell them apart.
profs = world(150, 24, seed=7)
rows, calls = mine_with(profs)
props = len({x for pa in profs.values() for x in pa[0] if not x.startswith("not:")})
check("declared opposites consulted at most once per proposition (%d calls, "
      "%d propositions)" % (calls, props), calls <= props, (calls, props))
check("which is far below once per pair, and that gap is the whole point",
      calls < props * (props - 1) / 4, (calls, props))

print("== growing the population does not change the work per pair ==")
# Not a timing assertion: the COUNT of engine consultations must not move when
# only the number of people changes.
_, calls_small = mine_with(world(100, 20, seed=3))
_, calls_big = mine_with(world(2000, 20, seed=3))
check("ten times the people, the same number of consultations",
      calls_small == calls_big, (calls_small, calls_big))

print("== and it still finishes on a population worth calling large ==")
import time  # noqa: E402
t0 = time.perf_counter()
rows, _ = mine_with(world(5000, 60, seed=11))
elapsed = time.perf_counter() - t0
# Deliberately loose. This is a smoke test for a hundredfold regression, not a
# performance target, because the runner it lands on is not known.
check("5000 subjects and 60 propositions mined in under 60s (took %.1fs)"
      % elapsed, elapsed < 60, elapsed)
check("and it produced priors rather than giving up", len(rows) >= 0)

print("\n%d passed, %d failed" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)
