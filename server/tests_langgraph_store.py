"""OMEM as a LangGraph BaseStore. Run: python3 tests_langgraph_store.py

Drives the adapter against a REAL server through the real langgraph BaseStore
interface, so this proves the contract LangGraph actually calls, not a
hand-rolled approximation of it. SKIPS honestly if langgraph is not installed,
because it is an optional dependency and a missing one is not a failure.

The interesting assertions are the ones about history. A store that overwrites
is easy; the reason to put OMEM behind this interface at all is that a `put`
over an existing key supersedes and a `delete` retracts, so what the agent used
to believe is still answerable afterwards.
"""
import json
import os
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "sdk", "python"))

DB = os.path.join(os.environ.get("TEMP", "/tmp"), "omem_langgraph_store.db")
if os.path.exists(DB):
    os.remove(DB)
os.environ["OMEM_DB"] = DB

try:
    import langgraph  # noqa: F401
except ImportError:
    print("SKIP: langgraph is not installed (optional). "
          "pip install langgraph to run this suite.")
    sys.exit(0)

import api  # noqa: E402
from http.server import ThreadingHTTPServer  # noqa: E402
from omem import Memory  # noqa: E402
from omem.integrations.langgraph_store import OmemStore  # noqa: E402

PASS = FAIL = 0


def check(n, c, d=""):
    global PASS, FAIL
    if c:
        PASS += 1
        print("  ok  " + n)
    else:
        FAIL += 1
        print("  FAIL " + n + "  " + str(d))


srv = ThreadingHTTPServer(("127.0.0.1", 0), api.Handler)
PORT = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()
time.sleep(0.2)
BASE = "http://127.0.0.1:%d" % PORT

import urllib.request  # noqa: E402

req = urllib.request.Request(
    BASE + "/v1/signup", data=json.dumps({"email": "lg@x.com"}).encode(),
    headers={"Content-Type": "application/json"}, method="POST")
acct = json.loads(urllib.request.urlopen(req).read().decode())
KEY, PID = acct["api_key"]["secret"], acct["project"]["id"]

mem = Memory(api_key=KEY, base_url=BASE, project=PID)
store = OmemStore(mem)

NS = ("memories", "alice")

print("== put / get round trip ==")
store.put(NS, "pref", {"text": "prefers annual billing", "n": 1})
got = store.get(NS, "pref")
check("get returns an Item", got is not None)
check("value round-trips exactly", got.value == {"text": "prefers annual billing", "n": 1},
      str(got.value if got else None))
check("namespace preserved", got.namespace == NS, str(got.namespace if got else None))
check("key preserved", got.key == "pref", str(got.key if got else None))
check("timestamps are real datetimes",
      hasattr(got.created_at, "year") and hasattr(got.updated_at, "year"))

print("== a missing key is None, not an error ==")
check("absent key -> None", store.get(NS, "nope") is None)
check("absent namespace -> None", store.get(("memories", "nobody"), "pref") is None)

print("== put over an existing key supersedes, it does not overwrite ==")
first = store.get(NS, "pref")
store.put(NS, "pref", {"text": "prefers monthly billing", "n": 2})
second = store.get(NS, "pref")
check("the new value is what reads back", second.value["text"] == "prefers monthly billing",
      str(second.value))
check("created_at is carried forward from the first write",
      second.created_at == first.created_at,
      "%s vs %s" % (first.created_at, second.created_at))
check("exactly one live value for the key", second.value["n"] == 2, str(second.value))

# The point of the whole exercise: the superseded value is still on the record.
rows = mem._req("GET", "/v1/assertions").get("data", [])
subj = "lg:memories/alice/pref"
history = [a for a in rows if subj in a.get("subjects", [])]
check("the old value is still in OMEM's history", len(history) >= 2, str(len(history)))
labels = " ".join(a.get("label") or "" for a in history)
check("and the superseded text is recoverable", "annual" in labels, labels[:160])

print("== delete retracts: the key stops resolving, history survives ==")
store.delete(NS, "pref")
check("get after delete -> None", store.get(NS, "pref") is None)
rows2 = mem._req("GET", "/v1/assertions").get("data", [])
still = [a for a in rows2 if subj in a.get("subjects", [])]
check("the record was not erased", len(still) >= len(history), str(len(still)))

print("== search over a namespace ==")
store.put(("memories", "bob"), "a", {"text": "bob one", "tag": "x"})
store.put(("memories", "bob"), "b", {"text": "bob two", "tag": "y"})
store.put(("memories", "carol"), "a", {"text": "carol one", "tag": "x"})
found = store.search(("memories", "bob"))
check("search returns only that namespace", len(found) == 2, str([f.key for f in found]))
check("search items carry values",
      sorted(f.value["text"] for f in found) == ["bob one", "bob two"],
      str([f.value for f in found]))
filtered = store.search(("memories",), filter={"tag": "x"})
check("filter narrows across namespaces",
      sorted((f.namespace[-1], f.key) for f in filtered) == [("bob", "a"), ("carol", "a")],
      str([(f.namespace, f.key) for f in filtered]))
check("limit is honoured", len(store.search(("memories",), limit=1)) == 1)

print("== a query is refused rather than faked ==")
try:
    store.search(("memories",), query="billing")
    check("search(query=...) raises", False, "it returned instead of raising")
except NotImplementedError as e:
    check("search(query=...) raises NotImplementedError", True)
    check("and the message says why", "vector search" in str(e).lower(), str(e)[:120])

print("== list_namespaces ==")
ns = store.list_namespaces()
check("namespaces are discovered", ("memories", "bob") in ns and ("memories", "carol") in ns,
      str(ns))
shallow = store.list_namespaces(max_depth=1)
check("max_depth truncates", ("memories",) in shallow, str(shallow))

print("== the async surface works ==")
import asyncio  # noqa: E402


async def _async_checks():
    await store.aput(("memories", "dave"), "k", {"text": "async write"})
    it = await store.aget(("memories", "dave"), "k")
    return it


it = asyncio.run(_async_checks())
check("aput then aget round-trips", it is not None and it.value["text"] == "async write",
      str(it.value if it else None))

print("== every write is attributed and explainable ==")
rows3 = mem._req("GET", "/v1/assertions").get("data", [])
mine = [a for a in rows3 if a.get("proposition") == "stored_value"]
check("writes are attributed to the store's agent",
      all(a.get("agent") == "agent:langgraph" for a in mine), str({a.get("agent") for a in mine}))
why = mem.why(mine[0]["id"])
check("why() answers for a stored item", isinstance(why, dict) and "state" in why,
      str(why)[:140])

srv.shutdown()
print("\n%d passed, %d failed" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)
