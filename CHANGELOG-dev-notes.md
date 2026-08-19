# OMEM Cloud

Developer-facing product for the OMEM memory standard. Two parts:

- `server/`, a thin HTTP API wrapping the **authoritative** OMEM reference engine.
  Every route delegates to one engine method; it invents no memory semantics.
- `web/`, Next.js 14 + TypeScript + Tailwind dashboard. Talks only to the API.

## What is real
Signup creates a persisted user, org, project, and hashed API key (SQLite at
`server/data/omem.db`). Every accepted write is recorded to an append-only ops
log and replayed through the reference engine at boot, so restarts lose
nothing. (On the engine's validation status and the limits of it, see
`ENGINE.md` and `ENGINE_VALIDATION.md`; the normative conformance suite the
code refers to is not part of this repository.) All API routes require a
session token or API key; keys are scoped to
their project and cross-project access is rejected. The demo scenario lives only
in the labeled shared "Demo" project. `server/tests.py` covers the full surface
(37 checks incl. auth, isolation, and restart replay).

---

The sections below are a development changelog. Several entries end with a
"CTS 29/29" marker recorded at the time. That marker refers to a conformance run
against an external suite that is not part of this repository and cannot be
reproduced here; read it as a historical note, not as current independent
validation. For the engine's actual, reproducible validation status see
`ENGINE_VALIDATION.md`.

---

## Automatic ingestion (product direction: memory control plane)
Connect a source once; OMEM ingests continuously. The pipeline (`server/ingest.py`)
polls connectors, writes immutable source records, extracts candidate facts,
resolves entities, emits a grounding event, and produces real OMEM assertions
through the same recorded write path the manual SDK uses. The frozen engine  - 
not the pipeline, determines proposition state, contradiction, and coreference.
Source-level and fact-level dedup, retry with a dead-letter queue after 3 attempts,
and reverse provenance (belief → source record) are built in. One real connector
(support inbox, deterministic rule extraction) is implemented end-to-end; the
`Connector` abstraction is where Gmail/Slack/Salesforce slot in behind the same
interface. Enterprise intelligence (`/v1/intelligence`) derives grounding
coverage, provenance coverage, unresolved conflicts, and source authority live
from the engine. Tests: `server/tests_ingest.py` (20 checks).

## Production connectors, LLM extraction, automatic sync
`connectors.py` adds a real Gmail connector (OAuth token storage encrypted at
rest, initial + incremental sync via cursor, connect/disconnect, per-project
isolation) behind the frozen pipeline; an `LLMExtractor` (strict JSON, evidence
must appear in source text, malformed output yields no facts) that only PROPOSES
candidate facts; and an auditable `EntityResolver` that records why each raw
signal became a given entity. `scheduler.py` drains connectors on a background
thread with per-project rate limiting. `agent.py` is a runnable support agent
that queries OMEM before responding and feeds the conversation back into the
pipeline. SDKs live in `sdk/python` and `sdk/typescript`. The LLM/Gmail transports
are injected: tests use deterministic mocks with real wire shapes; production
injects urllib pointed at Google / a model provider. Tests: `tests_gmail.py`
(23 checks). Frozen engine unchanged; CTS still 29/29.

## Enterprise control plane (real, enforced)
`enterprise.py` adds RBAC (owner/admin/developer/viewer with an explicit
permission matrix, enforced on every guarded route), an append-only audit log
(no update/delete methods exist by design), real usage metering (counters over
real events, with time-bucketed series), retention policies (sweep deletes stored
source material only; engine memory history is immutable), and billing
entitlements separate from provider state. `providers.py` holds real, env-gated
transports for Google OAuth/Gmail, any OpenAI-compatible LLM, and Stripe, active
only when their env vars are set, otherwise the tested mocks are used. Health,
graceful shutdown, and env validation are in `api.py`; see DEPLOYMENT.md.
Tests: `tests_enterprise.py` (31 checks). Frozen engine unchanged; CTS 29/29.

## Hardening (this cycle, REAL + VERIFIED, no external providers)
`secrets_provider.py` replaces the reversible XOR with authenticated encryption
(AES-GCM when available, else HMAC-authenticated stream) behind a `SecretsProvider`
abstraction; a `KMSSecretsProvider` envelope interface exists for AWS (real code,
untested without AWS). OAuth tokens are encrypted at rest and never returned by
API responses (get() hides them; only the Gmail transport reads them with
include_secrets=True). The job system now has the full lifecycle  - 
pending/running/completed/retrying/dead_lettered/cancelled, with exponential
backoff, crash recovery (stale 'running' jobs return to pending), and
cancellation. API keys support expiry (expired keys 401). Auth endpoints are
rate-limited (429 on abuse); OAuth state is a signed single-use nonce; responses
carry security headers + correlation IDs. Tests: `tests_hardening.py` (29 checks).
Frozen engine untouched; CTS 29/29.

