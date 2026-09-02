"""The commons experiment has to be able to return a bad answer.
Run: python3 tests_commons_benchmark.py

A benchmark that cannot fail is not evidence, and this one exists to decide
whether the commons is worth building, so the ways it could flatter us are the
ways that matter:

  it must be pinned to the engine's constants rather than to copies, or the
  simulation slowly stops describing the thing it claims to;

  it must respect the refusals the live system makes. A prior below the floor,
  a pooled row only one install has seen, a claim the person has already
  spoken to, a borrowed hunch born bolder than a local one: every one of those
  would inflate the result;

  and the negative control has to work. When the contributing populations are
  unrelated, the bank must stop paying. A harness where borrowed knowledge
  helps whether or not the populations have anything in common is measuring
  its own wishful thinking, and that check is the reason the positive number
  is worth reading at all.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "benchmarks", "commons"))
sys.path.insert(0, os.path.join(ROOT, "benchmarks", "calibration"))

import commons as _c  # noqa: E402
import hypotheses as _h  # noqa: E402
import simulate as sim  # noqa: E402

PASS = FAIL = 0


def check(n, c, d=""):
    global PASS, FAIL
    if c:
        PASS += 1
        print("  ok  " + n)
    else:
        FAIL += 1
        print("  FAIL " + n + "  " + str(d)[:220])


print("== pinned to the live system, not to copies of it ==")
for name, live in (("PRIOR_FLOOR_N", _h.PRIOR_FLOOR_N),
                   ("PRIOR_MIN_RATE", _h.PRIOR_MIN_RATE),
                   ("BASE_STRENGTH", _h.BASE_STRENGTH),
                   ("STRENGTH_FLOOR", _h.STRENGTH_FLOOR),
                   ("STRENGTH_CEILING", _h.STRENGTH_CEILING),
                   ("POOLED_DISCOUNT", _h.POOLED_DISCOUNT)):
    check(f"{name} is the engine's", getattr(sim, name) == live)
check("POOLED_MIN_SOURCES is the commons door's",
      sim.POOLED_MIN_SOURCES == _c.POOLED_MIN_SOURCES)
check("every token it uses would pass the commons vocabulary",
      all(_c.lexicon_ok(t) for t in sim.ANTECEDENTS + sim.CONSEQUENTS))

print("== the miner refuses what learn_priors refuses ==")
A, C = sim.ANTECEDENTS[0], sim.CONSEQUENTS[0]
two = [({A}, {C}), ({A}, {C})]
check("two subjects are not a law of humanity", sim.mine(two) == {}, sim.mine(two))
three = [({A}, {C})] * 3
check("three clear the floor", (A, C) in sim.mine(three), sim.mine(three))
weak = [({A}, {C})] * 3 + [({A}, set())] * 3
check("a pattern that holds half the time is not a prior",
      sim.mine(weak) == {}, sim.mine(weak))
check("and the rate it is judged on is the engine's",
      3 / 6 < sim.PRIOR_MIN_RATE)

print("== the echo check at the return door ==")
one_install = [{(A, C): (5, 0, 5)}]
check("a pair only one install has ever seen never crosses back",
      sim.pool(one_install) == {}, sim.pool(one_install))
two_installs = [{(A, C): (5, 0, 5)}, {(A, C): (4, 1, 5)}]
pooled = sim.pool(two_installs)
check("two separate populations unlock it", (A, C) in pooled, pooled)
check("and the counts are summed with the source count kept",
      pooled[(A, C)] == (9, 1, 10, 2), pooled)

print("== borrowed knowledge knows its place ==")
local = {(A, C): (5, 0, 5)}
inst = sim.Install(local, {(A, C): (9, 1, 10, 2), (A, sim.CONSEQUENTS[1]): (9, 1, 10, 2)})
keys = dict(inst.rows)
check("a pooled row covering a local pair is dropped, not merged",
      keys[(A, C)] is False, inst.rows)
check("a pooled row covering a pair the install has never seen is added",
      keys[(A, sim.CONSEQUENTS[1])] is True, inst.rows)
check("a borrowed hunch is born weaker than the same hunch held locally",
      inst.strength_for((A, sim.CONSEQUENTS[1]), True)
      < inst.strength_for((A, C), False))
check("and never below the floor",
      inst.strength_for((A, C), True) >= sim.STRENGTH_FLOOR)

print("== a prior fires only into a silence ==")
g = inst.guess({A}, set())
check("it guesses when the person has not spoken", len(g) == 2, g)
g2 = inst.guess({A}, {C, sim.CONSEQUENTS[1]})
check("and says nothing about a claim they have already spoken to",
      g2 == [], g2)
g3 = inst.guess(set(), set())
check("and nothing at all when the antecedent is absent", g3 == [], g3)

print("== no opinion is scored as nothing, never as zero ==")
empty = sim.set_stats([], {C: 0.5})
check("an install with nothing to guess with reports n=0",
      empty["n"] == 0 and empty["precision"] is None, empty)
check("and its lift is not reported as a number either",
      empty["lift"] is None, empty)

print("== lift is measured against the base rate of the same claims ==")
rows = [{"strength": 0.4, "won": True, "c": C, "q": (0, C), "borrowed": True}] * 8
st = sim.set_stats(rows, {C: 0.9})
check("guessing right about something almost everyone does earns no lift",
      st["precision"] == 1.0 and abs(st["lift"] - 0.1) < 1e-9, st)
st2 = sim.set_stats(rows, {C: 0.2})
check("the same guesses about something rare earn a lot",
      abs(st2["lift"] - 0.8) < 1e-9, st2)

print("== the run is deterministic, so a result can be rechecked ==")
a = sim.score_trial(sim.trial(7, 0.0))
b = sim.score_trial(sim.trial(7, 0.0))
check("the same seed gives the same answer", a == b)
check("a different seed does not", sim.score_trial(sim.trial(8, 0.0)) != a)

print("== both conditions sat the same exam ==")
res = sim.trial(3, 0.0)
loc = {r["q"] for r in res["local"]}
pool_q = {r["q"] for r in res["pooled"]}
check("every claim the local install spoke to, the pooled one did too",
      loc <= pool_q, len(loc - pool_q))
check("the shared set is exactly that overlap", res["shared_q"] == loc & pool_q)
check("the marginal set is what only the bank could reach",
      all(r["borrowed"] for r in res["pooled"] if r["q"] not in res["shared_q"]))

print("== the negative control, which is why the positive number counts ==")
# Sparse world, where the bank has room to help. When the contributing
# populations share the world, borrowed guesses should beat the base rate of
# the claims they are about. When the populations are unrelated, that has to
# stop. If a future change makes the bank look good in both, this goes red and
# the benchmark is telling us it has stopped measuring anything.
import statistics  # noqa: E402


def marg_lift(spread, trials=8):
    xs = [sim.score_trial(sim.trial(s, spread, hold=0.20, signal_frac=0.20)
                          )["marginal"]["lift"] for s in range(1, trials + 1)]
    return statistics.fmean([x for x in xs if x is not None])


agree, unrelated = marg_lift(0.0), marg_lift(1.0)
check("populations that share a world: the bank beats the base rate",
      agree > 0.02, agree)
check("populations that do not: the bank stops paying",
      unrelated < agree - 0.05, (agree, unrelated))

print("\n%d passed, %d failed" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)
