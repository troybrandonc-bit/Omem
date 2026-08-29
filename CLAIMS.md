# The claims ledger

Every load-bearing sentence this project says about itself, next to the
executable statement that would go red if it stopped being true. A claim
with no row here is opinion; a row here whose file is missing fails CI,
because the ledger itself is guarded by `server/tests_claims_ledger.py`.

Marketing that cannot fail is indistinguishable from marketing that is
false. Everything below can fail.

| The claim | What would go red |
|---|---|
| Zero runtime dependencies, and CI fails the build the moment one appears | `scripts/gen_sbom.py` (`--check` in CI) |
| The demos in the README are asserted tests: every line shown is verified on every commit | `scripts/demo_refusal.py`, `scripts/demo_reasoning.py` |
| Memory state follows from the append-only log: replay is deterministic, and an anchor detects a rewritten log | `server/replay_verify.py`, `server/tests_replay_verify.py` |
| The belief engine is frozen and hash-verified; the server refuses to boot over a modified engine | `server/omem_engine/ENGINE_HASHES.txt`, `server/engine_baseline.py`, `server/tests_p10_1_conformance.py` |
| Contradictions are surfaced with both sides preserved, never resolved by timestamp | `server/tests_contradiction.py` |
| Retracting a fact withdraws every conclusion resting on it, in the same request | `server/tests_inference_rules.py`, `scripts/demo_reasoning.py` |
| A shared name is not a shared identity, and a split a person makes is final for the machine | `server/tests_identity_resolution.py` |
| A hunch is never allowed to quietly become a belief: it is proven, refuted, or escalated to a human | `server/tests_hypotheses.py` |
| Priors learned about people in general fire only into a silence and yield to a person's own evidence; a pattern seen on too few people cannot fire | `server/tests_priors.py` |
| The Witness card: no fabrication, retraction honoured, disagreement visible, identities kept apart, conclusions die with premises, every memory sourced | `benchmarks/witness/harness.py`, `server/tests_witness_benchmark.py` |
| It phones home to nobody: a socket guard proves a full working session performs zero outbound connections or lookups | `server/tests_airgap.py` |
| Upgrades never rewrite your past: a log frozen on 2026-08-29 must replay to a byte-identical state digest in every future version | `server/testdata/golden_log_v1.json`, `server/tests_upgrade_stability.py` |
| Encryption at rest uses real AEAD or refuses to run, and the entire suite passes against ciphertext | `.github/workflows/ci.yml` |
| A write it refuses leaves a trace saying so | `server/tests_require_grounded.py`, `scripts/demo_refusal.py` |
| The LangGraph store adapter supersedes instead of overwriting and retracts instead of deleting | `sdk/python/omem/integrations/langgraph_store.py`, `server/tests_langgraph_store.py` |
| `pip install omem-infrastructure` is the whole install: server, dashboard and credentials on one port | `scripts/verify_quickstart.py` |
| The same log means the same state under SQLite and PostgreSQL alike | `server/tests_postgres.py`, `server/db_adapter.py` |
