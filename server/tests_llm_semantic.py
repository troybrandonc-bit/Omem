"""Semantic LLM layer integration. Run: python3 tests_llm_semantic.py

Drives the REAL wiring (factory -> SemanticGmailExtractor -> validation ->
quality gate -> frozen engine) with a scripted fake LLM, asserting:

  * the model receives the FULL email + identity + roles + existing memories
  * a valid candidate flows through the gate into the engine
  * invented entities are dropped (anti-hallucination allow-list)
  * evidence that is not an exact substring is dropped
  * QUESTION candidates never become facts
  * a reversal ("ignore my previous email") supersedes the old belief through
    the ENGINE's op, old belief closed, history preserved
  * marketing is rejected WITH a recorded rejection_reason (observability)
  * malformed model output falls back to the deterministic extractor + error row
  * escalation: low-confidence NON_BUSINESS mail REACHES the model
  * observe(): a raw interaction stream forms memory end-to-end

The real provider path (an actual OpenAI-compatible API) is NOT VERIFIED here:
no credentials exist in this environment. The interface is identical.
"""
import base64
import json
import os
import sys
import threading
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
DB = "/tmp/omem_llm_semantic.db"
if os.path.exists(DB):
    os.remove(DB)
os.environ["OMEM_DB"] = DB
os.environ["OMEM_LLM_API_KEY"] = "fake-key-for-wiring-tests"  # makes llm_configured() true

import api  # noqa: E402
import providers  # noqa: E402
from connectors import GmailTransport  # noqa: E402
from http.server import ThreadingHTTPServer  # noqa: E402

PASS = FAIL = 0


def check(n, c, d=""):
    global PASS, FAIL
    if c:
        PASS += 1; print(f"  ok  {n}")
    else:
        FAIL += 1; print(f"  FAIL {n}  {d}")


OWNER = "troy@kronos.com"


class FakeLLM:
    """Scripted per-email responses, keyed on a marker in the prompt. Records
    every prompt so tests can assert what the model was actually shown."""
    prompts: list[str] = []
    model = "fake-scripted-model"

    def complete(self, system, user):
        FakeLLM.prompts.append(user)
        j = json.dumps
        if "MARKER_GOOD" in user:
            return j({"business_relevance": "high", "memory_candidate": True,
                      "rejection_reason": None,
                      "reasoning_summary": "Customer explicitly decided to renew the annual contract.",
                      "candidates": [{
                          "memory_type": "customer_decision",
                          "actor": "company:acme", "subject": "company:acme",
                          "proposition": "decided_to_renew", "speech_act": "DECISION",
                          "certainty": "high", "temporal_status": "current",
                          "evidence": [{"quote": "we have decided to renew the annual contract"}],
                          "confidence": 0.93,
                          "existing_memory_relationship": None}]})
        if "MARKER_INVENT" in user:
            return j({"business_relevance": "high", "memory_candidate": True,
                      "rejection_reason": None, "reasoning_summary": "x",
                      "candidates": [{
                          "memory_type": "customer_decision",
                          "actor": "company:globex", "subject": "company:globex",
                          "proposition": "decided_to_renew", "speech_act": "DECISION",
                          "certainty": "high", "temporal_status": "current",
                          "evidence": [{"quote": "we have decided"}],
                          "confidence": 0.9,
                          "existing_memory_relationship": None}]})
        if "MARKER_BADQUOTE" in user:
            return j({"business_relevance": "high", "memory_candidate": True,
                      "rejection_reason": None, "reasoning_summary": "x",
                      "candidates": [{
                          "memory_type": "customer_decision",
                          "actor": "company:acme", "subject": "company:acme",
                          "proposition": "has_cancelled", "speech_act": "COMPLETED",
                          "certainty": "high", "temporal_status": "current",
                          "evidence": [{"quote": "we hereby cancel everything immediately"}],
                          "confidence": 0.9,
                          "existing_memory_relationship": None}]})
        if "MARKER_QUESTION" in user:
            return j({"business_relevance": "medium", "memory_candidate": True,
                      "rejection_reason": None, "reasoning_summary": "x",
                      "candidates": [{
                          "memory_type": "inquiry",
                          "actor": "company:acme", "subject": "company:acme",
                          "proposition": "wants_to_upgrade", "speech_act": "QUESTION",
                          "certainty": "low", "temporal_status": "current",
                          "evidence": [{"quote": "Could we upgrade our plan"}],
                          "confidence": 0.8,
                          "existing_memory_relationship": None}]})
        if "MARKER_REVERSAL" in user:
            return j({"business_relevance": "high", "memory_candidate": True,
                      "rejection_reason": None,
                      "reasoning_summary": "The customer reversed their earlier cancellation intent and decided to renew.",
                      "candidates": [{
                          "memory_type": "customer_decision",
                          "actor": "company:acme", "subject": "company:acme",
                          "proposition": "decided_to_renew", "speech_act": "DECISION",
                          "certainty": "high", "temporal_status": "current",
                          "evidence": [{"quote": "ignore my previous email - we have decided to renew after all"}],
                          "confidence": 0.95,
                          "existing_memory_relationship": {
                              "relation": "supersedes",
                              "target_proposition": "intends_to_cancel"}}]})
        if "MARKER_MARKETING" in user:
            return j({"business_relevance": "none", "memory_candidate": False,
                      "rejection_reason": "marketing",
                      "reasoning_summary": "Bulk promotional mail; no relationship information.",
                      "candidates": []})
        if "MARKER_MALFORMED" in user:
            return "I think this email is about a renewal! Definitely important."
        if "MARKER_CANCELINTENT" in user:
            return j({"business_relevance": "high", "memory_candidate": True,
                      "rejection_reason": None,
                      "reasoning_summary": "Customer states an intention to cancel at quarter end.",
                      "candidates": [{
                          "memory_type": "churn_risk",
                          "actor": "company:acme", "subject": "company:acme",
                          "proposition": "intends_to_cancel", "speech_act": "INTENTION",
                          "certainty": "high", "temporal_status": "future",
                          "evidence": [{"quote": "We intend to cancel our contract at the end of the quarter."}],
                          "confidence": 0.9,
                          "existing_memory_relationship": None}]})
        if "MARKER_ESCALATED" in user:
            return j({"business_relevance": "medium", "memory_candidate": True,
                      "rejection_reason": None,
                      "reasoning_summary": "Terse but genuine churn signal from a customer.",
                      "candidates": [{
                          "memory_type": "churn_risk",
                          "actor": "company:acme", "subject": "company:acme",
                          "proposition": "considering_cancel", "speech_act": "CONSIDERATION",
                          "certainty": "medium", "temporal_status": "current",
                          "evidence": [{"quote": "might stop soon tbh"}],
                          "confidence": 0.85,
                          "existing_memory_relationship": None}]})
        return j({"business_relevance": "none", "memory_candidate": False,
                  "rejection_reason": "irrelevant", "reasoning_summary": "n/a",
                  "candidates": []})


