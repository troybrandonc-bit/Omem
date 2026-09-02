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
 0.20  0.20    0.00   0.36   0.2        3/114     111      0.124
 0.20  0.20    0.50   0.36   0.1        2/172     169      0.033
 0.20  0.20    1.00   0.36   0.3        6/217     211     -0.021
 0.30  0.25    0.00   0.45   1.6       39/210     170      0.007
 0.30  0.25    0.50   0.45   1.6       40/285     245     -0.045
 0.30  0.25    1.00   0.43   1.9       45/328     282     -0.065
 0.45  0.40    0.00   0.63   5.6      168/331     163     -0.116
 0.45  0.40    0.50   0.62   5.7      165/363     198     -0.103
 0.45  0.40    1.00   0.61   5.5      162/375     214     -0.125
```

**The claim holds, under conditions worth stating.**

In a sparse world where the contributing populations share their regularities,
the bank gave a six-person install 111 claims it could not otherwise have had
an opinion about, and those guesses beat the base rate of those same claims by
**12 points**. On its own that install could mine almost nothing: 0.2 priors
on average, which is to say usually none at all.

**And it stops paying exactly where it should.** Hold the world fixed and make
the contributing populations unrelated, and the lift falls to zero and then
below. That is the negative control, it is asserted in the suite, and it is
the reason the first number is worth reading. A harness where borrowed
knowledge helps whether or not the populations have anything in common is
measuring wishful thinking.

**The failure mode is saturation, not disagreement.** When almost everyone
already holds the claim, the base rate is high and there is nothing left for a
prior to add: the bank goes negative even when every population agrees. So the
commons pays in domains where the behaviour is *not* near-universal, and the
denser the behaviour, the less there is to learn.

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
