# The conformance census

What each assessed system can already account for, and what it would have to
start keeping to account for more.

```
python3 benchmarks/census/run.py            # the report
python3 benchmarks/census/run.py --check    # validate the assessments only
python3 benchmarks/census/run.py --json     # machine-readable
```

## The question it asks

`scripts/testimony_validate.py` answers "does this record conform?". It cannot
answer "could this system produce such a record?", because a system that has
never heard of the specification emits nothing for it to read. Pointed at any
third-party agent framework it returns "none" for all of them, which is not a
finding about those systems. It is an artefact of asking the wrong question.

So this asks the other one. For each requirement behind a conformance level, it
states the capability in terms any system can be assessed against by reading
its source and its documentation:

> not "does it write `type: belief` with an `evidence` array"
> but "can the source a stored fact came from be recovered from the store"

A system that has the information but writes it in its own format is a
translation away from conformance. A system that does not have the information
cannot translate its way there at any price. That difference is the only thing
being measured.

Twenty requirements, spread across the levels as 5, 5, 7 and 3, and across the
capabilities as twelve for storing, seven for acting and one for deriving.

That last number looks thin and is deliberate. The specification imposes exactly
one duty specific to derivation, which is that a fact the system inferred can be
told apart from one it was told. A system that infers has other duties, but they
are not in this specification, and inventing requirements to make a column look
fuller would break the one property that makes this rubric checkable: every
question traces to a published conformance level. Those other duties are
measured separately, by `benchmarks/witness`.

## What it does not produce

There is no total, no percentage, and no ordering of systems. Not as a matter
of taste: the code cannot emit one. The systems assessed here are not trying to
do the same job, and a number that pretended otherwise would be read as a
league table within a week of publication, after which nothing else on the page
would matter.

What comes out instead is a gap map. For each system: the highest level its
existing capabilities already satisfy, and for the level above, exactly which
facts it does not currently keep and where that was checked. That is useful to
the people who build these systems, which a ranking is not.

## The rules that keep it honest

A census of other people's software can do real damage, and the people in it
did not ask to be. Care is not a defence, because care is not auditable. So the
rules are in `subject.py`, they are enforced on every file, and `--check` runs
in CI:

- **Every verdict cites evidence, including `absent`.** An `absent` verdict must
  carry at least one `searched` item saying where the assessor looked and did
  not find it. Saying a system lacks something without saying where you looked
  is an accusation wearing a measurement's clothes, and it is the failure this
  census is most likely to commit.
- **No requirement can be quietly dropped.** Every requirement applicable to a
  capability the subject claims must be answered. A silent omission is how an
  unflattering row disappears.
- **Scope cannot be an escape hatch, in either direction.** A subject declares
  what it is in the business of doing. It cannot mark a requirement
  `not_applicable` inside a business it claims, and it cannot be scored on one
  it never claimed. A vector store is not failing at approval gates; it is not
  an approval gate.
- **A version must be pinned.** "System X does not do Y" is false within a month
  of being written unless it says which X.
- **`partial` does not clear a level.** A requirement half met will not hold the
  first time somebody leans on it.
- **Not knowing is its own verdict, and not a free pass.** A system can keep the
  record in a component the assessor cannot read: a hosted server, a closed
  dependency. `undetermined` says so, needs the same `searched` evidence as
  `absent`, and blocks a level exactly as `absent` does, because a level
  awarded on unchecked facts looks identical to one that was verified.

`server/tests_census.py` proves each of these rejects what it claims to reject,
because a stated rule and an enforced one are different things.

## The conflict of interest

OMEM is the reference implementation of the specification these questions
derive from, written by the person who wrote them. It scores well here the way
a dictionary's author spells well, and its row should be read as carrying no
evidential weight at all. It is included so that the questions are applied to
the system that produced them before they are applied to anyone else's, and so
that a reader who doubts a question can open the source behind every answer to
it.

Building the instrument against OMEM first was not a formality. It found three
things:

1. **A defect in OMEM.** `scripts/export_testimony.py` emitted no evidence
   entries at all, hardcoding `"evidence": []` on every belief while `/why` was
   returning the source record, the provenance graph and the quoted text. The
   export passed TR-2 only because an empty array satisfies the validator
   vacuously. Fixed, with a regression test that drives a real connector, since
   the existing suite proved conformance on a fixture that had no evidence in
   it and so never ran the citation path.
2. **A defect in the rubric.** The first draft scored a lawful response to a
   GDPR erasure request as a TR-1 failure, which would have marked down every
   system deployed in the EU for obeying the law. Split into R1.3, about the
   ordinary write path, and R1.5, about whether the destruction is itself
   recorded.
3. **A second defect in the rubric.** The first draft scored a system that never
   resolves contradictions as failing TR-2, when the specification records
   resolution only "if any" and never resolving is the more conservative
   design. Reworded.