## Managed agent surface (this cycle, REAL + VERIFIED)
`/v1/learn` turns free text into candidate facts via the ingestion extractor,
records valid OMEM primitives through the recorded write path, and returns the
engine-determined state (the engine decides; the endpoint never computes state).
`/v1/recall` returns real memories about a subject with grounding + provenance.
Both are exposed in the Python and TypeScript SDKs as `learn`/`recall` plus an
agent-scoped `agent(id)` wrapper. The Playground now runs learn+recall live
against your project and generates the matching cURL/Python/TypeScript snippet.
The TypeScript SDK is compiled and executed in Node (v22): request-building,
response-parsing, and typed errors verified. Python SDK verified against the live
server. Tests: `tests_agent.py` (17 checks). Frozen engine unchanged; CTS 29/29.

## Playground: full developer loop (this cycle)
The Playground now runs the complete loop live against the user's project:
learn (free text -> engine belief) -> recall -> why (state + provenance chain),
with the provenance rendered visually and matching cURL/Python/TypeScript code
generated for the exact call. Both SDKs expose agent.learn/recall/why/remember/
believes; the generated snippets are truthful (every method exists and is tested).
Fake-metric audit: all 26 dashboard queries hit real API endpoints; no hardcoded
stats, no Math.random in data paths. Tests: tests_agent.py (22 checks).

## Product layer (this cycle)
Automatic memory without external providers: a DB-backed PushConnector powers
POST /v1/webhooks/{connector_id} (accepts deliveries, dedups by external id) and
POST /v1/documents (upload text -> extraction -> memory), both through the same
pipeline as every other source with full provenance back to the original payload.
Entitlement enforcement is real: plan quotas from the configurable PLANS dict
block learn/assert/connector-create with 402 and record quota_exceeded billing
events (demo project exempt). Internal operator console at /admin (guarded by
OMEM_ADMIN_EMAILS): org/user/project counts, global assertion count from the ops
log, job queue across tenants, per-customer plan + activity, DB size, and MRR
honestly labeled as an estimate (no Stripe verification). Data export:
GET /v1/export/memories (state + provenance, audited) and /v1/export/audit.
Tests: tests_product.py (25 checks). Frozen engine unchanged; CTS 29/29.

## Pilot readiness (this cycle)
GET /v1/onboarding computes an 8-step checklist entirely from backend state
(org, project, key, source connected, record received, memory created, first
recall, agent connected), each step flips only when the real thing happened,
verified step-by-step in tests. POST /v1/feedback records useful/incorrect/
missing/confusing on any memory (product telemetry outside the engine), with a
per-project summary. Per-memory recall counts power /v1/memory/top-recalled.
Customer lifecycle (pilot/trial/paid/cancelled + pilot dates + notes) is
founder-set data on /v1/admin/orgs/{id}/status, customers cannot set their own.
The operator console gained per-org drill-down: usage, job states, dead-letters
with errors, memories, conflicts, feedback summary and top-recalled per project,
for support/diagnosis. Tests: tests_pilot.py (27 checks). CTS 29/29.

## PostgreSQL + durable workers (this cycle, REAL + VERIFIED)
`db_adapter.py` runs the entire SaaS layer on PostgreSQL 16 (OMEM_DATABASE_URL),
verified by executing ALL existing suites against a real PG server: 214 checks
pass unchanged, engine replay is identical, plus `tests_postgres.py` (14 checks)
covering adapter semantics and restart replay. `worker.py` is a standalone
durable worker using FOR UPDATE SKIP LOCKED, two concurrent workers processed
20 jobs with zero double-claims, all completing through the frozen engine.
SQLite remains the credential-free default; both backends pass the full double
regression. Frozen engine untouched; CTS 29/29.

## Pilot completion (this cycle)
Gmail callback now performs the REAL Google code exchange when GOOGLE_* env is
set (local stub otherwise, honestly flagged `real_exchange:false`), with signed
single-use OAuth state enforced and an explicit status machine
(HEALTHY/SYNCING/ERROR/NEEDS_REAUTH/DISCONNECTED + messages_processed). Slack
and Salesforce connectors ship with real transports (conversations.history /
SOQL) verified through the pipeline with wire-shaped fixtures. Project-level
LLM configuration (`/v1/settings`) selects the model per project; every
extraction is logged (`/v1/extraction-logs`). Stripe webhooks are implemented
with Stripe's documented HMAC signature scheme, valid/invalid/replayed
signatures and the subscription lifecycle verified locally. Workers gained
per-tenant concurrency caps; schema versions are recorded in
`schema_migrations`; and backup/restore was VERIFIED on live PostgreSQL
(pg_dump -> destroy -> restore -> engine replay identical). Suites:
tests_e2e.py (25) incl. the full pilot flow with an engine-surfaced
contradiction from a competing email. SQLite 239x2, Postgres 253x2, CTS 29/29.
See PROVIDER-VERIFICATION.md for the exact credential checklist.

