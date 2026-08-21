"""One spelling of a claim is one claim. Run: python3 tests_canonical_form.py

THE PROBLEM. Proposition identity is byte-equality of canonical form
(Profile 3.1), which is right and unforgiving. `prefers annual billing`,
`Prefers_Annual_Billing` and `prefers-annual-billing` were three unrelated facts
about the same customer. Two agents written by two people, or one agent after
somebody reworded a prompt. Filled a project with beliefs that could never
contradict each other, never corroborate each other and never be recalled
together, and nothing anywhere looked wrong. Silent fragmentation is the worst
failure a memory can have, because the product keeps answering confidently.

extraction.py had required the shape `^(not:)?[a-z][a-z0-9_]{2,63}$` of
propositions since the beginning, but only on the email path. Anything arriving
through the SDK or the API kept whatever spelling the caller used. This applies
the project's own existing rule at the boundary where facts actually enter.

WHERE IT MUST APPLY, or it makes things worse rather than better: the write
path, the query path, and declarations. Normalising writes but not queries would
mean believes() missing a fact remember() had just stored. Normalising writes but
not contradict() would mean a declared pair that opposes nothing. Each of those
is a subtler bug than the one being fixed, so each has a test here.

WHAT IT DELIBERATELY DOES NOT DO. It does not decide `wants_annual` and
`prefers_annual` are the same claim. Case and punctuation are not meaning;
synonymy is, and guessing at it is the one thing this engine must never do.
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
# A fresh database per run. Pinning one path meant the second run signed up an
# address that already existed, and signup only returns an api_key for a NEW
# account - so the suite passed once and then failed forever after.
_DB = os.path.join(HERE, "data", "test_canonical.db")
for _stale in (_DB, _DB + "-wal", _DB + "-shm"):
    if os.path.exists(_stale):
        os.remove(_stale)
os.environ.setdefault("OMEM_DB", _DB)
os.environ.pop("OMEM_LLM_API_KEY", None)

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
BASE = f"http://127.0.0.1:{PORT}"


def call(m, path, body=None, key=None):
    r = urllib.request.Request(f"{BASE}{path}", method=m,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Content-Type": "application/json",
                 **({"Authorization": f"Bearer {key}"} if key else {})})
    try:
        with urllib.request.urlopen(r, timeout=60) as resp:
            return resp.status, json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


print("== the form itself ==")
cf = api.canonical_form
check("spaces become underscores", cf("Prefers Annual Billing") == "prefers_annual_billing")
check("hyphens too", cf("prefers-annual-billing") == "prefers_annual_billing")
check("case is levelled", cf("PREFERS_ANNUAL_BILLING") == "prefers_annual_billing")
check("surrounding space is dropped", cf("  prefers_annual  ") == "prefers_annual")
check("runs of punctuation collapse to one underscore",
      cf("prefers   ---   annual") == "prefers_annual")
check("the negation prefix survives", cf("not:Prefers Annual") == "not:prefers_annual")

# The reserved marker is not a claim (Profile 3.3). Lowercasing it would break
# N10: a retraction must contribute to neither side of a proposition state.
check("RETRACTED is left exactly alone", cf("RETRACTED") == "RETRACTED")
check("a bare negation prefix is untouched", cf("not:") == "not:")

# An ASCII-only rule turned café into caf_ and señor into se_or, quietly
# mangling propositions in the languages this product is most likely to meet.
check("accented letters survive", cf("Café Señor") == "café_señor")
check("non-Latin scripts survive", cf("已付款") == "已付款")
check("a token of pure punctuation is kept rather than emptied", cf("---") == "---")
check("normalising twice changes nothing (idempotent)",
      cf(cf("Prefers Annual Billing")) == cf("Prefers Annual Billing"))

print("== through the API: one claim, however it is spelled ==")
acct = call("POST", "/v1/signup", {"email": "canon@k.com"})[1]
KEY, PID = acct["api_key"]["secret"], acct["project"]["id"]
P = api.PROJECTS[PID]
api.record(P, "agent", {"id": "agent:s", "kind": "system"})
for e in ("customer:1", "customer:2", "customer:3"):
    api.record(P, "entity", {"id": e, "type": "organization"})


def assert_(aid, subject, proposition):
    api.record(P, "assert", {"id": aid, "agent": "agent:s", "subjects": [subject],
                             "proposition": proposition, "assertion_time": P.tick()})


assert_("k1", "customer:1", "Prefers Annual Billing")
stored = P.engine.store.assertion("k1").proposition
check("what is stored is the canonical token", stored == "prefers_annual_billing", stored)
check("and the caller's spelling is kept as the label",
      (P.labels.get("k1") or {}).get("label") == "Prefers Annual Billing",
      str(P.labels.get("k1")))

# The whole point: a query written differently from the write must still find it.
st, r = call("POST", f"/v1/queries/proposition-state?project={PID}",
             {"subjects": ["customer:1"], "proposition": "prefers-annual-billing"}, KEY)
check("a differently spelled query finds the same fact",
      st == 200 and r.get("state") == "BELIEVED_TRUE", f"{st} {r}")

# Two agents, two spellings, one referent: this used to be two unrelated facts.
assert_("k2", "customer:2", "pays_late")
assert_("k3", "customer:2", "not:Pays Late")
check("a contradiction is found across two spellings",
      P.engine.proposition_state(("customer:2",), "pays_late", P.now()) == "CONTRADICTED",
      P.engine.proposition_state(("customer:2",), "pays_late", P.now()))

print("== declarations are normalised the same way ==")
# A pair declared in prose must oppose the tokens actually stored, or the
# declaration silently does nothing at all.
st, _ = call("POST", f"/v1/contradictions?project={PID}",
             {"token_a": "Prefers Annual", "token_b": "prefers monthly"}, KEY)
check("POST /v1/contradictions accepts a prose pair", st == 201, f"status {st}")
assert_("k4", "customer:3", "prefers_annual")
assert_("k5", "customer:3", "PREFERS MONTHLY")
check("the declared pair opposes the stored tokens",
      P.engine.proposition_state(("customer:3",), "prefers_annual", P.now()) == "CONTRADICTED",
      P.engine.proposition_state(("customer:3",), "prefers_annual", P.now()))
st, lst = call("GET", f"/v1/contradictions?project={PID}", None, KEY)
check("and it is listed in canonical form", any(
    sorted([d["token_a"], d["token_b"]]) == ["prefers_annual", "prefers_monthly"]
    for d in lst.get("data", [])), str(lst.get("data")))

print("== what it refuses to do ==")
# Synonymy is a judgment about meaning. Normalisation must not make one.
assert_("k6", "customer:1", "wants_annual_billing")
check("a synonym is still a different claim",
      P.engine.proposition_state(("customer:1",), "wants_annual_billing", P.now())
      == "BELIEVED_TRUE"
      and P.engine.store.assertion("k6").proposition == "wants_annual_billing")
check("and it did not silently merge into the first",
      P.engine.store.assertion("k1").proposition != P.engine.store.assertion("k6").proposition)

print("== restart replay produces the same tokens ==")
before = sorted(a.proposition for a in P.engine.store.assertions())
srv.shutdown()
import importlib  # noqa: E402
import store as store_mod  # noqa: E402
importlib.reload(store_mod)
sys.modules.pop("api")
api2 = importlib.import_module("api")
P2 = api2.PROJECTS.get(PID)
check("project rehydrated", P2 is not None)
if P2:
    after = sorted(a.proposition for a in P2.engine.store.assertions())
    check("every proposition replays to the same canonical token", before == after,
          f"{len(before)} vs {len(after)}")
    check("and the contradiction still holds after the restart",
          P2.engine.proposition_state(("customer:2",), "pays_late", P2.now()) == "CONTRADICTED")

print(f"\n{PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
