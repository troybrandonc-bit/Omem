#!/usr/bin/env python3
"""How far the leap pass goes before it stops going.

Mining is quadratic in vocabulary and that is by design. The leap pass has a
different shape: for every target entity it scans every other entity for
resemblance, and then, for every look-alike and every prior, it walks the open
beliefs looking for one about a particular subject.

That last walk is the thing to watch. `_open_beliefs` iterates every assertion
in the store and asks the ledger whether each is open at T, which is real work
per assertion, and it does not depend on the target, the neighbour, or the
prior it is nested inside.

WHAT IT DRIVES. The real `leap`, with the real similarity scoring, the real
refusals and the real inserts. The belief engine is stood in for: assertions
are plain objects, the ledger says everything is open, and
`proposition_state` says UNKNOWN so that leaps are actually taken. `_profiles`
is stubbed for the same reason it is in the mining harness. Everything else is
shipped code, including `_open_beliefs`, which is the point: stubbing it away
would hide the cost being measured.
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


class Assertion:
    __slots__ = ("id", "subjects", "proposition")

    def __init__(self, aid, subject, proposition):
        self.id = aid
        self.subjects = [subject]
        self.proposition = proposition


class Ledger:
    def is_open_at(self, a, T):
        return True


class Store:
    def __init__(self, assertions):
        self._a = assertions

    def assertions(self):
        return self._a

    def assertion(self, aid):
        return None

    def entities(self):
        return []


class Engine:
    def __init__(self, assertions):
        self.store = Store(assertions)
        self.ledger = Ledger()

    def proposition_state(self, subjects, prop, T):
        return "UNKNOWN"


class FakeProject:
    is_demo = False

    def __init__(self, assertions, pid="proj"):
        self.id = pid
        self.engine = Engine(assertions)
        self.labels = {}

    def now(self):
        return 0.0

    def tick(self):
        return 0.0


def world(entities: int, props: int, seed: int = 1, hold: float = 0.3):
    """Assertions and profiles for `entities` people over `props`
    propositions, in the shapes leap expects."""
    rng = random.Random(seed)
    names = ["p%03d" % i for i in range(props)]
    assertions, profs = [], {}
    n = 0
    for e in range(entities):
        who = "person:%d" % e
        held = {x for x in names if rng.random() < hold}
        for x in held:
            assertions.append(Assertion("a%d" % n, who, x))
            n += 1
        profs[who] = [held, set()]
    return assertions, profs


def run(entities: int, props: int, priors: int = 0, seed: int = 1,
        hold: float = 0.3) -> dict:
    assertions, profs = world(entities, props, seed, hold)
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.executescript(_h.HYPOTHESES_SCHEMA)
    names = ["p%03d" % i for i in range(props)]
    for i in range(priors):
        db.execute("INSERT INTO priors VALUES(?,'proj',?,?,'default',9,1,10,0)",
                   ("pr_%d" % i, names[i % props], names[(i + 7) % props]))
    db.commit()

    calls = {"open_beliefs": 0}
    orig_profiles, orig_open, orig_opp = (_h._profiles, _h._open_beliefs,
                                          _h._declared_opposites)

    def counting_open(p_, T_):
        calls["open_beliefs"] += 1
        return orig_open(p_, T_)

    _h._profiles = lambda db_, p_, T_: profs
    _h._open_beliefs = counting_open
    _h._declared_opposites = lambda p_, prop_: set()
    try:
        t0 = time.perf_counter()
        res = _h.leap(FakeProject(assertions), db)
        elapsed = time.perf_counter() - t0
    finally:
        (_h._profiles, _h._open_beliefs,
         _h._declared_opposites) = orig_profiles, orig_open, orig_opp

    return {"entities": entities, "props": props, "priors": priors,
            "assertions": len(assertions), "seconds": round(elapsed, 3),
            "leapt": len(res.get("leapt", [])),
            "open_belief_scans": calls["open_beliefs"],
            "assertion_reads": calls["open_beliefs"] * len(assertions)}
