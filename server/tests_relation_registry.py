"""The relation vocabulary lives in one place. Run: python3 tests_relation_registry.py

It used to live in five: graph.RELATIONS, the LLM prompt (which offered five
of the eight relations, so the model obediently never proposed supplies, owns
or involves), the deterministic regexes, the consolidation hints (six of
eight, so an `owns_...` fact ranked as a plain fact while `works_at_...`
ranked relational), and the MCP tool prose. None of those drifts was visible
from any single file.

Now graph.RELATION_REGISTRY is the source: the prompt enum and the hints are
DERIVED from it, and the two consumers that cannot derive -- the extraction
regexes (hand-written per relation) and the MCP prose (which describes
whatever server it happens to talk to) -- are pinned here, so the next drift
is a red CI run instead of a quiet lie.
"""
import json
import os
import re
import sys
import threading
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "sdk", "python"))
TMP = os.environ.get("TEMP") or "/tmp"
DB = os.path.join(TMP, "omem_relation_registry.db")
if os.path.exists(DB):
    os.remove(DB)
os.environ["OMEM_DB"] = DB

import graph  # noqa: E402
import semantic  # noqa: E402
import consolidation  # noqa: E402
import extraction  # noqa: E402

PASS = FAIL = 0


def check(n, c, d=""):
    global PASS, FAIL
    if c:
        PASS += 1
        print("  ok  " + n)
    else:
        FAIL += 1
        print("  FAIL " + n + "  " + str(d)[:220])


RELS = set(graph.RELATIONS)

print("== the registry itself ==")
check("every relation is registered with a non-empty reading",
      all(graph.RELATION_REGISTRY.get(r, {}).get("reads") for r in graph.RELATIONS))
check("RELATIONS is exactly the registry's keys, in its order",
      graph.RELATIONS == tuple(graph.RELATION_REGISTRY))
check("relation_of answers for every registered relation",
      all(graph.relation_of(f"rel_{r}_x") == r for r in graph.RELATIONS))

print("== the LLM prompt derives, and offers everything the graph accepts ==")
check("the placeholder was substituted, not shipped",
      "__RELATION_ENUM__" not in semantic.SEMANTIC_SYSTEM)
m = re.search(r'"relation": null \| \{"name": ([^,]+),', semantic.SEMANTIC_SYSTEM)
offered = set(re.findall(r'"(\w+)"', m.group(1))) if m else set()
check("the prompt's relation enum is exactly the vocabulary -- it offered "
      "five of eight for two releases", offered == RELS,
      sorted(RELS ^ offered))

print("== the consolidation hints derive ==")
check("every relation's vocabulary classifies as relational",
      all(f"{r}_" in consolidation._RELATIONAL_HINTS for r in graph.RELATIONS))
check("including the two the hand-copied list forgot",
      consolidation.classify_proposition("owns_billing_integration") == "relational"
      and consolidation.classify_proposition("supplies_steel_parts") == "relational")
check("the one deliberate extra survives: integration_ predates the registry",
      "integration_" in consolidation._RELATIONAL_HINTS)

print("== the consumers that cannot derive are pinned ==")
check("every deterministic regex extracts a registered relation",
      {rel for _, rel, _ in extraction.RELATION_PATTERNS} <= RELS,
      {rel for _, rel, _ in extraction.RELATION_PATTERNS} - RELS)

from omem.mcp_server import TOOLS  # noqa: E402
remember = next(t for t in TOOLS if t["name"] == "omem_remember")
blob = remember["description"] + json.dumps(remember["inputSchema"])
missing = [r for r in graph.RELATIONS if r not in blob]
check("the MCP tool prose names every relation", not missing, missing)
_COUNT_WORDS = {6: "six", 7: "seven", 8: "eight", 9: "nine", 10: "ten",
                11: "eleven", 12: "twelve"}
word = _COUNT_WORDS.get(len(graph.RELATIONS))
check("and its spelled-out count matches the vocabulary size, so growing the "
      "registry forces the prose to keep up",
      word is not None and word in remember["description"], word)

print("== the vocabulary is queryable, so nobody hardcodes it downstream ==")
import api  # noqa: E402
from http.server import ThreadingHTTPServer  # noqa: E402

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


acct = call("POST", "/v1/signup", {"email": "registry@kronos.com"})[1]
KEY = acct["api_key"]["secret"]
st, rels = call("GET", "/v1/relations", None, KEY)
check("GET /v1/relations answers", st == 200, rels)
check("with exactly the vocabulary, each carrying its reading",
      [x["name"] for x in rels.get("data", [])] == list(graph.RELATIONS)
      and all(x.get("reads") for x in rels.get("data", [])), rels)

print("\n%d passed, %d failed" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)
