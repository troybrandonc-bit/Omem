#!/usr/bin/env python3
"""How far does prior mining go before it stops going?

The correctness benchmarks ask whether the rule finds real regularities. This
one asks whether it can still run when there are a lot of people and a lot of
things they might hold, which is a different question and the one that decides
whether any of the rest matters at scale.

WHAT IT DRIVES. The real `learn_priors`, with the real filters and the real
inserts, against synthetic profiles. `_profiles` and `_declared_opposites` are
stubbed, because the first reads the belief engine and the second queries it,
and neither is what this measures. Everything inside the pair loop is the
shipped code.

WHAT TO WATCH. The pair loop is quadratic in distinct propositions by
construction, which is expected and fine. What is not fine is anything that
turns that into a cube, and the way that happens is a per-pair call that walks
the whole vocabulary. The report prints time per pair examined, because a
number that grows with the population is the signature of exactly that.
"""
from __future__ import annotations

import os
import random
import sqlite3
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "server"))

import hypotheses as _h  # noqa: E402


class FakeProject:
    """learn_priors uses an id, a clock, and the engine only through the two
    functions this harness stubs."""

    def __init__(self, pid="proj"):
        self.id = pid

    def now(self):
        return 0.0


def world(subjects: int, props: int, seed: int = 1, hold: float = 0.3,
          signal: float = 0.25):
    """Synthetic profiles in the shape `_profiles` returns: subject ->
    (propositions, ...). Some pairs carry a real association so the miner has
    something to keep, and negations appear so the refute path is exercised."""
    rng = random.Random(seed)
    names = ["p%03d" % i for i in range(props)]
    rules = {}
    for i, a in enumerate(names):
        if rng.random() < signal:
            rules[a] = names[(i + 1) % props]
    profs = {}
    for s in range(subjects):
        held = set()
        for n in names:
            if rng.random() < hold:
                held.add(n)
        for a in list(held):
            q = rules.get(a)
            if q and rng.random() < 0.85:
                held.add(q)
        for n in names:                       # some stated disagreement
            if n not in held and rng.random() < 0.12:
                held.add("not:" + n)
        profs["person:%d" % s] = (held, set())
    return profs


def run(subjects: int, props: int, seed: int = 1) -> dict:
    profs = world(subjects, props, seed)
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.executescript(_h.HYPOTHESES_SCHEMA)

    orig_profiles, orig_opposites = _h._profiles, _h._declared_opposites
    _h._profiles = lambda db_, p_, T_: profs
    _h._declared_opposites = lambda p_, prop_: set()
    try:
        t0 = time.perf_counter()
        res = _h.learn_priors(FakeProject(), db)
        elapsed = time.perf_counter() - t0
    finally:
        _h._profiles, _h._declared_opposites = orig_profiles, orig_opposites

    pairs = res.get("examined_pairs", 0)
    return {"subjects": subjects, "props": props, "seconds": round(elapsed, 3),
            "pairs": pairs, "kept": res.get("kept", 0),
            "us_per_pair": round(elapsed / pairs * 1e6, 1) if pairs else None}
