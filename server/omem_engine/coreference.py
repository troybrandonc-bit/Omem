"""Phase 4 — coreference engine (Model 12; I-1 multiplicity; J-4 reflexive/symmetric).

A coreference Assertion claims two Entities are the same referent (12.2). It is an
ordinary Assertion with its own belief-interval, so "open at T" uses the interval
ledger (Phase 3). The referent partition at T is the transitive closure of the
"coreferent-at-T" relation (12.3/12.6, I-1):

  two Entities are coreferent at T iff >=1 coreference Assertion whose subjects are
  exactly those two Entities has an open belief-interval at T.

I-1: multiple coreference Assertions about the same pair are permitted; the pair is
coreferent while ANY one is open, and stops being coreferent only when EVERY such
Assertion is closed at T. Confidence MUST NOT affect the partition.

J-4: a coreference Assertion whose two Entities are identical is a permitted no-op on
the partition; coreference is symmetric (pair is unordered).

A split (12.4) is the supersession of a coreference Assertion — it closes that
Assertion's interval. Handled by the revision engine; here we simply read open/closed
status, so a split re-partitions automatically and losslessly (both Entities survive).
"""

from __future__ import annotations

from collections import OrderedDict
from typing import Dict, FrozenSet, List, Set

from .canon import identifier_order_key
from .interval import IntervalLedger
from .primitives import Assertion


