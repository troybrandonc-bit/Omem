"""A reconcile repairs nothing. Run: python3 tests_projection_invariant.py

OMEM keeps two projections above the engine: the candidate index and the
memory graph. Both are now maintained on every accepted write, so restarting a
healthy OMEM must find nothing to fix. That turns a metric into an INVARIANT,
and an invariant is worth asserting.

It was not one before. The graph was written only on the ingest/observe path
and otherwise rebuilt at boot, so any deployment using the SDK or the HTTP API
directly drifted as a matter of course and repaired itself at every restart.
Drift was therefore expected, which made it useless as a signal: nobody could
act on a warning that fires for everyone.

THE OTHER HALF IS THAT THE DETECTOR HAS TO BE ABLE TO SEE. Drift was measured
by comparing ROW COUNTS before and after the rebuild, which notices rows
appearing or vanishing and nothing else. A relation renamed, a token attached
to the wrong assertion, a stale assertion_time -- same count, no drift
reported, and answers quietly different from what the engine says. Both
rebuilds now report what they actually changed.

So this suite asserts both directions:

  after exercising every write path, a reconcile changes nothing;
  after CONTENT is corrupted without changing any row count, it is caught.

The second is the one that matters. "No drift" from a detector that cannot see
content drift is not reassurance, it is silence.

AND IT ASSERTS THE GAP, because a claim about integrity should be exact about
its own limits. Edge DIRECTION is not engine truth: the engine holds subjects
as a set (primitives.py says "order not observable", trust.py compares them
with frozenset), so which end of a relation is the source is information the
engine does not have. It comes from formation and rebuild takes it on trust. A
reversed edge therefore survives and reconcile still reports the system clean.
That is asserted here rather than left to be discovered, since the alternative
-- giving subjects an observable order -- is an engine invariant, not a
projection detail.
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
DB = os.path.join(TMP, "omem_projection_invariant.db")
if os.path.exists(DB):
    os.remove(DB)
os.environ["OMEM_DB"] = DB

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
        print("  FAIL " + n + "  " + str(d)[:240])


srv = ThreadingHTTPServer(("127.0.0.1", 0), api.Handler)
threading.Thread(target=srv.serve_forever, daemon=True).start()
time.sleep(0.2)
BASE = "http://127.0.0.1:%d" % srv.server_address[1]


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


acct = call("POST", "/v1/signup", {"email": "projection@kronos.com"})[1]
KEY, PID = acct["api_key"]["secret"], acct["project"]["id"]
mem = omem.Memory(KEY, base_url=BASE, project=PID)
P = api.PROJECTS[PID]
A = "agent:sales"


def reconcile():
    return api._reconcile_projections(P)


print("== every write path leaves both projections correct ==")
# Each of these reaches record() by a different route. The graph used to be
# projected on only one of them.
mem.remember(A, "company:acme", "prefers_annual_billing")            # plain fact
rel = mem.remember(A, ["person:sarah", "company:acme"], "rel_works_at")
mem.remember(A, ["company:acme", "company:globex"], "rel_supplies")
mem.ensure_entity("company:initech")
call("POST", "/v1/assertions?project=%s" % PID,                       # supersede
     {"agent": A, "subjects": ["person:sarah", "company:initech"],
      "proposition": "rel_works_at", "assertion_time": "now",
      "olds": [rel["id"]]}, KEY)
call("POST", "/v1/observe?project=%s" % PID,                          # observe
     {"agent": A, "interaction": {
         "text": "We have decided to renew the annual contract.",
         "speaker": "pat@acme.com"}}, KEY)

r = reconcile()
check("a reconcile straight after writing repairs nothing",
      r["drift_repaired"] is False, r)
check("and says so with no detail to report", not r["detail"], r)

r2 = reconcile()
check("running it again is still clean (idempotent)",
      r2["drift_repaired"] is False, r2)

print("== a retraction does not put them out of step ==")
call("POST", "/v1/assertions/%s/retract?project=%s" % (rel["id"], PID), {}, KEY)
r = reconcile()
check("reconcile after a retraction repairs nothing", r["drift_repaired"] is False, r)

print("== CONTENT corruption is detected, not just missing rows ==")
# The point of the change. Every corruption below keeps the row COUNT
# identical, so the previous count-based detector reported a clean system.


def edge_row():
    return dict(api.STORE.db.execute(
        "SELECT * FROM memory_edges WHERE project_id=? AND relation='supplies'",
        (PID,)).fetchone())


orig = edge_row()
n_before = api.STORE.db.execute(
    "SELECT COUNT(*) n FROM memory_edges WHERE project_id=?", (PID,)).fetchone()["n"]

# What a rebuild CAN check, and what it cannot.
#
# The engine holds subjects as a set -- primitives.py says "order not
# observable" and trust.py compares them with frozenset -- so which end of a
# relation is the source is information the engine does not have. Direction
# comes from formation and rebuild takes it on trust. Asserting that a flipped
# edge gets repaired would be asserting something the design cannot do, so this
# pins the real behaviour instead, including the gap.
api.STORE.db.execute(
    "UPDATE memory_edges SET src=?, dst=? WHERE project_id=? AND assertion_id=?",
    (orig["dst"], orig["src"], PID, orig["assertion_id"]))
api.STORE.db.commit()
r = reconcile()
check("a reversed direction is NOT caught: the engine has no direction to "
      "check against", r["drift_repaired"] is False, r)
check("and the reversed row survives the rebuild, as documented",
      (edge_row()["src"], edge_row()["dst"]) == (orig["dst"], orig["src"]),
      edge_row())
api.STORE.db.execute(
    "UPDATE memory_edges SET src=?, dst=? WHERE project_id=? AND assertion_id=?",
    (orig["src"], orig["dst"], PID, orig["assertion_id"]))
api.STORE.db.commit()

# The relation itself IS engine truth, and this is the case the old
# count-based detector missed: one row changed, count identical.
api.STORE.db.execute(
    "UPDATE memory_edges SET relation='owns' WHERE project_id=? AND assertion_id=?",
    (PID, orig["assertion_id"]))
api.STORE.db.commit()
n_after = api.STORE.db.execute(
    "SELECT COUNT(*) n FROM memory_edges WHERE project_id=?", (PID,)).fetchone()["n"]
check("the corruption left the row count identical", n_before == n_after,
      (n_before, n_after))
r = reconcile()
check("a renamed relation IS reported as drift", r["drift_repaired"] is True, r)
check("named as the memory graph", "memory_graph" in r["detail"], r["detail"])
check("and the relation is restored from the engine",
      edge_row()["relation"] == "supplies", edge_row())
check("after which it is clean again", reconcile()["drift_repaired"] is False)

print("== the same holds for the candidate index ==")
row = dict(api.STORE.db.execute(
    "SELECT * FROM candidate_subjects WHERE project_id=? LIMIT 1", (PID,)).fetchone())
api.STORE.db.execute(
    "UPDATE candidate_subjects SET assertion_time=assertion_time+9999 "
    "WHERE project_id=? AND subject=? AND assertion_id=?",
    (PID, row["subject"], row["assertion_id"]))
api.STORE.db.commit()
r = reconcile()
check("a wrong assertion_time on an index row IS reported",
      r["drift_repaired"] is True, r)
check("named as the candidate index", "candidate_index" in r["detail"], r["detail"])
check("and the row is corrected",
      dict(api.STORE.db.execute(
          "SELECT * FROM candidate_subjects WHERE project_id=? AND subject=? "
          "AND assertion_id=?", (PID, row["subject"], row["assertion_id"])
      ).fetchone())["assertion_time"] == row["assertion_time"])
check("leaving the system clean", reconcile()["drift_repaired"] is False)

print("== drift stays observable to an operator ==")
check("the last repair is recorded", PID in api.PROJECTION_DRIFT,
      sorted(api.PROJECTION_DRIFT))
st, h = call("GET", "/v1/memory/health?project=%s" % PID, None, KEY)
check("and health still surfaces it", st == 200 and "projection_drift" in json.dumps(h),
      json.dumps(h)[:200])

print("\n%d passed, %d failed" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)
