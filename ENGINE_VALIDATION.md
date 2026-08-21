# Engine validation status

This document records what has and has not been established about the reasoning
engine in `server/omem_engine/`. It is written for a technical reviewer doing
diligence. It is deliberately explicit about the limits of the evidence.

Summary: the engine's behaviour has been validated black-box against a
reconstruction of its intended semantics, exercised with property-based fuzzing,
and characterised for scale. No part of this constitutes third-party
certification, and the engine's own normative specification is not present in
this repository (see below). Claims are labelled VERIFIED (established by tests
run here), INFERRED (reasoned from code and behaviour but not independently
confirmed), or UNKNOWN (cannot be established from what is available).

## The normative specification is not in this repository

The engine's source refers throughout to a formal model and conformance test
suite, identifiers such as `Model 8.6`, `CTS 3.1`, `Profile 4.2`, and invariants
`INV-1`..`INV-9`, `N5`, `N10`, `J-1`, `J-4`, `I-1`. None of the documents these
refer to are in the repository. A search for those identifiers across all
documentation returns nothing; the CTS runner the README once pointed at
(`../omem-ref/run_cts.py`) does not exist here.

Consequence: we cannot certify the engine against its specification, because the
specification is not available to check against. Statements elsewhere in the
project's history of the form "CTS 29/29" refer to a conformance run that cannot
be reproduced in this repository and should not be read as independent
validation. What follows is validation against the semantics as reconstructed
from the code and its docstrings, which is a weaker claim and is treated as such.

## What was tested, and how

All validation drives the raw engine API directly (no server, no SDK) and derives
expected outcomes from first principles, the documented four-valued logic,
half-open intervals, transitive-closure coreference, monotonic revision, rather
than by comparing the engine to itself. Suites:

- `server/tests_p10_engine_proof.py`, 38 hand-constructed black-box checks
  across contradiction, temporal/as-of, coreference, retraction, provenance,
  determinism, isolation, and adversarial cases.
- `server/tests_p10_1_conformance.py`, invariant conformance map, Hypothesis
  property-based fuzzing, and scale characterisation.

### Self-stated invariants (VERIFIED black-box)

Each of the following was mapped to a passing test that constructs a situation
where the invariant must hold and checks the observable result. "Self-stated"
because the source of the invariant is the engine's own docstrings, not an
external spec.

- Assertions require at least one subject; subject order is not observable.
- Superseding an assertion does not mutate the frozen primitive.
- A closed interval cannot be reopened or re-closed (`R_REOPEN`).
- The derivation graph rejects cycles (`R_CYCLE`) and dangling references
  (`R_DANGLING`).
- An assertion dated before its agent's recorded existence is rejected
  (`R_TEMPORAL`).
- Belief intervals are half-open: the start instant is included, the close
  instant is excluded (checked at the exact boundary).
- A retracted proposition contributes to neither side and reads `UNKNOWN`.
- A pair stays coreferent while any one of several coreference assertions about
  it is open; a self-coreference is a no-op on the partition.

INV-9 ("interval state is a recomputable view") is PARTIAL: only its observable
consequence, determinism across identical builds, is checkable black-box; the
internal recomputation claim is not. INV-1 ("exactly one agent") is enforced by
the type signature and cannot be violated through the API, so there is nothing to
test; it is UNKNOWN in the sense of not independently exercised.

### Property-based fuzzing (VERIFIED)

A Hypothesis stateful machine drives randomised well-formed operation sequences
(add entity, assert, supersede, corefer) and asserts properties derived
independently of the implementation, checked after every step:

- `proposition_state` always returns one of the four valid values (totality).
- `referent_partition` is a valid partition, disjoint classes covering exactly
  the known entities.
- Conflict pairs are unordered pairs of exactly two open assertions.
- Repeated reads are stable.

Run at 120 examples × up to 40 steps: no violations. A separate seeded replay
check confirms that the same operation sequence produces byte-identical
observable state (partition, conflicts, and all proposition states). A batch of
300 malformed and boundary operations (missing subject, unknown agent, equal-time
supersession, dangling target, self-derivation, empty-subject query, negative
timestamps) produced clean `Rejected` errors or correct handling in every case,
with no crash or state corruption.

### Determinism and replay (VERIFIED)

Observable state is independent of insertion order for the cases tested, and
identical operation sequences reproduce identical state. Reproducibility markers
are canonical: order-independent over their inputs, and they change when logical
time or a confidence changes. This supports the API layer's boot-time replay,
which reconstructs engine state from the append-only ops log.

## Scale characterisation (VERIFIED by measurement)

Empirical complexity, single process, in-memory. The engine's query primitives
were quadratic and near-cubic; they are not any more, and both sets of numbers
are kept because the second only means something against the first.

BEFORE (measured over sizes 25-800):

| Operation             | Exponent | Reading                     |
|-----------------------|----------|-----------------------------|
| `referent_partition`  | ~1.0     | linear                      |
| replay / ingestion    | ~1.0     | linear                      |
| `provenance` (chain)  | ~1.9     | quadratic                   |
| `proposition_state`   | ~2.2     | quadratic                   |
| `conflicts`           | ~2.9     | near-cubic                  |

