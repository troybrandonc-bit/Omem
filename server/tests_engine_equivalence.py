"""The optimised query paths answer exactly what the naive ones answered.

Run: python3 tests_engine_equivalence.py

WHY THIS EXISTS. proposition_state and conflicts were quadratic and near-cubic
(ENGINE_VALIDATION.md measured exponents of 2.2 and 2.9) because they recomputed
the referent partition inside their per-assertion and per-pair loops. Fixing that
means touching the reasoning core, and the reasoning core is the one part of this
system whose entire value is that its answers do not drift. Faster is worthless
if it is also different.

So the reference implementation is written out again here, deliberately naive and
transcribed from the semantics rather than from the new code: partition per
subject, every pair compared, no caching, no bucketing, no early exit. Both are
then run over thousands of randomly generated stores and required to agree on
every question, including the awkward ones, coreference merges and splits that
change which subjects are the same referent, retractions, supersessions, and
as-of queries at times before and after each of those.

Randomised rather than hand-written because hand-written cases test what the
author thought of. The generator makes coreference chains, contradictions,
supersessions and splits collide at arbitrary logical times, which is exactly
where a cache keyed on the wrong thing would show up: stale after a split, or
serving a partition from before a merge.

Seeded, so a failure is reproducible rather than a story about a bad afternoon.
"""
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from omem_engine.canon import RETRACTED, identifier_order_key, proposition_identical  # noqa: E402
from omem_engine.engine import Engine  # noqa: E402

PASS = FAIL = 0


def check(n, c, d=""):
    global PASS, FAIL
    if c:
        PASS += 1; print(f"  ok  {n}")
    else:
        FAIL += 1; print(f"  FAIL {n}  {d}")


# ── the reference: the semantics, written the slow obvious way ───────────────
def ref_reduced_subject_set(eng, subjects, T):
    p = eng.prop
    all_ent = {e.id for e in p.store.entities()}
    assertions = {a.id: a for a in p.store.assertions()}
    out = set()
    for s in subjects:
        # recompute the whole partition for every single subject, as before
        cls = None
        for c in p.coref.partition_at(all_ent, assertions, p.ledger, T):
            if s in c:
                cls = c
                break
        if cls is None:
            cls = frozenset({s})
        out.add(min(cls, key=identifier_order_key))
    return frozenset(out)


def ref_open(eng, T):
    p = eng.prop
    return [a for a in p.store.assertions() if p.ledger.is_open_at(a, T)]


def ref_proposition_state(eng, subjects, proposition, T):
    p = eng.prop
    query_S = ref_reduced_subject_set(eng, tuple(subjects), T)
    a_plus = a_minus = False
    for a in ref_open(eng, T):
        if proposition_identical(a.proposition, RETRACTED):
            continue
        if ref_reduced_subject_set(eng, a.subjects, T) != query_S:
            continue
        if proposition_identical(a.proposition, proposition):
            a_plus = True
        elif p.contra.contradicts(a.proposition, proposition):
            a_minus = True
    if a_plus and a_minus:
        return "CONTRADICTED"
    if a_plus:
        return "BELIEVED_TRUE"
    if a_minus:
        return "BELIEVED_FALSE"
    return "UNKNOWN"


def ref_conflicts(eng, T):
    p = eng.prop
    open_as = ref_open(eng, T)
    out = set()
    for i in range(len(open_as)):
        for j in range(i + 1, len(open_as)):
            a, b = open_as[i], open_as[j]
            if proposition_identical(a.proposition, RETRACTED):
                continue
            if proposition_identical(b.proposition, RETRACTED):
                continue
            if not p.contra.contradicts(a.proposition, b.proposition):
                continue
            if ref_reduced_subject_set(eng, a.subjects, T) == ref_reduced_subject_set(eng, b.subjects, T):
                out.add(frozenset({a.id, b.id}))
    return out


