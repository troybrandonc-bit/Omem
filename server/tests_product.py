"""Product-layer tests: webhook/document ingestion, entitlement enforcement,
operator admin console, data export. Run: python3 tests_product.py"""
import os
import sys
import json
import threading
import time
import urllib.request
import urllib.error

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
DB = "/tmp/omem_product_tests.db"
if os.path.exists(DB):
    os.remove(DB)
os.environ["OMEM_DB"] = DB
os.environ["OMEM_ADMIN_EMAILS"] = "founder@omem.dev"

import os as _os_seed
_os_seed.environ['OMEM_SEED_DEMO']='1'
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


_, acct = call("POST", "/v1/signup", {"email": "pilot@corp.com", "org": "PilotCo"})
KEY = acct["api_key"]["secret"]; PID = acct["project"]["id"]; SESS = acct["token"]

print("== webhook ingestion (push -> pipeline -> engine) ==")
st, wh = call("POST", f"/v1/connectors?project={PID}",
              {"kind": "webhook", "name": "CRM webhook", "agent_id": "connector:crm", "authority": 0.85}, KEY)
check("webhook connector created", st == 201, str(wh))
CID = wh["id"]
st, r = call("POST", f"/v1/webhooks/{CID}",
             {"id": "evt-1", "customer": "ada", "subject": "crm", "body": "customer wants to upgrade"}, KEY)
check("webhook delivery accepted 202", st == 202 and r["accepted"])
call("POST", f"/v1/ingest/process?project={PID}", {}, KEY)
st, rec = call("POST", f"/v1/recall?project={PID}", {"about": "customer:ada"}, KEY)
check("webhook payload became memory", rec["count"] >= 1 and
      any(m["proposition"] == "intends_to_upgrade" for m in rec["memories"]), str(rec))

print("== webhook dedup (same external id twice) ==")
before = api.INGEST.stats(PID)["sources"]
call("POST", f"/v1/webhooks/{CID}", {"id": "evt-1", "customer": "ada", "subject": "crm", "body": "customer wants to upgrade"}, KEY)
check("duplicate delivery not re-ingested", api.INGEST.stats(PID)["sources"] == before)

print("== document upload ==")
st, d = call("POST", f"/v1/documents?project={PID}",
             {"filename": "meeting-notes.txt", "customer": "grace",
              "text": "Grace said they prefer email and are considering annual billing."}, KEY)
check("document upload 201 + processed", st == 201 and d["assertions"] >= 1, str(d))
st, rec = call("POST", f"/v1/recall?project={PID}", {"about": "customer:grace"}, KEY)
check("document facts recalled", rec["count"] >= 2, str(rec["count"]))
st, d2 = call("POST", f"/v1/documents?project={PID}", {"filename": "n2.txt", "text": "no facts here at all"}, KEY)
check("no-fact document completes (not error)", st == 201 and d2["assertions"] == 0)

print("== provenance traces back to the uploaded source ==")
aid = rec["memories"][0]["assertion"]
st, src = call("GET", f"/v1/assertions/{aid}/source?project={PID}", None, KEY)
check("assertion -> original source record", st == 200 and "grace" in json.dumps(src).lower())

print("== entitlement enforcement (real quotas from PLANS) ==")
# shrink the free plan for the test, then restore
orig = api.PLANS["free"]["quota_memories"]
api.PLANS["free"]["quota_memories"] = api.ENT.usage(PID).get("assertions_created", 0)  # already at quota
st, r = call("POST", f"/v1/learn?project={PID}", {"agent": "a", "text": "customer wants to cancel", "about": "customer:x"}, KEY)
check("learn blocked at quota -> 402", st == 402 and "quota" in r["error"]["message"].lower(), str(st))
call("POST", f"/v1/agents?project={PID}", {"id": "qa", "kind": "system"}, KEY)
st, r = call("POST", f"/v1/assertions?project={PID}",
             {"agent": "qa", "subjects": ["customer:ada"], "proposition": "x", "assertion_time": "now"}, KEY)
check("manual assertion blocked at quota -> 402", st == 402)
ev = api.ENT.billing_events(acct["org"]["id"] if "org" in acct else api.STORE.org_for_user(api.STORE.user_for_session(SESS)["id"])["id"])
check("quota_exceeded billing event recorded", any(e["kind"] == "quota_exceeded" for e in ev))
api.PLANS["free"]["quota_memories"] = orig
st, r = call("POST", f"/v1/learn?project={PID}", {"agent": "a", "text": "customer wants to cancel", "about": "customer:x"}, KEY)
check("learn works again under quota", st in (200, 201))

