"""Recall reasons two hops out, and can show both. Run: python3 tests_recall_two_hop.py

The graph has supported two hops since it was written (MAX_DEPTH = 2), and the
traversal endpoint honoured whatever depth was asked for. Recall asked for one:

    hops = _g.neighbors(db, p, ents, depth=1, ...)

So "Sarah works at Acme, Acme supplies Globex" never reached Globex from
Sarah. One hop finds what a person is attached to; two is where a memory graph
starts answering questions a keyword search cannot.

RAISING THE NUMBER WAS THE SMALL PART. neighbors() kept only the edge that
ARRIVED at an entity, which is enough to say something is related and not
enough to say why. A two-hop memory would have been explained as

    reached through the memory graph: company:acme, supplies→ company:globex

naming two things the caller never asked about, with Sarah -- the thing they
did ask about -- absent from her own explanation. For a system whose argument
is that every answer can be checked, an unfollowable reason is worse than none.
neighbors() now returns the whole chain and recall renders all of it.

PRECISION IS THE OTHER HALF. Every entity-tagged memory used to rank the same,
so widening the search would let a fact about a supplier's supplier displace a
fact about the customer in front of you. Ranking now includes distance, and
the explanation reports the NEAREST route so it cannot contradict the order.
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
DB = os.path.join(TMP, "omem_two_hop.db")
if os.path.exists(DB):
    os.remove(DB)
os.environ["OMEM_DB"] = DB

import api  # noqa: E402
import graph as _graph  # noqa: E402
import recall as _recall  # noqa: E402
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


acct = call("POST", "/v1/signup", {"email": "two-hop@kronos.com"})[1]
KEY, PID = acct["api_key"]["secret"], acct["project"]["id"]
mem = omem.Memory(KEY, base_url=BASE, project=PID)
P = api.PROJECTS[PID]
A = "agent:sales"

# sarah --works_at--> acme --supplies--> globex
mem.remember(A, ["person:sarah", "company:acme"], "rel_works_at")
mem.remember(A, ["company:acme", "company:globex"], "rel_supplies")
mem.remember(A, "company:acme", "prefers_annual_billing")     # one hop from sarah
mem.remember(A, "company:globex", "requires_net_60")          # two hops from sarah


def pack(context, limit=10):
    st, pk = call("POST", "/v1/recall?project=%s" % PID,
                  {"agent": A, "context": context, "limit": limit}, KEY)
    return pk.get("memories", [])


def find(mems, prop):
    return next((m for m in mems if m["proposition"] == prop), None)


print("== traversal itself reaches two hops and keeps the whole chain ==")
hops = _graph.neighbors(api.STORE.db, P, ["person:sarah"], depth=2)
check("globex is reachable from sarah", "company:globex" in hops, sorted(hops))
if "company:globex" in hops:
    info = hops["company:globex"]
    check("at two hops", info["hops"] == 2, info["hops"])
    check("and the path holds BOTH edges, not just the arriving one",
          len(info.get("path") or []) == 2, info.get("path"))
    # Direction of TRAVEL, not direction of the edge. Traversal is undirected,
    # so a chain can walk against an edge, and rendering edges in stored order
    # produced a path starting at a node nobody asked about.
    check("in walk order, starting from what was asked about",
          (info["path"][0]["from"], info["path"][-1]["to"])
          == ("person:sarah", "company:globex"), info["path"])
    check("each step continues from where the last one ended",
          all(a["to"] == b["from"] for a, b in zip(info["path"], info["path"][1:])),
          info["path"])
    # via is the raw arriving edge; path[-1] is that edge plus the travel
    # annotation. Same edge, so compare the edge and not the dict.
    check("via stays the arriving edge, for subgraph and older callers",
          all(info["via"][k] == info["path"][-1][k]
              for k in ("assertion", "src", "relation", "dst")),
          (info["via"], info["path"][-1]))

check("one hop still reaches only the neighbour",
      "company:globex" not in _graph.neighbors(api.STORE.db, P,
                                               ["person:sarah"], depth=1))

print("== recall now travels that far ==")
check("recall's depth is the graph's, not 1", _recall.RECALL_DEPTH == 2,
      _recall.RECALL_DEPTH)
mems = pack("what should I know before speaking to person:sarah")
far = find(mems, "requires_net_60")
check("a two-hop fact is recalled at all", far is not None,
      [m["proposition"] for m in mems])

print("== and can say how it got there ==")
if far:
    check("the explanation names the graph",
          "reached through the memory graph" in (far.get("why_included") or ""),
          far.get("why_included"))
    path = far.get("path") or ""
    check("the path names BOTH relations", "works_at" in path and "supplies" in path,
          path)
    check("and starts at the entity that was asked about",
          path.startswith("person:sarah"), path)
    check("so the whole chain is followable, not a dangling last edge",
          "then" in path, path)

print("== nearer memories still come first ==")
# The risk of widening the search: a fact about a supplier's supplier
# outranking a fact about the customer in front of you.
mems = pack("what should I know before speaking to person:sarah")
props = [m["proposition"] for m in mems]
if "prefers_annual_billing" in props and "requires_net_60" in props:
    check("the one-hop fact outranks the two-hop fact",
          props.index("prefers_annual_billing") < props.index("requires_net_60"),
          props)
else:
    check("both facts are present to compare", False, props)

near = find(mems, "prefers_annual_billing")
if near:
    check("and the nearer one is explained by its own short path",
          "then" not in (near.get("path") or ""), near.get("path"))

print("== a direct fact is never displaced by a travelled one ==")
mems = pack("company:globex terms")
direct = find(mems, "requires_net_60")
check("asking about globex directly still concerns it directly",
      direct is not None and "directly concerns" in (direct.get("why_included") or ""),
      direct and direct.get("why_included"))
check("and reports no path, because none was travelled",
      direct is not None and not direct.get("path"), direct and direct.get("path"))

print("== bounds are unchanged ==")
check("MAX_DEPTH still caps traversal", _graph.MAX_DEPTH == 2, _graph.MAX_DEPTH)
check("asking for more than the cap is clamped, not honoured",
      "company:globex" in _graph.neighbors(api.STORE.db, P, ["person:sarah"],
                                           depth=99))
d = _graph.rebuild_projection(api.STORE.db, P)
check("and the graph still round-trips a rebuild", d["reconciled"] == 0, d)

print("\n%d passed, %d failed" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)
