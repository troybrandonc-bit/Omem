"""API JSON contract. Run: python3 tests_json_contract.py

The dashboard does JSON.parse on every response, so the backend must NEVER
emit a non-JSON body: not on missing params, bad ids, malformed request
bodies, broken Content-Length headers, or internal errors. This suite fuzzes
every route family with garbage and asserts the response parses.
"""
from __future__ import annotations

import http.client
import json
import os
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
DB = "/tmp/omem_json_contract.db"
if os.path.exists(DB):
    os.remove(DB)
os.environ["OMEM_DB"] = DB

import api  # noqa: E402
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


def raw(method, path, body: bytes | None = None, headers: dict | None = None):
    """Raw HTTP so we can send broken headers/bodies. Returns (status, text)."""
    c = http.client.HTTPConnection("127.0.0.1", PORT, timeout=10)
    h = {"Content-Type": "application/json"}
    h.update(headers or {})
    c.request(method, path, body=body, headers=h)
    r = c.getresponse()
    text = r.read().decode("utf-8", "replace")
    status = r.status
    c.close()
    return status, text


def raw_headers(method, path, body: bytes | None = None, headers: dict | None = None):
    """Like raw(), but also returns the response headers.

    The verb contract below is partly a claim about a header, so the test has
    to be able to read one.
    """
    c = http.client.HTTPConnection("127.0.0.1", PORT, timeout=10)
    h = {"Content-Type": "application/json"}
    h.update(headers or {})
    c.request(method, path, body=body, headers=h)
    r = c.getresponse()
    text = r.read().decode("utf-8", "replace")
    status, hdrs = r.status, dict(r.getheaders())
    c.close()
    return status, hdrs, text


def assert_json(name, method, path, body=None, headers=None):
    st, text = raw(method, path, body, headers)
    try:
        json.loads(text or "{}")
        ok = True
    except Exception:
        ok = False
    check(f"{name} -> HTTP {st} is JSON", ok, repr(text[:100]))


# a real account so authorized paths are exercised too
st, t = raw("POST", "/v1/signup", json.dumps({"email": "fuzz@x.com"}).encode())
acct = json.loads(t)
KEY = acct["api_key"]["secret"]
PID = acct["project"]["id"]
AUTH = {"Authorization": f"Bearer {KEY}"}

print("== unauthenticated / bad-path ==")
assert_json("no auth on protected route", "GET", f"/v1/assertions?project={PID}")
assert_json("unknown route", "GET", "/v1/definitely-not-a-route", headers=AUTH)
assert_json("unknown nested route", "POST", "/v1/memory/nope/x", b"{}", AUTH)

print("== malformed request bodies ==")
assert_json("invalid JSON body", "POST", f"/v1/relationships?project={PID}",
            b"{not json!!", AUTH)
assert_json("truncated JSON body", "POST", f"/v1/identity?project={PID}",
            b'{"company_name": "A', AUTH)
assert_json("body on GET", "GET", f"/v1/contacts?project={PID}", b"garbage", AUTH)
assert_json("empty body on POST route", "POST", f"/v1/memory/scan?project={PID}",
            None, AUTH)

print("== malformed headers ==")
assert_json("non-numeric Content-Length", "POST", f"/v1/identity?project={PID}",
            b"{}", {**AUTH, "Content-Length": "banana"})
assert_json("negative Content-Length", "POST", f"/v1/identity?project={PID}",
            b"", {**AUTH, "Content-Length": "-5"})

print("== bad parameters / ids ==")
assert_json("missing project", "GET", "/v1/memory/quality", headers=AUTH)
assert_json("nonexistent project", "GET", "/v1/memory/quality?project=proj_nope",
            headers=AUTH)
assert_json("diagnostics missing source", "GET", f"/v1/diagnostics/email?project={PID}",
            headers=AUTH)
assert_json("diagnostics bad source", "GET",
            f"/v1/diagnostics/email?project={PID}&source=src_nope", headers=AUTH)
assert_json("scan detail bad id", "GET", f"/v1/memory/scans/scan_nope?project={PID}",
            headers=AUTH)
