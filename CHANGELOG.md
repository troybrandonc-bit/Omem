# Changelog

Release notes for people using OMEM. Engineering history lives in
`CHANGELOG-dev-notes.md`; this file is what changes for you.

## 0.2.7 - 26 Aug 2026

### Added

- **Listed in the MCP Registry.** `server.json` describes the `omem-mcp` server
  for the official registry at `registry.modelcontextprotocol.io`, so MCP
  clients can discover it rather than being told about it. The environment
  variables are declared there too, including that `OMEM_AGENT` and `OMEM_USER`
  are process configuration and not tool arguments, which is the whole reason a
  model cannot ask this server for someone else's memory.

### Fixed

- **Running on PostgreSQL still created a local data directory.** `Store`
  created the directory for its SQLite file before working out which backend it
  was going to use. Under `OMEM_DATABASE_URL` that file is never opened — the
  data lives in PostgreSQL — so the directory was made for something that would
  never exist. Harmless in itself, but it meant the path was being treated as a
  filesystem location before anything had established that it was one, and a
  caller passing the database URL as that path (reasonable, since the path is
  unused under PostgreSQL) got a silently-created directory tree named after the
  URL on Linux, and a hard `OSError` on Windows. The backend is now chosen
  first, and the filesystem is touched only when SQLite is actually in use.

## 0.2.6 - 26 Aug 2026

**Security fix. Upgrade if you use agent-bound API keys.** This closes the last
route in the family 0.2.3, 0.2.4 and 0.2.5 worked through.

### Fixed

- **A bound key could write as another agent by creating a connector.** 0.2.3
  and 0.2.4 stopped an agent-bound key attributing a claim to another agent on
  every route that records memory, and 0.2.5 stopped it minting its way out of
  the binding. `POST /v1/connectors` was none of those routes, and a connector
  **is** an OMEM agent: every assertion it produces is recorded under the
  `agent_id` given when it was created.

  So a key bound to `agent:bob` could not write as `agent:alice` directly — it
  was refused with a 403 — but it could create a connector with
  `agent_id: "agent:alice"`, and everything that connector ingested went onto
  the permanent record as alice's belief.

  Three things made it worse than the direct write it was blocked from:

  - **It persists.** One request establishes the channel. Every future poll and
    every webhook delivery writes as the impersonated agent.
  - **It supersedes.** The ingestion path records supersessions under the same
    identity, so the connector could take another agent's existing beliefs off
    the record under that agent's own name — the capability 0.2.4 singled out
    as the more serious one.
  - **It could outrank everyone.** `authority` was taken from the request body
    and written to the trust column unchecked. Conflict resolution breaks a tie
    on the highest authority among the connectors sharing an agent id, so a
    forged connector at `authority: 999` won every contradiction it entered.

  Now an agent-bound key may only create connectors that write as its own agent
  or as a `connector:<kind>` identity, `authority` must be a number between 0
  and 1, creating a connector requires `connector.manage` exactly as deleting
  one always has, and the creation is audited.

  The rule is an allowlist rather than a check on the `agent:` prefix, because
  agent ids are frequently unprefixed — this README uses `support` and the
  quickstart uses `support-bot` — and a prefix check would have refused the
  obvious forgery while passing those straight through.

  **Unbound keys and sessions are unchanged**, which is what a single trusted
  process provisioning connectors for many agents needs. **Scope is unchanged
  from 0.2.3 to 0.2.5:** a single project, no cross-tenant access, no data
  disclosure.