## Operational hardening (this cycle, REAL + VERIFIED)
Automated backups (`backups.py`): scheduled, retention-pruned, explicit
success/failure state (never silent), and restore-verification that rebuilds the
dump into a scratch DB and matches the ops-log count, verified on PostgreSQL.
Hardening migrations (versioned in `schema_migrations`): 6 indexes on both
backends + FK constraints with ON DELETE CASCADE on PostgreSQL (cascade verified;
concurrency + tenant isolation tested with parallel writers). TOTP MFA
(enroll/activate/enforced at login), session expiry + revocation. Operator plan
changes + backup panel + LLM-config UI. Tests: tests_ops.py (26), tests_postgres
extended (20). SQLite 265x2, Postgres 285x2, CTS 29/29, engine 9/9 identical.

## Real external source: GitHub (PROVIDER-VERIFIED)
The first genuinely provider-verified connector. `GitHubConnector` calls the real
api.github.com REST API: 28 real issues from psf/requests were ingested as
immutable source records, extracted by `GitHubIssueExtractor` (deterministic,
every fact carries the exact source substring that triggered it), resolved to a
`repo:` entity, and passed through the recorded path so the frozen engine decided
the states, producing BELIEVED_TRUE beliefs traceable to individual issue URLs.
Incremental sync uses GitHub's `since` cursor; PRs are skipped; source-level
dedup prevents re-ingestion. Rate limiting is honest: quota exhaustion raises a
typed `ProviderRateLimited`, the API answers 429 with the reset epoch, and the
connector reports RATE_LIMITED (verified against the real exhausted API, never a
fake success). Unauthenticated is 60 req/hour; set GITHUB_TOKEN for 5000/hour.
Tests: tests_github.py (24 offline; OMEM_GITHUB_LIVE=1 adds live checks).
Dashboard audit: all 55 queries hit real endpoints; zero Math.random, zero
hardcoded stats, zero fake percentages. SQLite 289x2, Postgres 309x2, CTS 29/29.

## GitHub as a first-class source (this cycle)
`GET /v1/connectors/{id}/detail` returns real per-source counts: items ingested,
memories generated (assertion ids recorded on completed jobs), every job state,
last successful sync, cursor, and last error. `POST /v1/connectors/{id}/resync`
clears the cursor for a full re-read (dedup still prevents duplicates). Provider
rate-limit reset epochs are tracked per connector and surfaced. The Sources page
was rebuilt around this: one card per source with live status
(HEALTHY/SYNCING/ERROR/RATE_LIMITED/NEEDS_REAUTH/DISCONNECTED), items ingested,
memories generated, in-flight jobs, last sync, job breakdown, cursor, a
rate-limit banner with reset time, the real last error, and Sync now / Re-sync
all / Disconnect actions. With no sources it shows an explicit "Not connected"
empty state, never invented values. Tests: tests_github.py now 41 checks.
SQLite 306x2, Postgres 326x2, CTS 29/29, engine hashes unchanged.

### Connecting real Gmail
Credentials go in **`server/.env.local`** (copy `server/.env.example`). A
`.env.local` under `web/` is a Next.js convention and is NOT read by the Python
API, that was a real bug, now fixed: the API loads `server/.env.local`,
`server/.env`, repo-root `.env*`, and `web/.env.local` at startup, and prints
which files it loaded. Real environment variables always win over file values.

Set `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` and `GOOGLE_REDIRECT_URI`, then
restart the API. The redirect URI may point at either the frontend
(`http://localhost:3000/oauth/gmail/callback`) or the API
(`http://localhost:8787/oauth/gmail/callback`), both serve that path, as long
as it matches the value registered in Google Cloud exactly. "Connect Gmail" now
redirects to Google's real consent screen with signed single-use state; Google
redirects back to `GET /oauth/gmail/callback`, which exchanges the code, stores
the refresh token encrypted, and returns you to the dashboard. If Google is not
configured the API says so explicitly (`real:false` + required env) and the UI
shows that message rather than crashing.

### Upgrading an existing database
`CREATE TABLE IF NOT EXISTS` never alters an existing table, so databases made by
earlier versions lacked columns added later (this produced
`OperationalError: no such column: s.expires`). The Store now performs an
additive, idempotent column upgrade on every boot: it reads the catalog
(PRAGMA on SQLite, information_schema on Postgres) and ALTERs in any missing
column, reporting them via `STORE.upgraded_columns`. Pre-existing rows are
preserved and remain valid, a NULL `expires` means "no expiry", not "expired",
so old sessions and keys keep working. No manual migration or DB reset needed.

### Relevance filtering and extraction quality
Ingestion is filtered twice. Gmail is queried server-side with a business-mail
filter (excludes promotions/social/forums/updates and noreply-style senders), so
bulk mail is never downloaded. Every connector then applies a client-side gate
that rejects List-Unsubscribe/List-Id mail, `Precedence: bulk`, auto-replies,
bounces and automated sender addresses. Nothing is dropped silently: every
exclusion is recorded with its reason in `filtered_items`, exposed at
`GET /v1/filtered` and shown on the Sources page. Genuine mail from addresses
like billing@ is deliberately kept.

Extraction now asks the model for durable business facts (preferences,
intentions, commitments, roles, renewal dates, blockers, reported problems),
distinguishes person-level from company-level subjects, and requires a VERBATIM
evidence span for every fact. Facts whose quote is not found in the source are
discarded, as are facts below 0.5 confidence, which is what makes a cheap model
safe here. Malformed and code-fenced output is handled without failing the job.

