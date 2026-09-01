"""OMEM exports a conforming Testimony Record, checked by the published
validator against a real server.
Run: python3 tests_testimony_export.py

Publishing a specification and calling yourself the reference implementation
is a claim. This is the check on it: drive a real project through the story
the specification was written for (two sources disagree, a risky action is
refused, a named human approves, it runs once), export it, and validate the
export at the level the site claims. If OMEM ever stops conforming to its own
specification, this suite goes red before anyone else finds out.
"""
import json
import os
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, ".."))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "scripts"))
sys.path.insert(0, os.path.join(ROOT, "sdk", "python"))

TMP = os.environ.get("TEMP") or "/tmp"
os.environ["OMEM_DB"] = os.path.join(TMP, "omem_testimony_export.db")
os.environ.setdefault("OMEM_SEED_DEMO", "0")
if os.path.exists(os.environ["OMEM_DB"]):
    os.remove(os.environ["OMEM_DB"])

import api  # noqa: E402
import healing as HEAL  # noqa: E402
import export_testimony as EX  # noqa: E402
import testimony_validate as TV  # noqa: E402
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


LEDGER = []
api.HEAL_ACTIONS.register(
    "issue_refund", HEAL.RISK_HIGH,
    lambda component, args: (LEDGER.append(args), {"ok": True})[1],
    "Refund a customer payment")
# clear_cache ships registered at low risk; it needs a component that offers
# the hook before it can actually run.
api.HEAL_COMPONENTS.register("billing", clear_cache=lambda: True)

srv = ThreadingHTTPServer(("127.0.0.1", 0), api.Handler)
PORT = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()
time.sleep(0.3)

import http.client  # noqa: E402


def call(method, path, body=None, key=None):
    c = http.client.HTTPConnection("127.0.0.1", PORT, timeout=15)
    h = {"Content-Type": "application/json"}
    if key:
        h["Authorization"] = "Bearer " + key
    c.request(method, path, body=json.dumps(body).encode() if body is not None else None,
              headers=h)
    r = c.getresponse()
    t = r.read().decode()
    c.close()
    return r.status, (json.loads(t or "{}") if t else {})


_, acct = call("POST", "/v1/signup", {"email": "export@omem.local"})
KEY, PID = acct["api_key"]["secret"], acct["project"]["id"]
OWNER = api.STORE.create_key(PID, "Reviewer key", "owner")["secret"]

from omem import Memory  # noqa: E402
mem = Memory(api_key=KEY, base_url="http://127.0.0.1:%d" % PORT, project=PID)

print("== the story the specification was written for ==")
mem.remember("crm-sync", "customer:acme", "plan_annual_pro", label="CRM record")
mem.remember("billing-watcher", "customer:acme", "not:plan_annual_pro",
             label="billing portal webhook")
mem.remember("support-agent", "customer:acme", "refund_eligible", label="policy")
check("two sources disagree and the memory says so",
      mem.believes("customer:acme", "plan_annual_pro") == "CONTRADICTED")

# refused: nobody approved it
call("POST", "/v1/healing/handle?project=" + PID, {
    "error": {"component": "billing", "error_type": "DoubleCharge"},
    "plan": {"diagnosis": "refund the second capture",
             "actions": [{"type": "issue_refund", "args": {"amount": 1180}},
                         {"type": "update_subscription"}]}}, OWNER)
check("the unapproved refund did not move money", LEDGER == [], LEDGER)

# permitted: a named human approved it
call("POST", "/v1/healing/handle?project=" + PID, {
    "error": {"component": "billing", "error_type": "DoubleChargeEscalated"},
    "plan": {"diagnosis": "refund the second capture",
             "actions": [{"type": "issue_refund", "args": {"amount": 1180}}]},
    "approved_by": "reviewer@example.com"}, OWNER)
check("with a named approver it ran exactly once", len(LEDGER) == 1, LEDGER)

# The approval that matters is the one an agent cannot write for itself. This
# key carries heal.execute.high and is bound to an agent, so the only thing
# standing between it and a refund is whether OMEM believes the name it sent.
AGENT_KEY = api.STORE.create_key(PID, "Support agent key", "owner",
                                 agent_id="support-agent")["secret"]
status, agent_try = call("POST", "/v1/healing/handle?project=" + PID, {
    "error": {"component": "billing", "error_type": "DoubleChargeSelfApproved"},
    "plan": {"diagnosis": "refund the second capture",
             "actions": [{"type": "issue_refund", "args": {"amount": 9999}}]},
    "approved_by": "reviewer@example.com"}, AGENT_KEY)
