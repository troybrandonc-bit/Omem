"""Memory scanner test suite. Run: python3 tests_rescan.py

Covers:
  - VALID, DUPLICATE, UNSUPPORTED, AUTOMATED_NOISE, STALE, LOW_VALUE,
    CONTRADICTED, UNKNOWN classifications
  - Dry-run: scan produces report without modifying memory
  - Apply: retractions go through the frozen retract path; audit survives restart
  - Idempotency: applying twice has no additional effect
  - Review queue: LOW_VALUE/IRRELEVANT items surface; approve retracts; reject keeps
  - Gmail source rescan: reclassified_include / reclassified_exclude
  - Health summary: real metrics, no fabricated numbers
  - API routes: POST /v1/memory/scan, GET /v1/memory/scans/{id},
    POST /v1/memory/scans/{id}/apply, GET /v1/memory/review-queue,
    POST /v1/memory/review-queue/{id}/decide, POST /v1/memory/gmail-rescan,
    GET /v1/memory/health
"""
import base64
import json
import os
import sys
import threading
import time
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
DB = "/tmp/omem_rescan_tests.db"
if os.path.exists(DB):
    os.remove(DB)
os.environ["OMEM_DB"] = DB
import api  # noqa: E402
from connectors import (MockGmailTransport, BusinessFactExtractor)  # noqa: E402
from memory_scanner import MemoryScanner  # noqa: E402
from http.server import ThreadingHTTPServer  # noqa: E402

PASS = FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ok  {name}")
    else:
        FAIL += 1
        print(f"  FAIL {name}  {detail}")


# ── helpers ────────────────────────────────────────────────────────────────
srv = ThreadingHTTPServer(("127.0.0.1", 0), api.Handler)
PORT = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()
time.sleep(0.2)


def call(m, path, body=None, key=None):
    req = urllib.request.Request(
        f"http://127.0.0.1:{PORT}{path}", method=m,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Content-Type": "application/json",
                 **({} if not key else {"Authorization": f"Bearer {key}"})})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def raw_msg(mid, frm, subj, body, thread=None, extra_headers=""):
    hdr = (f"From: {frm}\r\nTo: me@corp.com\r\nSubject: {subj}\r\n"
           f"{extra_headers}\r\n")
    raw = hdr + body + "\r\n"
    return {"id": mid, "threadId": thread or mid, "internalDate": "1700000000000",
            "raw": base64.urlsafe_b64encode(raw.encode()).decode()}


# ── create a project with real memories ──────────────────────────────────
_, acct = call("POST", "/v1/signup", {"email": "scanner@corp.com", "org": "Corp"})
KEY = acct["api_key"]["secret"]
PID = acct["project"]["id"]
SESS = acct["token"]
p = api.PROJECTS[PID]

MAILBOX = [
    # 1. Business email → will become a VALID memory
    raw_msg("m1", "Jane <jane@acme.com>", "Re: contract renewal",
            "Hi, we agreed the annual contract will be EUR 24,000 "
            "and renews every January. Payment terms Net 30. Regards"),
    # 2. Supplier pricing → VALID
    raw_msg("m2", "li@factory.cn", "Re: quotation",
            "Hello, our unit price is USD 3.90 for 10000 units, "
            "MOQ 5000, lead time 25 days. Regards"),
    # 3. Automated noise that still got ingested (old pipeline bug)
    raw_msg("m3", "noreply@alibaba.com", "Your order has shipped",
            "Track your shipment. Order #928173.",
            extra_headers="List-Unsubscribe: <u>\r"),
    # 4. Newsletter (noise)
    raw_msg("m4", "news@saas.io", "Product newsletter",
            "Webinar recap. Unsubscribe here. Limited time 20% off.",
            extra_headers="List-Unsubscribe: <u>\r"),
    # 5. Customer cancellation intent → VALID
    raw_msg("m5", "ops@client.com", "Re: account",
            "Hello, we plan to cancel our subscription at end of term. Regards"),
]


class InboxTransport:
    def list_messages(self, token, cursor):
        return ([], cursor) if cursor else (MAILBOX, "done")


api.GMAIL_TRANSPORT_FACTORY = lambda conn: InboxTransport()

