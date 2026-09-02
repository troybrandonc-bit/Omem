"""The calibration benchmark scores forecasts, and the scoring must be right.
Run: python3 tests_calibration_benchmark.py

A benchmark nobody checks is a number nobody should believe, so the arithmetic
is pinned against hand-computed values rather than against itself. The cases
that matter are the degenerate ones: a perfect forecaster, a useless one, and
the two situations where the honest answer is "not measurable" rather than a
number.
"""
import os
import sqlite3
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "benchmarks", "calibration"))

import score  # noqa: E402
import run as runner  # noqa: E402
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


print("== the constants match the engine they describe ==")
check("STRENGTH_FLOOR agrees with hypotheses.py",
      score.STRENGTH_FLOOR == _h.STRENGTH_FLOOR, (score.STRENGTH_FLOOR, _h.STRENGTH_FLOOR))
check("STRENGTH_CEILING agrees with hypotheses.py",
      score.STRENGTH_CEILING == _h.STRENGTH_CEILING,
      (score.STRENGTH_CEILING, _h.STRENGTH_CEILING))

print("== brier, by hand ==")
# (0.4-1)^2 + (0.4-0)^2 = 0.36 + 0.16 = 0.52, over 2 = 0.26
check("brier of two opposite outcomes at 0.4",
      close(score.brier([(0.4, True), (0.4, False)]), 0.26),
      score.brier([(0.4, True), (0.4, False)]))
check("a perfect forecaster scores 0",
      close(score.brier([(1.0, True), (0.0, False)]), 0.0))
check("an inverted forecaster scores 1",
      close(score.brier([(0.0, True), (1.0, False)]), 1.0))
check("no rows scores nothing, not zero", score.brier([]) is None)

print("== skill is measured against predicting the base rate ==")
# Base rate 0.5, so the reference brier is 0.25. Forecasts of 0.4/0.4 give
# 0.26, which is WORSE than climatology: skill must be negative.
s = score.brier_skill([(0.4, True), (0.4, False)])
check("a forecast no better than the base rate scores <= 0", s is not None and s <= 0, s)
check("a perfect forecaster has skill 1",
      close(score.brier_skill([(1.0, True), (0.0, False)]), 1.0))
check("all-one-outcome is not measurable, and says so, rather than scoring 0",
      score.brier_skill([(0.4, True), (0.9, True)]) is None)

print("== the report tells the truth about the ceiling ==")
# Hunches landing 90% of the time, born at the 0.6 cap: not a calibration
# failure, a floor the design imposes. The report has to say which.
rep = score.report([(0.6, True)] * 9 + [(0.6, False)])
check("precision is reported", close(rep["precision"], 0.9), rep)
check("the ceiling caveat fires when outcomes beat the cap",
      "capped at" in rep.get("note", ""), rep.get("note"))
rep2 = score.report([(0.3, True), (0.3, False), (0.3, True), (0.3, False)])
check("an uninformative strength is called out as uninformative",
      "carries no information" in rep2.get("note", ""), rep2.get("note"))
check("an empty record reports n=0 rather than dividing by zero",
      score.report([])["n"] == 0)

print("== reliability bands ==")
bands = score.reliability([(0.1, False), (0.1, False), (0.55, True), (0.55, True)])
check("bands are only emitted where there is data", len(bands) == 2, bands)
low = [b for b in bands if b["predicted"] == 0.1][0]
check("a band that never lands reports observed 0 and a negative gap",
      low["observed"] == 0.0 and low["gap"] < 0, low)
high = [b for b in bands if b["predicted"] == 0.55][0]
check("a band that always lands reports a positive gap", high["gap"] > 0, high)

print("== reading a real hypotheses table ==")
db = sqlite3.connect(":memory:")
db.row_factory = sqlite3.Row
db.executescript(_h.HYPOTHESES_SCHEMA)
rows = (("h1", "proj", 0.5, "supported"), ("h2", "proj", 0.2, "refuted"),
        ("h3", "proj", 0.4, "open"), ("h4", "other", 0.6, "supported"))
for hid, proj, strength, status in rows:
    db.execute("INSERT INTO hypotheses VALUES(?,?,'s','prefers_email','b','g','c',?,?,"
               "'d',0,'fp',0,0)", (hid, proj, strength, status))
db.commit()

pairs = runner.pairs_from(db, None)
check("only resolved hypotheses are scored, never the open ones",
      len(pairs) == 3, pairs)
check("the birth strength is what gets scored",
      sorted(p for p, _ in pairs) == [0.2, 0.5, 0.6], pairs)
check("a project filter narrows the record",
      len(runner.pairs_from(db, "proj")) == 2, runner.pairs_from(db, "proj"))
check("the renderer produces a report rather than raising",
      "resolved hypotheses" in score.render(score.report(pairs)))

print("\n%d passed, %d failed" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)
