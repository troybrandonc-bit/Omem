# OMEM: trustworthy memory for AI agents

OMEM is a memory layer for AI agents that tracks beliefs over time and handles
contradictions instead of silently overwriting them. This is the official Python
SDK. It has no third-party dependencies, so it installs instantly and won't
clash with anything else in your environment.

## Install

```bash
pip install omem-infrastructure
```

The import is short:

```python
from omem import Memory
```

## Run a server in one command

Installing also gives you an `omem-server` command that starts the full OMEM
server (engine and API) locally, with no extra setup:

```bash
omem-server
```

It runs on http://127.0.0.1:8787 and stores its data in an `omem-data` folder in
your current directory. Use a different port with `omem-server 9000`.

## Quickstart

```python
from omem import Memory

mem = Memory(api_key="omem_sk_...", project="proj_...")

# Remember a grounded fact. The agent and entity are created on first use.
mem.remember(agent="support-agent", about="customer:123",
             claim="prefers_annual_billing")

# Ask what's believed.
print(mem.believes(about="customer:123", claim="prefers_annual_billing"))
# -> BELIEVED_TRUE

# Contradictions. Simple negation needs no setup: `X` and `not:X` are paired
# for you, so this alone is enough to get a conflict rather than an overwrite.
mem.remember(agent="billing-agent", about="customer:123", claim="not:prefers_annual_billing")
print(mem.believes(about="customer:123", claim="prefers_annual_billing"))
# -> CONTRADICTED
mem.conflicts()   # both sides, their evidence, and a recommendation

# For claims that oppose each other without being a negation, say so once.
# OMEM never guesses this from wording: deciding that two sentences disagree is
# the judgment call that would stop a belief state being reproducible.
mem.contradict("prefers_annual_billing", "prefers_monthly_billing")

# Recall everything known about an entity, with provenance.
for m in mem.recall(about="customer:123")["memories"]:
    print(m["proposition"], m["state"])

# See why something is believed, with the full provenance chain.
mem.why("a_...")
```

## Cross-agent memory

Memory is private to an agent by default, and you decide what to share.

```python
# Private to one agent. Only agent-a can recall it.
mem.remember(agent="agent-a", about="acme", claim="secret_deal=1",
             scope="agent:agent-a")

# Shared across the whole project. Every agent can recall it.
mem.remember(agent="agent-a", about="acme", claim="tier=enterprise", scope="org")

# Shared with a named team.
mem.remember(agent="agent-a", about="acme", claim="ae=jane", scope="team:sales")

# Promote an existing memory to a wider scope later.
mem.share(assertion_id="a_...", scope="org")
```

## Use it as an MCP server

Installing also gives you an `omem-mcp` command that speaks MCP over stdio and
exposes three safe tools: `omem_recall`, `omem_observe`, and `omem_why`.

```bash
OMEM_API_KEY=omem_sk_... OMEM_BASE_URL=https://... OMEM_AGENT=support-agent omem-mcp
```

Point your MCP client (such as Claude Desktop) at that command. The agent
identity is fixed at the process level, so a model can't reach into another
agent's private memory.

## Self-healing

```python
# Report a failure and let OMEM's policy-gated recovery loop handle it.
mem.healing.report(component="db-pool", error_type="ECONNRESET")
mem.healing.handle(error={"component": "db-pool", "error_type": "ECONNRESET"})
mem.healing.health()   # aggregated component health
```

## How it fits together

Every method maps onto one operation or query in the OMEM engine. The SDK adds
authentication, retries on 5xx errors, typed errors (`OmemError.reason_code`
exposes codes like `R_DANGLING`), automatic registration of agents and entities,
and cross-agent scope control. It doesn't invent any new memory behavior of its
own; the engine remains the single source of truth.
