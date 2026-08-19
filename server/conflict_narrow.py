"""P7 narrow conflict query. The decision layer needs conflicts only for the
handful of CANDIDATE assertions in a pack, not for every open assertion in the
project. engine.conflicts(T) computes all O(n²) pairs; this computes the same
pairs restricted to the candidate neighbourhood.

It does NOT reimplement contradiction semantics. It REUSES the frozen engine's
own predicates:
    engine.prop._reduced_subject_set   (same-referent test, coreference-scoped)
    engine.prop.contra.contradicts     (the declared-contradiction predicate)
    engine.prop._open_assertions_at    (open-at-T filter)
so for any candidate the result is byte-identical to filtering the full
engine.conflicts(T) down to pairs touching that candidate — proven in
tests_p7_conflict_equiv.py. The engine remains the sole authority; this only
avoids computing conflicts we will never look at.
"""
from __future__ import annotations

try:
    from omem_engine.canon import proposition_identical, RETRACTED
except Exception:  # pragma: no cover - import shape fallback
    proposition_identical = None
    RETRACTED = "__retracted__"


def conflicts_for(engine, candidate_ids, T, pview=None):
    """Return the set of frozenset({a_id, b_id}) conflict pairs in which at
    least one side is a candidate. Identical verdicts to
    {pair for pair in engine.conflicts(T) if pair & set(candidate_ids)},
    but evaluated only over each candidate's same-subject neighbourhood.

    pview (optional): a PartitionView at T. When supplied, reduced-subject-set
    computations reuse its cached partition instead of rebuilding per call —
    same values, less work."""
    prop = engine.prop
    cand = [cid for cid in dict.fromkeys(candidate_ids)]
    if not cand:
        return set()
    store = engine.store
    # open assertions at T, indexed by id — the engine's own open filter
    open_list = prop._open_assertions_at(T)
    open_by_id = {a.id: a for a in open_list}

    def _rss(subjects):
        if pview is not None:
            return pview.reduced_subject_set(subjects)
        return prop._reduced_subject_set(subjects, T)
    # precompute reduced subject sets once per open assertion (the expensive
    # part of the pairwise scan) — but only for assertions that SHARE a subject
    # with some candidate, which is all a same-referent conflict can involve.
    cand_subject_union = set()
    for cid in cand:
        a = open_by_id.get(cid)
        if a is not None:
            cand_subject_union.update(a.subjects)
    relevant = [a for a in open_list if cand_subject_union.intersection(a.subjects)]
    rss = {a.id: _rss(a.subjects) for a in relevant}

    def is_retracted(p):
        if proposition_identical is not None:
            return proposition_identical(p, RETRACTED)
        return p == RETRACTED

    result = set()
    cand_set = set(cand)
    for cid in cand:
        a = open_by_id.get(cid)
        if a is None or is_retracted(a.proposition):
            continue
        a_rss = rss.get(cid)
        for b in relevant:
            if b.id == cid:
                continue
            # avoid double-adding a cand/cand pair; the frozenset dedups anyway
            if b.id in cand_set and b.id < cid:
                continue
            if is_retracted(b.proposition):
                continue
            if rss.get(b.id) != a_rss:
                continue
            if not prop.contra.contradicts(a.proposition, b.proposition):
                continue
            result.add(frozenset({cid, b.id}))
    return result
