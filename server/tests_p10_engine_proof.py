"""P10. BLACK-BOX ENGINE PROOF. Run: python3 tests_p10_engine_proof.py

Independent validation of the frozen omem_engine/. Rules of this suite:
  * It drives the RAW engine (omem_engine.Engine) directly, no server, no SDK.
  * Expected outcomes are derived from FIRST PRINCIPLES (the documented four-valued
    semantics, half-open intervals, transitive-closure coreference, monotonic
    revision), NOT copied from the implementation. Where a expectation is the
    engine's own claim rather than an external ground truth, it is labelled.
  * It does not redefine expected behavior to make a test pass. A divergence is
    reported as a FAILURE or an UNKNOWN, never silently accommodated.

Categories: correctness, determinism, adversarial/conflicting inputs, edge cases,
scale characteristics, replay consistency, isolation boundaries.
"""
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from omem_engine.engine import Engine  # noqa: E402
from omem_engine.primitives import Assertion  # noqa: E402
from omem_engine import proposition as _prop  # noqa: E402
from omem_engine.canon import RETRACTED  # noqa: E402

PASS = FAIL = 0
UNKNOWNS = []


def check(n, c, d=""):
    global PASS, FAIL
    if c:
        PASS += 1; print(f"  ok  {n}")
    else:
        FAIL += 1; print(f"  FAIL {n}  {d}")


def unknown(n, note):
    UNKNOWNS.append((n, note))
    print(f"  ??  UNKNOWN: {n}, {note}")


def new_engine():
    e = Engine()
    return e


# ═══════════════════════════════════════════════════════════════════════════
print("== 1. CORRECTNESS: four-valued proposition_state from first principles ==")
# Ground truth by construction: with NO declared contradiction, an affirming
# assertion => BELIEVED_TRUE; nothing => UNKNOWN.
e = new_engine()
e.put_agent("agent:a", "human")
e.put_entity("co:x", "org")
e.assert_("a1", "agent:a", ["co:x"], "prefers_annual", 10)
check("single affirming assertion => BELIEVED_TRUE",
      e.proposition_state(["co:x"], "prefers_annual", 20) == "BELIEVED_TRUE")
check("unqueried proposition => UNKNOWN",
      e.proposition_state(["co:x"], "prefers_monthly", 20) == "UNKNOWN")

# A declared contradiction with BOTH sides asserted => CONTRADICTED (external truth:
# the model declared these tokens mutually exclusive, both are open, same subject).
e.declare_contradiction("prefers_annual", "prefers_monthly")
e.assert_("a2", "agent:a", ["co:x"], "prefers_monthly", 12)
check("both sides of a declared contradiction, same subject => CONTRADICTED",
      e.proposition_state(["co:x"], "prefers_annual", 20) == "CONTRADICTED")
check("the contradicted state is symmetric (query the other token) => CONTRADICTED",
      e.proposition_state(["co:x"], "prefers_monthly", 20) == "CONTRADICTED")
# only the DENYING side open => BELIEVED_FALSE. Close a1 by superseding it.
sup = Assertion("a3", "agent:a", ("co:x",), "prefers_monthly", 15)
e.supersede(sup, ["a1"], "d1")
# now at T=20: a1 closed, a2 (monthly) open, a3 (monthly) open; annual has no open
# affirmer, monthly denies annual => BELIEVED_FALSE for 'prefers_annual'
check("only denying side open => BELIEVED_FALSE",
      e.proposition_state(["co:x"], "prefers_annual", 20) == "BELIEVED_FALSE")

print("== 1b. contradiction is DECLARATION-ONLY (no text parsing) ==")
# External truth: two textually 'opposite-looking' tokens must NOT conflict unless
# declared. This is the core defensibility claim - the model cannot smuggle in a
# contradiction the CTS didn't declare.
e2 = new_engine()
e2.put_agent("ag", "human"); e2.put_entity("co", "org")
e2.assert_("x1", "ag", ["co"], "is_active", 1)
e2.assert_("x2", "ag", ["co"], "is_not_active", 2)   # looks opposite, NOT declared
check("undeclared 'opposite-looking' tokens do NOT contradict",
      e2.proposition_state(["co"], "is_active", 5) == "BELIEVED_TRUE")