_, beg = call("POST", f"/v1/oauth/gmail/begin?project={PID}", {"name": "Gmail"}, KEY)
CID = beg["connector_id"]
call("POST", f"/v1/oauth/gmail/callback?project={PID}",
     {"connector_id": CID, "account": "me@corp.com"}, KEY)
call("POST", f"/v1/connectors/{CID}/poll?project={PID}", {}, KEY)
call("POST", f"/v1/ingest/process?project={PID}", {}, KEY)

# Verify we have real memories before scanning
_, rec = call("POST", f"/v1/recall?project={PID}", {"about": "company:acme"}, KEY)
check("setup: acme contract memories exist", rec["count"] >= 1, str(rec))
_, rec2 = call("POST", f"/v1/recall?project={PID}", {"about": "company:factory"}, KEY)
check("setup: factory supplier memories exist", rec2["count"] >= 1, str(rec2))


# ────────────────────────────────────────────────────────────────────────────
print("\n== unit: scanner classifications ==")
# ────────────────────────────────────────────────────────────────────────────

scanner = MemoryScanner(
    db=api.STORE.db,
    project=p,
    classifier_fn=lambda payload: __import__("classifier").classify(payload),
    record_fn=api.record,
    mint_fn=api._mint_global,
)

# VALID: fresh scan
scan_id = scanner.start_scan(triggered_by="test", scope="all")
scan = scanner.get_scan(scan_id)
check("scan completes", scan["state"] == "complete", str(scan["state"]))
check("scan examined >0 assertions", scan["examined"] > 0, str(scan["examined"]))

summary = scan["summary"]
check("summary has by_classification", "by_classification" in summary, str(list(summary.keys())))
by_cls = summary["by_classification"]
check("VALID memories detected", by_cls.get("VALID", 0) >= 1, str(by_cls))


# ────────────────────────────────────────────────────────────────────────────
print("\n== AUTOMATED_NOISE: manually inject a bad assertion then rescan ==")
# ────────────────────────────────────────────────────────────────────────────

# Simulate the old pipeline bug: assert a fact from an automated source.
# We do this by creating the assertion directly via the engine through record().
api.record(p, "entity", {"id": "customer:alibaba", "type": "person", "label": "Alibaba noreply"})
api.record(p, "agent", {"id": "test:bad-ingest", "kind": "system", "label": "Bad old ingestion"})
T_bad = p.tick()
api.record(p, "event", {"id": "evt_bad1", "ekind": "email", "event_time": T_bad, "label": "bad email"})
api.record(p, "assert", {
    "id": "a_bad1", "agent": "test:bad-ingest",
    "subjects": ["customer:alibaba"],
    "proposition": "order_shipped_928173",
    "assertion_time": T_bad, "confidence": 0.9,
    "label": "order shipped from alibaba",
})
api.record(p, "derive", {"id": "d_bad1", "consequent": "a_bad1",
                          "antecedents": ["evt_bad1"], "dkind": "extraction"})

# Plant a source record + evidence that links to the alibaba noise email
api.STORE.db.execute(
    "INSERT OR IGNORE INTO source_records(id,project_id,connector_id,external_id,payload,content_hash,received) "
    "VALUES(?,?,?,?,?,?,?)",
    ("src_bad1", PID, CID, "alibaba_noise_1",
     json.dumps({"message_id": "m3", "from": "noreply@alibaba.com",
                 "subject": "Your order has shipped",
                 "body": "Track your shipment. Order #928173.",
                 "headers": {"list-unsubscribe": "<u>"}}),
     "hash_bad1", time.time()))
api.STORE.db.execute(
    "INSERT OR REPLACE INTO assertion_evidence(assertion_id,project_id,source_record_id,"
    "evidence,confidence,extractor,created) VALUES(?,?,?,?,?,?,?)",
    ("a_bad1", PID, "src_bad1",
     '"Track your shipment. Order #928173."', 0.9, "BusinessFactExtractor", time.time()))
api.STORE.db.commit()

scan2_id = scanner.start_scan(triggered_by="test2", scope="all")
scan2 = scanner.get_scan(scan2_id)
by_cls2 = scan2["summary"]["by_classification"]
check("platform-notification memory flagged in second scan",
      by_cls2.get("AUTOMATED_NOISE", 0) + by_cls2.get("IRRELEVANT", 0) >= 1, str(by_cls2))

