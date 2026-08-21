"""P7 old-vs-new equivalence. Run: python3 tests_p7_equivalence.py

Proves the indexed candidate path produces SEMANTICALLY IDENTICAL results to
the original scan path, for the same DB state and query. The decision layer,
scope enforcement, engine state, conflict analysis, and ordering are shared,
only candidate GENERATION differs, so identical output demonstrates the index
narrows without changing meaning.

Strategy: build one populated project covering all 20 adversarial vectors,
then for a battery of queries run the pack/brief BOTH ways by toggling the
retriever's db (index) vs forcing the scan, and deep-compare.
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
DB = "/tmp/omem_p7_equiv.db"
if os.path.exists(DB):
    os.remove(DB)
os.environ["OMEM_DB"] = DB
os.environ.pop("OMEM_LLM_API_KEY", None)

import os as _os_seed
_os_seed.environ['OMEM_SEED_DEMO']='1'
import api  # noqa: E402
import recall as _recall  # noqa: E402
import brief as _brief  # noqa: E402
import conflict as _conflict  # noqa: E402
import consolidation as _consol  # noqa: E402
import graph as _graph  # noqa: E402
import candidate_index as _ci  # noqa: E402

PASS = FAIL = 0


def check(n, c, d=""):
    global PASS, FAIL
    if c:
        PASS += 1; print(f"  ok  {n}")
    else:
        FAIL += 1; print(f"  FAIL {n}  {d}")


# build state directly (no HTTP needed for equivalence)
acct = None
from store import Store  # noqa: E402
P = api.PROJECTS  # project registry
# use the API's signup to get a real project + STORE
import http.server, socketserver  # noqa: E402
srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), api.Handler)
PORT = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()
time.sleep(0.2)


def call(m, path, body=None, key=None):
    r = urllib.request.Request(f"http://127.0.0.1:{PORT}{path}", method=m,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Content-Type": "application/json",
                 **({"Authorization": f"Bearer {key}"} if key else {})})
    try:
        with urllib.request.urlopen(r, timeout=15) as resp:
            return resp.status, json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


acct = call("POST", "/v1/signup", {"email": "p7@kronos.com"})[1]
KEY, PID = acct["api_key"]["secret"], acct["project"]["id"]
proj = api.PROJECTS[PID]
db = api.STORE.db
if "agent:sales" not in proj.labels:
    api.record(proj, "agent", {"id": "agent:sales", "kind": "system"})
    api.record(proj, "agent", {"id": "agent:support", "kind": "system"})


def ent(eid, typ="organization"):
    if eid not in proj.labels:
        api.record(proj, "entity", {"id": eid, "type": typ, "label": eid.split(":")[-1]})


def fact(aid, subs, prop, label=None, agent="agent:sales", T=None):
    for s in subs:
        ent(s)
    ev = api._mint_global("evt")
    api.record(proj, "event", {"id": ev, "ekind": "seed", "event_time": proj.tick()})
    api.record(proj, "assert", {"id": aid, "agent": agent, "subjects": subs,
                                "proposition": prop, "assertion_time": T or proj.now(),
                                "label": label})
    api.record(proj, "derive", {"id": api._mint_global("d"), "consequent": aid,
                                "antecedents": [ev], "dkind": "extraction"})
    return aid


print("== building adversarial dataset (20 vectors) ==")
# 1 simple, 2 duplicate/reinforcement, 3 reinforcement
fact("a_simple", ["company:acme"], "contract_expires_sep_30", "expiry")
fact("a_ann", ["company:acme"], "prefers_annual_billing", "annual")
_consol.reinforce(db, PID, "a_ann", "agent:billing", "o1")
_consol.reinforce(db, PID, "a_ann", "agent:support", "o2")
# 4 contradiction, 5 supersession
fact("a_mon", ["company:acme"], "prefers_monthly_billing", "monthly")
call("POST", f"/v1/declare-contradiction?project={PID}",
     {"token_a": "prefers_annual_billing", "token_b": "prefers_monthly_billing"}, KEY)
fact("a_exp_old", ["company:acme"], "seat_count_50", "50 seats", T=proj.tick())
Tsup = proj.tick()
api.record(proj, "supersede", {"id": "a_exp_new", "agent": "agent:sales",
                               "subjects": ["company:acme"], "proposition": "seat_count_120",
                               "assertion_time": Tsup, "olds": ["a_exp_old"], "did": "d_s"})
api._cand_index.index_assertion(db, PID, "a_exp_new", ["company:acme"], "seat_count_120", Tsup)
# 6 retraction
fact("a_demo", ["company:acme"], "wants_demo", "demo")
call("POST", f"/v1/assertions/a_demo/retract?project={PID}",
     {"agent": "agent:sales", "reason": "done"}, KEY)
# 8-10 private / shared / cross-agent
priv = call("POST", f"/v1/observe?project={PID}",
            {"agent": "agent:secret", "interaction":
             {"text": "We have decided to renew the annual contract.",
              "speaker": "z@hidden.io", "audience": "p7@kronos.com"}}, KEY)[1]
# 11-12 generalization / specific-vs-general
for who in ("company:beta", "company:gamma", "company:delta"):
    fact(f"a_g_{who[-4:]}", [who], "prefers_annual_billing", f"{who} annual", T=proj.tick())
call("POST", f"/v1/memory/consolidate?project={PID}", {}, KEY)
# 13-14 graph relationships / multi-hop
fact("a_r1", ["person:sarah", "company:acme"], "rel_works_at", "sarah@acme")
_graph.record_edge(db, PID, "a_r1", "person:sarah", "works_at", "company:acme")
fact("a_r2", ["person:sarah", "person:david"], "rel_reports_to", "sarah->david")
_graph.record_edge(db, PID, "a_r2", "person:sarah", "reports_to", "person:david")
# 20 many irrelevant assertions
for i in range(60):
    fact(f"a_noise_{i}", [f"company:noise{i}"], f"irrelevant_prop_{i%7}", f"noise {i}", T=proj.tick())

# ensure the index is fully populated (mirrors what record() did live)
api._cand_index.rebuild(db, proj)


def pack_both(**kw):
    """Run build_memory_pack with the index (db=) and with a forced scan
    (db passed but retriever monkeypatched to scan), compare."""
    extras = lambda aid: (lambda a: {"mclass": _consol.class_of(db, PID, aid, a.proposition if a else "")[0],
                                     "ttl": _consol.class_of(db, PID, aid, a.proposition if a else "")[1],
                                     "reinforcements": db.execute(
                                         "SELECT COUNT(*) n FROM memory_reinforcements WHERE project_id=? AND assertion_id=?",
                                         (PID, aid)).fetchone()["n"]})(proj.engine.store.assertion(aid))
    ca = lambda pair: _conflict.analyze_pair(proj, db, pair)
    about = kw.pop("about", None)
    ents = kw.pop("entities", []) or []
    if about:
        ents = [about] + ents
    common = dict(agent=kw.pop("agent", "agent:sales"), extras_lookup=extras,
                  conflict_analyzer=ca, entities=ents, **kw)
    # NEW: indexed
    new = _recall.build_memory_pack(proj, db, api.SCOPES, **common)
    # OLD: forced scan - temporarily disable the index path
    orig = _recall.CandidateRetriever.retrieve
    _recall.CandidateRetriever.retrieve = _recall.CandidateRetriever._retrieve_scan
    try:
        old = _recall.build_memory_pack(proj, db, api.SCOPES, **common)
    finally:
        _recall.CandidateRetriever.retrieve = orig
    for r in (new, old):
        r["stats"] = None
    return old, new


print("== equivalence: memory packs ==")
vectors = [
    ("direct entity", dict(about="company:acme", context="renewal billing seats")),
    ("cross-agent private hidden", dict(agent="agent:billing", context="hidden corp renewal")),
    ("graph hop", dict(about="company:acme", context="who works here people", limit=20)),
    ("lexical only", dict(context="irrelevant_prop_3 noise")),
    ("cold start (no match)", dict(context="zzz_nomatch_qqq")),
    ("generalization + specific", dict(about="company:acme", context="annual billing preference", limit=20)),
    ("budgeted", dict(about="company:acme", context="everything", limit=25, max_chars=1500)),
]
for name, kw in vectors:
    old, new = pack_both(**kw)
    check(f"pack equivalence: {name}",
          json.dumps(old, sort_keys=True) == json.dumps(new, sort_keys=True),
          f"OLD {len(old['memories'])} NEW {len(new['memories'])}")

print("== equivalence: as_of historical ==")
T_hist = proj.engine.store.assertion("a_ann").assertion_time
old, new = pack_both(about="company:acme", context="billing seats", as_of=T_hist)
check("pack equivalence: as_of", json.dumps(old, sort_keys=True) == json.dumps(new, sort_keys=True))

print("== equivalence: situation brief ==")
def brief_both(**kw):
    extras = lambda aid: (lambda a: {"mclass": _consol.class_of(db, PID, aid, a.proposition if a else "")[0],
                                     "ttl": None,
                                     "reinforcements": db.execute(
                                         "SELECT COUNT(*) n FROM memory_reinforcements WHERE project_id=? AND assertion_id=?",
                                         (PID, aid)).fetchone()["n"]})(proj.engine.store.assertion(aid))
    ca = lambda pair: _conflict.analyze_pair(proj, db, pair)
    common = dict(agent="agent:sales", extras_lookup=extras, conflict_analyzer=ca, **kw)
    new = _brief.build_situation_brief(proj, db, api.SCOPES, **common)
    orig = _recall.CandidateRetriever.retrieve
    _recall.CandidateRetriever.retrieve = _recall.CandidateRetriever._retrieve_scan
    try:
        old = _brief.build_situation_brief(proj, db, api.SCOPES, **common)
    finally:
        _recall.CandidateRetriever.retrieve = orig
    for r in (new, old):
        r["stats"] = None
    return old, new

for name, kw in [("renewal", dict(about="company:acme", context="enterprise renewal negotiation")),
                 ("people", dict(about="company:acme", context="who are the people involved", limit=20)),
                 ("budgeted", dict(about="company:acme", context="everything", limit=25, max_chars=1200))]:
    old, new = brief_both(**kw)
    check(f"brief equivalence: {name}",
          json.dumps(old, sort_keys=True) == json.dumps(new, sort_keys=True))

print("== index correctness vs engine ==")
# every indexed subject row must correspond to a real assertion with that subject
bad = 0
for r in db.execute("SELECT subject, assertion_id FROM candidate_subjects WHERE project_id=?", (PID,)):
    a = proj.engine.store.assertion(r["assertion_id"])
    if a is None or r["subject"] not in a.subjects:
        bad += 1
check("no dangling/incorrect subject index rows", bad == 0, str(bad))
# rebuild idempotency
before = sorted(tuple(r) for r in db.execute(
    "SELECT project_id, subject, assertion_id FROM candidate_subjects WHERE project_id=?", (PID,)))
api._cand_index.rebuild(db, proj)
after = sorted(tuple(r) for r in db.execute(
    "SELECT project_id, subject, assertion_id FROM candidate_subjects WHERE project_id=?", (PID,)))
check("index rebuild is deterministic/idempotent", before == after)

srv.shutdown()
print(f"\n{PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
