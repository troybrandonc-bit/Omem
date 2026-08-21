"""Semantic recall + the utility learning loop. Locks in that (1) recall finds
paraphrased memories with no shared tokens, and (2) memories that prove useful
rank higher over time while ones marked incorrect fall back, deterministically."""
import os, sys, json, threading, time, urllib.request, urllib.error
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
    d=json.dumps(b).encode() if b is not None else None
    h={"Content-Type":"application/json"}
    if k: h["Authorization"]=f"Bearer {k}"
    r=urllib.request.Request(BASE+p,data=d,method=m,headers=h)
    try:
        with urllib.request.urlopen(r,timeout=5) as x: return x.status, json.loads(x.read() or b"{}")
    except urllib.error.HTTPError as e: return e.code, json.loads(e.read() or b"{}")
passed=failed=0
def check(n,c,d=""):
    global passed,failed; passed+=bool(c); failed+=(not c)
    print(("  ok   " if c else "  FAIL ")+n+("" if c else f"  <<< {d}"))
_,su=call("POST","/v1/signup",{"email":"learn@corp.com","org":"L"})
TOK=su["session_token"] if "session_token" in su else su.get("token")
PID=su["project"]["id"] if isinstance(su.get("project"),dict) else su.get("project_id")
_,key=call("POST",f"/v1/keys?project={PID}",{"name":"k"},TOK)
KEY=key["api_key"]["secret"] if "api_key" in key else (key.get("secret") or key.get("key"))
sys.path.insert(0, os.path.join("..","sdk","python"))
from omem import Memory
mem=Memory(api_key=KEY, base_url=BASE, project=PID)

print("== semantic recall: finds paraphrase with NO shared tokens ==")
mem.remember(agent="a", about="customer:acme", claim="prefers_annual_billing")
mem.remember(agent="a", about="customer:acme", claim="located_in_germany")
_,pack = call("POST", f"/v1/recall?project={PID}",
              {"agent":"a","context":"what are the customer's yearly invoicing preferences","about":"customer:acme"}, KEY)
props = [m.get("proposition","") for m in pack.get("memories",[])]
check("paraphrase 'yearly invoicing' finds 'annual_billing'", any("annual_billing" in p for p in props), props)

print("== utility learning loop: useful memory rises, incorrect falls ==")
r1=mem.remember(agent="a", about="customer:z", claim="fact_alpha")
r2=mem.remember(agent="a", about="customer:z", claim="fact_beta")
def order():
    _,pk = call("POST", f"/v1/recall?project={PID}", {"agent":"a","context":"about customer z","about":"customer:z"}, KEY)
    return [m.get("assertion") or m.get("id") for m in pk.get("memories",[])]
base = order()
check("both memories recalled", len(base) == 2, base)
second = base[1]
for _ in range(3):
    call("POST", f"/v1/feedback?project={PID}", {"kind":"useful","assertion_id":second}, KEY)
check("memory marked useful rises to first", order()[0] == second)
for _ in range(4):
    call("POST", f"/v1/feedback?project={PID}", {"kind":"incorrect","assertion_id":second}, KEY)
check("memory marked incorrect falls to last", order()[-1] == second)

print("== determinism: repeated recall with same feedback is stable ==")
o_a = order(); o_b = order()
check("recall order stable across identical calls", o_a == o_b, (o_a,o_b))

print(f"\n{passed} passed, {failed} failed")
srv.shutdown()
sys.exit(1 if failed else 0)
