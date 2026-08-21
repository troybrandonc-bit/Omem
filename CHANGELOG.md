# Changelog

Release notes for people using OMEM. Engineering history lives in
`CHANGELOG-dev-notes.md`; this file is what changes for you.

## 0.2.1 - unreleased

Self-healing was in the server and nowhere in the product. This release is
mostly about making what OMEM already does visible, and fixing two places
where the dashboard described what it did as *less* than it did.

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
