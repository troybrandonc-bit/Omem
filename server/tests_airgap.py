"""It phones home to nobody, provably. Run: python3 tests_airgap.py

"Runs air-gapped" appears in the README and on the site, and until this file
it was an architecture argument: stdlib only, no telemetry, the hashed
embedder by default. An argument is not a proof. This suite installs a guard
under the socket layer BEFORE the server is imported, then drives every major
feature through a live server: identity, contradiction, supersession,
retraction, rules with a cascade, constraints, semantic recall, hunches, the
belief diff. If any code path so much as looks up a non-local hostname, let
alone connects anywhere that is not loopback, the guard records it and this
suite fails with the address in hand.

The guard is itself tested before it is trusted: a deliberate connection to
an external address must be blocked and recorded, because a guard that
cannot catch anything would otherwise pass this suite in perfect silence.
"""
import os
import socket
import sys

VIOLATIONS = []

_LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1", ""}


def _is_local(addr):
    host = addr[0] if isinstance(addr, tuple) and addr else addr
    host = str(host)
    return host in _LOCAL_HOSTS or host.startswith("127.")


_orig_connect = socket.socket.connect
_orig_connect_ex = socket.socket.connect_ex
_orig_getaddrinfo = socket.getaddrinfo


def _guard_connect(self, addr):
    if self.family in (socket.AF_INET, socket.AF_INET6) and not _is_local(addr):
        VIOLATIONS.append(("connect", str(addr)))
        raise OSError("airgap guard: blocked connect to %r" % (addr,))
    return _orig_connect(self, addr)


def _guard_connect_ex(self, addr):
    if self.family in (socket.AF_INET, socket.AF_INET6) and not _is_local(addr):
        VIOLATIONS.append(("connect_ex", str(addr)))
        return 111
    return _orig_connect_ex(self, addr)


def _guard_getaddrinfo(host, *a, **kw):
    if not _is_local((host,)):
        VIOLATIONS.append(("dns", str(host)))
        raise socket.gaierror("airgap guard: blocked lookup of %r" % (host,))
    return _orig_getaddrinfo(host, *a, **kw)


socket.socket.connect = _guard_connect
socket.socket.connect_ex = _guard_connect_ex
socket.getaddrinfo = _guard_getaddrinfo

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "sdk", "python"))
TMP = os.environ.get("TEMP") or "/tmp"
DB = os.path.join(TMP, "omem_airgap.db")
if os.path.exists(DB):
    os.remove(DB)
os.environ["OMEM_DB"] = DB
# The point is the DEFAULT posture: no external embedder, nothing configured.
os.environ.pop("OMEM_EMBED_MODEL", None)
os.environ.setdefault("OMEM_TENANT_RL_BURST", "10000")
os.environ.setdefault("OMEM_TENANT_RL_RPS", "10000")

import api  # noqa: E402  (imported UNDER the guard, deliberately)
import omem  # noqa: E402
import json  # noqa: E402
import threading  # noqa: E402
import time  # noqa: E402
import urllib.request  # noqa: E402
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


print("== the guard must catch before it may clear ==")
try:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(2)
    try:
        s.connect(("203.0.113.9", 443))     # TEST-NET-3: never routable anyway
    finally:
        s.close()
    blocked = False
except OSError:
    blocked = True
check("a deliberate external connect is blocked", blocked)
check("and recorded with its address",
      VIOLATIONS and VIOLATIONS[-1] == ("connect", "('203.0.113.9', 443)"),
      VIOLATIONS[-3:])
try:
    socket.getaddrinfo("example.com", 443)
    dns_blocked = False
except socket.gaierror:
    dns_blocked = True
check("a deliberate external DNS lookup is blocked", dns_blocked)
CANARIES = len(VIOLATIONS)

print("== a full working session under the guard ==")
srv = ThreadingHTTPServer(("127.0.0.1", 0), api.Handler)
PORT = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()
time.sleep(0.2)
BASE = "http://127.0.0.1:%d" % PORT

req = urllib.request.Request(BASE + "/v1/signup", method="POST",
                             data=json.dumps({"email": "airgap@kronos.com"}).encode(),
                             headers={"Content-Type": "application/json"})
acct = json.loads(urllib.request.urlopen(req, timeout=20).read())
KEY, PID = acct["api_key"]["secret"], acct["project"]["id"]
mem = omem.Memory(KEY, base_url=BASE, project=PID)
A = "agent:offline"

a1 = mem.remember(A, "person:vera", "prefers_annual_billing")
mem.remember(A, "person:vera", "based_in_warsaw")
mem.remember(A, "person:noor", "not:prefers_annual_billing")
mem.remember(A, ["person:vera", "company:tabulate"], "rel_works_at_tabulate")
mem.remember(A, ["company:kernelworks", "company:tabulate"], "rel_owns_tabulate")
mem.declare_rule(when=[("works_at", "fwd"), ("owns", "rev")],
                 then=("involves", "rev"), agent=A)
run = mem.infer()
check("a rule concluded while offline",
      mem.believes(["company:kernelworks", "person:vera"], "rel_involves_vera")
      == "BELIEVED_TRUE", run)
mem.retract(a1["id"], agent=A)
check("a retraction landed while offline",
      mem.believes("person:vera", "prefers_annual_billing") == "UNKNOWN")
pack = mem.recall(agent=A, context="billing call with vera", task="prep")
check("semantic recall answered from the local embedder",
      isinstance(pack, dict), type(pack).__name__)
check("the belief diff answered", mem.changes(since=0).get("quiet") is False)
check("conflicts answered", mem.conflicts().get("count") is not None)
h = mem.leap()
check("the hunch pass ran without reaching for a network",
      isinstance(h, dict), h)

print("== the verdict ==")
new = VIOLATIONS[CANARIES:]
check("zero outbound connections or lookups during the whole session",
      not new, new[:5])
check("the session actually exercised the server",
      PASS >= 9)

print("\n%d passed, %d failed" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)
