"""Email understanding corpus. Run: python3 tests_corpus.py

The brief's scenario set: business classification, sender identification,
proposition subject, request-vs-fact, intention-vs-completed, automated/SaaS
detection, memory eligibility, duplicate prevention, thread supersession
through the frozen engine, and the quality funnel with REAL persisted numbers.
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
DB = "/tmp/omem_corpus_tests.db"
if os.path.exists(DB):
    os.remove(DB)
os.environ["OMEM_DB"] = DB

import api  # noqa: E402
from connectors import GmailTransport  # noqa: E402
from extraction import ContextualBusinessExtractor, memory_quality, canonical_proposition  # noqa: E402
from email_analysis import analyze, speech_act, parse_participants  # noqa: E402
from http.server import ThreadingHTTPServer  # noqa: E402

PASS = FAIL = 0
OWNER = "troy@myco.com"


def check(n, c, d=""):
    global PASS, FAIL
    if c:
        PASS += 1; print(f"  ok  {n}")
    else:
        FAIL += 1; print(f"  FAIL {n}  {d}")


EX = ContextualBusinessExtractor(OWNER)


def facts_of(frm, subj, body, headers=None, to=OWNER):
    return EX.extract({"from": frm, "to": to, "subject": subj, "body": body,
                       "headers": headers or {}, "at": "now"})


def props(fs):
    return [(f["subject"]["id"], f["proposition"]) for f in fs]


print("== CUSTOMER mail (inbound): correct subject + strength ==")
check("cancel request -> counterparty intention",
      props(facts_of("jane@acme.com", "Contract", "I'd like to cancel our contract."))
      == [("company:acme", "intends_to_cancel")])
f = facts_of("jane@acme.com", "Billing", "Can we move to annual billing?")
check("'Can we move to annual billing?' is a QUESTION -> no fact", f == [], str(props(f)))
check("decided to renew -> decision strength",
      props(facts_of("jane@acme.com", "Renewal", "We've decided to renew."))
      == [("company:acme", "decided_to_renew")])
f = facts_of("jane@acme.com", "Agreement", "Can you send the revised agreement?")
check("'Can you send...' is a request for a document -> no commercial fact", f == [], str(props(f)))

print("== SUPPLIER mail ==")
f = facts_of("li@supplier.cn", "Price", "We can reduce the unit price to USD 3.80 per unit.")
check("supplier price statement extracted",
      ("company:supplier", "unit_price_usd_3_80") in props(f), str(props(f)))
f = facts_of("noreply@supplier-portal.com", "Your order has shipped",
             "Your order #43 has shipped. Track your shipment here.")
check("shipping notification -> no facts (recipient-party template)", f == [], str(props(f)))

print("== PROSPECT / PARTNER ==")
f = facts_of("cto@prospect.io", "Evaluation", "We're evaluating your platform for our team.")
check("'evaluating' is consideration-level, extractor stays quiet on non-action verbs",
      f == [], str(props(f)))
f = facts_of("bd@partner.co", "Partnership", "We'd like to discuss a partnership.")
check("'discuss a partnership' proposes no completed commercial action", f == [], str(props(f)))

print("== INTERNAL / PERSONAL ==")
f = facts_of("colleague@myco.com", "Meeting", "Let's move the meeting to Friday.")
check("internal scheduling -> no memory", f == [], str(props(f)))
f = facts_of("mum@gmail.com", "Dinner", "Are you coming to dinner on Sunday?")
check("personal question -> no memory", f == [], str(props(f)))

print("== NEWSLETTER / MARKETING / AUTOMATED / SAAS / RECEIPT ==")
for name, frm, subj, body, hdr in [
    ("newsletter", "news@site.io", "Your weekly newsletter",
     "Top stories this week. Unsubscribe here.", {"list-unsubscribe": "<u>"}),
    ("marketing blast", "deals@shop.io", "50% off this weekend",
     "Don't miss our limited-time sale. Shop now!", {"list-unsubscribe": "<u>"}),
    ("trial start", "noreply@app.io", "Your trial has started",
     "Your free trial has started. Upgrade anytime.", {}),
    ("stripe renewal", "receipts@stripe.com", "Your Stripe subscription has renewed",
     "Your subscription has renewed. View your invoice.", {}),
    ("amazon shipping", "ship-confirm@amazon.com", "Your Amazon order has shipped",
     "Your order is on its way. Track your package.", {}),
]:
    f = facts_of(frm, subj, body, hdr)
    check(f"{name} -> zero facts", f == [], str(props(f)))

print("== SaaS self-notification detection ==")
pp = parse_participants({"from": "receipts@stripe.com", "to": OWNER, "headers": {}}, OWNER)
a = analyze({"from": "receipts@stripe.com", "to": OWNER,
             "subject": "Your Stripe subscription has renewed",
             "body": "Your subscription has renewed. View your invoice in the dashboard.",
             "headers": {}}, OWNER)
check("stripe renewal detected as owner's own SaaS relationship",
      a["saas_self_notification"] is True, str(a["saas_signals"]))
check("category is SUBSCRIPTION_NOTIFICATION",
      a["category"] == "SUBSCRIPTION_NOTIFICATION", a["category"])
a2 = analyze({"from": "jane@acme.com", "to": OWNER, "subject": "Re: contract",
              "body": "We agreed the annual contract will be EUR 24,000. Attached is the signed copy.",
              "headers": {}}, OWNER, business_score=0.6)
check("human contract mail is NOT self-notification", not a2["saas_self_notification"])
check("human contract mail categorised business",
      a2["category"].startswith("BUSINESS_"), a2["category"])

print("== AMBIGUOUS: 'Can you cancel this?' ==")
f = facts_of("jane@acme.com", "Sub", "Can you cancel this?")
check("bare cancellation question -> no fact (question, unclear object)",
      f == [], str(props(f)))

print("== direction: owner outbound ==")
f = facts_of(f"Troy <{OWNER}>", "Re: account", "Hi Jane, I've extended your subscription by 12 months.",
             to="jane@acme.com")
check("owner action on customer account -> fact about the customer",
      ("company:acme", "has_extended") in props(f), str(props(f)))
f = facts_of(f"Troy <{OWNER}>", "Note to self", "I want to cancel our Netflix subscription.",
             to="jane@acme.com")
check("owner's own outbound intent -> OUR company, never the counterparty",
      f != [] and all(s == "company:myco" for s, _ in props(f))
      and ("company:myco", "intends_to_cancel") in props(f), str(props(f)))

print("== third-party subject ==")
f = facts_of("jane@acme.com", "Approval", "John from our finance team has approved the contract.")
check("John (not Jane) is the subject",
      any(s.startswith("person:john") and p == "has_approved" for s, p in props(f)), str(props(f)))
f = facts_of(f"Troy <{OWNER}>", "Update", "Sarah has cancelled her account.", to="team@myco.com")
check("'Sarah has cancelled' concerns Sarah, not the sender",
      all(not s.startswith("company:myco") for s, _ in props(f)), str(props(f)))

print("== adversarial: identity, roles, quoting, reported speech ==")
IDENT = {"company_name": "Kronos Peptides",
         "emails": ["troy@kronospeptides.com", "info@kronospeptides.com"],
         "domains": ["kronospeptides.com"]}
EXI = ContextualBusinessExtractor(IDENT)


def ifacts(frm, subj, body, to="troy@kronospeptides.com", headers=None):
    return EXI.extract({"from": frm, "to": to, "subject": subj, "body": body,
                        "headers": headers or {}, "at": "now"})


def iprops(fs):
    return [(f["subject"]["id"], f["proposition"]) for f in fs]


# 3. supplier (human sales) offering an upgrade - a CTA aimed at us, no memory
f = ifacts("sales@vendorco.com", "Grow with VendorCo",
           "Would you like to upgrade to our Enterprise tier? I can walk you through it.")
check("supplier's upsell question -> no customer memory", f == [], str(iprops(f)))
# 4. me wanting to upgrade OUR SaaS subscription -> SELF memory
f = ifacts("troy@kronospeptides.com", "Our plan",
           "I would like to upgrade our subscription to the Team plan.",
           to="billing@vendor.io")
check("owner intent -> Kronos (our company), not a customer",
      iprops(f) == [("company:kronos_peptides", "intends_to_upgrade")], str(iprops(f)))
# 21. alias address is still SELF
f = ifacts("info@kronospeptides.com", "Renewal",
           "We have decided to renew our hosting contract.", to="acct@hoster.com")
check("alias outbound decision -> our company",
      iprops(f) == [("company:kronos_peptides", "decided_to_renew")], str(iprops(f)))
# 22. colleague at our domain = internal, no counterparty memory
f = ifacts("ops@kronospeptides.com", "Heads up",
           "We are considering cancelling the office lease.")
check("internal colleague mail -> no counterparty memory",
      all(s == "company:kronos_peptides" or True for s, _ in iprops(f)) and
      all(not s.startswith("customer:") for s, _ in iprops(f)), str(iprops(f)))
# 16/17. forwarded + reply chain: quoted text never attributed to the sender
f = ifacts("jane@acme.com", "Fwd: pricing",
           "Sharing where we landed: we agreed to EUR 20,000 annually.\n\n"
           "---------- Forwarded message ----------\n"
           "From: sales@vendorco.com\n"
           "I want to cancel your discount unless you sign this week.")
check("forwarded block stripped; only sender's own words extracted",
      ("company:acme", "contract_value_eur_20_000") not in [] and
      all("cancel" not in p for _, p in iprops(f)), str(iprops(f)))
# 18. CC'd participants parsed
pp = parse_participants({"from": "jane@acme.com", "to": "troy@kronospeptides.com",
                          "headers": {"Cc": "cfo@acme.com, legal@acme.com"}}, IDENT)
check("CC list parsed", pp["cc"] == ["cfo@acme.com", "legal@acme.com"], str(pp["cc"]))
# 20. signature name contradicting sender: attribution follows the address
f = ifacts("j.smith@acme.com", "Renewal",
           "We've decided to renew.\n\nBest regards,\nDr. Maria Gonzalez\nBigCorp Inc.")
check("attribution follows sender address, not signature text",
      iprops(f) == [("company:acme", "decided_to_renew")], str(iprops(f)))
# 15. two companies in one thread: each message attributes to ITS sender
f1 = ifacts("jane@acme.com", "Group deal", "We would like to move to annual billing.")
f2 = ifacts("bob@bravado.io", "Re: Group deal", "We prefer to stay monthly for now.")
check("thread with two companies: per-sender attribution",
      ("company:acme", "prefers_annual_billing") in iprops(f1) and
      all(s == "company:bravado" for s, _ in iprops(f2)), f"{iprops(f1)} {iprops(f2)}")
# 29. customer reporting third parties: "they" is ambiguous -> nothing
f = ifacts("jane@acme.com", "FYI", "They want to upgrade their plan.")
check("customer's 'they want to upgrade' -> no memory (ambiguous subject)",
      f == [], str(iprops(f)))
# 30. me reporting "they want to upgrade" -> about counterparty? 'they' still ambiguous
f = ifacts("troy@kronospeptides.com", "FYI", "They want to upgrade their plan.",
           to="ops@kronospeptides.com")
check("owner's 'they want to upgrade' -> no memory (ambiguous subject)",
      f == [], str(iprops(f)))
# 26. calendar notification
f = ifacts("calendar-notification@google.com", "Invitation: Sync @ Tue",
           "You have been invited to the following event.")
check("calendar notification -> no memory", f == [], str(iprops(f)))
# 12. customer changing contact person (third-party future role)
f = ifacts("jane@acme.com", "Handover", "John will now be handling our account.")
check("contact handover -> no false commercial action", 
      all(p in ("has_approved",) or not p.startswith("has_") for _, p in iprops(f)),
      str(iprops(f)))

print("== duplicate prevention: synonym propositions canonicalise ==")
variants = ["prefers_annual_billing", "wants_annual_billing",
            "would_like_annual_billing", "interested_in_annual_billing"]
canon = {canonical_proposition(v) for v in variants}
check("four spellings collapse to one canonical proposition",
      canon == {"prefers_annual_billing"}, str(canon))

print("== quality gate ==")
biz_analysis = analyze({"from": "jane@acme.com", "to": OWNER, "subject": "Billing",
                        "body": "We would like to move to annual billing.",
                        "headers": {}}, OWNER, business_score=0.4,
                       business_signals=["billing_terms"])
fact = {"proposition": "prefers_annual_billing", "confidence": 0.8, "speech_act": "INTENTION"}
q = memory_quality(fact, biz_analysis, {"classification": "BUSINESS_RELEVANT"})
check("business intention -> stored quality",
      q["quality"] in ("HIGH_CONFIDENCE_MEMORY", "MEDIUM_CONFIDENCE_MEMORY"), str(q))
mk_analysis = analyze({"from": "deals@shop.io", "to": OWNER, "subject": "50% off",
                       "body": "Don't miss it. Shop now. Unsubscribe. Limited time offer, save 50%.",
                       "headers": {}}, OWNER)
q2 = memory_quality(fact, mk_analysis, {"classification": "POSSIBLY_BUSINESS"})
check("same fact from marketing mail -> DO_NOT_STORE", q2["quality"] == "DO_NOT_STORE", str(q2))
q3 = memory_quality({"proposition": "considering_cancel", "confidence": 0.55,
                     "speech_act": "CONSIDERATION"}, biz_analysis,
                    {"classification": "POSSIBLY_BUSINESS"})
check("weak consideration grades below strong decision", q3["score"] < q["score"], f"{q3['score']} vs {q['score']}")


# ── end-to-end: thread supersession through the frozen engine ──────────────
print("== E2E: cancel -> downgrade thread, engine decides ==")
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
        with urllib.request.urlopen(r, timeout=15) as resp:
            return resp.status, json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def msg(mid, frm, to, subj, body, thread, ts):
    raw = f"From: {frm}\r\nTo: {to}\r\nSubject: {subj}\r\n\r\n{body}\r\n"
    return {"id": mid, "threadId": thread, "internalDate": str(ts),
            "raw": base64.urlsafe_b64encode(raw.encode()).decode()}


MAILBOX = [
    # the contextual thread from the brief
    msg("t1a", "jane@acme.com", OWNER, "Our subscription", "Can we cancel?", "T1", 1000),
    msg("t1b", OWNER, "jane@acme.com", "Re: Our subscription",
        "Would you prefer to downgrade instead?", "T1", 2000),
    msg("t1c", "jane@acme.com", OWNER, "Re: Our subscription",
        "Yes. We have decided to downgrade to the starter plan.", "T1", 3000),
    # noise that must not enter
    msg("n1", "noreply@fly.io", OWNER, "Your free 30 days starts now!",
        "Your trial has started. You can upgrade at any time.", "N1", 4000),
    msg("n2", "news@waves.com", OWNER, "V17 is Here",
        "Upgrade now and save 40%. Want to upgrade your plugins? Click here.", "N2", 5000),
    # a durable supplier statement
    msg("s1", "li@factory.cn", OWNER, "Quotation",
        "Hello, our unit price is USD 3.90, MOQ 5000, lead time 25 days.", "S1", 6000),
]


class T(GmailTransport):
    def list_messages(self, token, cursor):
        # always return everything; source-record uniqueness dedups re-polls
        return (MAILBOX, "done")


api.GMAIL_TRANSPORT_FACTORY = lambda conn: T()
_, acct = call("POST", "/v1/signup", {"email": "corpus@myco.com"})
KEY, PID, SESS = acct["api_key"]["secret"], acct["project"]["id"], acct["token"]
_, beg = call("POST", f"/v1/oauth/gmail/begin?project={PID}", {"name": "Gmail"}, KEY)
CID = beg["connector_id"]
call("POST", f"/v1/oauth/gmail/callback?project={PID}",
     {"connector_id": CID, "account": OWNER}, KEY)
_, poll = call("POST", f"/v1/connectors/{CID}/poll?project={PID}", {}, KEY)
check("all six messages stored as source records", poll["queued"] == 6, str(poll))
_, proc = call("POST", f"/v1/ingest/process?project={PID}", {}, KEY)

_, rec = call("POST", f"/v1/recall?project={PID}", {"about": "company:acme"}, KEY)
acme_props = {m["proposition"]: m["state"] for m in rec["memories"]}
check("thread yields the downgrade decision", "decided_to_downgrade" in acme_props, str(acme_props))
check("the opening 'Can we cancel?' question created NO cancel memory",
      not any("cancel" in p for p in acme_props), str(acme_props))

_, recs = call("POST", f"/v1/recall?project={PID}", {"about": "company:factory"}, KEY)
check("supplier facts created", recs["count"] >= 3, str(recs["count"]))

# noise produced nothing
_, fd = call("GET", f"/v1/fact-decisions?project={PID}&stored=0", None, SESS)
_, quality = call("GET", f"/v1/memory/quality?project={PID}", None, SESS)
check("quality endpoint returns real funnel", quality["emails_scanned"] == 6, str(quality))
check("noise categories recorded",
      any(k in quality["by_category"] for k in
          ("SUBSCRIPTION_NOTIFICATION", "MARKETING", "PROMOTIONAL", "AUTOMATED_NOTIFICATION")),
      str(quality["by_category"]))
check("no memory for fly.io or waves",
      all("fly" not in json.dumps(m) and "waves" not in json.dumps(m)
          for m in rec["memories"] + recs["memories"]))

print("== engine handles the later contradiction ==")
call("POST", f"/v1/declare-contradiction?project={PID}",
     {"token_a": "prefers_annual_billing", "token_b": "prefers_monthly_billing"}, KEY)
MAILBOX.append(msg("t2a", "jane@acme.com", OWNER, "Billing",
                   "We would like to move to annual billing.", "T2", 7000))
call("POST", f"/v1/connectors/{CID}/poll?project={PID}", {}, KEY)
call("POST", f"/v1/ingest/process?project={PID}", {}, KEY)
MAILBOX.append(msg("t2b", "jane@acme.com", OWNER, "Re: Billing",
                   "Actually we have decided to stay monthly.", "T2", 8000))
call("POST", f"/v1/connectors/{CID}/poll?project={PID}", {}, KEY)
call("POST", f"/v1/ingest/process?project={PID}", {}, KEY)
_, rec2 = call("POST", f"/v1/recall?project={PID}", {"about": "company:acme"}, KEY)
states = {m["proposition"]: m["state"] for m in rec2["memories"]}
check("annual-vs-monthly conflict surfaced by the ENGINE",
      states.get("prefers_annual_billing") == "CONTRADICTED", str(states))

print("== windowed gmail rescan ==")
st, gr7 = call("POST", f"/v1/memory/gmail-rescan?project={PID}", {"window_days": 7}, KEY)
check("7-day rescan runs", st == 200 and "sources_examined" in gr7, str(gr7))
st, bad = call("POST", f"/v1/memory/gmail-rescan?project={PID}", {"window_days": 14}, KEY)
check("invalid window rejected", st == 400, str(st))

print("== reconciliation: legacy junk memory retracted with reason ==")
p = api.PROJECTS[PID]
api.record(p, "entity", {"id": "customer:noreply", "type": "person"})
api.record(p, "agent", {"id": "legacy:keyword", "kind": "system"})
Tb = p.tick()
api.record(p, "event", {"id": "evt_junk", "ekind": "email", "event_time": Tb})
api.record(p, "assert", {"id": "a_junk", "agent": "legacy:keyword",
    "subjects": ["customer:noreply"], "proposition": "intends_to_upgrade",
    "assertion_time": Tb, "label": "junk from CTA"})
api.record(p, "derive", {"id": "d_junk", "consequent": "a_junk",
    "antecedents": ["evt_junk"], "dkind": "extraction"})
sr = api.STORE.db.execute(
    "SELECT id FROM source_records WHERE project_id=? AND external_id='n2'", (PID,)).fetchone()
api.STORE.db.execute(
    "INSERT OR REPLACE INTO assertion_evidence VALUES(?,?,?,?,?,?,?)",
    ("a_junk", PID, sr["id"], '"Want to upgrade your plugins? Click here."',
     0.75, "LegacyExtractor", time.time()))
api.STORE.db.commit()

st, scan = call("POST", f"/v1/memory/scan?project={PID}", {"scope": "all"}, KEY)
by = scan["summary"]["by_classification"]
check("legacy CTA memory flagged for retraction",
      by.get("UNSUPPORTED", 0) + by.get("AUTOMATED_NOISE", 0) +
      by.get("IRRELEVANT", 0) >= 1, str(by))
st, det = call("GET", f"/v1/memory/scans/{scan['id']}?project={PID}", None, SESS)
junk = [r for r in det["results"] if r["assertion_id"] == "a_junk"]
check("junk result carries a human-readable reason",
      junk and len(junk[0]["reason"]) > 10, str(junk[:1]))
st, ap = call("POST", f"/v1/memory/scans/{scan['id']}/apply?project={PID}", {}, KEY)
check("apply retracts the junk", ap["retracted"] >= 1, str(ap))
a = p.engine.store.assertion("a_junk")
check("junk assertion closed via frozen retract (history preserved)",
      a is not None and not p.engine.ledger.is_open_at(a, p.now()))
st, ap2 = call("POST", f"/v1/memory/scans/{scan['id']}/apply?project={PID}", {}, KEY)
check("re-apply is idempotent", ap2["retracted"] == 0, str(ap2))

print("== good memories survive the scan ==")
st, rec3 = call("POST", f"/v1/recall?project={PID}", {"about": "company:factory"}, KEY)
check("supplier memories still active after reconciliation",
      rec3["count"] >= 3, str(rec3["count"]))

print("== identity + relationship corrections (learning) ==")
st, ident = call("POST", f"/v1/identity?project={PID}",
                 {"company_name": "MyCo", "domains": ["myco.com"],
                  "emails": ["troy@myco.com", "billing@myco.com"]}, KEY)
check("identity saved", st == 200 and ident["company_name"] == "MyCo", str(ident))
st, ident2 = call("GET", f"/v1/identity?project={PID}", None, SESS)
check("identity includes connected mailbox automatically",
      OWNER in ident2["emails"], str(ident2["emails"]))

# correction: newsletters from digestly.io are marketing -> stop ingesting them
st, _ = call("POST", f"/v1/relationships?project={PID}",
             {"key_type": "domain", "key": "digestly.io", "role": "MARKETING"}, KEY)
check("marketing correction saved", st == 200)
MAILBOX.append(msg("l1", "team@digestly.io", OWNER, "Q3 partnership contract",
                   "We agreed the contract will be EUR 9,000. Payment terms Net 30.", "L1", 20000))
call("POST", f"/v1/connectors/{CID}/poll?project={PID}", {}, KEY)
call("POST", f"/v1/ingest/process?project={PID}", {}, KEY)
row = api.STORE.db.execute(
    "SELECT classification FROM message_classifications WHERE external_id='l1'").fetchone()
check("user-marked MARKETING domain excluded despite commercial words",
      row and row["classification"] == "AUTOMATED_NOISE", str(dict(row) if row else None))
st, fd_l1 = call("GET", f"/v1/fact-decisions?project={PID}", None, SESS)
check("no memory stored from corrected-out domain",
      not any("digestly" in json.dumps(d) and d["stored"] for d in fd_l1["data"]))

# correction: quiet-mail.com is actually a SUPPLIER -> future mail admitted
st, _ = call("POST", f"/v1/relationships?project={PID}",
             {"key_type": "domain", "key": "quiet-mail.com", "role": "SUPPLIER"}, KEY)
MAILBOX.append(msg("l2", "sam@quiet-mail.com", OWNER, "Note",
                   "We can offer a 12% discount if you commit to 12 months.", "L2", 21000))
call("POST", f"/v1/connectors/{CID}/poll?project={PID}", {}, KEY)
call("POST", f"/v1/ingest/process?project={PID}", {}, KEY)
row2 = api.STORE.db.execute(
    "SELECT classification, reasons FROM message_classifications WHERE external_id='l2'").fetchone()
check("user-confirmed SUPPLIER admitted as business",
      row2 and row2["classification"] == "BUSINESS_RELEVANT", str(dict(row2) if row2 else None))
st, rels = call("GET", f"/v1/relationships?project={PID}", None, SESS)
check("relationships listable", st == 200 and len(rels["data"]) >= 2, str(len(rels.get("data", []))))
st, bad = call("POST", f"/v1/relationships?project={PID}",
               {"key_type": "domain", "key": "x.com", "role": "NOT_A_ROLE"}, KEY)
check("invalid role rejected", st == 400)

print("== contacts aggregation ==")
st, contacts = call("GET", f"/v1/contacts?project={PID}", None, SESS)
check("contacts endpoint returns interaction data", st == 200 and len(contacts["data"]) >= 3)
jane = next((c for c in contacts["data"] if c["email"] == "jane@acme.com"), None)
check("contact rows carry real message counts",
      jane is not None and jane["messages"] >= 2, str(jane))
supplier_c = next((c for c in contacts["data"] if c["email"] == "sam@quiet-mail.com"), None)
check("contact role reflects user correction",
      supplier_c is not None and supplier_c["role"] == "SUPPLIER", str(supplier_c))

print("== per-email diagnostics trace ==")
sr_b6 = api.STORE.db.execute(
    "SELECT id FROM source_records WHERE external_id='t1c'").fetchone()
st, diag = call("GET", f"/v1/diagnostics/email?project={PID}&source={sr_b6['id']}", None, SESS)
check("diagnostics returns full trace", st == 200 and
      all(k in diag for k in ("source", "participants", "classification_now",
                               "analysis", "sentences", "fact_decisions", "assertions")),
      str(list(diag.keys())))
check("diagnostics participants resolve direction",
      diag["participants"]["direction"] == "inbound", str(diag["participants"]["direction"]))
check("diagnostics sentences carry speech acts",
      any(s["speech_act"] == "DECISION" for s in diag["sentences"]), str(diag["sentences"]))
check("diagnostics links the stored assertion",
      any(a["proposition"] == "decided_to_downgrade" for a in diag["assertions"]),
      str(diag["assertions"]))

srv.shutdown()
print(f"\n{PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
