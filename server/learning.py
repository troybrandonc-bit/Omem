"""OMEM learning loop: utility feedback closes the recall loop.

OMEM already learns in three ways (reinforcement of repeated observations,
time-decay via memory classes/TTL, and consolidation of repeated patterns into
generalizations). The missing piece was a UTILITY signal: does the system know
whether a recalled memory was actually *useful*, and does that feed back into
what it surfaces next time?

This module computes a per-memory utility score from signals the system already
collects — explicit "useful"/"incorrect" feedback (feedback table) and recall
frequency (recall_counts) — and exposes it to the ranker as a soft tie-break.
Memories that repeatedly prove useful drift ahead of equally-ranked memories
that don't; memories marked incorrect drift back. The engine's belief state and
the deterministic tier ordering are untouched — utility only orders *within* a
tier, and ties still break on assertion id, so ranking stays reproducible.

This is the concrete, verifiable version of "gets better with time": recall
quality improves as usage accumulates, without any model in the loop.
"""
from __future__ import annotations

# Weights: explicit feedback dominates; recall frequency is a weak prior (a
# memory recalled often *may* be useful, but usefulness is what we reward).
_W_USEFUL = 1.0
_W_INCORRECT = -1.5      # a wrong memory should fall faster than a useful one rises
_W_RECALL = 0.05        # mild prior from being surfaced repeatedly
_RECALL_CAP = 20        # don't let raw recall count dominate real feedback


def utility_scores(db, project_id: str) -> dict[str, float]:
    """assertion_id -> utility score for this project, from EXPLICIT feedback
    (useful/incorrect). Higher = more useful over time.

    Deliberately does NOT factor in raw recall frequency: recall itself
    increments recall_counts, so using it here would make two identical
    back-to-back recalls return different orderings (a memory recalled once ranks
    differently on the very next call). Learning must come from a genuine
    external signal — whether the memory was *useful* — not from the act of
    surfacing it, which would be a self-reinforcing loop. Recall frequency
    remains available for analytics; it just doesn't drive ranking."""
    scores: dict[str, float] = {}
    try:
        rows = db.execute(
            "SELECT assertion_id, kind, COUNT(*) AS c FROM feedback "
            "WHERE project_id=? AND assertion_id IS NOT NULL GROUP BY assertion_id, kind",
            (project_id,)).fetchall()
        for r in rows:
            aid = r["assertion_id"]
            kind = r["kind"]
            c = r["c"] if "c" in r.keys() else r[2]
            if kind == "useful":
                scores[aid] = scores.get(aid, 0.0) + _W_USEFUL * c
            elif kind == "incorrect":
                scores[aid] = scores.get(aid, 0.0) + _W_INCORRECT * c
    except Exception:
        pass
    return scores


def utility_rank_key(score: float) -> int:
    """Convert a utility score into a small integer sort key (lower sorts first,
    matching the ranker's ascending sort). Bucketed so tiny score differences
    don't cause churn — only meaningful utility differences reorder memories."""
    # bucket into: strongly-useful(-2), useful(-1), neutral(0), harmful(+1)
    if score >= 2.0:
        return -2
    if score >= 0.5:
        return -1
    if score <= -1.0:
        return 1
    return 0
