"""The graph is projected on write, not only at boot.
Run: python3 tests_graph_live_projection.py

OMEM keeps two projections above the engine: the candidate index and the
memory graph. The index was updated on every accepted write. The graph was
not, edges were written on the ingest/observe path and otherwise rebuilt at
startup by rebuild_projection.

So a relation asserted DIRECTLY produced no edge:

    mem.remember(agent, ["person:sarah", "company:acme"], "rel_works_at")

recorded a perfectly good two-subject relational assertion, and traversal from
person:sarah found nothing, until the process was restarted. Every path that
does not go through ingest has this shape: POST /v1/assertions, the Python
SDK's remember(), and the omem_remember MCP tool. The relation was in the
engine and invisible to the graph, which is the worst of the two states,
because nothing errors and recall silently answers as though the fact is not
there.

The fix keeps the graph in lockstep on write like the index. What this suite
pins down:

  the edge exists BEFORE any restart, and traversal reaches through it;

  a rebuild afterwards is a NO-OP. That is the real assertion. Live projection
  and boot rebuild have to agree exactly, or a restart silently rewrites the
  graph and as_of history moves. They now ask one function, relation_of();

  the observe path's formation direction still wins, since record() projects
  the sorted default first and record_edge upserts the real direction after;

  non-relations and single-subject assertions still project nothing.
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
DB = os.path.join(TMP, "omem_graph_live.db")
if os.path.exists(DB):
    os.remove(DB)
os.environ["OMEM_DB"] = DB

import api  # noqa: E402
import graph as _graph  # noqa: E402
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


srv = ThreadingHTTPServer(("127.0.0.1", 0), api.Handler)
PORT = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()
time.sleep(0.2)
BASE = "http://127.0.0.1:%d" % PORT


def call(m, path, body=None, key=None):
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = "Bearer " + key
    r = urllib.request.Request(
        BASE + path, method=m,
        data=json.dumps(body).encode() if body is not None else None,
        headers=headers)
    try:
        with urllib.request.urlopen(r, timeout=15) as resp:
            return resp.status, json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


# A signup address no other suite claims. Under PostgreSQL every suite shares
# one database, so a duplicate address gets 409 "That email already has an
# account" and the suite that runs second dies on KeyError: 'api_key'.
# tests_p5_graph.py owns troy@kronos.com, and this file sorts before it.
acct = call("POST", "/v1/signup", {"email": "graph-live@kronos.com"})[1]
KEY, PID = acct["api_key"]["secret"], acct["project"]["id"]
mem = omem.Memory(KEY, base_url=BASE, project=PID)
P = api.PROJECTS[PID]
AGENT = "agent:sales"


def edges_of(entity):
    """Straight from storage. SCOPED TO THIS PROJECT: a suite that reaches past
    the API into shared storage and forgets project_id reads (or rewrites)
    another suite's rows, and passes for the wrong reason."""
    return [dict(r) for r in api.STORE.db.execute(
        "SELECT * FROM memory_edges WHERE project_id=? AND (src=? OR dst=?)",
        (PID, entity, entity))]


print("== a relation recorded directly appears in the graph immediately ==")
rel = mem.remember(AGENT, ["person:sarah", "company:acme"], "rel_works_at",
                   label="from the intro call")
check("the assertion was accepted", bool(rel.get("id")), str(rel)[:160])
check("with both subjects on it",
      sorted(rel.get("subjects", [])) == ["company:acme", "person:sarah"],
      str(rel.get("subjects")))

rows = edges_of("person:sarah")
check("an edge exists WITHOUT restarting", len(rows) == 1, rows)
if rows:
    e = rows[0]
    check("it names the relation, canonicalised off the rel_ prefix",
          e["relation"] == "works_at", e["relation"])
    check("it connects the two subjects",
          {e["src"], e["dst"]} == {"person:sarah", "company:acme"},
          (e["src"], e["dst"]))
    check("and is backed by the assertion that created it",
          e["assertion_id"] == rel["id"], e["assertion_id"])

print("== and traversal reaches through it ==")
st, sub = call("GET", "/v1/memory/graph?project=%s&entity=person:sarah"
                      "&viewer=%s&depth=1" % (PID, AGENT), key=KEY)
check("the traversal endpoint answers", st == 200, sub)
blob = json.dumps(sub)
check("company:acme is reachable from person:sarah", "company:acme" in blob,
      blob[:220])