# ═══════════════════════════════════════════════════════════════════════════
print("== 2. TEMPORAL / AS-OF: half-open interval [start, end) ==")
e = new_engine()
e.put_agent("ag", "human"); e.put_entity("co", "org")
e.assert_("b1", "ag", ["co"], "P", 10)
sup = Assertion("b2", "ag", ("co",), "Q", 20)
e.declare_contradiction("P", "Q")
e.supersede(sup, ["b1"], "d1")  # closes b1 at 20
# first-principles half-open expectations:
check("before start (T=9): UNKNOWN (assertion not yet open)",
      e.proposition_state(["co"], "P", 9) == "UNKNOWN")
check("at start (T=10): BELIEVED_TRUE (start is included)",
      e.proposition_state(["co"], "P", 10) == "BELIEVED_TRUE")
check("just before close (T=19): still BELIEVED_TRUE",
      e.proposition_state(["co"], "P", 19) == "BELIEVED_TRUE")
check("AT close bound (T=20): P is CLOSED (half-open excludes end) => not TRUE",
      e.proposition_state(["co"], "P", 20) != "BELIEVED_TRUE")
check("at close bound (T=20): Q now open => P BELIEVED_FALSE",
      e.proposition_state(["co"], "P", 20) == "BELIEVED_FALSE")

print("== 2b. monotonicity: a closed interval cannot be reopened (INV-4) ==")
e = new_engine()
e.put_agent("ag", "human"); e.put_entity("co", "org")
e.assert_("c1", "ag", ["co"], "P", 10)
e.supersede(Assertion("c2", "ag", ("co",), "R", 20), ["c1"], "d1")
raised = False
try:
    e.supersede(Assertion("c3", "ag", ("co",), "S", 30), ["c1"], "d2")  # re-close c1
except Exception:
    raised = True
check("second supersession of the same assertion is rejected (INV-4)", raised)

print("== 2c. supersession requires strictly-greater time (non-empty intervals) ==")
e = new_engine()
e.put_agent("ag", "human"); e.put_entity("co", "org")
e.assert_("d1a", "ag", ["co"], "P", 10)
raised = False
try:
    e.supersede(Assertion("d2a", "ag", ("co",), "R", 10), ["d1a"], "dd")  # equal time
except Exception:
    raised = True
check("supersession at EQUAL time rejected (no zero-length interval)", raised,
      "if this passes-through, intervals could be empty")

# ═══════════════════════════════════════════════════════════════════════════
print("== 3. COREFERENCE: transitive closure, confidence-independent ==")
e = new_engine()
for ent in ("e1", "e2", "e3", "e4"):
    e.put_entity(ent, "org")
e.put_agent("ag", "human")
# e1~e2, e2~e3  => {e1,e2,e3} one class; e4 singleton
e.corefer("cf1", "e1", "e2", "ag", 5)
e.corefer("cf2", "e2", "e3", "ag", 5)
part = {frozenset(c) for c in e.referent_partition(10)}
check("transitive closure merges e1~e2~e3 into one class",
      frozenset({"e1", "e2", "e3"}) in part)
check("unrelated entity stays a singleton", frozenset({"e4"}) in part)

# confidence must not change the partition (I-1): coref assertions carry no
# confidence in this API, but a low-confidence-looking extra coref must behave
# identically to a normal one - test that ANY open coref merges.
check("partition is a proper set-cover (every entity in exactly one class)",
      sum(len(c) for c in part) == 4 and len(set().union(*part)) == 4)

print("== 3b. coreference reduction makes same-referent conflicts detectable ==")
# External truth: if e1~e2, an assertion about e1 and a contradicting one about e2
# are about the SAME referent, so they must conflict.
e = new_engine()
e.put_agent("ag", "human")
e.put_entity("e1", "org"); e.put_entity("e2", "org")
e.declare_contradiction("P", "Q")
e.assert_("s1", "ag", ["e1"], "P", 10)
e.assert_("s2", "ag", ["e2"], "Q", 11)
check("no coreference yet: different subjects => NOT a conflict",
      e.proposition_state(["e1"], "P", 20) == "BELIEVED_TRUE")
