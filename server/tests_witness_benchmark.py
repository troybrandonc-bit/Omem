"""OMEM's Witness results are asserted, not published. Run: python3 tests_witness_benchmark.py

The Witness benchmark (benchmarks/witness/) measures whether a memory system
behaves like testimony: repeats only what it was told, retracts what was
withdrawn, keeps disagreement visible, keeps two people with one name apart,
and lets conclusions die with their premises.

This suite runs the whole benchmark against a live OMEM server through the
same adapter any outside reader would use, and asserts a perfect card: every
probe PASS, nothing UNSUPPORTED, zero violations on every axis. The point of
running it here is the same as the demos: the repository's claims about the
benchmark cannot quietly drift from what the code does, because this file
would go red.
"""
import os
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "sdk", "python"))
sys.path.insert(0, os.path.join(HERE, "..", "benchmarks", "witness"))
TMP = os.environ.get("TEMP") or "/tmp"
DB = os.path.join(TMP, "omem_witness.db")
if os.path.exists(DB):
    os.remove(DB)
os.environ["OMEM_DB"] = DB
os.environ.setdefault("OMEM_TENANT_RL_BURST", "10000")
os.environ.setdefault("OMEM_TENANT_RL_RPS", "10000")

import api  # noqa: E402
import omem  # noqa: E402
import harness  # noqa: E402
from adapters.omem_adapter import OmemAdapter  # noqa: E402
from http.server import ThreadingHTTPServer  # noqa: E402
import json  # noqa: E402
import urllib.request  # noqa: E402

PASS = FAIL = 0


def check(n, c, d=""):
    global PASS, FAIL
    if c:
        PASS += 1
        print("  ok  " + n)
    else:
        FAIL += 1
        print("  FAIL " + n + "  " + str(d)[:220])


OWNER = "witness@kronos.com"

srv = ThreadingHTTPServer(("127.0.0.1", 0), api.Handler)
PORT = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()
time.sleep(0.2)
BASE = "http://127.0.0.1:%d" % PORT

req = urllib.request.Request(BASE + "/v1/signup", method="POST",
                             data=json.dumps({"email": OWNER}).encode(),
                             headers={"Content-Type": "application/json"})
acct = json.loads(urllib.request.urlopen(req, timeout=20).read())
KEY, PID = acct["api_key"]["secret"], acct["project"]["id"]
mem = omem.Memory(KEY, base_url=BASE, project=PID)

print("== the witness takes the stand ==")
report = harness.run_all(OmemAdapter(mem))

for sc in report:
    print("== %s ==" % sc["title"])
    for r in sc["results"]:
        detail = "; ".join(r.get("problems", [])) or r.get("missing", "")
        check("%s/%s [%s] holds" % (sc["scenario"], r["probe"], r["axis"]),
              r["outcome"] == "PASS", "%s %s" % (r["outcome"], detail))

print("== the card as a whole ==")
tally = harness.summarize(report)
check("every axis the benchmark defines was actually exercised",
      set(tally) == set(harness.AXES), sorted(set(harness.AXES) - set(tally)))
check("zero violations across all axes",
      sum(t["violation"] for t in tally.values()) == 0, tally)
check("nothing was unsupported: OMEM can express every question",
      sum(t["unsupported"] for t in tally.values()) == 0, tally)

print("\n%d passed, %d failed" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)
