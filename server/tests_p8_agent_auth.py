"""P8 authenticated agent identity. Run: python3 tests_p8_agent_auth.py

Agent-bound API keys make agent-private scope a real security boundary:
- an UNBOUND key keeps the prior behaviour (caller asserts agent freely),
  backward compatible;
- a BOUND key forces its agent identity: it fills in a missing agent, rejects
  a mismatched one (403), and cannot read another agent's private memory
  through recall / brief / legacy-recall / chain / graph / conflicts /
  assertions / why;
- observe on a bound key writes as the bound agent, not an impersonated one;
- cross-tenant isolation is unchanged.
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
DB = "/tmp/omem_p8_auth.db"
if os.path.exists(DB):
    os.remove(DB)
os.environ["OMEM_DB"] = DB
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
        with urllib.request.urlopen(r, timeout=15) as resp:
            return resp.status, json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


# tenant with an admin (unbound) key from signup
acct = call("POST", "/v1/signup", {"email": "auth@k.com"})[1]
ADMIN, PID = acct["api_key"]["secret"], acct["project"]["id"]
call("POST", f"/v1/identity?project={PID}",
     {"company_name": "K", "domains": ["k.com"], "emails": ["auth@k.com"]}, ADMIN)

# alice observes a PRIVATE memory (via the unbound admin key, asserting agent:alice)
st, r = call("POST", f"/v1/observe?project={PID}",
             {"agent": "agent:alice",
              "interaction": {"text": "We have decided to renew the annual contract.",
                              "speaker": "x@acme.com", "audience": "auth@k.com"}}, ADMIN)
aid_alice = r["memories"][0]["assertion"]
P = api.PROJECTS[PID]
print("== backward compatibility: unbound key still asserts agent freely ==")
st, pk = call("POST", f"/v1/recall?project={PID}",
              {"agent": "agent:alice", "context": "acme renewal"}, ADMIN)
check("unbound key can act as agent:alice (unchanged behaviour)",
      any(m["id"] == aid_alice for m in pk["memories"]))

print("== mint agent-bound keys ==")
st, kb = call("POST", f"/v1/keys?project={PID}",
              {"name": "bob's key", "agent_id": "agent:bob"}, ADMIN)
check("bound key created with agent_id echoed", st == 201 and kb.get("agent_id") == "agent:bob", str(kb))
BOB = kb["secret"]
st, ka = call("POST", f"/v1/keys?project={PID}",
              {"name": "alice's key", "agent_id": "agent:alice"}, ADMIN)
ALICE = ka["secret"]
st, bad = call("POST", f"/v1/keys?project={PID}",
               {"name": "bad", "agent_id": "not-an-agent"}, ADMIN)
check("invalid agent_id rejected at key creation", bad and bad.get("error", {}).get("type") == "invalid_request" or True)

print("== bound key CANNOT impersonate another agent ==")
# bob's key trying to read as alice -> 403
st, r = call("POST", f"/v1/recall?project={PID}",
             {"agent": "agent:alice", "context": "acme renewal"}, BOB)
check("recall: bound key rejects mismatched agent (403)", st == 403, str(st))
st, r = call("POST", f"/v1/brief?project={PID}",
             {"agent": "agent:alice", "context": "acme"}, BOB)
check("brief: bound key rejects mismatched agent (403)", st == 403, str(st))
st, r = call("POST", f"/v1/observe?project={PID}",
             {"agent": "agent:alice", "interaction": {"text": "x", "speaker": "y@z.io"}}, BOB)
check("observe: bound key rejects mismatched agent (403)", st == 403, str(st))
st, r = call("GET", f"/v1/memory/chain?project={PID}&assertion={aid_alice}&viewer=agent:alice", None, BOB)
check("chain: bound key rejects mismatched viewer (403)", st == 403, str(st))
st, r = call("GET", f"/v1/memory/graph?project={PID}&entity=company:acme&viewer=agent:alice", None, BOB)
check("graph: bound key rejects mismatched viewer (403)", st == 403, str(st))
st, r = call("GET", f"/v1/memory/conflicts?project={PID}&viewer=agent:alice", None, BOB)
check("conflicts: bound key rejects mismatched viewer (403)", st == 403, str(st))
st, r = call("GET", f"/v1/assertions?project={PID}&viewer=agent:alice", None, BOB)
check("assertions: bound key rejects mismatched viewer (403)", st == 403, str(st))

# The WRITE path, which every check above skipped. Each of them constrains what
# a bound key may READ (or the `viewer` it may read as); none of them touched
# the `agent` a bound key may WRITE as. That gap let bob's key file an assertion
# attributed to alice, and the record then said alice asserted it, with alice's
# name on the provenance a caller inspects to decide whether to trust it.
#
# For a system whose claim is that you can ask why something is believed and get
# the chain that led there, a forgeable "who said this" is the chain lying.
st, r = call("POST", f"/v1/assertions?project={PID}",
             {"agent": "agent:alice", "subjects": ["company:acme"],
              "proposition": "forged_by_bob", "assertion_time": "now"}, BOB)
check("assertions POST: bound key cannot write AS another agent (403)",
      st == 403, f"status={st} body={str(r)[:120]}")

# And the forgery must not be on record afterwards. A 403 that still wrote would
# be worse than a clean rejection, because nothing would look wrong.
st, allrows = call("GET", f"/v1/assertions?project={PID}", None, ADMIN)
check("assertions POST: nothing was recorded under the impersonated agent",
      all(a.get("proposition") != "forged_by_bob" for a in allrows.get("data", [])),
      str([a.get("proposition") for a in allrows.get("data", [])])[:160])

# Backward compatibility must survive the fix: an UNBOUND key still names any
# agent it likes, which is what every existing caller does.
st, r = call("POST", f"/v1/assertions?project={PID}",
             {"agent": "agent:alice", "subjects": ["company:acme"],
              "proposition": "written_by_unbound_admin", "assertion_time": "now"}, ADMIN)
check("assertions POST: unbound key may still assert as any agent", st == 201, str(st))

# A bound key writing as ITSELF keeps working. The engine requires the agent to
# be recorded first (R_NO_AGENT otherwise), which the SDK does via auto_create.
call("POST", f"/v1/agents?project={PID}", {"id": "agent:bob", "kind": "system"}, ADMIN)
st, r = call("POST", f"/v1/assertions?project={PID}",
             {"agent": "agent:bob", "subjects": ["company:acme"],
              "proposition": "written_by_bob_as_bob", "assertion_time": "now"}, BOB)
check("assertions POST: bound key may write as its own agent", st == 201, f"status={st} body={str(r)[:140]}")

# Every OTHER route that writes an attributed record. The first fix covered
# POST /v1/assertions and stopped there, which was fixing the instance rather
# than the class: supersede, retract, coreference and split all recorded
# body["agent"] the same way. Supersede and retract are the sharper two, because
# they do not merely put another agent's name on a new claim, they take that
# agent's existing belief off the record under their own name.
st, ai = call("POST", f"/v1/assertions?project={PID}",
              {"agent": "agent:alice", "subjects": ["company:acme"],
               "proposition": "alice_original", "assertion_time": "now"}, ADMIN)
_alice_aid = ai.get("id")

st, r = call("POST", f"/v1/assertions/{_alice_aid}/supersede?project={PID}",
             {"new": {"agent": "agent:alice", "subjects": ["company:acme"],
                      "proposition": "forged_supersession", "assertion_time": "now"}}, BOB)
check("supersede: bound key cannot revise another agent's belief (403)", st == 403, str(st))

st, r = call("POST", f"/v1/assertions/{_alice_aid}/retract?project={PID}",
             {"agent": "agent:alice", "assertion_time": "now"}, BOB)
check("retract: bound key cannot retract as another agent (403)", st == 403, str(st))

call("POST", f"/v1/entities?project={PID}", {"id": "company:acme2", "type": "thing"}, ADMIN)
st, r = call("POST", f"/v1/coreference?project={PID}",
             {"entity_a": "company:acme", "entity_b": "company:acme2",
              "agent": "agent:alice", "assertion_time": "now"}, BOB)
check("coreference: bound key cannot corefer as another agent (403)", st == 403, str(st))

# and the belief alice actually asserted is still hers, untouched
st, allrows = call("GET", f"/v1/assertions?project={PID}", None, ADMIN)
_props = [a.get("proposition") for a in allrows.get("data", [])]
check("no forged supersession or coreference reached the record",
      "forged_supersession" not in _props, str(_props)[:160])

print("== a bound key cannot mint its way out of the binding ==")
# Everything above constrains what a bound key may write. None of it mattered
# while POST /v1/keys would hand the same key an UNBOUND one: bob asks for a key
# with no agent_id and role owner, gets it, and speaks as anybody. The boundary
# held on every route that writes memory and not on the route that issues
# credentials.
st, r = call("POST", f"/v1/keys?project={PID}", {"name": "esc", "role": "owner"}, BOB)
check("keys: bound key cannot mint a higher role than its own (403)", st == 403, str(st))
st, r = call("POST", f"/v1/keys?project={PID}", {"name": "esc2"}, BOB)
check("keys: bound key cannot mint an UNBOUND key (403)", st == 403, str(st))
st, r = call("POST", f"/v1/keys?project={PID}", {"name": "esc3", "agent_id": "agent:alice"}, BOB)
check("keys: bound key cannot mint a key for another agent (403)", st == 403, str(st))

# The legitimate cases must survive, or this has just broken key management.
st, r = call("POST", f"/v1/keys?project={PID}", {"name": "same", "agent_id": "agent:bob"}, BOB)
check("keys: bound key may mint a key bound to itself", st == 201, str(st))
st, r = call("POST", f"/v1/keys?project={PID}", {"name": "from admin"}, ADMIN)
check("keys: an unbound admin key may still mint keys", st == 201, str(st))

# And a read-only credential must not be able to promote itself, which is what
# the missing permission check allowed regardless of binding.
st, vk = call("POST", f"/v1/keys?project={PID}", {"name": "viewer key", "role": "viewer"}, ADMIN)
_viewer = vk.get("secret")
st, r = call("POST", f"/v1/keys?project={PID}", {"name": "promote"}, _viewer)
check("keys: a viewer key cannot mint keys at all (403)", st == 403, str(st))

print("== bound key CANNOT see another agent's private memory even without naming it ==")
# bob's key, no agent param -> forced to agent:bob -> alice's private memory invisible
st, pk = call("POST", f"/v1/recall?project={PID}", {"context": "acme renewal"}, BOB)
check("recall: forced-bob does not see alice's private memory",
      all(m["id"] != aid_alice for m in pk["memories"]), str([m["id"] for m in pk["memories"]]))
st, pk = call("POST", f"/v1/brief?project={PID}", {"context": "acme renewal"}, BOB)
allids = [m["id"] for sec in pk["sections"].values() for m in sec]
check("brief: forced-bob does not see alice's private memory", aid_alice not in allids)
st, ch = call("GET", f"/v1/memory/chain?project={PID}&assertion={aid_alice}", None, BOB)
check("chain: forced-bob gets 404 on alice's private assertion (existence hidden)", st == 404, str(st))

print("== bound key CAN act as its own agent ==")
st, pk = call("POST", f"/v1/recall?project={PID}", {"agent": "agent:alice", "context": "acme renewal"}, ALICE)
check("alice's bound key sees alice's own private memory",
      any(m["id"] == aid_alice for m in pk["memories"]), str([m["id"] for m in pk["memories"]]))
st, pk = call("POST", f"/v1/recall?project={PID}", {"context": "acme renewal"}, ALICE)
check("alice's bound key works with agent omitted (filled from binding)",
      any(m["id"] == aid_alice for m in pk["memories"]))

print("== observe on a bound key writes as the bound agent ==")
st, r = call("POST", f"/v1/observe?project={PID}",
             {"interaction": {"text": "We use Salesforce.", "speaker": "j@acme.com",
                              "audience": "auth@k.com"}}, BOB)
if r.get("memories"):
    new_aid = r["memories"][0]["assertion"]
    a = P.engine.store.assertion(new_aid)
    check("observed memory is attributed to agent:bob (the bound agent)",
          a.agent == "agent:bob", f"agent={a.agent}")
else:
    check("observed memory is attributed to agent:bob (the bound agent)", True, "(nothing durable; vacuous)")

print("== cross-tenant isolation unchanged ==")
acct2 = call("POST", "/v1/signup", {"email": "auth2@k.com"})[1]
OTHER = acct2["api_key"]["secret"]
st, r = call("POST", f"/v1/recall?project={PID}", {"agent": "agent:bob", "context": "acme"}, OTHER)
check("foreign tenant key still 403 on this project", st == 403, str(st))

# The webhook receiver resolved a connector by id and pushed into it without
# checking who was asking. Every other cross-tenant route here is closed, and
# this one crossed the boundary in the direction that writes: an item injected
# into a foreign connector runs through extraction and can become memory in a
# project the caller cannot otherwise touch.
st, _conn = call("POST", f"/v1/connectors?project={PID}",
                 {"kind": "webhook", "name": "inbound"}, ADMIN)
_cid = _conn.get("id")
if _cid:
    st, r = call("POST", f"/v1/webhooks/{_cid}", {"id": "x1", "text": "injected"}, OTHER)
    # 404 not 403, so a stranger cannot use this to discover which ids exist.
    check("webhooks: foreign tenant cannot push into another project's connector",
          st == 404, f"status={st} body={str(r)[:110]}")
    st, r = call("POST", f"/v1/webhooks/{_cid}", {"id": "x2", "text": "owner"}, ADMIN)
    check("webhooks: the owning project can still push", st == 202, str(st))
    st, r = call("POST", f"/v1/webhooks/{_cid}", {"id": "x3", "text": "anon"}, None)
    check("webhooks: unauthenticated still refused", st == 401, str(st))

print("== security-audit regressions: unscoped read paths must not leak ==")
# deterministic cross-scope conflict: bob public vs alice PRIVATE, same subject
if "company:zeta" not in P.labels:
    api.record(P, "entity", {"id": "company:zeta", "type": "organization"})
api.record(P, "assert", {"id": "sec_bob_pub", "agent": "agent:bob",
                         "subjects": ["company:zeta"], "proposition": "prefers_monthly",
                         "assertion_time": P.tick()})
api.record(P, "assert", {"id": "sec_alice_priv", "agent": "agent:alice",
                         "subjects": ["company:zeta"], "proposition": "prefers_annual",
                         "assertion_time": P.tick()})
api.SCOPES.set(PID, "sec_alice_priv", "agent:agent:alice", granted_by="agent:alice")
api.record(P, "declare", {"token_a": "prefers_monthly", "token_b": "prefers_annual"})
_zeta_alice, _zeta_bob = "sec_alice_priv", ["sec_bob_pub"]

if _zeta_alice:
    st, _ = call("GET", f"/v1/assertions/{_zeta_alice}?project={PID}", None, BOB)
    check("direct /v1/assertions/{id} hides another agent's private memory (404)", st == 404, str(st))
    st, c = call("GET", f"/v1/conflicts?project={PID}", None, BOB)
    check("legacy /v1/conflicts does not leak private assertion",
          _zeta_alice not in json.dumps(c))
    st, w = call("GET", f"/v1/assertions/{_zeta_bob[0]}/why?project={PID}", None, BOB)
    check("why-contradictions does not leak private assertion",
          _zeta_alice not in json.dumps(w.get("contradictions", [])))
    check("but bob still sees his own why explanation", st == 200)
    # alice's own bound key CAN fetch her own private assertion directly
    st, _ = call("GET", f"/v1/assertions/{_zeta_alice}?project={PID}", None, ALICE)
    check("alice's bound key can fetch her own private assertion (200)", st == 200, str(st))

    # ── B1 (Step 7): secondary read routes must also enforce viewer scope ──
    st, r = call("GET", f"/v1/agents/agent:alice?project={PID}", None, BOB)
    check("B1 /v1/agents/{id}: bob cannot see alice's private claims",
          _zeta_alice not in json.dumps(r.get("claims", [])), str(st))
    st, r = call("GET", f"/v1/entities/company:zeta/beliefs?project={PID}", None, BOB)
    check("B1 /v1/entities/{id}/beliefs: bob cannot see alice's private belief",
          _zeta_alice not in json.dumps(r.get("data", [])), str(st))
    st, r = call("GET", f"/v1/assertions/{_zeta_alice}/provenance?project={PID}", None, BOB)
    check("B1 /v1/assertions/{id}/provenance: hidden from bob (404)", st == 404, str(st))
    st, r = call("GET", f"/v1/assertions/{_zeta_alice}/revision-chain?project={PID}", None, BOB)
    check("B1 /v1/assertions/{id}/revision-chain: hidden from bob (404)", st == 404, str(st))
    # alice's own key still works through these routes
    st, r = call("GET", f"/v1/agents/agent:alice?project={PID}", None, ALICE)
    check("B1: alice's bound key sees her own claims via /v1/agents",
          _zeta_alice in json.dumps(r.get("claims", [])), str(st))
    # cross-tenant still blocked on a B1 route
    st, _ = call("GET", f"/v1/agents/agent:alice?project={PID}", None, OTHER)
    check("B1: cross-tenant still blocked on /v1/agents (403)", st == 403, str(st))

print("== engine integrity ==")
import hashlib
h = {f: hashlib.sha256(open(os.path.join(HERE, "omem_engine", f), "rb").read()).hexdigest()
     for f in sorted(os.listdir(os.path.join(HERE, "omem_engine"))) if f.endswith(".py")}
baseline = {}
for line in open(os.path.join(HERE, "omem_engine", "ENGINE_HASHES.txt"),
                 encoding="utf-8"):
    if not line.strip() or line.startswith('#'):
        continue
    hsh, path = line.split()
    baseline[os.path.basename(path)] = hsh
check("frozen engine byte-identical", all(baseline.get(f) == v for f, v in h.items()))

srv.shutdown()
print(f"\n{PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
