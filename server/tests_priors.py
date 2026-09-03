"""The priors tier: learn about people in general, then doubt it per person.

Run: python3 tests_priors.py

The intuition layer leaps from one look-alike PERSON. The priors tier leaps
from a learned REGULARITY: "people who hold P tend to hold Q", mined across
many subjects, then projected onto a new person who holds P but has said
nothing about Q. This suite pins the whole contract:

  * a prior forms only from enough examples (PRIOR_FLOOR_N), and a pattern
    seen on too few people does not become a law;
  * a prior fires ONLY into a silence -- a person known to hold not:Q is never
    given the Q hunch, so a general pattern never overrides an individual;
  * a prior-born hunch is still a hunch: believes() stays UNKNOWN, the engine
    never hears it, and its case file names the prior it came from;
  * when reality settles the hunch, the prior's own record takes the verdict,
    exactly like any generator.
"""
import os
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "sdk", "python"))
TMP = os.environ.get("TEMP") or "/tmp"
DB = os.path.join(TMP, "omem_priors.db")
if os.path.exists(DB):
    os.remove(DB)
os.environ["OMEM_DB"] = DB
os.environ.setdefault("OMEM_TENANT_RL_BURST", "10000")
os.environ.setdefault("OMEM_TENANT_RL_RPS", "10000")

import api  # noqa: E402
import omem  # noqa: E402
import json  # noqa: E402
import urllib.request  # noqa: E402
from http.server import ThreadingHTTPServer  # noqa: E402

PASS = FAIL = 0


def check(n, c, d=""):
    global PASS, FAIL
    if c:
        PASS += 1
        print("  ok  " + n)
    else:
        FAIL += 1
        print("  FAIL " + n + "  " + str(d)[:240])


srv = ThreadingHTTPServer(("127.0.0.1", 0), api.Handler)
PORT = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()
time.sleep(0.2)
BASE = "http://127.0.0.1:%d" % PORT

req = urllib.request.Request(BASE + "/v1/signup", method="POST",
                             data=json.dumps({"email": "priors@kronos.com"}).encode(),
                             headers={"Content-Type": "application/json"})
acct = json.loads(urllib.request.urlopen(req, timeout=20).read())
KEY, PID = acct["api_key"]["secret"], acct["project"]["id"]
mem = omem.Memory(KEY, base_url=BASE, project=PID)
A = "agent:analyst"

P = "likes_dashboards"          # antecedent
Q = "wants_pdf_invoices"        # consequent

print("== a population, so a regularity can be learned ==")
# Twelve people hold P and Q: the support for a prior P -> Q.
#
# It used to be four, and four is no longer enough. The rule requires the
# LOWER BOUND of the pair's rate to beat the consequent's own base rate, and
# the bound on four of five is 0.38, which establishes very little. That is
# the intended behaviour rather than an inconvenience: a regularity about
# people should not be learnable from five of them. It does mean a small
# installation will mine nothing for a long time, which is exactly the gap
# the commons exists to fill.
for who in ("alpha", "bravo", "charlie", "delta", "echo", "foxtrot",
            "golf", "hotel", "india", "juliet", "kilo", "lima"):
    mem.remember(A, "person:" + who, P)
    mem.remember(A, "person:" + who, Q)
# eve holds P and has said nothing about Q: the silence a prior fills
mem.remember(A, "person:eve", P)
# frank holds P but the opposite of Q: a known individual a prior must respect
mem.remember(A, "person:frank", P)
mem.remember(A, "person:frank", "not:" + Q)
# two people share a different pair, too few to become a law
mem.remember(A, "person:gus", "runs_kubernetes")
mem.remember(A, "person:gus", "needs_audit_logs")
mem.remember(A, "person:hank", "runs_kubernetes")
mem.remember(A, "person:hank", "needs_audit_logs")
# ...and four people who do NOT like dashboards and do NOT want PDF invoices.
# Without them this fixture was itself the bug the lift test was added for:
# nearly everyone here held Q, so "P implies Q" was Q's popularity wearing P
# as a hat, and PRIOR_MIN_LIFT now refuses it. With them, Q is held by five of
# eleven overall and by four of five among P-holders, which is an association.
# ...and twenty who do NOT want PDF invoices and have no view on dashboards,
# so Q is held by twelve of thirty three overall and by twelve of thirteen
# among P-holders. That gap is the association; without it the pair would be
# Q's popularity wearing P as a hat.
for i in range(20):
    mem.remember(A, "person:other%d" % i, "not:" + Q)

print("== mining the priors tier ==")
learned = mem.learn_priors()
check("mining reports it learned at least one regularity",
      learned.get("learned", 0) >= 1, learned)

prs = mem.priors()
by_pattern = {(x["antecedent"], x["consequent"]): x for x in prs}
pq = by_pattern.get((P, Q))
check("the prior P -> Q was learned", pq is not None, list(by_pattern))
check("its population support is the twelve who hold both",
      pq and pq["in_population"]["support"] == 12, pq)
check("frank's opposite counts as refute, not support",
      pq and pq["in_population"]["refute"] == 1, pq)
check("its population rate is 12 of 13, and it is allowed to fire",
      pq and pq["in_population"]["rate"] == 0.92 and pq["fires"] is True, pq)
check("nothing has been applied yet, so it has no verdict record",
      pq and pq["when_applied"]["rate"] is None, pq)
check("a pair seen on only two people did NOT become a prior",
      ("runs_kubernetes", "needs_audit_logs") not in by_pattern, list(by_pattern))

print("== the prior fires into a silence, and only a silence ==")
r = mem.leap()
leapt = {(x["subject"], x["proposition"]): x for x in r.get("leapt", [])}
check("eve, who holds P and is silent on Q, gets the hunch",
      ("person:eve", Q) in leapt, list(leapt))
check("and it is attributed to the prior, not a look-alike person",
      leapt.get(("person:eve", Q), {}).get("from_prior"), leapt.get(("person:eve", Q)))
check("frank does NOT get it: he is known to hold the opposite",
      ("person:frank", Q) not in leapt, list(leapt))
check("the alpha-delta four get nothing: they already hold Q",
      not any(s.startswith("person:") and s[7:] in
              ("alpha", "bravo", "charlie", "delta") and pr == Q
              for s, pr in leapt), list(leapt))

print("== a prior-born hunch is still a hunch ==")
check("believes() about eve stays UNKNOWN: the engine never heard it",
      mem.believes("person:eve", Q) == "UNKNOWN")
exp = mem.expects(about="person:eve")
case = exp[0] if exp else {}
check("expects() serves it with its case file",
      case.get("proposition") == Q and case.get("docket"), case)
check("the case file names the prior it leapt from",
      any(s.get("kind") == "prior" for s in case.get("docket", {}).get("supports", [])),
      case.get("docket"))

print("== reality settles it, and the prior's record takes the verdict ==")
mem.remember(A, "person:eve", Q)            # eve turns out to hold Q after all
mem.interrogate()
after = mem.expects(about="person:eve", status="supported")
check("the hunch is now SUPPORTED, by reality about eve",
      any(h["proposition"] == Q for h in after), after)
prs2 = {(x["antecedent"], x["consequent"]): x for x in mem.priors()}
pq2 = prs2.get((P, Q))
check("the prior's applied record shows the win",
      pq2 and pq2["when_applied"]["supported"] == 1, pq2)

print("== calibration surfaces the priors tier ==")
cal = mem.calibration()
check("calibration includes a priors section",
      isinstance(cal.get("priors"), list) and cal["priors"], cal.get("priors"))

print("\n%d passed, %d failed" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)
