#!/usr/bin/env python3
"""Run the commons experiment and print the whole grid, not the good row.

    python3 benchmarks/commons/run.py
    python3 benchmarks/commons/run.py --trials 50 --json

Two axes, because the answer depends on both and reporting one would be a
choice about which conclusion to reach.

  SPREAD is how much of the world the contributing populations do NOT share.
  At 0 they live in the same world and the bank should help. At 1 they are
  unrelated and it should not. A run where the bank helps at both ends is a
  broken harness, not a good result.

  DENSITY is how saturated the world is: how much any one person holds, and
  how much of the world carries a real regularity. It matters more than it
  sounds. When almost everyone holds almost everything, the base rate is
  already high and there is nothing for a prior to add, so the bank cannot
  help however good it is.

The column to read is LIFT on the marginal set: of the claims only the bank
could reach, how far above those claims' own base rate the guesses landed.
Precision alone is not a finding. Guessing that someone prefers email, where
four in five people do, tells nobody anything.
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "calibration"))

import simulate  # noqa: E402

SPREAD = (0.0, 0.5, 1.0)
# (hold, signal_frac): how much a person holds, how much of the world is
# regular. The last is the saturated world, kept in the grid because it is
# where the bank fails and leaving it out would be the flattering choice.
DENSITY = ((0.20, 0.20), (0.30, 0.25), (0.45, 0.40))


def _mean(xs):
    xs = [x for x in xs if x is not None]
    return statistics.fmean(xs) if xs else None


def grid(trials: int = 25, spreads=SPREAD, densities=DENSITY) -> list:
    rows = []
    for hold, sig in densities:
        for d in spreads:
            s = [simulate.score_trial(
                    simulate.trial(seed, d, hold=hold, signal_frac=sig))
                 for seed in range(1, trials + 1)]
            rows.append({
                "hold": hold, "signal_frac": sig, "spread": d,
                "mean_base": _mean([x["mean_base"] for x in s]),
                "local_priors": _mean([x["local_priors"] for x in s]),
                "coverage": {"local": _mean([x["local"]["n"] for x in s]),
                             "pooled": _mean([x["pooled"]["n"] for x in s])},
                "shared_lift": {lab: _mean([x["shared"][lab]["lift"] for x in s])
                                for lab in ("local", "pooled")},
                "marginal": {k: _mean([x["marginal"][k] for x in s])
                             for k in ("n", "precision", "lift")},
            })
    return rows


def _n(v, p=3):
    return "n/a" if v is None else f"{v:.{p}f}"


def render(rows: list) -> str:
    out = ["",
           "A young install (6 subjects) meeting 120 strangers, with and",
           "without the bank. Same strangers, same order, both ways.",
           "",
           f"{'hold':>5} {'reg':>5} {'spread':>7} {'base':>6} {'own':>5} "
           f"{'cover l/p':>12} {'marg n':>7} {'marg lift':>10}"]
    for r in rows:
        out.append(
            f"{r['hold']:>5.2f} {r['signal_frac']:>5.2f} {r['spread']:>7.2f} "
            f"{_n(r['mean_base'], 2):>6} {_n(r['local_priors'], 1):>5} "
            f"{_n(r['coverage']['local'], 0) + '/' + _n(r['coverage']['pooled'], 0):>12} "
            f"{_n(r['marginal']['n'], 0):>7} {_n(r['marginal']['lift']):>10}")
    out += ["",
            "hold/reg  how much a person holds, how much of the world is regular",
            "base      average base rate of the claims being guessed at",
            "own       priors the install could mine from its own six people",
            "marg lift precision of the borrowed guesses, minus the base rate",
            "          of those same claims. Above 0 the bank told it something.",
            ""]

    sparse = [r for r in rows if (r["hold"], r["signal_frac"]) == DENSITY[0]]
    if len(sparse) >= 2:
        lo = next((r for r in sparse if r["spread"] == 0.0), None)
        hi = next((r for r in sparse if r["spread"] == 1.0), None)
        if lo and hi and lo["marginal"]["lift"] is not None:
            out.append(f"Sparse world, populations that agree: "
                       f"lift {lo['marginal']['lift']:+.3f} on "
                       f"{lo['marginal']['n']:.0f} claims it could not otherwise "
                       f"reach.")
            out.append(f"Same world, populations that do not agree: "
                       f"lift {hi['marginal']['lift']:+.3f}. The bank stops "
                       f"paying, which is")
            out.append("what makes the first number believable rather than an "
                       "artefact.")
    out.append("")
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--trials", type=int, default=25)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    rows = grid(a.trials)
    print(json.dumps(rows, indent=1) if a.json else render(rows))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