- **Over MCP, the model could name the end user whose memory it read.** The MCP
  server pins the agent identity to the process (`OMEM_AGENT`) precisely so a
  model cannot ask for another agent's private memory. But `user` — the other
  axis that scopes memory — was a tool *argument*, advertised in the tool schema
  as "unlocks user-scoped memory". It did exactly that, for whatever value the
  model put there, so a model could read memories scoped `user:<anyone>` by
  naming them.

  The end user is now pinned to the process too, via `OMEM_USER`, and the
  argument is gone from the schema. Leave `OMEM_USER` unset and no user-scoped
  memory is visible at all, which is the right default for a process that has
  not been told who it is acting for.

  This only ever affected `omem-mcp`. The HTTP API is unchanged: there the
  caller is your own application, which is trusted to say which end user it is
  acting for. The whole point of the MCP surface is that the model is not.

  **If you run `omem-mcp` and use `user:` scopes**, set `OMEM_USER` in your MCP
  client config — see the README — and treat user-scoped memory as having been
  readable by the model before this release.

- **The wheel shipped a developer's test cache.** 0.2.2 through 0.2.5 included
  48 `.hypothesis` files — a fifth of the archive, every byte of it one
  machine's local property-testing cache — plus `run_tests.py`, which the build
  hook already intended to exclude and missed because it tested for names
  starting with `tests`. `run_tests` mattered slightly more than dead weight:
  `omem-server` puts the bundled server directory first on `sys.path`, so it
  became an importable top-level module in the process. Neither ships now.

- **A memory-sharing grant did not record who granted it.** When a caller set
  `scope` on `POST /v1/assertions`, the assertion was attributed to the
  identity resolved from the key, but the grant beside it recorded the raw
  `agent` field from the request body. Agent-bound callers are told to omit
  that field and let the binding apply, so for exactly those callers
  `granted_by` was stored as null. It now records the resolved identity.

- **`DELETE` did whatever `POST` does.** The handler for `DELETE` was a bare
  call into the `POST` dispatcher, so every route that accepts a `POST` also
  answered a `DELETE` — and answered it by doing the `POST`.
  `DELETE /v1/assertions` ran the create handler and returned `201` with a new
  assertion written to the record.

  Nothing was bypassed by this: authentication, project scoping and the
  read-only key check all run before the dispatch either way, so no caller
  could reach anything they could not already reach with a `POST`. What it
  broke is the meaning of the verb for everything sitting in front of OMEM. A
  reverse proxy rule, a WAF policy, or an audit review that treats `DELETE`
  differently from `POST` was reading a method that did not describe the
  request, and a call that *created* data was indistinguishable in any
  method-keyed log from one that destroyed it.

  Only `DELETE /v1/connectors/{id}` and `DELETE /v1/projects/{id}` implement
  the verb. Everything else now returns `405` with an `Allow` header and the
  usual JSON error body (`reason_code: method_not_allowed`). Both real delete
  routes are unchanged.

  If you have a client sending `DELETE` to a route that is not one of those
  two, it was creating or updating rather than deleting, and it now fails
  loudly instead.

### Changed

- **The TypeScript SDK builds.** `sdk/typescript` had no build step, so
  `package.json` pointed `main` at raw TypeScript and the parity test imported
  a `dist/` that no command produced — running it failed immediately with
  `ERR_MODULE_NOT_FOUND`. It now compiles to ESM with type declarations:

  ```bash
  cd sdk/typescript
  npm install && npm test    # builds, then runs the parity suite against a live server
  ```

  The suite starts a real Python server and drives the built SDK against it:
  42 checks, all passing. It runs in CI on every push, so the SDK can no longer
  drift from the API unnoticed. Still not on npm, and it still does not cover
  the whole Python surface — `npm test` is what tells you where the gaps are.

## 0.2.5 - 26 Aug 2026

**Security fix. Upgrade if you use agent-bound API keys — this one makes 0.2.3
and 0.2.4 actually effective.**

### Fixed

