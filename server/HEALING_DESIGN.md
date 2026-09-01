# OMEM Self-Healing Subsystem, Design

## Phase 1 findings (existing architecture reused, not replaced)

- **Persistence**: `store.py` `Store` over `_ThreadSafeSqlite` (SQLite) or `db_adapter.PgDB`
  (Postgres, via `OMEM_DATABASE_URL`). Durable engine state is an append-only `ops`
  table replayed through `record()` at boot. Hardening/tables use versioned idempotent
  migrations in `Store._apply_migrations`.
- **Tenancy**: every row is scoped by `org_id` / `project_id`. `Project` holds per-tenant
  runtime state and its own `Engine()`. Isolation is by project.
- **RBAC**: `enterprise.py`, `PERMISSIONS` map (permission -> min role), `role_allows`,
  `Enterprise.can(org, user, perm)`. Roles: owner/admin/developer/viewer.
- **Audit**: `Enterprise.audit(action, actor, org_id, project_id, resource, metadata,
  correlation_id)` -> `audit_events`.
- **Concurrency**: atomic claim pattern already used by ingest:
  `UPDATE ... SET state='running' WHERE id=? AND state='pending'` (rowcount==1 wins).
- **Engine invariant**: the server "invents no memory semantics"; every engine write goes
  through `record()`. Healing must NOT pollute engine ops, it is *infrastructure* state.

## Decision: healing state is infrastructure, in its own tables (not engine ops)

Failures/plans/recoveries/health/snapshots are operational metadata, not beliefs. Putting
them in the engine ops log would violate the "engine invents no semantics" invariant and
mix untrusted failure text into the reasoning store. So: **new durable tables**, created via
the existing idempotent migration mechanism, scoped by `org_id`+`project_id`, reusing the
existing DB/ audit/ RBAC primitives. No parallel storage engine.

## New tables (all org_id+project_id scoped; created in Store._apply_migrations, idempotent)

- `heal_failures`, failure records (redacted). fingerprint, component, error_type,
  message, severity, resolved, occurrences, context(JSON, redacted), ts.
- `heal_diagnoses`, failure_id -> diagnosis, confidence, plan(JSON), outcome. The
  failure->diagnosis->repair->outcome memory that improves over time.
- `heal_recoveries`, a recovery attempt: failure_id, state machine column, claim owner,
  plan(JSON), actions_run(JSON), verification(JSON), outcome, attempts, ts. The atomic
  claim lives here (state: failed->claimed->diagnosing->repairing->verifying->recovered/failed).
- `heal_health`, component health reports (component, status, reason, metadata, ts).
- `heal_snapshots`, known-good state markers (label, kind, payload(JSON), ts).

## Modules

- `healing.py`, the subsystem. Pure-Python, stdlib only. Classes:
  - `Redactor`, strips secrets/tokens/credentials before persistence.
  - `ActionRegistry`, maps action_type -> (risk_class, handler). Handlers are the ONLY
    things that can execute; the LLM cannot inject new ones. Built-in low-risk handlers
    (retry, clear_cache, rebuild_index, reconnect, reload_config, restart_worker) operate
    on registered components only. Medium/high need explicit policy + approval.
  - `Policy`, evaluates a plan against RBAC + risk class + capability boundary. Returns
    permit/deny per action with reasons. High-risk => requires approval flag; never auto.
  - `HealingStore`, CRUD over the new tables, atomic claim, fingerprint idempotency.
  - `Healer`, orchestrates the lifecycle (handleFailure): capture -> recall prior ->
    (LLM diagnose hook) -> plan -> policy -> claim -> execute -> verify -> record ->
    rollback/retry -> structured result. Finite recovery budget; loop/oscillation guards.
- `tests_healing.py`, regression + adversarial suite.

## LLM boundary

The `Healer` accepts an optional `diagnose` callable (the reasoning component). It may
PROPOSE a plan (JSON). OMEM's `Policy` + `ActionRegistry` decide what is permitted, safe,
and executable, and `verify` decides success. Retrieved memories and error text are DATA:
they are redacted, never eval'd, never used to select a handler except by exact action_type
match against the registry. An error string cannot name a handler that isn't registered,
and cannot raise its own risk class.

## Safety boundaries

1. Only registered action handlers execute. No shell, no eval, no dynamic import.
2. Every action has a risk class. Medium/high require policy approval; high never
   auto-executes (requires `approved_by` present + RBAC `heal.execute.high`), and
   the approval must arrive on a credential that is not the agent's. An
   agent-bound key is refused however it fills in `approved_by`, because that
   field is a name the caller typed and the caller can be the agent being
   approved. A human's decision reaches OMEM through a console session or a key
   held by a person. The name is recorded as what that credential holder
   asserted; the identity in the record is the principal the auth layer
   resolved.
3. Redaction on all persisted context.
4. Atomic claim => one active recovery per (project, component) at a time.
5. Fingerprint idempotency => the same failed strategy is not retried endlessly
   (fingerprint = hash(component + error_type + plan_signature)); capped attempts.
6. Finite global recovery budget per component per window (repair-storm guard).
7. Healer-of-healer: recovering OMEM's own components is allowed but depth-limited
   (a recovery cannot spawn a recovery for the healing subsystem itself -> fail closed).
8. Tenant isolation: every query is filtered by org_id+project_id from the request scope;
   a recovery cannot read another tenant's rows.
9. Fail-closed: if the healer errors internally, it records and escalates; it never
   retries itself uncontrolled.

## New permissions (added to enterprise.PERMISSIONS)

- `heal.read` (viewer), read failures/health/history
- `heal.report` (developer), report failures/health
- `heal.execute.low` (developer), run low-risk repairs
- `heal.execute.medium` (admin), run medium-risk repairs
- `heal.execute.high` (owner), run high-risk repairs (still needs explicit approval)

## API (added to api.py, all RBAC-gated + audited + project-scoped)

- `POST /v1/healing/failures`, report a failure (heal.report). Returns failure + prior memory.
- `POST /v1/healing/handle`, full autonomous loop for a failure (heal.execute.*). Returns result.
- `GET  /v1/healing/failures`, list failures (heal.read).
- `GET  /v1/healing/failures/{id}`, failure + diagnosis + recovery history (heal.read).
- `POST /v1/healing/health`, component health report (heal.report).
- `GET  /v1/healing/health`, aggregated system health (heal.read).
- `POST /v1/healing/snapshots`, record known-good state (heal.report).

## SDK

- Python `Memory.healing`: `.report(...)`, `.handle(...)`, `.failures()`, `.failure(id)`,
  `.health_report(...)`, `.health()`, `.snapshot(...)`. Thin wrappers over the API.
- `createOMEM({healing:{enabled}})` equivalent: SDK `Memory(healing=True)` exposes `.healing`.

## Non-goals / limitations (documented, not silently worked around)

- OMEM ships handlers for repairs it can perform on registered in-process components. It does
  NOT gain shell/infrastructure access. Repairs needing host/infra changes are represented as
  high-risk actions that require developer-provided handlers + approval, OMEM will not invent
  that capability. This is the correct capability boundary, not a gap.
