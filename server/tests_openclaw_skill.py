"""The OpenClaw skill's client behaves, end to end, against a live server.
Run: python3 tests_openclaw_skill.py

sdk/openclaw-omem ships one stdlib-only script (scripts/omem.py) as the whole
client. This suite runs that actual script as a subprocess, the way OpenClaw
would, against an in-process server: remember with auto-create, the believes
act-or-ask primitive including the CONTRADICTED flip, recall, why with
provenance, conflicts, observe, and learn. If the script and the API drift
apart, this goes red instead of a marketplace listing quietly breaking.
"""
import json
import os
import subprocess
import sys
import threading
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SCRIPT = os.path.join(ROOT, "sdk", "openclaw-omem", "scripts", "omem.py")
sys.path.insert(0, HERE)
TMP = os.environ.get("TEMP") or "/tmp"
DB = os.path.join(TMP, "omem_openclaw_skill.db")
if os.path.exists(DB):
    os.remove(DB)
os.environ["OMEM_DB"] = DB
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

# an account + key, the way a real user's env would hold them
r = urllib.request.urlopen(urllib.request.Request(
    BASE + "/v1/signup", method="POST",
    data=json.dumps({"email": "ocskill@kronos.com"}).encode(),
    headers={"Content-Type": "application/json"}), timeout=15)
signup = json.load(r)

ENV = {**os.environ,
       "OMEM_BASE_URL": BASE,
       "OMEM_API_KEY": signup["api_key"]["secret"],
       "OMEM_PROJECT": signup["project"]["id"],
       "OMEM_AGENT": "openclaw"}


def run(*args, env=None):
    p = subprocess.run([sys.executable, SCRIPT, *args],
                       capture_output=True, text=True, timeout=60,
                       env=env or ENV)
    try:
        return p.returncode, json.loads(p.stdout)
    except json.JSONDecodeError:
        return p.returncode, {"_raw": p.stdout[:200], "_err": p.stderr[:200]}


print("== the skill's whole loop, via the actual script ==")
rc, out = run("remember", "--about", "customer:alice",
              "--claim", "prefers_annual_billing", "--note", "said in the call")
check("remember returns an assertion id", rc == 0 and str(out.get("id", "")).startswith("a_"), out)
AID = out.get("id", "")

rc, out = run("believes", "--about", "customer:alice", "--claim", "prefers_annual_billing")
check("believes = BELIEVED_TRUE", rc == 0 and out.get("state") == "BELIEVED_TRUE", out)

rc, _ = run("remember", "--about", "customer:alice",
            "--claim", "not:prefers_annual_billing",
            env={**ENV, "OMEM_AGENT": "openclaw2"})
check("opposite claim recorded by a second agent", rc == 0)

rc, out = run("believes", "--about", "customer:alice", "--claim", "prefers_annual_billing")
check("believes flips to CONTRADICTED", rc == 0 and out.get("state") == "CONTRADICTED", out)

rc, out = run("conflicts")
check("conflicts lists the disagreement", rc == 0 and "prefers_annual_billing" in json.dumps(out))

rc, out = run("why", "--id", AID)
check("why returns state + provenance", rc == 0 and "state" in out and "provenance" in out,
      list(out.keys()))

rc, out = run("recall", "--about", "customer:alice")
check("recall finds the memories", rc == 0 and out.get("count", 0) >= 1, out)

rc, out = run("observe", "--text", "Alice prefers email over phone calls.")
check("observe accepted", rc == 0 and out.get("observed") is True, out)

rc, out = run("learn", "--text", "The customer wants to upgrade to enterprise.",
              "--about", "customer:alice")
check("learn produced beliefs", rc == 0 and isinstance(out.get("learned"), list), out)

print("== failure is loud, not silent ==")
rc, out = run("believes", "--about", "x", "--claim", "y",
              env={**ENV, "OMEM_API_KEY": "omem_sk_wrong"})
check("bad key exits nonzero with an error body", rc == 1 and "error" in out, out)

print("\n%d passed, %d failed" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)
