#!/usr/bin/env python3
"""Can the scorecard detect accumulated understanding, when it is really there?

    python3 scripts/experiment_accumulation.py

Before asking whether OMEM's understanding of people improves with input, the
instrument has to be shown capable of detecting that improvement. So this runs
two synthetic worlds through belief_scorecard.py and checks that it tells them
apart.

  CONTROL     agents observe a person independently and never consult memory,
              so their accuracy is fixed no matter how long they have watched.
              Nothing accumulates. The curve should be flat.

  TREATMENT   agents consult what is already known before asserting, so their
              accuracy rises with the number of prior observations. Something
              accumulates. The curve should rise.

What a rising treatment curve proves: the measurement works. What it does NOT
prove: that OMEM accumulates understanding of real people. That claim needs
real longitudinal data, and this experiment is the thing that makes the result
of THAT run interpretable rather than decorative.

Copyright 2026 Michael Brandon Clifford. MIT licensed.
"""
from __future__ import annotations

import math
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import belief_scorecard as SC  # noqa: E402

PEOPLE = 400
OBSERVATIONS = 14
BASE_ACCURACY = 0.70          # an agent looking at a person cold
CEILING = 0.96                # an agent with the memory behind it
AGENTS = ["agent:%d" % i for i in range(6)]


def world(accuracy_fn, seed: int) -> list:
    """Synthetic records in the shape the memory export produces. Each person
    has one hidden trait; agents observe it with error and take turns, so
    consecutive observations are always by different agents and therefore
    independent by the scorecard's own test."""
    rng = random.Random(seed)
    memories = []
    clock = 0
    for i in range(PEOPLE):
        subject = "person:%d" % i
        truth = rng.random() < 0.5
        for k in range(OBSERVATIONS):
            clock += 1
            correct = rng.random() < accuracy_fn(k)
            says = truth if correct else (not truth)
            memories.append({
                "id": "a:%d:%d" % (i, k),
                "agent": AGENTS[k % len(AGENTS)],
                "subjects": [subject],
                "proposition": "prefers_async" if says else "not:prefers_async",
                "assertion_time": clock,
                "grounded": "UNGROUNDED",
                "provenance": [],
            })
    return memories


def flat(_k: int) -> float:
    return BASE_ACCURACY


def learns(k: int) -> float:
    """Accuracy improving with what is already known about this person, with
    diminishing returns, which is what learning about someone actually looks
    like."""
    return BASE_ACCURACY + (CEILING - BASE_ACCURACY) * (1 - math.exp(-k / 4.0))


def curve(memories: list):
    return SC.grade(memories)["accumulation"]


def main() -> int:
    print("A synthetic check that the instrument can see accumulation.\n")
    print("%d people, %d observations each, %d agents taking turns."
          % (PEOPLE, OBSERVATIONS, len(AGENTS)))
    print("Agreement is between a belief and the NEXT INDEPENDENT observation,")
    print("so with per-observation accuracy p it should read p^2 + (1-p)^2.\n")

    for name, fn, seed in (("CONTROL   (memory never consulted)", flat, 11),
                           ("TREATMENT (memory consulted)", learns, 11)):
        print(name)
        for row in curve(world(fn, seed)):
            rate = "n/a" if row["agreement"] is None else "%.3f" % row["agreement"]
            print("  after %5s prior observations: %5s   (tested %d)"
                  % (row["prior_observations"], rate, row["tested"]))
        print()

    print("Expected: control flat near %.2f, treatment rising toward %.2f."
          % (BASE_ACCURACY ** 2 + (1 - BASE_ACCURACY) ** 2,
             CEILING ** 2 + (1 - CEILING) ** 2))
    print("A rising treatment curve means the measurement works. It says")
    print("nothing yet about whether OMEM accumulates understanding of real")
    print("people, which is the next experiment and needs real data.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
