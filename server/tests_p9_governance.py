"""P9.5 data governance / erasure. Run: python3 tests_p9_governance.py

Verifies the tenant-grain right-to-erasure capability without changing
intra-tenant memory semantics:
- ?mode=erase hard-removes ALL project-scoped tables + connector OAuth secrets
  + the op-log + the project row + in-memory state;
- a cold-boot reboot cannot resurrect an erased project (op-log gone);
- erasure is owner-only (a bound API key cannot erase);
- one tenant's erasure does not touch another tenant (isolation during deletion);
- the org-level audit record of the erasure survives;
- the DEFAULT delete (soft) still preserves memory history (unchanged behavior).
"""
import json
import os
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
DB = "/tmp/omem_p95_gov.db"
for p in (DB, DB + "-wal", DB + "-shm"):
    if os.path.exists(p):
        os.remove(p)
os.environ["OMEM_DB"] = DB
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


def setup_tenant(email):
    a = call("POST", "/v1/signup", {"email": email})[1]
    sess, k, pid = a["token"], a["api_key"]["secret"], a["project"]["id"]
    oid = a["org"]["id"]
    call("POST", f"/v1/identity?project={pid}",
         {"company_name": "x", "domains": ["k.com"], "emails": [email]}, k)
    call("POST", f"/v1/observe?project={pid}",
         {"agent": "agent:alice", "interaction": {"text": "We have decided to renew the annual contract.",
          "speaker": "x@acme.com", "audience": email}}, k)
    call("POST", f"/v1/keys?project={pid}", {"name": "bob", "agent_id": "agent:bob"}, k)
    # a connector + encrypted oauth cred to prove secret erasure
    api.STORE.db.execute("INSERT INTO connectors(id,project_id,kind,name,config,agent_id,status,created) "
                         "VALUES(?,?,?,?,?,?,?,?)", (f"conn_{pid}", pid, "gmail", "t", "{}", "agent:s", "active", time.time()))
    api.STORE.db.execute("INSERT INTO oauth_creds(connector_id,provider,access_token,refresh_token,expires,scope,account,connected) "
                         "VALUES(?,?,?,?,?,?,?,?)", (f"conn_{pid}", "google", "enc_a", "enc_r", 0, "s", "a@b.io", time.time()))
    api.STORE.db.commit()
    return {"sess": sess, "key": k, "pid": pid, "oid": oid}


def proj_footprint(pid):
    d = api.STORE.db
    tables = ["ops", "keys", "memory_scopes", "candidate_subjects", "connectors"]
    total = sum(d.execute(f"SELECT COUNT(*) c FROM {t} WHERE project_id=?", (pid,)).fetchone()["c"] for t in tables)
    total += d.execute("SELECT COUNT(*) c FROM oauth_creds WHERE connector_id=?", (f"conn_{pid}",)).fetchone()["c"]
    total += d.execute("SELECT COUNT(*) c FROM projects WHERE id=?", (pid,)).fetchone()["c"]
    return total


print("== complete tenant erasure ==")
A = setup_tenant("a@k.com")
before = proj_footprint(A["pid"])
check("tenant A has data before erasure", before > 0, str(before))
st, r = call("DELETE", f"/v1/projects/{A['pid']}?mode=erase", None, A["sess"])
check("erase returns 200 + erased:true", st == 200 and r.get("erased") is True, str((st, r.get("erased"))))
after = proj_footprint(A["pid"])
check("all project-scoped data + oauth secrets + project row removed", after == 0, f"footprint={after}")
check("oauth secrets specifically erased",
      api.STORE.db.execute("SELECT COUNT(*) c FROM oauth_creds WHERE connector_id=?", (f"conn_{A['pid']}",)).fetchone()["c"] == 0)
check("op-log erased (no replay source)",
      api.STORE.db.execute("SELECT COUNT(*) c FROM ops WHERE project_id=?", (A["pid"],)).fetchone()["c"] == 0)
check("in-memory project state dropped", A["pid"] not in api.PROJECTS)

print("== reboot cannot resurrect an erased tenant ==")
runner = os.path.join(HERE, "_gov_boot.py")
with open(runner, "w") as f:
    f.write(f"import os,sys;sys.path.insert(0,{HERE!r})\nimport api,json\n"
            f"print(json.dumps({{'has_pid': {A['pid']!r} in api.PROJECTS}}))\n")
o = subprocess.run([sys.executable, runner], env={**os.environ}, capture_output=True, text=True, timeout=60)
os.remove(runner)
try:
    boot = json.loads(o.stdout.strip().splitlines()[-1])
    check("erased project absent after cold-boot replay", boot["has_pid"] is False, o.stdout + o.stderr)
except Exception as e:
    check("cold-boot resurrection check", False, f"{e}: {o.stdout} {o.stderr}")

print("== org-level audit of the erasure survives ==")
# the erasure was logged at org level (project_id=None), so it persists
erased_audits = api.STORE.db.execute(
    "SELECT COUNT(*) c FROM audit_events WHERE org_id=? AND action='project.erased'", (A["oid"],)).fetchone()["c"]
check("org-level 'project.erased' audit record persists", erased_audits >= 1, str(erased_audits))

print("== erasure is owner-only ==")
B = setup_tenant("b@k.com")
check("bound API key cannot erase (403)",
      call("DELETE", f"/v1/projects/{B['pid']}?mode=erase", None, B["key"])[0] == 403)

print("== cross-tenant isolation during deletion ==")
C = setup_tenant("c@k.com")
# B's owner cannot erase C
check("cross-tenant erase blocked (403)",
      call("DELETE", f"/v1/projects/{C['pid']}?mode=erase", None, B["sess"])[0] == 403)
# erasing B leaves C fully intact
cbefore = proj_footprint(C["pid"])
call("DELETE", f"/v1/projects/{B['pid']}?mode=erase", None, B["sess"])
cafter = proj_footprint(C["pid"])
check("erasing one tenant does not touch another", cbefore == cafter and cafter > 0, f"{cbefore}->{cafter}")
check("untouched tenant still serves recall",
      call("POST", f"/v1/recall?project={C['pid']}", {"agent": "agent:alice", "context": "renew"}, C["key"])[0] == 200)

print("== default (soft) delete preserves memory history (unchanged) ==")
D = setup_tenant("d@k.com")
ops_before = api.STORE.db.execute("SELECT COUNT(*) c FROM ops WHERE project_id=?", (D["pid"],)).fetchone()["c"]
st, r = call("DELETE", f"/v1/projects/{D['pid']}", None, D["sess"])  # no mode=erase
check("soft delete returns deleted:true", st == 200 and r.get("deleted") is True, str((st, r)))
ops_after = api.STORE.db.execute("SELECT COUNT(*) c FROM ops WHERE project_id=?", (D["pid"],)).fetchone()["c"]
check("soft delete retains op-log/memory history (unchanged semantics)", ops_after == ops_before, f"{ops_before}->{ops_after}")

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
