"""The bank can say "probably not", and cannot say both at once.
Run: python3 tests_prior_negation.py

`reps` was built from positive holders only and both mining loops walked it, so
two classes of regularity could never be learned: what people who DENY P tend
to hold, and what people who hold P tend to DENY. The second was the expensive
omission. A system that can only guess "holds" is structurally unable to be
right about a denial -- it stays silent or it is wrong -- and in the Big Five
data a third of the answers people give are denials.

Measured over 19,668 real respondents on three independent seed groups:

    space                     coverage              marginal lift
    positive only        762 /  721 /  740    +0.128 / +0.104 / +0.130
    negated antecedents  937 /  903 /  913    +0.108 / +0.089 / +0.106
    negated consequents 1014 /  974 / 1000    +0.189 / +0.156 / +0.168
    both               1249 / 1194 / 1226    +0.197 / +0.180 / +0.183

Negated antecedents are worse than positive-only in all three groups alone and
better in all three alongside negated consequents, because `not:P -> not:Q` is
then expressible and "people who deny P tend to deny Q" is the strongest
pattern this data holds. They ship together or not at all.

Brier skill FALLS while this improves, and that is not a regression: admitting
denials raises the observed rate, which grows the base-rate reference the score
divides by. Coverage and lift are the comparable pair. See tests_prior_anchor
and benchmarks/external/README.md.

The property this suite guards hardest is the last one. A record whose purpose
is to keep contradictions visible must never manufacture one, and with negation
in the space it otherwise could hand a single person both "holds Q" and "does
not hold Q" about the same silence.
"""
import os
import sqlite3
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "benchmarks", "scale"))

import hypotheses as _h  # noqa: E402
import commons as _c     # noqa: E402

PASS = FAIL = 0


def check(n, c, d=""):
    global PASS, FAIL
    if c:
        PASS += 1
        print("  ok  " + n)
    else:
        FAIL += 1
        print("  FAIL " + n + "  " + str(d)[:240])


class P:
    id = "proj"

    def now(self):
        return 0.0


def mine(profiles):
    """Drive the real learn_priors over given profiles."""
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.executescript(_h.HYPOTHESES_SCHEMA)
    op, pf = _h._declared_opposites, _h._profiles
    _h._profiles = lambda d_, p_, T_: profiles
    _h._declared_opposites = lambda p_, prop_: set()
    try:
        _h.learn_priors(P(), db)
    finally:
        _h._profiles, _h._declared_opposites = pf, op
    return {(r["antecedent"], r["consequent"]):
            (r["support"], r["refute"], r["subjects"])
            for r in db.execute("SELECT * FROM priors")}


print("== all four combinations of polarity can be learned ==")
# 60 people. Everyone who holds a also holds b. Everyone who denies a also
# denies c. Nobody's holding of a predicts d, which stays a control.
profs = {}
for i in range(60):
    held, opp = set(), set()
    if i < 30:
        held |= {"prefers_async", "prefers_email"}      # a -> b
        opp.add("prefers_calls")                        # a -> not:c
    else:
        opp |= {"prefers_async", "prefers_email"}       # not:a -> not:b
        held.add("prefers_calls")                       # not:a -> c
    profs["person:%d" % i] = (held, set())
    for x in opp:
        profs["person:%d" % i][0].add("not:" + x)

got = mine(profs)
kinds = {(a.startswith("not:"), c.startswith("not:")) for a, c in got}
check("positive antecedent to positive consequent", (False, False) in kinds, sorted(got)[:3])
check("positive antecedent to NEGATED consequent", (False, True) in kinds,
      [k for k in got if k[1].startswith("not:")][:3])
check("NEGATED antecedent to positive consequent", (True, False) in kinds,
      [k for k in got if k[0].startswith("not:")][:3])
check("NEGATED antecedent to negated consequent", (True, True) in kinds,
      [k for k in got if k[0].startswith("not:") and k[1].startswith("not:")][:3])

print("== a claim never predicts itself, or its own negation ==")
selfish = [(a, c) for a, c in got
           if (a[4:] if a.startswith("not:") else a)
           == (c[4:] if c.startswith("not:") else c)]
check("no prior has the same bare claim on both sides", not selfish, selfish[:4])

print("== a negated prior fires only on someone who actually denied it ==")
import leaping as _lp  # noqa: E402


