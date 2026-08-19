"""Cross-agent memory: sharing works and isolation holds. Locks in the behavior
that (1) remember(scope=...) controls visibility, (2) private stays private,
(3) org/team sharing is visible to the right agents only, (4) explicit share
promotes scope, and (5) agent-bound keys are secure by default (no explicit
viewer needed, and cannot impersonate another agent)."""
import os, sys, json, threading, time, urllib.request, urllib.error

os.chdir(os.path.dirname(__file__))
for f in ("data/omem.db", "data/omem.db-shm", "data/omem.db-wal"):
    try: os.remove(f)
    except OSError: pass

import api
from http.server import ThreadingHTTPServer
srv = ThreadingHTTPServer(("127.0.0.1", 0), api.Handler)
PORT = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()
time.sleep(0.5)
BASE = f"http://127.0.0.1:{PORT}"

def call(m, p, b=None, k=None):
    d = json.dumps(b).encode() if b is not None else None
    h = {"Content-Type": "application/json"}
    if k: h["Authorization"] = f"Bearer {k}"
    r = urllib.request.Request(BASE + p, data=d, method=m, headers=h)
    try:
        with urllib.request.urlopen(r, timeout=5) as x:
            return x.status, json.loads(x.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")

passed = failed = 0
def check(n, c, d=""):
    global passed, failed
    passed += bool(c); failed += (not c)
    print(("  ok   " if c else "  FAIL ") + n + ("" if c else f"  <<< {d}"))

_, su = call("POST", "/v1/signup", {"email": "xagent@corp.com", "org": "XCo"})
TOK = su["session_token"] if "session_token" in su else su.get("token")
PID = su["project"]["id"] if isinstance(su.get("project"), dict) else su.get("project_id")
_, keyA = call("POST", f"/v1/keys?project={PID}", {"name": "kA"}, TOK)
KEY = keyA["api_key"]["secret"] if "api_key" in keyA else (keyA.get("secret") or keyA.get("key"))

sys.path.insert(0, os.path.join("..", "sdk", "python"))
from omem import Memory
mem = Memory(api_key=KEY, base_url=BASE, project=PID)

A, B, C = "agent-a", "agent-b", "agent-c"

print("== remember(scope=agent:...) keeps memory private ==")
mem.remember(agent=A, about="acme", claim="secret_deal=1", scope=f"agent:{A}")
_, rb = call("POST", f"/v1/recall?project={PID}", {"about": "acme", "agent": B}, KEY)
check("B cannot see A's private memory", rb.get("count", 0) == 0, rb)
_, ra = call("POST", f"/v1/recall?project={PID}", {"about": "acme", "agent": A}, KEY)
check("A sees own private memory", ra.get("count", 0) == 1, ra)

print("== org scope is visible cross-agent ==")
mem.remember(agent=A, about="beta", claim="org_fact=1", scope="org")
_, rbo = call("POST", f"/v1/recall?project={PID}", {"about": "beta", "agent": B}, KEY)
check("B sees A's org-shared memory", rbo.get("count", 0) == 1, rbo)

print("== default remember() (no scope) is org-visible (backward compatible) ==")
mem.remember(agent=A, about="eps", claim="default_fact=1")
_, rd = call("POST", f"/v1/recall?project={PID}", {"about": "eps", "agent": B}, KEY)
check("default scope is org (B sees it)", rd.get("count", 0) == 1, rd)

print("== explicit share promotes private -> org ==")
r = mem.remember(agent=A, about="gamma", claim="promote=1", scope=f"agent:{A}")
aid = r["id"]
_, bef = call("POST", f"/v1/recall?project={PID}", {"about": "gamma", "agent": B}, KEY)
call("POST", f"/v1/memory/share?project={PID}", {"assertion_id": aid, "scope": "org", "viewer": A}, KEY)
_, aft = call("POST", f"/v1/recall?project={PID}", {"about": "gamma", "agent": B}, KEY)
check("private before share (B blocked)", bef.get("count", 0) == 0)
check("visible after share (B sees)", aft.get("count", 0) == 1)

print("== team scope: members see, non-members don't ==")
call("POST", f"/v1/teams?project={PID}", {"team_id": "t1", "agents": [A, B]}, KEY)
mem.remember(agent=A, about="delta", claim="team_fact=1", scope="team:t1")
_, rin = call("POST", f"/v1/recall?project={PID}", {"about": "delta", "agent": B}, KEY)
_, rout = call("POST", f"/v1/recall?project={PID}", {"about": "delta", "agent": C}, KEY)
check("team member B sees team memory", rin.get("count", 0) == 1, rin)
check("non-member C blocked", rout.get("count", 0) == 0, rout)

print("== agent-bound key is secure by default ==")
_, keyB = call("POST", f"/v1/keys?project={PID}", {"name": "kB", "agent_id": f"agent:{B}"}, TOK)
KEYB = keyB["api_key"]["secret"] if "api_key" in keyB else (keyB.get("secret") or keyB.get("key"))
mem.remember(agent=A, about="zeta", claim="private2=1", scope=f"agent:{A}")
# bound key B, NO explicit viewer -> must be scoped to B automatically
_, rz = call("POST", f"/v1/recall?project={PID}", {"about": "zeta"}, KEYB)
check("bound key B cannot see A's private without explicit viewer", rz.get("count", 0) == 0, rz)
# bound key B cannot impersonate A
s_imp, imp = call("POST", f"/v1/recall?project={PID}", {"about": "zeta", "agent": A}, KEYB)
check("bound key B cannot impersonate A", imp.get("count", 0) == 0 or s_imp == 403, (s_imp, imp))

print(f"\n{passed} passed, {failed} failed")
srv.shutdown()
sys.exit(1 if failed else 0)
