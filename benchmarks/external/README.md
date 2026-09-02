# The prior rule, tried on real people

The commons benchmark generates its own world, so it can only test the
mechanism against the assumptions used to build it. This one runs the same
mining rule over answers 19,719 people actually gave, whose correlation
structure nobody here chose.

```
python3 benchmarks/external/run.py            # the study
python3 server/tests_external_big5.py         # the harness, checked
```

## The data

Open Psychometrics' Big Five item responses, collected around 2012 through an
online personality test, with consent recorded at the time and published for
research. Fifty items rated 1 to 5, 19,668 respondents usable after dropping
those who answered fewer than twenty items.

It is downloaded when the benchmark runs and is **not committed here**. This
repository does not redistribute other people's survey responses.

## Why this dataset

Two reasons, and the second is the one that matters.

The mapping to the engine's semantics is almost exact. An answer of 4 or 5 is
holding a proposition, 1 or 2 is holding its negation, and **3, the neutral
answer, is a genuine silence**. A prior fires only into a silence, so the
experiment gets its held-out question for free: hide an answer somebody
actually gave and ask whether the bank can put it back.

And the dataset has a **known latent structure**. Fifty items, five factors,
ten items each. A pair drawn at random has a 9-in-49 chance of joining two
items of the same factor, which is 0.184. So there is a ground truth for
whether the miner finds real psychology or noise, which no synthetic world can
provide, because there the structure is whatever was put in.

## What it found

**The mining rule measures popularity, not association.**

```
within-factor rate of mined priors      0.185
chance                                  0.184
```

Exactly chance. The miner recovers none of the known structure. The reason is
visible in one number: the consequents of mined priors have a mean base rate
of **0.76** against an overall item mean of **0.57**. `PRIOR_MIN_RATE` asks
whether 60% of the people holding P also hold Q. If 76% of *everyone* holds Q,
that condition is met by Q being popular, and says nothing about P.

**Requiring lift recovers the structure, monotonically.** Keep only priors
whose rate among antecedent-holders beats the consequent's own base rate:

```
margin   priors kept   within-factor
+0.00        964          0.213
+0.05        522          0.310
+0.10        252          0.472
+0.15        160          0.619
```

At +0.15 the miner finds same-factor pairs at 3.4 times chance. It recovers
the Big Five without being told the Big Five exists.

**The prediction results, for completeness**, on 400 held-out answers per
trial. Lift is precision minus the base rate of the very items guessed at:

```
              coverage   precision     lift
local            207       0.737      +0.003
pooled           325       0.676      +0.015
marginal         118       0.578      +0.039
```

Borrowed priors beat the base rate, and barely. That is what a rule selecting
for popularity would produce: it guesses the popular answer, is often right,
and has told you almost nothing.

## What follows

`learn_priors` keeps a pair when the rate among antecedent-holders clears
`PRIOR_MIN_RATE`. On this evidence that is the wrong test, and the right one
compares the rate to the consequent's own base rate. The change is small and
its consequences are not: it alters what every installation learns and what
the commons is filled with.

That is worth doing before installations arrive rather than after. A bank
filled under the current rule would be full of popularity, and no amount of
pooling improves a corpus whose entries were never associations.

## What this does not show

It says nothing about whether personality items resemble the working
behaviours the commons vocabulary describes. It tests the *rule*, on a
population with real structure, and the rule is what was found wanting.
