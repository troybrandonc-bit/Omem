"""Assertions carry the real wall-clock time they were recorded.

Run: python3 tests_recorded_at.py

The engine's assertion_time is a LOGICAL clock (a tick, for deterministic
replay), which is the right thing to reason with and the wrong thing to show a
person: "t1" means nothing to somebody reading the dashboard. So every
assertion now also carries recorded_at, the real moment it was written, taken
from the op log's timestamp. It is display-only and never feeds the engine.
This suite pins that it is present, is a real epoch near now, and reaches the
list, the single-assertion and the why views alike.
"""
import json
import os
import sys
import threading
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "sdk", "python"))
TMP = os.environ.get("TEMP") or "/tmp"
DB = os.path.join(TMP, "omem_recorded_at.db")
if os.path.exists(DB):
    os.remove(DB)
os.environ["OMEM_DB"] = DB
os.environ.setdefault("OMEM_TENANT_RL_BURST", "10000")
os.environ.setdefault("OMEM_TENANT_RL_RPS", "10000")

import api  # noqa: E402
import omem  # noqa: E402
from http.server import ThreadingHTTPServer  # noqa: E402

PASS = FAIL = 0


def check(n, c, d=""):
    global PASS, FAIL
    if c:
        PASS += 1
        print("  ok  " + n)
    else:
        FAIL += 1
        print("  FAIL " + n + "  " + str(d)[:220])


srv = ThreadingHTTPServer(("127.0.0.1", 0), api.Handler)
PORT = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()
time.sleep(0.2)
BASE = "http://127.0.0.1:%d" % PORT

req = urllib.request.Request(BASE + "/v1/signup", method="POST",
                             data=json.dumps({"email": "recat@kronos.com"}).encode(),
                             headers={"Content-Type": "application/json"})
acct = json.loads(urllib.request.urlopen(req, timeout=20).read())
KEY, PID = acct["api_key"]["secret"], acct["project"]["id"]
mem = omem.Memory(KEY, base_url=BASE, project=PID)

before = time.time()
r = mem.remember("agent:owner", "person:vera", "prefers_annual_billing")
aid = r["id"]
after = time.time()

rows = mem._req("GET", "/v1/assertions").get("data", [])
row = next((a for a in rows if a["id"] == aid), None)
check("the list carries recorded_at", row is not None and "recorded_at" in row, row)
check("it is a real epoch, not the logical tick",
      row and isinstance(row["recorded_at"], (int, float))
      and row["recorded_at"] != row["assertion_time"], row)
check("and it falls in the window the write happened in",
      row and before - 1 <= row["recorded_at"] <= after + 1,
      (before, row and row["recorded_at"], after))

single = mem._req("GET", "/v1/assertions/%s" % aid)
check("the single-assertion view carries it too",
      isinstance(single.get("recorded_at"), (int, float)), single.get("recorded_at"))

why = mem.why(aid)
check("the why view carries it on its assertion",
      isinstance(why.get("assertion", {}).get("recorded_at"), (int, float)),
      why.get("assertion", {}).get("recorded_at"))

# earliest-wins: a supersede writes a new op; the ORIGINAL keeps its own time.
st, _ = None, None
sup = mem._req("POST", "/v1/assertions/%s/supersede" % aid,
               {"new": {"agent": "agent:owner", "subjects": ["person:vera"],
                        "proposition": "prefers_monthly_billing"}})
rows2 = {a["id"]: a for a in mem._req("GET", "/v1/assertions").get("data", [])}
check("the original assertion keeps its own recorded_at after a supersede",
      abs(rows2[aid]["recorded_at"] - row["recorded_at"]) < 0.001, rows2.get(aid))

print("\n%d passed, %d failed" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)
