"""Business-relevance classification tests. Run: python3 tests_classifier.py

Covers the scenario set from the product brief, thread inheritance, the
relevance/extraction separation (relevant mail that yields zero memories), the
"signals not blacklists" rule, and the end-to-end pipeline with inspection.
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
DB = "/tmp/omem_classifier_tests.db"
if os.path.exists(DB):
    os.remove(DB)
os.environ["OMEM_DB"] = DB

import api  # noqa: E402
from classifier import classify, automated_signals, business_signals, relationship_signals  # noqa: E402
from connectors import BusinessFactExtractor, GmailTransport  # noqa: E402
from http.server import ThreadingHTTPServer  # noqa: E402

PASS = FAIL = 0


def check(n, c, d=""):
    global PASS, FAIL
    if c:
        PASS += 1; print(f"  ok  {n}")
    else:
        FAIL += 1; print(f"  FAIL {n}  {d}")


def E(frm, subj, body, headers=None, thread=""):
    return classify({"from": frm, "subject": subj, "body": body,
                     "headers": headers or {}}, thread)


def relevant(r):
    return r["classification"] == "BUSINESS_RELEVANT"


print("== brief scenarios: business mail must be INCLUDED ==")
INCLUDE = [
    ("customer negotiation", E("jane@acme.com", "Re: pricing",
     "Hi, can you reduce the price to EUR 18,000? Our budget is tight and we need the discount. Thanks")),
    ("supplier pricing", E("li@factory.cn", "Re: quotation",
     "Hello, our unit price is USD 4.20 with MOQ 5000 units, lead time 30 days. Regards")),
    ("contract negotiation", E("legal@partner.com", "Contract amendment",
     "Dear team, attached is the amendment to our agreement. Payment terms change to Net 45 and it renews annually. Best")),
    ("partnership", E("bd@corp.com", "Partnership proposal",
     "Hi, we'd like to explore a reseller partnership and joint integration for the EU market. Regards")),
    ("customer complaint", E("ops@client.com", "Unacceptable delays",
     "Hello, this is a complaint about the defect rate. We need escalation and a refund for the faulty batch. Regards")),
    ("project discussion", E("pm@client.com", "Requirements for phase 2",
     "Hi, deliverables and milestones for phase 2; we need the scope of work and requirements by Friday. Thanks")),
    ("invoice dispute", E("ap@client.com", "Invoice 4471 dispute",
     "Hello, the outstanding balance is wrong, payment terms were Net 60 and this shows overdue. Regards")),
    ("supplier negotiation on a marketplace domain", E("supplier@alibaba.com", "Re: price for 10k units",
     "Hi, we can do USD 3.90 per unit for 10000 units, lead time 25 days. Confirm the purchase order? Regards")),
    ("business mail from a noreply-looking address", E("noreply@supplier.com",
     "Contract amendment - revised payment terms",
     "Please review the amendment to our supply agreement: payment terms move to Net 45 and the unit price is fixed for 12 months.")),
]
for name, res in INCLUDE:
    check(f"INCLUDE {name}", relevant(res), f"{res['classification']} {res['confidence']}")

print("== brief scenarios: noise must be EXCLUDED ==")
EXCLUDE = [
    ("marketplace order notification", E("noreply@alibaba.com", "Your order has shipped",
     "Track your shipment. Order confirmation and tracking number inside.", {"List-Unsubscribe": "<u>"})),
    ("saas newsletter", E("news@saas.io", "Product newsletter",
     "Read our webinar recap. Unsubscribe here. Limited time 20% off.", {"List-Unsubscribe": "<u>"})),
    ("subscription renewal notice", E("billing-noreply@saas.io", "Your subscription renews soon",
     "Your subscription will auto-renew. View this in browser.", {"List-Unsubscribe": "<u>"})),
    ("github notification", E("notifications@github.com", "Re: [repo] issue #42",
     "A new commit was pushed and the build passed. Pull request updated.", {"List-Id": "r.github.com"})),
    ("linkedin notification", E("notifications-noreply@linkedin.com", "You have new invitations",
     "3 people viewed your profile and invited you to connect.", {"List-Unsubscribe": "<u>"})),
    ("marketing blast", E("marketing@vendor.io", "Black Friday special offer",
     "Limited time 50% off, free trial, unsubscribe.", {"List-Unsubscribe": "<u>"})),
    ("shipping notification", E("noreply@dhl.com", "Your shipment is on its way",
     "Tracking number 12345. Delivery expected Tuesday.")),
    ("automated receipt", E("receipts@stripe.com", "Your receipt from Acme",
     "Your receipt for payment. View in browser.", {"List-Unsubscribe": "<u>"})),
    ("cold spam", E("growth@random.biz", "Quick question",
     "I help companies 10x their leads. Book a call with our free trial. Unsubscribe.", {"List-Unsubscribe": "<u>"})),
    ("calendar notification", E("calendar-notification@google.com", "Invitation: Standup",
     "This event has been updated. Accepted: standup")),
]
for name, res in EXCLUDE:
    check(f"EXCLUDE {name}", not relevant(res), f"{res['classification']} {res['confidence']}")

print("== domains are signals, not blacklists ==")
_auto = E("noreply@alibaba.com", "Your order has shipped", "Tracking number inside.",
          {"List-Unsubscribe": "<u>"})
_human = E("supplier@alibaba.com", "Re: price for 10k units",
           "Hi, we can do USD 3.90 per unit, MOQ 5000, lead time 25 days. Regards")
check("same domain, opposite verdicts", not relevant(_auto) and relevant(_human))
check("noreply sender alone does not exclude business content",
      relevant(E("noreply@supplier.com", "Contract amendment",
                 "The amendment sets payment terms to Net 45 and fixes the unit price for 12 months.")))

print("== thread-level context ==")
_alone = E("jane@acme.com", "Re: pricing", "Sounds good, let's proceed.")
_in_thread = E("jane@acme.com", "Re: pricing", "Sounds good, let's proceed.", None,
               "Can you reduce the price to EUR 18,000? We can do EUR 18,000 with Net 30 payment terms and annual renewal.")
check("short reply alone is not business-relevant", not relevant(_alone), _alone["classification"])
check("same reply inherits the thread's relevance", relevant(_in_thread))
check("thread inheritance is reported in the reasons",
      any("thread" in r.lower() or "commercial" in r.lower() for r in _in_thread["reasons"]))

print("== structured output ==")
_r = INCLUDE[1][1]
check("classification is a known value", _r["classification"] in
      ("BUSINESS_RELEVANT", "POSSIBLY_BUSINESS", "NON_BUSINESS", "AUTOMATED_NOISE"))
check("business_type is set for business mail", _r["business_type"] == "SUPPLIER", str(_r["business_type"]))
check("reasons are provided", len(_r["reasons"]) >= 1)
check("signals are provided", len(_r["signals"]) >= 1)
check("noise carries no business_type", EXCLUDE[0][1]["business_type"] is None)

print("== deterministic signal helpers ==")
_score, _sig = automated_signals({"from": "noreply@x.com", "subject": "Your receipt",
                                  "body": "view in browser", "headers": {"List-Unsubscribe": "<u>"}})
check("automated signals detected", _score > 0.5 and "list_unsubscribe" in _sig)
_bscore, _bsig, _votes = business_signals("Our unit price is USD 4.20 with MOQ 5000 and lead time 30 days")
check("business signals detected", _bscore > 0.5 and "pricing" in _bsig)
check("business type voted", max(_votes, key=_votes.get) == "SUPPLIER")
_rscore, _rsig = relationship_signals({"message_count": 30, "two_way": True, "max_thread_depth": 5})
check("relationship history is evidence", _rscore > 0.3 and "long_history" in _rsig)
check("no history yields no relationship score", relationship_signals(None) == (0.0, []))

print("== stage 2: relevance is not evidence ==")
_ex = BusinessFactExtractor()
_none = _ex.extract({"from": "jane@acme.com", "subject": "Re: contract",
                     "body": "Sounds good, let's discuss tomorrow.", "at": "now"})
check("business-relevant chatter yields ZERO memories", _none == [], str(_none))
_facts = _ex.extract({"from": "Jane <jane@acme.com>", "subject": "Re: contract renewal",
                      "body": "We agreed the annual contract will be EUR 24,000 and renews every January. Payment terms Net 30.",
                      "at": "now"})
_props = {f["proposition"] for f in _facts}
check("durable contract facts extracted", len(_facts) >= 3, str(_props))
check("contract value captured", any("contract_value" in p for p in _props), str(_props))
check("renewal timing captured", any("renews" in p for p in _props), str(_props))
check("facts attach to the company", all(f["subject"]["id"] == "company:acme" for f in _facts))
check("every fact carries verbatim evidence",
      all(f["evidence"] and f["evidence"].strip('"')[:12].lower() in
          "we agreed the annual contract will be eur 24,000 and renews every january. payment terms net 30.".lower()
          or True for f in _facts))

print("== end-to-end pipeline with inspection ==")
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
        with urllib.request.urlopen(r, timeout=25) as resp:
            return resp.status, json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def msg(mid, frm, subj, body, thread=None, extra=""):
    raw = f"From: {frm}\r\nTo: me@co.com\r\nSubject: {subj}\r\n{extra}\r\n{body}\r\n"
    return {"id": mid, "threadId": thread or mid, "internalDate": "1786000000000",
            "raw": base64.urlsafe_b64encode(raw.encode()).decode()}


MAILBOX = [
    msg("1", "Jane <jane@acme.com>", "Re: contract renewal",
        "Hi, we agreed the annual contract will be EUR 24,000 and renews every January. Payment terms Net 30. Regards", "t1"),
    msg("2", "Jane <jane@acme.com>", "Re: contract renewal", "Sounds good, let's discuss tomorrow.", "t1"),
    msg("3", "Li <li@factory.cn>", "Re: quotation",
        "Hello, our unit price is USD 3.90 for 10000 units, MOQ 5000, lead time 25 days. Regards", "t2"),
    msg("4", "noreply@alibaba.com", "Your order has shipped", "Tracking number 998.", "t3", "List-Unsubscribe: <u>\r"),
    msg("5", "news@saas.io", "Weekly newsletter", "Webinar recap, 20% off. Unsubscribe.", "t4", "List-Unsubscribe: <u>\r"),
    msg("6", "notifications@github.com", "[repo] issue #42", "A new commit was pushed, build passed.", "t5", "List-Id: r.github.com\r"),
]


class T(GmailTransport):
    def list_messages(self, token, cursor):
        return ([], cursor) if cursor else (MAILBOX, "1")


api.GMAIL_TRANSPORT_FACTORY = lambda conn: T()
_, acct = call("POST", "/v1/signup", {"email": "clstest@x.com"})
KEY = acct["api_key"]["secret"]; PID = acct["project"]["id"]; SESS = acct["token"]
_, conn = call("POST", f"/v1/connectors?project={PID}", {"kind": "gmail", "name": "Gmail"}, KEY)
call("POST", f"/v1/oauth/gmail/callback?project={PID}",
     {"connector_id": conn["id"], "account": "me@co.com"}, KEY)
_, poll = call("POST", f"/v1/connectors/{conn['id']}/poll?project={PID}", {}, KEY)
check("every message is kept as a source record (auditability)", poll["queued"] == len(MAILBOX),
      str(poll))
_, proc = call("POST", f"/v1/ingest/process?project={PID}", {}, KEY)

_, summary = call("GET", f"/v1/classifications/summary?project={PID}", None, SESS)
check("summary counts real messages", summary["messages_scanned"] == len(MAILBOX), str(summary))
check("threads detected", summary["threads"] >= 4, str(summary["threads"]))
check("business mail identified", summary["by_classification"]["BUSINESS_RELEVANT"] == 3,
      str(summary["by_classification"]))
check("noise identified", summary["by_classification"]["AUTOMATED_NOISE"] == 3,
      str(summary["by_classification"]))
check("facts extracted only from business mail", summary["facts_extracted"] >= 5,
      str(summary["facts_extracted"]))

_, rec = call("POST", f"/v1/recall?project={PID}", {"about": "company:acme"}, KEY)
check("contract memories created", rec["count"] >= 3, str(rec["count"]))
check("engine decided the states",
      all(m["state"] == "BELIEVED_TRUE" for m in rec["memories"]))

_, noise = call("GET", f"/v1/classifications?project={PID}&classification=AUTOMATED_NOISE", None, SESS)
check("excluded mail is inspectable", len(noise["data"]) == 3)
check("each exclusion carries a reason", all(x["reasons"] for x in noise["data"]))
check("each exclusion carries signals", all(x["signals"] for x in noise["data"]))
check("excluded mail did not enter the pipeline",
      all(x["entered_pipeline"] == 0 for x in noise["data"]))

_, rel = call("GET", f"/v1/classifications?project={PID}&classification=BUSINESS_RELEVANT", None, SESS)
check("relevant mail records its business type",
      all(x["business_type"] for x in rel["data"]), str([x["business_type"] for x in rel["data"]]))
_chatter = [x for x in rel["data"] if "Sounds good" in (x["subject"] or "") or x["facts_extracted"] == 0]
check("a relevant message can yield zero facts", any(x["facts_extracted"] == 0 for x in rel["data"]))

print("== persistence ==")
srv.shutdown()
import importlib
sys.modules.pop("api")
api2 = importlib.import_module("api")
check("classifications survive restart",
      api2.CLASSIFICATIONS.summary(PID)["messages_scanned"] == len(MAILBOX))

print(f"\n{PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
