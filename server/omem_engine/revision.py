"""Phase 5 — revision engine (Model 13; N5 strict time; N10 retraction; C1 chain order).

Supersession (13.1): recording a new Assertion, a supersession Derivation from new ->
superseded, and closing each superseded interval at the new Assertion's assertion-time.
N5: the new assertion-time MUST be strictly greater than every superseded
assertion-time, else R_TEMPORAL (no zero-width intervals).
INV-4: a superseded (already closed) interval MUST NOT be reopened/re-closed => R_REOPEN.
INV-5: supersession is a Derivation and shares the one acyclic Derivation graph;
a supersession that would create a cycle => R_CYCLE (checked via the derivation graph).

Retraction (13.3, N10): supersede with the reserved proposition RETRACTED. After
retraction, proposition_state for the retracted proposition is UNKNOWN (13.3.1) —
enforced by the proposition engine (Phase 6), which excludes RETRACTED from A+/A-.

Revision chain (13.5, C1): the supersession-linked chain to and from an Assertion,
ordered by ascending assertion-time, ties broken by canonical-id order (Profile 4.2).
"""

from __future__ import annotations

from typing import List, Sequence, Set

from .canon import RETRACTED, identifier_order_key
from .coreference import CoreferenceRegistry
from .interval import IntervalLedger
from .primitives import Assertion, Derivation, KIND_SUPERSESSION
from .provenance import DerivationGraph
from .reasons import Rejected, R_REOPEN, R_TEMPORAL, R_DANGLING
from .store import Store


class RevisionEngine:
    def __init__(self, store: Store, ledger: IntervalLedger,
                 coref: CoreferenceRegistry, graph: DerivationGraph) -> None:
        self.store = store
        self.ledger = ledger
        self.coref = coref
        self.graph = graph

    def supersede(self, new_assertion: Assertion,
                  superseded_ids: Sequence[str],
                  derivation_id: str) -> None:
        """Record a supersession (Model 13.1). new_assertion must already be a
        well-formed Assertion (not yet stored). superseded_ids are the closed targets.
        """
        if not superseded_ids:
            raise Rejected(R_DANGLING, "supersession has no superseded target")
        # All targets must be recorded assertions (INV-6).
        for sid in superseded_ids:
            if self.store.assertion(sid) is None:
                raise Rejected(R_DANGLING, f"superseded not a recorded assertion: {sid}")
        # INV-4: a target already closed cannot be superseded again (reopen/re-close).
        for sid in superseded_ids:
            if self.ledger.is_closed(sid):
                raise Rejected(R_REOPEN, f"belief-interval already closed: {sid}")
        # N5: new assertion-time strictly greater than every superseded time.
        for sid in superseded_ids:
            tgt = self.store.assertion(sid)
            if new_assertion.assertion_time <= tgt.assertion_time:
                raise Rejected(
                    R_TEMPORAL,
                    f"supersession time {new_assertion.assertion_time} not strictly "
                    f"greater than superseded {tgt.assertion_time}",
                )
        # Record the new assertion (store enforces INV-1/2/3/6/7 for it).
        self.store.put_assertion(new_assertion)
        # Record the supersession derivation (graph enforces INV-5 acyclicity, INV-6).
        deriv = Derivation(derivation_id, new_assertion.id, tuple(superseded_ids),
                           KIND_SUPERSESSION)
        self.graph.add_derivation(deriv)  # may raise R_CYCLE / R_DANGLING
        # Close each superseded interval at the new assertion-time (13.1c).
        for sid in superseded_ids:
            self.ledger.close(sid, new_assertion.assertion_time)

    def retract(self, retracting_assertion: Assertion,
                target_id: str, derivation_id: str) -> None:
        """Retraction (Model 13.3, N10): supersede target with the reserved RETRACTED
        proposition. retracting_assertion.proposition MUST be RETRACTED."""
        if retracting_assertion.proposition != RETRACTED:
            raise Rejected(
                R_DANGLING,  # structural misuse; not an observable model op otherwise
                "retraction assertion must carry the reserved RETRACTED proposition",
            )
        self.supersede(retracting_assertion, [target_id], derivation_id)

    # ── revision chain (13.5, C1 order) ─────────────────────────────────────
    def revision_chain(self, assertion_id: str) -> List[str]:
        """Ordered list of assertion ids linked to/from assertion_id by supersession
        Derivation edges (the connected supersession component), ordered by
        (assertion_time, canonical-id) per C1."""
        if self.store.assertion(assertion_id) is None:
            return []
        # Build adjacency over supersession edges only (both directions).
        members: Set[str] = set()
        frontier = [assertion_id]
        while frontier:
            cur = frontier.pop()
            if cur in members:
                continue
            members.add(cur)
            for d in self.store.derivations():
                if d.kind != KIND_SUPERSESSION:
                    continue
                if d.consequent == cur:
                    for anc in d.antecedents:
                        if self.store.assertion(anc) is not None and anc not in members:
                            frontier.append(anc)
                if cur in d.antecedents:
                    if self.store.assertion(d.consequent) is not None and d.consequent not in members:
                        frontier.append(d.consequent)
        # C1: order by ascending assertion-time, ties by canonical-id order.
        def sort_key(aid: str):
            a = self.store.assertion(aid)
            return (a.assertion_time, identifier_order_key(aid))
        return sorted(members, key=sort_key)
