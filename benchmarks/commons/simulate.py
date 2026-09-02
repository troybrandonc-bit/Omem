#!/usr/bin/env python3
"""Does a pooled bank make an install's guesses better, and when does it stop?

The commons rests on one sentence that has never been tested:

    an install with the pooled bank guesses measurably better than one without.

If it is true, contributing is self-interest and the loop turns. If it is
false, contributing is charity and no amount of distribution fixes that. It is
answerable now, with no installs, because the question is about the mechanism
rather than about any real population.

WHAT THIS SIMULATES, AND WHAT IT DOES NOT. It mirrors the prior mechanism:
mining a pair rule from co-occurrence under the same floor and rate as
`learn_priors`, keeping a verdict record PER PRIOR as `leap_generators` does,
projecting only into a silence, ranking pooled rows beneath local ones,
discounting a borrowed hunch, and moving birth strength by the prediction
error of each verdict. It does NOT run the belief engine, the similarity
layer, or the interrogation pass. So it answers "do pooled RATES beat local
rates for a young install", which is the question the flywheel turns on, and
nothing about the rest of the system. Every constant is imported from the live
modules and asserted equal in the suite, so the two cannot drift apart.

TWO MEASUREMENT RULES, BOTH LEARNED FROM THE FIRST DRAFT OF THIS FILE, WHICH
PRODUCED A CONFIDENT AND MEANINGLESS NUMBER.

  Average precision across the two conditions is not a comparison. The pooled
  install answers about twice as many questions, and the extra ones are the
  harder questions the local install had no prior for. Comparing the averages
  compares different exam papers. So the report separates the SHARED claims,
  where both had an opinion, from the MARGINAL ones only the bank could speak
  to, and it is the marginal set measured against the base rate of those very
  claims that says whether the bank added information.

  A record kept per install rather than per prior destroys the signal being
  measured. The engine keeps a win/loss record for every generator, so a prior
  that keeps landing births bolder hunches and one that keeps failing births
  weaker ones. One record shared across all of them makes every hunch the same
  strength and guarantees a meaningless calibration score.

DIVERGENCE is the fraction of regularities a population does NOT share with
the others: 0 means every install lives in the same world and pooling had
better help, 1 means they are unrelated and pooling had better hurt. A harness
that shows the bank helping at both ends is broken, and run.py sweeps the axis
so the crossover is reported rather than one flattering number.
"""
from __future__ import annotations

import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))   # the repo root
sys.path.insert(0, os.path.join(ROOT, "server"))
sys.path.insert(0, os.path.join(HERE, "..", "calibration"))

import hypotheses as _h  # noqa: E402
import commons as _c  # noqa: E402

# Imported, never copied. If a live module changes one of these the simulation
# changes with it, or the test asserting equality goes red. The source floor
# lives in commons.py because it is enforced at the return door, not in the
# engine.
PRIOR_FLOOR_N = _h.PRIOR_FLOOR_N
PRIOR_MIN_RATE = _h.PRIOR_MIN_RATE
BASE_STRENGTH = _h.BASE_STRENGTH
STRENGTH_FLOOR = _h.STRENGTH_FLOOR
STRENGTH_CEILING = _h.STRENGTH_CEILING
POOLED_DISCOUNT = _h.POOLED_DISCOUNT
POOLED_MIN_SOURCES = _c.POOLED_MIN_SOURCES

# Real tokens from the commons vocabulary, so nothing here could pass a gate
# the live system would refuse.
ANTECEDENTS = ("prefers_async", "works_remotely", "is_enterprise_customer",
               "prefers_short_meetings", "prefers_morning_meetings")
CONSEQUENTS = ("prefers_email_contact", "wants_pdf_invoices",
               "prefers_annual_billing", "intends_to_upgrade")

SIGNAL = 0.85       # a real regularity
BACKGROUND = 0.25   # no regularity: the consequent's own base rate


