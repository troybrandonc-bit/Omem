"""OMEM Cloud server test suite. Run: python3 tests.py
Covers: signup/session/keys, auth enforcement, project isolation, empty project,
assert/believe/why, contradiction, retraction, supersession, coreference,
provenance, timeline, multi-agent, error paths, and restart replay."""
import json
import os
import sys
import threading
import time
import urllib.request
import urllib.error

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
DB = "/tmp/omem_tests.db"
if os.path.exists(DB):
    os.remove(DB)
os.environ["OMEM_DB"] = DB

import os as _os_seed
_os_seed.environ['OMEM_SEED_DEMO']='1'
import api  # noqa: E402  (boots + seeds demo into the temp db)
from http.server import ThreadingHTTPServer  # noqa: E402

PORT = 8931
srv = ThreadingHTTPServer(("127.0.0.1", PORT), api.Handler)
threading.Thread(target=srv.serve_forever, daemon=True).start()
time.sleep(0.3)

BASE = f"http://127.0.0.1:{PORT}"
PASS = 0
FAIL = 0


def call(method, path, body=None, token=None):
    req = urllib.request.Request(BASE + path, method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Content-Type": "application/json",
                 **({"Authorization": f"Bearer {token}"} if token else {})})
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ok  {name}")
    else:
        FAIL += 1
        print(f"  FAIL {name}  {detail}")


print("== auth ==")
st, _ = call("GET", "/v1/health")
check("health is public", st == 200)
st, b = call("GET", "/v1/overview?project=demo")
check("no credentials -> 401", st == 401)

st, acct = call("POST", "/v1/signup", {"email": "ada@example.com", "org": "Ada Labs", "project": "Support agent"})
check("signup 201 with token+project+key", st == 201 and acct.get("token") and acct.get("project") and acct.get("api_key", {}).get("secret"))
SESS = acct["token"]
PROJ = acct["project"]["id"]
KEY = acct["api_key"]["secret"]

st, b = call("GET", "/v1/me", token=SESS)
check("me returns email+org", st == 200 and b["email"] == "ada@example.com" and b["org"])

st, b = call("GET", "/v1/projects", token=SESS)
ids = [p["id"] for p in b["data"]]
check("projects: own + labeled demo only", PROJ in ids and "demo" in ids)
demo_row = [p for p in b["data"] if p["id"] == "demo"][0]
check("demo flagged is_demo", demo_row.get("is_demo") is True)

print("== project isolation ==")
st, other = call("POST", "/v1/signup", {"email": "bob@example.com"})
OTHER_SESS = other["token"]
OTHER_PROJ = other["project"]["id"]
st, b = call("GET", f"/v1/overview?project={PROJ}", token=OTHER_SESS)
check("foreign session on my project -> 403", st == 403)
st, b = call("GET", f"/v1/overview?project={OTHER_PROJ}", token=KEY)
check("my key on foreign project -> 403", st == 403)
st, b = call("GET", "/v1/overview", token=KEY)
check("key without project param scopes itself", st == 200)

print("== empty project ==")
st, b = call("GET", f"/v1/overview?project={PROJ}", token=SESS)
check("fresh project has zero counts", b["counts"]["assertions"] == 0 and b["counts"]["conflicts"] == 0)
st, b = call("GET", f"/v1/assertions?project={PROJ}", token=SESS)
check("no memories yet", b["data"] == [])

print("== single assertion + why ==")
call("POST", f"/v1/entities?project={PROJ}", {"id": "cust:1", "type": "person", "label": "Cust One"}, SESS)
call("POST", f"/v1/agents?project={PROJ}", {"id": "bot@1", "kind": "system"}, SESS)
call("POST", f"/v1/events?project={PROJ}", {"id": "ev:1", "kind": "note", "event_time": "now"}, SESS)
st, a1 = call("POST", f"/v1/assertions?project={PROJ}",
              {"agent": "bot@1", "subjects": ["cust:1"], "proposition": "likes_tea",
               "because": ["ev:1"], "assertion_time": "now"}, SESS)
check("belief created grounded", st == 201 and a1["grounded"] in ("GROUNDED", True))
st, b = call("POST", f"/v1/queries/proposition-state?project={PROJ}",
             {"subjects": ["cust:1"], "proposition": "likes_tea"}, SESS)
check("believes -> BELIEVED_TRUE", b["state"] == "BELIEVED_TRUE")
st, w = call("GET", f"/v1/assertions/{a1['id']}/why?project={PROJ}", token=SESS)
check("why: grounded, provenance reaches event", w["grounded"] is True and any(n["id"] == "ev:1" for n in w["provenance"]["nodes"]))

print("== contradiction ==")
call("POST", f"/v1/declare-contradiction?project={PROJ}", {"token_a": "likes_tea", "token_b": "not:likes_tea"}, SESS)
call("POST", f"/v1/assertions?project={PROJ}",
     {"agent": "bot@1", "subjects": ["cust:1"], "proposition": "not:likes_tea", "assertion_time": "now"}, SESS)
st, b = call("POST", f"/v1/queries/proposition-state?project={PROJ}",
             {"subjects": ["cust:1"], "proposition": "likes_tea"}, SESS)
check("state flips to CONTRADICTED", b["state"] == "CONTRADICTED")
st, b = call("GET", f"/v1/conflicts?project={PROJ}", token=SESS)
check("conflicts lists the pair", len(b["conflicts"]) == 1)