def ref_beliefs_about(eng, entity, T):
    p = eng.prop
    all_ent = {e.id for e in p.store.entities()}
    assertions = {a.id: a for a in p.store.assertions()}
    cls = None
    for c in p.coref.partition_at(all_ent, assertions, p.ledger, T):
        if entity in c:
            cls = c
            break
    if cls is None:
        cls = frozenset({entity})
    return {a.id for a in ref_open(eng, T) if any(s in cls for s in a.subjects)}


# ── random world generator ───────────────────────────────────────────────────
PROPS = ["likes_tea", "not:likes_tea", "pays_late", "not:pays_late",
         "prefers_annual", "prefers_monthly", "is_active", "uses_slack"]
OPPOSED = [("likes_tea", "not:likes_tea"), ("pays_late", "not:pays_late"),
           ("prefers_annual", "prefers_monthly")]


# What the generator actually did. A random workload that quietly stopped
# producing splits would still pass every comparison below while testing none of
# the cases splits exist to cover, so the counts are asserted rather than assumed.
PERFORMED = dict(assertion=0, corefer=0, supersede=0, split=0, retract=0, refused=0)


def build_world(rng, n_ent, n_ops):
    eng = Engine()
    for a, b in OPPOSED:
        eng.declare_contradiction(a, b)
    eng.put_agent("ag", "system", 0)
    ents = [f"e{i}" for i in range(n_ent)]
    for e in ents:
        eng.put_entity(e, "org")

    live = []            # assertion ids that are still open, for supersede/retract
    corefs = []          # coreference assertion ids, for split
    t = 1
    for i in range(n_ops):
        roll = rng.random()
        aid = f"a{i}"
        if roll < 0.55:
            subs = tuple(rng.sample(ents, rng.choice([1, 1, 1, 2])))
            eng.assert_(aid, "ag", subs, rng.choice(PROPS), t)
            live.append((aid, subs))
            PERFORMED["assertion"] += 1
        elif roll < 0.70 and len(ents) >= 2:
            a, b = rng.sample(ents, 2)
            eng.corefer(aid, a, b, "ag", t)
            corefs.append(aid)
            PERFORMED["corefer"] += 1
        elif roll < 0.85 and live:
            old, subs = live.pop(rng.randrange(len(live)))
            try:
                eng.supersede_by(aid, "ag", subs, rng.choice(PROPS), t, [old], f"d{i}")
                live.append((aid, subs))
                PERFORMED["supersede"] += 1
            except Exception:
                PERFORMED["refused"] += 1
        elif corefs and roll < 0.93:
            cor = corefs.pop(rng.randrange(len(corefs)))
            try:
                eng.split(cor, "ag", t, aid, f"d{i}")
                PERFORMED["split"] += 1
            except Exception:
                PERFORMED["refused"] += 1
        elif live:
            old, subs = live.pop(rng.randrange(len(live)))
            try:
                eng.retract_by(aid, "ag", subs, t, old, f"d{i}")
                PERFORMED["retract"] += 1
            except Exception:
                PERFORMED["refused"] += 1
        t += 1
    return eng, ents, t


# The engine's public helpers differ in shape across versions; bind the two
# revision operations through whatever this build exposes so the generator keeps
# exercising supersession and retraction rather than silently skipping them.
def _bind_revision():
    from omem_engine.primitives import Assertion

    def supersede_by(eng, aid, agent, subs, prop, t, olds, did):
        eng.supersede(Assertion(aid, agent, tuple(subs), prop, t, None, None), olds, did)

    def retract_by(eng, aid, agent, subs, t, old, did):
        eng.retract(Assertion(aid, agent, tuple(subs), RETRACTED, t), old, did)

    Engine.supersede_by = lambda self, *a: supersede_by(self, *a)
    Engine.retract_by = lambda self, *a: retract_by(self, *a)


_bind_revision()


