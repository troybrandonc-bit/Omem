"""Phase 7 — provenance engine (Model 11, 15; INV-5 acyclicity; any-path grounding).

The Derivation graph is ONE acyclic graph over all derivation kinds (11.2, INV-5):
inference, supersession, coreference, etc. all share it. A derivation whose addition
would create a cycle is rejected R_CYCLE. Antecedents/consequent must exist (INV-6)
=> R_DANGLING.

Provenance (15.1): the set of primitives reachable from an Assertion by traversing
Derivation edges toward antecedents, transitively, terminating at Events or original
Assertions (no antecedents). It is a SET (dedup; diamonds collapse).

Grounding (15.3): GROUNDED iff traversal reaches AT LEAST ONE Event (any-path).
UNGROUNDED iff it terminates only in original Assertions with no Events.

Traversal terminates because the graph is acyclic (15.4 / INV-5).
"""

from __future__ import annotations

from typing import List, Set

from .primitives import Derivation
from .reasons import Rejected, R_CYCLE
from .store import Store


class DerivationGraph:
    """Wraps the store's derivation set with acyclicity enforcement on insert."""

    def __init__(self, store: Store) -> None:
        self.store = store

    def add_derivation(self, d: Derivation) -> Derivation:
        """Record a Derivation, enforcing invariants in order:
          INV-3 / INV-6 (id reuse, existence) — delegated to store.validate_derivation
          INV-5 (acyclicity) — enforced here, the single authority for cycles
        Existence is checked first because cycle detection traverses real edges."""
        self.store.validate_derivation(d)          # INV-3, INV-6 (single authority)
        if self._would_cycle(d):                   # INV-5 (single authority)
            raise Rejected(R_CYCLE, f"derivation would create a cycle: {d.id}")
        return self.store.record_derivation(d)

    def _successors_toward_antecedents(self, node_id: str) -> List[str]:
        """From a node, the antecedent primitives reachable via one derivation hop.
        Edges point consequent -> antecedent (direction of provenance traversal)."""
        out: List[str] = []
        for d in self.store.derivations():
            if d.consequent == node_id:
                out.extend(d.antecedents)
        return out

    def _would_cycle(self, new_d: Derivation) -> bool:
        # After adding new_d (consequent C -> antecedents A_i), a cycle exists iff
        # C is reachable from some A_i following consequent->antecedent edges,
        # INCLUDING the new edge. Equivalent: C reachable from any A_i in the graph
        # augmented with new_d. Since existing graph is acyclic, it suffices to check
        # whether C is reachable from any antecedent via existing edges, or an
        # antecedent equals C (self-derivation).
        C = new_d.consequent
        stack: List[str] = list(new_d.antecedents)
        seen: Set[str] = set()
        while stack:
            n = stack.pop()
            if n == C:
                return True
            if n in seen:
                continue
            seen.add(n)
            stack.extend(self._successors_toward_antecedents(n))
        return False

    # ── provenance & grounding (15.1, 15.3) ─────────────────────────────────
    def provenance(self, assertion_id: str) -> Set[str]:
        """Set of primitive ids reachable from the assertion toward antecedents,
        transitively (15.1). Excludes the starting assertion itself; includes all
        antecedent primitives (assertions and events) on the way to roots."""
        result: Set[str] = set()
        stack = list(self._successors_toward_antecedents(assertion_id))
        while stack:
            n = stack.pop()
            if n in result:
                continue
            result.add(n)
            stack.extend(self._successors_toward_antecedents(n))
        return result

    def is_grounded(self, assertion_id: str) -> bool:
        """GROUNDED iff any reachable primitive is an Event (15.3, any-path)."""
        for pid in self.provenance(assertion_id):
            if self.store.event(pid) is not None:
                return True
        return False