print("== source quota ==")
orig_s = api.PLANS["free"]["quota_sources"]
api.PLANS["free"]["quota_sources"] = 1  # already have 2 connectors
st, r = call("POST", f"/v1/connectors?project={PID}", {"kind": "webhook", "name": "Another"}, KEY)
check("connector blocked at source quota -> 402", st == 402)
api.PLANS["free"]["quota_sources"] = orig_s

print("== operator admin console ==")
st, _ = call("GET", "/v1/admin/metrics", None, SESS)
check("non-operator blocked -> 403", st == 403)
_, facct = call("POST", "/v1/signup", {"email": "founder@omem.dev", "org": "OMEM"})
st, m = call("GET", "/v1/admin/metrics", None, facct["token"])
check("operator sees metrics", st == 200 and m["organizations"] >= 2)
check("admin counts are real", m["assertions_created"] >= 3 and m["connected_sources"] >= 2)
check("revenue honestly labeled estimate", "no Stripe verification" in m["revenue_note"])
check("mrr is 0 with no active subs", m["estimated_mrr"] == 0)
st, orgs = call("GET", "/v1/admin/orgs", None, facct["token"])
check("org list with plan+activity", st == 200 and
      any(o["name"] == "PilotCo" and o["plan"] == "free" and o["usage_total"] > 0 for o in orgs["data"]))

print("== data export ==")
st, ex = call("GET", f"/v1/export/memories?project={PID}", None, KEY)
check("memory export includes state+provenance", st == 200 and len(ex["memories"]) >= 3 and
      all("state" in m and "provenance" in m for m in ex["memories"]))
st, ea = call("GET", "/v1/export/audit", None, SESS)
check("audit export (owner)", st == 200 and len(ea["events"]) >= 1)
_, aud = call("GET", "/v1/audit", None, SESS)
check("export itself audited", any(e["action"] == "export.memories" for e in aud["data"]))

print("== demo project exempt from quotas ==")
api.PLANS["free"]["quota_memories"] = 0
st, _ = call("POST", "/v1/queries/proposition-state?project=demo",
             {"subjects": ["customer:alice"], "proposition": "prefers_email_over_phone"}, SESS)
check("demo readable regardless of quota", st == 200)
api.PLANS["free"]["quota_memories"] = orig

print("== connector removal (source material only; memories are immutable) ==")
# lift the source quota for this section (earlier checks deliberately exhausted it)
api.ENT.set_billing(api.STORE.org_for_user(api.STORE.user_for_session(SESS)["id"])["id"], plan="business")
st, _dcn = call("POST", f"/v1/connectors?project={PID}",
                {"kind": "webhook", "name": "Removable"}, KEY)
_dcid = _dcn["id"]
call("POST", f"/v1/webhooks/{_dcid}", {"id": "rm1", "customer": "removeme",
                                       "subject": "s", "body": "prefer email"}, KEY)
call("POST", f"/v1/ingest/process?project={PID}", {}, KEY)
_, _before = call("POST", f"/v1/recall?project={PID}", {"about": "customer:removeme"}, KEY)
check("memory created before removal", _before["count"] >= 1)

st, _del = call("DELETE", f"/v1/connectors/{_dcid}?project={PID}", None, KEY)
check("delete returns 200 with counts", st == 200 and _del["removed"]["connectors"] == 1)
check("source records removed", _del["removed"]["source_records"] >= 1)
check("jobs removed", _del["removed"]["ingest_jobs"] >= 1)
_, _list = call("GET", f"/v1/connectors?project={PID}", None, KEY)
check("connector gone from the list", all(c["id"] != _dcid for c in _list["data"]))
_, _after = call("POST", f"/v1/recall?project={PID}", {"about": "customer:removeme"}, KEY)
check("memories survive removal (immutable engine history)",
      _after["count"] == _before["count"])
st, _ = call("DELETE", f"/v1/connectors/{_dcid}?project={PID}", None, KEY)
check("removing twice -> 404", st == 404)

# cross-tenant: another project cannot delete this project's connector
_, _other = call("POST", "/v1/signup", {"email": "rmthief@x.com"})
st, _ = call("DELETE", f"/v1/connectors/{_dcid}?project={_other['project']['id']}",
             None, _other["api_key"]["secret"])
check("foreign project cannot delete a connector", st in (403, 404))

print("== stale errors can be dismissed ==")
st, _e2 = call("POST", f"/v1/connectors?project={PID}", {"kind": "webhook", "name": "Erroring"}, KEY)
# a job in a FAILING state surfaces its error (completed ones deliberately do not)
api.STORE.db.execute(
    "INSERT INTO ingest_jobs(project_id,connector_id,source_record_id,state,last_error,created,updated) "
    "VALUES(?,?,?,'retrying',?,?,?)",
    (PID, _e2["id"], "s-old", "HTTPError: HTTP Error 401: Unauthorized", time.time(), time.time()))
