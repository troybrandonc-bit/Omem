"""P9.7 enterprise identity readiness. Run: python3 tests_p9_identity.py

Verifies the one justified hardening (keys now honor their stored RBAC role)
plus the existing identity-lifecycle invariants that must not regress:
- a 'viewer' key is genuinely read-only (reads ok, writes 403);
- 'developer'/default keys keep full write access (backward compatible);
- role is stored and returned on key creation;
- agent-binding (P8) still enforced independently of role;
- revoked and expired keys/sessions stop working;
- viewer read-only enforcement does not weaken cross-tenant/cross-agent isolation.
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
DB = "/tmp/omem_p97_id.db"
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


acct = call("POST", "/v1/signup", {"email": "id@k.com"})[1]
K, PID = acct["api_key"]["secret"], acct["project"]["id"]
call("POST", f"/v1/identity?project={PID}",
     {"company_name": "K", "domains": ["k.com"], "emails": ["id@k.com"]}, K)
call("POST", f"/v1/observe?project={PID}",
     {"agent": "agent:s", "interaction": {"text": "We renewed the annual contract.",
      "speaker": "x@acme.com", "audience": "id@k.com"}}, K)

print("== key role is stored + returned ==")
vk = call("POST", f"/v1/keys?project={PID}", {"name": "v", "role": "viewer"}, K)[1]
check("created key echoes its role", vk.get("role") == "viewer", str(vk.get("role")))
VIEW = vk["secret"]

print("== viewer key is read-only ==")
check("viewer can recall (read)",
      call("POST", f"/v1/recall?project={PID}", {"agent": "agent:s", "context": "renewed"}, VIEW)[0] == 200)
check("viewer can read assertions",
      call("GET", f"/v1/assertions?project={PID}", None, VIEW)[0] == 200)
check("viewer CANNOT observe (write) -> 403",
      call("POST", f"/v1/observe?project={PID}",
           {"agent": "agent:s", "interaction": {"text": "x", "speaker": "a@b.io"}}, VIEW)[0] == 403)
check("viewer CANNOT learn (write) -> 403",
      call("POST", f"/v1/learn?project={PID}", {"agent": "agent:s", "text": "y"}, VIEW)[0] == 403)
check("viewer CANNOT declare-contradiction (write) -> 403",
      call("POST", f"/v1/declare-contradiction?project={PID}",
           {"token_a": "a", "token_b": "b"}, VIEW)[0] == 403)

print("== developer/default keys keep write access (backward compatible) ==")
check("default (no role) key still writes",
      call("POST", f"/v1/observe?project={PID}",
           {"agent": "agent:s", "interaction": {"text": "Another fact.", "speaker": "a@b.io",
            "audience": "id@k.com"}}, K)[0] in (200, 201))
dev = call("POST", f"/v1/keys?project={PID}", {"name": "d", "role": "developer"}, K)[1]["secret"]
check("explicit developer key writes",
      call("POST", f"/v1/observe?project={PID}",
           {"agent": "agent:s", "interaction": {"text": "Dev fact.", "speaker": "a@b.io",
            "audience": "id@k.com"}}, dev)[0] in (200, 201))

print("== agent-binding (P8) still enforced independently of role ==")
bound = call("POST", f"/v1/keys?project={PID}", {"name": "b", "agent_id": "agent:bob"}, K)[1]["secret"]
check("bound key forging another agent still 403",
      call("POST", f"/v1/recall?project={PID}", {"agent": "agent:alice", "context": "x"}, bound)[0] == 403)

print("== identity lifecycle: revoke + expiry still enforced ==")
rk = call("POST", f"/v1/keys?project={PID}", {"name": "r"}, K)[1]
call("POST", f"/v1/keys/{rk['id']}/revoke?project={PID}", {}, K)
check("revoked key -> 401",
      call("POST", f"/v1/recall?project={PID}", {"context": "x"}, rk["secret"])[0] == 401)
# expired key: set expires in the past directly
ek = call("POST", f"/v1/keys?project={PID}", {"name": "e"}, K)[1]
api.STORE.db.execute("UPDATE keys SET expires=? WHERE id=?", (time.time() - 10, ek["id"]))
api.STORE.db.commit()
check("expired key -> 401",
      call("POST", f"/v1/recall?project={PID}", {"context": "x"}, ek["secret"])[0] == 401)

print("== read-only enforcement does not weaken isolation ==")
B = call("POST", "/v1/signup", {"email": "b2@k.com"})[1]
BK, BPID = B["api_key"]["secret"], B["project"]["id"]
# a viewer key from tenant A cannot read tenant B
check("viewer key cross-tenant still blocked (403)",
      call("POST", f"/v1/recall?project={BPID}", {"context": "x"}, VIEW)[0] == 403)

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