### Design system
Cool Stripe-style surface: page `#f6f8fa`, white panels with a single hairline
and one soft shadow, ink `#1a1f36`, accent `#635bff`. Supporting text sits at
normal weight, an earlier rule force-bolded every small class, which made the
whole interface read heavy. Headings are 600 (not 700), panel headers and table
rows are tight (`px-4 py-2.5`), stat figures are 20px tabular, and the sidebar is
a quiet 216px rail with a tinted pill for the active route. Density and restraint
carry the hierarchy; weight is used only where it means something.

### If the dev server runs out of memory
`RangeError: Failed to allocate memory` from `webpack.cache.PackFileCacheStrategy`
means webpack's on-disk cache could not allocate a serialisation buffer. The dev
config now uses an in-memory cache instead, which removes the failure. If it
recurs, clear `web/.next` and run `npm run dev:big` (or `build:big`), which
raises the Node heap to 4 GB.

### Business relevance classification (two-stage ingestion)
Gmail no longer turns a mailbox into memory. Ingestion is two separate stages:

  Stage 1 (`classifier.py`)  should this message enter the memory pipeline?
  Stage 2 (extractors)       what durable facts, if any, does it contain?

Every fetched message still becomes an immutable source record, retrieval is not
filtered, so any exclusion stays inspectable ("why did OMEM ignore this email?").
Classification decides pipeline entry only, and is persisted in
`message_classifications` with its confidence, business type, reasons and signals.

Judgement combines deterministic evidence: commercial-content patterns (pricing,
contracts, negotiation, payment terms, project scope, expansion, contact
preferences), automated-mail signals (List-Unsubscribe, Precedence, auto-reply,
noreply senders, marketing/dev/social notification shapes), a human-correspondence
baseline, thread context (a short reply inherits its conversation's relevance),
and relationship history (two-way exchange, thread depth). Domains are signals,
never verdicts: an order notification from a marketplace is noise while a price
negotiation on the same domain is business, and a contract amendment from a
noreply address is still business. An optional LLM judge refines the verdict but
cannot promote mail that carries strong automated evidence and no commercial
content of its own.

Thresholds are graded: BUSINESS_RELEVANT extracts normally, POSSIBLY_BUSINESS
extracts but only facts at =0.8 confidence may become memory, NON_BUSINESS and
AUTOMATED_NOISE never enter. Relevance is not evidence, "sounds good, let's talk
tomorrow" is business-relevant and correctly produces zero memories.
`BusinessFactExtractor` proposes only plainly-stated facts (contract value,
renewal timing, payment terms, unit price, lead time, MOQ, requirements, intent),
each with a verbatim evidence span, scoped to the company or the person as
appropriate. Tests: `tests_classifier.py` (55 checks) including all 20 brief
scenarios. Frozen engine untouched; CTS 29/29.

### Memory rescan & hygiene (this cycle, REAL + VERIFIED)
`memory_scanner.py` traces every open assertion back to its evidence and source,
then re-evaluates it against the current rules. Classifications: VALID, DUPLICATE,
UNSUPPORTED (evidence span absent from the source), AUTOMATED_NOISE (source
re-classified by the current classifier), LOW_VALUE, IRRELEVANT, SUPERSEDED,
CONTRADICTED (engine state, no action, the engine already handles it), STALE
(source record or provenance missing), UNKNOWN. Directly-asserted SDK/API writes
are VALID by design, pipeline evidence is only demanded of pipeline memories.

Scans are dry-runs: `POST /v1/memory/scan` produces a persisted report
(`memory_scans` + `memory_scan_results`) and changes nothing. `POST
/v1/memory/scans/{id}/apply` commits the proposals: retract-class results go
through the engine's append-only retract (agent `scanner:system`, recorded in the
ops log, replayed on restart, history stays auditable, nothing is deleted);
LOW_VALUE/IRRELEVANT go to a review queue (`/v1/memory/review-queue`) where a
person approves (retract) or rejects (keep). Apply is idempotent, a second apply
retracts zero. `POST /v1/memory/gmail-rescan` re-runs the current classifier over
already-stored Gmail source records (no re-fetch, no re-ingest) and reports
newly-relevant and newly-excluded mail. `GET /v1/memory/health` returns real
counts only: active memories, last-scan breakdown, pending review, and recent
scanner corrections read from the ops log.

The dashboard gained `/memory-health`: scan controls (all/recent), per-scan
dry-run reports filterable by classification, an explicit confirm before apply,
the review queue with retract/keep, the Gmail rescan report, and correction
history linking to each assertion's why-view. Tests: `tests_rescan.py`
(56 checks) covering every classification, dry-run immutability, apply,
idempotency, review decisions, restart replay of corrections, and all routes.
Frontend: 30 routes building, lint clean. Frozen engine untouched.

