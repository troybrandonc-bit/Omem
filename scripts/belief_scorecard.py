#!/usr/bin/env python3
"""Grade a project's past beliefs about people against what happened next.

    python3 scripts/belief_scorecard.py --url http://127.0.0.1:8787 \
        --key omem_sk_... --project proj_...

A memory that only accumulates gets larger, not wiser. The claim that a system
understands people better over time is only worth anything if the system can be
checked, so this asks the question nobody asks a memory: at the moment you
believed this about someone, what did the next independent observation say?

Three rules keep the grading honest.

Only LATER evidence counts. Grading a belief against the evidence it was
derived from measures nothing but arithmetic.

Only INDEPENDENT evidence counts. The same agent repeating itself is not
confirmation, and neither is a second agent reading the same source, so the
evidence-root test from independence_estimate.py decides what qualifies.

A belief nothing subsequently bore on is UNTESTED, and untested is its own
result rather than a quiet success. Most beliefs will land here, and a
scorecard that hid them would flatter the system exactly where it knows least.

The accumulation question is answered by the same walk: bucket beliefs by how
much the system already knew when it formed them, and see whether agreement
rises. That curve is the testable version of "it understands people better
over time".

Copyright 2026 Michael Brandon Clifford. MIT licensed.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from independence_estimate import roots_of  # noqa: E402

CONFIRMED, REFUTED, UNTESTED = "confirmed", "refuted", "untested"


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


def _split(proposition: str):
    """A denial is the same claim with the opposite polarity, which is what
    lets a later denial count as evidence against an earlier affirmation."""
    if (proposition or "").startswith("not:"):
        return proposition[4:], False
    return proposition, True


def _time(m: dict) -> float:
    at = m.get("assertion_time")
    return float(at if at is not None else 0)


def grade(memories: list) -> dict:
    """Walk every belief and ask what the next independent observation said."""
    roots = roots_of(memories)
    # Beliefs are grouped by the claim they are about, with denials folded in,
    # so "prefers_async" and "not:prefers_async" are graded against each other.
    claims: dict = {}
    for m in memories:
        base, affirms = _split(m.get("proposition") or "")
        for subject in (m.get("subjects") or []):
            claims.setdefault((subject, base), []).append((m, affirms))

    # How much did the system already know about this person when it formed a
    # given belief? Counted in prior assertions about that subject, which is
    # the input axis of the accumulation claim.
    prior_count: dict = {}
    seen_per_subject: dict = {}
    for m in sorted(memories, key=_time):
        for subject in (m.get("subjects") or []):
            prior_count[(m["id"], subject)] = seen_per_subject.get(subject, 0)
            seen_per_subject[subject] = seen_per_subject.get(subject, 0) + 1

    graded = []
    for (subject, base), rows in sorted(claims.items()):
        rows.sort(key=lambda r: _time(r[0]))
        for i, (m, affirms) in enumerate(rows):
            verdict, judge = UNTESTED, None
            for later, later_affirms in rows[i + 1:]:
                if _time(later) <= _time(m):
                    continue
                # Independence, the same test the estimator uses: a different
                # agent, and no shared evidence root.
                if later.get("agent") == m.get("agent"):
                    continue
                if roots[m["id"]] & roots[later["id"]]:
                    continue
                verdict = CONFIRMED if later_affirms == affirms else REFUTED
                judge = later["id"]
                break
            graded.append({
                "belief": m["id"], "subject": subject, "claim": base,
                "polarity": "affirm" if affirms else "deny",
                "agent": m.get("agent"),
                "grounded": m.get("grounded") == "GROUNDED",
                "prior_observations": prior_count.get((m["id"], subject), 0),
                "verdict": verdict, "judged_by": judge,
            })
    return summarise(graded)


def _rate(rows: list):
    """Agreement among beliefs that were actually tested. None when nothing
    was, because a rate over an empty set is a number that flatters."""
    tested = [r for r in rows if r["verdict"] != UNTESTED]
    if not tested:
        return None, 0
    hits = sum(1 for r in tested if r["verdict"] == CONFIRMED)
    return round(hits / len(tested), 3), len(tested)


def summarise(graded: list) -> dict:
    counts = {CONFIRMED: 0, REFUTED: 0, UNTESTED: 0}
    for r in graded:
        counts[r["verdict"]] += 1
    overall, tested_n = _rate(graded)

    # The accumulation curve. If understanding grows with input, agreement
    # should rise across these buckets. If it is flat, it does not, and that
    # is worth knowing early rather than in ten years.
    buckets = [(0, 0), (1, 2), (3, 9), (10, 10 ** 9)]
    curve = []
    for lo, hi in buckets:
        rows = [r for r in graded if lo <= r["prior_observations"] <= hi]
        rate, n = _rate(rows)
        curve.append({"prior_observations": (f"{lo}" if lo == hi else
                                             (f"{lo}+" if hi > 10 ** 8 else f"{lo}-{hi}")),
                      "beliefs": len(rows), "tested": n, "agreement": rate})

    grounded_rate, grounded_n = _rate([r for r in graded if r["grounded"]])
    ungrounded_rate, ungrounded_n = _rate([r for r in graded if not r["grounded"]])

    return {
        "beliefs": len(graded),
        "verdicts": counts,
        "tested": tested_n,
        "agreement": overall,
        "accumulation": curve,
        "by_grounding": {
            "grounded": {"tested": grounded_n, "agreement": grounded_rate},
            "ungrounded": {"tested": ungrounded_n, "agreement": ungrounded_rate},
        },
        "refuted_beliefs": [r for r in graded if r["verdict"] == REFUTED],
        "graded": graded,
    }


def report(s: dict) -> str:
    out = [f"beliefs graded: {s['beliefs']}   tested: {s['tested']}"
           f"   untested: {s['verdicts'][UNTESTED]}"]
    out.append("  agreement with the next independent observation: "
               + ("n/a, nothing was independently tested"
                  if s["agreement"] is None else str(s["agreement"])))
    out.append("")
    out.append("does it improve as it learns more about a person?")
    for row in s["accumulation"]:
        rate = "n/a" if row["agreement"] is None else str(row["agreement"])
        out.append(f"  after {row['prior_observations']:>5} prior observations: "
                   f"{rate:>5}   (tested {row['tested']} of {row['beliefs']})")
    g = s["by_grounding"]
    out.append("")
    out.append(f"  grounded beliefs:   {g['grounded']['agreement']}"
               f"   (tested {g['grounded']['tested']})")
    out.append(f"  ungrounded beliefs: {g['ungrounded']['agreement']}"
               f"   (tested {g['ungrounded']['tested']})")
    if s["refuted_beliefs"]:
        out.append("")
        out.append("beliefs the next independent observation contradicted:")
        for r in s["refuted_beliefs"][:10]:
            out.append(f"  {r['subject']} {r['claim']} ({r['polarity']}) "
                       f"from {r['agent']}, contradicted by {r['judged_by']}")
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Grade past beliefs against what happened next.")
    ap.add_argument("--url", default="http://127.0.0.1:8787")
    ap.add_argument("--key", required=True)
    ap.add_argument("--project", required=True)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    s = grade(fetch(a.url, a.key, a.project))
    if a.json:
        print(json.dumps(s, indent=2))
    else:
        print(report(s))
    return 0


if __name__ == "__main__":
    sys.exit(main())
