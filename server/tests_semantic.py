"""Adversarial semantic evaluation. Run: python3 tests_semantic.py

Tests the AI's decisions, not HTTP codes: identity/role resolution, request vs
fact vs intention vs completion, direction, Spanish-language business mail,
noise suppression, and the stale-intent supersession lifecycle through the
frozen engine. Cases where the system deliberately stays conservative (rather
than guessing) are asserted as such and labelled [conservative-by-design].
"""
import base64
import json
import os
import sys
import threading
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
DB = "/tmp/omem_semantic_tests.db"
if os.path.exists(DB):
    os.remove(DB)
os.environ["OMEM_DB"] = DB

import api  # noqa: E402
from connectors import GmailTransport  # noqa: E402
from extraction import ContextualBusinessExtractor  # noqa: E402
from classifier import classify  # noqa: E402
from http.server import ThreadingHTTPServer  # noqa: E402

PASS = FAIL = 0


def check(n, c, d=""):
    global PASS, FAIL
    if c:
        PASS += 1; print(f"  ok  {n}")
    else:
        FAIL += 1; print(f"  FAIL {n}  {d}")


IDENT = {"company_name": "Kronos", "emails": ["troy@kronos.com"],
         "domains": ["kronos.com"]}
EX = ContextualBusinessExtractor(IDENT)


def x(frm, to, body, subj="Re:"):
    f = EX.extract({"from": frm, "to": to, "subject": subj, "body": body,
                    "headers": {}, "at": "now"})
    return [(a["subject"]["id"], a["proposition"]) for a in f]


ME, CUST, SAAS, SUP = "troy@kronos.com", "jane@acme.com", "billing@saas.io", "li@supplier.cn"

print("== brief cases A-O: identity, direction, strength ==")
# A. customer asks to upgrade -> question, no flat fact; classified business
check("A: customer 'Can we upgrade our plan?' -> no flat fact",
      x(CUST, ME, "Can we upgrade our plan?") == [])
va = classify({"from": CUST, "subject": "Plan", "body": "Can we upgrade our plan for our subscription?", "headers": {}})
check("A: ...but classified business (enters pipeline)",
      va["classification"] in ("BUSINESS_RELEVANT", "POSSIBLY_BUSINESS"), va["classification"])
# B. owner -> SaaS: SELF subject, never customer
r = x(ME, SAAS, "I'd like to upgrade our subscription.")
check("B: owner->SaaS upgrade is OUR company's intent",
      r == [("company:kronos", "intends_to_upgrade")], str(r))
# C. business -> customer completed action on their account
r = x(ME, CUST, "We have cancelled your contract.")
check("C: 'we cancelled YOUR contract' -> customer's contract cancelled",
      r == [("company:acme", "has_cancelled")], str(r))
# D. request != action
r = x(CUST, ME, "Please cancel our contract.")
check("D: 'Please cancel' -> requested_cancel, never has_cancelled",
      r == [("company:acme", "requested_cancel")], str(r))
# E/F. marketing/newsletter -> nothing
check("E: newsletter 'Upgrade now and save 30%' -> no memory",
      x("news@letter.io", ME, "Upgrade now and save 30%! Click here. Unsubscribe.") == [])
check("F: marketplace 'New products available' -> no memory",
      x("promo@alibaba.com", ME, "New products available this week. Shop now.") == [])
# G. supplier offer -> negotiation memory
r = x(SUP, ME, "We can reduce the contract price by 15%.")
check("G: supplier price reduction offer captured",
      r == [("company:supplier", "offers_price_reduction_15")], str(r))
r = x(SUP, ME, "We can offer a 12% discount if you commit to 12 months.")
check("G2: percentage discount captured",
      r == [("company:supplier", "offers_discount_12")], str(r))
# H vs I. commitment vs completion
r = x(CUST, ME, "We will sign the contract Friday.")
check("H: 'will sign Friday' -> intention, NOT signed",
      r == [("company:acme", "intends_to_sign")], str(r))
r = x(CUST, ME, "We signed the contract Friday.")
check("I: 'signed Friday' -> has_signed",
      r == [("company:acme", "has_signed")], str(r))
r = x(CUST, ME, "I cancelled the subscription yesterday.")
check("I2: simple past 'I cancelled yesterday' -> has_cancelled",
      r == [("company:acme", "has_cancelled")], str(r))
# J. bare acknowledgement -> nothing without thread synthesis
check("J: 'Yes, that's fine.' alone -> no memory [thread synthesis not implemented]",
      x(CUST, ME, "Yes, that's fine.") == [])
# K. unresolvable referent stays unresolved
check("K: 'My customer wants to renew' -> no memory [conservative-by-design: WHICH customer is unknowable]",
      x(ME, "ops@kronos.com", "My customer wants to renew.") == [])
# L. owner's own subscription renewing (platform mail) -> not customer memory
check("L: 'Your subscription is renewing' notification -> no customer memory",
      x("noreply@saas.io", ME, "Your subscription is renewing on the 1st.") == [])
# M. 'your customer has paid' platform notification
check("M: 'Your customer has paid the invoice' -> conservatively dropped [recipient-side referent unresolved]",
      x("noreply@stripe.com", ME, "Your customer has paid the invoice.") == [])
# N. relationship statements carry no false action
check("N: 'This is our new supplier' -> no fabricated commercial action",
      all(not p.startswith("has_") and "cancel" not in p
          for _, p in x(CUST, ME, "This is our new supplier.")))