### P7, Narrow conflict query + Postgres upsert hardening (this cycle, REAL)
**Audit finding (measured).** The recall/brief bottleneck was NOT candidate
retrieval, a candidate index built in a prior session was already active but
gave no speedup. Profiling showed ~83% of time inside the frozen engine's
`conflicts(T)`, an O(n²) all-pairs contradiction scan run once per recall over
the WHOLE project, then filtered to a few candidates.
**Fix, narrower engine API, no engine change.** `conflict_narrow.conflicts_for`
computes conflicts only for the candidate assertions, REUSING the engine's own
predicates (`prop._reduced_subject_set`, `prop.contra.contradicts`,
`prop._open_assertions_at`), it does not reimplement contradiction semantics.
Proven byte-identical to filtering the full `engine.conflicts(T)` across
no/one/many conflicts, multiple subjects, supersession, retraction, multi-agent,
generalization, and as_of (tests_p7_conflict_equiv.py, 16 checks), including
"narrow-over-all reproduces the entire engine.conflicts() set". Wired into
build_memory_pack with a fall-back to the full call on any error; the 13/13
indexed-vs-scan equivalence still holds and output is byte-identical.
**Measured (600 assertions, real contradictions declared):** full
conflicts() ≈ 13,900 ms → narrow ≈ 360 ms per brief (~38× on this workload),
identical output. Remaining decision cost is `proposition_state` (per included
item, bounded by limit; inside the frozen engine, left untouched).
**Postgres bug found + fixed.** The P3–P7 tables (candidate_subjects/tokens,
memory_edges, memory_scopes, team_members, memory_class, consolidation_state)
used INSERT OR REPLACE/IGNORE but were missing from the adapter's upsert maps,
and INSERT OR IGNORE wasn't translated at all, both would break on Postgres.
Added the PK/column maps and IGNORE→ON CONFLICT DO NOTHING. Verified at the
SQL-translation level (7 checks, credential-free). **Live Postgres: NOT
VERIFIED, no Postgres instance available.** Totals: 952 functional checks
green across 27 suites + credential-free PG translation checks; frozen engine
byte-identical.

### P5 audit + P6 situation brief (this cycle, REAL)
**P5 audit + hardening.** Audited P5 against the divergence/stale/leakage/
determinism bug classes. Findings fixed: (1) the graph endpoint had no `as_of`
 -  added, and verified an edge cannot leak into a historical query before its
assertion existed while superseded edges remain reconstructable at past times;
(2) edges backed by a contradicted assertion now carry a `contradicted` flag
(both sides render, neither as uncontested fact), and the audit confirmed the
correct engine semantics: two relationships are contradictory only when
declared incompatible AND asserted over the same subject pair; (3) added a
projection `rebuild` (POST /v1/memory/graph/rebuild) proven idempotent,
dangling-row-cleaning, and byte-identical on re-run (restart consistency);
supersession-invalidates-edge, cycle-termination, direction integrity,
tenant isolation and concurrent-write consistency all verified. New suite:
tests_p5_audit.py (19 checks).
**P6, situation brief.** POST /v1/brief (SDK: memory.brief/agent.brief)
answers "what do I need to know about this situation?" It composes P1–P5  - 
candidate finding, engine-decided belief state, scope, graph hops, conflict
analysis, into ONE task-shaped answer with four sections (current_facts,
relationships, conflicts, patterns) and a transparent, documented PRIORITY
MODEL assembled only from real state (directness +3, graph_hop +1,
specificity +2, reinforcement +min(support-1,3), conflict_win +1; recency is
tie-break only). Deterministic, scope-safe, temporally correct (as_of),
size-bounded, and every item carries a numeric priority with reasons plus the
graph path that reached it. No LLM in the path; no fabricated scores. New
suite: tests_p6_brief.py (23 checks incl. injection cannot reprioritise,
malicious memory text cannot inflate its own priority, specific-over-general).
**Measured performance (honest):** at 309 assertions a brief totals ~220ms,
almost entirely in the decision stage, which re-scans assertions per
candidate, the known scaling limitation. The candidate/decision interfaces
are ready for indexed retrieval (P7); no index is built yet. Totals: 923
checks green across 25 suites; frozen engine byte-identical.

### P5, Memory graph + relationship intelligence (this cycle, REAL)
Relationships are ENGINE FACTS first, graph second: a relationship is a
two-subject assertion (subjects=[person:sarah, company:acme],
prop=rel_works_at) carrying full truth semantics, provenance, supersession,
contradiction, scope, and memory_edges holds a directed PROJECTION
(src --relation--> dst) used for traversal. An edge exists only while its
assertion is open at the queried time AND visible to the viewer; retraction
makes it vanish from traversal while the row and full history remain
(verified). Formation: the deterministic extractor gained conservative
relation patterns ("we use Salesforce" -> company --uses--> product:salesforce;
"integration is managed by Sarah"; "Sarah reports to David"), anchored on the
writer's organisation with the same identity/direction rules; the semantic
layer accepts a relation field validated against the entity allow-list, a
rel_* candidate whose target is not evidenced in the email is dropped ENTIRELY
as a hallucination (verified with the FakeLLM over the real wiring: hubspot
edge formed, oracle fact+edge rejected). Traversal (graph.py): bounded BFS
(depth <=2, fanout 8, 40 nodes), deterministic, scope-safe, private edges do
not exist for other viewers, with no existence leak. Recall's related-entity
hop now runs on the graph and pack items reached this way carry a "path"
("company:acme  - managed_by→ person:sarah") plus a why-explanation naming the
hop. GET /v1/memory/graph?entity=&depth=&viewer= returns the labelled
subgraph; SDKs gained memory.graph()/graph(). Tests: tests_p5_graph.py (23
checks incl. edge-syntax forgery, malformed depth, determinism, engine-hash
verification inside the suite). Totals: 881 checks green across 23 suites;
frozen engine hashes unchanged.