- **An agent-bound key could mint its way out of the binding.** 0.2.3 and 0.2.4
  stopped a bound key writing under another agent's name on every route that
  records memory. `POST /v1/keys` was not one of those routes, and it issued
  credentials: a key bound to `agent:bob` could request a key with **no**
  `agent_id` and role `owner`, receive it, and then speak as any agent at all.

  The boundary was enforced everywhere except at the door where you collect a
  new one, which meant the previous two fixes could be stepped around in a
  single request.

  Three things changed:

  - A bound key may only create keys bound to the **same** agent.
  - No key may create a key with a **higher role** than its own.
  - `POST /v1/keys` and `POST /v1/keys/{id}/revoke` now check `key.create` /
    `key.revoke` at all. They previously checked no permission, so a `viewer`
    key — the read-only role — could mint itself a writable one.

  `key.create` remains available to `developer` and above, which is unchanged
  and deliberate. Unbound keys, sessions, and normal key management are
  unaffected: an admin key still issues keys as before, and a bound key may
  still issue keys for itself.

  **Scope is unchanged:** a single project, no cross-tenant access, no data
  disclosure.

  Anyone who issued agent-bound keys before 0.2.5 should review the keys on
  their projects (`GET /v1/keys?project=...`) for credentials they did not
  create, and revoke anything unexpected.

- **Any authenticated account could push into another tenant's webhook
  connector.** `POST /v1/webhooks/{connector_id}` resolved the connector by id
  and accepted the payload without checking who was asking. A valid credential
  from *any* project on the server was enough to inject items into another
  project's ingestion pipeline, where they run through extraction and
  classification and can become memory in a project the caller has no access to.

  This is the only issue found in this round that crossed the tenant boundary,
  and it crossed it in the direction that writes. It required a valid account on
  the same server and knowledge of the connector id; unauthenticated requests
  were already refused.

  The receiver now requires that the caller own the connector's project. A
  foreign connector returns 404 rather than 403, so the endpoint cannot be used
  to discover which connector ids exist.

  Self-hosted single-user installs (`OMEM_AUTH=local`) were not exposed: there
  is only one tenant. Multi-user servers (`OMEM_AUTH=password`) were.

## 0.2.4 - 26 Aug 2026

**Security fix, and it completes 0.2.3.** Upgrade if you use agent-bound API
keys. If you already upgraded to 0.2.3, upgrade again.

### Fixed

- **0.2.3 fixed one route; the same flaw was on four.** That release stopped an
  agent-bound key attributing a new claim to another agent via
  `POST /v1/assertions`, and stopped there. The identical pattern — recording
  the caller's `agent` field without resolving it against the key's binding —
  was still present on:

  - `POST /v1/assertions/{id}/supersede`
  - `POST /v1/assertions/{id}/retract`
  - `POST /v1/coreference`
  - `POST /v1/coreference/split`

  Supersede and retract are the more serious two. They do not merely put another
  agent's name on a new claim: they take that agent's existing belief off the
  record under their own name, so the history reads as though that agent revised
  or withdrew it. A key bound to `agent:bob` could retire what `agent:alice` was
  on record as believing, and the audit trail would agree.

  Every route that records an attributed write now resolves identity through the
  same guard, and the test suite covers each one rather than only the first.

  **Scope is unchanged from 0.2.3:** a single project, no cross-tenant access, no
  data disclosure. Unbound keys and session tokens are unaffected.

  If you rely on agent-bound keys for attribution, treat supersessions,
  retractions and coreference claims written by a bound key before 0.2.4 as
  unverified for the agent they name, on the same basis as assertions before
  0.2.3.

## 0.2.3 - 25 Aug 2026

**Security fix. Upgrade if you use agent-bound API keys.**

### Fixed

- **An agent-bound key could file a claim under another agent's name.** A key
  minted with an `agent_id` constrained what it could *read* but not who it
  could write *as*: `POST /v1/assertions` passed the caller's `agent` field
  straight through, so a key bound to `agent:bob` could record an assertion
  attributed to `agent:alice`. Asking `why()` afterwards returned a provenance
  chain naming alice — the exact question provenance exists to answer.

  The identity guard already existed and was already correct; it was applied on
  every read surface (recall, brief, observe, chain, graph, conflicts, and the
  `viewer` parameter on this same route) and not on the write. This adds the
  missing call.

  **Scope:** within a single project. API keys remain project-scoped, so no
  other tenant was reachable. It matters wherever each agent holds its own bound
  key and the record is trusted to say who spoke, which is the reason to bind a
  key at all.

  **Unbound keys are unaffected** and may still name any agent, which is what a
  single trusted process writing for several agents depends on.

  If you have relied on agent-bound keys for attribution, treat assertions
  written by a bound key as unverified for the agent they name: the record
  cannot distinguish a genuine claim from a forged one after the fact.

