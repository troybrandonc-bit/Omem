#!/usr/bin/env python3
"""Does the prior mechanism find real structure in real people?

The commons benchmark generates its own world, so it can only test the
mechanism against the assumptions used to build it. This one does not. It runs
the same mining rule over answers that 19,719 people actually gave, whose
correlation structure nobody here chose, and asks two questions the simulation
could not:

  Does a young installation guess better with the pooled bank than without,
  on people it has never seen?

  Are the regularities it mines REAL ones? The dataset has a known latent
  structure, five factors of ten items each, so a pair drawn at random has
  about a one in five chance of falling inside a factor. If the miner is
  finding psychology rather than noise, its priors sit well above that line.
  That is a ground truth the synthetic world could not provide, because there
  the structure was whatever was put in.

THE DATA. Open Psychometrics' Big Five item responses, collected around 2012
through an online personality test, with consent recorded at the time and
published for research. Fifty items rated 1 to 5. It is downloaded when the
benchmark runs and never committed here: this repository does not redistribute
other people's survey responses.

THE MAPPING, which is closer than it has any right to be. An answer of 4 or 5
is holding the proposition; 1 or 2 is holding its negation; and 3, the neutral
answer, is a genuine silence. A prior fires only into a silence, so the
experiment gets its held-out question for free by hiding an answer somebody
actually gave and asking whether the bank can put it back.
"""
from __future__ import annotations

import csv
import io
import os
import random
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "server"))
sys.path.insert(0, os.path.join(HERE, "..", "calibration"))

import hypotheses as _h  # noqa: E402
import commons as _c  # noqa: E402

PRIOR_FLOOR_N = _h.PRIOR_FLOOR_N
PRIOR_MIN_RATE = _h.PRIOR_MIN_RATE
STRENGTH_FLOOR = _h.STRENGTH_FLOOR
POOLED_DISCOUNT = _h.POOLED_DISCOUNT
POOLED_MIN_SOURCES = _c.POOLED_MIN_SOURCES

SOURCE = ("https://raw.githubusercontent.com/haghish/openpsychometrics/"
          "master/BIG5/data.csv")
CACHE = os.path.join(HERE, "_big5.tsv")
FACTORS = ("E", "N", "A", "C", "O")


def fetch(path: str = CACHE) -> str:
    """Download once, keep it out of the repository."""
    if not os.path.exists(path):
        req = urllib.request.Request(SOURCE, headers={"User-Agent": "curl/8"})
        with urllib.request.urlopen(req, timeout=120) as r:
            io.open(path, "wb").write(r.read())
    return path


def load(path: str = CACHE, limit: int | None = None) -> list:
    """Each respondent as (held, opposed): the propositions they affirmed and
    the ones they denied. A neutral answer appears in neither, which is what
    makes it a silence rather than a missing value."""
    rows = []
    with io.open(path, encoding="utf-8", errors="replace") as f:
        r = csv.reader(f, delimiter="\t")
        header = next(r)
        items = [h for h in header
                 if len(h) >= 2 and h[0] in FACTORS and h[1:].isdigit()]
        idx = {h: header.index(h) for h in items}
        for row in r:
            held, opposed = set(), set()
            for it in items:
                try:
                    v = int(row[idx[it]])
                except (ValueError, IndexError):
                    continue
                if v >= 4:
                    held.add(it)
                elif 1 <= v <= 2:
                    opposed.add(it)
            if len(held) + len(opposed) >= 20:   # answered enough to be usable
                rows.append((held, opposed))
            if limit and len(rows) >= limit:
                break
    return rows, items


def mine(subjects: list) -> dict:
    """learn_priors' rule, unchanged: at least PRIOR_FLOOR_N subjects hold
    both, and the rate among those holding the antecedent clears
    PRIOR_MIN_RATE."""
    holders, opposers = {}, {}
    for i, (h, o) in enumerate(subjects):
        for p in h:
            holders.setdefault(p, set()).add(i)
        for p in o:
            opposers.setdefault(p, set()).add(i)
    out = {}
    for a, base in holders.items():
        if len(base) < PRIOR_FLOOR_N:
            continue
        for c in holders:
            if c == a:
                continue
            support = len(base & holders.get(c, set()))
            refute = len(base & opposers.get(c, set()))
            if support < PRIOR_FLOOR_N or not (support + refute):
                continue
            if support / (support + refute) < PRIOR_MIN_RATE:
                continue
            out[(a, c)] = (support, refute, len(base))
    return out


def pool(banks: list) -> dict:
    """The commons view, with the echo check: a pair no two separate
    installations have seen never crosses back."""
    agg = {}
    for b in banks:
        for k, (s, r, n) in b.items():
            e = agg.setdefault(k, [0, 0, 0, 0])
            e[0] += s
            e[1] += r
            e[2] += n
            e[3] += 1
    return {k: tuple(v) for k, v in agg.items() if v[3] >= POOLED_MIN_SOURCES}


