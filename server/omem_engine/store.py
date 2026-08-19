"""Phase 2 — the immutable OMEM store.

An append-only ledger of the five primitives, enforcing the write-time invariants
with the exact CTS reason codes. The store holds ONLY primitives (INV-9: everything
else is a computed view built by later phases over this store).

Write-time invariants enforced here:
  INV-1  R_NO_AGENT    assertion's agent missing/unrecorded (8.1, 10.2)
  INV-2  R_NO_SUBJECT  assertion has no entity subject (8.1)
  INV-3  R_MUTATION    re-recording an existing id / mutating a primitive (7.2,9.3,11.5)
  INV-6  R_DANGLING    derivation/assert references an unrecorded primitive (11.2)
  INV-7  R_TEMPORAL    assertion-time precedes agent recorded-existence (14.1)
INV-4 (reopen), INV-5 (cycle), INV-8 (identity closure) are enforced by the phases
that own those operations (revision, provenance, coreference), which call back into
the store. The store exposes the primitive maps they need.

Determinism: insertion order is recorded (a monotonic sequence) purely so that
snapshots and any "record order" needs are reproducible; it is NEVER used as a
semantic tiebreak (14.6 forbids insertion-order tiebreaks — ordering uses canonical
ids). The sequence is an audit aid, not a semantic input.
"""

from __future__ import annotations

from typing import Dict, Iterable, List, Optional

from .primitives import Entity, Event, Agent, Assertion, Derivation
from .reasons import (
    Rejected, R_NO_AGENT, R_NO_SUBJECT, R_MUTATION, R_DANGLING, R_TEMPORAL,
)