class World:
    """The truth the installs are each seeing a piece of."""

    def __init__(self, seed: int, divergence: float = 0.0,
                 hold: float = 0.3, signal_frac: float = 0.25):
        self.rng = random.Random(seed)
        self.divergence = divergence
        self.hold = hold                 # how much any one person holds
        self.signal_frac = signal_frac   # how much of the world is regular
        # Most pairs carry no regularity, so a miner that keeps everything is
        # punished by the floor and the minimum rate.
        self.shared = {(a, c): (SIGNAL if self.rng.random() < signal_frac
                                else BACKGROUND)
                       for a in ANTECEDENTS for c in CONSEQUENTS}

    def population_rates(self, seed: int) -> dict:
        """One population's rules.

        With probability `divergence` a pair is drawn independently for this
        population instead of taken from the shared world. That is genuine
        disagreement about people rather than noise around a common truth,
        which is what makes the high end of the sweep a real negative control:
        jittering a shared rate leaves a shared rate."""
        rng = random.Random(seed)
        out = {}
        for k, r in self.shared.items():
            if rng.random() < self.divergence:
                r = SIGNAL if rng.random() < self.signal_frac else BACKGROUND
            out[k] = r
        return out

    def subject(self, rates: dict, rng: random.Random) -> tuple[set, set]:
        """One person, generated BY the regularities rather than labelled with
        them."""
        held_a = {a for a in ANTECEDENTS if rng.random() < self.hold}
        held_c = set()
        for c in CONSEQUENTS:
            p = BACKGROUND
            for a in held_a:
                p = max(p, rates[(a, c)])
            if rng.random() < p:
                held_c.add(c)
        return held_a, held_c


def mine(subjects: list) -> dict:
    """The prior miner, mirroring learn_priors' rule.

    A pair is kept when at least PRIOR_FLOOR_N subjects hold both and the rate
    among those holding the antecedent clears PRIOR_MIN_RATE. No law of
    humanity from two examples."""
    out = {}
    for a in ANTECEDENTS:
        base = [s for s in subjects if a in s[0]]
        if len(base) < PRIOR_FLOOR_N:
            continue
        for c in CONSEQUENTS:
            support = sum(1 for s in base if c in s[1])
            refute = len(base) - support
            if support < PRIOR_FLOOR_N or not (support + refute):
                continue
            if support / (support + refute) < PRIOR_MIN_RATE:
                continue
            out[(a, c)] = (support, refute, len(base))
    return out


def pool(banks: list) -> dict:
    """The commons view: every install's priors summed, and a pair no two
    SEPARATE installs have seen refused entry. That is the echo check from
    commons.py, at the layer where other people's knowledge enters."""
    agg = {}
    for b in banks:
        for k, (s, r, n) in b.items():
            e = agg.setdefault(k, [0, 0, 0, 0])
            e[0] += s
            e[1] += r
            e[2] += n
            e[3] += 1
    return {k: tuple(v) for k, v in agg.items() if v[3] >= POOLED_MIN_SOURCES}


class Install:
    """One installation guessing about strangers, with or without the bank.

    Local priors rank first and a pooled row covering a pair a local prior
    already covers is dropped rather than merged: knowledge about YOUR
    population beats knowledge about other people's. A borrowed hunch is born
    at POOLED_DISCOUNT and floored, so borrowing can only ever make a guess
    more cautious. Every prior keeps its own record, as leap_generators does."""

    def __init__(self, local: dict, pooled: dict | None):
        self.rows = [(k, False) for k in sorted(local)]
        if pooled:
            self.rows += [(k, True) for k in sorted(pooled) if k not in local]
        self.record = {}          # key -> weighted (wins, losses)

    def strength_for(self, key, borrowed: bool) -> float:
        s = _h._birth_strength(self.record.get(key, (0.0, 0.0)), (0, 0))
        if borrowed:
            s = round(max(STRENGTH_FLOOR, s * POOLED_DISCOUNT), 2)
        return s

    def guess(self, held_a: set, spoken: set) -> list:
        """Every hypothesis this install forms about one stranger. A prior
        fires ONLY into a silence, which is why a general pattern can never
        override an individual."""
        out, claimed = [], set()
        for (a, c), borrowed in self.rows:
            if a not in held_a or c in spoken or c in claimed:
                continue
            claimed.add(c)
            out.append(((a, c), c, self.strength_for((a, c), borrowed), borrowed))
        return out

    def learn(self, key, strength: float, won: bool):
        w, l = self.record.get(key, (0.0, 0.0))
        s = _h.surprise(strength, won)
        self.record[key] = (w + (s if won else 0.0), l + (0.0 if won else s))


