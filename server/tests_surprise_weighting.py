"""Verdicts do not all teach the same amount.
Run: python3 tests_surprise_weighting.py

A flat win-or-loss record says being confident and wrong is worth exactly as
much as being unsure and wrong, which is not how anything learns. The record
that drives boldness is now weighted by prediction error: the gap between the
strength a hunch was born with and the verdict reality returned.

The suite pins three things, because each is a way this could go quietly
wrong:

  the arithmetic, by hand, including the case that reads as leniency and is
  not -- a generator that guesses weakly and is usually refuted told the
  truth about how little it knew, and is barely punished for it;

  the boundary with the commons, which is unchanged: counts stay integers,
  the bank still contributes counts, and calibration() still reports them.
  A weight is a fact about learning, not a fact about the world, and it must
  never cross the machine boundary;

  the upgrade, because leap_generators predates this on every install that
  has ever scored a generator. Missing columns get added, and a row written
  before weighting keeps what it had earned rather than resetting to zero.
"""
import os
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


def close(a, b, eps=1e-9):
    return a is not None and abs(a - b) < eps


def fresh():
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    _h.ensure_schema(db)
    return db


print("== the prediction error, by hand ==")
check("supported at 0.05 is a shock and teaches nearly everything",
      close(_h.surprise(0.05, True), 0.95), _h.surprise(0.05, True))
check("refuted at 0.05 was half expected and teaches almost nothing",
      close(_h.surprise(0.05, False), 0.05), _h.surprise(0.05, False))
check("refuted at the 0.6 ceiling is the expensive mistake",
      close(_h.surprise(0.6, False), 0.6), _h.surprise(0.6, False))
check("supported at the ceiling teaches least of the wins",
      close(_h.surprise(0.6, True), 0.4), _h.surprise(0.6, True))
check("a coin flip teaches the same either way",
      close(_h.surprise(0.5, True), 0.5) and close(_h.surprise(0.5, False), 0.5))
check("a strength outside [0,1] is clamped rather than trusted",
      close(_h.surprise(1.7, False), 1.0) and close(_h.surprise(-2.0, False), 0.0),
      (_h.surprise(1.7, False), _h.surprise(-2.0, False)))
check("a confident miss teaches more than a tentative one",
      _h.surprise(0.6, False) > _h.surprise(0.1, False))

print("== the counts stay countable ==")
db = fresh()
_h._score_generator(db, "proj", "customer:alpha", True, 0.35)
_h._score_generator(db, "proj", "customer:alpha", False, 0.35)
row = db.execute("SELECT * FROM leap_generators "
                 "WHERE generator='customer:alpha'").fetchone()
check("wins and losses are still whole verdicts",
      row["wins"] == 1 and row["losses"] == 1, dict(row))
check("and the weights sit beside them, not on top of them",
      close(row["w_wins"], 0.65) and close(row["w_losses"], 0.35), dict(row))
check("_gen_counts reports the countable half",
      _h._gen_counts(db, "proj", "customer:alpha") == (1, 1))
check("_gen_record reports the weighted half",
      close(_h._gen_record(db, "proj", "customer:alpha")[0], 0.65))
check("a generator nobody has scored has an empty record, not an error",
      _h._gen_record(db, "proj", "customer:nobody") == (0.0, 0.0))

print("== two records that disagree about how much was learned ==")
# Ten refutations at the floor against one at the ceiling. The counts say the
# first generator is ten times worse; the weights say it is barely worse at
# all, because it never claimed otherwise.
db = fresh()
for _ in range(10):
    _h._score_generator(db, "proj", "timid", False, 0.05)
_h._score_generator(db, "proj", "bold", False, 0.6)
timid = _h._gen_record(db, "proj", "timid")
bold = _h._gen_record(db, "proj", "bold")
check("ten quiet misses weigh less than one confident miss",
      timid[1] < bold[1], (timid, bold))
check("the counts still say ten and one, so nothing was hidden",
      _h._gen_counts(db, "proj", "timid") == (0, 10)
      and _h._gen_counts(db, "proj", "bold") == (0, 1))
# At this size the prior still dominates both, so compare the records where
# the difference can show: a hundred quiet misses against twenty confident
# ones. The counts say the first generator is five times worse; the weights
# say it is better, because it never claimed otherwise.
many_timid = (0.0, 100 * _h.surprise(0.05, False))
few_bold = (0.0, 20 * _h.surprise(0.6, False))
check("and boldness follows the weights, so the timid one keeps more of it",
      _h._birth_strength(many_timid, (0, 0)) > _h._birth_strength(few_bold, (0, 0)),
      (_h._birth_strength(many_timid, (0, 0)), _h._birth_strength(few_bold, (0, 0))))
# Under flat counting the timid generator would have been driven to the floor
# by ten losses (0.35 - 0.8). The weighting is what stops that.
check("ten flat misses take it well below the house rate, without pretending "
      "ten is certainty",
      _h.STRENGTH_FLOOR < _h._birth_strength((0, 10), (0, 0)) < 0.2,
      _h._birth_strength((0, 10), (0, 0)))

print("== families are weighted the same way, and reported unweighted ==")
db = fresh()
rows = (("h1", 0.6, "refuted"), ("h2", 0.05, "refuted"),
        ("h3", 0.05, "supported"), ("h4", 0.4, "open"))
for hid, strength, status in rows:
    db.execute("INSERT INTO hypotheses VALUES(?,'proj','s','wants_pdf','b','g','c',"
               "?,?,'{}',0,?,0,0)", (hid, strength, status, hid))
