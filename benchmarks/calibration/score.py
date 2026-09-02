"""Is OMEM's boldness honest? Scoring, as pure functions.

`leap()` commits to a claim about a person before the evidence is in, and
records how bold it was (`strength`). Later reality labels the hypothesis
`supported` or `refuted`. That pairing -- a probability stated in advance and
an outcome recorded afterwards -- is a forecast, and forecasts have a
century of scoring behind them. This module borrows it rather than inventing
a number.

WHAT IS MEASURED

  precision      supported / (supported + refuted). How often a hunch lands.
                 On its own it says nothing about calibration: a system that
                 only ever guesses the obvious scores well and is useless.

  brier          mean((strength - outcome)^2), outcome 1 or 0. Lower is
                 better. Rewards being right AND being appropriately unsure.

  brier_skill    1 - brier / brier_of_always_predicting_the_base_rate.
                 THE number. A Brier score alone is unreadable, because 0.2 is
                 excellent for a rare event and terrible for a coin flip. Skill
                 is the comparison against the only baseline that needs no
                 model: always predict how often hunches land in general.
                 Positive means birth strength carries information. Zero or
                 below means it does not, whatever the precision says.

  reliability    per strength band: what was predicted against what happened.
                 Where a single number hides a system that is confident in the
                 wrong places, this shows it.

A NOTE THE NUMBERS CANNOT SPEAK FOR THEMSELVES

`_birth_strength` clamps strength to [STRENGTH_FLOOR, STRENGTH_CEILING] =
[0.05, 0.6], deliberately, so a hunch can never dress as evidence. If hunches
actually land more often than 60% of the time, the Brier score is then
penalising OMEM for a floor its own design imposes, and the honest reading is
"systematically underconfident by construction", not "badly calibrated". The
report says so itself rather than leaving it to be discovered.

Stdlib only, no I/O: everything here takes a list of (strength, outcome).
"""
from __future__ import annotations

# Mirrors hypotheses.STRENGTH_FLOOR / STRENGTH_CEILING. Duplicated rather than
# imported so the scorer stays usable against a JSON dump from any install,
# including one running a different version; drift is caught by
# tests_calibration_benchmark.py, which asserts the two agree.
STRENGTH_FLOOR = 0.05
STRENGTH_CEILING = 0.6

BANDS = ((0.0, 0.2), (0.2, 0.35), (0.35, 0.5), (0.5, 1.01))


def _clean(pairs):
    out = []
    for p, o in pairs:
        p = float(p)
        if not (0.0 <= p <= 1.0):
            continue                       # a strength outside [0,1] is not a forecast
        out.append((p, 1 if o else 0))
    return out


def brier(pairs) -> float | None:
    rows = _clean(pairs)
    if not rows:
        return None
    return sum((p - o) ** 2 for p, o in rows) / len(rows)


def base_rate(pairs) -> float | None:
    rows = _clean(pairs)
    if not rows:
        return None
    return sum(o for _, o in rows) / len(rows)


def brier_skill(pairs) -> float | None:
    """Against the climatology baseline: always predict the base rate.

    Undefined when every outcome is the same, because then the baseline is
    perfect and the ratio divides by zero. Returning None there is the honest
    answer; a benchmark that reports 0.0 for "not measurable" is lying
    quietly."""
    rows = _clean(pairs)
    if not rows:
        return None
    b = base_rate(rows)
    ref = sum((b - o) ** 2 for _, o in rows) / len(rows)
    if ref == 0:
        return None
    return 1 - (brier(rows) / ref)


def reliability(pairs) -> list[dict]:
    """Per band: how bold OMEM was, and how often it was right to be."""
    rows = _clean(pairs)
    out = []
    for lo, hi in BANDS:
        band = [(p, o) for p, o in rows if lo <= p < hi]
        if not band:
            continue
        out.append({
            "band": f"{lo:.2f}-{min(hi, 1.0):.2f}",
            "n": len(band),
            "predicted": round(sum(p for p, _ in band) / len(band), 3),
            "observed": round(sum(o for _, o in band) / len(band), 3),
        })
    for b in out:
        b["gap"] = round(b["observed"] - b["predicted"], 3)
    return out


def report(pairs) -> dict:
    rows = _clean(pairs)
    n = len(rows)
    if not n:
        return {"n": 0, "note": "no resolved hypotheses; nothing to score"}
    rate = base_rate(rows)
    rep = {
        "n": n,
        "precision": round(rate, 3),
        "brier": round(brier(rows), 4),
        "brier_skill": None if brier_skill(rows) is None else round(brier_skill(rows), 4),
        "base_rate": round(rate, 3),
        "mean_strength": round(sum(p for p, _ in rows) / n, 3),
        "reliability": reliability(rows),
    }
    # The ceiling caveat, stated by the report rather than left to the reader.
    if rate > STRENGTH_CEILING:
        rep["note"] = (
            "Hunches land %.0f%% of the time but birth strength is capped at "
            "%.2f by design, so the engine cannot state a forecast this high. "
            "The Brier score below is therefore a floor imposed by the cap, not "
            "a calibration failure." % (rate * 100, STRENGTH_CEILING))
    elif rep["brier_skill"] is not None and rep["brier_skill"] <= 0:
        rep["note"] = (
            "Birth strength carries no information about the outcome: predicting "
            "the base rate for every hunch would score as well or better.")
    return rep


def render(rep: dict) -> str:
    if not rep.get("n"):
        return rep.get("note", "nothing to score")
    lines = [
        "resolved hypotheses  %d" % rep["n"],
        "precision            %.3f  (hunches that landed)" % rep["precision"],
        "mean birth strength  %.3f" % rep["mean_strength"],
        "brier                %.4f  (lower is better)" % rep["brier"],
        "brier skill          %s  (>0 means strength carries information)"
        % ("n/a" if rep["brier_skill"] is None else "%+.4f" % rep["brier_skill"]),
        "",
        "reliability by band",
        "  band        n   predicted  observed   gap",
    ]
    for b in rep["reliability"]:
        lines.append("  %-10s %3d      %.3f     %.3f  %+.3f"
                     % (b["band"], b["n"], b["predicted"], b["observed"], b["gap"]))
    if rep.get("note"):
        lines += ["", rep["note"]]
    return "\n".join(lines)
