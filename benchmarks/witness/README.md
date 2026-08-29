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