results2 = (scanner.scan_results(scan2_id, classification="AUTOMATED_NOISE")
            + scanner.scan_results(scan2_id, classification="IRRELEVANT"))
check("noise result points to assertion",
      any(r["assertion_id"] == "a_bad1" for r in results2), str([r["assertion_id"] for r in results2]))
check("noise result has proposed_action=retract",
      all(r["proposed_action"] == "retract" for r in results2), str(results2[:1]))


# ────────────────────────────────────────────────────────────────────────────
print("\n== DUPLICATE detection ==")
# ────────────────────────────────────────────────────────────────────────────

# Assert the same proposition twice for the same entity
api.record(p, "entity", {"id": "customer:dup", "type": "person", "label": "Dup customer"})
api.record(p, "agent", {"id": "test:dup-agent", "kind": "system", "label": "Dup agent"})
T_dup = p.tick()
api.record(p, "event", {"id": "evt_dup1", "ekind": "email", "event_time": T_dup, "label": "dup1"})
api.record(p, "assert", {"id": "a_dup1", "agent": "test:dup-agent",
                          "subjects": ["customer:dup"], "proposition": "prefers_annual_billing",
                          "assertion_time": T_dup})
T_dup2 = p.tick()
api.record(p, "event", {"id": "evt_dup2", "ekind": "email", "event_time": T_dup2, "label": "dup2"})
api.record(p, "assert", {"id": "a_dup2", "agent": "test:dup-agent",
                          "subjects": ["customer:dup"], "proposition": "prefers_annual_billing",
                          "assertion_time": T_dup2})

scan3_id = scanner.start_scan(triggered_by="dup_test", scope="all")
dup_results = scanner.scan_results(scan3_id, classification="DUPLICATE")
check("duplicate detected", len(dup_results) >= 1,
      f"found: {[r['assertion_id'] for r in dup_results]}")
check("duplicate has retract action", all(r["proposed_action"] == "retract" for r in dup_results))


# ────────────────────────────────────────────────────────────────────────────
print("\n== STALE: assertion with missing source record ==")
# ────────────────────────────────────────────────────────────────────────────

api.record(p, "entity", {"id": "customer:stale", "type": "person"})
api.record(p, "agent", {"id": "test:stale-agent", "kind": "system"})
T_stale = p.tick()
api.record(p, "event", {"id": "evt_stale1", "ekind": "email", "event_time": T_stale})
api.record(p, "assert", {"id": "a_stale1", "agent": "test:stale-agent",
                          "subjects": ["customer:stale"], "proposition": "wants_refund",
                          "assertion_time": T_stale})
api.record(p, "derive", {"id": "d_stale1", "consequent": "a_stale1",
                          "antecedents": ["evt_stale1"], "dkind": "extraction"})
# Evidence record pointing to a non-existent source record
api.STORE.db.execute(
    "INSERT OR REPLACE INTO assertion_evidence VALUES(?,?,?,?,?,?,?)",
    ("a_stale1", PID, "src_missing999", '"wants a refund"', 0.8, "Test", time.time()))
api.STORE.db.commit()

scan4_id = scanner.start_scan(triggered_by="stale_test", scope="all")
stale_results = scanner.scan_results(scan4_id, classification="STALE")
check("stale detection: missing source record",
      any(r["assertion_id"] == "a_stale1" for r in stale_results),
      str([r["assertion_id"] for r in stale_results]))


# ────────────────────────────────────────────────────────────────────────────
print("\n== UNSUPPORTED: evidence not in source ==")
# ────────────────────────────────────────────────────────────────────────────

api.record(p, "entity", {"id": "customer:unsup", "type": "person"})
T_unsup = p.tick()
api.record(p, "event", {"id": "evt_unsup1", "ekind": "email", "event_time": T_unsup})
api.record(p, "assert", {"id": "a_unsup1", "agent": "test:bad-ingest",
                          "subjects": ["customer:unsup"], "proposition": "is_vip_customer",
                          "assertion_time": T_unsup})
api.record(p, "derive", {"id": "d_unsup1", "consequent": "a_unsup1",
                          "antecedents": ["evt_unsup1"], "dkind": "extraction"})
