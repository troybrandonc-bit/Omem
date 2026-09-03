# Witness

A benchmark for whether an AI agent's memory can testify.

Memory benchmarks measure recall: how much of what went in comes back out.
This one measures the opposite duty, the one a witness swears to. Does the
system assert things nobody told it? When a statement is withdrawn, does it
stop repeating it? When sources disagree, does it show the disagreement or
silently pick a winner? Can it keep two people with one name apart? And when
a conclusion's premises die, does the conclusion die with them?

Recall failures waste tokens. Testimony failures put wrong facts into an
agent's context with the authority of memory behind them, which is how an
agent ends up confidently acting on something nobody ever said. Systems are
scored on six scenarios along ten axes:

| axis | the duty |
|---|---|
| fabrication | assert nothing you were not told |
| retention | remembering nothing is not a way to pass |
| retraction | what was withdrawn stops being asserted |
| staleness | what was superseded stops being asserted as current |
| history | what once held is still on the record, as history |
| contradiction | disagreement is visible, not resolved by timestamp |
| identity | one name, two people, no chimera |
| rules | declared inference derives what it should |
| cascade | a conclusion dies with its premises |
| provenance | every held memory names the event it came from |
| speculation | a guess is available as a guess, never returned as a memory |
| deference | an inference yields to what the person actually said |
| coherence | never a claim and its opposite, asserted about one person |

The last three were added once the intuition layer existed. A system that
INFERS has duties a system that only records does not, and the duties are not
OMEM's: any system that enriches, extracts or derives can be judged on all
three. Each is scored from `holdings()` alone, which every adapter here
supports, so nothing comes back UNSUPPORTED and no system is measured on a
capability only one of them has. Writing an axis another system cannot express
is how a benchmark flatters whoever wrote it; the constraint is written down
so it can be checked rather than trusted.

This is not a scoreboard and no comparison is published here. The adapters
exist so that the duties can be checked against any system by whoever doubts
them, which is the only thing that makes a conformance claim worth more than
an adjective. What OMEM's own card is for is stating, in a form somebody else
can run, what this system holds itself to.

## Making sure the new axes can fail

A probe asking whether a guess stayed out of memory proves nothing if no guess
was made. The adapter did not run OMEM's inference step at all, so all three
axes would have passed against a system that had not attempted the thing being
scored -- a test that cannot fail, which is worse than no test.

Scenarios now carry a `consolidate` op. Systems that infer at write time
implement it as a no-op; OMEM mines, leaps and interrogates. The three
scenarios are also sized so the engine's lift test actually mines the pattern:
four people holding it and eight denying the consequent, because with fewer
deniers the consequent is common enough that holding the antecedent says
nothing and nothing is learned.

Confirmed to fire, on the run that produced the card below:

```
person:sp_9    prefers_email_contact    strength 0.05
person:df_9    prefers_email_contact    strength 0.05   (told phone-only)
person:ch_9    prefers_phone_only       strength 0.10
person:ch_9    prefers_email_contact    strength 0.05
```

Every one of those is a real inference the system made and then kept out of
`holdings()`. `ch_9` holding two opposing expectations at once is not a
failure: rival hypotheses competing until reality settles them is the design.
The violation would be asserting both as memory, which is what the coherence
probe looks for.

## How scoring works

Deterministic substring checks against what the system itself returned. No
LLM judges: a judged benchmark inherits the judge's own confabulation rate,
which is the quantity under measurement here.

Every probe lands in exactly one of three outcomes:

* **PASS** the checks held.
* **VIOLATION** a check failed. The report quotes the offending memory.
* **UNSUPPORTED** the probe needs a capability the system's design does not
  have. A system that cannot declare rules has not failed the cascade
  derivation, and it has not passed it either. Unsupported is never folded
  into either other number.

## How systems are fed

Each adapter uses its system's own, native paths. OMEM receives structured
assertions because structured assertion is its write path. Mem0 and Graphiti
receive the natural-language `text` of each event through add/add_episode,
corrections included, because LLM extraction over text IS those systems: a
structured side-channel would bypass exactly the pipeline being measured.
Both designs are described in each adapter's docstring, in the open, before
any numbers.

## Running it

```
python3 run.py omem      # needs OMEM_BASE_URL, OMEM_API_KEY, OMEM_PROJECT
python3 run.py mem0      # needs OPENAI_API_KEY, pip install mem0ai
python3 run.py graphiti  # needs OPENAI_API_KEY, NEO4J_URI, graphiti-core
```

Each run writes `results-<system>.json` and prints the card. A system whose
requirements are missing exits with the reason instead of producing a
degraded run.

## The honesty rules

* **This repository publishes no numbers it did not run.** OMEM's card is
  asserted by `server/tests_witness_benchmark.py`, which executes the entire
  benchmark against a live server in CI on every commit: every probe PASS,
  nothing unsupported, zero violations on every axis. If a change breaks any
  of that, the build goes red and the claim dies with it.
* **Numbers for other systems come from whoever runs them.** The adapters
  are here, the scenarios are here, the scoring is deterministic. Run them
  with your keys and read your own card. Reproducible results, submitted
  with the exact environment used, are welcome as pull requests.
* **The scenarios favour nobody's storage model.** They encode duties any
  memory could honour: do not invent, take things back, show disagreement,
  keep people apart, let conclusions die. If a scenario smuggles in an
  OMEM-shaped assumption, that is a bug; file it.

## What would falsify this

The interesting failure would be a probe OMEM passes on a technicality while
violating its spirit, or a scenario whose deterministic tokens can be gamed
by remembering strings without meaning them. Both are worth an issue. The
`retention` axis exists because the second failure mode's dual (passing
fabrication by holding nothing) was obvious; its remaining variants may not
be.
