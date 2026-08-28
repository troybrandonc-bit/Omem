"""What changed since I was last here. Run: python3 tests_belief_diff.py

Everything the diff reports has been reconstructable since the beginning --
belief state, conflicts and the referent partition all take a past T -- and
no surface ever did the comparison. An agent starting a session wants the
delta, not the whole pack: what appeared, what closed and HOW (superseded by
what, or withdrawn), which conflicts opened, which resolved, who merged, who
split.

The suite pins the boundaries: the diff is read-only, deterministic, clamps
a future `since` instead of inventing one, distinguishes superseded from
withdrawn, hides from a viewer what that viewer could never have recalled,
and reports quiet honestly when nothing happened.
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
sys.path.insert(0, os.path.join(HERE, "..", "sdk", "python"))
TMP = os.environ.get("TEMP") or "/tmp"
DB = os.path.join(TMP, "omem_belief_diff.db")
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


OWNER = "diff@kronos.com"

srv = ThreadingHTTPServer(("127.0.0.1", 0), api.Handler)
PORT = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()
time.sleep(0.2)
BASE = "http://127.0.0.1:%d" % PORT


def call(m, path, body=None, key=None):
    h = {"Content-Type": "application/json"}
    if key:
        h["Authorization"] = "Bearer " + key
    r = urllib.request.Request(
        BASE + path, method=m,
        data=json.dumps(body).encode() if body is not None else None, headers=h)
    try:
        with urllib.request.urlopen(r, timeout=20) as resp:
            return resp.status, json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


acct = call("POST", "/v1/signup", {"email": OWNER})[1]
KEY, PID = acct["api_key"]["secret"], acct["project"]["id"]
mem = omem.Memory(KEY, base_url=BASE, project=PID)
A = "agent:owner"

print("== the world before the absence ==")
b1 = mem.remember(A, "person:sarah", "prefers_annual_billing")
b2 = mem.remember(A, "company:acme", "is_pilot_customer")
# a conflict that exists BEFORE the era, to be resolved after it
mem.remember(A, "person:tom", "likes_coffee")
old_no = mem.remember(A, "person:tom", "not:likes_coffee")
# a pre-era merge, to be split after
for e in ("customer:e3", "customer:e4"):
    mem.ensure_entity(e)
pre_cor = mem.corefer("customer:e3", "customer:e4", agent=A)

T0 = api.PROJECTS[PID].now()
d0 = mem.changes(since=T0)
check("nothing has happened yet, and the diff says so honestly",
      d0.get("quiet") is True and not d0["appeared"] and not d0["closed"], d0)

print("== the era: things happen while nobody is looking ==")
b3 = mem.remember(A, "company:acme", "signed_expansion")
st, sup = call("POST", "/v1/assertions/%s/supersede?project=%s" % (b1["id"], PID),
               {"new": {"agent": A, "subjects": ["person:sarah"],
                        "proposition": "prefers_monthly_billing"}}, KEY)
check("a belief was revised", st == 201, sup)
mem.retract(b2["id"], agent=A)
mem.retract(old_no["id"], agent=A)          # the old conflict resolves
mem.remember(A, "person:dana", "wants_discount")
mem.remember(A, "person:dana", "not:wants_discount")   # a new conflict opens
for e in ("customer:e1", "customer:e2"):
    mem.ensure_entity(e)
mem.corefer("customer:e1", "customer:e2", agent=A)     # a merge
mem.split(pre_cor["id"], agent=A)                      # and a split

print("== the return: one question, the whole delta ==")
d = mem.changes(since=T0)
check("the diff is not quiet", d.get("quiet") is False, d)

appeared = {x["proposition"] for x in d["appeared"]}
check("what appeared includes the new fact and the revision's new side",
      {"signed_expansion", "prefers_monthly_billing"} <= appeared, appeared)

closed = {x["id"]: x for x in d["closed"]}
check("the revised belief is closed as SUPERSEDED, naming its successor",
      closed.get(b1["id"], {}).get("how") == "superseded"
      and closed[b1["id"]]["superseded_by"]["proposition"]
      == "prefers_monthly_billing", closed.get(b1["id"]))
check("the retracted belief is closed as WITHDRAWN, which is not the same thing",
      closed.get(b2["id"], {}).get("how") == "withdrawn", closed.get(b2["id"]))
check("who closed each is on the record",
      closed[b1["id"]].get("by") == A and closed[b2["id"]].get("by") == A)

check("the new conflict is reported",
      any(sorted(c["propositions"]) == ["not:wants_discount", "wants_discount"]
          for c in d["new_conflicts"]), d["new_conflicts"])
check("and the old one is reported RESOLVED",
      any(sorted(c["propositions"]) == ["likes_coffee", "not:likes_coffee"]
          for c in d["resolved_conflicts"]), d["resolved_conflicts"])

check("the merge is in the identity section",
      ["customer:e1", "customer:e2"] in d["identity"]["merged"], d["identity"])
check("and the split is too",
      ["customer:e3", "customer:e4"] in d["identity"]["split"], d["identity"])

print("== the boundaries ==")
d2 = mem.changes(since=T0)
check("the same question gives the same answer", d == d2)
now = api.PROJECTS[PID].now()
check("a diff against now is quiet", mem.changes(since=now).get("quiet") is True)
check("a future `since` is clamped, not honoured",
      mem.changes(since=now + 9999).get("since") == now)
st, bad = call("GET", "/v1/memory/diff?project=%s&since=abc" % PID, None, KEY)
check("a malformed since is refused with the shape it wanted", st == 422, bad)

print("== a viewer's diff contains only what they could have recalled ==")
mem.remember(A, "person:sarah", "salary_negotiation_open",
             scope="agent:%s" % A)
d_owner = mem.changes(since=T0)
d_other = mem.changes(since=T0, viewer="agent:other")
check("the operator's diff has the private belief",
      any(x["proposition"] == "salary_negotiation_open"
          for x in d_owner["appeared"]))
check("another agent's diff does not",
      not any(x["proposition"] == "salary_negotiation_open"
              for x in d_other["appeared"]), [x["proposition"] for x in d_other["appeared"]])
check("while public changes still reach them",
      any(x["proposition"] == "signed_expansion" for x in d_other["appeared"]))

print("\n%d passed, %d failed" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)