api.STORE.db.execute(
    "INSERT OR IGNORE INTO source_records(id,project_id,connector_id,external_id,payload,content_hash,received) "
    "VALUES(?,?,?,?,?,?,?)",
    ("src_unsup1", PID, CID, "unsup_email_1",
     json.dumps({"message_id": "unsup1", "from": "real@co.com",
                 "subject": "Hello", "body": "Thanks for the call."}),
     "hash_unsup1", time.time()))
api.STORE.db.execute(
    "INSERT OR REPLACE INTO assertion_evidence VALUES(?,?,?,?,?,?,?)",
    ("a_unsup1", PID, "src_unsup1",
     '"the CEO told me personally they are VIP"', 0.85, "LLMExtractor", time.time()))
api.STORE.db.commit()

scan5_id = scanner.start_scan(triggered_by="unsup_test", scope="all")
unsup_results = scanner.scan_results(scan5_id, classification="UNSUPPORTED")
check("unsupported: evidence span absent from source",
      any(r["assertion_id"] == "a_unsup1" for r in unsup_results),
      str([r["assertion_id"] for r in unsup_results]))


# ────────────────────────────────────────────────────────────────────────────
print("\n== CONTRADICTED: engine already knows ==")
# ────────────────────────────────────────────────────────────────────────────

api.record(p, "entity", {"id": "customer:contra", "type": "person"})
api.record(p, "declare", {"token_a": "prefers_phone", "token_b": "not:prefers_phone"})
T_c1 = p.tick()
api.record(p, "event", {"id": "evt_c1", "ekind": "email", "event_time": T_c1})
api.record(p, "assert", {"id": "a_c1", "agent": "test:bad-ingest",
                          "subjects": ["customer:contra"], "proposition": "prefers_phone",
                          "assertion_time": T_c1})
T_c2 = p.tick()
api.record(p, "event", {"id": "evt_c2", "ekind": "email", "event_time": T_c2})
api.record(p, "assert", {"id": "a_c2", "agent": "test:bad-ingest",
                          "subjects": ["customer:contra"], "proposition": "not:prefers_phone",
                          "assertion_time": T_c2})

scan6_id = scanner.start_scan(triggered_by="contra_test", scope="all")
contra_results = scanner.scan_results(scan6_id, classification="CONTRADICTED")
check("contradicted: engine state reflected in scan",
      len(contra_results) >= 1, str(contra_results[:1]))
check("contradicted: no proposed action (engine handles it)",
      all(r["proposed_action"] is None for r in contra_results))


# ────────────────────────────────────────────────────────────────────────────
print("\n== dry-run: scan does NOT modify memory ==")
# ────────────────────────────────────────────────────────────────────────────

before_count = sum(1 for a in p.engine.store.assertions()
                   if p.engine.ledger.is_open_at(a, p.now()))
scan_dry_id = scanner.start_scan(triggered_by="dry_run_test")
after_count = sum(1 for a in p.engine.store.assertions()
                  if p.engine.ledger.is_open_at(a, p.now()))
check("dry-run: assertion count unchanged", before_count == after_count,
      f"before={before_count} after={after_count}")

dry_scan = scanner.get_scan(scan_dry_id)
proposed = dry_scan["summary"].get("proposed_retractions", 0)
check("dry-run: proposed_retractions > 0 (bad memories detected)", proposed > 0, str(proposed))


# ────────────────────────────────────────────────────────────────────────────
print("\n== apply corrections ==")
# ────────────────────────────────────────────────────────────────────────────

from omem_engine.canon import RETRACTED as _RETRACTED
def _open_beliefs():
    return sum(1 for a in p.engine.store.assertions()
               if a.proposition != _RETRACTED and p.engine.ledger.is_open_at(a, p.now()))
apply_scan_id = scanner.start_scan(triggered_by="apply_test")
before_open = _open_beliefs()
result = scanner.apply_corrections(apply_scan_id)
after_open = _open_beliefs()
check("apply: at least one retraction committed", result["retracted"] >= 1, str(result))
check("apply: open belief count decreased", after_open < before_open,
      f"before={before_open} after={after_open}")
check("apply: no errors during correction", result["errors"] == 0, str(result))

