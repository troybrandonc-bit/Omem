"""Subject files: one assessed system, and the rules that keep an assessment honest.

A census of other people's software is a document that can do real damage if it
is careless, and the people it damages did not ask to be in it. So the format
refuses more than it accepts:

  - Every applicable requirement must be assessed. A quietly omitted requirement
    is how an unflattering finding disappears.
  - Every verdict must cite evidence, INCLUDING `absent`. Saying a capability is
    missing without saying where you looked is not a measurement, it is an
    accusation, and it is the failure mode this whole census is most likely to
    commit.
  - `not_applicable` is only available for capabilities the subject does not
    claim. You cannot declare a requirement irrelevant to a business you are in.
  - A subject must pin a version or commit. "LangChain does not do X" is false
    within a month of being written unless it says which LangChain.

The point of putting these in code rather than in a style guide is that the
census cannot be published with an assessment that breaks them. The check runs
in CI like everything else.

Copyright 2026 Michael Brandon Clifford. MIT licensed.
"""
from __future__ import annotations

import json
import os
import re

import rubric

DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# How an assessor can know something. `searched` is the one that matters: it
# records where a look happened and found nothing, which is what makes an
# `absent` verdict a claim someone else can check rather than repeat.
EVIDENCE_KINDS = {
    "source": "a file and line in the assessed system's own source",
    "docs": "a page of the assessed system's documentation",
    "api": "a named method, endpoint or configuration surface",
    "test": "a test in the assessed system's own suite showing the behaviour",
    "run": "output from actually running the system",
    "searched": "where the assessor looked and did not find it",
}

REQUIRED_TOP = ("subject", "name", "version", "url", "claims", "assessed_on",
                "assessed_by", "method", "assessments")


class SubjectError(Exception):
    pass


def _evidence_problems(where: str, ev) -> list[str]:
    out = []
    if not isinstance(ev, list) or not ev:
        return [f"{where}: no evidence; every verdict must cite something"]
    for i, item in enumerate(ev):
        at = f"{where}.evidence[{i}]"
        if not isinstance(item, dict):
            out.append(f"{at}: not an object")
            continue
        kind = item.get("kind")
        if kind not in EVIDENCE_KINDS:
            out.append(f"{at}: kind {kind!r} is not one of "
                       f"{sorted(EVIDENCE_KINDS)}")
        if not str(item.get("locator") or "").strip():
            out.append(f"{at}: empty locator; say exactly where this was seen")
    return out


def validate(doc: dict) -> list[str]:
    """Every rule broken, rather than the first one, so one pass fixes a file."""
    problems: list[str] = []

    for f in REQUIRED_TOP:
        if f not in doc:
            problems.append(f"missing required field {f!r}")
    if problems:
        return problems

    if not str(doc["version"]).strip():
        problems.append("version is empty; an assessment of an unnamed version "
                        "is false as soon as the software moves")
    if not DATE.match(str(doc.get("assessed_on", ""))):
        problems.append("assessed_on must be YYYY-MM-DD")

    claims = doc["claims"]
    if not isinstance(claims, list) or not claims:
        problems.append("claims must be a non-empty list")
        claims = []
    for c in claims:
        if c not in rubric.CAPABILITIES:
            problems.append(f"claim {c!r} is not one of "
                            f"{sorted(rubric.CAPABILITIES)}")

    assessments = doc["assessments"]
    if not isinstance(assessments, dict):
        return problems + ["assessments must be an object keyed by requirement id"]

    for rid in assessments:
        if rid not in rubric.BY_ID:
            problems.append(f"assessment for unknown requirement {rid!r}")

    for req in rubric.REQUIREMENTS:
        applies = rubric.applicable(req, claims)
        got = assessments.get(req.id)

        if got is None:
            if applies:
                problems.append(
                    f"{req.id}: applicable to a claimed capability "
                    f"({req.applies_to}) but not assessed")
            continue

        if not isinstance(got, dict):
            problems.append(f"{req.id}: assessment is not an object")
            continue

        verdict = got.get("verdict")
        if verdict not in rubric.VERDICTS:
            problems.append(f"{req.id}: verdict {verdict!r} is not one of "
                            f"{list(rubric.VERDICTS)}")
            continue

        if applies and verdict == "not_applicable":
            problems.append(
                f"{req.id}: not_applicable is not available here. The subject "
                f"claims {req.applies_to!r}, so this requirement is part of the "
                f"business it says it is in.")
        if not applies and verdict != "not_applicable":
            problems.append(
                f"{req.id}: subject does not claim {req.applies_to!r}, so this "
                f"cannot be scored {verdict!r}. Assessing a system on a "
                f"capability it never offered is how a census flatters its "
                f"author.")

        if verdict == "not_applicable":
            continue

        problems.extend(_evidence_problems(req.id, got.get("evidence")))

        if verdict in ("absent", "undetermined"):
            kinds = {e.get("kind") for e in got.get("evidence") or []
                     if isinstance(e, dict)}
            if "searched" not in kinds:
                why = ("Otherwise it is an accusation, not a finding."
                       if verdict == "absent" else
                       "An unanswered question still has to say what was "
                       "looked at and why it could not be settled.")
                problems.append(
                    f"{req.id}: a {verdict!r} verdict needs at least one "
                    f"'searched' evidence item saying where you looked. {why}")

    return problems


def load(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        doc = json.load(f)
    problems = validate(doc)
    if problems:
        raise SubjectError(
            f"{os.path.basename(path)} is not a valid assessment:\n  - "
            + "\n  - ".join(problems))
    return doc


def load_all(directory: str) -> list[dict]:
    out = []
    for name in sorted(os.listdir(directory)):
        if name.endswith(".json"):
            out.append(load(os.path.join(directory, name)))
    return out


def level_reached(doc: dict) -> str | None:
    """The highest level with nothing missing below it.

    `partial` does not clear a level. A requirement half met is a requirement
    that will not hold up the first time somebody leans on it, and the whole
    value of a conformance level is that it means one thing.

    Nor does `undetermined`. A level awarded on a requirement nobody could
    check is a level resting on an assumption, which is worth less than no
    level at all because it looks the same as one that was verified.
    """
    reached = None
    for lvl in rubric.LEVEL_ORDER:
        ok = True
        for req in rubric.BY_LEVEL[lvl]:
            v = (doc["assessments"].get(req.id) or {}).get("verdict")
            if v in ("absent", "partial", "undetermined"):
                ok = False
            elif v is None and rubric.applicable(req, doc["claims"]):
                ok = False
        if not ok:
            break
        reached = lvl
    return reached
