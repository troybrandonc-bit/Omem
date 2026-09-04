#!/usr/bin/env python3
"""A manifest for the census, so it can be recomputed and cannot be edited quietly.

    python3 benchmarks/census/manifest.py           # write MANIFEST.json
    python3 benchmarks/census/manifest.py --check   # verify it still matches

WHY THIS EXISTS. A census of other people's software attracts one predictable
objection: that the finding is out of date, or was never true, or has since been
fixed and therefore the document is wrong. Two properties answer it, and neither
is rhetoric.

The first is pinning. Every subject names a full 40-character commit, so a
claim is not "mem0 does not record deletion" but "mem0 at 9a7924be... did not
record deletion, and here are the file and line". Anyone can check out that tree
and look. A project that ships the capability next month has not falsified
anything: the assessment was about a commit that still exists and still says
what it said. That is why `subject.py` refuses an abbreviated hash.

The second is this file. It records the digest of every subject file and of the
rubric they were scored against, so the census as published can be shown not to
have changed since. Without it, a finding could be softened after a complaint,
or hardened after an argument, and nobody could tell. A document that grades
other systems on whether their records can be shown unaltered has no business
being unable to demonstrate the same about itself.

Applying the standard to the standard is not a flourish. It is the only version
of this exercise that is not hypocritical.

Copyright 2026 Michael Brandon Clifford. MIT licensed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import subject  # noqa: E402

SUBJECTS = os.path.join(HERE, "subjects")
MANIFEST = os.path.join(HERE, "MANIFEST.json")
SCHEME = "sha256"

# The rubric is part of what a verdict means. A subject file that has not
# changed, scored against questions that have, is not the same assessment, so
# the questions are digested alongside the answers.
SCORED_AGAINST = ("rubric.py", "subject.py")


def _digest(path: str) -> str:
    with open(path, "rb") as f:
        return SCHEME + ":" + hashlib.sha256(f.read()).hexdigest()


def build() -> dict:
    rows = []
    for name in sorted(os.listdir(SUBJECTS)):
        if not name.endswith(".json"):
            continue
        path = os.path.join(SUBJECTS, name)
        doc = subject.load(path)          # a manifest of invalid files is worthless
        rows.append({
            "file": f"subjects/{name}",
            "subject": doc["subject"],
            "name": doc["name"],
            "version": doc["version"],
            "url": doc["url"],
            "commit": doc["commit"],
            "assessed_on": doc["assessed_on"],
            "level_reached": subject.level_reached(doc),
            "assessed_by": doc["assessed_by"],
            "digest": _digest(path),
        })

    assessors = sorted({r["assessed_by"] for r in rows})
    scored = {f: _digest(os.path.join(HERE, f)) for f in SCORED_AGAINST}

    # One digest over everything above, computed from the parts rather than
    # from the rendered file, so it can be recomputed from a fresh checkout
    # without depending on this file's formatting.
    lines = [f"{r['file']}  {r['digest']}" for r in rows]
    lines += [f"{f}  {d}" for f, d in sorted(scored.items())]
    census = SCHEME + ":" + hashlib.sha256(
        "\n".join(lines).encode()).hexdigest()

    return {
        "spec": "testimony-record/0.1",
        "what": "Conformance census: assessments of named systems at named "
                "commits, against the requirements in rubric.py.",
        # Who made these observations and when. A finding identifier names the
        # observation rather than the state of the world, so it survives the
        # thing it describes being fixed. That is the point: a project that
        # changes something found here has not made the finding go away, and
        # the id is what a changelog or an issue can point at afterwards.
        "attribution": {
            "assessors": assessors,
            "publisher": "Machine Testimony",
            "doi": "10.5281/zenodo.22290922",
            "doi_this_version": "10.5281/zenodo.22290923",
            "author": "Clifford, T.",
            "url": "https://machinetestimony.org",
            "finding_id_format": "MTC-<assessed date>-<subject>-<requirement>",
            "finding_id_example": "MTC-2026-09-04-mem0-R1.5",
            "cite_as": "Clifford, T. (2026). The Testimony Record Conformance "
                       "Census: What Eight Agent Systems Record About What They "
                       "Did. Machine Testimony. doi:10.5281/zenodo.22290922",
            "priority": "The digest below fixes the content of these findings "
                        "at the assessed date. The deposit at doi:10.5281/zenodo.22290923, "
                        "held by CERN and dated 4 September 2026, is the "
                        "third-party record of when each observation was first "
                        "made. Cite the concept DOI, 10.5281/zenodo.22290922, which "
                        "resolves to the latest version; cite the version DOI "
                        "to point at this one specifically.",
        },
        "assessed_on": sorted({r["assessed_on"] for r in rows}),
        "subjects": rows,
        "scored_against": scored,
        "census_digest": census,
        "recompute": "python3 benchmarks/census/manifest.py --check",
        "note": "Each subject names the exact commit its citations refer to. A "
                "system that later gains a capability recorded here as absent "
                "has not made this document wrong: the assessment was of that "
                "commit, which still exists and still reads the same way. A "
                "later assessment is a new entry with a new date, never an "
                "edit to this one.",
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--check", action="store_true",
                    help="verify the manifest matches the files, and stop")
    a = ap.parse_args()

    built = build()

    if not a.check:
        with open(MANIFEST, "w", encoding="utf-8", newline="\n") as f:
            json.dump(built, f, indent=2, ensure_ascii=False)
            f.write("\n")
        print(f"wrote {os.path.relpath(MANIFEST, os.path.dirname(HERE))}")
        print(f"census digest: {built['census_digest']}")
        return 0

    if not os.path.exists(MANIFEST):
        print("no MANIFEST.json; run without --check to write one",
              file=sys.stderr)
        return 1
    with open(MANIFEST, encoding="utf-8") as f:
        stored = json.load(f)

    problems = []
    have = {r["file"]: r for r in stored.get("subjects", [])}
    want = {r["file"]: r for r in built["subjects"]}
    for f in sorted(set(have) | set(want)):
        if f not in have:
            problems.append(f"{f}: present now, not in the manifest")
        elif f not in want:
            problems.append(f"{f}: in the manifest, missing now")
        elif have[f]["digest"] != want[f]["digest"]:
            problems.append(f"{f}: content changed since the manifest was written")
        elif have[f]["commit"] != want[f]["commit"]:
            problems.append(f"{f}: assessed commit changed")
    for f, d in built["scored_against"].items():
        if stored.get("scored_against", {}).get(f) != d:
            problems.append(f"{f}: the questions changed since the manifest "
                            f"was written, so the verdicts mean something else")
    if stored.get("census_digest") != built["census_digest"]:
        problems.append("census digest does not match")

    if problems:
        print("MANIFEST does not match the files:", file=sys.stderr)
        for p in problems:
            print("  - " + p, file=sys.stderr)
        print("\nIf the change was intended, rewrite the manifest and say in "
              "the commit what changed and why.", file=sys.stderr)
        return 1
    print(f"manifest matches: {len(built['subjects'])} subject(s), "
          f"digest {built['census_digest']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