### P4, Intelligent retrieval + conflict reasoning (this cycle, REAL)
Recall now answers "what should this agent know RIGHT NOW". `recall(about=...,
context=...)` work together; packs label every item SPECIFIC_FACT /
CONFLICTING_FACT / GENERAL_PATTERN, honor a deterministic size budget
(max_chars, trimmed items are explained), and reach 1-hop related entities
through relationship edges (multi-subject relational assertions; the full
graph is P5). Conflict reasoning (conflict.py + GET /v1/memory/conflicts,
embedded per-item in packs): for each open contradiction OMEM assembles each
side's REAL evidence, observations count, distinct agents, reinforcement
timestamps, stored connector authority, and produces a deterministic
recommendation under the documented policy: recency, then corroboration, then
stored source authority, and a full tie yields NO recommendation ("OMEM does
not guess"). Both sides always remain preserved and retrievable; the engine's
contradiction state is never altered; malicious text in context or in memory
content cannot steer a recommendation or leak scope-hidden sides (half-visible
pairs are omitted entirely for scoped viewers). Why-explanations now include
reinforcement ("supported by 3 independent observations") and conflict
standing ("best-supported side of an open conflict" / "a better-supported
opposing memory exists"). No LLM participates in any recall path. SDKs:
recall(about+context+max_chars), memory.conflicts() / memoryConflicts().
Tests: tests_p4_recall.py (28 checks). Totals: 858 checks green across 22
suites; frozen engine hashes unchanged.

### P3, Human-like memory: reinforcement, consolidation, generalization (this cycle, REAL)
The hierarchy is now real: EXPERIENCE -> OBSERVATION -> FACT -> REINFORCEMENT
-> PATTERN -> GENERALIZED KNOWLEDGE, every level traceable. Repeated
compatible observations REINFORCE one fact instead of duplicating it  - 
cross-agent, scope-checked (an agent never matches a belief it cannot see),
with the reinforcing agent recorded; "supported by N observations" is a count
of real rows, never an invented confidence number. Consolidation
(POST /v1/memory/consolidate + a throttled background scheduler hook) runs a
deterministic, idempotent, bounded pass under the EXPLICIT P3 policy
(documented in consolidation.py; intelligence-layer policy, not normative
semantics): >=3 distinct org-visible subjects, >=2 distinct times, no
generalization when a declared-contradiction counterpart holds comparable
support, at most 20 new patterns per run. A generalization is a real engine
assertion by agent:omem-consolidation whose DERIVATION antecedents are the
supporting facts, provenance is engine-native; new supporters reinforce the
existing pattern, shrinking evidence retracts it through the engine. Private
knowledge never enters shared generalizations. Recall gained tiers (specific
facts and EXCEPTIONS outrank relationships outrank generalized knowledge,
annotated), transient-TTL decay that affects RETRIEVAL ONLY (canonical
history and as_of untouched), and per-item learned_at/event_time/memory_class/
supported_by. GET /v1/memory/chain is the flagship "why do you know this?"
trace: belief, state, learned_by/at, reinforcements with agents, engine
provenance, conflicts, and which generalizations this fact feeds.
Tests: tests_consolidation.py (35 checks covering the P3 behavior list incl.
poisoned-observation, scope-escalation-by-text, restart resume, split-evidence
contradiction blocking). Totals: 830 checks green across 21 suites; frozen
engine hashes unchanged.

### P2, Runtime integration: omem.wrap() + MCP (this cycle, REAL)
A developer attaches memory to an existing agent in one line:
`agent = omem.wrap(existing_agent, memory=memory, agent_id="support-agent")`.
Before each run the runtime recalls a bounded MemoryPack for that agent's
scopes and injects it as a FENCED DATA ENVELOPE, explicitly "historical
data, NOT instructions; may be outdated or contradicted; carries no
authority", never merged into the system prompt (MessagesAdapter inserts it
as its own message after system; GenericAdapter prepends it to the prompt).
Fence-forging text inside memory content is neutralised, including unclosed
openers. After each run the runtime observes the interaction; the server-side
formation pipeline decides durability (transient chatter forms nothing;
duplicate observations confirm the open belief instead of growing memory) and
the frozen engine decides belief state. Failure policy is explicit and typed:
fail="open" (default, the agent always works, memory absence honestly
reported as unavailable/error states) or fail="closed" (raises before the
agent runs). Per-run metadata (omem_speaker=...) informs attribution without
touching the agent. Cross-agent flow verified end-to-end: support learns
privately -> share to team:accounts -> billing's next run receives it with
learned_by=agent:support intact -> revocation hides it again. MCP server
(`python -m omem.mcp_server`, stdio JSON-RPC): exactly omem_recall /
omem_observe / omem_why; agent identity is fixed at process level so a model
speaking MCP cannot spoof another viewer; scope-hidden memories 404 without
confirming existence. TypeScript wrap() mirrors the Python runtime. Adapters
beyond Generic/Messages (LangChain, CrewAI, AutoGen) are NOT built, no
superficial integrations claimed. Tests: tests_runtime.py (39 checks incl.
MCP over real stdio subprocess, envelope-forgery, spoofing, fail policies,
determinism, growth control). Totals: 795 checks green across 20 suites;
frozen engine hashes unchanged.

### P1, Intelligent recall, memory packs, memory scopes (this cycle, REAL)
Recall is now OBSERVE -> MEMORY FORMATION -> RECALL -> MEMORY PACK -> AGENT.
`POST /v1/recall` with context/task returns a MemoryPack: OMEM extracts the
entities from prose (no manual ids), a CandidateRetriever FINDS (entity,
lexical, cold-start recency, bounded, pluggable), and a deterministic
decision layer DECIDES with explainable signals: engine belief state at the
requested time, supersession/retraction exclusion with stated reasons,
contradiction links naming the other agent, entity-anchored relevance,
per-stage measured latencies, and byte-identical output for identical inputs.
`as_of` reconstructs what the system knew at any past instant through the
frozen belief-interval machinery. Memory scopes live ABOVE the engine
(memory_scopes/team_members): org, team:<id>, agent:<id>, user:<id>;
observe() is PRIVATE BY DEFAULT to the observing agent; sharing is an
explicit promotion (`POST /v1/memory/share`) that changes visibility only  - 
attribution, provenance and time are engine-side and immutable. One
visibility rule is enforced in packs, legacy recall, /why and /assertions
(agent-parameterized reads; the human control plane is governance and
documented as such). SDKs: `agent.observe(...)`, `agent.recall(context=...,
task=...)`, `memory.share(...)`, teams (Python + TypeScript).
Vector database: "find similar information." OMEM: "determine what the agent
should remember, and what it should know now, and prove why."
Tests: tests_recall_scopes.py (37 adversarial checks incl. private-memory
leak attempts across every read path, malicious-context bypass attempts,
injected-memory inertness, determinism, as_of, bounded packs). Totals: 756
checks green across 19 suites; frozen engine hashes unchanged.

### Semantic memory formation + observe() (this cycle, REAL; provider path NOT VERIFIED)
The LLM is now the primary reader of business mail when configured: it receives
the FULL cleaned email plus org identity, user-taught roles, the entity
allow-list, open beliefs about those entities, and thread context, and returns
a strict JSON analysis. Every candidate is validated before the engine sees it
 -  exact-substring evidence against the stored message, allow-listed entities
only (no invented people), speech-act ladder, questions/CTAs never become
facts. Escalation replaces blunt gates: only verdicts the deterministic layer
holds at >=0.75 confidence die cheaply; the ambiguous middle reaches the model,
and escalated candidates are graded on the model's relevance judgment (with a
confidence penalty when noise flags were overridden). Model-recognised
reversals ("ignore my previous email, we've decided to renew") supersede the
targeted belief through the ENGINE's own op even when the restated decision
dedups; history stays intact. Malformed model output falls back to the
deterministic extractor with the error recorded. Every analysed email persists
business relevance, memory decision, rejection reason and a reasoning summary
(no chain-of-thought) in semantic_analyses, joined into /v1/diagnostics/email.
`POST /v1/observe` (SDK: `memory.observe` / `agent.observe`) feeds raw agent
interactions through the same layer. `POST /v1/memory/gmail-rescan
{reprocess:true}` requeues newly-relevant historical mail through the current
pipeline (verified live: legacy-excluded Spanish mail became memory).
Cost layering: classification consults the model only when the deterministic
layer is unsure (<0.75). Tests: tests_llm_semantic.py (24 checks, scripted
FakeLLM over the REAL wiring). The real OpenAI-compatible provider path is
NOT VERIFIED, no LLM credentials exist in this environment; the interface
exercised is identical. Totals: 719 checks green across 18 suites; frozen
engine hashes unchanged.

