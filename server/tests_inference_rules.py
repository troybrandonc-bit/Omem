"""Declared rules conclude; truth maintenance withdraws. Run:
python3 tests_inference_rules.py

The graph knew person:sarah --works_at--> company:beta and company:acme
--owns--> company:beta, and concluded nothing, because nothing above the
engine was allowed to. A DECLARED rule -- data, like a declared contradiction,
never a judgment the machine invents -- lets OMEM compose them:

    works_at(fwd) . owns(rev)  =>  involves(rev)
    "whoever works at a company you own is in your orbit"

The conclusion is an ordinary assertion by agent:omem-rules, derived from the
exact premises it used, projected to a real edge recall can traverse.

The half that matters is TRUTH MAINTENANCE: retract the ownership and the
conclusion falls IN THE SAME REQUEST -- and a conclusion resting on THAT
conclusion falls after it, cascade through the engine's own derivation graph.
Then the refusals: a fingerprint is spent once, so a conclusion a person
closed is never re-litigated from the same evidence (new evidence makes a new
fingerprint and may conclude again); a deactivated rule's conclusions are
withdrawn on the next pass; and a relation outside graph.RELATIONS cannot be
declared at all.
"""
import json
import os
import sys
import threading
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
TMP = os.environ.get("TEMP") or "/tmp"
DB = os.path.join(TMP, "omem_inference_rules.db")
if os.path.exists(DB):
    os.remove(DB)
os.environ["OMEM_DB"] = DB

import api  # noqa: E402
import graph as _graph  # noqa: E402
from http.server import ThreadingHTTPServer  # noqa: E402

PASS = FAIL = 0


def check(n, c, d=""):
    global PASS, FAIL
    if c:
        PASS += 1
        print("  ok  " + n)
    else:
        FAIL += 1
        print("  FAIL " + n + "  " + str(d)[:220])


OWNER = "rules@kronos.com"

srv = ThreadingHTTPServer(("127.0.0.1", 0), api.Handler)
PORT = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()
time.sleep(0.2)
BASE = "http://127.0.0.1:%d" % PORT


def call(m, path, body=None, key=None):
    h = {"Content-Type": "application/json"}
    if key:
        h["Authorization"] = "Bearer " + key
    r = urllib.request.Request(
        BASE + path, method=m,
        data=json.dumps(body).encode() if body is not None else None, headers=h)
    try:
        with urllib.request.urlopen(r, timeout=20) as resp:
            return resp.status, json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


acct = call("POST", "/v1/signup", {"email": OWNER})[1]
KEY, PID = acct["api_key"]["secret"], acct["project"]["id"]
AGENT = "agent:test"
call("POST", "/v1/agents?project=%s" % PID, {"id": AGENT, "kind": "system"}, KEY)


def ent(eid, label):
    kind = "organization" if eid.startswith("company:") else "person"
    call("POST", "/v1/entities?project=%s" % PID,
         {"id": eid, "type": kind, "label": label}, KEY)


def rel(subjects, prop, src, r, dst):
    """A relational assertion with its formation direction, the way the
    observe path records one: record(), then record_edge with the direction
    formation knows (the sorted fallback would point half of these backwards,
    which is the documented direction gap, not part of what is under test)."""
    st, resp = call("POST", "/v1/assertions?project=%s" % PID,
                    {"agent": AGENT, "subjects": subjects, "proposition": prop}, KEY)
    check("premise %s recorded" % prop, st == 201, resp)
    _graph.record_edge(api.STORE.db, PID, resp["id"], src, r, dst)
    return resp["id"]


def state_of(subjects, prop):
    st, r = call("POST", "/v1/queries/proposition-state?project=%s" % PID,
                 {"subjects": subjects, "proposition": prop}, KEY)
    return r.get("state")


def infer():
    st, r = call("POST", "/v1/memory/infer?project=%s" % PID, {}, KEY)
    check("infer answers", st == 200, r)
    return r


