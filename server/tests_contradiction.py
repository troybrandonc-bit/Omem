"""Contradictions are reachable. Run: python3 tests_contradiction.py

THE BUG THIS EXISTS FOR. OMEM's headline is that conflicting information is
surfaced rather than silently overwritten. It was unreachable. The engine only
ever treats two claims as opposed if some caller declared that pair, which is
the right rule and the reason a belief state is reproducible without a model,
but nothing ever declared one: `declare_contradiction` had a single call site,
an op kind, and the SDK exposed no way to reach it. So a developer stored two
opposed facts, called conflicts(), got an empty list, and concluded the product
did not work. It did exactly what it was told and had been told nothing.

Two ways in now, and both are proved here:

  `X` / `not:X`   paired automatically the first time either is stored, so the
                  common case needs no setup at all.
  contradict()    any two tokens the caller names, for what a prefix cannot say
                  (annual versus monthly).

WHAT MUST NOT BREAK. Auto-declaration lives in api.apply_op, above the frozen
engine, and omem_engine/ is untouched: the engine still knows only what it was
told, and the rule that it never reads meaning out of text still holds. It must
also stay a pure function of the op being applied, or a boot replay would
rebuild a different registry from the same log, which the restart case below is
what actually checks.

And the refusals matter as much as the detections: two claims that nobody
declared opposed must stay independent. A memory that invents conflicts is
worse than one that finds none.
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
DB = os.environ.get("OMEM_DB") or "/tmp/omem_contradiction.db"
for suffix in ("", "-wal", "-shm"):
    if os.path.exists(DB + suffix):
        try:
            os.remove(DB + suffix)
        except OSError:
            pass
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


acct = call("POST", "/v1/signup", {"email": "contradiction@k.com"})[1]
KEY, PID = acct["api_key"]["secret"], acct["project"]["id"]
P = api.PROJECTS[PID]
api.record(P, "agent", {"id": "agent:s", "kind": "system"})
for e in ("customer:1", "customer:2", "customer:3", "customer:4"):
    api.record(P, "entity", {"id": e, "type": "organization"})


def assert_(aid, subject, proposition):
    api.record(P, "assert", {"id": aid, "agent": "agent:s", "subjects": [subject],
                             "proposition": proposition, "assertion_time": P.tick()})


print("== the common case needs no setup ==")
assert_("c1", "customer:1", "likes_tea")
assert_("c2", "customer:1", "not:likes_tea")
check("X and not:X contradict with nothing declared by hand",
      P.engine.proposition_state(("customer:1",), "likes_tea", P.now()) == "CONTRADICTED",
      P.engine.proposition_state(("customer:1",), "likes_tea", P.now()))
check("and the pair is listed, so an empty conflicts() is diagnosable",
      any(sorted([a, b]) == ["likes_tea", "not:likes_tea"]
          for a, b in api.CONTRADICTIONS.get(PID, [])))

print("== order of arrival does not matter (the convention is involutive) ==")
assert_("c3", "customer:2", "not:pays_on_time")
assert_("c4", "customer:2", "pays_on_time")
check("negation first, then the positive, still contradicts",
      P.engine.proposition_state(("customer:2",), "pays_on_time", P.now()) == "CONTRADICTED")

print("== claims nobody opposed stay independent ==")
assert_("c5", "customer:3", "uses_slack")
assert_("c6", "customer:3", "uses_email")
check("two unrelated claims are both simply believed",
      P.engine.proposition_state(("customer:3",), "uses_slack", P.now()) == "BELIEVED_TRUE",
      P.engine.proposition_state(("customer:3",), "uses_slack", P.now()))
check("no conflict was invented between them",
      not any({"c5", "c6"} == set(pair) for pair in P.engine.conflicts(P.now())))

print("== the general case: any two tokens, declared explicitly ==")
st, _ = call("POST", f"/v1/contradictions?project={PID}",
             {"token_a": "prefers_annual", "token_b": "prefers_monthly"}, KEY)
check("POST /v1/contradictions accepted", st == 201, f"status {st}")
assert_("c7", "customer:4", "prefers_annual")
assert_("c8", "customer:4", "prefers_monthly")
check("the declared pair now contradicts",
      P.engine.proposition_state(("customer:4",), "prefers_annual", P.now()) == "CONTRADICTED")
st, lst = call("GET", f"/v1/contradictions?project={PID}", None, KEY)
check("GET /v1/contradictions lists it", st == 200 and any(
    sorted([d["token_a"], d["token_b"]]) == ["prefers_annual", "prefers_monthly"]
    for d in lst.get("data", [])), f"status {st}")

print("== a declaration that means nothing is refused, not stored ==")
check("a claim cannot contradict itself",
      call("POST", f"/v1/contradictions?project={PID}",
           {"token_a": "x", "token_b": "x"}, KEY)[0] == 422)
check("empty tokens refused",
      call("POST", f"/v1/contradictions?project={PID}",
           {"token_a": "", "token_b": "y"}, KEY)[0] == 422)
check("non-string tokens refused",
      call("POST", f"/v1/contradictions?project={PID}",
           {"token_a": 7, "token_b": "y"}, KEY)[0] == 422)

print("== the reserved marker is not a claim and gets no counterpart ==")
# RETRACTED contributes to neither side of a proposition state (N10). Pairing it
# with `not:RETRACTED` would put the retraction machinery into the contradiction
# registry, where it has no business being.
check("RETRACTED has no negation counterpart", api._negation_counterpart(api.RETRACTED) is None)
check("a bare prefix is not a negation of anything", api._negation_counterpart("not:") is None)
check("the empty token has no counterpart", api._negation_counterpart("") is None)
check("double negation is still just a pair",
      api._negation_counterpart("not:not:x") == "not:x")

print("== restart replay rebuilds the same registry ==")
# The one that would rot silently. Auto-declaration is a pure function of the op
# being applied, so replaying the log must reconstruct exactly the same pairs. If
# it ever depended on surrounding state, a restarted server would answer
# CONTRADICTED before and BELIEVED_TRUE after, and nothing else here would catch it.
before = {frozenset(p) for p in api.CONTRADICTIONS.get(PID, [])}
srv.shutdown()
import importlib  # noqa: E402
import store as store_mod  # noqa: E402
importlib.reload(store_mod)
sys.modules.pop("api")
api2 = importlib.import_module("api")
P2 = api2.PROJECTS.get(PID)
check("project rehydrated", P2 is not None)
if P2:
    after = {frozenset(p) for p in api2.CONTRADICTIONS.get(PID, [])}
    check("the declared pairs are identical after replay", before == after,
          f"{len(before)} before, {len(after)} after")
    check("an auto-declared contradiction survives the restart",
          P2.engine.proposition_state(("customer:1",), "likes_tea", P2.now()) == "CONTRADICTED",
          P2.engine.proposition_state(("customer:1",), "likes_tea", P2.now()))
    check("an explicitly declared one survives too",
          P2.engine.proposition_state(("customer:4",), "prefers_annual", P2.now()) == "CONTRADICTED")
    check("and independent claims are still independent",
          P2.engine.proposition_state(("customer:3",), "uses_slack", P2.now()) == "BELIEVED_TRUE")

print(f"\n{PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
