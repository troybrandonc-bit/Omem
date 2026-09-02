#!/usr/bin/env python3
"""Run the prior rule over real respondents and report what it finds.

    python3 benchmarks/external/run.py
    python3 benchmarks/external/run.py --trials 10 --json

Downloads the data on first run and keeps it out of the repository. The number
to read is the within-factor rate: the dataset has five factors of ten items,
so a pair drawn at random joins two items of the same factor 9 times in 49,
which is 0.184. A miner finding real structure sits above that. A miner
finding popularity sits on it.
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

import big5  # noqa: E402

CHANCE = 9 / 49


def _m(xs):
    xs = [x for x in xs if x is not None]
    return statistics.fmean(xs) if xs else None


def study(trials: int = 5) -> dict:
    big5.fetch()
    rows, items = big5.load()
    scored = [big5.score_trial(big5.trial(s, rows)) for s in range(1, trials + 1)]

    # The lift sweep: keep only priors whose rate among antecedent-holders
    # beats the consequent's own base rate by a margin.
    import random
    yes = {i: 0 for i in items}
    tot = {i: 0 for i in items}
    for held, opp in rows:
        for i in held:
            yes[i] += 1
            tot[i] += 1
        for i in opp:
            tot[i] += 1
    base = {i: yes[i] / tot[i] for i in items if tot[i]}
    rng = random.Random(1)
    sample = list(rows)
    rng.shuffle(sample)
    mined = big5.mine(sample[:250])
    sweep = []
    for margin in (0.0, 0.05, 0.10, 0.15):
        kept = {k: v for k, v in mined.items()
                if v[0] / (v[0] + v[1]) >= base[k[1]] + margin}
        sweep.append({"margin": margin, "kept": len(kept),
                      "within_factor": round(big5.within_factor(kept), 3)})

    return {
        "respondents": len(rows), "items": len(items), "trials": trials,
        "chance_within_factor": round(CHANCE, 3),
        "bank_within_factor": round(_m(x["bank_within_factor"] for x in scored), 3),
        "mean_base_rate": round(statistics.fmean(base.values()), 3),
        "mean_base_rate_of_consequents":
            round(statistics.fmean(base[c] for (_a, c) in mined), 3),
        "prediction": {lab: {k: (round(_m(x[lab][k] for x in scored), 3)
                                 if _m(x[lab][k] for x in scored) is not None else None)
                             for k in ("n", "precision", "lift")}
                       for lab in ("local", "pooled", "marginal")},
        "lift_sweep": sweep,
    }


def render(r: dict) -> str:
    o = ["", "The prior rule, over %d real respondents and %d items."
         % (r["respondents"], r["items"]), ""]
    o.append("DOES IT FIND REAL STRUCTURE")
    o.append("  chance, a pair joining two items of one factor   %.3f"
             % r["chance_within_factor"])
    o.append("  the miner's priors                               %.3f"
             % r["bank_within_factor"])
    verdict = ("above chance" if r["bank_within_factor"] > r["chance_within_factor"] + 0.03
               else "AT CHANCE: it is finding no structure at all")
    o.append("  -> %s" % verdict)
    o.append("")
    o.append("WHY")
    o.append("  mean base rate of all items                      %.2f" % r["mean_base_rate"])
    o.append("  mean base rate of the consequents it picked      %.2f"
             % r["mean_base_rate_of_consequents"])
    o.append("  A rule asking whether 60% of P-holders hold Q is satisfied by Q")
    o.append("  being popular. That is what it is selecting.")
    o.append("")
    o.append("REQUIRING LIFT OVER THE CONSEQUENT'S OWN BASE RATE")
    o.append("  %-8s %12s %16s" % ("margin", "priors kept", "within-factor"))
    for s in r["lift_sweep"]:
        o.append("  %+8.2f %12d %16.3f" % (s["margin"], s["kept"], s["within_factor"]))
    o.append("")
    o.append("PREDICTING A HELD-OUT ANSWER SOMEBODY REALLY GAVE")
    o.append("  %-10s %9s %11s %8s" % ("", "coverage", "precision", "lift"))
    for lab in ("local", "pooled", "marginal"):
        p = r["prediction"][lab]
        o.append("  %-10s %9.0f %11s %8s" % (
            lab, p["n"],
            "%.3f" % p["precision"] if p["precision"] is not None else "n/a",
            "%+.3f" % p["lift"] if p["lift"] is not None else "n/a"))
    o.append("")
    return "\n".join(o)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--trials", type=int, default=5)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    r = study(a.trials)
    print(json.dumps(r, indent=1) if a.json else render(r))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
