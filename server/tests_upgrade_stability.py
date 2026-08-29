"""Upgrades never rewrite your past. Run: python3 tests_upgrade_stability.py

testdata/golden_log_v1.json is an ops log frozen on 2026-08-29 together with
the state digest it replayed to that day: a story that walks contradiction,
supersession, retraction, a coreference merge and split, and a declared rule
whose conclusion cascades away with its premise. This suite replays that log
through TODAY's code and asserts the digest is byte-identical.

What that buys a deployment: the meaning of a recorded history is stable
across upgrades. No migration quietly reinterprets an op, no refactor changes
what an old log claims was believed. A deliberate semantic change is still
possible, but it cannot be quiet: it goes red here, and the honest path is a
golden_log_v2.json BESIDE this one, with v1 still replaying.

The digest is trusted because it is falsifiable: the suite also tampers with
one op and asserts the digest MOVES. A fixture check that cannot fail on a
changed history would be measuring nothing.
"""
import copy
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
TMP = os.environ.get("TEMP") or "/tmp"
DB = os.path.join(TMP, "omem_upgrade_stability.db")
if os.path.exists(DB):
    os.remove(DB)
os.environ["OMEM_DB"] = DB

import api  # noqa: E402
import replay_verify  # noqa: E402

PASS = FAIL = 0


def check(n, c, d=""):
    global PASS, FAIL
    if c:
        PASS += 1
        print("  ok  " + n)
    else:
        FAIL += 1
        print("  FAIL " + n + "  " + str(d)[:220])


FIXTURE = os.path.join(HERE, "testdata", "golden_log_v1.json")
check("the golden fixture exists and is committed", os.path.exists(FIXTURE))
with open(FIXTURE, encoding="utf-8") as f:
    g = json.load(f)

check("the fixture is a real session, not a stub",
      len(g["ops"]) >= 20 and g["counts"]["assertions"] >= 8, g.get("counts"))

print("== the log written then, replayed now ==")
row = dict(g["project_row"])
p1 = replay_verify.replay(api, row, g["ops"])
p2 = replay_verify.replay(api, row, g["ops"])
d1, counts1 = replay_verify.state_digest(p1)
d2, _ = replay_verify.state_digest(p2)

check("today's replay is deterministic with itself", d1 == d2, (d1, d2))
check("today's digest equals the digest frozen at generation time",
      d1 == g["digest"], {"now": d1, "frozen": g["digest"]})
check("and the counts agree too", counts1 == g["counts"],
      {"now": counts1, "frozen": g["counts"]})

print("== the states the story pinned, still pinned ==")
e, T = p1.engine, p1.now()
check("the retraction resolved the contradiction toward the surviving side",
      e.proposition_state(["person:ada"], "prefers_annual_billing", T)
      == "BELIEVED_FALSE")
check("the superseded address is closed and its successor holds",
      e.proposition_state(["person:grace"], "lives_in_paris", T)
      == "BELIEVED_TRUE"
      and e.proposition_state(["person:grace"], "lives_in_berlin", T)
      != "BELIEVED_TRUE")
check("the rule conclusion died with its retracted premise",
      e.proposition_state(["company:kernelworks", "person:ada"],
                          "rel_involves_ada", T) == "UNKNOWN")

print("== the digest can actually fail ==")
tampered = copy.deepcopy(g["ops"])
target = next(op for op in tampered
              if "prefers_annual_billing" in json.dumps(op["args"]))
target["args"] = json.loads(json.dumps(target["args"]).replace(
    "prefers_annual_billing", "prefers_monthly_billing"))
dt, _ = replay_verify.state_digest(replay_verify.replay(api, row, tampered))
check("one edited op moves the digest: tampering cannot be quiet",
      dt != g["digest"], dt)

print("\n%d passed, %d failed" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)