print("== declaring rules: data in, judgments refused ==")
st, bad = call("POST", "/v1/rules?project=%s" % PID,
               {"when": [{"rel": "acquired"}, {"rel": "owns"}],
                "then": {"rel": "involves"}}, KEY)
check("a relation outside the vocabulary cannot be declared", st == 422, bad)
check("and the refusal names the vocabulary",
      "works_at" in json.dumps(bad), bad)
st, bad2 = call("POST", "/v1/rules?project=%s" % PID,
                {"when": [{"rel": "works_at", "dir": "up"}, {"rel": "owns"}],
                 "then": {"rel": "involves"}}, KEY)
check("a made-up direction cannot be declared", st == 422, bad2)

st, r1 = call("POST", "/v1/rules?project=%s" % PID,
              {"when": [{"rel": "works_at", "dir": "fwd"},
                        {"rel": "owns", "dir": "rev"}],
               "then": {"rel": "involves", "dir": "rev"},
               "agent": AGENT}, KEY)
check("works_at . owns => involves declared", st == 201, r1)
RULE1 = r1["id"]
st, r1b = call("POST", "/v1/rules?project=%s" % PID,
               {"when": [{"rel": "works_at", "dir": "fwd"},
                         {"rel": "owns", "dir": "rev"}],
                "then": {"rel": "involves", "dir": "rev"}}, KEY)
check("declaring twice is declaring once", r1b.get("id") == RULE1, r1b)

st, r2 = call("POST", "/v1/rules?project=%s" % PID,
              {"when": [{"rel": "involves", "dir": "fwd"},
                        {"rel": "works_at", "dir": "fwd"}],
               "then": {"rel": "partner_of", "dir": "fwd"}}, KEY)
RULE2 = r2["id"]
st, listing = call("GET", "/v1/rules?project=%s" % PID, None, KEY)
check("both rules are listed", listing.get("count") == 2, listing)

print("== the premises: what the graph knew and could not use ==")
ent("company:acme", "Acme")
ent("company:beta", "BetaCorp")
ent("person:sarah", "Sarah Chen")
WORKS = rel(["person:sarah", "company:beta"], "rel_works_at_beta",
            "person:sarah", "works_at", "company:beta")
OWNS = rel(["company:acme", "company:beta"], "rel_owns_beta",
           "company:acme", "owns", "company:beta")
check("nothing concluded yet",
      state_of(["company:acme", "person:sarah"], "rel_involves_sarah") == "UNKNOWN")

print("== inference: compose, chain, explain ==")
run1 = infer()
props = [d["proposition"] for d in run1.get("derived", [])]
check("the orbit conclusion was derived", "rel_involves_sarah" in props, props)
check("and the chained rule fired on the conclusion's own edge",
      "rel_partner_of_beta" in props, props)
check("the engine now believes it",
      state_of(["company:acme", "person:sarah"], "rel_involves_sarah")
      == "BELIEVED_TRUE")
INV = next(d["assertion"] for d in run1["derived"]
           if d["proposition"] == "rel_involves_sarah")
erow = api.STORE.db.execute(
    "SELECT * FROM memory_edges WHERE project_id=? AND assertion_id=?",
    (PID, INV)).fetchone()
check("the conclusion is a real directed edge",
      erow is not None and (erow["src"], erow["relation"], erow["dst"])
      == ("company:acme", "involves", "person:sarah"), dict(erow or {}))
st, w = call("GET", "/v1/assertions/%s/why?project=%s&viewer=%s"
             % (INV, PID, AGENT), None, KEY)
blob = json.dumps(w)
check("/why walks from the conclusion to both premises",
      st == 200 and WORKS in blob and OWNS in blob, blob[:260])
check("and calls it a conclusion", '"inference"' in blob, blob[:200])

st, g = call("GET", "/v1/memory/graph?project=%s&entity=person:sarah&viewer=%s"
             % (PID, AGENT), None, KEY)
hops = {n["id"]: n["hops"] for n in g.get("nodes", [])}
check("recall's graph now reaches the owner in ONE hop, not two",
      hops.get("company:acme") == 1, hops)

