"""The suites must fail for reasons that are about the code.
Run: python3 tests_harness.py

Four suites each demanded a particular TCP port be free: 8931, 8814, 8823 and
8817. Anything else already listening there answered the request instead, and
what the suite reported was whatever that other process happened to say. In the
case that prompted this, a static file server on 8931 returned an HTML page,
tests.py tried to decode it as JSON, and the run ended in a JSONDecodeError
pointing at column 1 of line 1 of a document nobody was looking at. Nothing in
that output named the port, the collision, or the other process.

That is worse than a plain failure. A red build that blames the wrong thing
costs more than a red build, because somebody goes looking in the code under
test, and the code under test is fine.

Binding port 0 removes the problem rather than reporting it better: the
operating system hands back a port nobody holds, so a collision cannot happen.
Most of the suites already did this. This file exists so the four that did not
cannot come back, since the cost is paid by whoever next runs the suite on a
machine that happens to have something on that port, and they will have no idea
why.

Copyright 2026 Michael Brandon Clifford. MIT licensed.
"""
import glob
import io
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PASS = FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  ok  " + name)
    else:
        FAIL += 1
        print("  FAIL " + name + "  " + str(detail)[:400])


# A bind site: HTTPServer(("127.0.0.1", <something>), ...) or a bare
# sock.bind(("127.0.0.1", <something>)). The port is the second element, and
# the only literal allowed there is 0.
BIND = re.compile(
    r"""(?:HTTPServer|\.bind)\(\s*\(\s*["'][^"']*["']\s*,\s*([^)\s,]+)""")

print("no suite requires a particular port to be free")
suites = sorted(glob.glob(os.path.join(HERE, "tests*.py")))
check("there are suites to check", len(suites) > 50, len(suites))

offenders = []
binds = 0
for path in suites:
    if os.path.basename(path) == os.path.basename(__file__):
        continue
    src = io.open(path, encoding="utf-8").read()
    for m in BIND.finditer(src):
        binds += 1
        port = m.group(1).strip()
        # 0 is the fix. A name is fine: it is either derived from a bind or it
        # is somebody else's server, and neither is a literal this can judge.
        if port.isdigit() and port != "0":
            line = src[:m.start()].count("\n") + 1
            offenders.append("%s:%d binds port %s"
                             % (os.path.basename(path), line, port))

check("every bind in every suite asks for any free port, not a chosen one",
      not offenders, offenders)
check("and there were binds to find, so this checked something",
      binds >= 4, binds)

print("\nand the four that used to are still the four that matter")
# Named rather than counted: if one of these grows a fixed port again, the
# check above catches it, and this says which suite is being talked about.
for name in ("tests.py", "tests_auth_password.py", "tests_dashboard.py",
             "tests_hardening_p11.py"):
    src = io.open(os.path.join(HERE, name), encoding="utf-8").read()
    ports = [m.group(1).strip() for m in BIND.finditer(src)]
    check("%s binds only what it is given" % name,
          ports and all(p == "0" or not p.isdigit() for p in ports), ports)

print("\na non-JSON answer says what answered")
# Port 0 makes the collision impossible, and something else can still answer:
# a proxy, a captive portal, a stale process on a port the OS reissued. The
# decode failure has to name the request rather than the character offset.
src = io.open(os.path.join(HERE, "tests.py"), encoding="utf-8").read()
check("tests.py does not decode a response without a way to explain it",
      "json.JSONDecodeError" in src and "is not " in src, "no guarded decode")
check("and the explanation carries the request and the address",
      "{method} {path}" in src and "{BASE}" in src)

print("\n%d passed, %d failed" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)