api.STORE.db.commit()
_, _d1 = call("GET", f"/v1/connectors/{_e2['id']}/detail?project={PID}", None, KEY)
check("a live failure is visible", _d1["last_error"] is not None)
st, _ = call("POST", f"/v1/connectors/{_e2['id']}/clear-errors?project={PID}", {}, KEY)
_, _d2 = call("GET", f"/v1/connectors/{_e2['id']}/detail?project={PID}", None, KEY)
check("dismiss clears the stale error", _d2["last_error"] is None, str(_d2["last_error"]))

# regression: previously only completed/cancelled jobs were cleared, so a
# dead-lettered 401 stayed on screen forever
api.STORE.db.execute(
    "INSERT INTO ingest_jobs(project_id,connector_id,source_record_id,state,last_error,created,updated) "
    "VALUES(?,?,?,'dead_lettered',?,?,?)",
    (PID, _e2["id"], "s-dead", "HTTPError: HTTP Error 401: Unauthorized", time.time(), time.time()))
api.STORE.db.commit()
_, _d3 = call("GET", f"/v1/connectors/{_e2['id']}/detail?project={PID}", None, KEY)
check("dead-lettered error is visible", _d3["last_error"] is not None)
call("POST", f"/v1/connectors/{_e2['id']}/clear-errors?project={PID}", {}, KEY)
_, _d4 = call("GET", f"/v1/connectors/{_e2['id']}/detail?project={PID}", None, KEY)
check("dead-lettered error is cleared too", _d4["last_error"] is None, str(_d4["last_error"]))

print("== historical errors do not haunt the connector card ==")
_hc = call("POST", f"/v1/connectors?project={PID}", {"kind": "webhook", "name": "Historical"}, KEY)[1]
_now = time.time()
api.STORE.db.execute(
    "INSERT INTO ingest_jobs(project_id,connector_id,source_record_id,state,last_error,created,updated) "
    "VALUES(?,?,?,'completed',?,?,?)",
    (PID, _hc["id"], "hist1",
     "OperationalError: cannot commit - no transaction is active", _now, _now))
api.STORE.db.commit()
_, _hd = call("GET", f"/v1/connectors/{_hc['id']}/detail?project={PID}", None, KEY)
check("error on a COMPLETED job is not shown", _hd["last_error"] is None, str(_hd["last_error"]))

api.STORE.db.execute(
    "INSERT INTO ingest_jobs(project_id,connector_id,source_record_id,state,last_error,created,updated) "
    "VALUES(?,?,?,'dead_lettered',?,?,?)",
    (PID, _hc["id"], "hist2", "Genuine live failure", _now + 1, _now + 1))
api.STORE.db.commit()
_, _hd2 = call("GET", f"/v1/connectors/{_hc['id']}/detail?project={PID}", None, KEY)
check("a genuinely failing job IS shown", _hd2["last_error"] == "Genuine live failure")

call("POST", f"/v1/jobs/retry-dead?project={PID}", {}, KEY)
_, _hd3 = call("GET", f"/v1/connectors/{_hc['id']}/detail?project={PID}", None, KEY)
check("retrying a dead letter clears the surfaced error", _hd3["last_error"] is None, str(_hd3["last_error"]))

print("== bulk removal of duplicate connectors ==")
for _i in range(4):
    call("POST", f"/v1/connectors?project={PID}", {"kind": "gmail", "name": f"Dup {_i}"}, KEY)
_, _pre = call("GET", f"/v1/connectors?project={PID}", None, KEY)
_gmails = [c for c in _pre["data"] if c["kind"] == "gmail"]
check("duplicate gmail connectors exist", len(_gmails) >= 4, str(len(_gmails)))
st, _bulk = call("POST", f"/v1/connectors/bulk-delete?project={PID}", {"kind": "gmail"}, KEY)
check("bulk delete removes them all", st == 200 and _bulk["deleted"] >= 4, str(_bulk))
_, _post = call("GET", f"/v1/connectors?project={PID}", None, KEY)
check("no gmail connectors remain", not any(c["kind"] == "gmail" for c in _post["data"]))
check("other kinds untouched", any(c["kind"] == "webhook" for c in _post["data"]))

print("== persistence: push items + billing events survive restart ==")
srv.shutdown()
import importlib
sys.modules.pop("api")
api2 = importlib.import_module("api")
p = api2.PROJECTS.get(PID)
check("webhook-derived memory replayed", p is not None and
      p.engine.proposition_state(["customer:ada"], "intends_to_upgrade", p.now()) == "BELIEVED_TRUE")
check("push items persisted", api2.STORE.db.execute("SELECT COUNT(*) c FROM push_items").fetchone()["c"] >= 2)

print(f"\n{PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
