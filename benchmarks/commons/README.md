# Does the commons pay?

The commons rests on one sentence, and until now nobody had tested it:

> An install with the pooled bank guesses measurably better than one without.

If it holds, contributing is self-interest and the loop turns. If it does not,
contributing is charity, and no amount of distribution fixes that. It is
answerable with zero installs, because the question is about the mechanism
rather than about any real population.

```
python3 benchmarks/commons/run.py            # the grid
python3 benchmarks/commons/run.py --json     # the numbers
python3 server/tests_commons_benchmark.py    # the harness, checked
```

## What it does

A young install has seen six people, which is barely enough to mine a prior
from. Eight other installs have each seen forty, and their priors are pooled
under the real rules: a pair no two separate installs have seen never crosses
back, borrowed rows rank beneath local ones, and a borrowed hunch is born at a
discount. The young install then meets 120 strangers from its own population
and guesses at what they have not said yet. Reality answers, and every prior
keeps its own record, so a prior that lands births bolder hunches next time.

The same install is run twice over the same strangers in the same order, with
and without the bank.

## The two rules that make the number mean something

**Average precision across the two conditions is not a comparison.** The
pooled install answers roughly twice as many questions, and the extra ones are
the harder questions the local install had no prior for. Comparing averages
compares different exam papers. So the report separates the **shared** claims,
where both had an opinion, from the **marginal** claims only the bank could
reach.

**Precision is not a finding either.** Guessing that someone prefers email,
where four in five people do, tells nobody anything. The column to read is
**lift**: precision minus the base rate of the very claims being guessed at.

## What it found

```
 hold   reg  spread   base   own    cover l/p  marg n  marg lift
 0.20  0.20    0.00   0.35   0.0         0/51      51      0.405
 0.20  0.20    0.50   0.35   0.0         0/51      51      0.159
 0.20  0.20    1.00   0.35   0.0         0/48      48      0.015
 0.30  0.25    0.00   0.45   0.0         0/73      73      0.323
 0.30  0.25    0.50   0.43   0.0         0/82      82      0.106
 0.30  0.25    1.00   0.41   0.0         0/69      69      0.012
 0.45  0.40    0.00   0.63   0.0         0/36      36      0.264
 0.45  0.40    0.50   0.61   0.0         0/49      49      0.021
 0.45  0.40    1.00   0.58   0.0         0/16      16      0.033
```

**The claim holds, and more strongly than before.** A six-person installation
now mines nothing at all on its own, because a Wilson bound will not call six
people a law, so every opinion it forms comes from the bank. Those borrowed
guesses beat the base rate of the claims they are about by between 26 and 40
points, at every density tested.

**And it stops paying where it should.** Hold the world fixed and make the
contributing populations unrelated, and the lift falls to zero and then below.
That negative control is asserted in the suite rather than described, and it is
the reason the positive numbers are worth reading.

## A finding this file previously reported, and which was wrong

An earlier version of this README said the failure mode was **saturation**:
that when almost everyone already holds a claim there is nothing for a prior to
add, and the bank went negative in a dense world even when the populations
agreed. The number was real, the explanation was not.

It was the missing lift test. `learn_priors` kept a pair when most holders of P
also held Q, which a popular Q satisfies on its own, so a dense world filled
the bank with popularity and the pooled rows predicted nothing. The external
study on 19,719 real respondents found the same defect against a known ground
truth, `PRIOR_MIN_LIFT` was added, and the saturated row went from -0.116 to
+0.107 without anything else changing.

The lesson is worth more than the retracted claim. A harness that measures the
mechanism honestly will attribute its results to the wrong cause if the
mechanism has a defect the harness cannot see. It took a dataset with a known
answer to tell the two apart.

## What this does not answer

It mirrors the prior mechanism. It does not run the belief engine, the
similarity layer or the interrogation pass, so it says nothing about the rest
of the system. It says nothing about whether real working populations are
sparse or saturated, or how much of their structure they share, which is an
empirical question the first ten contributing installs will answer and this
cannot.

Every constant is imported from `server/hypotheses.py` and
`server/commons.py`, never copied, and the suite asserts they still match.

## Honest note on how this was built

The first version of this harness produced a confident negative number that
was meaningless, for two reasons now written into the top of `simulate.py`: it
compared average precision across two different question sets, and it kept one
verdict record per install where the engine keeps one per prior. The second
bug flattened every hunch to the same strength and guaranteed the calibration
score would say nothing.

The density parameters were then made explicit rather than fixed, because the
first run happened to sit in the saturated corner where nothing can help. The
direction of the result changed when they did, so the whole grid is printed
and the saturated row is kept in it.