# O. ambiguous plural referent
check("O: 'They want to upgrade' -> no memory (ambiguous subject)",
      x(CUST, ME, "They want to upgrade their plan.") == [])

print("== Spanish-language business mail ==")
r = x("maria@clienta.es", ME, "Hola Troy, queremos cancelar nuestro contrato a final de mes.")
check("ES: customer cancellation intent extracted",
      r == [("company:clienta", "intends_to_cancel")], str(r))
r = x("maria@clienta.es", ME, "Hemos decidido renovar el contrato anual.")
check("ES: decision strength preserved",
      r == [("company:clienta", "decided_to_renew")], str(r))
r = x("maria@clienta.es", ME, "Ya firmamos el acuerdo esta ma\u00f1ana.")
check("ES: completed action", r == [("company:clienta", "has_signed")], str(r))
r = x("proveedor@fabrica.es", ME, "Podemos ofrecer un descuento del 10% en el pedido.")
check("ES: supplier discount", r == [("company:fabrica", "offers_discount_10")], str(r))
check("ES: marketing boilerplate 'puedes cancelar' stays silent",
      x("ofertas@amazon.es", ME, "Miles de ofertas. Puedes cancelar tu suscripci\u00f3n cuando quieras.") == [])
v = classify({"from": "maria@clienta.es", "subject": "Contrato",
              "body": "Hola, queremos cancelar nuestro contrato a final de mes.", "headers": {}})
check("ES: business mail classified relevant",
      v["classification"] == "BUSINESS_RELEVANT", str(dict(v)))
v = classify({"from": "ofertas@amazon.es", "subject": "Prime Day",
              "body": "Miles de ofertas. Puedes cancelar tu suscripci\u00f3n cuando quieras. Date de baja.",
              "headers": {"list-unsubscribe": "<u>"}})
check("ES: Spanish marketing NOT classified business",
      v["classification"] in ("NON_BUSINESS", "AUTOMATED_NOISE"), str(dict(v)))

print("== guards: earlier behaviour must not regress ==")
r = x(CUST, ME, "Hi Troy, we agreed the annual contract will be EUR 24,000 and renews every January.")
check("guard: contract-attribute statement yields values, no bare verbs",
      set(p for _, p in r) == {"contract_value_eur_24_000", "renews_every_january"}, str(r))
check("guard: CTA 'Want to upgrade? Click here' silent",
      x("news@waves.com", ME, "Want to upgrade your plugins? Click here.") == [])


# ── lifecycle: consideration superseded by renewal, via the frozen engine ──
print("== lifecycle: stale intent superseded through the engine ==")
srv = ThreadingHTTPServer(("127.0.0.1", 0), api.Handler)
PORT = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()
time.sleep(0.2)


def call(m, path, body=None, key=None):
    r = urllib.request.Request(f"http://127.0.0.1:{PORT}{path}", method=m,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Content-Type": "application/json",
                 **({"Authorization": f"Bearer {key}"} if key else {})})
    with urllib.request.urlopen(r, timeout=15) as resp:
        return resp.status, json.loads(resp.read() or b"{}")


def msg(mid, frm, subj, body, ts):
    raw = f"From: {frm}\r\nTo: {ME}\r\nSubject: {subj}\r\n\r\n{body}\r\n"
    return {"id": mid, "threadId": mid, "internalDate": str(ts),
            "raw": base64.urlsafe_b64encode(raw.encode()).decode()}


MAILBOX = [msg("m1", CUST, "Thinking", "We're considering cancelling next quarter.", 1000)]


class T(GmailTransport):
    def list_messages(self, token, cursor):
        return (MAILBOX, "done")


api.GMAIL_TRANSPORT_FACTORY = lambda conn: T()
_, acct = call("POST", "/v1/signup", {"email": "sem@kronos.com"})
KEY, PID = acct["api_key"]["secret"], acct["project"]["id"]
_, beg = call("POST", f"/v1/oauth/gmail/begin?project={PID}", {"name": "G"}, KEY)
CID = beg["connector_id"]
call("POST", f"/v1/oauth/gmail/callback?project={PID}", {"connector_id": CID, "account": ME}, KEY)
call("POST", f"/v1/connectors/{CID}/poll?project={PID}", {}, KEY)
call("POST", f"/v1/ingest/process?project={PID}", {}, KEY)
_, r1 = call("POST", f"/v1/recall?project={PID}", {"about": "company:acme"}, KEY)
check("churn-risk consideration becomes memory",
      any(m["proposition"] == "considering_cancel" and m["state"] == "BELIEVED_TRUE"
          for m in r1["memories"]), str(r1["memories"]))

MAILBOX.append(msg("m2", CUST, "Good news", "We've renewed for another year.", 2000))
call("POST", f"/v1/connectors/{CID}/poll?project={PID}", {}, KEY)
call("POST", f"/v1/ingest/process?project={PID}", {}, KEY)
_, r2 = call("POST", f"/v1/recall?project={PID}", {"about": "company:acme"}, KEY)
states = {m["proposition"]: m["state"] for m in r2["memories"]}
check("renewal becomes current belief", states.get("has_renewed") == "BELIEVED_TRUE", str(states))
check("old consideration no longer current belief",
      states.get("considering_cancel") != "BELIEVED_TRUE", str(states))
p = api.PROJECTS[PID]
old = [a for a in p.engine.store.assertions() if a.proposition == "considering_cancel"]
check("history preserved: old assertion exists but is closed",
      len(old) == 1 and not p.engine.ledger.is_open_at(old[0], p.now()))

srv.shutdown()
print(f"\n{PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
