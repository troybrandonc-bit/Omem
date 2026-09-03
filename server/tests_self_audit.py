"""The system applies its own discipline to claims about itself.
Run: python3 tests_self_audit.py

Three defects, all the same defect. A number was reported without the
conditions that would let a reader know whether to believe it.

ONE. `rate = wins / (wins + losses)` was the popularity bug, one level up from
the mining rule where it was already found and fixed. A generator that only
ever predicts claims most people hold accumulates an excellent record and
carries no information, in exactly the way a prior selected on popularity did.
PRIOR_MIN_LIFT stopped that in the miner; nothing stopped it here, and this
number feeds birth strength, so the confounded quantity reached every forecast.

TWO. The pass could not see its own selection. Measured against an external
reference, OMEM answers the claims whose base rate already supplies most of
the answer and declines the balanced ones where a forecast is worth most. That
was invisible from inside: it took a naive Bayes model over all 49 items to
reveal it.

THREE. Rates travelled bare. The one place a condition already travelled --
the calibration scorer's note that its Brier figure was a floor imposed by the
strength cap rather than a calibration failure -- is what identified the
largest defect this layer had. That pattern existed once. It is the pattern.

None of the three acts on what it now records. Correcting birth strength by
lift is a change that should be measured before it is made.
"""
import os
import sqlite3
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "benchmarks", "scale"))

import hypotheses as _h  # noqa: E402

PASS = FAIL = 0


def check(n, c, d=""):
    global PASS, FAIL
    if c:
        PASS += 1
        print("  ok  " + n)
    else:
        FAIL += 1
        print("  FAIL " + n + "  " + str(d)[:240])


def fresh():
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.executescript(_h.HYPOTHESES_SCHEMA)
    return db


print("== what chance was, on the claim that was guessed ==")
# 70 hold it, 30 deny it: the claim's own rate is 0.7, and denying it is 0.3.
profs = {}
for i in range(100):
    profs["person:%d" % i] = ({"likes_dashboards"} if i < 70
                              else {"not:likes_dashboards"}, set())
check("a claim's base rate is measured over those who took a position",
      _h.base_rate_of(profs, "likes_dashboards") == 0.7,
      _h.base_rate_of(profs, "likes_dashboards"))
check("and a denial's rate is the rate of denying it, not one minus nothing",
      abs(_h.base_rate_of(profs, "not:likes_dashboards") - 0.3) < 1e-9,
      _h.base_rate_of(profs, "not:likes_dashboards"))
check("a claim nobody has taken a position on has no base rate rather than "
      "a default one", _h.base_rate_of(profs, "prefers_calls") is None)

print("== a record that is right about the obvious shows no lift ==")
db = fresh()
# Ten wins on a claim that was going to be true 90% of the time anyway.
for _ in range(10):
    _h._score_generator(db, "proj", "prior:popular", True, 0.5, base=0.9)
rep = _h.calibration(db, "proj")["generators"]["prior:popular"]
check("the raw rate looks perfect", rep["rate"] == 1.0, rep)
check("and the lift says how little that was worth (%.2f)" % rep["lift"],
      abs(rep["lift"] - 0.10) < 0.02, rep)

db = fresh()
# Ten wins on a claim that was a coin flip.
for _ in range(10):
    _h._score_generator(db, "proj", "prior:informative", True, 0.5, base=0.5)
rep2 = _h.calibration(db, "proj")["generators"]["prior:informative"]
check("the same raw rate on a harder claim carries far more lift (%.2f)"
      % rep2["lift"], rep2["lift"] > 0.4, rep2)
check("so two identical win rates are no longer indistinguishable",
      rep["lift"] < rep2["lift"], (rep["lift"], rep2["lift"]))

print("== a rate that cannot bear weight says so ==")
db = fresh()
_h._score_generator(db, "proj", "prior:thin", True, 0.5, base=0.5)
e = _h.calibration(db, "proj")["generators"]["prior:thin"]
check("one verdict is reported with a note rather than as a rate",
      "note" in e and "too few" in e["note"], e)
check("and the count it rests on travels with it", e["n"] == 1, e)

db = fresh()
# A generator no better than the claim's own base rate.
for _ in range(8):
    _h._score_generator(db, "proj", "prior:chance", True, 0.5, base=1.0)
e = _h.calibration(db, "proj")["generators"]["prior:chance"]
check("a record no better than chance says exactly that",
      "note" in e and "usually true anyway" in e["note"], e)

