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

One subject. A census of one is not a census, and the honest description of
this directory today is that the instrument exists and has been tested against
the only system its author can assess without doing somebody else's reading
first. The subject files that would make it a census are ordinary work: open
the source, answer twenty questions, cite each answer.

## Files

| file | what it is |
|---|---|
| `rubric.py` | the twenty requirements, as capability questions |
| `subject.py` | the assessment format, and the rules that reject a bad one |
| `run.py` | the report |
| `subjects/*.json` | one assessed system each |

Copyright 2026 Michael Brandon Clifford. MIT licensed.