check("an agent holding a high-risk key cannot approve its own refund",
      agent_try.get("status") == "denied", agent_try)
check("and the refusal says the approval came from the agent itself",
      "cannot be approved by the agent" in json.dumps(agent_try), agent_try)
check("no money moved on the agent's own say-so", len(LEDGER) == 1, LEDGER)

# a low-risk action needs no approval, and must not be exported as though it had
call("POST", "/v1/healing/handle?project=" + PID, {
    "error": {"component": "billing", "error_type": "StaleRateCache"},
    "plan": {"diagnosis": "drop the cached rate table",
             "actions": [{"type": "clear_cache"}]}}, OWNER)

print("== the export ==")
client = EX.Client("http://127.0.0.1:%d" % PORT, KEY, PID)
entries = EX.build_record(client)
text = "\n".join(json.dumps(e) for e in entries)
kinds = {}
for e in entries:
    kinds[e["type"]] = kinds.get(e["type"], 0) + 1
print("     entries: " + json.dumps(kinds))

check("the export contains beliefs", kinds.get("belief", 0) >= 3, kinds)
check("the export contains the conflict", kinds.get("conflict", 0) >= 1, kinds)
check("the export contains decisions", kinds.get("decision", 0) >= 2, kinds)
check("the export contains the approval", kinds.get("approval", 0) >= 1, kinds)
check("the export contains an integrity entry", kinds.get("integrity", 0) == 1, kinds)

beliefs = [e for e in entries if e["type"] == "belief"]
check("the denied side is the same proposition with the opposite polarity",
      any(b["polarity"] == "deny" and b["proposition"] == "plan_annual_pro"
          for b in beliefs), beliefs)
check("both contradicted sides are present and neither was dropped",
      len([b for b in beliefs if b["state"] == "contradicted"]) == 2, beliefs)

refusals = [e for e in entries if e["type"] == "decision" and e["verdict"] == "refused"]
check("the refusals are in the record with their reasons",
      len(refusals) >= 2 and all(r["reason"] for r in refusals), refusals)
check("no refused action is recorded as executed",
      all(r["executed"] is False for r in refusals))
# A record that says "unknown" where the action name belongs is useless to the
# auditor it was written for, so every decision has to name what was proposed.
check("every decision names the action it was about",
      all(e["action_type"] != "unknown"
          for e in entries if e["type"] == "decision"),
      [e["action_type"] for e in entries if e["type"] == "decision"])
check("the refused unregistered action is named, not summarised away",
      any(r["action_type"] == "update_subscription" for r in refusals), refusals)
executed = [e for e in entries if e["type"] == "decision" and e["executed"]]
by_type = {e["action_type"]: e for e in executed}
check("the refund that ran is reported at the registry's risk class",
      by_type["issue_refund"]["risk_class"] == "high", by_type.get("issue_refund"))
# The risk column has to come from the registry rather than be reconstructed
# from what happened: a low-risk action runs without an approval, and an
# exporter guessing from "was this approved" would mislabel exactly this case.
check("a low-risk action that ran without approval is reported as low",
      by_type["clear_cache"]["risk_class"] == "low", by_type.get("clear_cache"))
check("and it carries no approval, because none was required",
      by_type["clear_cache"]["approval"] is None)

approval = next((e for e in entries if e["type"] == "approval"), None)
check("the approver is a person, not the agent",
      approval and approval["approver"]["kind"] == "human", approval)
check("the approval names where the identity came from",
      approval and approval["identity_source"] == "api-key", approval)
# The identity is what the authentication layer resolved. The name the caller
# sent is kept as a label, because a string in a request body is a claim about
# a person and not a person.
check("the approver identity is the authenticated principal, not the sent name",
      approval and approval["approver"]["id"].startswith("key:"), approval)
check("the name the caller supplied is kept, as a label rather than as proof",
      approval and approval["approver"]["name"] == "reviewer@example.com", approval)
check("the approver is not the agent that proposed the action",
      approval and approval["approver"]["id"]
      != by_type["issue_refund"]["proposed_by"]["id"], approval)

print("== the published validator's verdict on OMEM's own export ==")
report = TV.validate(text)
for c in report.checks:
    if not c["ok"]:
        print("     unmet: %s (%s) %s" % (c["check"], c["level"], c["detail"][:120]))
print("     conformance: " + str(report.level))
check("OMEM's export reaches TR-3, the level the site claims",
      report.level in ("TR-3", "TR-4"), report.level)
check("no TR-1 or TR-2 requirement is unmet",
      not report.failures("TR-1") and not report.failures("TR-2"))

srv.shutdown()
print("\n%d passed, %d failed" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)
