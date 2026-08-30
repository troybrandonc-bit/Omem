"""Managed agent surface tests (learn/recall). Run: python3 tests_agent.py
Verifies the managed loop: text -> extraction -> engine primitives -> engine
decides state, plus recall reads real memory, and the Python SDK agent wrapper
works against the live server."""
import os
import sys
import json
import threading
import time
import urllib.request
import urllib.error

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "sdk", "python"))
DB = "/tmp/omem_agent_tests.db"
if os.path.exists(DB):
    os.remove(DB)
os.environ["OMEM_DB"] = DB

import api  # noqa: E402
from http.server import ThreadingHTTPServer  # noqa: E402

srv = ThreadingHTTPServer(("127.0.0.1", 0), api.Handler)
PORT = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()
time.sleep(0.2)
BASE = f"http://127.0.0.1:{PORT}"
PASS = FAIL = 0


def check(n, c, d=""):
    global PASS, FAIL
    if c:
        PASS += 1; print(f"  ok  {n}")
    else:
        FAIL += 1; print(f"  FAIL {n}  {d}")


def call(m, path, body=None, key=None):
    req = urllib.request.Request(BASE + path, method=m,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Content-Type": "application/json", **({"Authorization": f"Bearer {key}"} if key else {})})
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


_, acct = call("POST", "/v1/signup", {"email": "agent@corp.com"})
KEY = acct["api_key"]["secret"]
PID = acct["project"]["id"]

print("== learn: text -> engine belief ==")
st, r = call("POST", f"/v1/learn?project={PID}",
             {"agent": "support-agent", "about": "customer:123",
              "text": "The customer told us they prefer annual billing.", "source": "ticket:8842"}, KEY)
check("learn 201", st == 201)
check("one belief produced", len(r["learned"]) == 1)
check("engine says BELIEVED_TRUE", r["learned"][0]["state"] == "BELIEVED_TRUE")
check("evidence recorded", "annual billing" in (r["learned"][0].get("evidence") or ""))

print("== learn: no durable fact -> empty (not an error) ==")
st, r = call("POST", f"/v1/learn?project={PID}",
             {"agent": "support-agent", "about": "customer:123", "text": "Hello, thanks!"}, KEY)
check("empty learn 200", st == 200 and r["learned"] == [])

print("== recall: reads real memory, engine state ==")
st, r = call("POST", f"/v1/recall?project={PID}", {"about": "customer:123"}, KEY)
check("recall finds the belief", r["count"] == 1)
check("recall proposition", r["memories"][0]["proposition"] == "prefers_annual_billing")
check("recall state from engine", r["memories"][0]["state"] == "BELIEVED_TRUE")
check("recall shows grounding", r["memories"][0]["grounded"] is True)

print("== learn drives engine contradiction (engine decides) ==")
call("POST", f"/v1/declare-contradiction?project={PID}",
     {"token_a": "prefers_annual_billing", "token_b": "not:prefers_annual_billing"}, KEY)
# a fact that maps to the negation would flip state; RuleExtractor has no negation for billing,
# so assert the negation directly to prove recall reflects the engine, not the pipeline
call("POST", f"/v1/agents?project={PID}", {"id": "crm", "kind": "system"}, KEY)
call("POST", f"/v1/assertions?project={PID}",
     {"agent": "crm", "subjects": ["customer:123"], "proposition": "not:prefers_annual_billing",
      "assertion_time": "now"}, KEY)
st, r = call("POST", f"/v1/recall?project={PID}", {"about": "customer:123"}, KEY)
states = {m["proposition"]: m["state"] for m in r["memories"]}
check("recall reflects engine CONTRADICTED", states.get("prefers_annual_billing") == "CONTRADICTED", str(states))

print("== usage metered for learn/recall ==")
_, sess = call("POST", "/v1/session", {"email": "agent@corp.com"})
st, u = call("GET", f"/v1/usage?project={PID}", key=sess["token"])
check("learn_requests metered", u["metrics"].get("learn_requests", 0) >= 2)
check("agent_recalls metered", u["metrics"].get("agent_recalls", 0) >= 2)

print("== Python SDK against live server ==")
from omem import Memory, Agent, OmemError  # noqa: E402
mem = Memory(api_key=KEY, base_url=BASE, project=PID)
r = mem.learn(agent="support-agent", about="customer:777", text="Customer wants to upgrade.")
check("SDK learn works", any(m["state"] in ("BELIEVED_TRUE", "CONTRADICTED") for m in r["learned"]))
rec = mem.recall("customer:777")
check("SDK recall works", rec["count"] >= 1)
ag = mem.agent("support-agent")
check("SDK Agent wrapper .recall", ag.recall("customer:777")["count"] >= 1)
# Regression: Agent.observe once called self.memory/self.agent_id (which do not
# exist on the wrapper), so every call raised AttributeError. Pin that it works.
obs = ag.observe("The customer at customer:777 prefers email over phone calls.")
check("SDK Agent wrapper .observe works", isinstance(obs, dict))
try:
    mem.remember(agent="support-agent", about="ghost:1", claim="x", auto_create=False)
    check("SDK error", False)
except OmemError as e:
    check("SDK surfaces R_DANGLING", e.reason_code == "R_DANGLING")

print("== playground flow: learn -> recall -> why (via SDK agent) ==")
ag2 = mem.agent("support-agent")
lr = ag2.learn(text="The customer wants to cancel their subscription.", about="customer:flow")
check("agent.learn produced a belief", len(lr["learned"]) >= 1)
aid = lr["learned"][0]["assertion"]
w = ag2.why(aid)
check("agent.why returns state", w["state"] in ("BELIEVED_TRUE", "CONTRADICTED", "UNKNOWN"))
check("agent.why returns grounded flag", isinstance(w["grounded"], bool))
check("agent.why has provenance nodes reaching an event",
      any(n["kind"] == "event" for n in w["provenance"]["nodes"]))
check("agent.why provenance edge is extraction",
      any(e["kind"] == "extraction" for e in w["provenance"]["edges"]))

print("== persistence: learned memory replays ==")
srv.shutdown()
import importlib
sys.modules.pop("api")
api2 = importlib.import_module("api")
p = api2.PROJECTS.get(PID)
check("learned belief replayed", p is not None and
      p.engine.proposition_state(["customer:123"], "prefers_annual_billing", p.now()) == "CONTRADICTED")

print(f"\n{PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