run2 = infer()
check("a second pass derives nothing new", len(run2.get("derived", [])) == 0, run2)
check("because the evidence is already spent", run2.get("skipped_spent", 0) >= 1, run2)

print("== truth maintenance: retract the premise, watch the cascade ==")
st, _ = call("POST", "/v1/assertions/%s/retract?project=%s" % (OWNS, PID),
             {"agent": AGENT}, KEY)
check("a person retracts the ownership", st == 201)
check("the conclusion fell IN THE SAME REQUEST, no pass needed",
      state_of(["company:acme", "person:sarah"], "rel_involves_sarah") == "UNKNOWN")
check("and the conclusion resting on THAT conclusion fell after it",
      state_of(["company:acme", "company:beta"], "rel_partner_of_beta") == "UNKNOWN")
check("while the untouched premise still stands",
      state_of(["person:sarah", "company:beta"], "rel_works_at_beta")
      == "BELIEVED_TRUE")

print("== new evidence may conclude again; a person's closure is final ==")
OWNS2 = rel(["company:acme", "company:beta"], "rel_owns_beta",
            "company:acme", "owns", "company:beta")
run3 = infer()
props3 = [d["proposition"] for d in run3.get("derived", [])]
check("re-asserted ownership re-derives the orbit (new premises, new print)",
      "rel_involves_sarah" in props3, props3)
INV2 = next(d["assertion"] for d in run3["derived"]
            if d["proposition"] == "rel_involves_sarah")
st, _ = call("POST", "/v1/assertions/%s/retract?project=%s" % (INV2, PID),
             {"agent": AGENT}, KEY)
check("a person disagrees and retracts the conclusion itself", st == 201)
run4 = infer()
check("the machine does NOT re-litigate it from the same evidence",
      "rel_involves_sarah" not in
      [d["proposition"] for d in run4.get("derived", [])], run4.get("derived"))
check("it stays withdrawn",
      state_of(["company:acme", "person:sarah"], "rel_involves_sarah") == "UNKNOWN")

print("== a deactivated rule takes its conclusions with it ==")
ent("company:gamma", "Gamma")
ent("person:tom", "Tom Reyes")
rel(["person:tom", "company:gamma"], "rel_works_at_gamma",
    "person:tom", "works_at", "company:gamma")
rel(["company:acme", "company:gamma"], "rel_owns_gamma",
    "company:acme", "owns", "company:gamma")
run5 = infer()
check("the rule concludes for Tom too",
      "rel_involves_tom" in [d["proposition"] for d in run5.get("derived", [])],
      run5.get("derived"))
st, _ = call("POST", "/v1/rules/%s/deactivate?project=%s" % (RULE1, PID), {}, KEY)
check("the rule is deactivated", st == 200)
run6 = infer()
check("the next pass withdraws what only that rule justified",
      any(x.get("reason") == "rule deactivated"
          for x in run6.get("retracted", [])), run6.get("retracted"))
check("Tom's orbit conclusion is gone",
      state_of(["company:acme", "person:tom"], "rel_involves_tom") == "UNKNOWN")
check("and nothing re-derives while it stays off",
      len(infer().get("derived", [])) == 0)

print("== replay: the reasoning reconstructs from the op log ==")
p2 = api.Project(PID, "replay")
for op in api.STORE.ops_for(PID):
    p2.clock = max(p2.clock, op["clock"])
    api.apply_op(p2, op["kind"], op["args"])
T2 = p2.now()
check("replay reaches the same withdrawn state",
      p2.engine.proposition_state(["company:acme", "person:sarah"],
                                  "rel_involves_sarah", T2) == "UNKNOWN"
      and p2.engine.proposition_state(["company:acme", "person:tom"],
                                      "rel_involves_tom", T2) == "UNKNOWN")
check("and the surviving premise survives replay",
      p2.engine.proposition_state(["person:sarah", "company:beta"],
                                  "rel_works_at_beta", T2) == "BELIEVED_TRUE")

print("\n%d passed, %d failed" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)
