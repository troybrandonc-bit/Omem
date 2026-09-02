# Design: what the commons should count

Written 2 Sep 2026, before any code, because the consent model is the one
thing in this system that cannot be retrofitted.

## The problem with the commons as it stands

`hypotheses.bank()` contributes association rules: `antecedent -> consequent`
with support, refute and subject counts. Both tokens must be composed from
`COMMONS_LEXICON`, which is **383 words**, because a free-form token can be
engineered to carry an identity (`johnsmith_of_acmecorp` passes every
structural check).

That vocabulary is what makes the corpus defensible. It is also what caps it.
The number of distinct rows is bounded by the vocabulary, not by adoption: a
thousand more installs do not create new rows past a point, they sharpen the
counts on rows that already exist. The artifact asymptotes at thousands of
pairs and megabytes of data, and it is competing for a model builder's
attention with training sets of trillions of tokens of real human text.

So "grow the corpus by getting installs" is not, on its own, a plan. The
corpus does not grow that way.

## The thing that does not have this ceiling

Every generalisation of the form "counts over a closed vocabulary" is bounded,
whatever is being counted. Counting revisions instead of co-occurrences does
not escape it: the cell space of
`(family, generator, strength, passes, outcome)` is finite too.

What is not bounded is a **model**, and OMEM is already producing the training
signal for one that almost nobody else can produce.

`leap()` forms a hypothesis about a person from thin evidence and records how
bold it was (`strength`), which strategy produced it (`generator`), what family
of claim it was (`prefers_*`, `wants_*`, `uses_*`), how many interrogation
passes it survived (`passes`), whether it had to ask a human, and then reality
labels it `supported` or `refuted`. `_birth_strength` already feeds that back
so boldness follows the record.

That is a labelled dataset of *inferences about people and whether they were
right*, generated as a by-product of ordinary use. Model builders have
effectively unlimited text about what people said. They have very little
structured, outcome-labelled data about **when an inference about a person
should be trusted**, because producing it requires a system that commits to a
guess, records the commitment, and is later corrected by evidence.

The asset is therefore not a table of regularities. It is calibration: knowing
how much confidence a thin-evidence claim about a person deserves, learned
across many populations. That is a capability, and capabilities do not
asymptote at lexicon size.

## What to contribute, and why each part is safe

Three record kinds, all counts, all subject to the existing `PRIOR_FLOOR_N`
floor and the same refusal at both doors.

### 1. `prior` (exists today, unchanged)

`{antecedent, consequent, support, refute, subjects}`. Keep it.

### 2. `calibration` (new — and the obvious version of it leaks)

The first draft of this section said contributing `leap_generators` was
"strictly safer than what already flows, because a generator name is a code
identifier chosen by OMEM". **That is false, and checking it is the reason this
document exists.**

`hypotheses.py:468` sets `generator = nb`, where `nb` is the neighbour the
projection came from: **a subject id**. A second generator form is
`"prior:" + pr["id"]`. So `leap_generators.generator` holds real entity
identifiers from the install, and shipping that table would have sent a list of
the people each contributor knows about, keyed by id, into a bank whose entire
promise is that it holds a fact about no one. It would have passed the
`_identifying` check at both doors, because those doors inspect proposition
tokens, not this column.

What is contributable is the **generator class**, not its name:

- `neighbour` — the hunch came from a look-alike subject
- `prior` — the hunch came from a population regularity

That is a closed two-value enum, derived by testing the `prior:` prefix, and it
carries the calibration question intact: *do look-alike projections beat
prior-driven ones, and where?*

So the contributable rows are:

- `{scope: "generator_class", name: "neighbour"|"prior", supported, refuted}`
  with `name` validated against the closed enum at both doors.
- `{scope: "family", name: <family>, supported, refuted}` where `family` is the
  first token of a proposition and is therefore **not** guaranteed to be
  lexicon-bound — a caller can assert any proposition it likes. It gets the
  same `lexicon_ok` and `_identifying` refusal as an antecedent, at both doors.

Both are floored by `PRIOR_FLOOR_N` on `supported + refuted`, so a family seen
on two hypotheses does not travel.

The general lesson, worth keeping: **the anonymity argument has to be made per
column, against the code that writes it.** "It is an internal identifier" is
not an argument, it is an assumption, and this one was wrong.

**The two columns added after this was written, under the same rule.**
`leap_generators` now also carries `w_wins` and `w_losses`: the same verdicts
weighted by prediction error, which is what drives how bold the next hunch is
born. They do not travel, and the reason is not privacy — a weight is a real
number over two integers already contributed, so it leaks nothing the counts
do not. It is that a weight is a fact about *this install's learning*, not a
fact about people, and the bank answers only the second kind of question.
Pooling weights would also silently double-count: a verdict already
contributed as a count would arrive a second time carrying a different unit.
`tests_surprise_weighting.py` asserts every number the bank emits is an `int`,
so a future contributor cannot widen the door by accident.

### 3. `revision` (new, the actual prize)

A histogram, never a trace. One row is:

```
{family, generator, strength_bucket, passes, asked_human, outcome} -> count
```

**A trace is a fingerprint; a histogram cell is not.** A sequence of
corrections with timestamps re-identifies easily, which is why nothing here
emits one. What leaves the machine is how many hypotheses of a given shape
ended a given way — the same kind of object as a prior, counted over a richer
event.

Safety follows the existing argument rather than needing a new one:
`family` is lexicon-bound, `generator` is ours, `strength_bucket` is one of a
fixed set, `passes` and `count` are integers, `outcome` is an enum. No subject,
no proposition, no timestamp, no sentence. The floor applies per cell.

## What this changes about the success metric

Not corpus size. The claim to make falsifiable, in the style of `CLAIMS.md`, is:

> Priors and calibration learned from the pooled bank make OMEM's hypotheses
> measurably better calibrated than the same engine with an empty bank.

That is testable on the benchmark harness that already exists: run the Witness
suite with and without a pooled bank, and compare hypothesis precision and the
Brier score of birth strength against outcome. If the pooled signal does not
beat the empty baseline, the commons is a nice idea that does not pay, and
better to learn that on a small bank than a large one.

## Order of work

1. Contribute `calibration`. Small, safe, no new privacy argument needed.
2. The benchmark above, with an honest number, before building more.
3. `revision` histograms, only if step 2 shows pooled signal helps.
4. The contribution ledger itself as an append-only record (see below).

## The part that decides an acquisition, whenever one comes

A corpus is worth nothing in diligence that cannot prove its provenance. "No
personal data is in it" is a weaker claim than "every count came from an
install that opted in, on a date, under a stated version of the terms, and a
withdrawal removes it."

OMEM already contains the machinery for that claim and does not yet point it at
itself. The commons contribution ledger should be an append-only, hash-chained,
replayable record — a Testimony Record for the corpus. Build it while the bank
is small, because consent cannot be reconstructed after the fact.
