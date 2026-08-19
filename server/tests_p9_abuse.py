"""P9.4 abuse & availability hardening. Run: python3 tests_p9_abuse.py

Verifies the guarantees P9.4 introduces without weakening the security model:
- per-tenant data-endpoint rate limit returns 429 after the burst;
- the limit is per-(project,key): one key hitting the limit does NOT block a
  different tenant/key;
- request bodies over the cap are rejected 413 (not silently truncated);
- observe/learn text over the per-field cap is rejected 413;
- legitimate normal-sized requests still succeed;
- rate limiting does not apply to public/health routes.
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
DB = "/tmp/omem_p94_abuse.db"
for p in (DB, DB + "-wal", DB + "-shm"):
    if os.path.exists(p):
        os.remove(p)
os.environ["OMEM_DB"] = DB
# deterministic small limits for the test
os.environ["OMEM_TENANT_RL_BURST"] = "6"
os.environ["OMEM_TENANT_RL_RPS"] = "1"
os.environ["OMEM_MAX_BODY_BYTES"] = "1000000"
os.environ["OMEM_MAX_TEXT_CHARS"] = "100000"
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


def call(m, path, body=None, key=None, raw=None):
    data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
    r = urllib.request.Request(f"{BASE}{path}", method=m, data=data,
        headers={"Content-Type": "application/json",
                 **({"Authorization": f"Bearer {key}"} if key else {})})
    try:
        with urllib.request.urlopen(r, timeout=20) as resp:
            ct = resp.headers.get("content-type", "")
            return resp.status, (json.loads(resp.read() or b"{}") if "json" in ct else {})
    except urllib.error.HTTPError as e:
        ct = e.headers.get("content-type", "")
        return e.code, (json.loads(e.read() or b"{}") if "json" in ct else {})


# two independent tenants
A = call("POST", "/v1/signup", {"email": "a@k.com"})[1]
AK, APID = A["api_key"]["secret"], A["project"]["id"]
B = call("POST", "/v1/signup", {"email": "b@k.com"})[1]
BK, BPID = B["api_key"]["secret"], B["project"]["id"]
for pid, k in [(APID, AK), (BPID, BK)]:
    call("POST", f"/v1/identity?project={pid}",
         {"company_name": "x", "domains": ["k.com"], "emails": ["a@k.com"]}, k)

print("== per-tenant rate limit ==")
codes = [call("POST", f"/v1/recall?project={APID}", {"agent": "agent:s", "context": "x"}, AK)[0]
         for _ in range(14)]
check("burst then 429 (rate limit active)", 429 in codes, str(codes))
check("burst allows ~OMEM_TENANT_RL_BURST before 429",
      2 <= codes.index(429) <= 8, f"first 429 at {codes.index(429) if 429 in codes else 'never'}")

print("== rate limit is per-tenant, not global ==")
# tenant A is now throttled; tenant B (different key+project) must still work
stB, _ = call("POST", f"/v1/recall?project={BPID}", {"agent": "agent:s", "context": "x"}, BK)
check("a throttled tenant does not block a different tenant", stB == 200, str(stB))

print("== body-size cap ==")
time.sleep(7)  # let A's bucket refill so we test the body cap, not the rate limit
big = json.dumps({"agent": "agent:s", "interaction": {"text": "y" * 1_100_000}}).encode()
st, _ = call("POST", f"/v1/observe?project={APID}", raw=big, key=AK)
check("body over 1MB rejected 413 (not silently truncated)", st == 413, str(st))

print("== per-field text cap ==")
time.sleep(2)
st, r = call("POST", f"/v1/observe?project={APID}",
             {"agent": "agent:s", "interaction": {"text": "z" * 200_000, "speaker": "a@b.io"}}, AK)
check("observe text over cap rejected 413", st == 413, str(st))
time.sleep(2)
st, r = call("POST", f"/v1/learn?project={APID}", {"agent": "agent:s", "text": "w" * 200_000}, AK)
check("learn text over cap rejected 413", st == 413, str(st))

print("== legitimate usage still works ==")
time.sleep(2)
st, _ = call("POST", f"/v1/observe?project={APID}",
             {"agent": "agent:s", "interaction": {"text": "We renewed the annual contract.",
              "speaker": "x@acme.com", "audience": "a@k.com"}}, AK)
check("normal observe still succeeds (201)", st == 201, str(st))
time.sleep(1)
st, _ = call("POST", f"/v1/recall?project={APID}", {"agent": "agent:s", "context": "renewed"}, AK)
check("normal recall still succeeds (200)", st == 200, str(st))

print("== public/health route not rate-limited ==")
oks = sum(1 for _ in range(20) if call("GET", "/v1/health")[0] == 200)
check("health endpoint not throttled by tenant limiter", oks == 20, f"{oks}/20")

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