- **`omem-data/` was not ignored by git.** `omem-server` writes it into whatever
  directory it is started from, and the quickstart simply says to run it — so
  anyone following the quickstart inside a clone got their memories, hashed API
  keys and organisation rows sitting untracked in the working tree.

## 0.2.2 - 25 Aug 2026

A correctness and honesty release. Nothing about how you call OMEM changes; the
dashboard stops lying to you on first load, and the documentation stops
describing a product that does not exist.

### Fixed

- **The dashboard's first load was silently empty.** On any browser with no
  stored session, the app raced itself: the provider that resolves your project
  asked for it before the shell had established a session, got a 401, and gave
  up permanently. Every panel then queried `?project=` and got a 404, so a
  brand-new install showed "No conflicts" and empty lists **on a server with
  your data in it**. Startup is now a single ordered sequence, so the state you
  see is the state that exists.
- **A failed read no longer reports itself as an empty result.** Every list
  rendered `!data || data.length === 0` as an empty state, which collapses "the
  request failed" into "there is nothing here" — and answered both with a
  confident sentence about your data. The Conflicts screen said "Every
  proposition has a consistent belief state" when it had simply failed to look.
  Unreadable is now its own state, and it says so.
- **`omem.__version__` reported 0.1.2** while the package was 0.2.1. It is now
  checked against `pyproject.toml` at release time so it cannot drift again.

### Documentation

The published docs told you to run `pip install omem` (the package is
`omem-infrastructure`; `omem` is a different project), `npm i @omem/sdk` (never
published), and `omem.Client()` / `Client(embedded=True)` / `mem.entity()` /
`mem.event()` — none of which exist. There was a Go SDK tab for an SDK that is
not in this repository, and curl examples against `https://api.omem.dev`, a
domain that does not resolve, carrying an `sk_live_` key format OMEM does not
issue. Following the quickstart produced an `ImportError` on the first line.
Every sample is now taken from `QUICKSTART.md`, which CI runs verbatim against a
live server on every push.

"CTS 29/29" has been removed from the marketing footer, the security page, the
developers page and the server's startup banner. `ENGINE_VALIDATION.md` states
that the conformance suite behind that figure is not in this repository and the
number "should not be read as independent validation" — so it should not have
been the most prominent claim on the site. What is checkable is reported
instead: the frozen engine version, whose digests the suites verify.

### Project

- The contributor licence agreement is replaced by a **Developer Certificate of
  Origin**. MIT already permits sublicensing and sale, so the CLA's stated
  rationale did not hold, and it charged contributors an unreviewed legal
  document for an option this project has committed never to exercise. Sign off
  with `git commit -s`. See [DCO.md](DCO.md).
- `LICENSE` names a copyright holder who exists.
- Dependabot now watches npm, GitHub Actions and pip. All workflow actions moved
  to Node 24 generations.

## 0.2.1 - 21 Aug 2026

**If you are on Python 3.9, upgrade.** 0.2.0 did not import at all on it, so
`pip install omem-infrastructure` failed for the oldest version this project
says it supports. See below.

Otherwise this release is mostly about self-healing, which was in the server and
nowhere in the product, and about fixing three places where the dashboard
described what OMEM did as *less* than it did.

### New

- **Self-healing is visible.** The subsystem that records failures and runs
  repairs under policy has been in the server since it was written, and appeared
  nowhere in the dashboard. It was a feature you had to read the source to know
  existed. There is now a **Self-healing** screen: component health, the failure
  record, and each repair drawn as the loop it actually is (claimed, diagnosing,
  repairing, verifying, recovered) with the step it stopped at marked.
  A health indicator sits in the top bar on every screen and stays quiet while
  healthy. OMEM also now reports on five of its own components, store, writer
  lock, scheduler, ingest queue, backups, so the screen says something true on a
  fresh install rather than "nothing has reported yet".
