"""P5 audit hardening. Run: python3 tests_p5_audit.py

Targets the audit bug-classes that the original P5 suite under-covered:
temporal (as_of) graph filtering, contradiction-annotated edges, projection
rebuild determinism + dangling cleanup, cycle safety, tenant isolation,
concurrent mutation, and relationship-direction integrity.
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
DB = "/tmp/omem_p5_audit.db"
if os.path.exists(DB):
    os.remove(DB)
os.environ["OMEM_DB"] = DB
os.environ.pop("OMEM_LLM_API_KEY", None)

import api  # noqa: E402
import graph as _graph  # noqa: E402
from http.server import ThreadingHTTPServer  # noqa: E402

PASS = FAIL = 0


def check(n, c, d=""):
    global PASS, FAIL
    if c:
        PASS += 1; print(f"  ok  {n}")
    else:
        FAIL += 1; print(f"  FAIL {n}  {d}")


srv = ThreadingHTTPServer(("127.0.0.1", 0), api.Handler)
PORT = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()
time.sleep(0.2)
BASE = f"http://127.0.0.1:{PORT}"


def call(m, path, body=None, key=None):
    r = urllib.request.Request(f"{BASE}{path}", method=m,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Content-Type": "application/json",
                 **({"Authorization": f"Bearer {key}"} if key else {})})
    try:
        with urllib.request.urlopen(r, timeout=15) as resp:
            return resp.status, json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


acct = call("POST", "/v1/signup", {"email": "audit@kronos.com"})[1]
KEY, PID = acct["api_key"]["secret"], acct["project"]["id"]
P = api.PROJECTS[PID]


def ent(eid, typ="entity", label=None):
    if eid not in P.labels:
        api.record(P, "entity", {"id": eid, "type": typ, "label": label or eid.split(":")[-1]})


def rel(aid, src, dst, prop, relation, T=None):
    ent(src); ent(dst)
    api.record(P, "assert", {"id": aid, "agent": "agent:sys", "subjects": [src, dst],
                             "proposition": prop, "assertion_time": T or P.tick()})
    _graph.record_edge(api.STORE.db, PID, aid, src, relation, dst)


if "agent:sys" not in P.labels:
    api.record(P, "agent", {"id": "agent:sys", "kind": "system"})

print("== temporal: as_of graph filtering ==")
T_before = P.now()
Trel = P.tick()
rel("a_rel1", "person:sarah", "company:acme", "rel_works_at_acme", "works_at", T=Trel)
st, g_now = call("GET", f"/v1/memory/graph?project={PID}&entity=company:acme", None, KEY)
check("edge visible in the present", any(e["dst"] == "company:acme" or e["src"] == "company:acme"
                                        for e in g_now["edges"]))
st, g_past = call("GET", f"/v1/memory/graph?project={PID}&entity=company:acme&as_of={T_before}", None, KEY)
check("edge does NOT leak into an as_of query before it existed",
      g_past["edges"] == [], str(g_past["edges"]))
st, g_at = call("GET", f"/v1/memory/graph?project={PID}&entity=company:acme&as_of={Trel}", None, KEY)
check("edge present at exactly its assertion time", len(g_at["edges"]) >= 1)

print("== supersession invalidates the projection edge ==")
Tsup = P.tick()
ent("company:beta")
api.record(P, "supersede", {"id": "a_rel1b", "agent": "agent:sys",
                            "subjects": ["person:sarah", "company:beta"],
                            "proposition": "rel_works_at_beta", "assertion_time": Tsup,
                            "olds": ["a_rel1"], "did": "d_sw"})
_graph.record_edge(api.STORE.db, PID, "a_rel1b", "person:sarah", "works_at", "company:beta")
st, g2 = call("GET", f"/v1/memory/graph?project={PID}&entity=person:sarah", None, KEY)
dsts = {e["dst"] for e in g2["edges"]}
check("superseded edge gone, new edge present", dsts == {"company:beta"}, str(dsts))
st, g_hist = call("GET", f"/v1/memory/graph?project={PID}&entity=person:sarah&as_of={Trel}", None, KEY)
check("historical as_of still shows the OLD relationship",
      any(e["dst"] == "company:acme" for e in g_hist["edges"]), str(g_hist["edges"]))

print("== contradiction annotation on edges ==")
# a genuine engine contradiction requires the SAME subject pair with
# incompatible relation propositions (two different relationships are not
# contradictory just because their labels were declared incompatible)
ent("person:pat"); ent("company:zed")
api.record(P, "assert", {"id": "a_c1", "agent": "agent:sys",
                         "subjects": ["person:pat", "company:zed"],
                         "proposition": "rel_works_at", "assertion_time": P.tick()})
_graph.record_edge(api.STORE.db, PID, "a_c1", "person:pat", "works_at", "company:zed")
api.record(P, "assert", {"id": "a_c2", "agent": "agent:sys",
                         "subjects": ["person:pat", "company:zed"],
                         "proposition": "rel_partner_of", "assertion_time": P.tick()})
_graph.record_edge(api.STORE.db, PID, "a_c2", "person:pat", "partner_of", "company:zed")
call("POST", f"/v1/declare-contradiction?project={PID}",
     {"token_a": "rel_works_at", "token_b": "rel_partner_of"}, KEY)
st, gc = call("GET", f"/v1/memory/graph?project={PID}&entity=company:zed", None, KEY)
zed_edges = [e for e in gc["edges"] if e["dst"] == "company:zed"]
check("both contradicting edges render (both assertions open)", len(zed_edges) == 2, str(zed_edges))
check("contradicted edges are annotated, never shown as uncontested fact",
      all(e.get("contradicted") for e in zed_edges), str(zed_edges))

print("== projection rebuild: determinism, idempotency, dangling cleanup ==")
# inject a dangling edge row (no backing assertion) - rebuild must drop it
api.STORE.db.execute("INSERT OR REPLACE INTO memory_edges VALUES(?,?,?,?,?,?)",
                     (PID, "a_ghost", "person:ghost", "works_at", "company:void", time.time()))
api.STORE.db.commit()
st, rb1 = call("POST", f"/v1/memory/graph/rebuild?project={PID}", {}, KEY)
st, rb2 = call("POST", f"/v1/memory/graph/rebuild?project={PID}", {}, KEY)
check("rebuild drops dangling edges", rb1["dropped_dangling"] >= 1, str(rb1))
check("rebuild is idempotent (second run reconciles nothing)",
      rb2["reconciled"] == 0 and rb2["dropped_dangling"] == 0, str(rb2))
# snapshot the whole projection, rebuild, compare - restart-consistency proof
def snapshot():
    return sorted(tuple(r) for r in api.STORE.db.execute(
        "SELECT assertion_id, src, relation, dst FROM memory_edges WHERE project_id=?", (PID,)))
before = snapshot()
call("POST", f"/v1/memory/graph/rebuild?project={PID}", {}, KEY)
check("projection rebuild reproduces identical edges (restart-safe)",
      snapshot() == before, f"{len(before)} edges")
check("every rebuilt edge is backed by a real engine assertion (no dangling)",
      all(P.engine.store.assertion(aid) is not None for aid, *_ in snapshot())
      and len(snapshot()) >= 1, f"{len(snapshot())} edges")

print("== cycles ==")
rel("a_cyc1", "person:x", "person:y", "rel_reports_to_y", "reports_to")
rel("a_cyc2", "person:y", "person:z", "rel_reports_to_z", "reports_to")
rel("a_cyc3", "person:z", "person:x", "rel_reports_to_x", "reports_to")  # cycle back
st, gcyc = call("GET", f"/v1/memory/graph?project={PID}&entity=person:x&depth=2", None, KEY)
check("cyclic graph terminates and is bounded",
      len(gcyc["nodes"]) <= _graph.MAX_NODES and gcyc["depth"] == 2)
check("cycle traversal deterministic",
      call("GET", f"/v1/memory/graph?project={PID}&entity=person:x&depth=2", None, KEY)[1] == gcyc)

print("== direction integrity ==")
st, gd = call("GET", f"/v1/memory/graph?project={PID}&entity=company:beta", None, KEY)
wedge = [e for e in gd["edges"] if e["relation"] == "works_at"][0]
check("works_at direction preserved (person -> company, not reversed)",
      wedge["src"] == "person:sarah" and wedge["dst"] == "company:beta", str(wedge))

print("== tenant isolation ==")
acct2 = call("POST", "/v1/signup", {"email": "audit2@x.com"})[1]
K2, PID2 = acct2["api_key"]["secret"], acct2["project"]["id"]
st, cross = call("GET", f"/v1/memory/graph?project={PID}&entity=company:acme", None, K2)
check("cross-tenant graph read rejected", st in (403, 404), str(st))
st, own = call("GET", f"/v1/memory/graph?project={PID2}&entity=company:acme", None, K2)
check("other tenant sees no edges from the first tenant's data",
      own["edges"] == [], str(own))

print("== concurrent writes ==")
def writer(i):
    ent(f"company:c{i}")
    aid = f"a_conc_{i}"
    api.record(P, "assert", {"id": aid, "agent": "agent:sys",
                             "subjects": ["person:sarah", f"company:c{i}"],
                             "proposition": f"rel_partner_of_c{i}", "assertion_time": P.tick()})
    _graph.record_edge(api.STORE.db, PID, aid, "person:sarah", "partner_of", f"company:c{i}")
threads = [threading.Thread(target=writer, args=(i,)) for i in range(8)]
[t.start() for t in threads]; [t.join() for t in threads]
n = api.STORE.db.execute("SELECT COUNT(*) n FROM memory_edges "
                         "WHERE relation='partner_of' AND assertion_id LIKE 'a_conc_%'").fetchone()["n"]
check("concurrent edge writes all land, no corruption", n == 8, str(n))
st, gp = call("POST", f"/v1/memory/graph/rebuild?project={PID}", {}, KEY)
check("projection still consistent after concurrent writes", st == 200)

print("== engine integrity ==")
import hashlib
h = {f: hashlib.sha256(open(os.path.join(HERE, "omem_engine", f), "rb").read()).hexdigest()
     for f in sorted(os.listdir(os.path.join(HERE, "omem_engine"))) if f.endswith(".py")}
baseline = {}
for line in open(os.path.join(HERE, "omem_engine", "ENGINE_HASHES.txt"),
                 encoding="utf-8"):
    if not line.strip() or line.startswith('#'):
        continue
    hsh, path = line.split()
    baseline[os.path.basename(path)] = hsh
check("frozen engine byte-identical", all(baseline.get(f) == v for f, v in h.items()))

srv.shutdown()
print(f"\n{PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
