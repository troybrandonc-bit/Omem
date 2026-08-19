"""Agent integration DX: remember() works on first call for a brand-new agent and
entity (auto_create default), and strict mode still surfaces R_DANGLING. This
locks in the out-of-the-box integration behavior an AI agent depends on."""
import os, sys, json, urllib.request, urllib.error, threading, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "sdk", "python"))
os.chdir(os.path.dirname(__file__))
for f in ("data/omem.db","data/omem.db-shm","data/omem.db-wal"):
    try: os.remove(f)
    except OSError: pass

import api
from http.server import ThreadingHTTPServer
srv = ThreadingHTTPServer(("127.0.0.1", 0), api.Handler)
PORT = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()
time.sleep(0.5)
BASE=f"http://127.0.0.1:{PORT}"
def call(m,p,b=None,k=None):
    req=urllib.request.Request(BASE+p, method=m,
        data=json.dumps(b).encode() if b is not None else None,
        headers={"Content-Type":"application/json", **({"Authorization":f"Bearer {k}"} if k else {})})
    try:
        with urllib.request.urlopen(req, timeout=5) as r: return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e: return e.code, json.loads(e.read() or b"{}")

_, acct = call("POST","/v1/signup",{"email":"autocreate@corp.com"})
KEY=acct["api_key"]["secret"]; PID=acct["project"]["id"]

from omem import Memory, OmemError
mem = Memory(api_key=KEY, base_url=BASE, project=PID)

passed=failed=0
def check(n,c):
    global passed,failed
    print(("  ok  " if c else "  FAIL ")+n); 
    globals().__setitem__("passed",passed+ (1 if c else 0)); globals().__setitem__("failed",failed+(0 if c else 1))

print("== remember() first call: brand-new agent + entity, no manual registration ==")
r = mem.remember(agent="brand-new-agent", about="brand-new-entity", claim="status=active")
check("remember returns an assertion id", bool(r.get("id")))
check("belief is BELIEVED_TRUE", mem.believes(about="brand-new-entity", claim="status=active")=="BELIEVED_TRUE")
check("recall finds it", mem.recall(about="brand-new-entity").get("count",0) >= 1)

print("== ensure_agent / ensure_entity are idempotent (safe to repeat) ==")
mem.ensure_agent("brand-new-agent"); mem.ensure_entity("brand-new-entity")
r2 = mem.remember(agent="brand-new-agent", about="brand-new-entity", claim="tier=gold")
check("second remember on same agent/entity works", bool(r2.get("id")))

print("== strict mode (auto_create=False) still surfaces R_DANGLING ==")
try:
    mem.remember(agent="brand-new-agent", about="ghost-entity", claim="x", auto_create=False)
    check("strict mode raised", False)
except OmemError as e:
    check("strict mode raises R_DANGLING", e.reason_code == "R_DANGLING")

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