- **Refused repair plans are recorded and readable.** When a proposed plan
  contains an action OMEM has not registered, the plan is denied and nothing
  executes: that has always been true, but it left no trace above the database,
  and the dashboard reported it as "no recovery was attempted". Each proposed
  action now shows the registry's risk class and the policy's reason for
  permitting or refusing it. `GET /v1/healing/failures/{id}` returns a
  `diagnoses` array alongside `recoveries`.
- **Repairs record their provenance.** A recovery now stores whether its plan
  came from a prior repair that verified (`memory`) or from a model proposal
  (`llm`), which attempt it is out of the cap for that strategy, and who was
  named as approving it when the plan contained a high-risk action.

### Fixed

- **The package did not import on Python 3.9.** `omem/__init__.py` annotated the
  `Memory` constructor with `project: str | None`. PEP 604 unions are evaluated
  when the class is defined and are a `TypeError` before 3.10, so every 3.9 user
  got this on `import omem`, and `omem-server` never started:

  ```
  TypeError: unsupported operand type(s) for |: 'type' and 'NoneType'
  ```

  Annotations are now deferred, so the syntax stays readable and 3.9 works.
  `requires-python` was always `>=3.9`; now that is true.

- **A repair OMEM refused left no readable trace.** A plan proposing an action
  that is not registered is denied and nothing executes, which has always been
  the case, but it produced a diagnosis and no recovery, and the dashboard reads
  recoveries. So the refusal displayed as "no recovery was attempted". Refused
  plans are now shown with the risk class and the policy's reason for each
  proposed action.

- **The bundled dashboard shadowed the Gmail OAuth callback.**
  `/oauth/gmail/callback` is the one API route that cannot live under `/v1/`,
  because Google redirects a browser to it. The static-file handler runs before
  every GET route and excluded only `/v1/`, so in any build with the dashboard
  bundled, which is every published wheel, the page was served and the handler
  never ran. On success it also redirected to `OMEM_APP_URL`, defaulting to
  `localhost:3000`, which is right for `npm run dev` and dead for `pip install`.

- **A failed repair rendered as though nothing had been attempted.** The
  recovery rail matched the loop's five success states against the state the
  engine writes on failure, matched nothing, and greyed out every step, so a
  repair that claimed a component, diagnosed it, ran two actions and failed
  verification displayed as if it had never started. Progress is now derived
  from what the recovery left behind, and the step it stopped at is marked.
- **A failed health request left the page loading forever.** An error meant the
  query resolved with no data, which the page could not tell apart from "still
  loading", so a 403 or an unreachable server pulsed placeholders indefinitely.
  It now says what went wrong and offers a retry. The top-bar indicator no
  longer disappears on error either. Vanishing made the failure mode look
  exactly like the healthy one.
- **A component could report healthy next to its own unresolved failures.** Both
  readings are honest and they can disagree; the page now shows the
  disagreement instead of picking one.
- **`attempts` was always 0.** It was written once at claim time and never
  updated, so a recovery could not say how close a strategy was to its retry
  cap. It now records the attempt's ordinal, and reads "attempt 3 of 3,
  strategy exhausted".
- **Timestamps and the recovery rail failed the contrast minimum.** `--faint`
  measured 3.62:1 in light and 3.80:1 in dark against a panel, below the 4.5:1
  floor for text, and it styles every 11px timestamp in the product. Both are
  now pinned to the floor against the worst surface they sit on. The rail's
  done-versus-not-done signal was a background tint measuring 1.15:1; it now
  uses the same marks as belief state, which survive a greyscale screenshot.
- Expandable rows announce themselves to screen readers, relative times carry
  the absolute timestamp, and open failures are separated from handled ones.


