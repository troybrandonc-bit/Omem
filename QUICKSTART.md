# Quickstart

Two commands to a working memory, and one more if you want to look at it.

## 1. Install and run

```bash
pip install omem-infrastructure
omem-server
```

Python 3.9+. No other dependencies, no database to set up, no account anywhere.

The first run prints a project id and an API key:

```
OMEM starting on 127.0.0.1:8787
  listening on http://127.0.0.1:8787
  auth: local, no login, safe only because this binds 127.0.0.1.

  Your workspace is ready. The key is shown once:

    project   proj_7993648a58e3
    api key   omem_sk_88c19b12338874511…
```

The key is shown once, at creation. Lost it? `POST /v1/keys?project=<id>` makes
another, or delete `./omem-data/omem.db` and start over.

## 2. Give an agent a memory

```python
from omem import Memory

mem = Memory(api_key="omem_sk_…", base_url="http://127.0.0.1:8787",
             project="proj_…")

mem.remember(agent="support-bot", about="customer:alice",
             claim="prefers_annual_billing")

mem.believes(about="customer:alice", claim="prefers_annual_billing")
# -> 'BELIEVED_TRUE'
```

`about` is any entity id you choose: `customer:alice`, `repo:omem`,
`user:42`. `claim` is a token, not a sentence: OMEM normalises spelling, so
`prefers_annual_billing`, `Prefers Annual Billing` and `prefers-annual-billing`
are the same claim about the same customer. Meaning is still yours. It will not
decide that `wants_annual` and `prefers_annual` are the same thing.

## 3. Recall it

```python
mem.recall(about="customer:alice")
# {'count': 2, 'memories': [{'proposition': 'prefers_annual_billing', 'state': 'BELIEVED_TRUE', …}]}
```

Or let OMEM work out which entities matter from what the agent is doing:

```python
mem.recall(agent="support-bot", task="answer a question about billing")
```

## 4. The part a vector store cannot do

Tell it two claims disagree, then contradict yourself:

```python
mem.contradict("prefers_annual_billing", "prefers_monthly_billing")
mem.remember(agent="sales", about="customer:alice", claim="prefers_monthly_billing")

mem.believes(about="customer:alice", claim="prefers_annual_billing")
# -> 'CONTRADICTED'
```

Nothing was overwritten and nothing was lost. Both claims are still on record,
the state is computed from the evidence, and `mem.why(assertion_id)` returns the
chain that led there: which agent said it, when, and on what basis.

Claims named `X` and `not:X` are opposed automatically; anything else you say
once, as above. OMEM never decides two claims disagree by reading them, because
that judgment is what would stop the same question having the same answer a year
from now.

## 5. Look at it

Open **http://127.0.0.1:8787**: the same address the server is already on.

The dashboard ships inside the package and is served by the server itself, so
there is nothing else to install and no second process. It opens on the project
you have been writing to, with no login: memory, conflicts, the belief graph,
the timeline, and the provenance behind any claim.

If it says the dashboard is not bundled, you have a build without it, the API
works exactly the same, and `cd web && OMEM_STATIC=1 npm run build` produces one.

## Use it from Claude Desktop, or any MCP client

Installing the package also gives you `omem-mcp`, which speaks MCP over stdio:

```bash
OMEM_API_KEY=omem_sk_… OMEM_BASE_URL=http://127.0.0.1:8787 OMEM_AGENT=support omem-mcp
```

The client gets `omem_recall`, `omem_observe` and `omem_why` as tools.

## Where the data is

`./omem-data/omem.db`, a single SQLite file, in whatever directory you ran
`omem-server` from. Override with `OMEM_DATA_DIR`. Back it up by copying it.

## Before anyone else can reach it

Local mode has **no passwords**: it is safe because it refuses to bind anything
but loopback. The moment you put OMEM on a network, read the Authentication
section of `README.md`: you want `OMEM_AUTH=password`, a real `OMEM_MASTER_KEY`,
and TLS. The server will refuse the dangerous configurations rather than let you
find out later.
