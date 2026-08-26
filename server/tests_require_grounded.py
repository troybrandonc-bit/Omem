"""Write-admission: OMEM_REQUIRE_GROUNDED refuses claims with nothing behind them.

Run: OMEM_REQUIRE_GROUNDED=1 python3 tests_require_grounded.py

OMEM has always recorded whether a belief is GROUNDED, meaning its provenance
reaches a real event, and left the caller to filter on it. This suite covers the
stricter option: refuse the write instead. The argument for it, made by a reader
rather than by us, is that "the consumer can filter" only holds until someone
forgets to filter, whereas "it never got in" holds always.

What must NOT break is as important as what must be refused, so the legitimate
paths are asserted alongside: citing an event works, citing an already-grounded
assertion works, and with the flag off nothing changes at all.
"""
import json
import os
import sys
import threading
import time
import http.client

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
DB = os.path.join(os.environ.get("TEMP", "/tmp"), "omem_require_grounded.db")
if os.path.exists(DB):
    os.remove(DB)
os.environ["OMEM_DB"] = DB
os.environ["OMEM_REQUIRE_GROUNDED"] = "1"

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


def call(m, path, body=None, key=None):
    c = http.client.HTTPConnection("127.0.0.1", PORT, timeout=10)
    h = {"Content-Type": "application/json"}
    if key:
        h["Authorization"] = f"Bearer {key}"
    c.request(m, path, body=json.dumps(body).encode() if body is not None else None, headers=h)
    r = c.getresponse(); t = r.read().decode(); st = r.status; c.close()
    try:
        return st, json.loads(t or "{}")
    except Exception:
        return st, {"raw": t[:200]}


st, acct = call("POST", "/v1/signup", {"email": "grounded@x.com"})
KEY, PID = acct["api_key"]["secret"], acct["project"]["id"]
call("POST", f"/v1/agents?project={PID}", {"id": "agent:a", "kind": "ai"}, KEY)
call("POST", f"/v1/entities?project={PID}", {"id": "customer:1", "type": "customer"}, KEY)

print("== a claim with nothing behind it is refused ==")
st, r = call("POST", f"/v1/assertions?project={PID}",
             {"agent": "agent:a", "subjects": ["customer:1"],
              "proposition": "prefers_annual"}, KEY)
check("bare assertion refused", st == 422, f"HTTP {st}: {r}")
check("and says why", r.get("error", {}).get("reason_code") == "R_UNGROUNDED", str(r)[:160])
check("naming the field to fix", r.get("error", {}).get("param") == "because", str(r)[:160])

st, r = call("POST", f"/v1/assertions?project={PID}",
             {"agent": "agent:a", "subjects": ["customer:1"],
              "proposition": "prefers_annual", "because": []}, KEY)
check("an empty because is still nothing", st == 422, f"HTTP {st}")

st, r = call("POST", f"/v1/assertions?project={PID}",
             {"agent": "agent:a", "subjects": ["customer:1"],
              "proposition": "prefers_annual", "because": ["evt_does_not_exist"]}, KEY)
check("citing evidence that does not exist is refused", st == 422, f"HTTP {st}")

print("== nothing was written by any of those ==")
st, lst = call("GET", f"/v1/assertions?project={PID}", None, KEY)
check("the record is still empty", len(lst.get("data", [])) == 0, str(lst)[:160])

print("== every refusal is recorded, not just refused ==")
# A refusal that leaves no trace is its own kind of silence. These land in the
# same fact_decisions table the ingestion gate writes to, so one query answers
# "what did this project decline to store, and why" across both paths.
st, fd = call("GET", f"/v1/fact-decisions?project={PID}", None, KEY)
rows = fd.get("data", fd) if isinstance(fd, dict) else fd
rows = [r for r in rows] if isinstance(rows, list) else []
denied = [r for r in rows if r.get("category") == "direct_write"]
check("the denials were logged", len(denied) >= 3, f"{len(denied)} rows: {str(rows)[:200]}")
check("logged as not stored", all(int(r.get("stored", 1)) == 0 for r in denied), str(denied)[:200])
check("with the proposition that was refused",
      any(r.get("proposition") == "prefers_annual" for r in denied), str(denied)[:200])
check("and a reason a human can read",
      any("because" in json.dumps(r.get("reasons") or "") for r in denied), str(denied)[:200])
check("and the candidate itself, so a repeat offender is visible",
      any("agent:a" in json.dumps(r.get("evidence") or "") for r in denied), str(denied)[:200])

print("== citing a real event is admitted ==")
st, ev = call("POST", f"/v1/events?project={PID}",
              {"id": "evt_call", "kind": "observation", "event_time": 1}, KEY)
check("event recorded", st == 201, f"HTTP {st}: {ev}")
st, a1 = call("POST", f"/v1/assertions?project={PID}",
              {"agent": "agent:a", "subjects": ["customer:1"],
               "proposition": "prefers_annual", "because": ["evt_call"]}, KEY)
check("assertion citing an event is admitted", st == 201, f"HTTP {st}: {a1}")
check("and comes back GROUNDED", a1.get("grounded") == "GROUNDED", str(a1)[:160])

print("== citing an already-grounded assertion is admitted (any-path) ==")
st, a2 = call("POST", f"/v1/assertions?project={PID}",
              {"agent": "agent:a", "subjects": ["customer:1"],
               "proposition": "renewal_likely", "because": [a1["id"]]}, KEY)
check("derived claim admitted", st == 201, f"HTTP {st}: {a2}")
check("and is itself GROUNDED", a2.get("grounded") == "GROUNDED", str(a2)[:160])

print("== supersede still works: it replaces a claim that already passed ==")
st, sup = call("POST", f"/v1/assertions/{a1['id']}/supersede?project={PID}",
               {"new": {"agent": "agent:a", "subjects": ["customer:1"],
                        "proposition": "prefers_monthly"}}, KEY)
check("supersede is not blocked by the gate", st == 201, f"HTTP {st}: {sup}")

print("== with the flag OFF, the old behaviour is unchanged ==")
del os.environ["OMEM_REQUIRE_GROUNDED"]
st, a3 = call("POST", f"/v1/assertions?project={PID}",
              {"agent": "agent:a", "subjects": ["customer:1"],
               "proposition": "ungrounded_but_allowed"}, KEY)
check("a bare assertion is accepted again", st == 201, f"HTTP {st}: {a3}")
check("and is honestly marked UNGROUNDED", a3.get("grounded") == "UNGROUNDED", str(a3)[:160])
os.environ["OMEM_REQUIRE_GROUNDED"] = "1"

srv.shutdown()
print(f"\n{PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
