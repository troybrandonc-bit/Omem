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

# Every finding gets a stable identifier, so a changelog, an issue or a paper
# can point at one verdict rather than at a document. "MTC" is the census;
# the date is when it was assessed, not when it is read. A finding that gets
# fixed keeps its id: the id names the observation, not the state of the world.
CENSUS_ID = "MTC"


MARK = {"present": "yes", "partial": "part", "absent": "no",
        "undetermined": "?", "not_applicable": "-"}


def finding_id(doc: dict, req_id: str) -> str:
    return f"{CENSUS_ID}-{doc['assessed_on']}-{doc['subject']}-{req_id}"


def tally(doc: dict, level: str) -> tuple[int, int]:
    """Requirements met, out of those that apply to what the subject claims.

    A level is reached only when nothing in it is missing, which means a system
    meeting four of five requirements reads as "nothing at TR-1 yet". That is
    the correct verdict and a misleading headline, so the tally is printed
    beside it. It is per level and never summed: a total across levels would be
    the score this census refuses to produce.
    """
    met = applicable = 0
    for req in rubric.BY_LEVEL[level]:
        if not rubric.applicable(req, doc["claims"]):
            continue
        applicable += 1
        if (doc["assessments"].get(req.id) or {}).get("verdict") == "present":
            met += 1
    return met, applicable


def gaps(doc: dict, level: str) -> list[tuple]:
    """What stands between a subject and `level`, with where that was checked."""
    out = []
    for req in rubric.BY_LEVEL[level]:
        got = doc["assessments"].get(req.id) or {}
        if got.get("verdict") in ("absent", "partial", "undetermined"):
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
            # A requirement outside what the subject claims reads as "-", not
            # as a blank. An unanswered cell would say the assessor did not
            # look, which is a different thing and one the validator forbids.
            if not rubric.applicable(req, d["claims"]):
                cells.append(MARK["not_applicable"].ljust(c))
                continue
            v = (d["assessments"].get(req.id) or {}).get("verdict")
            cells.append(MARK.get(v, "?").ljust(c))
        w("  " + req.id.ljust(idw) + "  " + "  ".join(cells))
    w("")
    w("  yes = the system keeps this fact    part = partially, or not durably")
    w("  no  = it does not keep it           -    = outside what it claims to do")
    w("  ?   = kept somewhere the assessor could not read, so not settled")
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
        cells = []
        for lvl in rubric.LEVEL_ORDER:
            met, app = tally(d, lvl)
            cells.append(f"{lvl} {met}/{app}" if app else f"{lvl} n/a")
        w("  by level       " + "   ".join(cells))

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


def render_one(doc: dict) -> str:
    """One subject's assessment, as a document its maintainers can act on.

    Sending somebody a census and expecting them to find their own row is how a
    correction request becomes a press release. This renders their rows only,
    with every citation, so a reply can be "R2.1 is wrong, look here" rather
    than "which part?".

    Deliberately written as a document rather than as a form. Structured data
    invites a template, a template invites a bolded label in front of every
    field, and a page of bolded labels reads as something nobody wrote. The
    citations stay a list because a list of citations is a list; everything
    around them is sentences.
    """
    lines: list[str] = []
    w = lines.append
    reached = subject.level_reached(doc)
    LEVEL_WORD = {None: "No conformance level is reached."}

    w(f"# {doc['name']} {doc['version']}: Testimony Record assessment")
    w("")
    w(f"Assessed on {doc['assessed_on']} by {doc['assessed_by']}, against the "
      f"Testimony Record specification, which is CC BY 4.0.")
    w("")
    w(doc["method"])
    w("")
    w(f"Repository {doc['url']}, at commit {doc['commit']}.")
    w("")
    tallies = ", ".join(
        f"{lvl} {t[0]} of {t[1]}" if t[1] else f"{lvl} not applicable"
        for lvl in rubric.LEVEL_ORDER for t in [tally(doc, lvl)])
    w(LEVEL_WORD.get(reached, f"Reaches {reached}.")
      + f" Requirements met, counting only those that apply to what this "
        f"system does: {tallies}.")
    w("")
    w("A level counts as reached only when nothing in it is missing, so a "
      "system meeting four of five requirements shows no level at all. The "
      "counts above are given so that reads correctly. There is no total and "
      "no ranking against other systems.")
    w("")
    if doc.get("notes"):
        w(doc["notes"])
        w("")

    for lvl in rubric.LEVEL_ORDER:
        rows = [r for r in rubric.BY_LEVEL[lvl]
                if rubric.applicable(r, doc["claims"])]
        if not rows:
            continue
        w(f"## {lvl} {rubric.LEVELS[lvl][0]}")
        w("")
        w(rubric.LEVELS[lvl][1])
        w("")
        for req in rows:
            got = doc["assessments"].get(req.id) or {}
            v = got.get("verdict", "unassessed")
            w(f"### {req.id}, {v}")
            w("")
            w(req.question)
            w("")
            w(f"Passing means {req.present_means}. "
              f"Cite this finding as {finding_id(doc, req.id)}.")
            w("")
            if got.get("note"):
                w(got["note"])
                w("")
            w("Checked at:")
            w("")
            for e in got.get("evidence") or []:
                bit = f"- {e.get('kind')}, `{e.get('locator')}`"
                if e.get("note"):
                    bit += f". {e['note']}"
                w(bit)
            w("")

    w("## Citing a finding from this")
    w("")
    w("Each requirement above carries an identifier of the form "
      "`MTC-<assessed date>-<subject>-<requirement>`. It names the "
      "observation and not the state of the world, so it stays valid after "
      "the thing it describes is changed. A changelog entry might read:")
    w("")
    w("```")
    w(f"Reported in the Machine Testimony conformance census, "
      f"{doc['assessed_on']} ({finding_id(doc, 'R1.1')})")
    w("```")
    w("")
    w("The census as a whole:")
    w("")
    w("```")
    w(f"Clifford, T. ({doc['assessed_on'][:4]}). The Testimony Record "
      f"conformance census. Machine Testimony. machinetestimony.org")
    w("```")
    w("")
    w("## If a verdict here is wrong")
    w("")
    w("Every answer above cites a file and a line at the pinned commit, or a "
      "search that can be repeated against it, so a wrong one can be shown to "
      "be wrong rather than argued about. Corrections are welcome by pull "
      "request against the assessment file, or by email to "
      "hello@omem-cloud.com naming the requirement and where to look. A "
      "correction that lands changes the file, the report and the assessment "
      "date.")
    w("")
    w("There is no fee, no membership, and no requirement to use any "
      "particular software. The specification text is CC BY 4.0 and the tools "
      "are MIT.")
    w("")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--check", action="store_true",
                    help="validate the subject files and stop")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--for", dest="subject_id", default=None,
                    help="render one subject's assessment as markdown, for "
                         "sending to the people who maintain it")
    ap.add_argument("--out-dir", default=None,
                    help="with --for all, write one file per subject here")
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

    if a.subject_id:
        if a.subject_id == "all":
            out = a.out_dir or "."
            os.makedirs(out, exist_ok=True)
            for d in docs:
                path = os.path.join(out, f"{d['subject']}-assessment.md")
                with open(path, "w", encoding="utf-8", newline="\n") as f:
                    f.write(render_one(d))
                print(f"wrote {path}")
            return 0
        picked = [d for d in docs if d["subject"] == a.subject_id]
        if not picked:
            print(f"no subject {a.subject_id!r}; have: "
                  + ", ".join(d["subject"] for d in docs), file=sys.stderr)
            return 1
        print(render_one(picked[0]))
        return 0

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
