# OMEM reference engine

This document describes the reasoning core in `server/omem_engine/`. It is
intended for a reader who has not seen the project before and needs to
understand what the engine does, how it is structured, and where its
boundaries are. Validation status and test methodology are covered separately
in `ENGINE_VALIDATION.md`.

## Scope

The engine is a belief-revision store. It records assertions made by agents
about entities, tracks when each assertion is believed, resolves which entities
refer to the same real-world thing, and answers queries about belief state at a
point in logical time. It does not extract facts from text, rank sources, embed
vectors, or talk to a database, those concerns live in the API layer above it
(`server/`). The engine is roughly 1,300 lines of dependency-free Python across
14 modules and holds all state in memory.

The design principle the surrounding system is built on: the model (LLM
extraction, connectors, SDK callers) may only *propose* candidate facts; the
engine decides belief state; retrieval finds relevant memory. The engine never
parses text or infers a contradiction on its own, see "Contradiction" below.

## Primitives

Five immutable record types (`primitives.py`):

- **Entity**, a referent (a company, person, product). Identified by a caller-
  supplied logical id.
- **Event**, something that happened at an event-time, optionally with an end.
- **Agent**, who makes assertions, with a recorded-existence time.
- **Assertion**, an agent's claim that a proposition holds for a set of
  subjects (entities), stamped with an assertion-time (when it was learned) and
  optionally an event-time (when the claimed thing happened) and a confidence.
- **Derivation**, an edge recording that one primitive was derived from others
  (extraction, inference, supersession, coreference all share one graph).

Primitives are frozen once created. State that changes over time (whether an
assertion is still believed) is kept outside the primitive as a recomputable
view, so a primitive is never mutated after the fact.

## Time model

Every assertion has a half-open belief interval `[start, end)`:

- `start` is the assertion-time.
- `end` is the assertion-time of the supersession that closed it, or unbounded
  if it is still believed.
- An assertion is open at query time `T` when `start <= T < end`.

The close bound is not stored on the assertion. It is computed from the
supersession ledger (`interval.py` + `revision.py`), which keeps primitives
immutable and lets belief state be reconstructed for any past `T` ("as-of"
queries). Supersession requires the new assertion-time to be strictly greater
than the one it closes, so closed intervals are always non-empty.

## Contradiction

Two propositions conflict only if a caller has explicitly declared the pair
contradictory (`ContradictionRegistry` in `proposition.py`). There is no text
analysis and no built-in notion of negation: `is_active` and `is_not_active` do
not contradict unless declared. This keeps the engine's conflict detection
auditable, a conflict always traces back to a declared relation, never to an
inference the engine made about wording.

`proposition_state(subjects, proposition, T)` returns one of four values:

- `BELIEVED_TRUE`, an open assertion affirms the proposition, none denies it.
- `BELIEVED_FALSE`, an open assertion denies it (asserts a declared-
  contradictory proposition), none affirms.
- `CONTRADICTED`, both an affirming and a denying assertion are open.
- `UNKNOWN`, neither.

The function is total: it returns one of these for any input, including an empty
subject set or a proposition nobody has mentioned.

## Coreference

A coreference assertion claims two entities are the same referent. It is an
ordinary assertion with its own belief interval, so it can be superseded (a
"split") like any other belief. The referent partition at `T` is the transitive
closure of the "coreferent-at-T" relation over all entities, computed with
union-find (`coreference.py`). A pair stays merged while at least one coreference
assertion about it is open; it separates when the last one closes. Confidence
plays no part in the partition.

Queries reduce subject sets through the partition before comparing them, so an
assertion about entity A and a contradicting assertion about entity B are
recognised as being about the same referent once A and B are declared
coreferent, and stop being so after a split.

## Revision and retraction

Supersession records a new assertion, adds a supersession derivation from new to
old, and closes the old interval at the new assertion-time (`revision.py`). An
already-closed interval cannot be closed again. Retraction is supersession with a
reserved `RETRACTED` proposition; a retracted proposition contributes to neither
the affirming nor the denying side, so its state becomes `UNKNOWN` rather than
`BELIEVED_FALSE`, retraction withdraws a belief, it does not assert its
opposite. The revision chain for an assertion is the supersession-linked
sequence, ordered by ascending assertion-time with ties broken by canonical id
order.

## Provenance and grounding

Derivations form one acyclic graph across all derivation kinds
(`provenance.py`). Adding a derivation that would introduce a cycle is rejected,
as is one referencing a primitive that does not exist. Provenance for an
assertion is the set of primitives reachable by walking derivation edges toward
antecedents, terminating at events or original assertions. An assertion is
GROUNDED if that walk reaches at least one event, UNGROUNDED if it terminates
only in assertions with no evidential event behind them.

## Determinism

Given the same operations, the engine produces the same observable state
regardless of insertion order, reads recompute from stored primitives and the
supersession ledger rather than from mutable accumulators. Internal tie-breaks
(union-find roots, revision-chain ordering) use a canonical byte order over
identifiers so they are stable and reproducible. Reproducibility markers
(`reproducibility.py`) hash a canonical serialisation of the contributing
primitive ids, their confidences, and the logical time; identical inputs produce
identical markers, and markers are compared only for equality.

## Public surface

The engine facade (`engine.py`) exposes operations  - 
`assert_`, `supersede`, `retract`, `corefer`, `split`, `derive`,
`put_entity/event/agent`, and queries  - 
`proposition_state`, `beliefs_about`, `conflicts`, `referent_partition`,
`provenance`, `revision_chain`, `timeline`, `trust_order`, `repro_marker`.
Operations return `ACCEPTED` or raise `Rejected` with a reason code
(`R_NO_SUBJECT`, `R_NO_AGENT`, `R_TEMPORAL`, `R_REOPEN`, `R_CYCLE`,
`R_DANGLING`, ...). This facade is the whole observable interface; the API layer
calls nothing else.

## Boundaries

The engine is a single memory space with no concept of tenant, project, or
private/shared visibility. `beliefs_about` returns every agent's assertions
about a subject. Multi-tenant isolation and per-agent visibility are enforced
entirely in the API layer (`server/api.py`, scope store, viewer checks), not in
the engine. Anyone embedding the engine directly inherits no isolation and must
build it. This is a deliberate separation, but it means "the engine is safe for
multi-tenant use" is not a property the engine provides on its own.

## Persistence and replay

The engine holds state in memory. Durability is the API layer's responsibility:
every accepted operation is written to an append-only ops log and replayed
through the engine at boot to reconstruct state. Projections derived from engine
state (retrieval indexes, graph edges) are rebuilt and reconciled after replay.
The engine itself neither reads nor writes storage.
