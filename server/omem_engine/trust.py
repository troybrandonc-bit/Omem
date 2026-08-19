"""Phase 9 — trust engine (Model 16.3 only; ordering, never numeric value).

OMEM standardizes ONLY the monotonic ordering constraints (16.3); the numeric method
is non-normative (16.5) and MUST NOT appear in a snapshot (CTS 4.5). This module
therefore exposes only the required PARTIAL ORDER relations, as pairwise constraints:

  16.3(a) grounded >= otherwise-identical ungrounded
  16.3(b) open >= otherwise-identical closed (evaluated in-interval)

trust_order returns the set of mandated (>=) pairs among the probed assertions; the
CTS compares this as a subset-consistency check (only the required relations appear,
4.5), never as a total order or numeric value.
"""

from __future__ import annotations

from typing import List, Set, Tuple

from .interval import IntervalLedger
from .provenance import DerivationGraph
from .store import Store


class TrustEngine:
    def __init__(self, store: Store, ledger: IntervalLedger, graph: DerivationGraph) -> None:
        self.store = store
        self.ledger = ledger
        self.graph = graph

    def _otherwise_identical(self, a_id: str, b_id: str) -> bool:
        """16.3 (I-4): same subject-set, proposition, agent, assertion-time, event-time,
        confidence — differing only in grounding or open/closed status."""
        a = self.store.assertion(a_id)
        b = self.store.assertion(b_id)
        if a is None or b is None:
            return False
        return (frozenset(a.subjects) == frozenset(b.subjects)
                and a.proposition == b.proposition
                and a.agent == b.agent
                and a.assertion_time == b.assertion_time
                and a.event_time == b.event_time
                and a.confidence == b.confidence)

    def trust_order(self, assertion_ids: List[str], T: int) -> Set[Tuple[str, str]]:
        """Return mandated (x, y) meaning trust(x) >= trust(y), for probed assertions,
        per 16.3 only. Pairs not mandated by 16.3 are omitted (non-normative, 16.5)."""
        pairs: Set[Tuple[str, str]] = set()
        ids = list(assertion_ids)
        for x in ids:
            for y in ids:
                if x == y:
                    continue
                if not self._otherwise_identical(x, y):
                    continue
                gx = self.graph.is_grounded(x)
                gy = self.graph.is_grounded(y)
                # 16.3(a): grounded >= ungrounded
                if gx and not gy:
                    pairs.add((x, y))
                # 16.3(b): open >= closed (in-interval). Openness at T.
                ax, ay = self.store.assertion(x), self.store.assertion(y)
                ox = self.ledger.is_open_at(ax, T)
                oy = self.ledger.is_open_at(ay, T)
                if ox and not oy:
                    pairs.add((x, y))
        return pairs
