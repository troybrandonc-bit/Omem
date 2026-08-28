"""Declared shapes detect tensions; only a person resolves them. Run:
python3 tests_constraints.py

The engine's conflict rule is subject-set equality under coreference, which
is what keeps belief state reproducible -- and it means "Sarah works at Acme"
and "Sarah works at Beta" never contradict: different subject sets, both open
forever, each looking uncontested. Whether that is fine is domain knowledge
(supplies is many-to-many; works_at usually is not), so the shape a relation
may take is DECLARED, like a contradiction and like a rule:

    works_at is one_dst_per_src -- one employer at a time.

A violation among live edges becomes an open TENSION in the queue. Nothing
else happens: OMEM does not pick the newer employer. A person resolves by
naming the belief to keep (the rest are retracted under their name, and rule
conclusions resting on a retracted premise fall in the same request), or
dismisses, which is permanent for exactly that holder set.

The suite is mostly the boundaries: no engine involvement, no auto-
resolution, never the same nag twice, dismissals never widened, lapses on
changed evidence, and everything reconstructable from the op log.
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
DB = os.path.join(TMP, "omem_constraints.db")
if os.path.exists(DB):
    os.remove(DB)
os.environ["OMEM_DB"] = DB
# This suite fires ~40 SDK calls back to back; the default tenant limiter
# (burst 60, then 20/s) is for production tenants, not a test loop. The env
# knobs are the documented operator override, read at api import.
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


OWNER = "tensions@kronos.com"

srv = ThreadingHTTPServer(("127.0.0.1", 0), api.Handler)
PORT = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()
time.sleep(0.2)
BASE = "http://127.0.0.1:%d" % PORT


def call(m, path, body=None, key=None):
    h = {"Content-Type": "application/json"}
    if key:
        h["Authorization"] = "Bearer " + key
    r = urllib.request.Request(
        BASE + path, method=m,
        data=json.dumps(body).encode() if body is not None else None, headers=h)
    try:
        with urllib.request.urlopen(r, timeout=20) as resp:
            return resp.status, json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


acct = call("POST", "/v1/signup", {"email": OWNER})[1]
KEY, PID = acct["api_key"]["secret"], acct["project"]["id"]
mem = omem.Memory(KEY, base_url=BASE, project=PID)
A = "agent:owner"

print("== declaring shapes: data in, judgments refused ==")
st, bad = call("POST", "/v1/constraints?project=%s" % PID,
               {"relation": "acquired", "kind": "one_dst_per_src"}, KEY)
check("a relation outside the vocabulary cannot be constrained", st == 422, bad)
st, bad2 = call("POST", "/v1/constraints?project=%s" % PID,
                {"relation": "works_at", "kind": "at_most_three"}, KEY)
check("a made-up shape cannot be declared", st == 422, bad2)
c1 = mem.declare_constraint("works_at", "one_dst_per_src", agent=A)
check("works_at declared one-employer-at-a-time", c1.get("active") is True, c1)
c1b = mem.declare_constraint("works_at", "one_dst_per_src")
check("declaring twice is declaring once", c1b.get("id") == c1["id"], c1b)
check("and it is listed", any(c["id"] == c1["id"] for c in mem.constraints()))

print("== the clash the engine cannot see ==")
acme = mem.remember(A, ["person:sarah", "company:acme"], "rel_works_at_acme")
beta = mem.remember(A, ["person:sarah", "company:beta"], "rel_works_at_beta")
check("both employments are believed",
      mem.believes(["person:sarah", "company:acme"], "rel_works_at_acme")
      == "BELIEVED_TRUE"
      and mem.believes(["person:sarah", "company:beta"], "rel_works_at_beta")
      == "BELIEVED_TRUE")
check("and the ENGINE sees no conflict: different subject sets never contradict",
      mem.conflict_pairs() == [], mem.conflict_pairs())

r = mem.check()
raised = r.get("raised", [])
check("the check raises exactly one tension", len(raised) == 1, r)
check("naming the person and both employers",
      raised and raised[0]["entity"] == "person:sarah"
      and raised[0]["between"] == ["company:acme", "company:beta"], raised)
check("detection changed no belief",
      mem.believes(["person:sarah", "company:beta"], "rel_works_at_beta")
      == "BELIEVED_TRUE")
r2 = mem.check()
check("a second check raises nothing new (idempotent)",
      len(r2.get("raised", [])) == 0 and r2.get("unchanged", 0) == 1, r2)

# Corroboration is not violation: a second assertion of the SAME employment
# adds no counterparty, so the tension's evidence is unchanged.
mem.remember(A, ["person:sarah", "company:acme"], "rel_works_at_acme")
r3 = mem.check()
check("re-asserting one employment is corroboration, not a new tension",
      len(r3.get("raised", [])) == 0, r3)

print("== a person resolves; the machine only carries out the judgment ==")
mem.remember(A, ["company:root", "company:beta"], "rel_owns_beta")
mem.declare_rule(when=[("works_at", "fwd"), ("owns", "rev")],
                 then=("involves", "rev"))
mem.infer()
check("a rule concluded from the doomed employment first",
      mem.believes(["company:root", "person:sarah"], "rel_involves_sarah")
      == "BELIEVED_TRUE")

tension = mem.tensions(status="open")[0]
st, refuse = call("POST", "/v1/memory/tensions/%s/resolve?project=%s"
                  % (tension["id"], PID), {"keep": "a_nonsense", "agent": A}, KEY)
check("keep must name one of the holders", st == 422, refuse)
res = mem.resolve_tension(tension["id"], keep="company:acme", agent=A)
check("resolution keeps the named employer and retracts beliefs toward the rest",
      res.get("kept") == "company:acme" and res.get("retracted") == [beta["id"]], res)
check("the kept employment still stands",
      mem.believes(["person:sarah", "company:acme"], "rel_works_at_acme")
      == "BELIEVED_TRUE")
check("the other is withdrawn, not negated",
      mem.believes(["person:sarah", "company:beta"], "rel_works_at_beta")
      == "UNKNOWN")
check("and the rule conclusion resting on it fell IN THE SAME REQUEST",
      mem.believes(["company:root", "person:sarah"], "rel_involves_sarah")
      == "UNKNOWN")
done = [t for t in mem.tensions(status="resolved") if t["id"] == tension["id"]]
check("the judgment is on the record with who made it",
      done and done[0]["decided_by"] == A and done[0]["kept"] == "company:acme",
      done)
check("and the next check has nothing to say about it",
      len(mem.check().get("raised", [])) == 0)

print("== dismissed means dismissed, for exactly what was dismissed ==")
t_acme = mem.remember(A, ["person:tom", "company:acme"], "rel_works_at_acme")
t_glob = mem.remember(A, ["person:tom", "company:globex"], "rel_works_at_globex")
r4 = mem.check()
check("Tom's two employers raise a tension", len(r4.get("raised", [])) == 1, r4)
tom_t = mem.tensions(status="open")[0]
mem.dismiss_tension(tom_t["id"], agent=A)
check("both of Tom's employments still stand: dismissal judges the shape, "
      "not the beliefs",
      mem.believes(["person:tom", "company:acme"], "rel_works_at_acme")
      == "BELIEVED_TRUE"
      and mem.believes(["person:tom", "company:globex"], "rel_works_at_globex")
      == "BELIEVED_TRUE")
r5 = mem.check()
check("the machine never nags twice about judged evidence",
      len(r5.get("raised", [])) == 0 and r5.get("spent", 0) >= 1, r5)

t_ini = mem.remember(A, ["person:tom", "company:initech"], "rel_works_at_initech")
r6 = mem.check()
check("a THIRD employer is new evidence and raises a new tension",
      len(r6.get("raised", [])) == 1
      and len(r6["raised"][0]["between"]) == 3, r6)
mem.retract(t_ini["id"], agent=A)
r7 = mem.check()
check("retracting it lapses the three-way tension: the evidence changed",
      any("evidence changed" in x.get("reason", "") for x in r7.get("lapsed", [])), r7)
check("and the two-way violation is NOT re-raised: it was already dismissed",
      len(r7.get("raised", [])) == 0 and r7.get("spent", 0) >= 1, r7)

print("== a deactivated constraint takes its questions with it ==")
mem.remember(A, ["person:dana", "company:acme"], "rel_works_at_acme")
mem.remember(A, ["person:dana", "company:beta"], "rel_works_at_beta")
r8 = mem.check()
check("Dana's tension raises while the constraint is on",
      len(r8.get("raised", [])) == 1, r8)
mem.deactivate_constraint(c1["id"])
r9 = mem.check()
check("deactivation lapses it",
      any("constraint deactivated" in x.get("reason", "")
          for x in r9.get("lapsed", [])), r9)
check("and raises nothing while off", len(r9.get("raised", [])) == 0, r9)
mem.declare_constraint("works_at", "one_dst_per_src")
r10 = mem.check()
check("redeclaring reopens the undecided question: a lapse was circumstance, "
      "not judgment", len(r10.get("raised", [])) == 1, r10)

print("== replay: the judgments reconstruct from the op log ==")
p2 = api.Project(PID, "replay")
for op in api.STORE.ops_for(PID):
    p2.clock = max(p2.clock, op["clock"])
    api.apply_op(p2, op["kind"], op["args"])
T2 = p2.now()
check("the resolved-away employment is withdrawn after replay",
      p2.engine.proposition_state(["person:sarah", "company:beta"],
                                  "rel_works_at_beta", T2) == "UNKNOWN")
check("the kept one survives replay",
      p2.engine.proposition_state(["person:sarah", "company:acme"],
                                  "rel_works_at_acme", T2) == "BELIEVED_TRUE")

print("\n%d passed, %d failed" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)