e.corefer("cf", "e1", "e2", "ag", 12)
check("after e1~e2: P about e1 and Q about e2 => CONTRADICTED (same referent)",
      e.proposition_state(["e1"], "P", 20) == "CONTRADICTED")
# and a split must re-separate them
e.split("cf", "ag", 15, "spl", "dsplit")
check("after split: referents separate again => BELIEVED_TRUE",
      e.proposition_state(["e1"], "P", 20) == "BELIEVED_TRUE")

# ═══════════════════════════════════════════════════════════════════════════
print("== 4. RETRACTION: RETRACTED contributes to neither A+ nor A- (N10) ==")
e = new_engine()
e.put_agent("ag", "human"); e.put_entity("co", "org")
e.assert_("r1", "ag", ["co"], "P", 10)
e.retract(Assertion("r2", "ag", ("co",), RETRACTED, 20), "r1", "d1")
st = e.proposition_state(["co"], "P", 25)
check("after retraction, P is no longer BELIEVED_TRUE", st != "BELIEVED_TRUE", st)
# retraction should not fabricate a FALSE either (it withdraws, not denies)
check("retraction withdraws (UNKNOWN), does not assert FALSE",
      st == "UNKNOWN", f"got {st}, if BELIEVED_FALSE, retraction wrongly denies")

# ═══════════════════════════════════════════════════════════════════════════
print("== 5. DETERMINISM / REPLAY: identical op sequences => identical state ==")
def build(seed_order):
    e = new_engine()
    e.put_agent("ag", "human")
    for ent in ("a", "b", "c"):
        e.put_entity(ent, "org")
    e.declare_contradiction("P", "Q")
    ops = {
        "assert_pa": lambda: e.assert_("m1", "ag", ["a"], "P", 10),
        "assert_qa": lambda: e.assert_("m2", "ag", ["a"], "Q", 11),
        "coref_ab": lambda: e.corefer("m3", "a", "b", "ag", 5),
    }
    for k in seed_order:
        ops[k]()
    return e

# Same ops, DIFFERENT insertion order => the four-valued state at T must be equal
# (order-independence of the query result over the same open set).
e_order1 = build(["assert_pa", "assert_qa", "coref_ab"])
e_order2 = build(["coref_ab", "assert_qa", "assert_pa"])
s1 = e_order1.proposition_state(["a"], "P", 20)
s2 = e_order2.proposition_state(["a"], "P", 20)
check("proposition_state is insertion-order independent", s1 == s2, f"{s1} vs {s2}")

# reproducibility markers: identical canonical inputs => identical marker; a changed
# input => different marker.
m1 = e_order1.repro_marker(["m1", "m2"], 20, {"m1": 0.9, "m2": 0.8})
m2 = e_order2.repro_marker(["m2", "m1"], 20, {"m2": 0.8, "m1": 0.9})  # reordered input
check("repro_marker is input-order independent (canonical)", m1 == m2, f"{m1[:8]} {m2[:8]}")
m3 = e_order1.repro_marker(["m1", "m2"], 21, {"m1": 0.9, "m2": 0.8})  # different T
check("repro_marker changes when logical time changes", m1 != m3)
m4 = e_order1.repro_marker(["m1", "m2"], 20, {"m1": 0.7, "m2": 0.8})  # different conf
check("repro_marker changes when a confidence changes", m1 != m4)

print("== 5b. conflicts() equals the pairwise CONTRADICTED closure ==")
# External cross-check: the set of conflict pairs must be EXACTLY the open,
# same-referent, declared-contradictory pairs - computed here independently.
e = new_engine()
e.put_agent("ag", "human")
for ent in ("x", "y", "z"):
    e.put_entity(ent, "org")