def within_factor(pairs) -> float:
    """How many mined pairs join two items of the same factor. Chance is
    about 9 in 49, because each item has nine siblings among the other
    forty nine."""
    if not pairs:
        return 0.0
    same = sum(1 for a, c in pairs if a[0] == c[0])
    return same / len(pairs)


class Install:
    """One installation guessing about strangers. Local priors rank first, a
    pooled row covering a pair a local prior already covers is dropped, and a
    borrowed hunch is born at a discount."""

    def __init__(self, local: dict, pooled: dict | None):
        self.rows = [(k, False) for k in local]
        if pooled:
            self.rows += [(k, True) for k in pooled if k not in local]
        self.record = {}

    def strength(self, key, borrowed: bool) -> float:
        s = _h._birth_strength(self.record.get(key, (0.0, 0.0)), (0, 0))
        return round(max(STRENGTH_FLOOR, s * POOLED_DISCOUNT), 2) if borrowed else s

    def guess(self, held: set, silent: set):
        """Every hypothesis about one stranger. Fires only into a silence."""
        out, claimed = [], set()
        for (a, c), borrowed in self.rows:
            if a not in held or c not in silent or c in claimed:
                continue
            claimed.add(c)
            out.append(((a, c), c, self.strength((a, c), borrowed), borrowed))
        return out

    def learn(self, key, strength: float, won: bool):
        w, l = self.record.get(key, (0.0, 0.0))
        s = _h.surprise(strength, won)
        self.record[key] = (w + (s if won else 0.0), l + (0.0 if won else s))


def trial(seed: int, rows: list, n_installs: int = 12, peers_each: int = 250,
          local_subjects: int = 6, strangers: int = 400) -> dict:
    """One run. Peers fill the bank, a young installation meets strangers it
    has never seen, and one answer each of them really gave is hidden and asked
    for back."""
    rng = random.Random(seed)
    pool_rows = list(rows)
    rng.shuffle(pool_rows)

    cut = 0
    banks = []
    for _ in range(n_installs):
        banks.append(mine(pool_rows[cut:cut + peers_each]))
        cut += peers_each
    bank = pool(banks)

    local = mine(pool_rows[cut:cut + local_subjects])
    cut += local_subjects
    people = pool_rows[cut:cut + strangers]

    # Hide one answer each person actually gave: that is the silence.
    cases = []
    for held, opposed in people:
        answered = sorted(held | opposed)
        if not answered:
            continue
        hidden = rng.choice(answered)
        cases.append({
            "held": held - {hidden},
            "silent": {hidden},
            "truth": hidden in held,
            "item": hidden,
        })

    base = {}
    for c in cases:
        yes, no = base.get(c["item"], (0, 0))
        base[c["item"]] = (yes + (1 if c["truth"] else 0), no + (0 if c["truth"] else 1))
    base_rate = {k: y / (y + n) for k, (y, n) in base.items() if y + n}

    out = {"local_priors": len(local), "bank_rows": len(bank),
           "bank_within_factor": within_factor(bank),
           "local_within_factor": within_factor(local),
           "n_cases": len(cases)}
    asked = {}
    for label, pooled in (("local", None), ("pooled", bank)):
        inst = Install(local, pooled)
        recs = []
        for i, c in enumerate(cases):
            for key, item, st, borrowed in inst.guess(c["held"], c["silent"]):
                recs.append({"q": (i, item), "strength": st, "won": c["truth"],
                             "item": item, "borrowed": borrowed})
                inst.learn(key, st, c["truth"])
        out[label] = recs
        asked[label] = {r["q"] for r in recs}
    out["shared_q"] = asked["local"] & asked["pooled"]
    out["base_rate"] = base_rate
    return out


def stats(recs, base_rate):
    import score
    if not recs:
        return {"n": 0, "precision": None, "lift": None, "skill": None}
    rep = score.report([(r["strength"], r["won"]) for r in recs])
    exp = sum(base_rate.get(r["item"], 0.5) for r in recs) / len(recs)
    return {"n": len(recs), "precision": rep.get("precision"),
            "lift": round(rep.get("precision", 0.0) - exp, 3),
            "skill": rep.get("brier_skill")}


def score_trial(res: dict) -> dict:
    br, shared = res["base_rate"], res["shared_q"]
    out = {k: res[k] for k in ("local_priors", "bank_rows", "n_cases",
                               "bank_within_factor", "local_within_factor")}
    for lab in ("local", "pooled"):
        out[lab] = stats(res[lab], br)
    out["marginal"] = stats([r for r in res["pooled"] if r["q"] not in shared], br)
    return out
