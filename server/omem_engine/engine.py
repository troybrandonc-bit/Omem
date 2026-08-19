"""OMEM reference engine — the abstract CTS interface (CTS 3.1 operations, 3.2 queries).

This facade is the entire observable surface (CTS 3.3). It wires the phase engines
together and maps each abstract operation/query to normative behavior. Operations
return ACCEPTED or raise Rejected(reason_code); the harness observes the code.

Logical identifiers are supplied by the caller (CTS 3.1) and used directly as the
implementation's primitive ids (the bijection is the identity map here, which is a
permitted Adapter choice, CTS 3.1).
"""

from __future__ import annotations

from typing import Dict, FrozenSet, List, Optional, Sequence, Set, Tuple

from .coreference import CoreferenceRegistry
from .interval import IntervalLedger
from .primitives import Entity, Event, Agent, Assertion, Derivation
from .proposition import PropositionEngine, ContradictionRegistry
from .provenance import DerivationGraph
from .reproducibility import repro_marker
from .revision import RevisionEngine
from .store import Store
from .timeline import TimelineEngine
from .trust import TrustEngine

ACCEPTED = "ACCEPTED"


class Engine:
    def __init__(self) -> None:
        self.store = Store()
        self.ledger = IntervalLedger()
        self.coref = CoreferenceRegistry()
        self.contra = ContradictionRegistry()
        self.graph = DerivationGraph(self.store)
        self.revision = RevisionEngine(self.store, self.ledger, self.coref, self.graph)
        self.prop = PropositionEngine(self.store, self.ledger, self.coref, self.contra)
        self.timeline_engine = TimelineEngine(self.store)
        self.trust = TrustEngine(self.store, self.ledger, self.graph)
        self._agent_seq = 0  # for recorded-existence when caller gives no time

    # ── declared contradiction pairs (CTS 5.2 / 7.2) ────────────────────────
    def declare_contradiction(self, token_a: str, token_b: str) -> None:
        """Non-normative harness hook: declare a contradiction pair for a vector."""
        self.contra.declare(token_a, token_b)

    # ── operations (CTS 3.1) ────────────────────────────────────────────────
    def put_entity(self, lid: str, type: str) -> str:
        self.store.put_entity(Entity(lid, type))
        return ACCEPTED

    def put_event(self, lid: str, kind: str, event_time: int,
                  event_end: Optional[int] = None) -> str:
        self.store.put_event(Event(lid, kind, event_time, event_end))
        return ACCEPTED

    def put_agent(self, lid: str, kind: str, recorded_existence: Optional[int] = None) -> str:
        # If the caller supplies no existence time, the agent exists from the current
        # logical position; we use 0 so any assertion-time >= 0 is temporally coherent
        # unless a vector explicitly sets a later existence (INV-7).
        rec = 0 if recorded_existence is None else recorded_existence
        self.store.put_agent(Agent(lid, kind, rec))
        return ACCEPTED

    def assert_(self, lid: str, agent_lid: str, subject_lids: Sequence[str],
                proposition: str, assertion_time: int,
                event_time: Optional[int] = None,
                confidence: Optional[float] = None) -> str:
        a = Assertion(lid, agent_lid, tuple(subject_lids), proposition,
                      assertion_time, event_time, confidence)
        self.store.put_assertion(a)
        return ACCEPTED

    def derive(self, consequent_lid: str, antecedent_lids: Sequence[str],
               kind: str, derivation_lid: str) -> str:
        d = Derivation(derivation_lid, consequent_lid, tuple(antecedent_lids), kind)
        self.graph.add_derivation(d)
        return ACCEPTED

    def supersede(self, new_assertion: Assertion, superseded_lids: Sequence[str],
                  derivation_lid: str) -> str:
        self.revision.supersede(new_assertion, list(superseded_lids), derivation_lid)
        return ACCEPTED

    def retract(self, retracting: Assertion, target_lid: str,
                derivation_lid: str) -> str:
        self.revision.retract(retracting, target_lid, derivation_lid)
        return ACCEPTED

    def corefer(self, assertion_lid: str, entity_lid_a: str, entity_lid_b: str,
                agent_lid: str, assertion_time: int) -> str:
        # A coreference Assertion (12.2): an ordinary Assertion whose subjects are the
        # two entities and whose proposition is a coreference claim. We register the
        # pair so the partition engine can read it.
        a = Assertion(assertion_lid, agent_lid, (entity_lid_a, entity_lid_b),
                      f"COREF({entity_lid_a},{entity_lid_b})", assertion_time)
        self.store.put_assertion(a)
        self.coref.register(assertion_lid, entity_lid_a, entity_lid_b)
        return ACCEPTED

    def split(self, coreference_assertion_lid: str, agent_lid: str,
              assertion_time: int, new_assertion_lid: str,
              derivation_lid: str) -> str:
        # Split (12.4) = supersede the coreference Assertion. The superseding assertion
        # is a retraction of the coreference claim (reserved RETRACTED marker, N10),
        # which closes the coreference interval so the partition re-separates.
        from .canon import RETRACTED
        retracting = Assertion(new_assertion_lid, agent_lid,
                               self._coref_subjects(coreference_assertion_lid),
                               RETRACTED, assertion_time)
        self.revision.supersede(retracting, [coreference_assertion_lid], derivation_lid)
        return ACCEPTED

    def _coref_subjects(self, coref_aid: str) -> Tuple[str, ...]:
        a = self.store.assertion(coref_aid)
        return a.subjects if a else ()

    # ── queries (CTS 3.2) ───────────────────────────────────────────────────
    def beliefs_about(self, entity_lid: str, T: int) -> Set[str]:
        return self.prop.beliefs_about(entity_lid, T)

    def proposition_state(self, subject_lids: Sequence[str], proposition: str, T: int) -> str:
        return self.prop.proposition_state(tuple(subject_lids), proposition, T)

    def referent_partition(self, T: int) -> Set[FrozenSet[str]]:
        all_ent = {e.id for e in self.store.entities()}
        assertions = {a.id: a for a in self.store.assertions()}
        return self.coref.partition_at(all_ent, assertions, self.ledger, T)

    def provenance(self, assertion_lid: str, T: int = None) -> Tuple[Set[str], str]:
        prov = self.graph.provenance(assertion_lid)
        grounded = "GROUNDED" if self.graph.is_grounded(assertion_lid) else "UNGROUNDED"
        return prov, grounded

    def revision_chain(self, assertion_lid: str) -> List[str]:
        return self.revision.revision_chain(assertion_lid)

    def timeline(self, T: int) -> List[str]:
        return self.timeline_engine.timeline(T)

    def conflicts(self, T: int) -> Set[FrozenSet[str]]:
        return self.prop.conflicts(T)

    def trust_order(self, assertion_lids: Sequence[str], T: int) -> Set[Tuple[str, str]]:
        return self.trust.trust_order(list(assertion_lids), T)

    def repro_marker(self, primitive_ids: Sequence[str], T: int,
                     confidences: Optional[Dict[str, float]] = None) -> str:
        return repro_marker(primitive_ids, T, confidences)
