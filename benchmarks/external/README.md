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

**Requiring lift recovers the structure**, and requiring it of the rate's
*lower bound* rather than the rate itself recovers far more of it. A raw rate
treats three of three as certainty; a Wilson bound does not, so a pair resting
on a handful of people must be much cleaner than one resting on hundreds to
earn the same standing.

```
                    priors  within-f  consequent BR  marginal n  marg lift
no lift test          1269     0.199           0.76         120     +0.040
shipped                 72     0.875           0.48         152     +0.128
```

Chance is 0.184. The shipped rule recovers same-factor pairs at **4.8 times
chance**, triples the lift, and does it while forming opinions about MORE
claims than the unfiltered rule, not fewer. Ninety-four per cent of the priors
are gone and the coverage went up, which is what it looks like when the
discarded ones were firing constantly and saying nothing.

The bound was chosen at a margin of 0.10 rather than the 0.15 that scored best
in the sweep, for the same reason as before: the sweep was run on the data it
was evaluated against, and 0.10 already beats the incumbent on every axis
including coverage.

## What followed

The change shipped. `learn_priors` now requires the Wilson lower bound of a
pair's rate to clear the consequent's own base rate by `PRIOR_MIN_LIFT`, on
top of the support floor and the reliability rate that were already there.
Both were kept: the bound says whether a pair is informative, the rate says
whether it is reliable enough to act on, and dropping the rate test scored
worse on every measure here.

It altered what every installation learns and what the commons is filled with,
which is why it was worth doing before installations arrived rather than
after. A bank filled under the old rule would have held popularity, and
pooling does not improve a corpus whose entries were never associations.

It also corrected a finding published the same day. The commons benchmark had
reported that the pooled bank fails in a saturated world, where almost
everyone already holds the claim. The number was real and the explanation was
wrong: it was this defect. With the rule fixed, that case went from -0.116 to
+0.264, and the harness's negative control still behaves.

## What this does not show

It says nothing about whether personality items resemble the working
behaviours the commons vocabulary describes. It tests the *rule*, on a
population with real structure, and the rule is what was found wanting.

## The second thing this dataset found

Once the prior rule was fixed, the same harness could be pointed at the other
half of the intuition layer: how bold a hunch is born.

Birth strength was `BASE_STRENGTH` plus fixed steps per verdict, clamped. That
is not a probability of anything, and the calibration benchmark was scoring it
as though it were. Measured here it carried no information at all.

```
                                              brier    skill   pred / obs
linear steps, constant anchor                0.3687   -0.689
posterior mean, anchor learned               0.2674   -0.176   0.45 / 0.65
...with borrowing raising the bar            0.2281   -0.003   0.58 / 0.66
```

Three findings, in the order they appeared.

**The anchor was the problem, not the estimator.** `BASE_STRENGTH` is 0.35, a
guess about a population nobody had seen; hunches here land 68% of the time.
Moving the anchor to the install's own observed rate improved skill five-fold,
while changing the estimator's shape barely moved it. The house rate is now
learned, and itself shrunk toward 0.35 until there is enough of a record to
believe it.

**A measurement can be confounded by a design choice.** The first sweep said a
small pseudo-count scored best. It scored best because birth strength is
capped below the rate these hunches achieve, so the sweep rewarded whatever
reached the cap fastest. The guard caught the consequence: at that value, one
win took a generator straight to the ceiling. The constant was set on the
principle instead.

**Two refusals were stacking into a fixed error.** Every guess a young install
makes is borrowed, because six people cannot mine a prior. A borrowed hunch was
capped at the ceiling times the discount, 0.45, while borrowed hunches were
landing 65% of the time. That is not caution, it is a twenty point error that
no amount of evidence could correct. Borrowing now raises the bar instead:
a borrowed prior needs more of its own record before it moves off the house
rate, and once it has proved itself on this install's people it is not really
borrowed any more.

## The third thing, and it settles the question the second one left open

The block above ends at a Brier skill of -0.003, which is parity with predicting
the base rate every time, and the paper written from it said establishing
positive skill remained outstanding. It no longer does.

Two defects, and the measurement only moves when both are fixed. The numbers
below are on identical seeds and identical cases, aggregated over the pooled
run rather than averaged per trial, so they are internally comparable and are
NOT comparable to the table above, which averages per-trial skill.

```
                                    brier     skill    pred / obs   sd(pred)
shipped                            0.2372   -0.0895   0.544 / 0.680   0.0607
prior anchors on its own rate      0.2224   -0.0219   0.593 / 0.680   0.0208
ceiling raised, old anchor         0.2359   -0.0836   0.548 / 0.680   0.0653
both                               0.1998   +0.0819   0.704 / 0.680   0.1011
```

**A firing prior was ignoring its own measurement.** Birth strength anchored
every hunch on the house rate, which is how often this install's guesses land in
general. For a leap from a look-alike that is the only thing available. For a
prior it is the wrong anchor: the prior arrives carrying a direct measurement of
how often Q follows P across a population, and that number was computed, used to
write the explanation string, and then discarded. It now anchors the forecast,
as the lower bound of the rate rather than the rate, shrunk toward the house rate
by support so a pair seen in twelve people barely moves and one seen in three
hundred nearly speaks for itself.

**The ceiling was stating a falsehood.** STRENGTH_CEILING was 0.6 while hunches
land 68% of the time here, so the engine was forbidden from stating the correct
forecast. The scorer already knew, and printed a note saying the Brier figure
was a floor imposed by the cap rather than a calibration failure. That is the
same fault as the borrowed-hunch cap in the paragraph above, applied to every
hunch rather than only borrowed ones: a cap below the rate a thing actually
achieves is not caution, it is a fixed error. Raised to 0.85, which is above the
observed rate; 0.85 and 1.0 score within 0.0005 of each other, so the finding is
that the cap must not bind below the observed rate, not that 0.85 is optimal.

The separation between a hunch and a belief is untouched, because that ceiling
was never what enforced it. `expects()` and `believes()` are different verbs
over different tables, the engine's UNKNOWN stays UNKNOWN for everything the
intuition layer holds, and nothing in the codebase compares a hunch's strength
against an evidenced confidence. `server/tests_prior_anchor.py` asserts that,
along with the interaction: revert either half and the skill goes with it.

**What this does not show.** +0.08 is modest positive skill, not strong. It
establishes that birth strength now carries information about the outcome, which
it previously did not, on one population whose hit rate happens to be 68%. On a
population where hunches land at 45% the ceiling would not bind and only the
anchor would matter. And the anchor's shrink weight of 60 was chosen on this
data, which is the same in-sample exposure disclosed for the lift margin.
