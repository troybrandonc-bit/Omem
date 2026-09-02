"""Approval policy: does it narrow who may approve, and only when paid for?
Run: python3 tests_approval_policy.py

Two properties matter more than the feature itself.

A policy may only ever REFUSE something the open gate already allowed. If a
configuration could talk the gate into permitting what the MIT rules refuse,
the paid component would have made the free one less trustworthy, and everyone
running without a licence would be right to worry.

And an unlicensed install must be TOLD, at the moment it tries to write a
policy, rather than storing one that quietly does nothing. A policy that exists
and is not enforced is the worst of the three states, because it reads as
protection in a security review.
"""
import json
import os
import sys
import threading
import time
import http.client
from http.server import ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, ".."))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "scripts"))

TMP = os.environ.get("TEMP") or "/tmp"
os.environ["OMEM_DB"] = os.path.join(TMP, "omem_approval_policy.db")
os.environ.setdefault("OMEM_SEED_DEMO", "0")
if os.path.exists(os.environ["OMEM_DB"]):
    os.remove(os.environ["OMEM_DB"])

import api  # noqa: E402
import healing as HEAL  # noqa: E402
import licence as LICENCE  # noqa: E402
from ee import approval_policy as AP  # noqa: E402
from sign_licence import public_key, sign, _b64  # noqa: E402
import binascii  # noqa: E402

PASS = FAIL = 0


def check(n, c, d=""):
    global PASS, FAIL
    if c:
        PASS += 1
        print("  ok  " + n)
    else:
        FAIL += 1
        print("  FAIL " + n + "  " + str(d)[:220])


print("== the policy document is checked when it is written ==")
for bad, why in [
    ("not json", "not JSON"),
    ('{"rules": "nope"}', "rules not a list"),
    ('{"rules": [{"approvers": ["a"]}]}', "names neither action nor risk"),
    ('{"rules": [{"risk_class": "spicy", "approvers": ["a"]}]}', "unknown risk class"),
    ('{"rules": [{"risk_class": "high", "approvers": []}]}', "no approvers"),
    ('{"rules": [{"risk_class": "high", "approvers": [""]}]}', "empty approver"),
    ('{"default": "maybe", "rules": []}', "bad default"),
]:
    try:
        AP.parse(bad)
        check("rejected at write time: " + why, False, bad)
    except AP.PolicyError:
        check("rejected at write time: " + why, True)

good = AP.parse('{"default": "deny", "rules": ['
                '{"action_type": "issue_refund", "approvers": ["key:key_fin"]},'
                '{"risk_class": "high", "approvers": ["*"]}]}')
check("a valid policy parses and normalises", good["default"] == "deny"
      and len(good["rules"]) == 2, good)
check("it can be described in words for an auditor",
      "issue_refund may be approved by key:key_fin" in AP.describe(good),
      AP.describe(good))

print("== evaluation ==")
ok, _ = AP.evaluate(good, "issue_refund", "high", "key:key_fin", "")
check("the named principal may approve the action named", ok)
no, why = AP.evaluate(good, "issue_refund", "high", "key:key_other", "")
check("another principal may not, and is told which rule refused",
      not no and "rule 1" in why, why)
check("a later rule does not rescue what an earlier one refused",
      not AP.evaluate(good, "issue_refund", "high", "key:key_other", "")[0])
ok2, _ = AP.evaluate(good, "restart_service", "high", "key:anyone", "")
check("a wildcard rule allows anyone the base gate allowed", ok2)
no3, why3 = AP.evaluate(good, "rebuild_index", "medium", "key:anyone", "")
check("an action no rule covers falls to the default", not no3 and "deny" in why3, why3)
check("and defaults to allow when the policy does not say otherwise",
      AP.evaluate(AP.parse('{"rules": []}'), "anything", "low", "key:x", "")[0])
check("a claimed name can satisfy a rule that names it",
      AP.evaluate(AP.parse('{"rules": [{"risk_class": "high",'
                           ' "approvers": ["fin@acme.com"]}]}'),
                  "issue_refund", "high", "key:key_1", "fin@acme.com")[0])
check("no policy at all permits everything",
      AP.evaluate(None, "issue_refund", "high", "", "")[0])

print("== through the gate, with a licence ==")
LEDGER = []
api.HEAL_ACTIONS.register("issue_refund", HEAL.RISK_HIGH,
                          lambda c, a: (LEDGER.append(a), {"ok": True})[1], "refund")

srv = ThreadingHTTPServer(("127.0.0.1", 0), api.Handler)
PORT = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()
time.sleep(0.3)


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