# route the factory's OpenAICompatClient to the fake (same interface)
providers.OpenAICompatClient = lambda *a, **k: FakeLLM()

srv = ThreadingHTTPServer(("127.0.0.1", 0), api.Handler)
PORT = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()
time.sleep(0.2)


def call(m, path, body=None, key=None):
    r = urllib.request.Request(f"http://127.0.0.1:{PORT}{path}", method=m,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Content-Type": "application/json",
                 **({"Authorization": f"Bearer {key}"} if key else {})})
    try:
        with urllib.request.urlopen(r, timeout=20) as resp:
            return resp.status, json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def msg(mid, frm, subj, body, ts, thread=None, extra=""):
    raw = f"From: {frm}\r\nTo: {OWNER}\r\nSubject: {subj}\r\n{extra}\r\n{body}\r\n"
    return {"id": mid, "threadId": thread or mid, "internalDate": str(ts),
            "raw": base64.urlsafe_b64encode(raw.encode()).decode()}


MAILBOX = []


class T(GmailTransport):
    def list_messages(self, token, cursor):
        return (MAILBOX, "done")


api.GMAIL_TRANSPORT_FACTORY = lambda conn: T()
_, acct = call("POST", "/v1/signup", {"email": "llm@kronos.com"})
KEY, PID, SESS = acct["api_key"]["secret"], acct["project"]["id"], acct["token"]
call("POST", f"/v1/identity?project={PID}",
     {"company_name": "Kronos", "domains": ["kronos.com"], "emails": [OWNER]}, KEY)
call("POST", f"/v1/settings?project={PID}", {"llm_enabled": "1"}, KEY)
_, beg = call("POST", f"/v1/oauth/gmail/begin?project={PID}", {"name": "G"}, KEY)
CID = beg["connector_id"]
call("POST", f"/v1/oauth/gmail/callback?project={PID}", {"connector_id": CID, "account": OWNER}, KEY)


def drain():
    call("POST", f"/v1/connectors/{CID}/poll?project={PID}", {}, KEY)
    return call("POST", f"/v1/ingest/process?project={PID}", {}, KEY)[1]


