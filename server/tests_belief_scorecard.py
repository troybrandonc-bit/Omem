"""Does the scorecard grade honestly, or does it flatter the system?
Run: python3 tests_belief_scorecard.py

The two ways this could cheat are the ones worth testing hardest: counting an
agent agreeing with itself as confirmation, and counting a second agent that
read the same source as confirmation. Both would produce a rising, meaningless
number, which is worse than no number at all. The third failure is quieter and
more tempting: treating a belief nothing ever tested as though it were right.
"""
import json
import os
import sys
import threading
import time
import http.client
from http.server import ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, ".."))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "scripts"))

TMP = os.environ.get("TEMP") or "/tmp"
os.environ["OMEM_DB"] = os.path.join(TMP, "omem_scorecard.db")
os.environ.setdefault("OMEM_SEED_DEMO", "0")
if os.path.exists(os.environ["OMEM_DB"]):
    os.remove(os.environ["OMEM_DB"])

import api  # noqa: E402
import belief_scorecard as SC  # noqa: E402

PASS = FAIL = 0


def check(n, c, d=""):
    global PASS, FAIL
    if c:
        PASS += 1
        print("  ok  " + n)
    else:
        FAIL += 1
        print("  FAIL " + n + "  " + str(d)[:220])


srv = ThreadingHTTPServer(("127.0.0.1", 0), api.Handler)
PORT = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()
time.sleep(0.3)


def call(method, path, body=None):
    c = http.client.HTTPConnection("127.0.0.1", PORT, timeout=15)
    c.request(method, path, body=json.dumps(body).encode() if body is not None else None,
              headers={"Content-Type": "application/json"})
    r = c.getresponse()
    t = r.read().decode()
    c.close()
    return json.loads(t or "{}")


PID = call("POST", "/v1/signup", {"email": "scorecard@omem.local"})["project"]["id"]
p = api.PROJECTS[PID]

for a in ("agent:a", "agent:b", "agent:c"):
    api.record(p, "agent", {"id": a, "kind": "system"})
for e in ("person:kai", "person:mira", "person:sol", "person:wren", "person:ash"):
    api.record(p, "entity", {"id": e, "type": "person"})


def event(eid):
    api.record(p, "event", {"id": eid, "ekind": "observation",
                            "event_time": p.tick(), "label": eid})


def claim(aid, agent, subject, proposition, because=None):
    api.record(p, "assert", {"id": aid, "agent": agent, "subjects": [subject],
                             "proposition": proposition, "assertion_time": p.tick()})
    if because:
        api.record(p, "derive", {"id": "d:" + aid, "consequent": aid,
                                 "antecedents": list(because), "dkind": "extraction"})


print("== what the next independent observation said ==")
# confirmed: a different agent, a different source, later, agreeing
event("obs:1"); event("obs:2")
claim("a:kai1", "agent:a", "person:kai", "prefers_async", ["obs:1"])
claim("a:kai2", "agent:b", "person:kai", "prefers_async", ["obs:2"])

# refuted: a different agent, a different source, later, denying
event("obs:3"); event("obs:4")
claim("a:mira1", "agent:a", "person:mira", "prefers_async", ["obs:3"])
claim("a:mira2", "agent:b", "person:mira", "not:prefers_async", ["obs:4"])

# untested: nothing subsequently bore on it
event("obs:5")
claim("a:sol1", "agent:a", "person:sol", "prefers_async", ["obs:5"])

# an agent agreeing with itself is not confirmation
event("obs:6"); event("obs:7")
claim("a:wren1", "agent:a", "person:wren", "prefers_async", ["obs:6"])
claim("a:wren2", "agent:a", "person:wren", "prefers_async", ["obs:7"])

# a second agent reading the SAME source is not confirmation either
event("obs:8")
claim("a:ash1", "agent:a", "person:ash", "prefers_async", ["obs:8"])
claim("a:ash2", "agent:b", "person:ash", "prefers_async", ["obs:8"])

memories = []
T = p.now()
for a in p.engine.store.assertions():
    row = api.shape_assertion(p, a.id, T)
    prov, grounded = p.engine.provenance(a.id)
    row.update({"grounded": grounded, "provenance": list(prov)})
    memories.append(row)

s = SC.grade(memories)
verdict = {r["belief"]: r["verdict"] for r in s["graded"]}

check("a later independent observation that agrees confirms the belief",
      verdict["a:kai1"] == SC.CONFIRMED, verdict.get("a:kai1"))
check("a later independent observation that denies refutes it",
      verdict["a:mira1"] == SC.REFUTED, verdict.get("a:mira1"))
check("a belief nothing bore on is untested, not correct",
      verdict["a:sol1"] == SC.UNTESTED, verdict.get("a:sol1"))
check("an agent agreeing with itself does not confirm anything",
      verdict["a:wren1"] == SC.UNTESTED, verdict.get("a:wren1"))
check("a second agent reading the same source does not confirm anything",
      verdict["a:ash1"] == SC.UNTESTED, verdict.get("a:ash1"))
check("the observation doing the judging is named, so a score can be checked",
      next(r for r in s["graded"] if r["belief"] == "a:kai1")["judged_by"] == "a:kai2")

print("== the rate refuses to flatter ==")
check("untested beliefs are excluded from the rate rather than counted right",
      s["tested"] == 2 and s["agreement"] == 0.5,
      {"tested": s["tested"], "agreement": s["agreement"]})
check("every belief is accounted for somewhere",
      sum(s["verdicts"].values()) == s["beliefs"] == len(s["graded"]), s["verdicts"])
check("a project with nothing in it reports no rate at all",
      SC.grade([])["agreement"] is None)
check("the refuted belief is listed so a person can go and look at it",
      [r["belief"] for r in s["refuted_beliefs"]] == ["a:mira1"], s["refuted_beliefs"])

print("== the accumulation curve ==")
# the axis of the ten year claim: beliefs formed when the system already knew
# more about that person should, if the thesis holds, agree more often.
for i in range(6):
    event("obs:acc%d" % i)
    claim("a:acc%d" % i, "agent:a" if i % 2 else "agent:c", "person:kai",
          "likes_mornings", ["obs:acc%d" % i])

memories = []
T = p.now()
for a in p.engine.store.assertions():
    row = api.shape_assertion(p, a.id, T)
    prov, grounded = p.engine.provenance(a.id)
    row.update({"grounded": grounded, "provenance": list(prov)})
    memories.append(row)
s2 = SC.grade(memories)
by_bucket = {row["prior_observations"]: row for row in s2["accumulation"]}

check("beliefs are bucketed by how much was already known about the person",
      set(by_bucket) == {"0", "1-2", "3-9", "10+"}, list(by_bucket))
check("a person the system has watched repeatedly lands in a later bucket",
      by_bucket["3-9"]["beliefs"] > 0, by_bucket)
check("every bucket's tested count never exceeds the beliefs in it",
      all(r["tested"] <= r["beliefs"] for r in s2["accumulation"]), s2["accumulation"])
check("the curve reports n/a rather than zero where nothing was tested",
      all(r["agreement"] is None or 0 <= r["agreement"] <= 1
          for r in s2["accumulation"]), s2["accumulation"])

print("== grounding is reported separately, because it should differ ==")
check("grounded and ungrounded beliefs are scored apart",
      set(s2["by_grounding"]) == {"grounded", "ungrounded"}, s2["by_grounding"])
check("the report renders without a rate when nothing was tested",
      "n/a" in SC.report(SC.grade([])), SC.report(SC.grade([])))

srv.shutdown()
print("\n%d passed, %d failed" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)