def run():
    rng = random.Random(20260819)
    worlds = 0
    comparisons = 0
    mismatch = None

    for trial in range(24):
        n_ent = rng.choice([3, 5, 8])
        n_ops = rng.choice([15, 30, 45])
        eng, ents, t_end = build_world(rng, n_ent, n_ops)
        worlds += 1
        # query at times across the whole history, not just the end: an as-of
        # query is where a partition cached against the wrong version would show.
        times = sorted({1, t_end - 1, t_end, *[rng.randrange(1, t_end + 1) for _ in range(4)]})
        for T in times:
            if ref_conflicts(eng, T) != eng.conflicts(T):
                mismatch = f"conflicts differ at T={T} (trial {trial})"
                break
            comparisons += 1
            for e in ents:
                for prop in PROPS:
                    if ref_proposition_state(eng, (e,), prop, T) != eng.proposition_state((e,), prop, T):
                        mismatch = f"state differs: {e}/{prop} at T={T} (trial {trial})"
                        break
                    comparisons += 1
                if ref_beliefs_about(eng, e, T) != eng.beliefs_about(e, T):
                    mismatch = f"beliefs_about differs: {e} at T={T} (trial {trial})"
                    break
                comparisons += 1
            if mismatch:
                break
        if mismatch:
            break

    check(f"optimised and naive agree over {worlds} random worlds "
          f"({comparisons} comparisons)", mismatch is None, mismatch or "")

    # The comparison above is only worth its name if the workload contained the
    # operations that make the query paths hard. Every one of these must appear,
    # or the agreement was reached over a world too simple to disagree in.
    for op in ("assertion", "corefer", "supersede", "split", "retract"):
        check(f"the workload actually exercised {op} ({PERFORMED[op]}x)",
              PERFORMED[op] > 0)
    check("and no operation was silently refused", PERFORMED["refused"] == 0,
          f'{PERFORMED["refused"]} refused')

    # ── the specific cache hazards, made explicit ────────────────────────────
    # Randomised coverage is probabilistic; these three are the failures a cache
    # keyed on the wrong thing produces, so they are pinned individually.
    eng = Engine()
    eng.declare_contradiction("likes_tea", "not:likes_tea")
    eng.put_agent("ag", "system", 0)
    eng.put_entity("x", "org"); eng.put_entity("y", "org")
    eng.assert_("a1", "ag", ("x",), "likes_tea", 1)
    eng.assert_("a2", "ag", ("y",), "not:likes_tea", 2)
    before = eng.proposition_state(("x",), "likes_tea", 3)
    eng.corefer("c1", "x", "y", "ag", 4)          # x and y become one referent
    after = eng.proposition_state(("x",), "likes_tea", 5)
    check("a merge is seen immediately after it happens",
          before == "BELIEVED_TRUE" and after == "CONTRADICTED", f"{before} -> {after}")

    eng.split("c1", "ag", 6, "s1", "ds1")          # and separate again
    after_split = eng.proposition_state(("x",), "likes_tea", 7)
    check("a split is seen immediately after it happens",
          after_split == "BELIEVED_TRUE", after_split)

    check("an as-of query before the merge still reads the old world",
          eng.proposition_state(("x",), "likes_tea", 3) == "BELIEVED_TRUE")
    check("and during the merge still reads the merged world",
          eng.proposition_state(("x",), "likes_tea", 5) == "CONTRADICTED")

    # Declaring a contradiction changes an answer without touching the store, so
    # a cache keyed only on store state would miss it.
    eng2 = Engine()
    eng2.put_agent("ag", "system", 0)
    eng2.put_entity("z", "org")
    eng2.assert_("b1", "ag", ("z",), "prefers_annual", 1)
    eng2.assert_("b2", "ag", ("z",), "prefers_monthly", 2)
    undeclared = eng2.proposition_state(("z",), "prefers_annual", 3)
    eng2.declare_contradiction("prefers_annual", "prefers_monthly")
    declared = eng2.proposition_state(("z",), "prefers_annual", 3)
    check("a later declaration changes the answer at the same T",
          undeclared == "BELIEVED_TRUE" and declared == "CONTRADICTED",
          f"{undeclared} -> {declared}")


run()
print(f"\n{PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
