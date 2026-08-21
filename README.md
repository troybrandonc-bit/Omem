# OMEM

OMEM is a memory layer for AI agents. Instead of dumping text into a vector
store and hoping for the best, it tracks what each agent believes over time and
handles contradictions explicitly, so an agent can reason about what it knows,
when it learned it, and why.

It runs locally with no external services and no dependencies to install.

## What makes it different

Most agent memory is a list of facts. When two facts conflict, one silently
overwrites the other and the history is gone. OMEM keeps both, tracks which one
is currently believed, and can tell you why. A few things it does that a plain
vector store does not:

- **Belief state over time.** Every fact has a state (believed, contradicted,
  unknown) that the engine computes from the evidence, not a static row.
- **Contradiction handling.** Conflicting information is surfaced, not lost.
  Claims named `X` and `not:X` are treated as opposed automatically; for anything
  else, `mem.contradict("prefers_annual", "prefers_monthly")` says so once. OMEM
  never decides two claims disagree by reading them, because that judgment is
  what would stop the same question having the same answer a year later.
- **Provenance.** Ask why something is believed and get the chain that led there.
- **Cross-agent memory.** Memory is private to an agent by default; you choose
  what to share with a team or the whole project.
- **Semantic recall.** Finds relevant memories even when the wording differs
  from how they were stored.
- **A learning loop.** Memories that prove useful rank higher over time.

## Quick start

You need Python 3.9 or newer. No other dependencies.

**Option 1: install from PyPI (server included).**

```bash
pip install omem-infrastructure
omem-server
```

That starts the server on http://127.0.0.1:8787 and, on first run, prints a
project id and an API key, no signup call, no dashboard visit, nothing to
configure. Paste them straight in:

```python
from omem import Memory

mem = Memory(api_key="omem_sk_...", base_url="http://127.0.0.1:8787",
             project="proj_...")
mem.remember(agent="support", about="customer:1", claim="prefers_annual_billing")
print(mem.believes(about="customer:1", claim="prefers_annual_billing"))
# -> BELIEVED_TRUE
```

**[QUICKSTART.md](QUICKSTART.md)** takes that to a contradiction and a provenance
chain in about five minutes, which is where the difference from a vector store
actually shows.

**Option 2: run from this repo.**

```bash
cd server
python api.py
```

Same server, started from source. Setup takes about a minute either way.

## The dashboard

The dashboard ships inside the package. Start the server and open the same
address — **http://127.0.0.1:8787** — and it is there: memory, conflicts, the
belief graph, the timeline, logs and the audit trail. No Node, no second
process, no second port.

In local mode (the default) there is no login; it opens on the project the
server created for you. On a server running `OMEM_AUTH=password` it shows a
sign-in form instead.

It is a static export of `web/`, the only UI in this repository, copied into the
wheel at build time. To work on it:

```bash
cd web
npm install
npm run dev          # http://localhost:3000, proxying to the API on 8787
```

and to rebuild the bundled copy, `OMEM_STATIC=1 npm run build`.

## Authentication

OMEM runs in one of two modes, and the difference matters before you put it
anywhere other than your own machine.

**`OMEM_AUTH=local`** — the default, and what makes the quickstart a minute.
There is no login: the dashboard provisions a session against the server it can
see. That is only safe while nothing else can reach the server, so local mode
**refuses to bind a non-loopback address**. If you mean it (a container whose
ports are published to `127.0.0.1`, a single-user VM), set
`OMEM_ALLOW_INSECURE_BIND=1`.

**`OMEM_AUTH=password`** — required for a server other people can reach.
Accounts have passwords, hashed with PBKDF2-SHA256. Signing up with an address
that already has a password returns 409 rather than a session, TOTP is enforced
where it is enrolled, and the server refuses to start unless `OMEM_MASTER_KEY`
is set to something other than its development default.

```bash
export OMEM_AUTH=password
export OMEM_MASTER_KEY="$(python3 -c 'import secrets;print(secrets.token_urlsafe(32))')"
omem-server
```

### TLS

Point `OMEM_TLS_CERT` and `OMEM_TLS_KEY` at a certificate and the server speaks
HTTPS itself (TLS 1.2 floor). Setting only one is a startup error, not a quiet
fall back to plaintext. A terminating proxy is still better at scale, but
running without one no longer means running in the clear.

### Encrypting memory at rest

```bash
pip install "omem-infrastructure[encryption]"
export OMEM_ENCRYPT_AT_REST=1
export OMEM_MASTER_KEY="$(python3 -c 'import secrets;print(secrets.token_urlsafe(32))')"
```

Encrypts the operations log, ingested source payloads and the quoted evidence
behind each memory with AES-GCM. Existing plaintext rows keep working, so it can
be switched on for a database that already has data. It refuses to start on the
development master key, and refuses to run without a real AEAD library rather
than falling back to the stdlib keystream used for OAuth tokens.

**Lose the key and the data is gone** — there is no recovery path, and no
rotation tooling yet.

## What is in this repo

- `server/` is the OMEM server: an HTTP API wrapping the memory engine. The
  engine itself lives in `server/omem_engine/` and is the source of truth for all
  memory decisions.
- `sdk/python/` is the Python SDK and the `omem-server` / `omem-mcp` commands.
- `sdk/typescript/` is the TypeScript SDK.
- `web/` is the dashboard.

## Use it from an MCP client

Installing the package gives you an `omem-mcp` command that speaks MCP over
stdio, so MCP clients like Claude Desktop can use OMEM as a memory tool:

```bash
OMEM_API_KEY=... OMEM_BASE_URL=http://127.0.0.1:8787 OMEM_AGENT=support omem-mcp
```

## Status and price

Free, and free while it stays in beta, no plans, no card, no quota.

This is early software under active development. It is meant for testing and
feedback right now. `web/app/(marketing)/security/page.tsx` lists what it
protects and, just as importantly, what it does not yet: no SSO, no
certifications, no key rotation, an audit chain that detects tampering rather
than preventing it, and one process holding authoritative state — enforced now,
so a second one refuses to start rather than diverging, but that is the honest
absence of high availability rather than the presence of it. Read that before
you plan around it. If you try it and something breaks or feels wrong, that feedback is
exactly what is useful at this stage.

## License

MIT. See `LICENSE`.

---

Development history and detailed engine notes are in `CHANGELOG-dev-notes.md`,
`ENGINE.md`, and `ENGINE_VALIDATION.md`.