class CoreferenceRegistry:
    """Tracks which assertion ids are coreference assertions and the (unordered)
    entity pair each one asserts. Populated by the store's corefer operation."""

    # How many distinct logical times to keep partitions for. A query answers at
    # one T, so a handful covers "the present" plus a few as-of reconstructions;
    # anything larger would hold memory for reconstructions nobody asks twice.
    _CACHE_SLOTS = 16

    def __init__(self) -> None:
        # assertion id -> frozenset({entity_a, entity_b}) (size 1 if self-coref, J-4)
        self._pairs: Dict[str, FrozenSet[str]] = {}
        self._version = 0
        # (registry version, ledger version, #assertions, #entities, T) -> partition.
        # See _cache_key for why that tuple is a sound identity for engine state.
        self._cache: "OrderedDict[tuple, Set[FrozenSet[str]]]" = OrderedDict()
        self._rep_cache: "OrderedDict[tuple, Dict[str, str]]" = OrderedDict()

    def register(self, assertion_id: str, entity_a: str, entity_b: str) -> None:
        # J-4: symmetric => store as unordered set; identical entities => size-1 set
        # (a no-op on the partition, but still a recorded coreference Assertion).
        self._pairs[assertion_id] = frozenset({entity_a, entity_b})
        self._version += 1
        self._cache.clear()
        self._rep_cache.clear()

    def is_coreference(self, assertion_id: str) -> bool:
        return assertion_id in self._pairs

    def pair(self, assertion_id: str) -> FrozenSet[str]:
        return self._pairs[assertion_id]

    # ── partition computation (12.3/12.6, I-1) ──────────────────────────────
    def _open_coreferent_pairs_at(
        self, assertions: Dict[str, Assertion], ledger: IntervalLedger, T: int
    ) -> List[FrozenSet[str]]:
        """All entity pairs that are coreferent at T (>=1 open coreference assertion,
        I-1). Self-pairs (size 1, J-4) contribute nothing to closure and are skipped."""
        pairs: List[FrozenSet[str]] = []
        for aid, ent_pair in self._pairs.items():
            if len(ent_pair) < 2:
                continue  # J-4 self-coreference: no effect on partition
            a = assertions.get(aid)
            if a is None:
                continue
            if ledger.is_open_at(a, T):
                pairs.append(ent_pair)
        return pairs

    def _cache_key(self, all_entity_ids: Set[str], assertions: Dict[str, Assertion],
                   ledger: IntervalLedger, T: int) -> tuple:
        """A tuple that changes whenever the partition at T could change.

        The store is append-only and primitives are frozen, so entity and assertion
        counts only ever grow and a change of either is a change of one. Coreference
        registrations bump this registry's version, and interval closures bump the
        ledger's. Those four are the complete set of inputs partition_at reads, so
        equal keys mean an identical computation and the cached answer is the answer.

        Cheap on purpose: hashing the inputs themselves would cost more than the
        union-find this exists to avoid.
        """
        return (self._version, ledger.version, len(assertions), len(all_entity_ids), T)

    def _remember(self, cache: "OrderedDict", key: tuple, value):
        cache[key] = value
        while len(cache) > self._CACHE_SLOTS:
            cache.popitem(last=False)
        return value

    def representatives_at(
        self,
        all_entity_ids: Set[str],
        assertions: Dict[str, Assertion],
        ledger: IntervalLedger,
        T: int,
    ) -> Dict[str, str]:
        """entity id -> the canonical representative of its referent class at T.

        The partition as a lookup rather than a set of sets, because that is the
        shape every caller actually wanted. Reducing a subject set was previously
        a partition computation per subject, which is what made a single belief
        query quadratic in the size of the whole store; with this it is a dict
        lookup per subject.

        The representative is the class member smallest under the Profile 4.2
        unsigned-byte order, exactly as before. It is internal and unobservable —
        only equality of reduced sets is — but keeping it canonical keeps the
        choice reproducible across versions.
        """
        return self._index_at(all_entity_ids, assertions, ledger, T)[0]

    def _index_at(
        self,
        all_entity_ids: Set[str],
        assertions: Dict[str, Assertion],
        ledger: IntervalLedger,
        T: int,
    ):
        """(entity -> representative, representative -> class), computed once."""
        key = self._cache_key(all_entity_ids, assertions, ledger, T)
        hit = self._rep_cache.get(key)
        if hit is not None:
            return hit
        reps: Dict[str, str] = {}
        classes: Dict[str, FrozenSet[str]] = {}
        for cls in self.partition_at(all_entity_ids, assertions, ledger, T):
            rep = min(cls, key=identifier_order_key)
            classes[rep] = cls
            for member in cls:
                reps[member] = rep
        return self._remember(self._rep_cache, key, (reps, classes))

    def partition_at(
        self,
        all_entity_ids: Set[str],
        assertions: Dict[str, Assertion],
        ledger: IntervalLedger,
        T: int,
    ) -> Set[FrozenSet[str]]:
        """Referent partition at T: transitive closure of coreferent-at-T over the
        entities, with every entity appearing in exactly one class (singletons for
        entities in no open coreference)."""
        key = self._cache_key(all_entity_ids, assertions, ledger, T)
        hit = self._cache.get(key)
        if hit is not None:
            return hit
        # union-find over entity ids
        parent: Dict[str, str] = {e: e for e in all_entity_ids}

        def find(x: str) -> str:
            root = x
            while parent[root] != root:
                root = parent[root]
            while parent[x] != root:
                parent[x], x = root, parent[x]
            return root

        def union(x: str, y: str) -> None:
            rx, ry = find(x), find(y)
            if rx == ry:
                return
            # deterministic root: smaller under Profile 4.2 canonical byte order wins
            # (internal structure only, not observable, but reproducible across versions)
            if identifier_order_key(ry) < identifier_order_key(rx):
                rx, ry = ry, rx
            parent[ry] = rx

        for ent_pair in self._open_coreferent_pairs_at(assertions, ledger, T):
            a, b = tuple(ent_pair)
            if a in parent and b in parent:
                union(a, b)

        classes: Dict[str, Set[str]] = {}
        for e in all_entity_ids:
            classes.setdefault(find(e), set()).add(e)
        return self._remember(self._cache, key,
                              {frozenset(members) for members in classes.values()})

    def class_of(
        self,
        entity_id: str,
        all_entity_ids: Set[str],
        assertions: Dict[str, Assertion],
        ledger: IntervalLedger,
        T: int,
    ) -> FrozenSet[str]:
        """The coreference class containing entity_id at T.

        Resolved through the index rather than by scanning the partition for the
        member, so this is two dict lookups instead of a walk over every class. An
        entity the store has never seen is its own singleton, as before.
        """
        reps, classes = self._index_at(all_entity_ids, assertions, ledger, T)
        rep = reps.get(entity_id)
        if rep is None:
            return frozenset({entity_id})
        return classes[rep]
