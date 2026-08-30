"""The bank is the instance operator's, and nobody else's.
Run: python3 tests_bank_gate.py

A public collector accepts signups, and every signup mints its own org with
its own owner. If an owner-role check were the only gate, any stranger who
registered would read the pooled contributions. So the bank and the dataset
export answer only to the OPERATOR: the emails in OMEM_ADMIN_EMAILS. This
suite pins that, plus the public dataset staying 404 while unpublished.
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
TMP = os.environ.get("TEMP") or "/tmp"
DB = os.path.join(TMP, "omem_bank_gate.db")
if os.path.exists(DB):
    os.remove(DB)
os.environ["OMEM_DB"] = DB
os.environ["OMEM_BANK_COLLECTOR"] = "1"
os.environ["OMEM_ADMIN_EMAILS"] = "bankop@kronos.com"
os.environ.setdefault("OMEM_TENANT_RL_BURST", "10000")
os.environ.setdefault("OMEM_TENANT_RL_RPS", "10000")

import api  # noqa: E402
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


def signup(email):
    return json.loads(urllib.request.urlopen(urllib.request.Request(
        BASE + "/v1/signup", method="POST",
        data=json.dumps({"email": email}).encode(),
        headers={"Content-Type": "application/json"})).read())["token"]


def get(path, token):
    req = urllib.request.Request(BASE + path,
        headers={"Authorization": "Bearer " + token})
    try:
        return 200, json.loads(urllib.request.urlopen(req, timeout=15).read())
    except urllib.error.HTTPError as e:
        return e.code, None


OP = signup("bankop@kronos.com")
STRANGER = signup("stranger@kronos.com")

code, body = get("/v1/org/bank", OP)
check("the operator reads the bank", code == 200 and body is not None, code)
code, _ = get("/v1/org/bank", STRANGER)
check("a registered stranger does not (403)", code == 403, code)
code, body = get("/v1/commons-dataset", OP)
check("the operator reads the dataset export", code == 200, code)
code, _ = get("/v1/commons-dataset", STRANGER)
check("a stranger does not (403)", code == 403, code)
try:
    urllib.request.urlopen(BASE + "/v1/commons/dataset", timeout=15)
    check("public dataset stays 404 while unpublished", False, "opened")
except urllib.error.HTTPError as e:
    check("public dataset stays 404 while unpublished", e.code == 404, e.code)
check("the contribution address is the project's own domain",
      "omem-cloud.com" in __import__("commons").DEFAULT_COMMONS_URL)

print("\n%d passed, %d failed" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)
