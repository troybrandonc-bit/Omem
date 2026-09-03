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
    """Both arms. The shipped rule, and the same rule with the lift test
    switched off, because the case for the test is the difference between
    them and stating only one arm would be an assertion."""
    big5.fetch()
    rows, items = big5.load()

    yes = {i: 0 for i in items}
    tot = {i: 0 for i in items}
    for held, opp in rows:
        for i in held:
            yes[i] += 1
            tot[i] += 1
        for i in opp:
            tot[i] += 1
    base = {i: yes[i] / tot[i] for i in items if tot[i]}

    import random
    arms = {}
    for label, lift in (("shipped", None), ("no_lift_test", "off")):
        _orig = big5.mine
        if lift == "off":
            big5.mine = lambda s, _o=_orig: _mine_nolift(_o, s)
        scored = [big5.score_trial(big5.trial(s, rows)) for s in range(1, trials + 1)]
        rng = random.Random(1)
        sample = list(rows)
        rng.shuffle(sample)
        mined = big5.mine(sample[:250])
        big5.mine = _orig
        arms[label] = {
            "within_factor": round(big5.within_factor(mined), 3),
            "priors": len(mined),
            "consequent_base_rate":
                round(statistics.fmean(base[c] for (_a, c) in mined), 3) if mined else None,
            "prediction": {lab: {k: (round(_m(x[lab][k] for x in scored), 3)
                                     if _m(x[lab][k] for x in scored) is not None else None)
                                 for k in ("n", "precision", "lift")}
                           for lab in ("local", "pooled", "marginal")},
        }

    return {"respondents": len(rows), "items": len(items), "trials": trials,
            "chance_within_factor": round(CHANCE, 3),
            "mean_base_rate": round(statistics.fmean(base.values()), 3),
            "shipped_margin": big5.PRIOR_MIN_LIFT, "arms": arms}


def _mine_nolift(orig, subjects):
    """The rule as it stood before the lift test, for the comparison arm."""
    import big5 as _b
    holders, opposers = {}, {}
    for i, (h, o) in enumerate(subjects):
        for p in h:
            holders.setdefault(p, set()).add(i)
        for p in o:
            opposers.setdefault(p, set()).add(i)
    out = {}
    for a, base in holders.items():
        if len(base) < _b.PRIOR_FLOOR_N:
            continue
        for c in holders:
            if c == a:
                continue
            s = len(base & holders.get(c, set()))
            r = len(base & opposers.get(c, set()))
            if s < _b.PRIOR_FLOOR_N or not (s + r):
                continue
            if s / (s + r) < _b.PRIOR_MIN_RATE:
                continue
            out[(a, c)] = (s, r, len(base))
    return out


def render(r: dict) -> str:
    o = ["", "The prior rule, over %d real respondents and %d items."
         % (r["respondents"], r["items"]),
         "Chance, for a pair joining two items of one factor: %.3f"
         % r["chance_within_factor"],
         "Mean base rate across items: %.2f" % r["mean_base_rate"], ""]
    o.append("%-16s %9s %9s %14s %11s %9s" % (
        "", "priors", "within-f", "consequent BR", "marginal n", "marg lift"))
    for label in ("no_lift_test", "shipped"):
        a = r["arms"][label]
        p = a["prediction"]["marginal"]
        o.append("%-16s %9d %9.3f %14.2f %11.0f %+9.3f" % (
            label.replace("_", " "), a["priors"], a["within_factor"],
            a["consequent_base_rate"], p["n"], p["lift"]))
    o.append("")
    ship, plain = r["arms"]["shipped"], r["arms"]["no_lift_test"]
    if plain["within_factor"] <= r["chance_within_factor"] + 0.03:
        o.append("Without the lift test the miner sits at chance: it recovers none of")
        o.append("the known structure, and the consequents it picks are the popular")
        o.append("items, which is the whole of the effect.")
    if ship["within_factor"] > plain["within_factor"] + 0.1:
        o.append("With it, structure recovery rises to %.3f and the marginal guesses"
                 % ship["within_factor"])
        o.append("carry %+.3f lift against %+.3f, on comparable coverage. Requiring a"
                 % (ship["prediction"]["marginal"]["lift"],
                    plain["prediction"]["marginal"]["lift"]))
        o.append("prior to beat its consequent's own base rate is what turns the rule")
        o.append("from a popularity contest into an association.")
    o.append("")
    o.append("Shipped margin: PRIOR_MIN_LIFT = %.2f" % r["shipped_margin"])
    o.append("")
    return chr(10).join(o)


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
