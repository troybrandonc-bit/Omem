# Changelog

Release notes for people using OMEM. Engineering history lives in
`CHANGELOG-dev-notes.md`; this file is what changes for you.

## 0.2.0 — unreleased

**Upgrading from 0.1.x: read the two notes at the bottom before you do.**

### Security — please upgrade

`POST /v1/session {"email": "..."}` returned a valid 30-day session for **any**
address. There was no password anywhere in 0.1.x, so knowing an email address
was the entire credential — including for the addresses in `OMEM_ADMIN_EMAILS`,
which reach every project on the server. Enrolling TOTP did not help, because
`/v1/signup` handed back a session for an existing address without checking it.

If you ran 0.1.x on anything other than loopback, treat its data as exposed.

OMEM now has two modes and refuses the configurations that gave it away:

- **`OMEM_AUTH=local`** (default) keeps the no-login flow that makes setup a
  minute, and **refuses to bind a non-loopback address**. With no passwords,
  being unreachable is the access control, so it is now enforced rather than
  assumed. Override deliberately with `OMEM_ALLOW_INSECURE_BIND=1`.
- **`OMEM_AUTH=password`** stores PBKDF2-SHA256 passwords, enforces TOTP where
  enrolled, and answers 409 — not a session — for an address that already has an
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
  you lose the data** — there is no recovery path, and no key rotation yet.
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
  no matter how many there were. It now selects a real project — the one with
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
0.1.x — back up `omem-data/omem.db` first, and check anything that pinned exact
proposition strings.

`RETRACTED` is untouched, and accented and non-Latin tokens survive intact.

**2. Signup no longer returns a session for a known address** in password mode.
Anything built against the old behaviour breaks, deliberately.

## 0.1.2 — 11 Aug 2026

First published build. Superseded — see the security note above.
