#!/usr/bin/env python3
"""Generate golden_log_v1.json: a frozen ops log and the digest it replays to.

Run ONCE, commit the output, and then never run it again for v1. The whole
point of the fixture is that it does not change: tests_upgrade_stability.py
replays it on every commit and any code change that makes the same log
produce a different state digest goes red. If a future, deliberate semantic
change ever needs a new baseline, it gets golden_log_v2.json NEXT TO this
one, with the old file still replaying, because "we changed what your
history means" is exactly the event the suite exists to make loud.

The session below walks one story through most of the engine: entities and
agents, plain claims, relation claims, a contradiction, a supersession, a
retraction, a coreference merge and split, a declared rule with its
conclusion, and the take-back cascade. Nothing time-based, nothing random
beyond ids that are recorded into the log itself.
"""
import json
import os
import sys
import threading
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
SERVER = os.path.dirname(HERE)
sys.path.insert(0, SERVER)
sys.path.insert(0, os.path.join(SERVER, "..", "sdk", "python"))
TMP = os.environ.get("TEMP") or "/tmp"
DB = os.path.join(TMP, "omem_golden_gen.db")
if os.path.exists(DB):
    os.remove(DB)
os.environ["OMEM_DB"] = DB
os.environ.setdefault("OMEM_TENANT_RL_BURST", "10000")
os.environ.setdefault("OMEM_TENANT_RL_RPS", "10000")

import api  # noqa: E402
import omem  # noqa: E402
import replay_verify  # noqa: E402
from http.server import ThreadingHTTPServer  # noqa: E402

srv = ThreadingHTTPServer(("127.0.0.1", 0), api.Handler)
threading.Thread(target=srv.serve_forever, daemon=True).start()
time.sleep(0.2)
BASE = "http://127.0.0.1:%d" % srv.server_address[1]

req = urllib.request.Request(BASE + "/v1/signup", method="POST",
                             data=json.dumps({"email": "golden@kronos.com"}).encode(),
                             headers={"Content-Type": "application/json"})
acct = json.loads(urllib.request.urlopen(req, timeout=20).read())
KEY, PID = acct["api_key"]["secret"], acct["project"]["id"]
mem = omem.Memory(KEY, base_url=BASE, project=PID)
A, B = "agent:scout", "agent:archivist"

# The story.
first = mem.remember(A, "person:ada", "prefers_annual_billing")
mem.remember(A, "person:ada", "based_in_turin")
mem.remember(B, "person:ada", "not:prefers_annual_billing")      # a contradiction
mem.remember(A, ["person:ada", "company:tabulate"], "rel_works_at_tabulate")
owns = mem.remember(A, ["company:kernelworks", "company:tabulate"],
                    "rel_owns_tabulate")
mem.declare_rule(when=[("works_at", "fwd"), ("owns", "rev")],
                 then=("involves", "rev"), agent=A)
mem.infer()                                                       # concludes
mem.retract(owns["id"], agent=A)                                  # cascade
sup_target = mem.remember(A, "person:grace", "lives_in_berlin")
mem._req("POST", "/v1/assertions/%s/supersede" % sup_target["id"],
         {"new": {"agent": A, "subjects": ["person:grace"],
                  "proposition": "lives_in_paris"}})
for e in ("customer:c1", "customer:c2"):
    mem.ensure_entity(e)
cor = mem.corefer("customer:c1", "customer:c2", agent=A)
mem.split(cor["id"], agent=A)
mem.retract(first["id"], agent=B)

# Freeze what the log says and what it replays to.
row = next(r for r in api.STORE.projects_all() if r["id"] == PID)
ops = list(api.STORE.ops_for(PID))
p1 = replay_verify.replay(api, row, ops)
p2 = replay_verify.replay(api, row, ops)
d1, counts = replay_verify.state_digest(p1)
d2, _ = replay_verify.state_digest(p2)
assert d1 == d2, "the golden session itself does not replay deterministically"

out = os.path.join(HERE, "golden_log_v1.json")
with open(out, "w", encoding="utf-8") as f:
    json.dump({
        "version": 1,
        "generated_with": omem.__version__,
        "project_row": {k: row[k] for k in
                        ("id", "name", "env", "org_id", "is_demo")},
        "ops": ops,
        "digest": d1,
        "counts": counts,
    }, f, indent=1, sort_keys=True)
print("wrote %s: %d ops, digest %s" % (out, len(ops), d1[:16]))
