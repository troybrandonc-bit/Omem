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

print("== the best-evidenced prior speaks, and local still outranks pooled ==")
# Only one prior may fire into a silence. It used to be whichever came first
# out of the tables, which is arbitrary among priors of equal standing. Sorting
# best-evidenced first is worth Brier 0.2006 -> 0.1950 on 19,668 respondents,
# and it cost nothing: at six local subjects the harness forms no local priors,
# so every reordering was among pooled rows and none was displaced. The tier
# stays the primary key anyway, because a real install does have local priors
# and a guarantee must not depend on their absence.
import sqlite3  # noqa: E402

ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "benchmarks", "scale"))
try:
    import leaping as _lp           # noqa: E402
except ImportError:
    _lp = None

SRC = open(os.path.join(HERE, "hypotheses.py"), encoding="utf-8").read()
check("the engine ranks prior rows by tier first, so a thin local prior still "
      "outranks a strong pooled one",
      'bool(r.get("pooled"))' in SRC and "prior_rows.sort(" in SRC)
check("and by the evidence behind each one second",
      "-_prior_anchor(r[" in SRC)

if _lp is None:
    check("leap harness available", False, "benchmarks/scale/leaping.py missing")
else:
    assertions, profs = _lp.world(40, 8, seed=3, hold=1.0)
    # Everyone holds both antecedents and nobody holds the consequent, in the
    # profiles AND in the store. A prior fires only into a silence, and if any
    # assertion of p005 survives, the resemblance pass projects it from a
    # look-alike first and `claimed` then locks the priors out entirely --
    # which is what the first version of this test actually measured.
    for _pa in profs.values():
        _pa[0].discard("p005")
    assertions = [a for a in assertions if a.proposition != "p005"]
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.executescript(_h.HYPOTHESES_SCHEMA)
    # Two priors race for one silence: one thin, one strong.
    for i2, (ant, cons, sup, ref) in enumerate(
            [("p000", "p005", 8, 6), ("p001", "p005", 400, 20)]):
        db.execute("INSERT INTO priors VALUES(?,'proj',?,?,'default',?,?,?,0)",
                   ("pr_%d" % i2, ant, cons, sup, ref, sup + ref))
    db.commit()
    op, pf = _h._declared_opposites, _h._profiles
    _h._profiles = lambda d_, p_, T_: profs
    _h._declared_opposites = lambda p_, prop_: set()
    try:
        _h.leap(_lp.FakeProject(assertions), db)
    finally:
        _h._profiles, _h._declared_opposites = pf, op
    rows = [dict(r) for r in db.execute(
        "SELECT subject, generator FROM hypotheses WHERE proposition='p005'")]
    check("a hunch was formed for the contested claim", bool(rows), rows)
    if rows:
        check("the better-evidenced prior is the one that spoke",
              all("pr_1" in r["generator"] for r in rows),
              [r["generator"] for r in rows])
        # One hunch per PERSON, not one overall: `claimed` is keyed on
        # (target, claim), so forty people each get their own, capped by
        # MAX_NEW_PER_RUN. What matters is that the second prior never adds a
        # second hunch about the same person's silence.
        per = {}
        for r in rows:
            per[r["subject"]] = per.get(r["subject"], 0) + 1
        check("one hunch per person, so agreeing priors are not double-counted "
              "into confidence they have not earned",
              per and max(per.values()) == 1, sorted(per.items())[:4])

print("== the external harness measures the engine, not a lookalike ==")
# It has diverged twice. It kept pair keys without their counts, so it could
# not anchor on them; and it walked priors in dict order while the engine
# sorted them. Either way it publishes a number about an engine that does not
# exist, which is worse than publishing nothing.
BIG5 = os.path.join(ROOT, "benchmarks", "external", "big5.py")
if os.path.exists(BIG5):
    H = open(BIG5, encoding="utf-8").read()
    check("the harness keeps the counts behind each pair, or it cannot anchor "
          "on them at all", "self.counts" in H)
    check("it anchors through the engine's own function rather than a copy",
          "_h._prior_anchor(" in H)
    check("and it applies the engine's selection rule rather than dict order",
          "self.rows.sort(" in H)
else:
    check("external harness present", False, BIG5)

print("\n%d passed, %d failed" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)