print("== a rebuild afterwards changes nothing ==")
# The point of the whole change. If the live write and the boot rebuild
# disagree by even the direction of one edge, restarting an OMEM silently
# rewrites history that as_of queries read.
before = sorted((r["assertion_id"], r["src"], r["relation"], r["dst"])
                for r in edges_of("person:sarah"))
diff = _graph.rebuild_projection(api.STORE.db, P)
check("rebuild reconciles nothing", diff["reconciled"] == 0, diff)
check("and drops nothing as dangling", diff["dropped_dangling"] == 0, diff)
after = sorted((r["assertion_id"], r["src"], r["relation"], r["dst"])
               for r in edges_of("person:sarah"))
check("the edges are byte-identical across a rebuild", before == after,
      "%s != %s" % (before, after))

print("== the graph still refuses what is not a relation ==")
mem.remember(AGENT, ["person:sarah", "company:acme"], "met_on_tuesday")
check("a two-subject NON-relation projects no edge",
      len(edges_of("person:sarah")) == 1, edges_of("person:sarah"))

mem.remember(AGENT, "person:lone", "rel_works_at")
check("a relation proposition with ONE subject projects no edge",
      edges_of("person:lone") == [], edges_of("person:lone"))

print("== an uncanonicalised spelling is handled the same way both times ==")
# relation_of() is the single decision point now; before, the live path had no
# opinion at all and only the rebuild decided. This is the case where a second
# copy of that logic would have drifted.
mem.remember(AGENT, ["person:dana", "product:hubspot"], "uses")
rows = edges_of("person:dana")
check("'uses' without the rel_ prefix still projects live",
      len(rows) == 1 and rows[0]["relation"] == "uses", rows)
d2 = _graph.rebuild_projection(api.STORE.db, P)
check("and the rebuild agrees with it", d2["reconciled"] == 0, d2)

print("== superseding a relation projects the new edge too ==")
# Straight to the API rather than through the SDK, because supersession takes
# `olds`. The SDK's remember() auto-creates subjects and this does not, so the
# entity is registered first or the engine correctly refuses it as dangling.
mem.ensure_entity("company:globex")
st3, r3 = call("POST", "/v1/assertions?project=%s" % PID,
               {"agent": AGENT, "subjects": ["person:sarah", "company:globex"],
                "proposition": "rel_works_at", "assertion_time": "now",
                "olds": [rel["id"]]}, KEY)
rows = edges_of("person:sarah")
check("the superseding relation got its own edge",
      any(r["dst"] == "company:globex" or r["src"] == "company:globex"
          for r in rows), (st3, r3, rows))
check("the superseded edge is still stored (as_of history is preserved)",
      any(r["assertion_id"] == rel["id"] for r in rows), rows)
d3 = _graph.rebuild_projection(api.STORE.db, P)
check("and a rebuild still reconciles nothing", d3["reconciled"] == 0, d3)

print("== formation direction from the observe path still wins ==")
# record() projects sorted order, then the observe path upserts the direction
# it knows. Ordering matters and is easy to break; this pins it.
aid = "a_direction_probe"
api.STORE.db.execute("DELETE FROM memory_edges WHERE project_id=? AND assertion_id=?",
                     (PID, aid))
_graph.project_assertion(api.STORE.db, PID, aid,
                         ["zeta:one", "alpha:two"], "rel_works_at")
sorted_first = [dict(r) for r in api.STORE.db.execute(
    "SELECT * FROM memory_edges WHERE project_id=? AND assertion_id=?", (PID, aid))]
check("the write-time default is deterministic sorted order",
      bool(sorted_first) and sorted_first[0]["src"] == "alpha:two", sorted_first)
_graph.record_edge(api.STORE.db, PID, aid, "zeta:one", "works_at", "alpha:two")
now = [dict(r) for r in api.STORE.db.execute(
    "SELECT * FROM memory_edges WHERE project_id=? AND assertion_id=?", (PID, aid))]
check("an explicit record_edge afterwards overrides it",
      len(now) == 1 and now[0]["src"] == "zeta:one", now)
_graph.project_assertion(api.STORE.db, PID, aid,
                         ["zeta:one", "alpha:two"], "rel_works_at")
again = [dict(r) for r in api.STORE.db.execute(
    "SELECT * FROM memory_edges WHERE project_id=? AND assertion_id=?", (PID, aid))]
check("and re-projecting does not flip it back",
      again[0]["src"] == "zeta:one", again)
api.STORE.db.execute("DELETE FROM memory_edges WHERE project_id=? AND assertion_id=?",
                     (PID, aid))
api.STORE.db.commit()

print("\n%d passed, %d failed" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)