class Store:
    def __init__(self) -> None:
        self._entities: Dict[str, Entity] = {}
        self._events: Dict[str, Event] = {}
        self._agents: Dict[str, Agent] = {}
        self._assertions: Dict[str, Assertion] = {}
        self._derivations: Dict[str, Derivation] = {}
        self._seq = 0                       # monotonic record counter (audit only)
        self._record_order: Dict[str, int] = {}  # primitive id -> record seq

    # ── id existence (INV-6 support) ────────────────────────────────────────
    def _known_primitive(self, pid: str) -> bool:
        return (pid in self._entities or pid in self._events or pid in self._agents
                or pid in self._assertions or pid in self._derivations)

    def _id_taken(self, pid: str) -> bool:
        return self._known_primitive(pid)

    @property
    def version(self) -> int:
        """A counter that changes whenever a primitive is recorded.

        The store is append-only, so this is monotonic and any change to its
        contents is a change to this number. Derived views cache against it.
        Distinct from the record order below in intent, though they share a
        counter: that is an audit aid and explicitly not a semantic input (14.6),
        and this is a cache-invalidation input. Neither decides anything.
        """
        return self._seq

    def _stamp(self, pid: str) -> None:
        self._seq += 1
        self._record_order[pid] = self._seq

    # ── Entity (7.1) ────────────────────────────────────────────────────────
    def put_entity(self, entity: Entity) -> Entity:
        # INV-3: recording an id that already exists is a mutation attempt.
        if self._id_taken(entity.id):
            raise Rejected(R_MUTATION, f"id already recorded: {entity.id}")
        self._entities[entity.id] = entity
        self._stamp(entity.id)
        return entity

    # ── Event (9.1) ─────────────────────────────────────────────────────────
    def put_event(self, event: Event) -> Event:
        if self._id_taken(event.id):
            raise Rejected(R_MUTATION, f"id already recorded: {event.id}")
        self._events[event.id] = event
        self._stamp(event.id)
        return event

    # ── Agent (10.1) ────────────────────────────────────────────────────────
    def put_agent(self, agent: Agent) -> Agent:
        if self._id_taken(agent.id):
            raise Rejected(R_MUTATION, f"id already recorded: {agent.id}")
        self._agents[agent.id] = agent
        self._stamp(agent.id)
        return agent

    # ── Assertion (8.1) ─────────────────────────────────────────────────────
    def put_assertion(self, a: Assertion) -> Assertion:
        if self._id_taken(a.id):
            raise Rejected(R_MUTATION, f"id already recorded: {a.id}")
        # INV-1: exactly one recorded Agent.
        if not a.agent or a.agent not in self._agents:
            raise Rejected(R_NO_AGENT, f"agent missing/unrecorded: {a.agent!r}")
        # INV-2 + subject referential integrity (Model 8.1, normative resolution
        # Option 2). Empty subject list => R_NO_SUBJECT (reserved solely for empty).
        # ANY subject id that does not resolve to a recorded Entity => R_DANGLING.
        # No forward references. Cases:
        #   []            -> R_NO_SUBJECT
        #   [e999]        -> R_DANGLING
        #   [e1,e999]     -> R_DANGLING
        #   [e1,e2]       -> ACCEPTED
        if not a.subjects:
            raise Rejected(R_NO_SUBJECT, "assertion has no subject")
        for s in a.subjects:
            if s not in self._entities:
                raise Rejected(R_DANGLING, f"subject not a recorded entity: {s}")
        # INV-7: assertion-time MUST NOT precede agent recorded-existence.
        agent = self._agents[a.agent]
        if a.assertion_time < agent.recorded_existence:
            raise Rejected(
                R_TEMPORAL,
                f"assertion-time {a.assertion_time} precedes agent existence "
                f"{agent.recorded_existence}",
            )
        self._assertions[a.id] = a
        self._stamp(a.id)
        return a

    # ── Derivation (11.1) ───────────────────────────────────────────────────
    def validate_derivation(self, d: Derivation) -> None:
        """Enforce INV-3 (id reuse) and INV-6 (existence) for a Derivation. This is
        the SINGLE authority for those invariants on derivations; the provenance
        engine calls this, then checks INV-5 (cycle), then records. Raises Rejected."""
        if self._id_taken(d.id):
            raise Rejected(R_MUTATION, f"id already recorded: {d.id}")
        # Consequent MUST be a recorded Assertion (11.1, INV-6).
        if d.consequent not in self._assertions:
            raise Rejected(R_DANGLING, f"consequent not a recorded assertion: {d.consequent}")
        # Antecedents MUST all be recorded primitives, at least one (INV-6).
        if not d.antecedents:
            raise Rejected(R_DANGLING, "derivation has no antecedents")
        for anc in d.antecedents:
            if not self._known_primitive(anc):
                raise Rejected(R_DANGLING, f"antecedent not recorded: {anc}")

    def record_derivation(self, d: Derivation) -> Derivation:
        """Record a derivation that has ALREADY been validated (validate_derivation)
        and cycle-checked (provenance engine). Does not re-check invariants — the
        provenance engine is the single caller and has enforced them in order."""
        self._derivations[d.id] = d
        self._stamp(d.id)
        return d
        return d

    # ── retrieval (read-only views; INV-3 preserved by returning the objects) ─
    def entity(self, pid: str) -> Optional[Entity]: return self._entities.get(pid)
    def event(self, pid: str) -> Optional[Event]: return self._events.get(pid)
    def agent(self, pid: str) -> Optional[Agent]: return self._agents.get(pid)
    def assertion(self, pid: str) -> Optional[Assertion]: return self._assertions.get(pid)
    def derivation(self, pid: str) -> Optional[Derivation]: return self._derivations.get(pid)

    def entities(self) -> Iterable[Entity]: return list(self._entities.values())
    def events(self) -> Iterable[Event]: return list(self._events.values())
    def agents(self) -> Iterable[Agent]: return list(self._agents.values())
    def assertions(self) -> Iterable[Assertion]: return list(self._assertions.values())
    def derivations(self) -> Iterable[Derivation]: return list(self._derivations.values())

    def has(self, pid: str) -> bool: return self._known_primitive(pid)

    # Derivations whose consequent is a given assertion / that reference a primitive.
    def derivations_for_consequent(self, aid: str) -> List[Derivation]:
        return [d for d in self._derivations.values() if d.consequent == aid]

    def derivations_referencing(self, pid: str) -> List[Derivation]:
        return [d for d in self._derivations.values()
                if pid == d.consequent or pid in d.antecedents]
