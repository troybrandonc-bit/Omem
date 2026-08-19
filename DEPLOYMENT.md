# OMEM Cloud, Deployment

## Architecture
```
Frontend (Next.js)  ──►  API (Python stdlib http.server / ThreadingHTTPServer)
                              │
                              ├─ Engine (frozen OMEM v1.0 reference)
                              ├─ SQLite persistence + append-only ops log
                              ├─ In-process scheduler (workers)
                              └─ Providers: Google, LLM, Stripe (env-gated)
```

## Environments
Set `OMEM_DB` per environment to isolate data:
- development: `server/data/omem.db` (default), demo project seeded
- staging / production: distinct DB paths or hosts; do NOT seed demo

## Required environment variables (production integrations)
| Variable | Enables | Without it |
|---|---|---|
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` / `GOOGLE_REDIRECT_URI` | real Gmail OAuth + sync | mock transport (tests only) |
| `OMEM_LLM_API_KEY` / `OMEM_LLM_BASE_URL` / `OMEM_LLM_MODEL` | real LLM extraction (any OpenAI-compatible endpoint) | rule/mock extractor |
| `STRIPE_SECRET_KEY` | real billing (test mode) | checkout returns 503 (no fake success) |
| `OMEM_HOST` | bind address (0.0.0.0 in containers) | 127.0.0.1 |

`python api.py` prints which integrations are CONFIGURED vs falling back.

## Health & lifecycle
- `GET /v1/health` → `{status, cts, db, scheduler_runs}` (200 healthy, `db:false` degraded)
- SIGTERM/SIGINT → graceful shutdown (stops scheduler, drains server)
- Migrations: schemas are `CREATE TABLE IF NOT EXISTS`, applied idempotently at boot

## Backup / restore
The single SQLite file is the entire SaaS state (engine memory is replayed from
the ops log). Back up with `sqlite3 omem.db ".backup backup.db"`; restore by
swapping the file and restarting (boot replays the ops log through the engine).

## PostgreSQL (verified)
Set `OMEM_DATABASE_URL=postgres://user:pass@host/db` and the SaaS layer runs on
PostgreSQL through `db_adapter.py` (same code paths; all 214 SQLite checks pass
unchanged on PG, plus 14 PG-specific checks). SQLite remains the credential-free
dev/test default via `OMEM_DB`. Schemas apply idempotently at boot; the
append-only ops log replays through the frozen engine identically on both
backends. Backup: `pg_dump omem > backup.sql`; restore: `psql omem < backup.sql`
then restart (boot replays the ops log). Transaction model: the adapter runs
autocommit (statement-level atomicity, matching the codebase's write+commit
pattern); the ops log makes this sufficient for engine-state correctness.

## Automated backups (verified)
`backups.py` runs scheduled backups via the in-process scheduler (env
`OMEM_BACKUP_DIR`, `OMEM_BACKUP_INTERVAL`, `OMEM_BACKUP_RETAIN`). Each run records
a `backup_runs` row (running/completed/failed/pruned) with bytes + error; a
failure is never silent (status='failed', `failing:true` surfaced in
`/v1/admin/backups` and observability). Retention prunes old files. Restore
verification (`/v1/admin/backups/verify`) restores the latest dump into a scratch
DB and compares the ops-log row count to live, VERIFIED on PostgreSQL. The DB
user needs the `CREATEDB` privilege for restore verification
(`ALTER USER omem CREATEDB;`).

## Hardening migrations (verified)
Versioned, idempotent migrations tracked in `schema_migrations`: v1-baseline,
v2-indexes (6 high-value indexes on both backends), v3-fks (FK constraints with
ON DELETE CASCADE, PostgreSQL only, applied after all module schemas exist, and
only marked complete when every constraint is present so a partial apply retries
next boot). FK cascade verified: deleting a connector removes its jobs/sources.

## MFA + session security (verified)
TOTP MFA (RFC 6238, stdlib): enroll -> activate with a valid code -> enforced at
session creation (`/v1/session` returns 401 mfa_required without a valid code).
Sessions now expire (30d default) and are revocable (`/v1/sessions/revoke`);
expired and revoked sessions return 401. All verified.

## Durable workers (verified)
`python3 worker.py` runs a standalone worker process claiming jobs via
`FOR UPDATE SKIP LOCKED` on PG (the standard DB-queue pattern), multiple
workers run concurrently with zero double-claims (verified with 2 workers /
20 jobs). Heartbeats, exponential backoff, dead-lettering, cancellation and
stale-job recovery come from the existing job machine. Env: `WORKER_ID`,
`WORKER_ONCE=1` for drain-and-exit.

## Authentication (required reading before exposing this)
`OMEM_AUTH=local` (default) has no passwords; the dashboard provisions a session
against whatever server it reaches. The server therefore refuses to bind a
non-loopback address in local mode unless `OMEM_ALLOW_INSECURE_BIND=1` is set.

For a deployment other people reach, set `OMEM_AUTH=password` and a real
`OMEM_MASTER_KEY` (the server will not start on the development default).
Accounts then use PBKDF2-SHA256 passwords, signup returns 409 rather than a
session for an already-registered address, and TOTP is enforced where enrolled.
`OMEM_ADMIN_EMAILS` gates `/v1/admin/*`, which spans every tenant — it is only a
boundary in password mode.

The server speaks plain HTTP. Terminate TLS at a proxy in front of it.

## What is NOT yet production infrastructure
- The in-process scheduler remains for zero-setup dev; production should run
  `worker.py` processes instead (the API still enqueues via the same tables).
- No object storage, no CDN, no secrets manager wired (env vars only).
- No TLS in the server itself; a terminating proxy is mandatory.
- Memory content is not encrypted at rest — only stored OAuth tokens are. Use
  disk or database encryption underneath if that matters.
- The engine is authoritative IN PROCESS and rebuilt by replaying the ops log at
  boot, so a second API replica would not see the first one's writes. One process
  only: no horizontal scaling, no rolling deploys, and boot time grows with total
  history (there is no snapshot or log compaction).
- The audit log is append-only by convention, not hash-chained.
- No SSO/OIDC/SAML/SCIM.
