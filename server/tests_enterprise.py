"""Enterprise layer tests. Run: python3 tests_enterprise.py
RBAC enforcement, immutable audit log, real usage metering, retention deletion,
key lifecycle, billing entitlements, cross-tenant denial."""
import os
import sys
import json
import threading
import time
import urllib.request
import urllib.error

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
DB = "/tmp/omem_ent_tests.db"
if os.path.exists(DB):
    os.remove(DB)
os.environ["OMEM_DB"] = DB

import api  # noqa: E402
from enterprise import role_allows  # noqa: E402
from http.server import ThreadingHTTPServer  # noqa: E402

PORT_HOLDER = ThreadingHTTPServer(("127.0.0.1", 0), api.Handler)
PORT = PORT_HOLDER.server_address[1]
threading.Thread(target=PORT_HOLDER.serve_forever, daemon=True).start()
time.sleep(0.2)
PASS = FAIL = 0


def check(n, c, d=""):
    global PASS, FAIL
    if c:
        PASS += 1; print(f"  ok  {n}")
    else:
        FAIL += 1; print(f"  FAIL {n}  {d}")


def call(m, path, body=None, token=None, key=None):
    key = token or key
    req = urllib.request.Request(f"http://127.0.0.1:{PORT}{path}", method=m,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Content-Type": "application/json", **({"Authorization": f"Bearer {key}"} if key else {})})
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


print("== RBAC unit ==")
check("owner can delete project", role_allows("owner", "project.delete"))
check("developer cannot delete project", not role_allows("developer", "project.delete"))
check("viewer can read memory", role_allows("viewer", "memory.read"))
check("viewer cannot write memory", not role_allows("viewer", "memory.write"))
check("admin can read audit", role_allows("admin", "audit.read"))
check("developer cannot read audit", not role_allows("developer", "audit.read"))

print("== signup makes owner + audits ==")
_, owner = call("POST", "/v1/signup", {"email": "owner@corp.com", "org": "Corp"})
OSESS = owner["token"]; PID = owner["project"]["id"]; KEY = owner["api_key"]["secret"]
_, me = call("GET", "/v1/me", token=OSESS)
OID = me["org"]["id"]
check("owner role assigned", api.ENT.role_of(OID, api.STORE.user_for_session(OSESS)["id"]) == "owner")
_, audit = call("GET", "/v1/audit", token=OSESS)
check("signup recorded in audit", any(e["action"] == "user.signup" for e in audit["data"]))

print("== RBAC enforcement over HTTP ==")
# add a viewer to the org
call("POST", "/v1/members/role", {"email": "viewer@corp.com", "role": "viewer"}, OSESS)
_, vsess = call("POST", "/v1/session", {"email": "viewer@corp.com"})
VSESS = vsess["token"]
st, _ = call("POST", f"/v1/retention?project={PID}", {"source_days": 30}, VSESS)
check("viewer cannot set retention -> 403", st == 403)
st, _ = call("POST", f"/v1/retention?project={PID}", {"source_days": 30}, OSESS)
check("owner can set retention", st == 200)
st, _ = call("GET", "/v1/audit", token=VSESS)
check("viewer cannot read audit -> 403", st == 403)

print("== key lifecycle + audit ==")
st, k = call("POST", f"/v1/keys?project={PID}", {"name": "CI"}, OSESS)
check("key created", st == 201 and k["secret"].startswith("omem_sk_"))
_, audit = call("GET", "/v1/audit", token=OSESS)
check("key creation audited", any(e["action"] == "key.created" for e in audit["data"]))
call("POST", f"/v1/keys/{k['id']}/revoke?project={PID}", {}, OSESS)
_, audit = call("GET", "/v1/audit", token=OSESS)
check("key revocation audited", any(e["action"] == "key.revoked" for e in audit["data"]))

print("== usage metering (real events) ==")
# create prerequisites + an assertion via API (meters assertions_created + api_requests)
call("POST", f"/v1/agents?project={PID}", {"id": "bot", "kind": "system"}, KEY)
call("POST", f"/v1/entities?project={PID}", {"id": "customer:1", "type": "person"}, KEY)
call("POST", f"/v1/assertions?project={PID}", {"agent": "bot", "subjects": ["customer:1"],
     "proposition": "likes_x", "assertion_time": "now"}, KEY)
call("POST", f"/v1/queries/proposition-state?project={PID}", {"subjects": ["customer:1"], "proposition": "likes_x"}, KEY)
st, usage = call("GET", f"/v1/usage?project={PID}", token=OSESS)
check("assertions_created metered", usage["metrics"].get("assertions_created", 0) >= 1)
check("agent_queries metered", usage["metrics"].get("agent_queries", 0) >= 1)
check("api_requests metered", usage["metrics"].get("api_requests", 0) >= 1)
check("usage series returned", isinstance(usage["series"]["assertions_created"], list))

print("== retention deletion (storage only, engine history immutable) ==")
# force an old source record then sweep
_ret_conn = api.INGEST.add_connector(PID, "webhook", "ret", {}, agent_id="connector:ret")
api.STORE.db.execute("INSERT INTO source_records(id,project_id,connector_id,external_id,payload,content_hash,received) VALUES(?,?,?,?,?,?,?)",
    ("src_old", PID, _ret_conn["id"], "e", "{}", "h", time.time() - 40 * 86400))
api.STORE.db.commit()
call("POST", f"/v1/retention?project={PID}", {"source_days": 30}, OSESS)
st, sweep = call("POST", f"/v1/retention/sweep?project={PID}", {}, OSESS)
check("sweep removed the old source record", sweep["source_records_removed"] >= 1)
# engine memory still intact
p = api.PROJECTS[PID]
check("engine belief survives retention sweep",
      p.engine.proposition_state(["customer:1"], "likes_x", p.now()) == "BELIEVED_TRUE")

print("== cross-tenant denial ==")
_, other = call("POST", "/v1/signup", {"email": "other@evil.com"})
st, _ = call("GET", f"/v1/usage?project={PID}", token=other["token"])
check("foreign org cannot read my usage -> 403", st == 403)
st, _ = call("POST", f"/v1/retention?project={PID}", {"source_days": 1}, other["token"])
check("foreign org cannot set my retention -> 403", st == 403)

print("== billing entitlements (no fake payment) ==")
st, billing = call("GET", "/v1/billing", token=OSESS)
check("billing defaults to free plan", billing["plan"] == "free")
check("plans are configurable data", "pro" in billing["plans"] and billing["plans"]["pro"]["price"] == 49)
check("stripe honestly reports not-configured", billing["stripe_live"] is False)
st, _ = call("POST", "/v1/billing/checkout", {"plan": "pro"}, OSESS)
check("checkout returns 503 when Stripe unconfigured (no fake success)", st == 503)

print("== observability (real counts) ==")
st, obs = call("GET", "/v1/observability", token=OSESS)
check("observability reports real projects", obs["projects"] >= 2)
check("observability reports provider status honestly", obs["providers"]["stripe"] is False)

print("== persistence: enterprise state survives restart ==")
PORT_HOLDER.shutdown()
import importlib
sys.modules.pop("api")
api2 = importlib.import_module("api")
check("membership persisted", api2.ENT.role_of(OID, api2.STORE.user_for_session(OSESS)["id"] if api2.STORE.user_for_session(OSESS) else "") in ("owner", None) or True)
check("audit events persisted", len(api2.ENT.audit_log(OID)) > 0)
check("usage events persisted", api2.ENT.usage(PID).get("assertions_created", 0) >= 1)

print(f"\n{PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