## 0.2.0 - 19 Aug 2026

**Upgrading from 0.1.x: read the two notes at the bottom before you do.**

### Security - please upgrade

`POST /v1/session {"email": "..."}` returned a valid 30-day session for **any**
address. There was no password anywhere in 0.1.x, so knowing an email address
was the entire credential, including for the addresses in `OMEM_ADMIN_EMAILS`,
which reach every project on the server. Enrolling TOTP did not help, because
`/v1/signup` handed back a session for an existing address without checking it.

If you ran 0.1.x on anything other than loopback, treat its data as exposed.

OMEM now has two modes and refuses the configurations that gave it away:

- **`OMEM_AUTH=local`** (default) keeps the no-login flow that makes setup a
  minute, and **refuses to bind a non-loopback address**. With no passwords,
  being unreachable is the access control, so it is now enforced rather than
  assumed. Override deliberately with `OMEM_ALLOW_INSECURE_BIND=1`.
- **`OMEM_AUTH=password`** stores PBKDF2-SHA256 passwords, enforces TOTP where
  enrolled, and answers 409 (not a session) for an address that already has an
  account.

### New

- **First run gives you a workspace.** `omem-server` now prints a project id, an
  API key, and a paste-ready snippet instead of leaving you to POST to
  `/v1/signup` by hand.
- **TLS.** `OMEM_TLS_CERT` + `OMEM_TLS_KEY` and the server speaks HTTPS itself
  (TLS 1.2 floor). Half a configuration is a startup error, not a silent fall
  back to plaintext.
- **Encryption at rest.** `OMEM_ENCRYPT_AT_REST=1` encrypts the operations log,
  ingested source payloads and stored evidence with AES-GCM. Needs
  `pip install "omem-infrastructure[encryption]"`. **Lose `OMEM_MASTER_KEY` and
  you lose the data**: there is no recovery path, and no key rotation yet.
- **Tamper-evident audit log.** Rows are hash-chained per organization;
  `GET /v1/audit/verify` recomputes the chain and reports the first altered or
  deleted row. Anchor the head hash somewhere outside OMEM for it to mean
  anything against someone with database access.
- **PostgreSQL is installable.** `pip install "omem-infrastructure[postgres]"`.
  The driver was never declared, so `OMEM_DATABASE_URL` used to fail with a bare
  `ModuleNotFoundError`.
- `QUICKSTART.md`, and a dashboard redesign.

### Fixed

- **The dashboard showed nothing.** It defaulted to a project literally named
  `demo`, which only exists with `OMEM_SEED_DEMO=1`. Every query went to a
  project that did not exist, so memories written through the SDK were invisible
  no matter how many there were. It now selects a real project, the one with
  memories in it.
- **The dashboard and the SDK used different projects.** A developer signing up
  under their own address got a project the dashboard could not see. One local
  machine is now one local workspace.
- Inviting a member created a live session for their account.
- Billing marked an organization as paid the moment a Stripe customer was
  created, before any payment. Webhook signatures were verified against a
  re-serialised body and so could only ever fail against real Stripe.
- A second server process on one database silently kept a second copy of the
  engine; it now refuses to start and says which process holds the database.

### Two things to know before upgrading

**1. Propositions are normalised, and existing ones change on first boot.**
Spelling is canonicalised at the boundary: `Prefers_Annual_Billing`,
`prefers annual billing` and `prefers-annual-billing` are now one claim rather
than three unrelated facts about the same customer. This applies on the replay
path, so **stored propositions are renormalised the first time 0.2.0 starts**.
That is the intended fix, but it changes belief identity for data written by
0.1.x, back up `omem-data/omem.db` first, and check anything that pinned exact
proposition strings.

`RETRACTED` is untouched, and accented and non-Latin tokens survive intact.

**2. Signup no longer returns a session for a known address** in password mode.
Anything built against the old behaviour breaks, deliberately.

## 0.1.2 - 11 Aug 2026

First published build. Superseded, see the security note above.
