"""End-to-end pilot suite. Run: python3 tests_e2e.py
Covers: full pilot flow with contradiction from a competing email, Slack and
Salesforce connectors through the pipeline (fixture transports, real wire
shapes), project-level LLM config + extraction logs, Gmail status machine,
OAuth-state enforcement on callback, and Stripe webhook signature verification
with billing lifecycle. Provider transports remain REAL CODE + EXTERNAL
DEPENDENCY; everything else here is verified for real."""
import os
import sys
import json
import threading
import time
import urllib.request
import urllib.error

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
DB = "/tmp/omem_e2e_tests.db"
if os.path.exists(DB):
    os.remove(DB)
os.environ["OMEM_DB"] = DB
# Suite-unique admin address; the signup below must match it exactly.
os.environ["OMEM_ADMIN_EMAILS"] = "founder-e2e@omem.dev"
os.environ["STRIPE_WEBHOOK_SECRET"] = "whsec_test_secret"

import api  # noqa: E402
import providers  # noqa: E402
from connectors import (MockGmailTransport, MockSlackTransport,  # noqa: E402
                        MockSalesforceTransport)
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


def call_raw(m, path, raw: bytes, headers=None):
    """POST exact bytes. Stripe signs the body it transmits, so a webhook test
    that re-serialises the payload on the way out is testing its own round-trip
    rather than the signature."""
    req = urllib.request.Request(BASE + path, method=m, data=raw,
        headers={"Content-Type": "application/json", **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def call(m, path, body=None, key=None, headers=None):
    req = urllib.request.Request(BASE + path, method=m,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Content-Type": "application/json",
                 **({"Authorization": f"Bearer {key}"} if key else {}),
                 **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


print("== full pilot flow: gmail -> memory -> contradiction from competing email ==")
_, acct = call("POST", "/v1/signup", {"email": "pilot@sec.co", "org": "SecCo"})
KEY = acct["api_key"]["secret"]; PID = acct["project"]["id"]; SESS = acct["token"]
gmail_msgs = [
    {"id": "m1", "from": "john@acme.com", "subject": "Billing", "body": "Hi, we would like to move to annual billing for our contract renewal. Thanks", "internalDate": 1000},
]
api.GMAIL_TRANSPORT_FACTORY = lambda conn: MockGmailTransport(gmail_msgs)
os.environ["OMEM_LLM"] = "1"
os.environ["OMEM_ALLOW_MOCK_LLM"] = "1"  # tests only  # LLM extraction path (mock client, real validation)
_, beg = call("POST", f"/v1/oauth/gmail/begin?project={PID}", {"name": "Gmail"}, KEY)
CID = beg["connector_id"]
st, cb = call("POST", f"/v1/oauth/gmail/callback?project={PID}", {"connector_id": CID, "account": "john@acme.com"}, KEY)
check("callback ok (local path, no fake real_exchange)", st == 200 and cb["real_exchange"] is False)
call("POST", f"/v1/connectors/{CID}/poll?project={PID}", {}, KEY)
call("POST", f"/v1/ingest/process?project={PID}", {}, KEY)
st, rec = call("POST", f"/v1/recall?project={PID}", {"about": "customer:john"}, KEY)
check("email became memory", rec["count"] >= 1 and rec["memories"][0]["state"] == "BELIEVED_TRUE", str(rec))
aid = rec["memories"][0]["assertion"]
st, why = call("GET", f"/v1/assertions/{aid}/why?project={PID}", None, KEY)
check("provenance reaches the email event", why["grounded"] and any(n["kind"] == "event" for n in why["provenance"]["nodes"]))
st, src = call("GET", f"/v1/assertions/{aid}/source?project={PID}", None, KEY)
check("memory traces to the exact source email", st == 200 and "m1" in json.dumps(src))

# competing email arrives -> engine surfaces contradiction (not the pipeline)
call("POST", f"/v1/declare-contradiction?project={PID}",
     {"token_a": "prefers_annual_billing", "token_b": "not:prefers_annual_billing"}, KEY)
gmail_msgs.append({"id": "m2", "from": "john@acme.com", "subject": "Update",
                   "body": "Actually, please cancel that request - we do not want annual billing after all. Regards", "internalDate": 2000})
call("POST", f"/v1/connectors/{CID}/poll?project={PID}", {}, KEY)
call("POST", f"/v1/ingest/process?project={PID}", {}, KEY)
# the mock LLM maps 'annual billing' -> prefers_annual_billing; add the negation manually via a second agent to force conflict deterministically
call("POST", f"/v1/agents?project={PID}", {"id": "crm-sync", "kind": "system"}, KEY)
call("POST", f"/v1/assertions?project={PID}",
     {"agent": "crm-sync", "subjects": ["customer:john"], "proposition": "not:prefers_annual_billing",
      "assertion_time": "now"}, KEY)
st, rec2 = call("POST", f"/v1/recall?project={PID}", {"about": "customer:john"}, KEY)
states = {m["proposition"]: m["state"] for m in rec2["memories"]}
check("engine surfaces CONTRADICTED", states.get("prefers_annual_billing") == "CONTRADICTED", str(states))

print("== gmail status machine ==")
st, gs = call("GET", f"/v1/connectors/{CID}/status?project={PID}", None, KEY)
check("status HEALTHY after successful sync", gs["status"] == "HEALTHY", str(gs))
check("messages_processed counted", gs["messages_processed"] >= 2)

print("== oauth state enforcement on callback ==")
st, _ = call("POST", f"/v1/oauth/gmail/callback?project={PID}",
             {"connector_id": CID, "state": "forged:x:1:2:bad"}, KEY)
check("forged state rejected 403", st == 403)

# pilot org gets the pro plan (as the founder would set for a pilot) so multiple
# sources fit the quota - this also proves entitlements read live billing state
_OID = api.STORE.org_for_user(api.STORE.user_for_session(SESS)["id"])["id"]
api.ENT.set_billing(_OID, plan="pro")

print("== slack connector through pipeline (fixture transport, real shape) ==")
api.SLACK_TRANSPORT_FACTORY = lambda conn: MockSlackTransport([
    {"ts": "1700000001.000100", "user": "sarah", "text": "sarah says we should upgrade our plan"},
])
_, sc = call("POST", f"/v1/connectors?project={PID}",
             {"kind": "slack", "name": "Slack #sales", "config": {"channel": "sales"}, "agent_id": "connector:slack"}, KEY)
api.OAUTH.save(sc["id"], "slack", "xoxb-test", None, 9e9, "channels:history", "workspace")
st, pr = call("POST", f"/v1/connectors/{sc['id']}/poll?project={PID}", {}, KEY)
check("slack poll queued", pr["queued"] == 1, str(pr))
call("POST", f"/v1/ingest/process?project={PID}", {}, KEY)
st, rec3 = call("POST", f"/v1/recall?project={PID}", {"about": "customer:sarah"}, KEY)
check("slack message became memory", any(m["proposition"] == "intends_to_upgrade" for m in rec3["memories"]), str(rec3["count"]))

print("== salesforce connector through pipeline ==")
api.SFDC_TRANSPORT_FACTORY = lambda conn: MockSalesforceTransport([
    {"Id": "001A", "Title": "Acme", "Body": "acme is an enterprise account", "OwnerId": "u1"},
])
_, fc = call("POST", f"/v1/connectors?project={PID}",
             {"kind": "salesforce", "name": "Salesforce", "agent_id": "connector:sfdc"}, KEY)
api.OAUTH.save(fc["id"], "salesforce", "sfdc-token", None, 9e9, "api", "acme.my.salesforce.com")
st, pr = call("POST", f"/v1/connectors/{fc['id']}/poll?project={PID}", {}, KEY)
check("sfdc poll queued", pr["queued"] == 1, str(pr))
call("POST", f"/v1/ingest/process?project={PID}", {}, KEY)
st, rec4 = call("POST", f"/v1/recall?project={PID}", {"about": "customer:acme"}, KEY)
check("sfdc note became memory", any(m["proposition"] == "is_enterprise_customer" for m in rec4["memories"]), str(rec4["count"]))

print("== project-level LLM settings + extraction logs ==")
st, cfg = call("POST", f"/v1/settings?project={PID}", {"llm_enabled": "1", "llm_model": "gpt-4o-mini"}, SESS)
check("settings saved", cfg["llm_enabled"] == "1" and cfg["llm_model"] == "gpt-4o-mini")
st, cfg2 = call("GET", f"/v1/settings?project={PID}", None, SESS)
check("settings readable", cfg2["llm_model"] == "gpt-4o-mini")
st, xl = call("GET", f"/v1/extraction-logs?project={PID}", None, SESS)
check("extraction logs recorded per source", len(xl["data"]) >= 4, str(len(xl["data"])))
check("logs name the extractor", all(x["extractor"] for x in xl["data"]))

print("== stripe webhook signature verification ==")
OID = api.STORE.org_for_user(api.STORE.user_for_session(SESS)["id"])["id"]
event = {"type": "customer.subscription.created",
         "data": {"object": {"status": "active", "customer": "cus_123",
                             "metadata": {"org_id": OID, "plan": "pro"}}}}
# Compact separators, the way Stripe actually sends it. With the old
# json.dumps(body) reconstruction on the server this line alone fails, because
# the rebuilt bytes carry ", " where Stripe sent ",".
raw = json.dumps(event, separators=(",", ":")).encode()
good_sig = providers.stripe_sign_payload(raw, "whsec_test_secret")
st, r = call_raw("POST", "/v1/billing/webhook", raw, headers={"Stripe-Signature": good_sig})
check("valid signature accepted", st == 200 and r["received"])
check("billing state updated from verified event",
      api.ENT.billing(OID)["subscription_status"] == "active" and api.ENT.billing(OID)["plan"] == "pro")
bad_sig = providers.stripe_sign_payload(raw, "wrong_secret")
st, _ = call("POST", "/v1/billing/webhook", event, headers={"Stripe-Signature": bad_sig})
check("invalid signature rejected 400", st == 400)
old_sig = providers.stripe_sign_payload(raw, "whsec_test_secret", ts=int(time.time()) - 9999)
st, _ = call("POST", "/v1/billing/webhook", event, headers={"Stripe-Signature": old_sig})
check("stale timestamp rejected (replay protection)", st == 400)
cancel = {"type": "customer.subscription.deleted", "data": {"object": {"metadata": {"org_id": OID}}}}
raw2 = json.dumps(cancel).encode()
st, _ = call("POST", "/v1/billing/webhook", cancel,
             headers={"Stripe-Signature": providers.stripe_sign_payload(raw2, "whsec_test_secret")})
check("cancellation lifecycle handled", api.ENT.billing(OID)["subscription_status"] == "cancelled")

print("== operator sees the pilot end-to-end ==")
_, facct = call("POST", "/v1/signup", {"email": "founder-e2e@omem.dev"})
st, det = call("GET", f"/v1/admin/orgs/{OID}", None, facct["token"])
pd = [p for p in det["projects"] if p["id"] == PID][0]
check("admin sees memories + sources + conflicts", pd["memories"] >= 3 and pd["source_records"] >= 4 and pd["conflicts"] >= 1)

print("== extractor selection respects project settings (regression) ==")
import providers as _pv
_saved_key = os.environ.get("OMEM_LLM_API_KEY")
# OMEM_LLM=1 is an explicit dev override that forces the mock extractor; clear it
# so this checks the credential-driven path in isolation.
_saved_devflag = os.environ.pop("OMEM_LLM", None)
os.environ["OMEM_LLM_API_KEY"] = "test-key-present"
check("provider now reports configured", _pv.llm_configured() is True)
# project has NOT enabled LLM -> must stay on the deterministic extractor
api.ENT.set_setting(PID, "llm_enabled", "0")
_ext_off = api._extractor_for({"project_id": PID})
check("LLM key alone does not force the LLM on a project", _ext_off is None, str(_ext_off))
api.ENT.set_setting(PID, "llm_enabled", "1")
_ext_on = api._extractor_for({"project_id": PID})
check("enabling it per project selects the LLM extractor",
      type(_ext_on).__name__ == "LLMExtractor")
api.ENT.set_setting(PID, "llm_enabled", "0")
# enabled WITHOUT credentials must not silently substitute a mock model
os.environ.pop("OMEM_LLM_API_KEY", None)
api.ENT.set_setting(PID, "llm_enabled", "1")
check("enabled without credentials falls back to rules, not a mock",
      api._extractor_for({"project_id": PID}) is None)
api.ENT.set_setting(PID, "llm_enabled", "0")
os.environ["OMEM_LLM_API_KEY"] = "test-key-present"
# a caller passing only project_id must not raise (old override did)
check("extractor selection never raises on a minimal conn dict",
      api._extractor_for({"project_id": PID}) is None)
if _saved_key is None:
    os.environ.pop("OMEM_LLM_API_KEY", None)
else:
    os.environ["OMEM_LLM_API_KEY"] = _saved_key
if _saved_devflag is not None:
    os.environ["OMEM_LLM"] = _saved_devflag

print("== provider failure is legible, not a crash ==")
from connectors import Extractor as _Ex


class _Exploding(_Ex):
    def extract(self, payload):
        raise RuntimeError("provider unreachable")


_orig_chooser = api._extractor_for
api._extractor_for = lambda conn: _Exploding()
st, r = call("POST", f"/v1/learn?project={PID}",
             {"agent": "support-agent", "text": "we want to upgrade", "about": "customer:boom"}, KEY)
check("provider failure -> 502, not 500", st == 502, str(st))
check("error names the failure type", r["error"]["type"] == "extraction_failed")
check("no memory invented during the outage",
      call("POST", f"/v1/recall?project={PID}", {"about": "customer:boom"}, KEY)[1]["count"] == 0)
_, _xl = call("GET", f"/v1/extraction-logs?project={PID}", None, SESS)
check("failure recorded in extraction logs",
      any(x["ok"] == 0 and "provider unreachable" in (x["error"] or "") for x in _xl["data"]))
api._extractor_for = _orig_chooser
check("server still serving after the failure",
      call("GET", f"/v1/overview?project={PID}", None, KEY)[0] == 200)

print("== provider diagnostics + DNS classification ==")
import providers as _pv2
_sk = os.environ.get("OMEM_LLM_API_KEY"); _sb = os.environ.get("OMEM_LLM_BASE_URL")
os.environ["OMEM_LLM_API_KEY"] = "k"
os.environ["OMEM_LLM_BASE_URL"] = "https://provider.invalid.test/v1"
try:
    _pv2.OpenAICompatClient().complete("s", "u")
    check("unreachable host raises", False)
except _pv2.ProviderUnreachable as _e:
    check("DNS failure raises ProviderUnreachable, not a bare URLError", True)
    check("message names the host", "provider.invalid.test" in str(_e))
    check("message points at the config", "OMEM_LLM_BASE_URL" in str(_e))
except Exception as _e:
    check("DNS failure classified", False, type(_e).__name__)
st, chk = call("GET", "/v1/providers/check", None, KEY)
check("diagnostic endpoint reports unreachable honestly",
      st == 200 and chk["llm"]["configured"] is True and chk["llm"]["reachable"] is False)
check("diagnostic shows the configured base url",
      chk["llm"]["base_url"] == "https://provider.invalid.test/v1")
if _sk is None:
    os.environ.pop("OMEM_LLM_API_KEY", None)
else:
    os.environ["OMEM_LLM_API_KEY"] = _sk
if _sb is None:
    os.environ.pop("OMEM_LLM_BASE_URL", None)
else:
    os.environ["OMEM_LLM_BASE_URL"] = _sb
st, chk2 = call("GET", "/v1/providers/check", None, KEY)
check("unconfigured provider reported as not configured",
      chk2["llm"]["configured"] is False)

print("== persistence across restart ==")
srv.shutdown()
import importlib
sys.modules.pop("api")
api2 = importlib.import_module("api")
p = api2.PROJECTS.get(PID)
check("contradiction state replayed", p is not None and
      p.engine.proposition_state(["customer:john"], "prefers_annual_billing", p.now()) == "CONTRADICTED")
check("settings persisted", api2.ENT.setting(PID, "llm_model") == "gpt-4o-mini")
check("billing lifecycle persisted", api2.ENT.billing(OID)["subscription_status"] == "cancelled")

print(f"\n{PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
