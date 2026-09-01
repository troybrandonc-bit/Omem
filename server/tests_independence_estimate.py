"""Does the independence estimator tell corroboration from an echo?
Run: python3 tests_independence_estimate.py

The cases below are the whole point, built on a real engine rather than on
fixtures: two agents reading the same ticket agree and add nothing; two agents
reading different tickets agree and add a great deal; one agent agreeing with
itself adds nothing whatever its confidence says; and two agents agreeing about
something neither can evidence is not corroboration at all.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, ".."))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "scripts"))

TMP = os.environ.get("TEMP") or "/tmp"
os.environ["OMEM_DB"] = os.path.join(TMP, "omem_independence.db")
os.environ.setdefault("OMEM_SEED_DEMO", "0")
if os.path.exists(os.environ["OMEM_DB"]):
    os.remove(os.environ["OMEM_DB"])

import api  # noqa: E402
import independence_estimate as IE  # noqa: E402

PASS = FAIL = 0


def check(n, c, d=""):
    global PASS, FAIL
    if c:
        PASS += 1
        print("  ok  " + n)
    else:
        FAIL += 1
        print("  FAIL " + n + "  " + str(d)[:220])


import http.client  # noqa: E402
import threading  # noqa: E402
import time  # noqa: E402
from http.server import ThreadingHTTPServer  # noqa: E402

srv = ThreadingHTTPServer(("127.0.0.1", 0), api.Handler)
PORT = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()
time.sleep(0.3)


def call(method, path, body=None):
    c = http.client.HTTPConnection("127.0.0.1", PORT, timeout=15)
    c.request(method, path, body=json.dumps(body).encode() if body is not None else None,
              headers={"Content-Type": "application/json"})
    r = c.getresponse()
    t = r.read().decode()
    c.close()
    return json.loads(t or "{}")


PID = call("POST", "/v1/signup", {"email": "independence@omem.local"})["project"]["id"]
p = api.PROJECTS[PID]


def event(eid, label):
    api.record(p, "event", {"id": eid, "ekind": "support_ticket",
                            "event_time": p.tick(), "label": label})


def claim(aid, agent, subject, proposition, because=None):
    api.record(p, "assert", {"id": aid, "agent": agent, "subjects": [subject],
                             "proposition": proposition,
                             "assertion_time": p.tick()})
    if because:
        api.record(p, "derive", {"id": "d:" + aid, "consequent": aid,
                                 "antecedents": list(because),
                                 "dkind": "extraction"})


for a in ("crm-sync", "billing-watcher", "support-agent"):
    api.record(p, "agent", {"id": a, "kind": "system"})
for e in ("customer:acme", "customer:beta", "customer:gamma", "customer:delta"):
    api.record(p, "entity", {"id": e, "type": "organization"})

print("== the four cases ==")
# 1. two agents, one ticket: agreement that carries no new information
event("ticket:1", "the only ticket either of them read")
claim("a:echo1", "crm-sync", "customer:acme", "plan_annual_pro", ["ticket:1"])
claim("a:echo2", "billing-watcher", "customer:acme", "plan_annual_pro", ["ticket:1"])

# 2. two agents, two tickets: agreement that is worth something
event("ticket:2", "the billing portal webhook")
event("ticket:3", "a signed order form")
claim("a:indep1", "crm-sync", "customer:beta", "plan_annual_pro", ["ticket:2"])
claim("a:indep2", "billing-watcher", "customer:beta", "plan_annual_pro", ["ticket:3"])

# 3. one agent agreeing with itself, from two separate observations
event("ticket:4", "first look")
event("ticket:5", "second look")
claim("a:self1", "support-agent", "customer:gamma", "refund_eligible", ["ticket:4"])
claim("a:self2", "support-agent", "customer:gamma", "refund_eligible", ["ticket:5"])

# 4. two agents, no evidence between them
claim("a:air1", "crm-sync", "customer:delta", "churn_risk")
claim("a:air2", "billing-watcher", "customer:delta", "churn_risk")

memories = []
T = p.now()
for a in p.engine.store.assertions():
    row = api.shape_assertion(p, a.id, T)
    prov, grounded = p.engine.provenance(a.id)
    row.update({"grounded": grounded, "provenance": list(prov)})
    memories.append(row)

roots = IE.roots_of(memories)
by_id = {m["id"]: m for m in memories}


def klass(x, y):
    return IE.classify(by_id[x], by_id[y], roots)


check("an assertion's roots are the events under it, not the whole chain",
      roots["a:echo1"] == frozenset({"ticket:1"}), roots["a:echo1"])
check("two agents reading the same ticket are an echo",
      klass("a:echo1", "a:echo2") == IE.ECHO, klass("a:echo1", "a:echo2"))
check("two agents reading different tickets corroborate",
      klass("a:indep1", "a:indep2") == IE.CORROBORATING,
      klass("a:indep1", "a:indep2"))
check("one agent agreeing with itself is an echo, separate evidence or not",
      klass("a:self1", "a:self2") == IE.ECHO, klass("a:self1", "a:self2"))
check("two agents agreeing about nothing evidenced is not corroboration",
      klass("a:air1", "a:air2") == IE.UNEVIDENCED, klass("a:air1", "a:air2"))

print("== the numbers ==")
r = IE.estimate(memories)
print("     " + json.dumps(r["pairs"]) + "  echo_rate=" + str(r["echo_rate"]))
check("the echo rate counts only pairs that had evidence to share",
      r["pairs"][IE.CORROBORATING] == 1 and r["pairs"][IE.ECHO] == 2
      and r["pairs"][IE.UNEVIDENCED] == 1, r["pairs"])
check("and it reads as two thirds of evidenced agreement being an echo",
      r["echo_rate"] == round(2 / 3, 3), r["echo_rate"])

props = {(x["subject"], x["proposition"]): x for x in r["propositions"]}
check("the echoed proposition rests on one source however many agents said it",
      props[("customer:acme", "plan_annual_pro")]["independent_support"] == 1,
      props[("customer:acme", "plan_annual_pro")])
check("the genuinely corroborated one counts two",
      props[("customer:beta", "plan_annual_pro")]["independent_support"] == 2,
      props[("customer:beta", "plan_annual_pro")])
check("an unevidenced proposition supports nothing at all",
      props[("customer:delta", "churn_risk")]["independent_support"] == 0,
      props[("customer:delta", "churn_risk")])
check("the report names what looks attested but rests on one source",
      "customer:acme" in IE.report(r) and "customer:beta" not in IE.report(r),
      IE.report(r))

print("== a claim nobody contested is not an agreement ==")
check("a proposition with a single assertion produces no pairs",
      all(x["assertions"] >= 2 for x in r["propositions"]), r["propositions"])
check("an empty project reports no rate rather than a flattering zero",
      IE.estimate([])["echo_rate"] is None)

print("\n%d passed, %d failed" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)