db.commit()
counts = _h._family_records(db, "proj")
wts = _h._family_records(db, "proj", weighted=True)
check("counts are whole verdicts and ignore the open case",
      counts["wants"] == (1, 2), counts)
check("the weighted view scores the same verdicts by what they taught",
      close(wts["wants"][0], 0.95) and close(wts["wants"][1], 0.65), wts)
check("calibration() reports the counts, because that is what a person reads",
      _h.calibration(db, "proj")["families"]["wants"]["refuted"] == 2)

print("== the commons never sees a weight ==")
db = fresh()
_h._score_generator(db, "proj", "prior:p-1", True, 0.05)
_h._score_generator(db, "proj", "prior:p-1", False, 0.05)
_h._score_generator(db, "proj", "prior:p-1", True, 0.05)
rows = _h.calibration_bank(db, ["proj"])
gen = [r for r in rows if r["scope"] == "generator_class"]
check("the bank contributes a generator class with integer counts",
      len(gen) == 1 and gen[0]["name"] == "prior"
      and gen[0]["supported"] == 2 and gen[0]["refuted"] == 1, gen)
check("and every contributed number is an int, never a weight",
      all(isinstance(r[k], int) for r in rows
          for k in ("supported", "refuted")), rows)

print("== the upgrade, which every existing install has to survive ==")
db = sqlite3.connect(":memory:")
db.row_factory = sqlite3.Row
# The table exactly as it stood before weighting existed.
db.execute("CREATE TABLE leap_generators(project_id TEXT NOT NULL, "
           "generator TEXT NOT NULL, wins INTEGER NOT NULL, "
           "losses INTEGER NOT NULL, PRIMARY KEY(project_id, generator))")
db.execute("INSERT INTO leap_generators VALUES('proj','customer:old',9,1)")
db.commit()
cols = {r["name"] for r in db.execute("PRAGMA table_info(leap_generators)")}
check("the old table genuinely lacks the columns", "w_wins" not in cols, cols)
_h.ensure_schema(db)
cols = {r["name"] for r in db.execute("PRAGMA table_info(leap_generators)")}
check("ensure_schema adds them without dropping anything",
      {"w_wins", "w_losses"} <= cols
      and db.execute("SELECT wins FROM leap_generators").fetchone()["wins"] == 9,
      cols)
check("a row written before weighting keeps what it earned rather than resetting",
      _h._gen_record(db, "proj", "customer:old") == (9.0, 1.0),
      _h._gen_record(db, "proj", "customer:old"))
_h._score_generator(db, "proj", "customer:old", True, 0.35)
check("and the first weighted verdict builds on it instead of starting over",
      close(_h._gen_record(db, "proj", "customer:old")[0], 9.65),
      _h._gen_record(db, "proj", "customer:old"))
_h.ensure_schema(db)
check("running the migration twice is not an error",
      _h._gen_counts(db, "proj", "customer:old") == (10, 1))

print("== the bulk read agrees with the single read ==")
db = fresh()
_h._score_generator(db, "proj", "customer:a", True, 0.2)
_h._score_generator(db, "proj", "customer:b", False, 0.5)
_h._score_generator(db, "other", "customer:c", True, 0.2)
recs = _h._gen_records(db, "proj")
check("_gen_records returns this project's generators only",
      set(recs) == {"customer:a", "customer:b"}, recs)
check("and each record matches what _gen_record returns for it",
      all(recs[g] == _h._gen_record(db, "proj", g) for g in recs), recs)

print("== boldness is a probability, anchored on what this install does ==")
check("with no record at all, a hunch is born at the house rate",
      _h._birth_strength((0.0, 0.0), (0, 0), 0.4) == 0.4,
      _h._birth_strength((0.0, 0.0), (0, 0), 0.4))
check("one win moves it a little off that rate",
      0.4 < _h._birth_strength((1.0, 0.0), (0, 0), 0.4) < 0.55,
      _h._birth_strength((1.0, 0.0), (0, 0), 0.4))
check("thirty wins move it a great deal further",
      _h._birth_strength((30.0, 0.0), (0, 0), 0.4)
      > _h._birth_strength((1.0, 0.0), (0, 0), 0.4) + 0.09)
check("a hunch is never born stronger than the ceiling, whatever its record",
      _h._birth_strength((10000.0, 0.0), (0, 0), 0.9) == _h.STRENGTH_CEILING)
check("nor weaker than the floor",
      _h._birth_strength((0.0, 10000.0), (0, 0), 0.1) == _h.STRENGTH_FLOOR)
check("the family record counts, at half the weight of the generator's own",
      _h._birth_strength((0.0, 0.0), (4, 0), 0.4)
      < _h._birth_strength((4.0, 0.0), (0, 0), 0.4))

print("== and the house rate is learned, not assumed ==")
check("an install with no verdicts falls back to BASE_STRENGTH",
      _h._house_rate([]) == _h.BASE_STRENGTH, _h._house_rate([]))
check("an install whose hunches keep landing raises it",
      _h._house_rate([(40, 10)]) > 0.6, _h._house_rate([(40, 10)]))
check("one whose hunches keep failing lowers it",
      _h._house_rate([(10, 40)]) < 0.3, _h._house_rate([(10, 40)]))
check("and four verdicts barely move it, because four verdicts are not a rate",
      abs(_h._house_rate([(4, 0)]) - _h.BASE_STRENGTH) < 0.12,
      _h._house_rate([(4, 0)]))

print("\n%d passed, %d failed" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)