db = fresh()
# Verdicts recorded before the base rate was: lift is unknown, not zero.
for _ in range(8):
    _h._score_generator(db, "proj", "prior:legacy", True, 0.5, base=None)
e = _h.calibration(db, "proj")["generators"]["prior:legacy"]
check("verdicts predating the base rate report lift as unknown, not as zero",
      "lift" not in e and "note" in e and "unknown" in e["note"], e)

print("== a database predating the columns does not go dark ==")
old = sqlite3.connect(":memory:")
old.row_factory = sqlite3.Row
old.executescript("""CREATE TABLE leap_generators(
  project_id TEXT NOT NULL, generator TEXT NOT NULL,
  wins INTEGER NOT NULL, losses INTEGER NOT NULL,
  PRIMARY KEY(project_id, generator));
CREATE TABLE hypotheses(id TEXT, project_id TEXT, subject TEXT,
  proposition TEXT, born_from TEXT, generator TEXT, because TEXT,
  strength REAL, status TEXT, docket TEXT, passes INT, fingerprint TEXT,
  decided REAL, asked REAL);
CREATE TABLE priors(id TEXT, project_id TEXT, antecedent TEXT,
  consequent TEXT, context TEXT, support INT, refute INT, subjects INT,
  updated REAL);""")
old.execute("INSERT INTO leap_generators VALUES('proj','g',7,3)")
old.commit()
try:
    got = _h.calibration(old, "proj")["generators"]["g"]
    ok = got["rate"] == 0.7 and "lift" not in got
except Exception as exc:      # noqa: BLE001
    ok, got = False, repr(exc)
check("the rate still reads, and lift is simply absent", ok, got)
_h.ensure_schema(old)
cols = {r["name"] for r in old.execute("PRAGMA table_info(leap_generators)")}
check("and ensure_schema adds the columns to a table that already existed",
      {"base_sum", "verdicts"} <= cols, sorted(cols))

print("== a pass reports which claims it chose to speak about ==")
import leaping as _lp  # noqa: E402

assertions, profiles = _lp.world(60, 10, seed=4, hold=1.0)
# One claim almost everyone holds, one that splits the room. Both are silences
# for everybody, so the only thing deciding which gets spoken about is which
# prior exists.
# p003 needs a base rate AND has to be a silence for whoever is guessed
# about, so some people take a position on it and others leave it open. The
# first version gave everybody a position, which made it no silence at all and
# no prior could fire -- the same mistake, in the same shape, as the earlier
# harness where every proposition was held.
for i, who in enumerate(sorted(profiles)):
    held = {"p000"}
    if i < 30:
        held.add("p003")                # takes a position: 30 hold
    elif i < 35:
        held.add("not:p003")            # 5 deny, so base rate is 30/35
    # the rest leave p003 open, and are the ones a prior can speak about
    held.add("p004" if i % 2 else "not:p004")   # an available 50/50 claim
    profiles[who] = [held, set()]
assertions = [a for a in assertions if a.proposition == "p000"]
n = len(assertions)
for who in profiles:
    for prop in sorted(profiles[who][0]):
        assertions.append(_lp.Assertion("a%d" % n, who, prop))
        n += 1

db = fresh()
db.execute("INSERT INTO priors VALUES('pr_easy','proj','p000','p003',"
           "'default',300,10,310,0)")
db.commit()
op, pf = _h._declared_opposites, _h._profiles
_h._profiles = lambda d_, p_, T_: profiles
_h._declared_opposites = lambda p_, prop_: set()
try:
    res = _h.leap(_lp.FakeProject(assertions), db)
finally:
    _h._profiles, _h._declared_opposites = pf, op

check("the pass reports the mean base rate of what it spoke about",
      "spoken_base_mean" in res, sorted(res))
check("and the mean over every claim available to speak about",
      "population_base_mean" in res, sorted(res))
check("and the gap between them, which is the selection it cannot otherwise "
      "see", "selection_bias" in res, sorted(res))
if "selection_bias" in res:
    check("a pass that spoke only about a claim held by 92%% of people, in a "
          "population also holding a 50/50 claim, reports a positive bias "
          "(%.3f)" % res["selection_bias"], res["selection_bias"] > 0.05,
          (res.get("spoken_base_mean"), res.get("population_base_mean")))

print("\n%d passed, %d failed" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)
