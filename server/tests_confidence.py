"""The confidence field finally does something. Run: python3 tests_confidence.py

Assertions have carried a confidence since the engine's first commit and no
read path ever used it: a claim scored 0.9 and one scored 0.3 ranked, showed
and explained identically. Now confidence.py owns one deterministic
arithmetic -- stated (or 0.6 unstated), +0.1 per independent corroboration
capped at three, held under 0.99 always -- and recall ranks by its coarse
bucket while /why and the pack spell out the derivation.

The suite pins the boundaries: distinctness (a thousand copies of one email
are one observation), the cap, the ceiling, the ranking flip a corroboration
causes and the flag that turns it off, and the line this number never
crosses: it is strength of support, and the engine's belief state is not
consulted, adjusted, or overridden by it.
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
sys.path.insert(0, os.path.join(HERE, "..", "sdk", "python"))
TMP = os.environ.get("TEMP") or "/tmp"
DB = os.path.join(TMP, "omem_confidence.db")
if os.path.exists(DB):
    os.remove(DB)
os.environ["OMEM_DB"] = DB
os.environ.setdefault("OMEM_TENANT_RL_BURST", "10000")
os.environ.setdefault("OMEM_TENANT_RL_RPS", "10000")

import api  # noqa: E402
import omem  # noqa: E402
import confidence  # noqa: E402
import consolidation as _consol  # noqa: E402
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


print("== the arithmetic, alone ==")
s, why = confidence.effective(None, 0)
check("unstated is 0.6, and says so", s == 0.6 and "no stated" in why[0], (s, why))
s, _ = confidence.effective(0.9, 0)
check("stated is taken as stated", s == 0.9)
s, why = confidence.effective(0.5, 2)
check("two corroborations add 0.2", s == 0.7, (s, why))
s, why = confidence.effective(0.5, 50)
check("corroboration caps at three, and the reason admits it",
      s == 0.8 and any("capped" in w for w in why), (s, why))
s, why = confidence.effective(0.95, 3)
check("the ceiling holds: certainty is never claimed",
      s == 0.99 and any("certainty" in w for w in why), (s, why))
check("buckets are coarse on purpose",
      confidence.bucket(0.6) == confidence.bucket(0.61)
      and confidence.bucket(0.99) == 4)

OWNER = "confidence@kronos.com"
srv = ThreadingHTTPServer(("127.0.0.1", 0), api.Handler)
PORT = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()
time.sleep(0.2)
BASE = "http://127.0.0.1:%d" % PORT


def call(m, path, body=None, key=None):
    h = {"Content-Type": "application/json"}
    if key:
        h["Authorization"] = "Bearer " + key
    r = urllib.request.Request(
        BASE + path, method=m,
        data=json.dumps(body).encode() if body is not None else None, headers=h)
    try:
        with urllib.request.urlopen(r, timeout=20) as resp:
            return resp.status, json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


acct = call("POST", "/v1/signup", {"email": OWNER})[1]
KEY, PID = acct["api_key"]["secret"], acct["project"]["id"]
mem = omem.Memory(KEY, base_url=BASE, project=PID)
A = "agent:owner"

print("== independence: a repeated source corroborates once ==")
older = mem.remember(A, "customer:acme", "prefers_annual_billing")
newer = mem.remember(A, "customer:acme", "prefers_phone_contact")
for _ in range(5):
    _consol.reinforce(api.STORE.db, PID, older["id"], "connector:gmail", "src_1")
sup = confidence.bulk_support(api.STORE.db, PID, [older["id"], newer["id"]])
check("five readings of one source are ONE observation",
      sup.get(older["id"]) == 1, sup)
_consol.reinforce(api.STORE.db, PID, older["id"], "connector:slack", "src_9")
sup = confidence.bulk_support(api.STORE.db, PID, [older["id"]])
check("a second independent source is a second observation",
      sup.get(older["id"]) == 2, sup)

print("== recall: support outranks recency, and explains itself ==")
st, pack = call("POST", "/v1/recall?project=%s" % PID,
                {"agent": A, "context": "what do we know about acme",
                 "limit": 8}, KEY)
mems = pack.get("memories", [])
props = [m["proposition"] for m in mems]
check("both facts are in the pack",
      {"prefers_annual_billing", "prefers_phone_contact"} <= set(props), props)
check("the corroborated OLDER fact outranks the newer unsupported one",
      props.index("prefers_annual_billing") < props.index("prefers_phone_contact"),
      props)
annual = next(m for m in mems if m["proposition"] == "prefers_annual_billing")
check("the pack carries the score", annual.get("confidence") == 0.8, annual)
check("and its derivation, spelled out",
      any("corroboration" in w for w in (annual.get("confidence_because") or [])),
      annual.get("confidence_because"))

os.environ["OMEM_CONFIDENCE_RANKING"] = "0"
st, pack2 = call("POST", "/v1/recall?project=%s" % PID,
                 {"agent": A, "context": "what do we know about acme",
                  "limit": 8}, KEY)
props2 = [m["proposition"] for m in pack2.get("memories", [])]
check("with the flag off, recency decides again",
      props2.index("prefers_phone_contact") < props2.index("prefers_annual_billing"),
      props2)
check("but the fields still ship: display is not gated, only rank",
      all(m.get("confidence") is not None for m in pack2.get("memories", [])))
os.environ["OMEM_CONFIDENCE_RANKING"] = "1"

print("== /why spells out the same derivation ==")
st, w = call("GET", "/v1/assertions/%s/why?project=%s&viewer=%s"
             % (older["id"], PID, A), None, KEY)
check("/why answers with a confidence block",
      st == 200 and w.get("confidence", {}).get("score") == 0.8, w.get("confidence"))
check("naming the corroboration",
      any("corroboration" in x for x in w["confidence"]["because"]),
      w["confidence"])

print("== the line it never crosses: support is not truth ==")
mem.remember(A, "customer:acme", "not:prefers_annual_billing")
check("a contradicted claim is CONTRADICTED however well-supported one side is",
      mem.believes("customer:acme", "prefers_annual_billing") == "CONTRADICTED")
st, w2 = call("GET", "/v1/assertions/%s/why?project=%s&viewer=%s"
              % (older["id"], PID, A), None, KEY)
check("and /why reports the engine's state beside the support, unblended",
      w2.get("state") == "CONTRADICTED"
      and w2.get("confidence", {}).get("score") == 0.8, (w2.get("state"), w2.get("confidence")))

print("\n%d passed, %d failed" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)
