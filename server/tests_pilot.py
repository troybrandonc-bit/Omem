"""Pilot tests: onboarding checklist from real state, feedback, recall counting,
customer status lifecycle, admin support drill-down, full zero-to-value flow.
Run: python3 tests_pilot.py"""
import os
import sys
import json
import threading
import time
import urllib.request
import urllib.error

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
DB = "/tmp/omem_pilot_tests.db"
if os.path.exists(DB):
    os.remove(DB)
os.environ["OMEM_DB"] = DB
os.environ["OMEM_ADMIN_EMAILS"] = "founder@omem.dev"

import api  # noqa: E402
from http.server import ThreadingHTTPServer  # noqa: E402

srv = ThreadingHTTPServer(("127.0.0.1", 0), api.Handler)
PORT = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()
time.sleep(0.2)
BASE = f"http://127.0.0.1:{PORT}"
PASS = FAIL = 0


def check(n, c, d=""):
    global PASS, FAIL
    if c:
        PASS += 1; print(f"  ok  {n}")
    else:
        FAIL += 1; print(f"  FAIL {n}  {d}")


def call(m, path, body=None, key=None):
    req = urllib.request.Request(BASE + path, method=m,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Content-Type": "application/json", **({"Authorization": f"Bearer {key}"} if key else {})})
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def steps_done(chk):
    return {s["id"]: s["done"] for s in chk["steps"]}


print("== onboarding checklist tracks REAL state, step by step ==")
_, acct = call("POST", "/v1/signup", {"email": "pilot@newco.com", "org": "NewCo"})
KEY = acct["api_key"]["secret"]; PID = acct["project"]["id"]; SESS = acct["token"]
_, chk = call("GET", f"/v1/onboarding?project={PID}", None, SESS)
d = steps_done(chk)
check("org+project+key done after signup", d["org"] and d["project"] and d["key"])
check("source/record/memory/recall/agent NOT done yet",
      not d["source"] and not d["record"] and not d["memory"] and not d["recall"] and not d["agent"])

# connect a source (webhook)
_, wh = call("POST", f"/v1/connectors?project={PID}", {"kind": "webhook", "name": "CRM"}, KEY)
_, chk = call("GET", f"/v1/onboarding?project={PID}", None, SESS)
check("source step flips after connect", steps_done(chk)["source"])

# deliver data
call("POST", f"/v1/webhooks/{wh['id']}", {"id": "e1", "customer": "ada", "subject": "s", "body": "prefer email"}, KEY)
call("POST", f"/v1/ingest/process?project={PID}", {}, KEY)
_, chk = call("GET", f"/v1/onboarding?project={PID}", None, SESS)
d = steps_done(chk)
check("record + memory + agent flip after ingestion", d["record"] and d["memory"] and d["agent"])
check("recall still pending", not d["recall"])

call("POST", f"/v1/recall?project={PID}", {"about": "customer:ada"}, KEY)
_, chk = call("GET", f"/v1/onboarding?project={PID}", None, SESS)
check("recall flips after first recall", steps_done(chk)["recall"])
check("checklist complete 8/8", chk["completed"] == 8)

print("== recall frequency tracking ==")
call("POST", f"/v1/recall?project={PID}", {"about": "customer:ada"}, KEY)
call("POST", f"/v1/recall?project={PID}", {"about": "customer:ada"}, KEY)
_, top = call("GET", f"/v1/memory/top-recalled?project={PID}", None, KEY)
check("top-recalled has the memory", len(top["data"]) >= 1)
check("count reflects 3 recalls", top["data"][0]["count"] == 3, str(top["data"]))

print("== feedback ==")
aid = None
_, rec = call("POST", f"/v1/recall?project={PID}", {"about": "customer:ada"}, KEY)
aid = rec["memories"][0]["assertion"]
st, _ = call("POST", f"/v1/feedback?project={PID}", {"kind": "useful", "assertion_id": aid}, SESS)
check("feedback recorded 201", st == 201)
st, _ = call("POST", f"/v1/feedback?project={PID}", {"kind": "incorrect", "assertion_id": aid, "comment": "wrong customer"}, SESS)
check("second feedback recorded", st == 201)
st, r = call("POST", f"/v1/feedback?project={PID}", {"kind": "amazing"}, SESS)
check("invalid kind -> 422", st == 422)
_, fb = call("GET", f"/v1/feedback?project={PID}", None, SESS)
check("feedback summary counts", fb["summary"].get("useful") == 1 and fb["summary"].get("incorrect") == 1)
check("feedback rows carry comment", any(f.get("comment") == "wrong customer" for f in fb["data"]))

print("== customer/pilot lifecycle ==")
_, facct = call("POST", "/v1/signup", {"email": "founder@omem.dev"})
FTOK = facct["token"]
OID = api.STORE.org_for_user(api.STORE.user_for_session(SESS)["id"])["id"]
st, cs = call("POST", f"/v1/admin/orgs/{OID}/status", {"status": "trial", "pilot_start": time.time(), "notes": "security co pilot"}, FTOK)
check("operator sets pilot status", st == 200 and cs["status"] == "trial")
st, _ = call("POST", f"/v1/admin/orgs/{OID}/status", {"status": "platinum"}, FTOK)
check("invalid status -> 422", st == 422)
st, _ = call("POST", f"/v1/admin/orgs/{OID}/status", {"status": "paid"}, SESS)
check("customer cannot set own status -> 403", st == 403)
_, orgs = call("GET", "/v1/admin/orgs", None, FTOK)
check("org list carries customer status", any(o["customer"]["status"] == "trial" for o in orgs["data"]))

print("== admin support drill-down ==")
st, det = call("GET", f"/v1/admin/orgs/{OID}", None, FTOK)
check("drill-down 200 with projects", st == 200 and len(det["projects"]) >= 1)
pd = [p for p in det["projects"] if p["id"] == PID][0]
check("drill-down shows memories + sources", pd["memories"] >= 1 and pd["source_records"] >= 1)
check("drill-down shows usage + feedback", pd["usage"].get("agent_recalls", 0) >= 3 and pd["feedback"].get("useful") == 1)
check("drill-down includes top recalled", len(pd["top_recalled"]) >= 1)
st, _ = call("GET", f"/v1/admin/orgs/{OID}", None, SESS)
check("customer blocked from admin drill-down", st == 403)

print("== empty project onboarding (fresh org) ==")
_, e2 = call("POST", "/v1/signup", {"email": "empty@x.com"})
_, chk = call("GET", f"/v1/onboarding?project={e2['project']['id']}", None, e2["token"])
check("fresh org shows 3/8 done", chk["completed"] == 3, str(chk["completed"]))

print("== persistence: feedback + status + recall counts survive restart ==")
srv.shutdown()
import importlib
sys.modules.pop("api")
api2 = importlib.import_module("api")
check("feedback persisted", api2.ENT.feedback_summary(PID).get("useful") == 1)
check("customer status persisted", api2.ENT.customer_status(OID)["status"] == "trial")
check("recall counts persisted", api2.ENT.top_recalled(PID)[0]["count"] >= 3)

print(f"\n{PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
