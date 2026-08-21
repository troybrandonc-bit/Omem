"""P8 partition-reuse equivalence. Run: python3 tests_p8_partition_equiv.py

Proves partition_view.PartitionView answers proposition_state and
reduced_subject_set BYTE-IDENTICALLY to the frozen engine's own per-call
methods, across every semantic situation. The engine is the oracle; if the
cached view ever differs it must not ship.
"""
import os
import sys
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
DB = "/tmp/omem_p8_peq.db"
if os.path.exists(DB):
    os.remove(DB)
os.environ["OMEM_DB"] = DB
os.environ.pop("OMEM_LLM_API_KEY", None)

import os as _os_seed
_os_seed.environ['OMEM_SEED_DEMO']='1'
import api  # noqa: E402
from partition_view import PartitionView  # noqa: E402

PASS = FAIL = 0


def check(n, c, d=""):
    global PASS, FAIL
    if c:
        PASS += 1; print(f"  ok  {n}")
    else:
        FAIL += 1; print(f"  FAIL {n}  {d}")


# Own project, not whatever happens to be first in PROJECTS.
#
# On SQLite this suite gets a fresh OMEM_DB tempfile, so the first project is
# always its own. On PostgreSQL OMEM_DATABASE_URL wins, the tempfile is
# ignored, and the first project is a leftover that already contains this
# suite's hardcoded assertion ids ("a_r", "a_m1", ...) from the previous run.
# Replay then re-adds them and the engine rejects the duplicate with
# R_MUTATION: id already recorded.
#
# A brand-new project id has no ops to replay, so its Engine starts empty and
# the fixed ids below are unique within it on either backend.
_PID = "proj_peq_" + uuid.uuid4().hex[:10]
P = api.Project(_PID, "partition-equivalence suite", "development", "org_test")
api.PROJECTS[_PID] = P
api.CONTRADICTIONS[_PID] = []
api._DECLARED_PAIRS[_PID] = set()
E = P.engine
if "agent:t" not in P.labels:
    api.record(P, "agent", {"id": "agent:t", "kind": "system"})
if "agent:b" not in P.labels:
    api.record(P, "agent", {"id": "agent:b", "kind": "system"})


def ent(eid, typ="entity"):
    if eid not in P.labels:
        api.record(P, "entity", {"id": eid, "type": typ})


def assert_(aid, subs, prop, agent="agent:t", T=None):
    for s in subs:
        ent(s)
    api.record(P, "assert", {"id": aid, "agent": agent, "subjects": subs,
                             "proposition": prop, "assertion_time": T or P.tick()})
    return aid


def compare_state(label, subjects, prop, T=None):
    T = T if T is not None else P.now()
    want = E.proposition_state(list(subjects), prop, T)
    got = PartitionView(E, T).proposition_state(list(subjects), prop)
    check(label, got == want, f"view={got} engine={want}")


def compare_rss(label, subjects, T=None):
    T = T if T is not None else P.now()
    want = E.prop._reduced_subject_set(tuple(subjects), T)
    got = PartitionView(E, T).reduced_subject_set(tuple(subjects))
    check(label, got == want, f"view={sorted(got)} engine={sorted(want)}")


print("== simple states ==")
assert_("a1", ["company:a"], "prefers_annual")
compare_state("BELIEVED_TRUE", ["company:a"], "prefers_annual")
compare_state("UNKNOWN (never asserted)", ["company:a"], "prefers_monthly")
compare_state("UNKNOWN (unknown subject)", ["company:zzz"], "prefers_annual")

print("== contradiction / CONTRADICTED / BELIEVED_FALSE ==")
assert_("a2", ["company:a"], "prefers_monthly")
api.record(P, "declare", {"token_a": "prefers_annual", "token_b": "prefers_monthly"})
compare_state("CONTRADICTED (both open)", ["company:a"], "prefers_annual")
compare_state("CONTRADICTED symmetric", ["company:a"], "prefers_monthly")
assert_("a3", ["company:b"], "prefers_monthly")
compare_state("BELIEVED_FALSE (only opposing side)", ["company:b"], "prefers_annual")

print("== supersession / as_of ==")
T_before = P.now()
Tn = P.tick()
ent("company:a")
api.record(P, "supersede", {"id": "a1b", "agent": "agent:t", "subjects": ["company:a"],
                            "proposition": "prefers_biennial", "assertion_time": Tn,
                            "olds": ["a1"], "did": "d1"})
compare_state("after supersede: old prop UNKNOWN/false now", ["company:a"], "prefers_annual")
compare_state("as_of before supersede: old state intact", ["company:a"], "prefers_annual", T=T_before)
compare_state("new prop true now", ["company:a"], "prefers_biennial")

print("== retraction ==")
assert_("a_r", ["company:r"], "prefers_annual")
rid = api._mint_global("a")
api.record(P, "retract", {"id": rid, "agent": "agent:t", "subjects": ["company:r"],
                          "assertion_time": P.tick(), "old": "a_r", "did": api._mint_global("d")})
compare_state("retracted prop no longer true", ["company:r"], "prefers_annual")

print("== multi-agent same referent ==")
ent("company:m")
api.record(P, "assert", {"id": "a_m1", "agent": "agent:t", "subjects": ["company:m"],
                         "proposition": "prefers_annual", "assertion_time": P.tick()})
api.record(P, "assert", {"id": "a_m2", "agent": "agent:b", "subjects": ["company:m"],
                         "proposition": "prefers_monthly", "assertion_time": P.tick()})
compare_state("cross-agent contradiction", ["company:m"], "prefers_annual")

print("== coreference: reduced subject sets ==")
ent("person:bob"); ent("person:robert")
# corefer bob == robert, then their subject sets should reduce equally
api.record(P, "corefer", {"id": api._mint_global("cor"), "entity_a": "person:bob",
                          "entity_b": "person:robert", "agent": "agent:t",
                          "assertion_time": P.tick()})
compare_rss("coreferent singletons reduce equally A", ["person:bob"])
compare_rss("coreferent singletons reduce equally B", ["person:robert"])
compare_rss("multi-subject reduced set", ["person:bob", "company:m"])
# a proposition about bob vs about robert -> same referent
api.record(P, "assert", {"id": "a_bob", "agent": "agent:t", "subjects": ["person:bob"],
                         "proposition": "is_lead", "assertion_time": P.tick()})
compare_state("state queried via coreferent alias", ["person:robert"], "is_lead")

print("== many-subject stress: full parity over all assertions ==")
for i in range(30):
    assert_(f"a_s{i}", [f"company:s{i}"], f"prop_{i%5}", T=P.tick())
T = P.now()
pv = PartitionView(E, T)
mismatch = 0
for a in E.store.assertions():
    if E.proposition_state(list(a.subjects), a.proposition, T) != \
            pv.proposition_state(list(a.subjects), a.proposition):
        mismatch += 1
check("full-project parity: every assertion's state matches", mismatch == 0, f"{mismatch} mismatches")

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