print("== supersession + revision chain ==")
st, a2 = call("POST", f"/v1/assertions?project={PROJ}",
              {"agent": "bot@1", "subjects": ["cust:1"], "proposition": "on_free_plan", "assertion_time": "now"}, SESS)
st, a3 = call("POST", f"/v1/assertions/{a2['id']}/supersede?project={PROJ}",
              {"new": {"agent": "bot@1", "subjects": ["cust:1"], "proposition": "on_pro_plan", "assertion_time": "now"}}, SESS)
check("supersede 201", st == 201)
st, rc = call("GET", f"/v1/assertions/{a3['id']}/revision-chain?project={PROJ}", token=SESS)
check("revision chain ordered", [x["proposition"] for x in rc["chain"]] == ["on_free_plan", "on_pro_plan"])
st, b = call("POST", f"/v1/queries/proposition-state?project={PROJ}",
             {"subjects": ["cust:1"], "proposition": "on_free_plan"}, SESS)
check("old belief closed -> UNKNOWN", b["state"] == "UNKNOWN")

print("== retraction ==")
st, a4 = call("POST", f"/v1/assertions?project={PROJ}",
              {"agent": "bot@1", "subjects": ["cust:1"], "proposition": "temp_belief", "assertion_time": "now"}, SESS)
st, r = call("POST", f"/v1/assertions/{a4['id']}/retract?project={PROJ}", {"agent": "bot@1", "assertion_time": "now"}, SESS)
check("retract 201", st == 201)
st, b = call("POST", f"/v1/queries/proposition-state?project={PROJ}",
             {"subjects": ["cust:1"], "proposition": "temp_belief"}, SESS)
check("retracted -> UNKNOWN", b["state"] == "UNKNOWN")

print("== coreference ==")
call("POST", f"/v1/entities?project={PROJ}", {"id": "cust:dup", "type": "person"}, SESS)
st, c = call("POST", f"/v1/coreference?project={PROJ}",
             {"entity_a": "cust:1", "entity_b": "cust:dup", "agent": "bot@1", "assertion_time": "now"}, SESS)
check("corefer 201", st == 201)
st, part = call("GET", f"/v1/coreference/partition?project={PROJ}", token=SESS)
merged = [c for c in part["partition"] if "cust:1" in c and "cust:dup" in c]
check("partition merges the pair", len(merged) == 1)

print("== timeline + agents ==")
call("POST", f"/v1/agents?project={PROJ}", {"id": "bot@2", "kind": "system"}, SESS)
call("POST", f"/v1/assertions?project={PROJ}",
     {"agent": "bot@2", "subjects": ["cust:1"], "proposition": "second_agent_claim", "assertion_time": "now"}, SESS)
st, tl = call("GET", f"/v1/timeline?project={PROJ}", token=SESS)
check("timeline events ordered", [e["id"] for e in tl["events"]] == ["ev:1"])
st, ag = call("GET", f"/v1/agents/bot@2?project={PROJ}", token=SESS)
check("agent claims attributed", len(ag["claims"]) == 1)

print("== error paths ==")
st, b = call("POST", f"/v1/assertions?project={PROJ}",
             {"agent": "bot@1", "subjects": ["ghost"], "proposition": "x", "assertion_time": "now"}, SESS)
check("dangling subject -> 422 R_DANGLING", st == 422 and b["error"]["reason_code"] == "R_DANGLING")
st, b = call("POST", f"/v1/assertions?project={PROJ}", {"agent": "bot@1", "subjects": [], "proposition": "x", "assertion_time": "now"}, SESS)
check("empty subjects rejected", st == 422)
st, b = call("GET", f"/v1/assertions/nope/why?project={PROJ}", token=SESS)
check("missing assertion -> 404", st == 404)

print("== keys ==")
st, k2 = call("POST", f"/v1/keys?project={PROJ}", {"name": "CI key"}, SESS)
check("key create returns secret once", st == 201 and k2["secret"].startswith("omem_sk_"))
st, kl = call("GET", f"/v1/keys?project={PROJ}", token=SESS)
check("key list has no secrets", st == 200 and all("secret" not in k for k in kl["data"]))
st, _ = call("GET", f"/v1/overview?project={PROJ}", token=k2["secret"])
check("new key authenticates", st == 200)
st, _ = call("POST", f"/v1/keys/{k2['id']}/revoke?project={PROJ}", {}, SESS)
st, b = call("GET", f"/v1/overview?project={PROJ}", token=k2["secret"])
check("revoked key -> 401", st == 401)
st, kl = call("GET", f"/v1/keys?project={PROJ}", token=SESS)
used = [k for k in kl["data"] if k["prefix"] == acct["api_key"]["prefix"]]
check("last_used recorded on real use", used and used[0]["last_used"] is not None)

print("== restart replay (user writes persist) ==")
srv.shutdown()
snapshot_assertions = None
import importlib
import store as store_mod
importlib.reload(store_mod)
sys.modules.pop("api")
api2 = importlib.import_module("api")
p2 = api2.PROJECTS.get(PROJ)
check("project rehydrated", p2 is not None)
if p2:
    st_state = p2.engine.proposition_state(["cust:1"], "likes_tea", p2.now())
    check("replayed state still CONTRADICTED", st_state == "CONTRADICTED")
    chain = p2.engine.revision_chain(a3["id"])
    check("replayed revision chain intact", len(chain) == 2)
    part2 = [sorted(c) for c in p2.engine.referent_partition(p2.now())]
    check("replayed coreference intact", any("cust:1" in c and "cust:dup" in c for c in part2))

print(f"\n{PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
