"""P8 Step 1, request-scoped coreference reuse (infrastructure optimization).

The frozen engine's proposition_state() and _reduced_subject_set() rebuild the
coreference partition on EVERY call (coreference.partition_at). During one
pack build the time T and the open-assertion set are fixed, so that partition
is identical across all candidates, yet the engine recomputes it once per
candidate, giving O(n) partition rebuilds per pack (each O(n)), i.e. the
observed O(n²).

This module computes the partition ONCE (via the engine's own partition_at)
and reuses it to answer proposition_state / reduced_subject_set for every
candidate in that pack. It does NOT reimplement coreference, contradiction, or
belief semantics, it calls:

    engine.coref.partition_at(...)        the engine's partition (once)
    engine.prop.contra.contradicts(...)   the engine's contradiction predicate
    engine.canon.canon.proposition_identical / RETRACTED  (engine constants)

and applies the engine's exact class-reduction and A+/A- rules over the cached
partition. Proven byte-identical to per-candidate engine calls in
tests_p8_partition_equiv.py, across current/as_of/supersession/contradiction/
retraction/multi-agent/scoped state.

Scope & safety:
- One PartitionView is bound to (engine, T). Never shared across T or across
  projects/tenants (each build makes its own; the store is per-project).
- Read-only: it never mutates engine state.
- Bounded: holds one partition (a set of frozensets) + a member->class index.
- Deterministic: same inputs -> same partition (the engine guarantees this).
"""
from __future__ import annotations

try:
    from omem_engine.canon import proposition_identical, RETRACTED, identifier_order_key
    from omem_engine.proposition import (BELIEVED_TRUE, BELIEVED_FALSE,
                                         CONTRADICTED, UNKNOWN)
except Exception:  # pragma: no cover - fall back to string constants
    proposition_identical = None
    identifier_order_key = lambda s: s.encode("utf-8")  # noqa: E731
    RETRACTED = "__retracted__"
    BELIEVED_TRUE, BELIEVED_FALSE, CONTRADICTED, UNKNOWN = (
        "BELIEVED_TRUE", "BELIEVED_FALSE", "CONTRADICTED", "UNKNOWN")


def _prop_identical(a: str, b: str) -> bool:
    if proposition_identical is not None:
        return proposition_identical(a, b)
    return a == b


class PartitionView:
    """Cached coreference partition at a fixed T, plus engine-identical
    proposition_state / reduced_subject_set over it."""

    def __init__(self, engine, T: int):
        self.engine = engine
        self.T = T
        self.prop = engine.prop
        self.coref = engine.coref
        self.ledger = engine.ledger
        # snapshot the exact inputs the engine would use, at this T
        self._assertions = {a.id: a for a in engine.store.assertions()}
        self._all_ent = {e.id for e in engine.store.entities()}
        # THE partition - computed once via the engine's own algorithm
        self._partition = self.coref.partition_at(
            self._all_ent, self._assertions, self.ledger, T)
        # member -> its class, for O(1) class_of
        self._index: dict[str, frozenset] = {}
        for cls in self._partition:
            for m in cls:
                self._index[m] = cls
        # open assertions at T, computed once (engine's own filter)
        self._open = self.prop._open_assertions_at(T)

    # ── engine-identical primitives over the cached partition ──
    def class_of(self, entity_id: str) -> frozenset:
        return self._index.get(entity_id, frozenset({entity_id}))

    def reduced_subject_set(self, subjects) -> frozenset:
        """Mirror of prop._reduced_subject_set, using the cached partition and
        the engine's own canonical-representative rule (smallest member under
        the engine's identifier order, we reuse the class the engine built, and
        pick the representative exactly as the engine does: min over the class
        by the engine's key)."""
        reps = set()
        for s in subjects:
            cls = self.class_of(s)
            reps.add(self._rep(cls))
        return frozenset(reps)

    def _rep(self, cls: frozenset) -> str:
        # The engine picks the canonical representative as
        # min(cls, key=identifier_order_key) - we reuse that EXACT key function
        # imported from omem_engine.canon, so the representative is identical.
        return min(cls, key=identifier_order_key)

    def proposition_state(self, subjects, proposition: str) -> str:
        """Byte-identical to engine.proposition_state(subjects, proposition, T),
        computed against the cached partition/open-set."""
        query_S = self.reduced_subject_set(tuple(subjects))
        a_plus = a_minus = False
        for a in self._open:
            if _prop_identical(a.proposition, RETRACTED):
                continue
            if self.reduced_subject_set(a.subjects) != query_S:
                continue
            if _prop_identical(a.proposition, proposition):
                a_plus = True
            elif self.prop.contra.contradicts(a.proposition, proposition):
                a_minus = True
        if a_plus and a_minus:
            return CONTRADICTED
        if a_plus:
            return BELIEVED_TRUE
        if a_minus:
            return BELIEVED_FALSE
        return UNKNOWN