def leap_with(priors, held, denied, props=8):
    assertions, profiles = _lp.world(30, props, seed=5, hold=1.0)
    for who in list(profiles):
        profiles[who] = [set(held) | {"not:" + d for d in denied}, set()]
    keep = set(held) | set(denied)
    assertions = [a for a in assertions
                  if (a.proposition[4:] if a.proposition.startswith("not:")
                      else a.proposition) in keep]
    # The store must carry the denial too, or nothing grounds the hunch.
    n = len(assertions)
    for who in profiles:
        for d in denied:
            assertions.append(_lp.Assertion("neg%d" % n, who, "not:" + d))
            n += 1
        for hh in held:
            assertions.append(_lp.Assertion("pos%d" % n, who, hh))
            n += 1
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.executescript(_h.HYPOTHESES_SCHEMA)
    for i, (ant, cons, sup, ref) in enumerate(priors):
        db.execute("INSERT INTO priors VALUES(?,'proj',?,?,'default',?,?,?,0)",
                   ("pr_%d" % i, ant, cons, sup, ref, sup + ref))
    db.commit()
    op, pf = _h._declared_opposites, _h._profiles
    _h._profiles = lambda d_, p_, T_: profiles
    _h._declared_opposites = lambda p_, prop_: set()
    try:
        _h.leap(_lp.FakeProject(assertions), db)
    finally:
        _h._profiles, _h._declared_opposites = pf, op
    return [dict(r) for r in db.execute(
        "SELECT subject, proposition, generator, because FROM hypotheses")]


# The prior is "people who deny p001 tend to hold p005". A population that
# HOLDS p001 must not trigger it.
rows = leap_with([("not:p001", "p005", 300, 10)], held=["p001"], denied=[])
check("a negated antecedent does not fire on someone who holds the claim",
      not any(r["proposition"] == "p005" for r in rows),
      [r["proposition"] for r in rows][:4])

rows = leap_with([("not:p001", "p005", 300, 10)], held=[], denied=["p001"])
check("and does fire on someone who denied it",
      any(r["proposition"] == "p005" for r in rows),
      [r["proposition"] for r in rows][:4])
if rows:
    grounded = [r for r in rows if r["proposition"] == "p005"]
    check("the hunch is grounded in the denial rather than a same-named "
          "positive", grounded and "not:p001" in (grounded[0]["because"] or ""),
          grounded[0]["because"] if grounded else None)

print("== a hunch may predict absence ==")
rows = leap_with([("p001", "not:p005", 300, 10)], held=["p001"], denied=[])
neg = [r for r in rows if r["proposition"] == "not:p005"]
check("a prior with a negated consequent forms a 'probably not' hunch",
      bool(neg), [r["proposition"] for r in rows][:4])

print("== and never both directions about one silence ==")
# Two priors disagree about p005: one says hold it, one says deny it. Only one
# hunch may exist per person per bare claim, or the engine has manufactured the
# contradiction it exists to expose.
rows = leap_with([("p001", "p005", 40, 30), ("p001", "not:p005", 300, 10)],
                 held=["p001"], denied=[])
per = {}
for r in rows:
    b = (r["proposition"][4:] if r["proposition"].startswith("not:")
         else r["proposition"])
    per.setdefault((r["subject"], b), []).append(r["proposition"])
worst = max((v for v in per.values()), key=len, default=[])
check("at most one hunch per person per bare claim, so no person is handed "
      "both a claim and its denial", len(worst) <= 1, worst)
check("and the better-evidenced direction is the one that spoke",
      all(v[0].startswith("not:") for v in per.values()) if per else False,
      sorted(per.items())[:2])

print("== a negated count may reach the commons, an entity id may not ==")
check("not:<behaviour> passes both doors", _c.lexicon_ok("not:prefers_async"))
check("not:<entity id> does not, because the second colon survives the strip",
      not _c.lexicon_ok("not:person:sam"))
check("not:rel_ does not either, because the prefix survives it",
      not _c.lexicon_ok("not:rel_works_at_acme"))
check("a bare entity id is still refused", not _c.lexicon_ok("person:sam"))
check("and a negated word outside the lexicon is still foreign",
      not _c.lexicon_ok("not:zzzznotaword"))

print("== the terms say a count may record what people do NOT do ==")
summary = _c.TERMS[_c.TERMS_VERSION]["summary"]
check("the granted terms describe negation, so consent covers what now leaves",
      "tend NOT to do" in summary or "tend not to do" in summary, summary[:160])

print("\\n%d passed, %d failed" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)
