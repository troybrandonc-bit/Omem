"""The census refuses assessments that cannot be checked. Run: python3 tests_census.py

A census of other people's software is a document that can do real damage, and
the people in it did not ask to be. The defence is not care, because care is
not auditable. It is that the tooling will not accept an assessment somebody
else cannot go and check, and this suite is what says so out loud.

The rule that matters most is the one about absence. Saying a system does not
keep some fact, without saying where you looked, is an accusation with a
measurement's clothes on. Every other rule here is ordinary hygiene; that one
is the whole reason the census can be published at all.
"""
import copy
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(ROOT, "benchmarks", "census"))

import rubric   # noqa: E402
import subject  # noqa: E402

PASS = FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  ok  " + name)
    else:
        FAIL += 1
        print("  FAIL " + name + "  " + str(detail)[:240])


def rejects(doc, fragment):
    """True when validation fails AND the message names the reason."""
    problems = subject.validate(doc)
    return bool(problems) and any(fragment in p for p in problems), problems


def valid_doc(claims=("stores",)):
    """A minimal assessment that passes, built from the rubric itself so it
    cannot drift out of date when a requirement is added."""
    doc = {
        "subject": "example", "name": "Example", "version": "1.0.0",
        "url": "https://example.invalid", "claims": list(claims),
        "assessed_on": "2026-09-04", "assessed_by": "tester",
        "method": "read of the source", "assessments": {},
    }
    for req in rubric.REQUIREMENTS:
        if rubric.applicable(req, doc["claims"]):
            doc["assessments"][req.id] = {
                "verdict": "present",
                "evidence": [{"kind": "source", "locator": "src/thing.py:1",
                              "note": "it is here"}]}
    return doc


print("== the baseline is actually valid ==")
base = valid_doc()
check("a complete, cited assessment passes", subject.validate(base) == [],
      subject.validate(base))
check("and it reaches the top level when nothing is missing",
      subject.level_reached(base) == "TR-4", subject.level_reached(base))

print("== an assessment nobody can check is refused ==")
d = copy.deepcopy(base)
d["assessments"]["R1.1"]["evidence"] = []
ok, why = rejects(d, "no evidence")
check("a verdict with no evidence at all is rejected", ok, why)

d = copy.deepcopy(base)
d["assessments"]["R1.1"]["evidence"] = [{"kind": "source", "locator": "   "}]
ok, why = rejects(d, "empty locator")
check("evidence with a blank locator is rejected", ok, why)

d = copy.deepcopy(base)
d["assessments"]["R1.1"]["evidence"] = [{"kind": "vibes", "locator": "x"}]
ok, why = rejects(d, "is not one of")
check("evidence of an invented kind is rejected", ok, why)

print("== the rule that keeps this from being a smear ==")
# An 'absent' verdict is the only kind that harms the system being assessed.
# It is therefore the only kind that has to say where the assessor looked.
d = copy.deepcopy(base)
d["assessments"]["R2.3"] = {
    "verdict": "absent",
    "evidence": [{"kind": "docs", "locator": "https://example.invalid/docs"}]}
ok, why = rejects(d, "'searched' evidence item")
check("claiming a capability is absent, without saying where you looked, "
      "is rejected", ok, why)

d = copy.deepcopy(base)
d["assessments"]["R2.3"] = {
    "verdict": "absent",
    "evidence": [
        {"kind": "searched", "locator": "grep -r 'conflict' src/",
         "note": "no conflict type in the store"},
        {"kind": "docs", "locator": "https://example.invalid/docs/memory"}]}
check("the same claim with a search that can be repeated is accepted",
      subject.validate(d) == [], subject.validate(d))
check("and an absent requirement stops the level being reached",
      subject.level_reached(d) == "TR-1", subject.level_reached(d))

print("== a requirement cannot be quietly dropped ==")
d = copy.deepcopy(base)
del d["assessments"]["R4.3"]
ok, why = rejects(d, "not assessed")
check("omitting an applicable requirement is rejected", ok, why)

print("== scope cannot be used as an escape hatch either way ==")
# Declaring a requirement irrelevant to a business you are in is how an
# unflattering row disappears.
d = copy.deepcopy(base)
d["assessments"]["R2.4"] = {"verdict": "not_applicable"}
ok, why = rejects(d, "not_applicable is not available here")
check("not_applicable on a capability the subject claims is rejected", ok, why)

# And the reverse: scoring a vector store on approval gates would be the way
# this census flattered whoever wrote it.
d = valid_doc(claims=("stores",))
d["assessments"]["R3.5"] = {
    "verdict": "absent",
    "evidence": [{"kind": "searched", "locator": "grep -r approve src/"}]}
ok, why = rejects(d, "cannot be scored")
check("scoring a subject on a capability it never claimed is rejected", ok, why)

d = valid_doc(claims=("stores", "acts"))
check("a subject that does claim to act is assessed on the gate requirements",
      "R3.5" in d["assessments"], sorted(d["assessments"]))
check("and one that does not is not",
      "R3.5" not in valid_doc(claims=("stores",))["assessments"])

print("== an assessment of an unnamed version is worthless ==")
d = copy.deepcopy(base)
d["version"] = ""
ok, why = rejects(d, "version is empty")
check("a subject with no version pinned is rejected", ok, why)

d = copy.deepcopy(base)
d["assessed_on"] = "September 2026"
ok, why = rejects(d, "assessed_on")
check("a free-text assessment date is rejected", ok, why)

print("== partial does not clear a level ==")
# A requirement half met is one that will not hold the first time somebody
# leans on it, and a conformance level is worth having only if it means one
# thing.
d = valid_doc(claims=("stores",))
d["assessments"]["R2.1"]["verdict"] = "partial"
check("a partial at TR-2 leaves the subject at TR-1",
      subject.level_reached(d) == "TR-1", subject.level_reached(d))
check("and the file is still valid, because partial is an honest answer",
      subject.validate(d) == [], subject.validate(d))

print("== every requirement is answerable by reading somebody else's code ==")
# The failure mode this rubric is most exposed to is a question only OMEM can
# answer, which would make the census an advertisement. Each one has to name a
# capability, not an implementation.
for req in rubric.REQUIREMENTS:
    if req.applies_to not in rubric.CAPABILITIES:
        check("requirement %s names a real capability" % req.id, False,
              req.applies_to)
check("every requirement is scoped to a declared capability",
      all(r.applies_to in rubric.CAPABILITIES for r in rubric.REQUIREMENTS))
check("no requirement mentions OMEM by name",
      not any("omem" in (r.question + r.present_means + r.partial_means).lower()
              for r in rubric.REQUIREMENTS),
      [r.id for r in rubric.REQUIREMENTS
       if "omem" in r.question.lower()])
check("every level has at least one requirement",
      all(rubric.BY_LEVEL.get(lvl) for lvl in rubric.LEVEL_ORDER))
check("requirement ids are unique",
      len(rubric.BY_ID) == len(rubric.REQUIREMENTS))

print("== the shipped subject files pass their own rules ==")
SUBJ = os.path.join(ROOT, "benchmarks", "census", "subjects")
for name in sorted(os.listdir(SUBJ)):
    if not name.endswith(".json"):
        continue
    with open(os.path.join(SUBJ, name), encoding="utf-8") as f:
        doc = json.load(f)
    check("%s is a valid assessment" % name, subject.validate(doc) == [],
          subject.validate(doc))

print("\n%d passed, %d failed" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)
