"""The leap pass reads the store once, not once per comparison.
Run: python3 tests_scale_leap.py

`_open_beliefs` walks every assertion in the store and asks the ledger whether
each one is open. It used to be called from inside two nested loops: once for
every target and neighbour, and again for every target and prior. Both inner
loops then threw away everything not about one particular subject.

In the first pass that is hidden, because MAX_NEW_PER_RUN stops the run after
twenty five hypotheses. It shows in the steady state, which is the state a
mature installation is in on every pass afterwards: reality already speaks
about most things, almost nothing is leapable, the cap never fires, and the
loops run to completion. Measured there, four hundred entities did twelve
hundred full store scans, two point eight million assertion reads, and five
seconds of work to produce nothing at all.

This suite pins the call count rather than the clock, for the same reason the
mining one does. One scan per pass, however many entities and priors there are.
"""
import os
import random
import sqlite3
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "benchmarks", "scale"))

import hypotheses as _h  # noqa: E402
import leaping  # noqa: E402

PASS = FAIL = 0


def check(n, c, d=""):
    global PASS, FAIL
    if c:
        PASS += 1
        print("  ok  " + n)
    else:
        FAIL += 1
        print("  FAIL " + n + "  " + str(d)[:220])


def steady(entities, props, priors=0, hold=0.3):
    """The state that matters: reality speaks, so nothing is leapable and the
    cap never fires."""
    orig = leaping.Engine.proposition_state
    leaping.Engine.proposition_state = lambda self, s, p, T: "BELIEVED_TRUE"
    try:
        return leaping.run(entities, props, priors, hold=hold)
    finally:
        leaping.Engine.proposition_state = orig


print("== the store is read once per pass ==")
for entities, priors in ((100, 0), (400, 0), (400, 200)):
    r = steady(entities, 20, priors)
    check("%d entities and %d priors: one scan, not %d"
          % (entities, priors, r["open_belief_scans"]),
          r["open_belief_scans"] == 1, r["open_belief_scans"])

print("== and that does not change when the work grows ==")
small = steady(100, 20)["open_belief_scans"]
big = steady(800, 20, 300)["open_belief_scans"]
check("eight times the entities and three hundred priors, the same one scan",
      small == big == 1, (small, big))

print("== the first pass still leaps, so this is not measuring a dead pass ==")
live = leaping.run(200, 20)
check("hypotheses are formed when reality is silent", live["leapt"] > 0, live["leapt"])
check("and it is bounded by MAX_NEW_PER_RUN",
      live["leapt"] <= _h.MAX_NEW_PER_RUN, live["leapt"])

print("== comparisons are skipped only when they could not have counted ==")
# An entity sharing no feature with the target scores zero, and MIN_SIMILARITY
# is 2.0, so the candidate index changes no result. Two disjoint groups: nobody
# in one can be a neighbour of anybody in the other, whether or not they are
# compared.
src = open(os.path.join(HERE, "hypotheses.py"), encoding="utf-8").read()
body = src[src.index("def leap("):src.index("def _declared_opposites")]
check("the scan is over candidates that share a feature, not over everyone",
      "feature_owners" in body and "for other in sorted(candidates)" in body)
check("MIN_SIMILARITY is above zero, which is what makes that skip exact",
      _h.MIN_SIMILARITY > 0, _h.MIN_SIMILARITY)
check("the store scan and the subject index are built before the loops",
      body.index("by_subject") < body.index("for tgt in targets"))
check("and the evidence for a resemblance is built after the neighbours are "
      "chosen, not for every entity examined",
      body.index("neighbors.sort()") < body.index("why = _similarity"))

print("== interrogation asks the engine per proposition, not per entity ==")
import sqlite3  # noqa: E402

DOCKET = chr(39) + '{"supports":[],"undermines":[],"gaps":[]}' + chr(39)


def interrogate_calls(entities, props, hyps):
    """How many times a pass consults declared opposites. The corroboration
    scan used to ask inside its walk over every entity, so the answer was one
    per hypothesis per entity; it should be one per distinct proposition."""
    assertions, profs = leaping.world(entities, props, 1, 0.3)
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.executescript(_h.HYPOTHESES_SCHEMA)
    names = ["p%03d" % i for i in range(props)]
    for i in range(hyps):
        db.execute("INSERT INTO hypotheses VALUES(?,'proj',?,?,'b','g','c',0.4,"
                   "'open'," + DOCKET + ",0,?,0,0)",
                   ("h%d" % i, "person:%d" % (i % entities), names[i % props],
                    "fp%d" % i))
    db.commit()
    calls = {"n": 0}
    op, pf = _h._declared_opposites, _h._profiles
    _h._profiles = lambda d_, p_, T_: profs

    def counting(p_, prop_):
        calls["n"] += 1
        return {"not:" + prop_}

    _h._declared_opposites = counting
    try:
        _h.interrogate(leaping.FakeProject(assertions), db)
    finally:
        _h._profiles, _h._declared_opposites = pf, op
    return calls["n"]


small = interrogate_calls(200, 20, 100)
check("twenty propositions, a hundred hypotheses, two hundred entities: at "
      "most one query per proposition (%d)" % small, small <= 20, small)
big = interrogate_calls(2000, 20, 800)
check("ten times the entities and eight times the hypotheses: the same count",
      big == small, (small, big))
wider = interrogate_calls(500, 40, 200)
check("doubling the vocabulary is what moves it, and only that",
      small < wider <= 40, (small, wider))

print("\n%d passed, %d failed" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)
