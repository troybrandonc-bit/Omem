# The calibration benchmark

Does OMEM know how much to trust its own guesses about people?

`leap()` commits to a claim before the evidence is in and records how bold it
was. Reality later labels the hypothesis `supported` or `refuted`. A
probability stated in advance against an outcome recorded afterwards is a
forecast, so this scores it the way forecasts have been scored for a century,
rather than inventing a number that flatters the system.

```
python3 run.py                    # the default database
python3 run.py --db path/to.db --project proj_x
python3 run.py --json
```

Nothing is written and no network call is made.

## What the numbers mean

| | |
|---|---|
| `precision` | how often a hunch landed. On its own it says nothing: a system that only guesses the obvious scores well and is useless. |
| `brier` | mean squared error of the forecast. Lower is better. Rewards being right *and* being appropriately unsure. |
| `brier_skill` | **the number.** 1 − brier ÷ the brier of always predicting the base rate. Above zero, birth strength carries information. At or below zero it does not, whatever the precision says. |
| `reliability` | per strength band, predicted against observed. Where one number hides a system confident in the wrong places, this shows it. |

`brier_skill` is `null` when every outcome is the same, because the baseline is
then perfect and the ratio divides by zero. Reporting `0.0` for "not
measurable" would be a quiet lie.

## The caveat the report states itself

`_birth_strength` clamps strength to **[0.05, 0.6]** on purpose, so a hunch can
never dress itself as evidence. If hunches land more than 60% of the time, the
Brier score is penalising OMEM for a ceiling its own design imposes. That is
systematic underconfidence by construction, not a calibration failure, and the
report says which of the two it is looking at instead of leaving it to be
discovered.

## Why this exists

It is the baseline the commons has to beat.

Today a contributing install sends counts and gets nothing back: `leap()` reads
only its own project's priors, and the pooled bank is read by three display
routes and nothing else. If the pooled bank is ever wired into inference, this
benchmark run before and after is the whole argument for contributing — either
an install that shares gets measurably better at reading people, or the commons
is a donation and should be described as one.

See `server/COMMONS_REVISION_DESIGN.md`.