assert_json("apply bad scan id", "POST", f"/v1/memory/scans/scan_nope/apply?project={PID}",
            b"{}", AUTH)
assert_json("review decide bad id", "POST",
            f"/v1/memory/review-queue/nope/decide?project={PID}",
            json.dumps({"decision": "approve"}).encode(), AUTH)
assert_json("relationship bad key_type", "POST", f"/v1/relationships?project={PID}",
            json.dumps({"key_type": "planet", "key": "mars", "role": "CUSTOMER"}).encode(), AUTH)
assert_json("relationship bad role", "POST", f"/v1/relationships?project={PID}",
            json.dumps({"key_type": "domain", "key": "x.com", "role": "OVERLORD"}).encode(), AUTH)
assert_json("identity bad email", "POST", f"/v1/identity?project={PID}",
            json.dumps({"emails": ["not-an-email"]}).encode(), AUTH)
assert_json("identity wrong types", "POST", f"/v1/identity?project={PID}",
            json.dumps({"emails": 42, "domains": {"a": 1}}).encode(), AUTH)
assert_json("gmail-rescan bad window", "POST", f"/v1/memory/gmail-rescan?project={PID}",
            json.dumps({"window_days": "yes"}).encode(), AUTH)
assert_json("fact-decisions bad limit", "GET",
            f"/v1/fact-decisions?project={PID}&limit=banana", headers=AUTH)
assert_json("assertions bad as_of", "GET",
            f"/v1/assertions?project={PID}&as_of=banana", headers=AUTH)
assert_json("why on missing assertion", "GET",
            f"/v1/assertions/a_missing/why?project={PID}", headers=AUTH)

print("== DELETE means delete ==")
# do_DELETE used to be a bare `self.do_POST()`, which handed every route in
# _route_post a DELETE alias for free: `DELETE /v1/assertions` ran the create
# handler and answered 201 with a new assertion written to the record.
#
# No authorization was bypassed - _guard and the read-only key check run first
# either way - so this is not a privilege bug. What it broke is the contract
# everything in FRONT of the server reasons about. A reverse proxy rule, a WAF
# policy or an audit review that treats DELETE differently from POST was
# reading a verb that did not mean what it says, and a request that created
# data was indistinguishable from one that destroyed it in any log keyed on
# the method.
#
# Only two routes implement DELETE. Everything else must refuse the verb, and
# refusing it is the whole of the fix, so it is asserted here rather than left
# to be rediscovered the next time someone touches the dispatcher.
_st, _hdrs, _body = raw_headers("DELETE", f"/v1/assertions?project={PID}",
                               json.dumps({"agent": "a", "about": "b",
                                           "claim": "c"}).encode(), AUTH)
check("DELETE on a POST-only route is refused", _st == 405, f"HTTP {_st}: {_body[:120]}")
check("and it does not create anything", '"id"' not in _body, _body[:120])
check("405 names the methods that ARE allowed", "DELETE" not in _hdrs.get("Allow", "DELETE"),
      repr(_hdrs.get("Allow")))
# This suite exists because the dashboard calls JSON.parse on every response,
# and an EMPTY body fails that as surely as an HTML error page does. The first
# version of the refusal sent Content-Length: 0, which slipped past a check
# written as `json.loads(text or "{}")`. So assert the body itself, not the
# helper's substitute for one.
check("the 405 body is a real JSON error", json.loads(_body)["error"]["reason_code"]
      == "method_not_allowed", _body[:160])

# The other half of the contract: the two routes that DO implement DELETE must
# still reach their handlers. Nonexistent ids on purpose, so proving the verb
# arrives does not destroy the account this suite is still using.
for _name, _path in (("connectors", f"/v1/connectors/conn_nope?project={PID}"),
                     ("projects", "/v1/projects/proj_nope")):
    _st, _, _b = raw_headers("DELETE", _path, None, AUTH)
    check(f"DELETE still reaches /v1/{_name}", _st != 405, f"HTTP {_st}: {_b[:120]}")

srv.shutdown()
print(f"\n{PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
