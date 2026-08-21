"""P8 Step 7 B2 regression. Run: python3 tests_p8_b2_conflicts.py

Proves the two routes that previously ran the unbounded O(n²)
engine.conflicts(T) (GET /v1/conflicts and GET /v1/assertions/{id}/why)
now use the P7 narrowed path: same results, bounded latency.
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
DB = "/tmp/omem_p8_b2.db"
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
        with urllib.request.urlopen(r, timeout=60) as resp:
            return resp.status, json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


acct = call("POST", "/v1/signup", {"email": "b2@k.com"})[1]
KEY, PID = acct["api_key"]["secret"], acct["project"]["id"]
P = api.PROJECTS[PID]
api.record(P, "agent", {"id": "agent:s", "kind": "system"})

print("== correctness: /v1/conflicts matches engine.conflicts() on a small set ==")
# a few real conflicts on shared subjects
for e in ("company:a", "company:b"):
    api.record(P, "entity", {"id": e, "type": "organization"})
api.record(P, "assert", {"id": "x1", "agent": "agent:s", "subjects": ["company:a"],
                         "proposition": "prefers_annual", "assertion_time": P.tick()})
api.record(P, "assert", {"id": "x2", "agent": "agent:s", "subjects": ["company:a"],
                         "proposition": "prefers_monthly", "assertion_time": P.tick()})
api.record(P, "assert", {"id": "x3", "agent": "agent:s", "subjects": ["company:b"],
                         "proposition": "prefers_annual", "assertion_time": P.tick()})
api.record(P, "assert", {"id": "x4", "agent": "agent:s", "subjects": ["company:b"],
                         "proposition": "prefers_monthly", "assertion_time": P.tick()})
api.record(P, "declare", {"token_a": "prefers_annual", "token_b": "prefers_monthly"})

st, c = call("GET", f"/v1/conflicts?project={PID}", None, KEY)
route_pairs = {frozenset((pr["pair"][0]["id"], pr["pair"][1]["id"])) for pr in c["conflicts"]}
engine_pairs = set(P.engine.conflicts(P.now()))
check("/v1/conflicts returns exactly the engine's conflict pairs",
      route_pairs == engine_pairs, f"route={route_pairs} engine={engine_pairs}")

st, w = call("GET", f"/v1/assertions/x1/why?project={PID}", None, KEY)
why_ids = {cc["id"] for cc in w.get("contradictions", [])}
check("/why lists the contradictory assertion (x2)", "x2" in why_ids, str(why_ids))
check("/why does not list a different subject's conflict (x4)", "x4" not in why_ids)

print("== bounded latency: /v1/conflicts does not exhibit O(n²) blow-up ==")
# grow to 1500 assertions across distinct subjects; the OLD full path was
# multi-second→minutes here. The narrowed path must stay well bounded.
n = 4
while n < 1500:
    e = f"company:c{n}"
    api.record(P, "entity", {"id": e, "type": "organization"})
    api.record(P, "assert", {"id": api._mint_global("a"), "agent": "agent:s",
                             "subjects": [e], "proposition": f"prop_{n % 20}",
                             "assertion_time": P.tick()})
    n += 1
for i in range(0, 20, 2):
    api.record(P, "declare", {"token_a": f"prop_{i}", "token_b": f"prop_{i + 1}"})

t0 = time.perf_counter()
st, c = call("GET", f"/v1/conflicts?project={PID}", None, KEY)
dt = time.perf_counter() - t0
check("/v1/conflicts at 1500 assertions returns 200", st == 200, str(st))
# generous ceiling - the point is "seconds, not tens of seconds"; the old full
# O(n²) path was ~tens of seconds by 5k and unusable. 10s is a safe bound that
# still fails loudly if the narrowing regresses.
check(f"/v1/conflicts at 1500 stays bounded (<10s, was O(n^2)), {dt:.1f}s", dt < 10.0,
      f"{dt:.1f}s")

print("== C2: /v1/conflicts uses the narrow path, not the O(n^2) fallback ==")
import conflict_narrow as _cn_mod
_orig_narrow = _cn_mod.conflicts_for
_narrow_calls = {"n": 0}
def _spy(*a, **k):
    _narrow_calls["n"] += 1
    return _orig_narrow(*a, **k)
_cn_mod.conflicts_for = _spy
_full_calls = {"n": 0}
_orig_full = P.engine.conflicts
def _fullspy(*a, **k):
    _full_calls["n"] += 1
    return _orig_full(*a, **k)
P.engine.conflicts = _fullspy
try:
    call("GET", f"/v1/conflicts?project={PID}", None, KEY)
finally:
    _cn_mod.conflicts_for = _orig_narrow
    P.engine.conflicts = _orig_full
check("narrow conflicts_for was invoked", _narrow_calls["n"] >= 1, str(_narrow_calls))
check("full engine.conflicts() was NOT invoked (no O(n^2) fallback)",
      _full_calls["n"] == 0, f"full called {_full_calls['n']}x")

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
