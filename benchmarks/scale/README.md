# How far mining goes before it stops going

The other benchmarks ask whether prior mining finds real regularities. This one
asks whether it can still run when there are a lot of people and a lot of
things they might hold, which is a different question and the one that decides
whether the rest matters at scale.

```
python3 benchmarks/scale/run.py             # the envelope
python3 server/tests_scale_mining.py        # the guard
```

It drives the real `learn_priors`, with the real filters and the real inserts,
over synthetic profiles. `_profiles` and `_declared_opposites` are stubbed:
the first reads the belief engine and the second queries it, and neither is
what this measures. Everything inside the pair loop is shipped code.

## The measured envelope

```
POPULATION, at 80 propositions
   subjects    seconds      pairs    us per pair
        200      0.356       6320           56.4
       1000      0.315       6320           49.9
       4000      0.505       6320           79.9
      10000      1.076       6320          170.2
      20000      2.371       6320          375.2

VOCABULARY, at 5000 subjects
      props    seconds      pairs    us per pair
         40      0.223       1560          143.1
         80      0.601       6320           95.1
        160      1.769      25440           69.5
        320      5.982     101442           59.0
```

Twenty thousand subjects over eighty propositions in under two and a half
seconds, and five thousand subjects over a vocabulary of three hundred and
twenty in six, on a laptop with 3.8 GB of RAM that cannot build the dashboard.
Mining runs on the consolidation pass, not in a request.

Per-pair cost still rises with population, because intersecting two bitmasks
costs one machine word per sixty four subjects and that is real work. It does
not rise with vocabulary, which is what a cubic loop would do.

## What was wrong, and how it was found

Two things, both introduced the same day the lift test was.

**A vocabulary walk inside the pair loop.** `opposers(Q)` was called from
inside the loop, twice per surviving pair once the lift test arrived, and each
call iterated every negated proposition and asked the engine for declared
opposites. A loop quadratic in vocabulary by design became cubic. The
signature was visible before the cause was: cost per pair climbed from 84
microseconds at two hundred subjects to 170 at two thousand, when it should
have been flat. Both are now computed once, before the loop.

**Python sets for subject membership.** Intersecting two sets is linear in the
population and the loop does it twice per pair. Bitmasks measured 30 times
faster at a thousand subjects, 60 at ten thousand, 90 at fifty thousand, and
the gap widens as the population does. `int.bit_count` is 3.10 and later, so
there is a `bin(x).count("1")` fallback for 3.9.

## The guard

`tests_scale_mining.py` pins the property, not the clock, because a timing
assertion on a shared runner is a flake generator.

It counts how many times mining consults declared opposites and requires at
most one per proposition. With 24 propositions that is 24 calls; the
regression made 576, which is one per ordered pair, and the count says so
deterministically on any machine in under a second. It also runs the same
world at a hundred and at two thousand subjects and requires the count not to
move.

And it checks the optimisation did not change the answer: every prior the
engine writes is compared against a plain set implementation of the same rule,
counts included. A bitmask that disagrees with the set it replaced is worse
than a slow loop.

## The leap pass

Mining was the quadratic-by-design one. The leap pass had the worse problem,
and it only shows in the state a mature installation is actually in.

On the first run, `MAX_NEW_PER_RUN` stops everything after twenty five
hypotheses, so the cost is invisible. In steady state, reality already speaks
about most things, almost nothing is leapable, the cap never fires and the
loops run to the end. Measured there, before the fix:

```
 entities   seconds  store scans   assertion reads   hypotheses
      100     0.424          300           175,200            0
      200     1.322          600           726,600            0
      400     5.165        1,200         2,863,200            0
```

Five seconds and nearly three million assertion reads to produce nothing.
`_open_beliefs` walks the whole store and asks the ledger about every
assertion, and it was being called from inside a loop over entities and again
from inside a loop over priors, with both inner loops then discarding
everything not about one subject.

Three fixes, all exact:

**Read the store once and index it by subject.** Store scans went from twelve
hundred to one, and assertion reads from 2.8 million to 2,386.

**Build the evidence only for the neighbours that are used.** `_similarity`
formatted a human-readable explanation of every resemblance it scored, for
every entity in the project, and then three of them were kept. Scoring and
explaining are now separate calls, and the target's representative map is
built once per target rather than twice per comparison.

**Compare a target only with entities that share a feature.** An entity
sharing no proposition and no relation scores exactly zero, and
`MIN_SIMILARITY` is 2.0, so skipping it cannot change a result.

```
                    before      after
 400 entities        5.165      0.199
2000 entities       47.585      13.68
8000, sparse            --      46.75
```

The dense case stays quadratic and always will: when every entity shares a
feature with every other, there is nothing to skip. That case is a tiny
vocabulary, which is not the shape a real installation has.

## The guards

`tests_scale_leap.py` requires exactly one store scan per pass, at a hundred
entities and at eight hundred with three hundred priors, so the count cannot
start growing again. `tests_scale_mining.py` does the same for declared
opposites, at most one consultation per proposition. Both pin counts rather
than seconds, because a timing assertion on a shared runner is a flake
generator, and both were checked by reintroducing the regression and watching
them fail.
