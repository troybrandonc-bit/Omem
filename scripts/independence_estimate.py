#!/usr/bin/env python3
"""Measure how independent an OMEM project's agreements actually are.

    python3 scripts/independence_estimate.py --url http://127.0.0.1:8787 \
        --key omem_sk_... --project proj_...

Agreement is cheap. Independent agreement is the thing worth paying for, and
it is the thing nobody measures. Two agents agreeing that a customer is on the
annual plan means something only if they arrived there separately: if both
read the same CRM record, the second one is an echo, and counting it as
corroboration is how a system talks itself into confidence it has not earned.

This computes that from the log the engine already writes. An assertion's
provenance is the transitive set of antecedents reached by following
derivation edges, terminating at Events, so the Events in that set are its
evidence roots. Two agreeing assertions corroborate each other only if they
were made by different agents AND their evidence roots are disjoint.

The headline number is the echo rate: of the times this project agreed with
itself, the fraction that was one source talking twice. It needs no
cooperation from any agent and no self-reported independence.

What it does not prove, stated here rather than in a footnote: disjoint roots
are not causal independence, because two Events can descend from one upstream
source OMEM never saw. Read it as a LOWER BOUND on correlation. And distinct
agent ids are not distinct models, which is the weakest term here.

Copyright 2026 Michael Brandon Clifford. MIT licensed.
"""
from __future__ import annotations

import argparse
import itertools
import json
import sys
import urllib.error
import urllib.request

CORROBORATING, ECHO, UNEVIDENCED = "corroborating", "echo", "unevidenced"


def fetch(url: str, key: str, project: str) -> list:
    req = urllib.request.Request(
        f"{url.rstrip('/')}/v1/export/memories?project={project}",
        headers={"Authorization": "Bearer " + key})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read().decode()).get("memories") or []
    except urllib.error.HTTPError as e:
        print(f"error {e.code}: {e.read().decode()[:200]}", file=sys.stderr)
        raise SystemExit(2)


def roots_of(memories: list) -> dict:
    """Evidence roots per assertion: everything in its provenance that is not
    itself an assertion, which is what the traversal bottoms out in. Derived
    from the export alone, so this needs no endpoint the engine does not
    already have."""
    assertion_ids = {m["id"] for m in memories}
    return {m["id"]: frozenset(p for p in (m.get("provenance") or [])
                               if p not in assertion_ids)
            for m in memories}


def classify(a: dict, b: dict, roots: dict) -> str:
    """How much does b add, given a? Ungrounded claims are their own answer
    rather than being counted as independent on the technicality that two
    empty root sets are disjoint: two agents asserting something neither can
    support is the failure this exists to name, not a kind of agreement."""
    if a.get("grounded") != "GROUNDED" or b.get("grounded") != "GROUNDED":
        return UNEVIDENCED
    if a.get("agent") == b.get("agent"):
        return ECHO
    if roots[a["id"]] & roots[b["id"]]:
        return ECHO
    return CORROBORATING


def independent_support(group: list, roots: dict) -> int:
    """The largest set of assertions in `group` that all corroborate each
    other. Maximum independent set is hard in general and irrelevant at this
    size: a proposition carries a handful of assertions, so exact search
    costs nothing and beats explaining a heuristic."""
    usable = [m for m in group if m.get("grounded") == "GROUNDED"]
    for size in range(len(usable), 1, -1):
        for combo in itertools.combinations(usable, size):
            if all(classify(x, y, roots) == CORROBORATING
                   for x, y in itertools.combinations(combo, 2)):
                return size
    return 1 if usable else 0


def estimate(memories: list) -> dict:
    roots = roots_of(memories)
    groups: dict = {}
    for m in memories:
        # Agreement means the same claim about the same subject. A denial is a
        # different claim and belongs to the conflict view, not to this one.
        for subject in (m.get("subjects") or []):
            groups.setdefault((subject, m.get("proposition")), []).append(m)

    counts = {CORROBORATING: 0, ECHO: 0, UNEVIDENCED: 0}
    propositions = []
    for (subject, proposition), group in sorted(groups.items()):
        if len(group) < 2:
            continue
        local = {CORROBORATING: 0, ECHO: 0, UNEVIDENCED: 0}
        for a, b in itertools.combinations(group, 2):
            local[classify(a, b, roots)] += 1
        for k in counts:
            counts[k] += local[k]
        propositions.append({
            "subject": subject, "proposition": proposition,
            "assertions": len(group),
            "independent_support": independent_support(group, roots),
            "pairs": local,
            "agents": sorted({m.get("agent") for m in group}),
        })

    decided = counts[CORROBORATING] + counts[ECHO]
    return {
        "assertions": len(memories),
        "agreeing_pairs": sum(counts.values()),
        "pairs": counts,
        # Of the times this project agreed with itself on evidence, how often
        # was that one source talking twice.
        "echo_rate": round(counts[ECHO] / decided, 3) if decided else None,
        "propositions": sorted(propositions,
                               key=lambda p: (p["independent_support"],
                                              -p["assertions"])),
    }


def report(r: dict) -> str:
    out = [f"assertions: {r['assertions']}   agreeing pairs: {r['agreeing_pairs']}"]
    p = r["pairs"]
    out.append(f"  corroborating {p[CORROBORATING]}   echo {p[ECHO]}"
               f"   unevidenced {p[UNEVIDENCED]}")
    out.append("  echo rate: " + ("n/a, nothing agreed on evidence yet"
                                  if r["echo_rate"] is None else str(r["echo_rate"])))
    weak = [x for x in r["propositions"]
            if x["assertions"] >= 2 and x["independent_support"] <= 1]
    if weak:
        out.append("")
        out.append("looks well attested, rests on one source:")
        for x in weak[:10]:
            out.append(f"  {x['subject']} {x['proposition']}: "
                       f"{x['assertions']} assertions from "
                       f"{len(x['agents'])} agent(s), independent support "
                       f"{x['independent_support']}")
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Estimate how independent a project's agreements are.")
    ap.add_argument("--url", default="http://127.0.0.1:8787")
    ap.add_argument("--key", required=True)
    ap.add_argument("--project", required=True)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    result = estimate(fetch(a.url, a.key, a.project))
    print(json.dumps(result, indent=2) if a.json else report(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
