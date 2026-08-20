"""P8 event_time distinction. Run: python3 tests_p8_event_time.py

Proves assertion_time (when OMEM learned it) and event_time (when it happened)
are distinct, engine-native fields, populated at formation and surfaced in the
memory chain and packs. Does not fabricate timestamps: when no event time is
supplied they legitimately coincide; when one is supplied they differ.
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
DB = "/tmp/omem_p8_et.db"
if os.path.exists(DB):
    os.remove(DB)
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
        with urllib.request.urlopen(r, timeout=15) as resp:
            return resp.status, json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


acct = call("POST", "/v1/signup", {"email": "et@k.com"})[1]
KEY, PID = acct["api_key"]["secret"], acct["project"]["id"]
call("POST", f"/v1/identity?project={PID}",
     {"company_name": "K", "domains": ["k.com"], "emails": ["et@k.com"]}, KEY)
P = api.PROJECTS[PID]

print("== explicit event time (happened earlier than we learned it) ==")
# advance the clock so 'now' is well past 3
for _ in range(20):
    P.tick()
st, r = call("POST", f"/v1/observe?project={PID}",
             {"agent": "agent:s", "scope": "org",
              "interaction": {"text": "We have decided to renew the annual contract.",
                              "speaker": "jane@acme.com", "audience": "et@k.com",
                              "at": 3}}, KEY)  # the decision happened at logical t=3
check("observe succeeded", st == 201, str(st))
aid = r["memories"][0]["assertion"]
a = P.engine.store.assertion(aid)
check("event_time populated from 'at' (=3)", getattr(a, "event_time", None) == 3,
      f"event_time={getattr(a, 'event_time', None)}")
check("assertion_time is the (later) learning moment, distinct from event_time",
      a.assertion_time != a.event_time and a.assertion_time > a.event_time,
      f"assertion_time={a.assertion_time} event_time={a.event_time}")

print("== chain surfaces both, distinctly ==")
st, ch = call("GET", f"/v1/memory/chain?project={PID}&assertion={aid}&viewer=agent:s", None, KEY)
check("chain exposes learned_at (assertion_time)", ch.get("learned_at") == a.assertion_time)
check("chain exposes event_time distinct from learned_at",
      ch.get("event_time") == 3 and ch["event_time"] != ch["learned_at"],
      f"event_time={ch.get('event_time')} learned_at={ch.get('learned_at')}")

print("== pack surfaces event_time ==")
st, pk = call("POST", f"/v1/recall?project={PID}",
              {"agent": "agent:s", "context": "acme renewal decision"}, KEY)
item = [m for m in pk["memories"] if m["id"] == aid]
check("pack item carries event_time",
      item and item[0].get("event_time") == 3, str(item)[:150] if item else "absent")
check("pack item carries learned_at distinct from event_time",
      item and item[0].get("learned_at") == a.assertion_time
      and item[0]["learned_at"] != item[0]["event_time"])

print("== no fabrication: 'now' coincides honestly ==")
st, r2 = call("POST", f"/v1/observe?project={PID}",
              {"agent": "agent:s", "scope": "org",
               "interaction": {"text": "We prefer monthly billing now.",
                               "speaker": "bob@beta.io", "audience": "et@k.com"}}, KEY)
if r2.get("memories"):
    a2 = P.engine.store.assertion(r2["memories"][0]["assertion"])
    check("no explicit 'at' -> event_time == assertion_time (not invented)",
          a2.event_time == a2.assertion_time,
          f"assertion_time={a2.assertion_time} event_time={a2.event_time}")
else:
    check("no explicit 'at' -> event_time == assertion_time (not invented)", True,
          "(no durable memory formed; vacuous)")

print("== malformed 'at' degrades safely ==")
st, r3 = call("POST", f"/v1/observe?project={PID}",
              {"agent": "agent:s", "scope": "org",
               "interaction": {"text": "We have decided to renew the annual contract.",
                               "speaker": "kim@gamma.co", "audience": "et@k.com",
                               "at": "banana"}}, KEY)
check("malformed 'at' does not error (treated as now)", st == 201, str(st))

print("== distinct observations get distinct event times (clock advances) ==")
ids = []
for who in ("a@x.io", "b@y.io", "c@z.io"):
    st, rr = call("POST", f"/v1/observe?project={PID}",
                  {"agent": "agent:s", "scope": "org",
                   "interaction": {"text": "We have decided to renew the annual contract.",
                                   "speaker": who, "audience": "et@k.com"}}, KEY)
    if rr.get("memories"):
        ids.append(rr["memories"][0]["assertion"])
ets = {P.engine.store.assertion(i).event_time for i in ids}
check("consecutive observations get distinct event times", len(ets) == len(ids),
      f"{len(ets)} distinct of {len(ids)}")

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
