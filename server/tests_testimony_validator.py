"""The Testimony Record validator: does it actually catch the things the
specification exists to prevent?
Run: python3 tests_testimony_validator.py

A conformance claim is worth exactly what the checker behind it is worth, so
each test below breaks one requirement and asserts the level drops. The
published example record is validated too, so the specification's own example
can never quietly stop conforming.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import testimony_validate as tv  # noqa: E402

PASS = FAIL = 0
EXAMPLE = os.path.join(ROOT, "web", "public", "testimony-record-example.jsonl")


def check(n, c, d=""):
    global PASS, FAIL
    if c:
        PASS += 1
        print("  ok  " + n)
    else:
        FAIL += 1
        print("  FAIL " + n + "  " + str(d)[:200])


def lines():
    with open(EXAMPLE, encoding="utf-8") as f:
        return [l for l in f.read().splitlines() if l.strip()]


def level_of(ls):
    return tv.validate("\n".join(ls)).level


def edit(idx_match, mutate):
    """Copy the example, mutate the first line whose id matches, return lines."""
    out = []
    for l in lines():
        o = json.loads(l)
        if o.get("id") == idx_match:
            mutate(o)          # mutations are in place; a return value is not used
        out.append(json.dumps(o))
    return out


print("== the published example conforms ==")
check("the specification's own example reaches TR-4", level_of(lines()) == "TR-4",
      level_of(lines()))
check("the example is valid JSON Lines throughout",
      all(json.loads(l) for l in lines()))

print("== TR-1: the record is well formed and append-only ==")
check("a reused id is caught",
      level_of(lines() + [json.dumps({"spec": tv.SPEC, "type": "evidence",
                                      "id": "e_11", "at": "2026-09-01T10:00:00Z",
                                      "kind": "api", "source": "x"})]) is None)
check("an entry written before the one above it is caught",
      level_of(lines() + [json.dumps({"spec": tv.SPEC, "type": "evidence",
                                      "id": "e_99", "at": "2020-01-01T00:00:00Z",
                                      "kind": "api", "source": "x"})]) is None)
check("a different spec version is caught",
      level_of(edit("b_41", lambda o: o.update({"spec": "other/9.9"}))) is None)
check("a missing required field is caught",
      level_of(edit("b_41", lambda o: o.pop("asserted_by"))) is None)
check("an invalid enum value is caught",
      level_of(edit("b_41", lambda o: o.update({"state": "probably"}))) is None)
check("a malformed timestamp is caught",
      level_of(edit("b_44", lambda o: o.update({"at": "yesterday"}))) is None)

print("== TR-2: beliefs resolve to evidence, disagreements survive ==")
check("a belief citing evidence that is not in the record stops at TR-1",
      level_of(edit("b_45", lambda o: o.update({"evidence": ["e_nope"]}))) == "TR-1")
check("a belief that omits the evidence field entirely stops at TR-1",
      level_of(edit("b_45", lambda o: o.pop("evidence"))) == "TR-1")
check("a contradicted belief with no conflict entry stops at TR-1",
      level_of([l for l in lines() if '"id":"c_7"' not in l]) == "TR-1")
check("a conflict whose side is missing from the record stops at TR-1",
      level_of(edit("c_7", lambda o: o.update({"sides": ["b_41", "b_gone"]}))) == "TR-1")
check("a resolution that keeps a side outside the conflict stops at TR-1",
      level_of(edit("c_7", lambda o: o.update({"resolution": {
          "method": "policy", "by": {"id": "p", "kind": "system"},
          "at": "2026-09-01T09:20:00Z", "kept": "b_zzz"}}))) == "TR-1")
check("an unresolved conflict is fine, because honesty is not a failure",
      level_of(lines()) == "TR-4")

print("== TR-3: the gate, and who is behind it ==")
check("a plan declaring its own risk class stops at TR-2",
      level_of(edit("d_5", lambda o: o.update({"risk_source": "model"}))) == "TR-2")
check("a decision that never says where the risk class came from stops at TR-2",
      level_of(edit("d_5", lambda o: o.pop("risk_source"))) == "TR-2")
check("a refused action recorded as executed stops at TR-2",
      level_of(edit("d_3", lambda o: o.update({"executed": True}))) == "TR-2")
check("a refusal without a reason stops at TR-2",
      level_of(edit("d_4", lambda o: o.update({"reason": ""}))) == "TR-2")
check("an executed high-risk action with no approval stops at TR-2",
      level_of(edit("d_5", lambda o: o.update({"approval": None}))) == "TR-2")
check("an agent approving itself stops at TR-2",
      level_of(edit("a_9", lambda o: o.update({"approver": {
          "id": "support-agent", "kind": "agent"}}))) == "TR-2")
check("an approver identity taken from the request body stops at TR-2",
      level_of(edit("a_9", lambda o: o.update({"identity_source": "request"}))) == "TR-2")
check("an approval with no identity source at all stops at TR-2",
      level_of(edit("a_9", lambda o: o.pop("identity_source"))) == "TR-2")

print("== TR-4: verifiability ==")
check("no integrity entry stops at TR-3",
      level_of([l for l in lines() if '"id":"i_1"' not in l]) == "TR-3")
check("an integrity entry with no digest stops at TR-3",
      level_of(edit("i_1", lambda o: o.update({"digest": ""}))) == "TR-3")
check("a replay scheme that does not name its engine stops at TR-3",
      level_of(edit("i_1", lambda o: o.pop("engine_version"))) == "TR-3")
check("an integrity entry covering an entry that is not there stops at TR-3",
      level_of(edit("i_1", lambda o: o.update({"covers": ["nope"]}))) == "TR-3")

print("== the report itself ==")
r = tv.validate("\n".join(lines()))
d = r.as_dict()
check("the report is machine readable and names the level",
      d["level"] == "TR-4" and d["spec"] == tv.SPEC, d)
check("every check carries its level and outcome",
      all({"level", "check", "ok"} <= set(c) for c in d["checks"]))
check("an empty record reaches no level at all", tv.validate("").level is None)
check("a record of pure noise reaches no level", tv.validate("not json\n{").level is None)

print("\n%d passed, %d failed" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)