e.declare_contradiction("P", "Q")
e.assert_("p1", "ag", ["x"], "P", 1)
e.assert_("p2", "ag", ["x"], "Q", 2)   # conflicts with p1 (same subject)
e.assert_("p3", "ag", ["y"], "P", 3)
e.assert_("p4", "ag", ["y"], "Q", 4)   # conflicts with p3
e.assert_("p5", "ag", ["z"], "P", 5)   # lonely, no conflict
engine_conflicts = {frozenset(pr) for pr in e.conflicts(100)}
# independent expectation
expected = {frozenset({"p1", "p2"}), frozenset({"p3", "p4"})}
check("conflicts() == independently-computed CONTRADICTED pairs",
      engine_conflicts == expected, f"engine={engine_conflicts} expected={expected}")

# ═══════════════════════════════════════════════════════════════════════════
print("== 6. ISOLATION: engine has no tenant/agent concept. Must be enforced ABOVE ==")
# Critical finding to VERIFY, not assume: the raw engine is a single memory space.
# Two 'agents' write about the same subject in ONE engine and both are visible -
# proving isolation is an API-layer responsibility, not an engine guarantee.
e = new_engine()
e.put_agent("agent:alice", "human"); e.put_agent("agent:bob", "human")
e.put_entity("co", "org")
e.assert_("al", "agent:alice", ["co"], "P", 10)
e.assert_("bo", "agent:bob", ["co"], "P", 11)
beliefs = e.beliefs_about("co", 20)
check("engine exposes BOTH agents' assertions about a shared subject (no engine-level privacy)",
      "al" in beliefs and "bo" in beliefs,
      "=> tenant/agent isolation is NOT an engine guarantee; it lives in the API layer")

# ═══════════════════════════════════════════════════════════════════════════
print("== 7. EDGE CASES ==")
e = new_engine()
e.put_agent("ag", "human"); e.put_entity("co", "org")
# empty subject set
try:
    st = e.proposition_state([], "P", 10)
    check("empty subject set is handled (returns a total state)", st in
          ("UNKNOWN", "BELIEVED_TRUE", "BELIEVED_FALSE", "CONTRADICTED"), st)
except Exception as ex:
    unknown("empty subject set", f"raised {type(ex).__name__}")
# query at T=0 and negative T
try:
    e.assert_("z1", "ag", ["co"], "P", 0)
    check("assertion at T=0 open at T=0 (start included)",
          e.proposition_state(["co"], "P", 0) == "BELIEVED_TRUE")
except Exception as ex:
    unknown("T=0 assertion", str(ex))
# self-coreference no-op (J-4)
e.corefer("selfcf", "co", "co", "ag", 1)
part = e.referent_partition(10)
check("self-coreference is a partition no-op (co still singleton-or-in-its-class)",
      any("co" in c for c in part))

# ═══════════════════════════════════════════════════════════════════════════
print("== 8. SCALE CHARACTERISTICS (measured, not claimed) ==")
import time as _t
def bench_conflicts(n):
    e = new_engine(); e.put_agent("ag", "human")
    e.declare_contradiction("P", "Q")
    for i in range(n):
        e.put_entity(f"e{i}", "org")
        e.assert_(f"a{i}", "ag", [f"e{i}"], "P" if i % 2 else "Q", i + 1)
    t0 = _t.perf_counter(); e.conflicts(n + 10); return _t.perf_counter() - t0
def bench_state(n):
    e = new_engine(); e.put_agent("ag", "human")
    for i in range(n):
        e.put_entity(f"e{i}", "org")
        e.assert_(f"a{i}", "ag", [f"e{i}"], "P", i + 1)
    t0 = _t.perf_counter()
    for _ in range(20):
        e.proposition_state(["e0"], "P", n + 10)
    return (_t.perf_counter() - t0) / 20