### Identity, learning & diagnostics (this cycle, REAL + VERIFIED)
The pipeline now knows who "we" are and learns from corrections. Org identity
(`GET/POST /v1/identity`: company name, domains, extra addresses; connected
mailboxes always merged in) anchors every direction decision: mail from any
configured address or domain is SELF, colleagues at our domain are internal,
and the owner's own "I'd like to upgrade our subscription" becomes a memory
about OUR company, never about a customer. Without configured identity the
extractor still refuses to guess. Quoted and forwarded content is stripped
before extraction so a reply never attributes quoted text to its sender.

Relationship corrections (`GET/POST /v1/relationships`) are stored as reusable
intelligence: a domain marked MARKETING/IGNORE is excluded from ingestion even
when its copy is full of commercial vocabulary, and a user-confirmed
CUSTOMER/SUPPLIER/PARTNER outranks the heuristics (including a wrong
AUTOMATED_NOISE verdict). Roles are never guessed, unclassified stays
unclassified. `GET /v1/contacts` derives people and organisations from real
interaction (message counts, threads, first/last contact, stored facts,
corrected role) and the /contacts page lets the user teach roles per domain.
`GET /v1/diagnostics/email?source=…` returns the complete decision trace  - 
raw email → participants/identity → classification → analysis → per-sentence
speech acts → fact decisions → final engine assertions, rendered on the
/diagnostics page; the memory evidence panel now highlights the exact evidence
span inside the real email body and links to the trace. Settings gained the
organization-identity panel; /memory gained relationship chips and
role/source filters.