# Verify the alibaba assertion is now closed
bad_a = p.engine.store.assertion("a_bad1")
check("apply: alibaba assertion is now closed",
      bad_a is None or not p.engine.ledger.is_open_at(bad_a, p.now()))


# ────────────────────────────────────────────────────────────────────────────
print("\n== idempotency: apply twice has no additional effect ==")
# ────────────────────────────────────────────────────────────────────────────

result2 = scanner.apply_corrections(apply_scan_id)
after_open2 = _open_beliefs()
check("idempotent: second apply retracts 0 more", result2["retracted"] == 0, str(result2))
check("idempotent: open count unchanged on second apply", after_open == after_open2)


# ────────────────────────────────────────────────────────────────────────────
print("\n== LOW_VALUE → review queue ==")
# ────────────────────────────────────────────────────────────────────────────

api.record(p, "entity", {"id": "customer:lowval", "type": "person"})
T_lv = p.tick()
api.record(p, "event", {"id": "evt_lv1", "ekind": "email", "event_time": T_lv})
api.record(p, "assert", {"id": "a_lv1", "agent": "test:bad-ingest",
                          "subjects": ["customer:lowval"], "proposition": "scheduling_call_tomorrow",
                          "assertion_time": T_lv})
api.record(p, "derive", {"id": "d_lv1", "consequent": "a_lv1",
                          "antecedents": ["evt_lv1"], "dkind": "extraction"})
api.STORE.db.execute(
    "INSERT OR IGNORE INTO source_records(id,project_id,connector_id,external_id,payload,content_hash,received) VALUES(?,?,?,?,?,?,?)",
    ("src_lv1", PID, CID, "lv_email_1",
     json.dumps({"from": "jim@co.com", "subject": "Quick call",
                 "body": "Let's schedule a call tomorrow at 2pm.", "headers": {}}),
     "hash_lv1", time.time()))
api.STORE.db.execute(
    "INSERT OR REPLACE INTO assertion_evidence VALUES(?,?,?,?,?,?,?)",
    ("a_lv1", PID, "src_lv1", '"schedule a call tomorrow at 2pm"', 0.55, "Test", time.time()))
api.STORE.db.commit()

lv_scan_id = scanner.start_scan(triggered_by="lv_test")
lv_results = scanner.scan_results(lv_scan_id, classification="LOW_VALUE")
check("low_value assertion flagged",
      any(r["assertion_id"] == "a_lv1" for r in lv_results),
      str([r["assertion_id"] for r in lv_results]))

# Apply sends it to review queue, not auto-retract
scanner.apply_corrections(lv_scan_id)
queue = scanner.review_queue()
check("low_value in review queue after apply", len(queue) >= 1, str(len(queue)))
check("review queue item has assertion_id",
      all("assertion_id" in q for q in queue))

# Approve one
qid = queue[0]["id"]
aid_to_retract = queue[0]["assertion_id"]
a_before = p.engine.store.assertion(aid_to_retract)
before_open_review = (p.engine.ledger.is_open_at(a_before, p.now())
                      if a_before else False)
scanner.review_decision(qid, "approve", reviewer="founder@omem.dev")
if a_before and before_open_review:
    after_a = p.engine.store.assertion(aid_to_retract)
    check("review approve: assertion closed",
          after_a is None or not p.engine.ledger.is_open_at(after_a, p.now()))
queue_after = scanner.review_queue()
check("review queue item marked approved", not any(q["id"] == qid for q in queue_after))

# Idempotent: can't review twice
try:
    scanner.review_decision(qid, "reject")
    check("double-review raises error", False, "no error raised")
except ValueError:
    check("double-review raises error", True)


# ────────────────────────────────────────────────────────────────────────────
print("\n== Gmail source rescan ==")
# ────────────────────────────────────────────────────────────────────────────

# Insert a source record that was previously excluded but should now be included
api.STORE.db.execute(
    "INSERT OR IGNORE INTO source_records(id,project_id,connector_id,external_id,payload,content_hash,received) VALUES(?,?,?,?,?,?,?)",
    ("src_unclassified1", PID, CID, "unclassified_email_1",
     json.dumps({
         "message_id": "u1", "thread_id": "t_u1",
         "from": "partner@bigcorp.com", "to": "me@corp.com",
         "subject": "Re: partnership proposal",
         "body": ("Hi, we'd like to explore a reseller partnership "
                  "and joint integration for the EU market. Regards"),
         "headers": {}, "at": "now",
     }),
     "hash_unc1", time.time()))
