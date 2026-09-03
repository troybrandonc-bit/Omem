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
| How bold a hunch is born follows the record of past ones, weighted by how much each verdict surprised it; the counts the commons contributes stay whole verdicts | `server/tests_surprise_weighting.py` |
| Pooling priors across installations earns its keep where the populations share their regularities, and stops paying where they do not | `benchmarks/commons/`, `server/tests_commons_benchmark.py` |
| A prior has to beat its consequent's own base rate, and it is the lower bound of its rate that must clear the line, so a pair resting on three people cannot outrank one resting on three hundred; measured against a known latent structure in 19,668 real respondents | `benchmarks/external/`, `server/tests_prior_lift.py` |
| Agreement across installs is not agreement across populations: a pooled pattern backed by one declared kind of population raises the evidence bar rather than being treated like one backed by several, and the spread it held across them travels with it | `server/tests_population_frame.py` |
| What a contribution says about where it came from is a working domain, a macro-region and a size band, chosen from closed lists and holding no fact about any person; an operator who declares nothing still contributes and cannot be counted as many populations | `server/tests_population_frame.py`, `server/tests_commons_guards.py` |
| Mining stays quadratic in vocabulary rather than cubic, and the work per pair does not grow with the population: the engine consults declared opposites once per proposition, never once per pair | `benchmarks/scale/`, `server/tests_scale_mining.py` |
| The leap pass reads the belief store once per run however many entities and priors it examines, and compares a target only with entities that share a feature with it | `benchmarks/scale/`, `server/tests_scale_leap.py` |
| Priors learned about people in general fire only into a silence and yield to a person's own evidence; a pattern seen on too few people cannot fire | `server/tests_priors.py` |
| The Witness card: no fabrication, retraction honoured, disagreement visible, identities kept apart, conclusions die with premises, every memory sourced | `benchmarks/witness/harness.py`, `server/tests_witness_benchmark.py` |
| Only a field with a written argument for why it is safe ever leaves the machine, and an install that was never asked, or said no, contacts nobody | `server/tests_commons_guards.py` |
| How bold a hunch is born is a probability rather than a running tally: the posterior mean of that generator's hit rate, anchored on what this install's hunches do in general rather than on a constant, and never above the ceiling | `server/tests_surprise_weighting.py`, `benchmarks/external/` |
| A hunch from a prior is forecast from that prior's own measured rate, as the lower bound shrunk toward the install's house rate by support, and the strength cap does not bind below the rate hunches actually achieve; both are required, and reverting either returns the forecast to no better than the base rate | `server/tests_prior_anchor.py`, `benchmarks/external/` |
| The bank can record what people who do one thing tend NOT to do, and no person is ever handed both a claim and its denial about the same silence: one hunch per bare claim, with the better-evidenced prior deciding the direction | `server/tests_prior_negation.py`, `benchmarks/external/` |
| It phones home to nobody: a socket guard proves a full working session performs zero outbound connections or lookups | `server/tests_airgap.py` |
| Upgrades never rewrite your past: a log frozen on 2026-08-29 must replay to a byte-identical state digest in every future version | `server/testdata/golden_log_v1.json`, `server/tests_upgrade_stability.py` |
| Encryption at rest uses real AEAD or refuses to run, and the entire suite passes against ciphertext | `.github/workflows/ci.yml` |
| A write it refuses leaves a trace saying so | `server/tests_require_grounded.py`, `scripts/demo_refusal.py` |
| The LangGraph store adapter supersedes instead of overwriting and retracts instead of deleting | `sdk/python/omem/integrations/langgraph_store.py`, `server/tests_langgraph_store.py` |
| `pip install omem-infrastructure` is the whole install: server, dashboard and credentials on one port | `scripts/verify_quickstart.py` |
| The same log means the same state under SQLite and PostgreSQL alike | `server/tests_postgres.py`, `server/db_adapter.py` |