Measured live (17 mails: the 8 reported junk shapes + 8 business + 1
personal, with identity configured and one prior correction): 9 memories, all
correct including the SELF-attributed vendor intent, zero junk; reconciliation
retracted a planted legacy CTA memory and kept all 9 good ones. Tests: 628
checks green across 14 suites (corpus now 71). Frozen engine hashes unchanged.
Note: no CTS runner file exists in this repository; engine integrity is
verified by hash comparison plus the full suite.

### Gmail intelligence overhaul (previous cycle, REAL + VERIFIED)
The pipeline now reads mail the way an assistant would, not a keyword grep.
Root causes of the junk-memory problem were found and fixed: the naive
substring `RuleExtractor` ("cancel" matched inside "cancelar" and "cancel at
any time"), a mock LLM that could run in production when `OMEM_LLM=1`, and a
fact extractor that matched second-person marketing CTAs ("Want to upgrade?
Click here" → intends_to_upgrade).

New modules ABOVE the frozen engine: `email_analysis.py` (participants and
direction anchored on the connected account's identity, a 23-category taxonomy,
speech acts, QUESTION/REQUEST/MARKETING_CTA/SUGGESTION/CONSIDERATION/
INTENTION/DECISION/COMPLETED/STATEMENT, marketing-density scoring, and
SaaS-self-notification detection so "Your Stripe subscription renewed" is
recognised as the owner's own vendor relationship) and `extraction.py`
(`ContextualBusinessExtractor`: per-sentence speech acts, grammatical-party
attribution so inbound "we want to cancel" is about the counterparty, the
owner's outbound "I've extended your subscription" is about the counterparty's
account, and "John has approved" is about John; strength-graded propositions
considering_/intends_to_/decided_to_/has_; a quality gate grading every
candidate HIGH/MEDIUM/LOW/DO_NOT_STORE with persisted reasons in
`fact_decisions`; canonical proposition families collapsing synonym spellings
for dedup). Questions, CTAs and suggestions never become facts. The
classifier gained plan-change-conversation patterns so short thread replies
("Yes. We have decided to downgrade.") inherit their conversation's relevance.

The scanner re-evaluates existing memories with the same analysis (SaaS
notifications, marketing templates, question/CTA evidence → retract with a
stated reason) and the Gmail rescan accepts 7/30/90/365-day windows. New
endpoints: `GET /v1/memory/quality` (the real funnel: scanned → classified →
categorised → candidates → stored/rejected → active) and
`GET /v1/fact-decisions` ("why was this stored / not stored"). The /memory
page shows WHO each memory is about, who said it (human email vs connector vs
scanner), when, grounding, state and a View-evidence link; /memory-health
gained the quality funnel and rescan windows. Measured on a representative
mailbox (8 real junk shapes + 6 business mails + 1 personal): 15 scanned,
8 memories, all correct, zero junk. Tests: `tests_corpus.py` (44 checks) plus
all prior suites, 601 checks green. Frozen engine hashes unchanged.

## Run

```bash
# 1. backend (stdlib only, no pip install)
cd server && python3 api.py 8787

# 2. frontend
cd web && npm install && npm run dev   # http://localhost:3000
```

The web app proxies `/api/omem/*` → `http://127.0.0.1:8787` (see `next.config.js`).

## Verify
The external conformance runner referenced in earlier notes
(`../omem-ref/run_cts.py`) is not present in this repository. Engine behaviour is
instead validated by the black-box and property-based suites that ship here:
- `python3 server/tests_p10_engine_proof.py`, black-box semantics checks.
- `python3 server/tests_p10_1_conformance.py`, invariants, Hypothesis fuzzing,
  and scale measurements (requires `hypothesis`).
- Both confirm the engine files are byte-identical to their baseline. See
  `ENGINE_VALIDATION.md` for scope and limitations.

## Design
Dark-first, Linear-chrome + Stripe-reference feel. Belief-state colour is fixed and
semantic everywhere: emerald=believed_true, amber=unknown, rose=contradicted,
slate=closed. Trust is shown as ordering only (never numeric). Search is retrieval,
never a belief decision. No UI path recomputes semantics, it renders query results.