# No message_classification row → was_in_pipeline=False
api.STORE.db.commit()

# Insert one that was included but is now noise
api.STORE.db.execute(
    "INSERT OR IGNORE INTO source_records(id,project_id,connector_id,external_id,payload,content_hash,received) VALUES(?,?,?,?,?,?,?)",
    ("src_was_included", PID, CID, "was_included_email_1",
     json.dumps({
         "message_id": "wi1", "thread_id": "t_wi1",
         "from": "noreply@newsletter.io", "to": "me@corp.com",
         "subject": "Weekly update", "body": "Newsletter content. Unsubscribe here.",
         "headers": {"list-unsubscribe": "<unsubscribe>"}, "at": "now",
     }),
     "hash_wi1", time.time()))
api.STORE.db.execute(
    "INSERT INTO message_classifications"
    "(project_id,connector_id,source_record_id,external_id,thread_id,subject,sender,"
    "classification,confidence,business_type,reasons,signals,method,entered_pipeline,facts_extracted,ts)"
    " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
    (PID, CID, "src_was_included", "wi1", "t_wi1", "Weekly update", "noreply@newsletter.io",
     "BUSINESS_RELEVANT", 0.75, "OTHER_BUSINESS", "[]", "[]", "deterministic", 1, 0, time.time()))
api.STORE.db.commit()

rescan = scanner.rescan_gmail_sources(connector_id=CID)
check("gmail rescan runs without error", "error" not in rescan, str(rescan))
check("gmail rescan reports sources_examined", rescan["sources_examined"] > 0,
      str(rescan["sources_examined"]))
check("newly relevant email detected",
      rescan["newly_relevant"] >= 1,
      f"newly_relevant={rescan['newly_relevant']}, items={[i['subject'] for i in rescan['reclassified_include']]}")
check("newly excluded email detected",
      rescan["newly_excluded"] >= 1,
      f"newly_excluded={rescan['newly_excluded']}, items={[i['subject'] for i in rescan['reclassified_exclude']]}")


# ────────────────────────────────────────────────────────────────────────────
print("\n== health summary ==")
# ────────────────────────────────────────────────────────────────────────────

health = scanner.health_summary()
check("health has active_memories", isinstance(health["active_memories"], int), str(health))
check("health has last_scan_id set", health["last_scan_id"] is not None, str(health["last_scan_id"]))
check("health has by_classification", isinstance(health["by_classification"], dict))
check("health pending_review is int", isinstance(health["pending_review"], int))
check("health recent_corrections is list", isinstance(health["recent_corrections"], list))


# ────────────────────────────────────────────────────────────────────────────
print("\n== audit trail: corrections survive restart ==")
# ────────────────────────────────────────────────────────────────────────────

import importlib
srv.shutdown()
sys.modules.pop("api")
os.environ.pop("OMEM_LLM", None)
api2 = importlib.import_module("api")

# The retraction that corrected the alibaba assertion should be in the ops log
ops = api2.STORE.db.execute(
    "SELECT args FROM ops WHERE project_id=? AND kind='retract' ORDER BY seq",
    (PID,)).fetchall()
retract_args = [json.loads(r["args"]) for r in ops]
scanner_retractions = [a for a in retract_args if a.get("agent") == "scanner:system"]
check("scanner retractions in audit log after restart",
      len(scanner_retractions) >= 1,
      f"found {len(scanner_retractions)} scanner retractions")

# Alibaba assertion should still be closed after replay
p2 = api2.PROJECTS.get(PID)
if p2:
    bad_a2 = p2.engine.store.assertion("a_bad1")
    check("alibaba assertion closed after restart replay",
          bad_a2 is None or not p2.engine.ledger.is_open_at(bad_a2, p2.now()))
else:
    check("project survives restart", False, "project not in PROJECTS after restart")


# ────────────────────────────────────────────────────────────────────────────
print("\n== API routes ==")
# ────────────────────────────────────────────────────────────────────────────

srv2 = ThreadingHTTPServer(("127.0.0.1", 0), api2.Handler)
PORT2 = srv2.server_address[1]
threading.Thread(target=srv2.serve_forever, daemon=True).start()
time.sleep(0.2)


