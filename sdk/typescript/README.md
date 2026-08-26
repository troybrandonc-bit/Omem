# @omem/sdk

TypeScript client for [OMEM](https://github.com/troybrandonc-bit/Omem), a memory
layer for AI agents that tracks what is believed, when, and why.

Most agent memory is a list of facts. When two conflict, one silently overwrites
the other and the history is gone. OMEM keeps both, tracks which is currently
believed, and can tell you why.

## Install

```bash
npm install @omem/sdk
```

You also need an OMEM server, which is a Python package and runs locally:

```bash
pip install omem-infrastructure && omem-server
```

It prints a project id and API key on first run.

## Use

```ts
import { Memory } from "@omem/sdk";

const mem = new Memory({
  apiKey: "omem_sk_...",
  baseUrl: "http://127.0.0.1:8787",
  project: "proj_...",
});

await mem.remember({
  agent: "support",
  about: "customer:123",
  claim: "prefers_annual_billing",
});

await mem.believes({ about: "customer:123", claim: "prefers_annual_billing" });
// -> "BELIEVED_TRUE"
```

Contradictions are surfaced rather than overwritten. OMEM never decides two
claims disagree by reading them, because that judgement is what would stop the
same question having the same answer a year later. Claims named `X` and `not:X`
are opposed automatically; for anything else you say so once:

```ts
await mem.contradict("prefers_annual", "prefers_monthly");
```

## Agent-bound keys

A key minted with an `agent_id` is bound to that agent. Omit `agent` on your
calls and the bound identity applies; naming a different one is refused by the
server with a 403, on writes as well as reads.

```ts
const bob = new Memory({ apiKey: "omem_sk_<bob-bound-key>", project: "proj_..." });
await bob.recallPack({ context: "acme renewal" });   // scoped to agent:bob
```

## Status

This SDK does not yet cover the whole Python surface. `test_parity.mjs` runs it
against a live server and reports what is missing, which is also the most useful
contribution available if you want to help:

```bash
npm install && npm test
```

MIT. Issues and docs live in the
[main repository](https://github.com/troybrandonc-bit/Omem).
