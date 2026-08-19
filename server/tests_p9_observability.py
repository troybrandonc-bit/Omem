"""P9.6 operational observability. Run: python3 tests_p9_observability.py

Verifies operators can actually see system state:
- /v1/health is a REAL readiness probe (db reachability + backend + status),
  not a static string; reports 'degraded' when backups are failing;
- /v1/observability exposes runtime metrics that actually move: request count,
  rate-limit rejections (429), auth failures (401), authz denials (403), latency;
- database backend + reachability are surfaced;
- rate-limit config + rejection count are surfaced;
- projection drift is surfaced.
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
DB = "/tmp/omem_p96_obs.db"
for p in (DB, DB + "-wal", DB + "-shm"):
    if os.path.exists(p):
        os.remove(p)
os.environ["OMEM_DB"] = DB
os.environ["OMEM_TENANT_RL_BURST"] = "3"
os.environ["OMEM_TENANT_RL_RPS"] = "1"
os.environ.pop("OMEM_LLM_API_KEY", None)

import api  # noqa: E402
from http.server import ThreadingHTTPServer  # noqa: E402

PASS = FAIL = 0


def check(n, c, d=""):
    global PASS, FAIL
    if c:
        PASS += 1; print(f"  ok  {n}")
    else:
        FAIL += 1; print(f"  FAIL {n}  {d}")


srv = ThreadingHTTPServer(("127.0.0.1", 0), api.Handler)
PORT = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()
time.sleep(0.2)
BASE = f"http://127.0.0.1:{PORT}"


def call(m, path, body=None, key=None):
    r = urllib.request.Request(f"{BASE}{path}", method=m,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Content-Type": "application/json",
                 **({"Authorization": f"Bearer {key}"} if key else {})})
    try:
        with urllib.request.urlopen(r, timeout=20) as resp:
            return resp.status, json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


print("== /v1/health is a real readiness probe ==")
st, h = call("GET", "/v1/health")
check("health returns 200 when ready", st == 200 and h.get("ready") is True, str((st, h.get("ready"))))
check("health reports db reachability + backend",
      h["checks"]["database"]["ok"] is True and "backend" in h["checks"]["database"])
check("health is not the old static stub", "checks" in h and "uptime_seconds" in h)

print("== runtime metrics move with traffic ==")
acct = call("POST", "/v1/signup", {"email": "o@k.com"})[1]
SESS, K, PID = acct["token"], acct["api_key"]["secret"], acct["project"]["id"]
call("POST", f"/v1/identity?project={PID}",
     {"company_name": "K", "domains": ["k.com"], "emails": ["o@k.com"]}, K)
# an unauthenticated call -> 401 (auth failure)
call("POST", f"/v1/recall?project={PID}", {"context": "x"})
_, o1 = call("GET", "/v1/observability", None, SESS)
check("requests_total is counting", o1["runtime"]["requests_total"] > 0, str(o1["runtime"]))
check("auth_failures_total captured the 401", o1["runtime"]["auth_failures_total"] >= 1,
      str(o1["runtime"]["auth_failures_total"]))
check("latency is measured (mean >= 0, max > 0)",
      o1["runtime"]["latency_ms_max"] > 0)

print("== rate-limit rejections are observable ==")
codes = [call("POST", f"/v1/recall?project={PID}", {"agent": "agent:s", "context": "x"}, K)[0]
         for _ in range(10)]
check("429s were triggered (abuse simulated)", 429 in codes, str(codes))
_, o2 = call("GET", "/v1/observability", None, SESS)
check("rate_limited_total reflects the 429s", o2["rate_limit"]["rate_limited_total"] >= 1,
      str(o2["rate_limit"]))
check("rate-limit config is surfaced (burst + rps)",
      "tenant_burst" in o2["rate_limit"] and "tenant_rps" in o2["rate_limit"])

print("== database health surfaced ==")
check("observability reports db backend + reachable",
      o2["database"]["reachable"] is True and "backend" in o2["database"])

print("== degraded health when backups fail (db still ok) ==")
api.BACKUPS.db.execute("INSERT INTO backup_runs(started,status,kind) VALUES(?,?,?)",
                       (time.time(), "failed", "sqlite_backup"))
api.BACKUPS.db.commit()
st, h2 = call("GET", "/v1/health")
check("health degrades (not fails) on backup failure",
      st == 200 and h2["status"] == "degraded" and h2["ready"] is True, str((st, h2.get("status"))))
check("backup check reflects failure", h2["checks"]["backups"]["ok"] is False)

print("== projection drift surfaced in observability ==")
# corrupt candidate index then reconcile -> drift recorded
p = api.PROJECTS[PID]
api.STORE.db.execute("DELETE FROM candidate_subjects WHERE project_id=?", (PID,))
api.STORE.db.commit()
api._reconcile_projections(p)
_, o3 = call("GET", "/v1/observability", None, SESS)
check("projection_drift is surfaced in observability", "projection_drift" in o3)

print("== engine integrity ==")
import hashlib
h = {f: hashlib.sha256(open(os.path.join(HERE, "omem_engine", f), "rb").read()).hexdigest()
     for f in sorted(os.listdir(os.path.join(HERE, "omem_engine"))) if f.endswith(".py")}
baseline = {}
for line in open(os.path.join(HERE, "omem_engine", "ENGINE_HASHES.txt"),
                 encoding="utf-8"):
    if not line.strip() or line.startswith('#'):
        continue
    hsh, path = line.split()
    baseline[os.path.basename(path)] = hsh
check("frozen engine byte-identical", all(baseline.get(f) == v for f, v in h.items()))

srv.shutdown()
print(f"\n{PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