acct = call("POST", "/v1/signup", {"email": "policy@omem.local"})[1]
KEY, PID = acct["api_key"]["secret"], acct["project"]["id"]
OWNER = api.STORE.create_key(PID, "Owner key", "owner")["secret"]
FINANCE = api.STORE.create_key(PID, "Finance approver", "owner")["secret"]
FINANCE_ID = "key:" + api.STORE.keys_for(PID)[-1]["id"]

POLICY = {"default": "allow", "rules": [
    {"action_type": "issue_refund", "approvers": [FINANCE_ID]}]}

print("-- unlicensed --")
st, body = call("POST", "/v1/healing/policy?project=" + PID, POLICY, OWNER)
check("an unlicensed install refuses to store a policy", st == 402, (st, body))
check("and says what the free gate still does",
      "self-approval" in json.dumps(body), body)
st, seen = call("GET", "/v1/healing/policy?project=" + PID, None, OWNER)
check("nothing was stored", st == 200 and seen["policy"] is None, seen)

print("-- licensed --")
SEED = binascii.unhexlify("9d61b19deffd5a60ba844af492ec2cc44449c5697b32691970"
                          "3bac031cae7f60")
claims = json.dumps({"customer": "Acme", "expires": round(time.time() + 3600),
                     "features": ["approval_policy"]},
                    sort_keys=True, separators=(",", ":")).encode()
TOKEN = _b64(claims) + "." + _b64(sign(SEED, claims))
LICENCE.ISSUER_PUBLIC_KEY = binascii.hexlify(public_key(SEED)).decode()
os.environ["OMEM_LICENCE"] = TOKEN
try:
    st, body = call("POST", "/v1/healing/policy?project=" + PID, POLICY, OWNER)
    check("a licensed install stores the policy", st == 200, (st, body))
    st, seen = call("GET", "/v1/healing/policy?project=" + PID, None, OWNER)
    check("and reports it as enforced, not merely stored",
          seen["licensed"] and seen["enforced"], seen)

    def refund(approver_key, name):
        return call("POST", "/v1/healing/handle?project=" + PID, {
            "error": {"component": "billing", "error_type": "Dup" + name},
            "plan": {"diagnosis": "refund", "actions": [
                {"type": "issue_refund", "args": {"amount": 100}}]},
            "approved_by": name}, approver_key)[1]

    before = len(LEDGER)
    denied = refund(OWNER, "someone@acme.com")
    check("an approver the policy does not name is refused",
          denied.get("status") == "denied", denied)
    check("and the refusal names the rule rather than saying 'policy'",
          "does not list" in json.dumps(denied), denied)
    check("no money moved", len(LEDGER) == before, LEDGER)

    allowed = refund(FINANCE, "fin@acme.com")
    check("the approver the policy names may approve",
          allowed.get("status") in ("failed", "recovered"), allowed)
    check("and the refund actually ran", len(LEDGER) == before + 1, LEDGER)

    print("-- policy can only ever narrow, never widen --")
    # a wide-open policy must not rescue an agent trying to approve itself
    call("POST", "/v1/healing/policy?project=" + PID,
         {"default": "allow", "rules": [{"risk_class": "high", "approvers": ["*"]}]},
         OWNER)
    agent_key = api.STORE.create_key(PID, "Agent 2", "owner",
                                     agent_id="support-agent")["secret"]
    before = len(LEDGER)
    selfapp = call("POST", "/v1/healing/handle?project=" + PID, {
        "error": {"component": "billing", "error_type": "SelfApprove"},
        "plan": {"diagnosis": "refund", "actions": [
            {"type": "issue_refund", "args": {"amount": 999}}]},
        "approved_by": "fin@acme.com"}, agent_key)[1]
    check("a wildcard policy still cannot let an agent approve itself",
          selfapp.get("status") == "denied", selfapp)
    check("and the reason is the free gate's, not the policy's",
          "cannot be approved by the agent" in json.dumps(selfapp), selfapp)
    check("still no money moved", len(LEDGER) == before, LEDGER)
finally:
    os.environ.pop("OMEM_LICENCE", None)

print("== when the licence lapses ==")
check("the stored policy stops being enforced",
      call("GET", "/v1/healing/policy?project=" + PID, None, OWNER)[1]["enforced"]
      is False)
before = len(LEDGER)
lapsed = call("POST", "/v1/healing/handle?project=" + PID, {
    "error": {"component": "billing", "error_type": "Lapsed"},
    "plan": {"diagnosis": "refund", "actions": [
        {"type": "issue_refund", "args": {"amount": 50}}]},
    "approved_by": "someone@acme.com"}, OWNER)[1]
check("and the free gate still runs, so a billing lapse is not an outage",
      lapsed.get("status") in ("failed", "recovered"), lapsed)
check("the refund the free rules allow goes through", len(LEDGER) == before + 1)

srv.shutdown()
print("\n%d passed, %d failed" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)
