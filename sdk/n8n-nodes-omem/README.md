# n8n-nodes-omem

OMEM for n8n: belief-revision memory for AI agents inside your workflows.
Keeps both sides of a contradiction instead of overwriting, tracks what was
believed and when, answers "why" with a provenance chain, and gives your
workflow a branchable belief state instead of trusting the latest write.

OMEM is open source (MIT) and self-hosted: your data stays on your own
machine. https://infrastructure.omem-cloud.com

## Install

In n8n: Settings, Community Nodes, Install, enter `n8n-nodes-omem`.

Run the server (one command, no dependencies):

```
pip install omem-infrastructure
omem-server
```

The first run prints your API key and project id; put them in the node's
OMEM API credentials along with the base URL (default http://127.0.0.1:8787).

## Operations

- **Remember**: record a claim as a belief with provenance
- **Believes**: the four-valued state of a claim right now
  (BELIEVED_TRUE, BELIEVED_FALSE, CONTRADICTED, UNKNOWN); route an IF node
  on it instead of trusting the newest value
- **Recall**: retrieve relevant memory, optionally as of a past moment
- **Why**: the evidence chain behind one assertion, exportable
- **Observe / Learn**: feed raw text; the engine decides what becomes memory
- **Conflicts**: every open contradiction, both sides included

## Why OMEM instead of a plain store

When two facts conflict, most memory silently overwrites one and the history
is gone. OMEM keeps both, marks which is believed, and can prove why, which
is what "why did the agent do that" requires in a client security review.

MIT licensed. Issues and source: https://github.com/troybrandonc-bit/Omem
