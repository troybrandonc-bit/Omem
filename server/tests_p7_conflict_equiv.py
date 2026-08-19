"""P7 narrow-conflict equivalence. Run: python3 tests_p7_conflict_equiv.py

Proves conflict_narrow.conflicts_for(engine, candidates, T) returns EXACTLY
the same pairs as filtering the full engine.conflicts(T) to those candidates —
across every semantic situation. If they ever differ, the narrow path is
wrong and must not ship. The engine's own conflicts(T) is the oracle.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
DB = "/tmp/omem_p7_confeq.db"
if os.path.exists(DB):
    os.remove(DB)
os.environ["OMEM_DB"] = DB
os.environ.pop("OMEM_LLM_API_KEY", None)

import os as _os_seed
_os_seed.environ['OMEM_SEED_DEMO']='1'
import api  # noqa: E402
import conflict_narrow as _cn  # noqa: E402

PASS = FAIL = 0


def check(n, c, d=""):
    global PASS, FAIL
    if c:
        PASS += 1; print(f"  ok  {n}")
    else:
        FAIL += 1; print(f"  FAIL {n}  {d}")


acct = api.STORE  # noqa
P = None
for _p in api.PROJECTS.values():
    P = _p
    break
# fresh project
import types  # noqa
pid = api._mint_global("proj")


def new_project():
    # use the signup path so the project is fully wired
    import json
    return None


# simplest: operate on the default demo project's engine directly
P = list(api.PROJECTS.values())[0]
E = P.engine


def ent(eid, typ="entity"):
    if eid not in P.labels:
        api.record(P, "entity", {"id": eid, "type": typ})


def agent(aid):
    if aid not in P.labels:
        api.record(P, "agent", {"id": aid, "kind": "system"})


def assert_(aid, subs, prop, T=None):
    for s in subs:
        ent(s)
    agent("agent:t")
    api.record(P, "assert", {"id": aid, "agent": "agent:t", "subjects": subs,
                             "proposition": prop, "assertion_time": T or P.tick()})
    return aid


def declare(a, b):
    api.record(P, "declare", {"token_a": a, "token_b": b})


def oracle(candidates, T):
    """Ground truth: full engine conflicts filtered to the candidate set."""
    cset = set(candidates)
    return {pair for pair in E.conflicts(T) if pair & cset}


def compare(label, candidates, T=None):
    T = T if T is not None else P.now()
    got = _cn.conflicts_for(E, candidates, T)
    want = oracle(candidates, T)
    check(label, got == want, f"narrow={sorted(map(sorted, got))} full={sorted(map(sorted, want))}")


print("== no conflicts ==")
assert_("a_n1", ["company:x1"], "prefers_annual")
assert_("a_n2", ["company:x2"], "prefers_monthly")
compare("no declared contradiction -> no pairs", ["a_n1", "a_n2"])

print("== one conflict, same subject ==")
assert_("a_c1", ["company:y"], "prefers_annual")
assert_("a_c2", ["company:y"], "prefers_monthly")
declare("prefers_annual", "prefers_monthly")
compare("single same-subject conflict", ["a_c1", "a_c2"])
compare("querying only ONE side still finds the pair", ["a_c1"])
compare("querying the other side finds it too", ["a_c2"])

print("== declared contradiction but DIFFERENT subjects (no engine conflict) ==")
assert_("a_d1", ["company:z1"], "prefers_annual")
assert_("a_d2", ["company:z2"], "prefers_monthly")
compare("different subjects -> not a conflict (engine semantics)", ["a_d1", "a_d2"])

print("== multiple conflicting propositions / multiple subjects ==")
assert_("a_m1", ["company:w"], "uses_sf")
assert_("a_m2", ["company:w"], "uses_hs")
assert_("a_m3", ["company:w"], "uses_oracle")
declare("uses_sf", "uses_hs")
declare("uses_sf", "uses_oracle")
declare("uses_hs", "uses_oracle")
compare("three-way mutual conflict, all candidates", ["a_m1", "a_m2", "a_m3"])
compare("three-way, single candidate", ["a_m2"])
compare("mixed candidate set across subjects", ["a_c1", "a_m1", "a_m3", "a_n1"])

print("== supersession ==")
Tn = P.tick()
api.record(P, "supersede", {"id": "a_c1b", "agent": "agent:t", "subjects": ["company:y"],
                            "proposition": "prefers_biennial", "assertion_time": Tn,
                            "olds": ["a_c1"], "did": "d_sup"})
compare("after supersession: old side closed, conflict gone", ["a_c1", "a_c2", "a_c1b"])
# but historically it still conflicts
T_hist = None
a_hist = E.store.assertion("a_c1")
compare("as_of before supersession: conflict still present",
        ["a_c1", "a_c2"], T=a_hist.assertion_time)

print("== retraction ==")
assert_("a_r1", ["company:r"], "prefers_annual")
assert_("a_r2", ["company:r"], "prefers_monthly")
rid = api._mint_global("a")
api.record(P, "retract", {"id": rid, "agent": "agent:t", "subjects": ["company:r"],
                          "assertion_time": P.tick(), "old": "a_r1", "did": api._mint_global("d")})
compare("retracted side removed from conflicts", ["a_r1", "a_r2"])

print("== multiple agents, same referent ==")
agent("agent:b")
ent("company:ag")
api.record(P, "assert", {"id": "a_ag1", "agent": "agent:t", "subjects": ["company:ag"],
                         "proposition": "prefers_annual", "assertion_time": P.tick()})
api.record(P, "assert", {"id": "a_ag2", "agent": "agent:b", "subjects": ["company:ag"],
                         "proposition": "prefers_monthly", "assertion_time": P.tick()})
compare("cross-agent conflict on same subject", ["a_ag1", "a_ag2"])

print("== generalization / cohort subjects ==")
for c in ("company:g1", "company:g2", "company:g3"):
    assert_(f"a_gg_{c[-2:]}", [c], "prefers_annual", T=P.tick())
api.record(P, "entity", {"id": "cohort:prefers_annual", "type": "cohort"})
api.record(P, "assert", {"id": "a_gen", "agent": "agent:t",
                         "subjects": ["cohort:prefers_annual"],
                         "proposition": "pattern_prefers_annual", "assertion_time": P.tick()})
compare("generalization included as candidate, no spurious conflict",
        ["a_gen", "a_gg_g1", "a_gg_g2"])

print("== full-project spot check: every candidate matches the oracle ==")
allids = [a.id for a in E.store.assertions()]
compare("ALL assertions as candidates == full conflicts()", allids)
# and the inverse: narrow over all candidates must equal the ENTIRE conflicts()
got_all = _cn.conflicts_for(E, allids, P.now())
check("narrow-over-all reproduces the entire engine.conflicts() set",
      got_all == E.conflicts(P.now()),
      f"n_narrow={len(got_all)} n_full={len(E.conflicts(P.now()))}")

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

print(f"\n{PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
