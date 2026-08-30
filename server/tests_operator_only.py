"""On a private commons collector, the dashboard is the operator's alone.
Run: python3 tests_operator_only.py

OMEM_OPERATOR_ONLY closes account creation and sign-in to the emails in
OMEM_ADMIN_EMAILS, so the whole authenticated app is the operator's. What it
must NOT close is the commons itself: the public page and the contribution
endpoint need no account, so a locked-down collector still takes contributions
and still shows /commons. This suite pins both halves.
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
DB = os.path.join(TMP, "omem_operator_only.db")
if os.path.exists(DB):
    os.remove(DB)
os.environ["OMEM_DB"] = DB
os.environ["OMEM_BANK_COLLECTOR"] = "1"
os.environ["OMEM_OPERATOR_ONLY"] = "1"
os.environ["OMEM_ADMIN_EMAILS"] = "op@kronos.com"
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


def post(path, payload, token=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    req = urllib.request.Request(BASE + path, method="POST",
        data=json.dumps(payload).encode(), headers=headers)
    try:
        r = urllib.request.urlopen(req, timeout=15)
        return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, None


def get(path):
    try:
        r = urllib.request.urlopen(BASE + path, timeout=15)
        return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, None


print("== the dashboard is the operator's ==")
code, body = post("/v1/signup", {"email": "op@kronos.com"})
check("the operator can register", code == 201 and body and body.get("token"), code)

# Case should not lock the operator out of their own box.
code, _ = post("/v1/session", {"email": "OP@Kronos.com"})
check("operator sign-in is case-insensitive (not 403)", code != 403, code)

code, _ = post("/v1/signup", {"email": "stranger@kronos.com"})
check("a stranger cannot register (403)", code == 403, code)

# Even a would-be existing account is turned away at sign-in, before any
# password is considered.
code, _ = post("/v1/session", {"email": "stranger@kronos.com", "password": "whatever-goes-here"})
check("a stranger cannot sign in (403)", code == 403, code)

print("== the commons stays open ==")
code, body = get("/v1/commons/public")
check("the public commons page still answers (200)", code == 200 and body.get("collector"), code)

code, body = post("/v1/commons", {"instance": "a" * 16, "patterns": [
    {"antecedent": "prefers_morning_meetings", "consequent": "prefers_email_contact",
     "support": 5, "refute": 1, "subjects": 8}]})
check("a contribution needs no account and is accepted (2xx)", code in (200, 201), code)

print("\n%d passed, %d failed" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)