def call2(m, path, body=None, key=None):
    req = urllib.request.Request(
        f"http://127.0.0.1:{PORT2}{path}", method=m,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Content-Type": "application/json",
                 **({} if not key else {"Authorization": f"Bearer {key}"})})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


# Create a fresh project via API for route tests
_, acct2 = call2("POST", "/v1/signup", {"email": "route-test@corp.com"})
KEY2 = acct2["api_key"]["secret"]
PID2 = acct2["project"]["id"]
SESS2 = acct2["token"]

# Seed some memories
_, _ag = call2("POST", f"/v1/agents?project={PID2}", {"id": "test-agent", "kind": "system"}, KEY2)
_, _ent = call2("POST", f"/v1/entities?project={PID2}", {"id": "customer:api-test", "type": "person"}, KEY2)
_, _ev = call2("POST", f"/v1/events?project={PID2}",
               {"id": "evt-api1", "ekind": "email", "event_time": "now"}, KEY2)
_, _a = call2("POST", f"/v1/assertions?project={PID2}",
              {"id": "a-api1", "agent": "test-agent", "subjects": ["customer:api-test"],
               "proposition": "prefers_annual_billing", "assertion_time": "now"}, KEY2)

# GET /v1/memory/health
st, health_r = call2("GET", f"/v1/memory/health?project={PID2}", key=SESS2)
check("GET /v1/memory/health 200", st == 200, str(st))
check("health response has active_memories", "active_memories" in health_r, str(list(health_r.keys())))

# POST /v1/memory/scan
st, scan_r = call2("POST", f"/v1/memory/scan?project={PID2}", {"scope": "all"}, KEY2)
check("POST /v1/memory/scan 201", st == 201, str((st, scan_r)))
check("scan response has id and state", "id" in scan_r and scan_r.get("state") == "complete",
      str(scan_r))

SCAN_ID2 = scan_r["id"]

# GET /v1/memory/scans
st, scans_r = call2("GET", f"/v1/memory/scans?project={PID2}", key=SESS2)
check("GET /v1/memory/scans 200", st == 200, str(st))
check("scans list contains our scan",
      any(s["id"] == SCAN_ID2 for s in scans_r.get("data", [])))

# GET /v1/memory/scans/{id}
st, scan_detail = call2("GET", f"/v1/memory/scans/{SCAN_ID2}?project={PID2}", key=SESS2)
check("GET /v1/memory/scans/{id} 200", st == 200, str(st))
check("scan detail has results list", "results" in scan_detail, str(list(scan_detail.keys())))

# POST /v1/memory/scan with invalid scope
st, _ = call2("POST", f"/v1/memory/scan?project={PID2}", {"scope": "garbage"}, KEY2)
check("invalid scope -> 400", st == 400, str(st))

# POST /v1/memory/scans/{id}/apply
st, apply_r = call2("POST", f"/v1/memory/scans/{SCAN_ID2}/apply?project={PID2}", {}, KEY2)
check("POST /v1/memory/scans/{id}/apply 200", st == 200, str(st))
check("apply response has retracted count", "retracted" in apply_r, str(list(apply_r.keys())))

# GET /v1/memory/review-queue
st, rq = call2("GET", f"/v1/memory/review-queue?project={PID2}", key=SESS2)
check("GET /v1/memory/review-queue 200", st == 200, str(st))
check("review queue has data key", "data" in rq, str(list(rq.keys())))

# POST /v1/memory/gmail-rescan (no connector_id → scans all gmail connectors)
st, gr = call2("POST", f"/v1/memory/gmail-rescan?project={PID2}", {}, KEY2)
check("POST /v1/memory/gmail-rescan 200", st == 200, str(st))
check("gmail rescan response has sources_examined", "sources_examined" in gr, str(gr))

# POST /v1/memory/scan with 'recent' scope
st, sr_r = call2("POST", f"/v1/memory/scan?project={PID2}", {"scope": "recent"}, KEY2)
check("POST /v1/memory/scan scope=recent 201", st == 201, str(st))


print(f"\n{PASS} passed, {FAIL} failed")
import sys as _sys
_sys.exit(1 if FAIL else 0)
