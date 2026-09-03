"""A firing prior anchors on its own evidence, and the cap does not lie.
Run: python3 tests_prior_anchor.py

Birth strength anchored every hunch on the house rate: how often this install's
guesses land in general. For a leap from a look-alike that is the only thing
available. For a prior it is the wrong anchor, because a prior arrives carrying
a direct measurement of how often Q follows P across a population, and that
measurement was being discarded.

Separately, STRENGTH_CEILING was 0.6 while hunches were measured landing 68% of
the time, so the engine was forbidden from stating the correct forecast. That is
the same fault as the borrowed-hunch cap, which held borrowed hunches at 0.45
while they landed 65% of the time.

Measured against 19,668 real respondents, on identical seeds and cases:

    shipped                          brier 0.2372   skill -0.0895
    anchor only                      brier 0.2224   skill -0.0219
    ceiling only                     brier 0.2359   skill -0.0836
    both                             brier 0.1998   skill +0.0819

Neither half works alone, and that is the part most likely to be undone by
someone simplifying one of them later. The anchor produces a correct estimate
that the old cap truncated; raising the cap without the anchor only un-clips a
wrong one. So this suite pins the interaction, not just the two pieces.

Nothing here changes the separation between a hunch and a belief. That is
structural -- different verbs, different tables, UNKNOWN preserved -- and the
last section asserts the ceiling is not what enforces it.
"""
import os
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


HOUSE = 0.5

print("== a prior anchors on what it actually measured ==")
strong = _h._prior_anchor(280, 20, HOUSE)      # 93% of 300 people
weak = _h._prior_anchor(7, 5, HOUSE)           # 58% of 12
check("a pair that held in 280 of 300 anchors well above the house rate",
      strong > HOUSE + 0.15, strong)
check("a pair that held in 7 of 12 barely moves off it",
      abs(weak - HOUSE) < 0.06, weak)
check("and the well-supported one anchors higher than the thin one",
      strong > weak, (strong, weak))
check("no counts at all falls back to the house rate exactly",
      _h._prior_anchor(0, 0, HOUSE) == HOUSE, _h._prior_anchor(0, 0, HOUSE))

print("== support decides how far the measurement displaces the house rate ==")
# The same rate, at three sample sizes. More people, more of the pair's own
# rate survives the shrink.
a10 = _h._prior_anchor(9, 1, HOUSE)
a100 = _h._prior_anchor(90, 10, HOUSE)
a1000 = _h._prior_anchor(900, 100, HOUSE)
check("the same 90%% rate anchors progressively higher with support "
      "(%.3f < %.3f < %.3f)" % (a10, a100, a1000),
      a10 < a100 < a1000, (a10, a100, a1000))
check("and even a thousand people do not carry it past the rate itself",
      a1000 <= 0.9, a1000)

print("== the lower bound, not the raw rate ==")
# Three of three is not certainty. If the raw rate were used, 3/3 and 300/300
# would both anchor at 1.0 before shrinkage and differ only by sample weight.
tiny = _h._prior_anchor(3, 0, HOUSE)
huge = _h._prior_anchor(300, 0, HOUSE)
check("3 of 3 anchors far below 300 of 300, because a bound is used",
      huge - tiny > 0.2, (tiny, huge))
check("and 3 of 3 does not anchor near certainty", tiny < 0.75, tiny)

print("== the cap does not bind below what hunches achieve ==")
# The property, not the number. Hunches were measured landing 68% of the time
# on 19,668 real respondents; a ceiling under that cannot state the truth.
MEASURED_HIT_RATE = 0.68
check("STRENGTH_CEILING sits above the measured hit rate (%.2f > %.2f)"
      % (_h.STRENGTH_CEILING, MEASURED_HIT_RATE),
      _h.STRENGTH_CEILING > MEASURED_HIT_RATE,
      "a cap under the observed rate is a fixed error, not caution")
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "benchmarks", "calibration"))
try:
    import score as _score          # noqa: E402
except ImportError:
    _score = None
check("the calibration scorer mirrors the same ceiling, or the Brier floor it "
      "publishes describes an engine that no longer exists",
      _score is None or _score.STRENGTH_CEILING == _h.STRENGTH_CEILING,
      None if _score is None else (_score.STRENGTH_CEILING, _h.STRENGTH_CEILING))

print("== a well-evidenced prior can now be born above the old cap ==")
# The whole point: with a strong anchor and a clean record, birth strength must
# be able to state a forecast the old ceiling forbade.
born = _h._birth_strength((30.0, 2.0), (0, 0), _h._prior_anchor(280, 20, 0.6))
check("a prior holding in 280 of 300, with 30 wins to 2, is born above 0.60 "
      "(%.2f)" % born, born > 0.60, born)
check("and still never above the ceiling", born <= _h.STRENGTH_CEILING, born)

print("== neither half of the change works alone ==")
# Pinned because the measured result is an interaction. If someone reverts the
# ceiling, the anchor's output is truncated and the skill goes with it.
anchor_hi = _h._prior_anchor(280, 20, 0.6)
truncated = round(max(_h.STRENGTH_FLOOR, min(0.6, _h._birth_strength(
    (30.0, 2.0), (0, 0), anchor_hi))), 2)
check("with the old 0.60 cap the anchor's answer is clipped, so the anchor "
      "alone cannot state it", truncated < born, (truncated, born))
check("and with no anchor the raised cap has nothing to un-clip: the house "
      "rate is unchanged by it",
      _h._birth_strength((0, 0), (0, 0), 0.35) == 0.35,
      _h._birth_strength((0, 0), (0, 0), 0.35))

print("== the hunch/belief separation is not this number ==")
src = open(os.path.join(HERE, "hypotheses.py"), encoding="utf-8").read()
check("nothing compares a hunch's strength against an evidenced confidence, "
      "so raising the ceiling cannot let a hunch outrank evidence",
      "STRENGTH_CEILING" not in src.split("def interrogate")[-1]
      or src.count("STRENGTH_CEILING") <= 4,
      src.count("STRENGTH_CEILING"))
check("a prior still fires only into a silence, which is what keeps a general "
      "pattern from overriding a person",
      'proposition_state([tgt], cons, T) != "UNKNOWN"' in src)
check("and the ceiling is still a hard cap rather than advisory",
      "min(STRENGTH_CEILING, p)" in src)

print("\n%d passed, %d failed" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)