`conflicts` ran in roughly 7 ms at 25 assertions, 334 ms at 100 and 2.6 s at 200;
a single `proposition_state` query took about 1.6 ms at 50 and 700 ms at 800.

The cause, visible in `proposition.py`, was that the query primitives recomputed
the coreference-reduced subject set (which itself computes the partition) inside
their per-assertion and per-pair loops. Coreference and ingestion were already
linear; the cost was in re-reducing, not in the union-find.

AFTER (measured over 200-40,000 assertions on the same machine):

| assertions | `proposition_state` | `conflicts` |
|-----------:|--------------------:|------------:|
| 200        | <1 ms               | <10 ms      |
| 1,000      | 3 ms                | 10 ms       |
| 4,000      | 12 ms               | 50 ms       |
| 10,000     | 28 ms               | 150 ms      |
| 40,000     | 112 ms              | 1.15 s      |

`proposition_state` is now linear (~1.0) and `conflicts` roughly 1.4. At the
4,000 assertions where a single belief query previously took 6.2 s, it takes
12 ms, and the engine reaches sizes the old code could not be measured at.

Three changes, none of them to the semantics: the referent partition is computed
once per query and indexed entity-to-representative instead of being recomputed
per subject; `conflicts` buckets open assertions by referent before pairing, so
only assertions that could possibly conflict are compared; and the contradiction
registry is indexed by canonical form rather than scanned pairwise.

That the answers did not change is not asserted, it is tested.
`server/tests_engine_equivalence.py` re-implements the query primitives in their
original naive form and requires both to agree on every question across randomly
generated stores containing coreference merges, splits, supersessions,
retractions and as-of queries at points before and after each, and asserts that
the generated workload actually contained each of those operations, so agreement
cannot be reached over a world too simple to disagree in.

The engine is no longer byte-identical to the frozen v1.0 reference. Its hashes
live in `server/omem_engine/ENGINE_HASHES.txt`, are checked by the suites, and
are regenerated only by `python3 engine_baseline.py --update`. Previously that
baseline was read from `/tmp/engine_hashes_before.txt`, which nothing in the
repository created; on a clean machine nineteen suites crashed on it, and on a
machine that had one it had been produced by hand at an unrecorded moment.

The API layer's narrower `conflict_narrow.conflicts_for` remains what the product
calls on the hot path, and is unchanged.

## Isolation boundary (VERIFIED)

The engine has no tenant or per-agent visibility model. `beliefs_about` returns
every agent's assertions about a subject. Isolation is enforced entirely in the
API layer. Any integration that embeds the engine directly must implement its own
isolation; the engine provides none.

## Proven vs. still open

VERIFIED here:
- Four-valued belief semantics behave as documented, including the boundary and
  symmetry cases.
- Contradiction is declaration-driven, with no text inference.
- Half-open temporal semantics and as-of reconstruction.
- Monotonic revision; retraction withdraws rather than denies.
- Coreference as transitive closure, confidence-independent, reversible by split.
- Acyclic provenance with event-reachability grounding.
- Determinism and replay for the cases exercised.
- The complexity curves above.
- No crashes or invariant violations under the fuzzing and malformed-input
  batches run.

INFERRED:
- The engine's semantics match the intent described in its docstrings. This is a
  reading of the code, not confirmation against the external model.

UNKNOWN:
- Conformance to the actual normative specification (absent from the repo).
- Completeness beyond the tested cases, black-box testing and bounded fuzzing do
  not prove the absence of edge-case defects.
- Correctness of the trust-ordering and confidence-weighting paths, which are
  only lightly exercised here.

No test failures, crashes, or flaky cases were observed in this work. The engine
was not modified and is byte-identical to its baseline.

## External validation roadmap

To move any of the UNKNOWN items to VERIFIED, and to support licensing,
integration, or acquisition diligence, the following would be needed, roughly in
priority order:

1. **The normative model and conformance suite.** The single highest-value
   artifact. With the actual CTS in hand, the engine can be run against it and
   the "self-stated" qualifier on the invariants above can be dropped. Without
   it, correctness remains an inference.
2. **Independent correctness review.** Someone who did not write the engine
   reading the reasoning core against the model and reproducing its guarantees.
3. **Security audit.** A review of the engine and, more importantly, of the API
   layer that provides the isolation the engine does not. The isolation boundary
   is the highest-risk area precisely because it sits outside the engine.
4. **Expanded property-based and fuzz testing.** The Hypothesis suite here is a
   starting point at modest breadth. Larger example counts, longer histories, and
   additional invariants (e.g. supersession-chain integrity, timeline ordering)
   would raise confidence. This is cheap to extend.
5. **Scale testing at target volume.** The curves here go to 800 assertions in
   one process. A consumer intending to call the engine primitives directly at
   large scale needs measurements at their volume and a decision on whether the
   quadratic/cubic query paths are acceptable or require an indexing/caching
   layer (which would be an engine change and would need re-validation against
   items 1-4).

## Reproducing this validation

```
cd server
python3 tests_p10_engine_proof.py       # 38 black-box checks
python3 tests_p10_1_conformance.py       # invariants + Hypothesis fuzz + scale
```

Both print per-check results and confirm the engine files are byte-identical to
their recorded baseline at the end of the run. `tests_p10_1_conformance.py`
requires the `hypothesis` package.