print("== the model sees the FULL context ==")
MAILBOX.append(msg("g1", "jane@acme.com", "Renewal MARKER_GOOD",
                   "Hi Troy, quick note between meetings.\n\nAfter our board call, "
                   "we have decided to renew the annual contract. MARKER_GOOD\n\n"
                   "Best,\nJane", 1000))
drain()
prompt = FakeLLM.prompts[-1]
check("full body included (not a keyword snippet)",
      "quick note between meetings" in prompt and "Best,\nJane" in prompt)
check("identity block included", "Kronos" in prompt and "kronos.com" in prompt)
check("allowed entities enumerated", "company:acme" in prompt and "company:kronos" in prompt)
check("direction stated", "inbound" in prompt)

print("== valid candidate reaches the engine ==")
_, mem = call("POST", f"/v1/recall?project={PID}", {"about": "company:acme"}, KEY)
props = {m["proposition"]: m["state"] for m in mem["memories"]}
check("decided_to_renew is believed", props.get("decided_to_renew") == "BELIEVED_TRUE", str(props))
_, diag_fd = call("GET", f"/v1/fact-decisions?project={PID}", None, SESS)
check("gate recorded the model's reasoning",
      any("Model:" in r for d in diag_fd["data"]
          for r in (d["reasons"] if isinstance(d["reasons"], list) else json.loads(d["reasons"] or "[]"))))

print("== anti-hallucination ==")
MAILBOX.append(msg("g2", "jane@acme.com", "Re MARKER_INVENT",
                   "As discussed, we have decided. MARKER_INVENT", 2000))
MAILBOX.append(msg("g3", "jane@acme.com", "Re MARKER_BADQUOTE",
                   "Nothing was cancelled here. MARKER_BADQUOTE", 3000))
MAILBOX.append(msg("g4", "jane@acme.com", "Plan MARKER_QUESTION",
                   "Could we upgrade our plan? MARKER_QUESTION", 4000))
drain()
_, mem = call("POST", f"/v1/recall?project={PID}", {"about": "company:globex"}, KEY)
check("invented entity produced NO memory", mem["memories"] == [], str(mem["memories"]))
_, mem = call("POST", f"/v1/recall?project={PID}", {"about": "company:acme"}, KEY)
props = {m["proposition"] for m in mem["memories"]}
check("non-substring evidence dropped (no has_cancelled)", "has_cancelled" not in props, str(props))
check("QUESTION never becomes a fact (no wants_to_upgrade)", "wants_to_upgrade" not in props, str(props))
row = api.STORE.db.execute(
    "SELECT dropped FROM semantic_analyses WHERE source_record_id IN "
    "(SELECT id FROM source_records WHERE external_id='g3') ORDER BY id DESC LIMIT 1").fetchone()
check("drop reason recorded for bad evidence",
      row and "not found verbatim" in (row["dropped"] or ""), str(dict(row) if row else None))

print("== reversal supersedes through the ENGINE ==")
MAILBOX.append(msg("g5", "sam@bravado.io", "Cancelling", "We intend to cancel our subscription next month.", 5000))
drain()
# plant sequence on acme: intends_to_cancel (deterministic path via g5 is bravado;
# create acme's intent via observe with deterministic extractor off? use direct mail)
MAILBOX.append(msg("g6", "jane@acme.com", "Cancelling MARKER_CANCELINTENT",
                   "We intend to cancel our contract at the end of the quarter. MARKER_CANCELINTENT", 6000))
drain()
_, mem = call("POST", f"/v1/recall?project={PID}", {"about": "company:acme"}, KEY)
props = {m["proposition"]: m["state"] for m in mem["memories"]}
had_intent = props.get("intends_to_cancel") == "BELIEVED_TRUE"
check("cancellation intent believed first", had_intent, str(props))
MAILBOX.append(msg("g7", "jane@acme.com", "Re: Cancelling MARKER_REVERSAL",
                   "ignore my previous email - we have decided to renew after all MARKER_REVERSAL",
                   7000, thread="g6"))
drain()
_, mem = call("POST", f"/v1/recall?project={PID}", {"about": "company:acme"}, KEY)
props = {m["proposition"]: m["state"] for m in mem["memories"]}
check("renewal now believed", props.get("decided_to_renew") == "BELIEVED_TRUE", str(props))
check("old intent no longer believed", props.get("intends_to_cancel") != "BELIEVED_TRUE", str(props))
p = api.PROJECTS[PID]
old = [a for a in p.engine.store.assertions()
       if a.proposition == "intends_to_cancel" and "company:acme" in a.subjects]