def trial(seed: int, divergence: float, n_installs: int = 8,
          peers_each: int = 40, local_subjects: int = 6,
          strangers: int = 120, hold: float = 0.3,
          signal_frac: float = 0.25) -> dict:
    """One run. A young install meets a stream of strangers from its own
    population and guesses at what they have not said. The same install is run
    twice over the SAME strangers in the same order, with and without the
    bank, so the comparison is not confounded by luck."""
    world = World(seed, divergence=divergence, hold=hold,
                  signal_frac=signal_frac)
    rng = random.Random(seed * 7919 + 13)

    banks = []
    for i in range(n_installs):
        rates = world.population_rates(seed * 100 + i)
        banks.append(mine([world.subject(rates, rng) for _ in range(peers_each)]))
    bank = pool(banks)

    mine_rates = world.population_rates(seed * 100 + n_installs)
    local = mine([world.subject(mine_rates, rng) for _ in range(local_subjects)])
    people = []
    for _ in range(strangers):
        held_a, held_c = world.subject(mine_rates, rng)
        # Some of what they hold is already on the record; the rest are the
        # silences a prior may fire into.
        spoken = {c for c in held_c if rng.random() < 0.3}
        people.append((held_a, held_c, spoken))

    # The population's own base rate per consequent: what a guess has to beat
    # to have told anyone anything.
    base = {c: sum(1 for _, hc, _ in people if c in hc) / len(people)
            for c in CONSEQUENTS}

    out = {"local_priors": len(local), "bank_rows": len(bank), "base": base,
           "mean_base": sum(base.values()) / len(base)}
    asked = {}
    for label, pooled in (("local", None), ("pooled", bank)):
        inst = Install(local, pooled)
        rows = []
        for idx, (held_a, held_c, spoken) in enumerate(people):
            for key, c, strength, borrowed in inst.guess(held_a, spoken):
                won = c in held_c
                rows.append({"q": (idx, c), "strength": strength,
                             "won": won, "borrowed": borrowed, "c": c})
                inst.learn(key, strength, won)
        out[label] = rows
        asked[label] = {r["q"] for r in rows}
    out["shared_q"] = asked["local"] & asked["pooled"]
    return out


def set_stats(rows, base):
    """Precision, and how far it sits above the base rate of the very claims
    that were guessed at. LIFT is the number that matters: guessing that
    someone prefers email, when four in five people do, is not information."""
    import score
    if not rows:
        return {"n": 0, "precision": None, "lift": None, "skill": None}
    rep = score.report([(r["strength"], r["won"]) for r in rows])
    exp = sum(base[r["c"]] for r in rows) / len(rows)
    return {"n": len(rows), "precision": rep.get("precision"),
            "lift": round(rep.get("precision", 0.0) - exp, 3),
            "skill": rep.get("brier_skill")}


def score_trial(res: dict) -> dict:
    base, shared = res["base"], res["shared_q"]
    out = {"local_priors": res["local_priors"], "bank_rows": res["bank_rows"],
           "mean_base": res["mean_base"]}
    for label in ("local", "pooled"):
        out[label] = set_stats(res[label], base)
    # The two comparisons that are actually comparable.
    out["shared"] = {lab: set_stats([r for r in res[lab] if r["q"] in shared], base)
                     for lab in ("local", "pooled")}
    out["marginal"] = set_stats(
        [r for r in res["pooled"] if r["q"] not in shared], base)
    return out
