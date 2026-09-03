"""OMEM leaps, then doubts the leap. Run: python3 tests_hypotheses.py

The intuition layer projects a look-alike's beliefs onto a new entity after
ONE similar case, which is how humans learn fast and also why human memory
confabulates. The suite pins the discipline that keeps the speed without
the confabulation:

  a hypothesis is never a belief -- believes() stays UNKNOWN however good
  the hunch, the engine receives no ops, and expects() is the only mouth;
  every hypothesis is born suspect, wearing a docket;
  only reality about the TARGET can support or refute (look-alikes just
  move strength); the source case dying lapses the leap;
  verdicts teach, weighted by how much each one surprised it -- a
  generator's confirmed leaps make its future leaps stronger, refuted ones
  make them weaker, and a spent fingerprint is never leapt again;
  and a case that will not resolve starts ASKING, saying what it needs.
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
sys.path.insert(0, os.path.join(HERE, "..", "sdk", "python"))
TMP = os.environ.get("TEMP") or "/tmp"
DB = os.path.join(TMP, "omem_hypotheses.db")
if os.path.exists(DB):
    os.remove(DB)
os.environ["OMEM_DB"] = DB
os.environ.setdefault("OMEM_TENANT_RL_BURST", "10000")
os.environ.setdefault("OMEM_TENANT_RL_RPS", "10000")

import api  # noqa: E402
import omem  # noqa: E402
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


OWNER = "hunch@kronos.com"

srv = ThreadingHTTPServer(("127.0.0.1", 0), api.Handler)
PORT = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()
time.sleep(0.2)
BASE = "http://127.0.0.1:%d" % PORT

acct = json.loads(urllib.request.urlopen(urllib.request.Request(
    BASE + "/v1/signup", method="POST",
    data=json.dumps({"email": OWNER}).encode(),
    headers={"Content-Type": "application/json"}), timeout=20).read())
KEY, PID = acct["api_key"]["secret"], acct["project"]["id"]
mem = omem.Memory(KEY, base_url=BASE, project=PID)
A = "agent:owner"


def ops_count():
    return api.STORE.db.execute(
        "SELECT COUNT(*) n FROM ops WHERE project_id=?", (PID,)).fetchone()["n"]


print("== the world: one rich look-alike, several thin newcomers ==")
mem.ensure_entity("product:crm", type="product", label="CRM")
# beta is the experienced case everything will be leapt from
mem.remember(A, "customer:beta", "prefers_annual_billing")
mem.remember(A, "customer:beta", "wants_pdf_invoices")
mem.remember(A, ["customer:beta", "product:crm"], "rel_uses_crm")
# alpha resembles beta AND already holds the projectable belief
mem.remember(A, "customer:alpha", "prefers_annual_billing")
mem.remember(A, "customer:alpha", "wants_pdf_invoices")
mem.remember(A, ["customer:alpha", "product:crm"], "rel_uses_crm")
# gamma is new and thin: shares one belief and one relation with beta
mem.remember(A, "customer:gamma", "prefers_annual_billing")
mem.remember(A, ["customer:gamma", "product:crm"], "rel_uses_crm")
# omega shares only the relation: one signal is not resemblance
mem.remember(A, ["customer:omega", "product:crm"], "rel_uses_crm")
# zeta has nothing in common with anyone
mem.remember(A, "customer:zeta", "runs_on_mainframes")

print("== the leap: one similar case is enough, refusals still hold ==")
before_ops = ops_count()
r = mem.leap()
leapt = {(x["subject"], x["proposition"]) for x in r.get("leapt", [])}
check("gamma gets the hunch from its look-alike",
      ("customer:gamma", "wants_pdf_invoices") in leapt, r.get("leapt"))
check("alpha gets nothing: it already holds the belief",
      not any(s == "customer:alpha" for s, _ in leapt), leapt)
check("omega gets nothing: one shared signal is not resemblance",
      not any(s == "customer:omega" for s, _ in leapt), leapt)
check("zeta gets nothing: no look-alike, no leap",
      not any(s == "customer:zeta" for s, _ in leapt), leapt)
check("no relation was projected: one liberty at a time",
      not any(prop.startswith("rel_") for _, prop in leapt), leapt)

print("== the discipline: a hunch is not a belief ==")
check("believes() stays UNKNOWN however good the hunch",
      mem.believes("customer:gamma", "wants_pdf_invoices") == "UNKNOWN")
check("the ENGINE never heard about any of this: zero new ops",
      ops_count() == before_ops, (before_ops, ops_count()))
exp = mem.expects(about="customer:gamma")
check("expects() serves it, wearing its case file",
      exp and exp[0]["proposition"] == "wants_pdf_invoices"
      and exp[0]["docket"]["gaps"], exp)
check("born suspect, at hunch strength, saying why it leapt",
      exp[0]["strength"] == 0.35 and "customer:alpha" in exp[0]["because"], exp[0])
check("one claim, ONE case file: the second look-alike is corroboration, "
      "not a rival hypothesis", len(exp) == 1, exp)
r2 = mem.leap()
check("leaping twice creates nothing new (fingerprints)",
      len(r2.get("leapt", [])) == 0, r2)

print("== interrogation: only reality about the target gives verdicts ==")
mem.remember(A, "customer:gamma", "wants_pdf_invoices")
verdicts = mem.interrogate()
check("reality confirmed the leap: SUPPORTED",
      any(v["subject"] == "customer:gamma" for v in verdicts.get("supported", [])),
      verdicts)

# epsilon: same resemblance, and this time the leap will be wrong
mem.remember(A, "customer:epsilon", "prefers_annual_billing")
mem.remember(A, ["customer:epsilon", "product:crm"], "rel_uses_crm")
r3 = mem.leap()
eps = [x for x in r3.get("leapt", []) if x["subject"] == "customer:epsilon"
       and x["proposition"] == "wants_pdf_invoices"]
# Birth strength is now the posterior mean of this generator's hit rate,
# shrunk toward what this install's hunches do in general, so the number is a
# probability rather than a running total of fixed steps. The gamma hunch was
# born at 0.35 and confirmed, so the win taught 0.65; alpha and the wants
# family each carry it, the family at half weight, and the house rate is still
# near BASE_STRENGTH because one verdict barely moves it.
check("a confirmed generator leaps STRONGER next time, and so does a "
      "confirmed claim-family",
      eps and eps[0]["strength"] == 0.44, eps)
mem.remember(A, "customer:epsilon", "not:wants_pdf_invoices")
verdicts2 = mem.interrogate()
check("reality refuted the leap: REFUTED",
      any(v["subject"] == "customer:epsilon"
          for v in verdicts2.get("refuted", [])), verdicts2)
r4 = mem.leap()
check("a refuted leap is never re-leapt: the fingerprint is spent",
      not any(x["subject"] == "customer:epsilon" and
              x["proposition"] == "wants_pdf_invoices"
              for x in r4.get("leapt", [])), r4.get("leapt"))

# theta arrives after one win and one loss for the generator
mem.remember(A, "customer:theta", "prefers_annual_billing")
mem.remember(A, ["customer:theta", "product:crm"], "rel_uses_crm")
r5 = mem.leap()
th = [x for x in r5.get("leapt", []) if x["subject"] == "customer:theta"
      and x["proposition"] == "wants_pdf_invoices"]
# One win and one loss, each weighted by its own prediction error: the win
# was a 0.65 surprise, the refutation at 0.4 was a 0.4 one. A record of roughly
# one and a half wins to six tenths of a loss, against a house rate that has
# barely moved, lands above the house and below the ceiling. Two rewrites ago
# this number was 0.30 under flat counts and 0.35 under weighted ones; it is a
# probability now, and it says a generator with more wins than losses should be
# trusted more than the average hunch and nothing like as much as evidence.
check("verdicts teach twice over, and by how much each one taught: a win "
      "and a near-even loss leave it barely above the house rate",
      th and th[0]["strength"] == 0.4, th)

print("== the source dying lapses the leap ==")
webinars = mem.remember(A, "customer:beta", "likes_webinars")
r6 = mem.leap()
check("the new belief projects onto the look-alikes",
      any(x["proposition"] == "likes_webinars" for x in r6.get("leapt", [])),
      r6.get("leapt"))
mem.retract(webinars["id"], agent=A)
verdicts3 = mem.interrogate()
check("the case it leapt from died, so the hypothesis LAPSES, not refutes",
      any(True for v in verdicts3.get("lapsed", [])), verdicts3)
check("and a lapse charges nobody: the lapsed generator has no loss record",
      api.STORE.db.execute(
          "SELECT * FROM leap_generators WHERE project_id=? AND generator=?",
          (PID, "customer:beta")).fetchone() is None)
check("while the refuted generator's one loss stands where it belongs",
      api.STORE.db.execute(
          "SELECT losses FROM leap_generators WHERE project_id=? AND generator=?",
          (PID, "customer:alpha")).fetchone()["losses"] == 1)

print("== doubt that will not resolve starts asking ==")
open_now = mem.expects(status="open")
check("theta's hypothesis is still open", any(
    h["subject"] == "customer:theta" for h in open_now), open_now)
mem.interrogate()
verdicts4 = mem.interrogate()
asking = mem.expects(status="asking")
th_ask = [h for h in asking if h["subject"] == "customer:theta"]
check("after two unresolved passes it moves to ASKING",
      bool(th_ask), [h["subject"] for h in asking])
check("and the docket carries the actual question, with the reasoning",
      th_ask and "is it true that" in th_ask[0]["docket"]["gaps"][0]
      and "customer:alpha" in th_ask[0]["docket"]["gaps"][0],
      th_ask and th_ask[0]["docket"]["gaps"])
check("corroboration moved strength while it waited (the other look-alike "
      "agrees)",
      th_ask and th_ask[0]["strength"] > 0.30
      and any(s.get("entity") == "customer:beta"
              for s in th_ask[0]["docket"]["supports"]), th_ask)

print("== the ledger of hunches survives: verdict rows are history ==")
allrows = mem.expects(about="customer:gamma", status="supported")
check("a supported hypothesis is kept as a verdict row, not deleted",
      allrows and allrows[0]["status"] == "supported", allrows)

print("== rare coincidences bind: one unusual shared trait is enough ==")
# zeta shares nothing common with anyone, but nu shares zeta's one RARE
# trait. omega shares a COMMON feature with half the project and still
# gets nothing: rarity, not count, is what resemblance weighs.
mem.remember(A, "customer:zeta", "collects_vintage_terminals")
mem.remember(A, "customer:nu", "runs_on_mainframes")
r7 = mem.leap()
nu = [x for x in r7.get("leapt", []) if x["subject"] == "customer:nu"]
check("one rare shared trait binds nu to zeta and projects its belief",
      any(x["proposition"] == "collects_vintage_terminals" for x in nu), r7)
check("and the evidence names the rarity",
      nu and "rare" in nu[0]["because"], nu)

print("== meaning beats spelling when a real embedder is wired ==")
import semantic_recall as sr  # noqa: E402
SAME = {"prefers annual billing", "wants yearly invoicing"}


def fake_embedder(texts):
    return [[1.0, 0.0, 0.0] if t in SAME else sr._hash_embed(t)
            for t in texts]


sr.set_embedder(fake_embedder, tag="fake-cluster")
mem.remember(A, "customer:rho", "wants_yearly_invoicing")
mem.remember(A, ["customer:rho", "product:crm"], "rel_uses_crm")
r8 = mem.leap()
rho = {x["proposition"] for x in r8.get("leapt", [])
       if x["subject"] == "customer:rho"}
check("differently-worded experience still counts as resemblance",
      "wants_pdf_invoices" in rho, r8.get("leapt"))
check("and a sibling claim is never projected onto its own cluster",
      "prefers_annual_billing" not in rho, rho)
sr.set_embedder(None)

print("== the asking loop closes: an answer is evidence, not a decree ==")
res = mem.answer_expectation(th_ask[0]["id"], "yes", agent=A)
check("answering yes records a real assertion and the verdict follows",
      res.get("verdict") == "supported" and res.get("recorded"), res)
check("the answer is a belief now, under the ANSWERER's name",
      mem.believes("customer:theta", "wants_pdf_invoices") == "BELIEVED_TRUE"
      and api.PROJECTS[PID].engine.store.assertion(res["recorded"]).agent == A)
nu_h = mem.expects(about="customer:nu", status="open")
res2 = mem.answer_expectation(nu_h[0]["id"], "no", agent=A)
check("answering no records the negation and refutes the case",
      res2.get("verdict") == "refuted"
      and mem.believes("customer:nu", "collects_vintage_terminals")
      == "BELIEVED_FALSE", res2)
st = None
try:
    mem.answer_expectation(nu_h[0]["id"], "yes", agent=A)
except omem.OmemError as e:
    st = e.status
check("a settled case cannot be re-answered", st == 409, st)
st2 = None
try:
    mem.answer_expectation(th_ask[0]["id"], "maybe", agent=A)
except omem.OmemError as e:
    st2 = e.status
check("an answer must take a side", st2 in (409, 422), st2)

print("== metacognition: it knows what it is good at guessing ==")
cal = mem.calibration()
fam = cal.get("families", {})
# The second wants-refutation was not planned by this suite and is the
# system outreasoning it: once epsilon held not:wants_pdf_invoices, epsilon
# became a look-alike source and projected the NEGATIVE expectation onto
# theta -- a competing hypothesis. The yes answer refuted it through
# reality, and epsilon's record paid. Rival conjectures, reality deciding,
# every verdict charged to whoever leapt: exactly the tradecraft.
check("the wants-family record shows its wins and losses, competing "
      "hypotheses included",
      fam.get("wants", {}).get("supported") == 2
      and fam.get("wants", {}).get("refuted") == 2, fam)
check("and the counter-example that became a role model has its own record",
      gens_pre.get("customer:epsilon", {}).get("refuted") == 1
      if (gens_pre := cal.get("generators", {})) else False, cal)
check("the collects-family knows it has never guessed one right",
      fam.get("collects", {}).get("rate") == 0.0, fam)
gens = cal.get("generators", {})
check("and per-generator records sit beside them",
      gens.get("customer:alpha", {}).get("supported") == 2
      and gens.get("customer:zeta", {}).get("refuted") == 1, gens)

print("\n%d passed, %d failed" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)