c100, c200, c400 = bench_conflicts(100), bench_conflicts(200), bench_conflicts(400)
print(f"  conflicts(): n=100 {c100*1000:.0f}ms  n=200 {c200*1000:.0f}ms  n=400 {c400*1000:.0f}ms")
ratio = (c400 / c200) if c200 else 0
print(f"  conflicts() growth 200->400 ratio = {ratio:.1f}x (linear~2x, quadratic~4x)")
# This check used to assert the OPPOSITE: that doubling the input more than
# tripled the time, confirming the near-cubic growth as a known scale risk. It
# was an honest characterisation of a real defect, and it failed the moment the
# defect was fixed, which is exactly what a characterisation test should do.
#
# Inverted rather than deleted, because the property is worth holding onto: the
# cost of conflicts() must stay close to the cost of the data. Doubling the
# assertions may not much more than double the work.
#
# The bound is 3x rather than 2x because this benchmark gives every assertion its
# own entity, so every open assertion lands in its own referent bucket and the
# measurement is dominated by per-assertion overhead and timer noise at these
# small sizes. A regression to the old behaviour would be ~4x and upwards.
check("conflicts() growth stays near-linear (ratio<=3)", ratio <= 3,
      f"ratio={ratio:.1f}. Above 3 means the per-pair partition recomputation is back")
s100, s400 = bench_state(100), bench_state(400)
print(f"  proposition_state single-query: n=100 {s100*1000:.1f}ms  n=400 {s400*1000:.1f}ms")
# Same reasoning for a single belief query, which was 2.2 in the log-log fit
# recorded in ENGINE_VALIDATION.md and is linear now.
_sratio = (s400 / s100) if s100 else 0
print(f"  proposition_state growth 100->400 ratio = {_sratio:.1f}x (linear~4x, quadratic~16x)")
check("proposition_state growth stays near-linear (ratio<=8)", _sratio <= 8,
      f"ratio={_sratio:.1f}. Above 8 means the per-subject partition recomputation is back")

print("== 9. ADVERSARIAL: attempts to BREAK the guarantees ==")
def _fresh():
    _e = new_engine(); _e.put_agent("ag", "human"); return _e
# cyclic coreference must terminate to a single class (no infinite loop)
e = _fresh()
for x in ("e1", "e2", "e3"):
    e.put_entity(x, "org")
e.corefer("c1", "e1", "e2", "ag", 1); e.corefer("c2", "e2", "e3", "ag", 1)
e.corefer("c3", "e3", "e1", "ag", 1)
check("cyclic coreference terminates to one class",
      frozenset({"e1", "e2", "e3"}) in {frozenset(c) for c in e.referent_partition(10)})
# re-assert after retract
e = _fresh(); e.put_entity("co", "org")
e.assert_("a1", "ag", ["co"], "P", 10)
e.retract(Assertion("a2", "ag", ("co",), RETRACTED, 20), "a1", "d1")
e.assert_("a3", "ag", ["co"], "P", 30)
check("re-assert after retract => BELIEVED_TRUE",
      e.proposition_state(["co"], "P", 40) == "BELIEVED_TRUE")
check("as-of BEFORE the retraction still sees the old belief",
      e.proposition_state(["co"], "P", 15) == "BELIEVED_TRUE")
# supersede a non-existent target must be rejected, not corrupt state
e = _fresh(); e.put_entity("co", "org")
raised = False
try:
    e.supersede(Assertion("s1", "ag", ("co",), "P", 10), ["ghost"], "d1")
except Exception:
    raised = True
check("supersede of a non-existent target is rejected", raised)
# a token declared to contradict ITSELF must be a no-op (not self-CONTRADICTED)
e = _fresh(); e.put_entity("co", "org")
e.declare_contradiction("P", "P")
e.assert_("a1", "ag", ["co"], "P", 10)
check("token declared to contradict itself stays BELIEVED_TRUE",
      e.proposition_state(["co"], "P", 20) == "BELIEVED_TRUE")
# provenance + grounding
e = _fresh(); e.put_entity("co", "org"); e.put_event("ev", "obs", 5)
e.assert_("a0", "ag", ["co"], "P", 10); e.derive("a0", ["ev"], "extraction", "d0")
prov, grounded = e.provenance("a0", 20)
check("provenance returns antecedents and a grounding verdict",
      "ev" in prov and grounded in ("GROUNDED", "UNGROUNDED", True, False))

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
check("frozen engine byte-identical (validation touched nothing)",
      all(baseline.get(f) == v for f, v in h.items()))

print(f"\n{PASS} passed, {FAIL} failed, {len(UNKNOWNS)} unknown")
sys.exit(1 if FAIL else 0)
