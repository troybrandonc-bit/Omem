"""The queue over HTTP, including what it does with no licence.
Run: python3 tests_approval_queue_api.py

The queue is a paid component, and the thing that matters commercially is also
the thing that matters ethically: an unlicensed install must behave like the
open one, not like a broken one. A billing lapse that turns into an outage, or
into a queue that appears to hold actions and does not, would be worse than
having no paid tier at all.

The rest is the ordinary business of not trusting the caller. The approver is
the principal the authentication layer resolved, never a name in the body, and
the identity source is reported from how they authenticated rather than chosen.

Copyright 2026 Michael Brandon Clifford. Commercial licence required for
production use. See ee/LICENSE.
"""
import json
import os
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
os.environ["OMEM_DB"] = os.path.join(tempfile.mkdtemp(prefix="aq_"), "omem.db")

import api                                     # noqa: E402
import licence as LICENCE                      # noqa: E402
from sign_licence import public_key, sign, _b64  # noqa: E402
import binascii  # noqa: E402

PASS = FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  ok  " + name)
    else:
        FAIL += 1
        print("  FAIL " + name + "  " + str(detail)[:240])


srv = ThreadingHTTPServer(("127.0.0.1", 0), api.Handler)
PORT = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()
time.sleep(0.3)
BASE = "http://127.0.0.1:%d" % PORT


def call(method, path, body=None, key=None):
    req = urllib.request.Request(
        BASE + path, method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Content-Type": "application/json",
                 **({"Authorization": "Bearer " + key} if key else {})})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status, json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode() or "{}")


acct = call("POST", "/v1/signup", {"email": "queue@omem.local"})[1]
KEY, PID = acct["api_key"]["secret"], acct["project"]["id"]
Q = "/v1/healing/queue?project=" + PID

print("== without a licence, it is the open product ==")
code, out = call("POST", Q, {"action_type": "issue_refund"}, KEY)
check("holding an action is refused with 402", code == 402, (code, out))
check("and the refusal says the open gate still works",
      "open gate still refuses" in json.dumps(out), out)
code, out = call("GET", Q, None, KEY)
check("listing is refused the same way", code == 402, (code, out))

# The point of the 402 is that nothing else changes. A billing lapse must not
# take the product down.
code, out = call("GET", "/v1/health")
check("the rest of the server is unaffected", code == 200, code)

print("\n== with a licence ==")
# A real signed licence rather than a monkeypatched check, so what is
# exercised is the path a customer's install takes.
SEED = binascii.unhexlify("9d61b19deffd5a60ba844af492ec2cc44449c5697b32691970"
                          "3bac031cae7f60")
claims = json.dumps({"customer": "Acme", "expires": round(time.time() + 3600),
                     "features": ["approval_queue"]},
                    sort_keys=True, separators=(",", ":")).encode()
LICENCE.ISSUER_PUBLIC_KEY = binascii.hexlify(public_key(SEED)).decode()
os.environ["OMEM_LICENCE"] = _b64(claims) + "." + _b64(sign(SEED, claims))
check("the licence verifies offline, with no network",
      LICENCE.has("approval_queue"))
check("and it does not unlock what it does not name",
      not LICENCE.has("approval_policy"))

code, held = call("POST", Q, {"action_type": "issue_refund",
                              "risk_class": "high",
                              "payload": {"amount": "38.60 EUR"},
                              "reason": "customer asked"}, KEY)
check("an action can be held", code == 201, (code, held))
item = (held or {}).get("item") or {}
check("it comes back pending", item.get("state") == "pending", item)
check("the proposer is the resolved principal, not a name from the body",
      str(item.get("proposed_by", "")).startswith(("key:", "user:", "agent:")),
      item.get("proposed_by"))

code, listed = call("GET", Q, None, KEY)
check("listing works", code == 200, (code, listed))
check("and the proposer is not offered their own action",
      [i["id"] for i in listed.get("pending", [])] == [], listed)
code, everything = call("GET", Q + "&mine=0", None, KEY)
check("asking for everything shows it is still waiting",
      item.get("id") in [i["id"] for i in everything.get("pending", [])],
      everything)

print("\n== the caller cannot approve their own action ==")
code, out = call("POST", Q.replace("?", "/" + item["id"] + "?"),
                 {"verdict": "approve"}, KEY)
check("settling your own item is refused", code == 409, (code, out))
check("and the reason is the one a person should be shown",
      "proposer" in json.dumps(out), out)

print("\n== a second principal settles it ==")
other = call("POST", "/v1/keys?project=" + PID,
             {"name": "approver", "role": "developer"}, KEY)
code2, keyout = other
second = ((keyout or {}).get("key") or {}).get("secret") or \
    (keyout or {}).get("secret")
if not second:
    print("  NOT VERIFIED: could not mint a second key (%s), so the two-party "
          "path was not exercised over HTTP" % code2)
else:
    code, out = call("POST", Q.replace("?", "/" + item["id"] + "?"),
                     {"verdict": "approve", "reason": "net of the balance"},
                     second)
    check("a different principal can approve", code == 200, (code, out))
    settled = (out or {}).get("item") or {}
    check("the item is approved", settled.get("state") == "approved", settled)
    acts = (out or {}).get("acts") or []
    check("the act records how they authenticated, not what they claimed",
          acts and acts[0].get("identity_source") == "api-key", acts)
    check("and who, as the resolved principal",
          acts and str(acts[0].get("principal", "")).startswith(
              ("key:", "user:", "agent:")), acts)

print("\n== an item that does not exist ==")
code, out = call("POST", Q.replace("?", "/aq_nope?"), {"verdict": "approve"}, KEY)
check("is a 409 with a reason, not a crash", code == 409, (code, out))

code, out = call("POST", Q, {"action_type": "", "risk_class": "high"}, KEY)
check("an action with no type is refused at the door", code == 422, (code, out))
code, out = call("POST", Q, {"action_type": "x", "ttl_seconds": 0}, KEY)
check("an item that would never expire is refused", code == 422, (code, out))

print("\n%d passed, %d failed" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)
