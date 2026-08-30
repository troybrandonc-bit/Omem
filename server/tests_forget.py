"""The right to be forgotten, executed for real. Run: python3 tests_forget.py

Retraction is not erasure: the append-only log keeps history, and Article 17
means the personal data is GONE. This suite pins the whole path on the hardest
shape -- one message that produced BOTH a company fact and the writer's own
habit -- and checks that forgetting the person removes every trace of them,
keeps the company's belief, redacts the person's sentence from the surviving
evidence and event label, leaves a log that still replays and serves, and
records only a hash that the erasure happened.
"""
import json
import os
import sqlite3
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "sdk", "python"))
TMP = os.environ.get("TEMP") or "/tmp"
DB = os.path.join(TMP, "omem_forget.db")
if os.path.exists(DB):
    os.remove(DB)
os.environ["OMEM_DB"] = DB
os.environ.setdefault("OMEM_TENANT_RL_BURST", "10000")
os.environ.setdefault("OMEM_TENANT_RL_RPS", "10000")

import api  # noqa: E402
import omem  # noqa: E402
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


def call(method, path, body=None, expect_error=False):
    req = urllib.request.Request(BASE + path, method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Content-Type": "application/json", "Authorization": "Bearer " + KEY})
    try:
        return json.loads(urllib.request.urlopen(req, timeout=30).read() or b"{}"), None
    except urllib.error.HTTPError as e:
        if not expect_error:
            raise
        return None, e.code


acct = json.loads(urllib.request.urlopen(urllib.request.Request(
    BASE + "/v1/signup", method="POST",
    data=json.dumps({"email": "forget@kronos.com"}).encode(),
    headers={"Content-Type": "application/json"})).read())
KEY = acct["token"]
PID = acct["project"]["id"]
mem = omem.Memory(KEY, base_url=BASE, project=PID)
ALICE = "person:alice_chen@acme"
QALICE = urllib.parse.quote(ALICE, safe="")

call("POST", f"/v1/identity?project={PID}",
     {"company_name": "T", "emails": ["me@t.dev"], "domains": ["t.dev"]})
# One message -> a company fact AND the writer's own habit: a shared event.
mem.observe("agent:sup", {
    "text": "we have decided to switch to annual billing. Mornings work best for me.",
    "speaker": "Alice Chen <alice.chen@acme.com>"})
mem.remember("agent:sup", "company:acme", "is_enterprise_customer")

before, _ = call("GET", f"/v1/assertions?project={PID}")
check("setup: the shared message produced facts for both parties",
      any(ALICE in a["subjects"] for a in before["data"])
      and any("company:acme" in a["subjects"] for a in before["data"]))

print("== the guards ==")
_, code = call("POST", f"/v1/entities/{QALICE}/forget?project={PID}",
               {"confirm": "wrong"}, expect_error=True)
check("confirm must repeat the id", code == 422, code)
_, code = call("POST", f"/v1/entities/person%3Anobody/forget?project={PID}",
               {"confirm": "person:nobody"}, expect_error=True)
check("an unknown entity is 404", code == 404, code)

print("== the erasure ==")
rep, _ = call("POST", f"/v1/entities/{QALICE}/forget?project={PID}",
              {"confirm": ALICE, "email": "alice.chen@acme.com"})
check("replay was verified before writing", rep.get("verified_replay") is True)
check("ops were removed", rep["removed"].get("ops", 0) >= 3, rep["removed"])
check("her evidence rows were removed", rep["removed"].get("assertion_evidence", 0) >= 1)
check("the surviving quote was redacted", rep["redacted"].get("evidence_quotes", 0) >= 1)
check("the shared event label was redacted", rep["redacted"].get("event_labels", 0) >= 1)

after, _ = call("GET", f"/v1/assertions?project={PID}")
check("no assertion references her any more",
      not any(ALICE in a["subjects"] for a in after["data"]))
ents, _ = call("GET", f"/v1/entities?project={PID}")
ids = {e["id"] for e in ents["data"]}
check("her entity is gone", ALICE not in ids)
check("the company survives", "company:acme" in ids)

acme = [a for a in after["data"] if a.get("proposition") == "prefers_annual_billing"]
check("the company's belief from her message survives", len(acme) == 1, len(acme))
if acme:
    w, _ = call("GET", f"/v1/assertions/{urllib.parse.quote(acme[0]['id'], safe='')}/why?project={PID}")
    ev = (w.get("evidence") or {}).get("evidence")
    check("its evidence no longer carries her sentence", ev == api.ERASURE_NOTE, ev)
tl, _ = call("GET", f"/v1/timeline?project={PID}&as_of=now")
labels = [e.get("label") for e in tl["events"]]
check("the shared event's label is the erasure note, not her words",
      api.ERASURE_NOTE in labels and not any("Mornings" in (l or "") for l in labels), labels)

print("== the record that it happened, holding nothing ==")
# Read through the SERVER's own database handle, not a fresh sqlite connection:
# under Postgres the erasures row lives in Postgres, and a raw sqlite reader
# would find no such table. STORE.db speaks whichever backend is configured.
row = api.STORE.db.execute(
    "SELECT * FROM erasures WHERE project_id=?", (PID,)).fetchone()
check("an erasures row exists", row is not None)
if row:
    check("it holds a hash, not the identity",
          ALICE not in row["entity_hash"] and len(row["entity_hash"]) == 16, row["entity_hash"])
    check("it records what was removed, as counts",
          "removed" in json.loads(row["removed"]))

print("== life goes on: the rewritten log still serves writes ==")
r = mem.observe("agent:sup", {"text": "we are planning to upgrade to the enterprise plan.",
                              "speaker": "Bob Ramos <bob.ramos@acme.com>"})
check("a new observation lands after the rewrite", len(r.get("memories", [])) >= 1)
_, code = call("POST", f"/v1/entities/{QALICE}/forget?project={PID}",
               {"confirm": ALICE}, expect_error=True)
check("forgetting her twice finds nothing (404)", code == 404, code)

print("\n%d passed, %d failed" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)
