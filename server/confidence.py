"""Effective confidence: the number the engine stored and nothing ever read.

Assertions have carried a confidence field since the engine's first commit,
and no read path ever used it -- not ranking, not /why, not the pack. A
caller who carefully scored a claim 0.9 and one who scored it 0.3 got
identical treatment everywhere, which made the field decorative and the
careful caller a fool.

This module is the one place the arithmetic lives:

  base            the stated confidence, or 0.6 when none was stated -- an
                  unqualified claim is better than a coin flip and worse
                  than one somebody actually scored
  corroboration   +0.1 per independent observation, capped at three. What
                  counts as independent is a DISTINCT (observer, source)
                  pair: a thousand copies of one email are one observation,
                  because a lie repeated is not evidence
  ceiling         0.99, always. Certainty is not a thing this system claims
                  about the world; the cap is the honesty, not a rounding

And the two things it deliberately is NOT:

  not truth       belief state is the engine's alone. A contradicted claim
                  can carry high support on both sides -- that is exactly
                  what CONTRADICTED means -- so this number never feeds a
                  truth decision, only ordering and display
  not decayed     decay needs a clock, and assertion-time is LOGICAL time.
                  Aging beliefs by a counter that advances per-write would
                  punish busy projects and flatter idle ones. When wall-time
                  provenance is reliable enough to decay against, decay can
                  come back as a declared policy; guessing is worse than
                  abstaining

Derived conclusions already arrive here honest: the rules engine writes them
with the minimum of their premises' confidences, so support propagates at
formation and is not re-derived at read time.

Deterministic, recomputable, engine-untouched: same inputs, same number,
and deleting every output changes no belief.
"""
from __future__ import annotations

DEFAULT_UNSTATED = 0.6
CORROBORATION_STEP = 0.1
CORROBORATION_CAP = 3
CEILING = 0.99


def bulk_support(db, project_id: str, assertion_ids) -> dict:
    """{assertion_id: distinct independent observations}, one query per 500
    ids. Distinctness is (observed_by, source): the same connector reading
    the same mail twice corroborates nothing."""
    ids = [a for a in assertion_ids if a]
    out: dict = {}
    for i in range(0, len(ids), 500):
        chunk = ids[i:i + 500]
        marks = ",".join("?" for _ in chunk)
        for r in db.execute(
                "SELECT assertion_id, COUNT(DISTINCT observed_by || '|' || "
                "COALESCE(source,'')) AS n FROM memory_reinforcements "
                f"WHERE project_id=? AND assertion_id IN ({marks}) "
                "GROUP BY assertion_id", [project_id] + chunk):
            out[r["assertion_id"]] = int(r["n"])
    return out


def effective(base, support: int = 0) -> tuple[float, list]:
    """(score, reasons). The reasons are the audit: every adjustment names
    itself, so a surprising number is a readable derivation, not a shrug."""
    reasons = []
    if base is None:
        score = DEFAULT_UNSTATED
        reasons.append(f"no stated confidence, treated as {DEFAULT_UNSTATED:g}")
    else:
        score = max(0.0, min(1.0, float(base)))
        reasons.append(f"stated {score:g}")
    n = min(CORROBORATION_CAP, max(0, int(support or 0)))
    if n:
        score += CORROBORATION_STEP * n
        reasons.append(
            f"+{CORROBORATION_STEP * n:g} for {n} independent "
            f"corroboration{'s' if n > 1 else ''}"
            + (" (capped)" if support > CORROBORATION_CAP else ""))
    if score > CEILING:
        score = CEILING
        reasons.append(f"held at {CEILING:g}: certainty is not claimed")
    return round(score, 2), reasons


def bucket(score: float) -> int:
    """A coarse rank key (0..4). Ranking uses buckets, not raw floats, so a
    0.01 difference cannot reorder memories and determinism survives
    arithmetic drift."""
    return max(0, min(4, int(score * 5)))
