# A Testimony Record from a LangGraph human-in-the-loop flow

One file, LangGraph as its only dependency, and nothing from OMEM.

```bash
pip install testimony-langgraph
```

```python
rec.approve(graph, config,
            approver={"id": "sam@example.com", "kind": "human"},
            identity_source="auth-session")
rec.write("record.jsonl")
```

```bash
testimony-validate record.jsonl
# Conformance: TR-4
```

The reference validator ships with the package, so a record can be checked by
whoever is holding it without cloning anything. It is one standard-library file
with no network access, and it is the same file this repository uses, copied in
at build time rather than forked.

## What problem this solves

LangGraph pauses a graph with `interrupt()` and resumes it with
`Command(resume=value)`. The resume payload says which interrupt it answers and
carries a value. **It has no field for who answered**, and no principal is
modelled on that boundary, so any code holding the thread can resume it,
including the process that raised the pause.

That is not a defect in LangGraph. It is a graph and checkpointing library and
it never claimed to be an authorisation layer. But the consequence is that an
approval flow built on `interrupt()` produces, by default, a record in which a
run where an engineer read the arguments and decided is indistinguishable from
one where a script resumed everything automatically.

This is measured rather than asserted. A September 2026 assessment of eight
agent memory and agent framework implementations
([10.5281/zenodo.22290922](https://doi.org/10.5281/zenodo.22290922)) examined
the six that take or gate actions. Against the question "does an approval
identify a person or a named role holder", four were assessed absent and one
could not be established either way. LangGraph 1.2.11 was one of the four, with
the evidence pinned to `libs/langgraph/langgraph/types.py`.

## What this adapter does not do

**It does not invent an approver.** The identity does not exist anywhere in
LangGraph for it to find. What it does instead is refuse to write an approval
unless you supply an identity from your own authentication layer, and make the
omission visible rather than silent: resume the graph without going through
`approve()` or `refuse()` and the record still says exactly what happened, it
simply does not reach TR-3.

Three things it refuses outright, each of them a way to produce a plausible
file that lies:

| refusal | why |
|---|---|
| an action absent from your risk table | a default risk class is a guess wearing a policy's clothes |
| `identity_source` the model could have written | `request-body`, `model`, `prompt`, `plan`, `agent`, or empty |
| approver id equal to proposer id | an agent's own credential signing off its own action satisfies every other requirement and is worth nothing |

It also refuses to write a record while an action is still awaiting a verdict,
because that file would describe a gate that never closed.

## Usage

Your node names the action in the interrupt payload. That name is what the risk
table is keyed on, and the table belongs to you rather than to the model:

```python
def gate(state):
    ok = interrupt({"action": "issue_refund",
                    "args": {"ticket": state["ticket"], "amount": state["amount"]}})
    return {"refunded": bool(ok)}
```

```python
from testimony_langgraph import Recorder

rec = Recorder(
    agent={"id": "support-agent", "kind": "agent"},
    risk={"issue_refund": "high", "send_receipt": "low"},
    risk_source="registry",
)

ev = rec.cite("api", "billing://orders/8812", digest="sha256:...")
rec.believe("customer:acme", "eligible_for_refund", evidence=[ev])

rec.invoke(graph, {"ticket": 41}, config)      # runs until the interrupt

rec.approve(graph, config,
            approver={"id": "troy@example.com", "kind": "human"},
            identity_source="auth-session")    # from YOUR auth, not the payload

rec.write("record.jsonl")
```

Refusing is recorded with the same standing as permitting, because a system
that only records what it did is a receipt:

```python
rec.refuse(graph, config, reason="amount exceeds desk limit",
           approver={"id": "troy@example.com", "kind": "human"},
           identity_source="auth-session")
```

`rec.warnings()` says out loud what a record will not demonstrate, before you
find out from a validator.

## What the levels mean here

- **TR-1** the record is well formed and append-only
- **TR-2** beliefs cite their evidence, or say there is none
- **TR-3** actions are gated, and approvals name a person from authentication
- **TR-4** an integrity digest covers the record

The example reaches TR-4. Delete the `approve()` call and resume the graph
directly, the way an application does today, and it stops below TR-3. That
difference is the entire contribution of this file.

## On the integrity entry

The digest covers every entry written before it, so any later alteration of the
file is detectable by anyone holding the value. **It does not prove the file was
not rewritten wholesale by whoever produced it.** That needs an external anchor,
and this scheme does not claim to be one. See the security considerations in the
specification.

## Specification

- Internet-Draft: <https://datatracker.ietf.org/doc/draft-clifford-testimony-record/>
- Reference validator: `scripts/testimony_validate.py`, one stdlib file, no network
- Licence: MIT. The specification text is CC BY 4.0. Implementing it costs
  nothing and requires no permission.

The point of the adapter is that you can read it in one sitting, copy it, and
change it. If it is wrong about what LangGraph carries across the resume
boundary, the fix is a pull request and the assessment above should be corrected
too.
