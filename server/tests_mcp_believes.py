"""omem_believes over MCP behaves: the act-or-ask primitive round-trips.
Run: python3 tests_mcp_believes.py

The tool exists so an MCP agent checks a claim's state BEFORE acting on it.
This pins the whole loop through the real JSON-RPC handler: remember via
tools/call, believes answers BELIEVED_TRUE, an opposing claim lands, believes
flips to CONTRADICTED, and unknown claims answer UNKNOWN rather than erroring.
"""
import json
import os
import sys
import threading
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "sdk", "python"))
TMP = os.environ.get("TEMP") or "/tmp"
DB = os.path.join(TMP, "omem_mcp_believes.db")
if os.path.exists(DB):
    os.remove(DB)
os.environ["OMEM_DB"] = DB
os.environ.setdefault("OMEM_TENANT_RL_BURST", "10000")
os.environ.setdefault("OMEM_TENANT_RL_RPS", "10000")

import api  # noqa: E402
from http.server import ThreadingHTTPServer  # noqa: E402
from omem import Memory  # noqa: E402
from omem.mcp_server import McpServer  # noqa: E402

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

r = urllib.request.urlopen(urllib.request.Request(
    BASE + "/v1/signup", method="POST",
    data=json.dumps({"email": "mcpb@kronos.com"}).encode(),
    headers={"Content-Type": "application/json"}), timeout=15)
signup = json.load(r)
mem = Memory(api_key=signup["api_key"]["secret"], base_url=BASE,
             project=signup["project"]["id"])
mcp = McpServer(mem, agent_id="mcp-agent")


def call(name, args, mid=1):
    resp = mcp.handle({"jsonrpc": "2.0", "id": mid, "method": "tools/call",
                       "params": {"name": name, "arguments": args}})
    content = resp["result"]["content"][0]["text"]
    return json.loads(content)


print("== believes round-trips through the JSON-RPC handler ==")
out = call("omem_remember",
           {"about": "customer:alice", "claim": "prefers_annual_billing",
            "because": "said on the call"})
check("remember over MCP records", "id" in out or "assertion" in json.dumps(out), out)

out = call("omem_believes", {"about": "customer:alice",
                             "claim": "prefers_annual_billing"})
check("believes = BELIEVED_TRUE", out.get("state") == "BELIEVED_TRUE", out)

mem2 = Memory(api_key=signup["api_key"]["secret"], base_url=BASE,
              project=signup["project"]["id"])
mem2.remember("agent:other", "customer:alice", "not:prefers_annual_billing")
out = call("omem_believes", {"about": "customer:alice",
                             "claim": "prefers_annual_billing"})
check("believes flips to CONTRADICTED", out.get("state") == "CONTRADICTED", out)

out = call("omem_believes", {"about": "customer:alice",
                             "claim": "never_asserted_claim"})
check("unknown claim answers UNKNOWN, not an error",
      out.get("state") == "UNKNOWN", out)

print("\n%d passed, %d failed" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)