Two of the three findings were against the author. That is the intended ratio
for a first run, and it is why this file says so rather than leaving it out.

A fourth correction came later, from assessing somebody else. Letta Code keeps
its approval record in a server that is not in the repository the harness lives
in, and the rubric had no way to say so: the choice was between calling a
capability absent without looking at it and calling it present without looking
at it. `undetermined` was added for that, and the first thing it did was stop
this census from publishing a guess about the one system whose answer might
have been yes.

## Being assessed, and correcting an assessment

Nothing here is self-reported and nothing is taken on trust, in either
direction. An assessment is a file in `subjects/` with a citation on every line,
which means every claim in it can be checked by whoever disagrees.

If your system is assessed here and a verdict is wrong, the fix is a pull
request against its subject file, or an email to `hello@omem-cloud.com` naming
the requirement and where to look. A correction that lands changes the file, the
report and the assessment date. There is no fee, no membership, and no
requirement to use OMEM or anything else.

If your system is not here and you would like it to be, the same applies. Being
absent from this file is not a judgement; it means nobody has done the reading
yet.

## Status

Eight subjects, assessed on 4 September 2026: OMEM, mem0, Graphiti, LangGraph,
CrewAI, the OpenAI Agents SDK, AutoGen and Letta Code. Each was read from a
clone of its public repository at a pinned commit, and every verdict cites a
file and line in that commit or a search that can be repeated against it.

Three patterns hold across every system except the reference implementation,
and they are the findings worth taking away:

**Nobody records who approved.** Four of the eight gate actions and not one
records a person. The OpenAI Agents SDK's `approve()` takes no approver
argument, and the only thing called an identity in its approval path names the
tool call. CrewAI's `request_human_input` reads a line from the console.
AutoGen's `ApprovalResponse` requires a reason and has no field for who gave
it. LangGraph resumes an interrupt with an arbitrary value from whoever holds
the thread. Letta Code is the one possible exception and could not be settled:
it has a server-validated acting-user identity built for exactly this, and
whether that identity reaches the approval record is not visible from the
harness. In every case the pause is real. In seven of eight the attribution is
absent, which matters to anyone who has to evidence human oversight rather than
perform it.

**Nobody records that data was destroyed.** R1.5 is absent in five and partial
in two. Every one of these systems has a delete path somebody will reach for on
a subject-erasure request, and afterwards the store is mostly indistinguishable
from one where the data never existed. The two partials fail in opposite
directions and both are instructive: mem0 writes a history row and keeps the
deleted text inside it, and Letta Code records the deletion as a git commit
while the content stays in history and on every mirror it was pushed to.

**Almost nobody can show a record did not change.** TR-4 is absent outright for
six of the eight. Where history survives, it survives because the code path
behaved, which is weaker than being able to show nobody went around it.

Setting aside OMEM, whose result is a tautology for the reasons given above:

- **Letta Code** has the most interesting store in the census. Memory is a git
  repository, so append-only, revision history and content addressing come free,
  and it is the only assessed system with any answer at TR-4 at all. It stops
  one step short deliberately: `memory-git-signing.ts` disables commit signing,
  for the sound reason that the harness-managed committer identities have no
  key, so a rewritten history carries no attestation. Its post-commit push
  mirror is already most of an external anchor.
- **Graphiti** and **LangGraph** each meet four of five at TR-1 and fail only
  R1.5, so both are one change from a level neither was aiming at. Graphiti got
  there by being bi-temporal, stamping a contradicted fact invalid rather than
  deleting it. LangGraph got there because time travel needs it: every
  checkpoint is a new row carrying its parent's id.
- **mem0** and **CrewAI** both consolidate through an LLM that decides
  keep/update/delete over existing memories. mem0 keeps the previous value in a
  history database; CrewAI keeps nothing.
- **AutoGen** models the approval request best of anyone here, carrying the code
  and the full context, and requires a reason on the response. It then returns a
  refusal as `exit_code=1`, the same shape an execution error takes, and its
  memory items carry no timestamp at all.
- **The OpenAI Agents SDK** keeps a careful ledger of which calls executed and
  leaves durability to the application embedding it.

None of this is an accusation of failure. Seven of the eight are not trying to
produce a testimony record and have never said they were. What the census
establishes is narrower and more useful: which facts each one already keeps, so
anybody who needs those facts knows what they are starting from, and which
single change would move each system furthest. For three of them that change is
small, and for two it is the same one.

## Files

| file | what it is |
|---|---|
| `rubric.py` | the twenty requirements, as capability questions |
| `subject.py` | the assessment format, and the rules that reject a bad one |
| `run.py` | the report |
| `subjects/*.json` | one assessed system each |

Copyright 2026 Michael Brandon Clifford. MIT licensed.
