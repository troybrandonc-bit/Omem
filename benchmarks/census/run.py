#!/usr/bin/env python3
"""The conformance census: what each assessed system can already account for.

    python3 benchmarks/census/run.py              # the report
    python3 benchmarks/census/run.py --check      # validate the subject files only
    python3 benchmarks/census/run.py --json       # machine-readable

WHAT THIS IS NOT. It is not a scoreboard, and it deliberately cannot be turned
into one. There is no total, no percentage and no ordering of systems, because
the systems here are not trying to do the same job and a number that pretends
otherwise would be read as a ranking within a week of publication.

What it produces instead is a gap map: for each system, the highest level its
existing capabilities already satisfy, and for the level above that, exactly
which facts it does not currently keep. That is useful to the people who build
these systems, which a ranking is not, and it is checkable by them, which a
ranking also is not.

WHY THE AUTHOR'S OWN SYSTEM IS IN IT AND WHY THAT PROVES NOTHING. OMEM is the
reference implementation of the specification these questions derive from. It
scores well the way a dictionary's author spells well. The row is here so the
questions get applied to the system that wrote them first, and so a reader with
doubts about a question can open the source behind every answer in it.

Copyright 2026 Michael Brandon Clifford. MIT licensed.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import rubric      # noqa: E402
import subject     # noqa: E402

SUBJECTS = os.path.join(HERE, "subjects")
MARK = {"present": "yes", "partial": "part", "absent": "no", "not_applicable": "-"}


def gaps(doc: dict, level: str) -> list[tuple]:
    """What stands between a subject and `level`, with where that was checked."""
    out = []
    for req in rubric.BY_LEVEL[level]:
        got = doc["assessments"].get(req.id) or {}
        if got.get("verdict") in ("absent", "partial"):
            where = "; ".join(
                f"{e.get('kind')}: {e.get('locator')}"
                for e in (got.get("evidence") or [])[:2])
            out.append((req, got.get("verdict"), got.get("note") or "", where))
    return out


def render(docs: list[dict]) -> str:
    lines: list[str] = []
    w = lines.append

    w("The Testimony Record conformance census")
    w("=" * 39)
    w("")
    w(f"{len(docs)} system(s) assessed against {len(rubric.REQUIREMENTS)} "
      f"requirements drawn from the four conformance levels.")
    w("")
    w("Each answer below cites where it was checked. An 'absent' verdict cites")
    w("where the assessor looked and did not find it, which is the difference")
    w("between a measurement and an accusation.")
    w("")

    # ── the matrix ──────────────────────────────────────────────────────────
    names = [d["name"] for d in docs]
    idw = max(len("requirement"), *(len(r.id) for r in rubric.REQUIREMENTS))
    colw = [max(4, len(n)) for n in names]
    w("  " + "requirement".ljust(idw) + "  "
      + "  ".join(n.ljust(c) for n, c in zip(names, colw)))
    w("  " + "-" * idw + "  " + "  ".join("-" * c for c in colw))
    last = None
    for req in rubric.REQUIREMENTS:
        if req.level != last:
            last = req.level
            w("  " + f"{req.level} {rubric.LEVELS[req.level][0]}".ljust(idw))
        cells = []
        for d, c in zip(docs, colw):
            v = (d["assessments"].get(req.id) or {}).get("verdict")
            cells.append(MARK.get(v, "?").ljust(c))
        w("  " + req.id.ljust(idw) + "  " + "  ".join(cells))
    w("")
    w("  yes = the system keeps this fact    part = partially, or not durably")
    w("  no  = it does not keep it           -    = outside what it claims to do")
    w("")

    # ── per system ──────────────────────────────────────────────────────────
    for d in docs:
        reached = subject.level_reached(d)
        w("")
        w(d["name"] + " " + d["version"])
        w("-" * (len(d["name"]) + len(d["version"]) + 1))
        w(f"  claims to      {', '.join(d['claims'])}")
        w(f"  assessed       {d['assessed_on']} by {d['assessed_by']}")
        w(f"  already meets  {reached or 'nothing at TR-1 yet'}")

        nxt = None
        if reached is None:
            nxt = "TR-1"
        elif reached != "TR-4":
            nxt = rubric.LEVEL_ORDER[rubric.LEVEL_ORDER.index(reached) + 1]

        if nxt:
            missing = gaps(d, nxt)
            w("")
            w(f"  to reach {nxt} {rubric.LEVELS[nxt][0]}, it would need:")
            for req, verdict, note, where in missing:
                w(f"    {req.id} [{verdict}] {req.question}")
                w(f"          would need: {req.present_means}")
                if note:
                    w(f"          today:      {note}")
                if where:
                    w(f"          checked at: {where}")
        else:
            w("")
            w("  nothing outstanding at TR-4 on these questions.")

        if d.get("notes"):
            w("")
            w("  " + d["notes"])
    w("")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--check", action="store_true",
                    help="validate the subject files and stop")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--dir", default=SUBJECTS)
    a = ap.parse_args()

    files = sorted(f for f in os.listdir(a.dir) if f.endswith(".json"))
    docs, bad = [], 0
    for name in files:
        try:
            docs.append(subject.load(os.path.join(a.dir, name)))
        except subject.SubjectError as e:
            bad += 1
            print(str(e), file=sys.stderr)

    if a.check:
        print(f"{len(docs)} subject file(s) valid, {bad} rejected")
        return 1 if bad else 0
    if bad:
        return 1

    if a.json:
        print(json.dumps({
            "requirements": [r.as_dict() for r in rubric.REQUIREMENTS],
            "subjects": [dict(d, level_reached=subject.level_reached(d))
                         for d in docs]}, indent=1))
    else:
        print(render(docs))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