check("history preserved (old assertion exists, closed)",
      len(old) >= 1 and not p.engine.ledger.is_open_at(old[0], p.now()))

print("== rejection observability ==")
# ambiguous: human tone + promotional intent - exactly the mail the cheap
# layer cannot judge (NON_BUSINESS at 0.03 confidence) and must escalate
MAILBOX.append(msg("g8", "maria@shop.io", "Following up from the expo MARKER_MARKETING",
                   "Hi Troy, great meeting you at the expo! We are running 50% off "
                   "this month if you want to try us out. MARKER_MARKETING", 8000))
drain()
row = api.STORE.db.execute(
    "SELECT * FROM semantic_analyses WHERE source_record_id IN "
    "(SELECT id FROM source_records WHERE external_id='g8') ORDER BY id DESC LIMIT 1").fetchone()
check("marketing rejected with reason persisted",
      row and row["rejection_reason"] == "marketing" and row["memory_candidate"] == 0,
      str(dict(row) if row else None))
check("reasoning summary persisted (no chain-of-thought)",
      row and "promotional" in (row["reasoning_summary"] or ""))

print("== malformed model output: fallback + error recorded ==")
MAILBOX.append(msg("g9", "jane@acme.com", "Terms MARKER_MALFORMED",
                   "Hi Troy, we agreed the annual contract will be EUR 24,000. MARKER_MALFORMED", 9000))
drain()
row = api.STORE.db.execute(
    "SELECT error FROM semantic_analyses WHERE source_record_id IN "
    "(SELECT id FROM source_records WHERE external_id='g9') ORDER BY id DESC LIMIT 1").fetchone()
check("model error recorded", row and "non-JSON" in (row["error"] or ""), str(dict(row) if row else None))
_, mem = call("POST", f"/v1/recall?project={PID}", {"about": "company:acme"}, KEY)
props = {m["proposition"] for m in mem["memories"]}
check("deterministic fallback still extracted the contract value",
      "contract_value_eur_24_000" in props, str(props))

print("== escalation: ambiguous mail REACHES the model ==")
before = len(FakeLLM.prompts)
MAILBOX.append(msg("g10", "jane@acme.com", "hey MARKER_ESCALATED",
                   "Hi Troy, been mulling over our setup lately. might stop soon tbh. MARKER_ESCALATED\n\nJane", 10000))
drain()
check("low-confidence NON_BUSINESS escalated to the LLM",
      len(FakeLLM.prompts) > before, f"{len(FakeLLM.prompts)} vs {before}")
_, mem = call("POST", f"/v1/recall?project={PID}", {"about": "company:acme"}, KEY)
props = {m["proposition"]: m["state"] for m in mem["memories"]}
check("churn signal from terse mail became memory",
      props.get("considering_cancel") == "BELIEVED_TRUE", str(props))

print("== confident noise still never reaches the model ==")
MAILBOX.append(msg("g11", "news@spamco.io", "MEGA SALE",
                   "Buy now! 70% off! Click here! Unsubscribe here! View in browser!", 11000,
                   extra="List-Unsubscribe: <mailto:u@spamco.io>\r"))
drain()
check("confident noise never reaches semantic extraction (no LLM spend)",
      not any("MEGA SALE" in pr for pr in FakeLLM.prompts))
row = api.STORE.db.execute(
    "SELECT id FROM semantic_analyses WHERE source_record_id IN "
    "(SELECT id FROM source_records WHERE external_id='g11')").fetchone()
check("no semantic analysis row for confident noise", row is None)

print("== observe(): raw interaction stream ==")
_, ob = call("POST", f"/v1/observe?project={PID}",
             {"agent": "agent:support", "interaction":
              {"text": "Customer confirmed: we have decided to renew the annual contract. MARKER_GOOD",
               "speaker": "jane@acme.com", "audience": OWNER}}, KEY)
check("observe formed memory with evidence",
      ob.get("memories") and ob["memories"][0]["proposition"] == "decided_to_renew"
      and ob["memories"][0]["evidence"], str(ob)[:200])
_, ob2 = call("POST", f"/v1/observe?project={PID}",
              {"agent": "agent:support", "interaction":
               {"text": "ok sounds good talk tomorrow"}}, KEY)
check("small talk observed but NOT remembered",
      ob2.get("observed") and ob2["memories"] == [], str(ob2)[:150])

srv.shutdown()
print(f"\n{PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
