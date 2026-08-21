"""P3 memory intelligence: reinforcement, classes, consolidation, why-chains.

Everything here is ABOVE the frozen engine. The engine remains the only
authority on belief state; this layer tracks EVIDENCE STRUCTURE (what supports
what, who reinforced what, what generalized from what) and proposes
generalizations through the engine's own ops.

Hierarchy implemented:
    EXPERIENCE      raw interaction (observe/gmail source)
    OBSERVATION     structured extraction with evidence (existing formation)
    FACT            engine assertion (existing)
    REINFORCEMENT   memory_reinforcements rows: repeated compatible
                    observations support ONE fact instead of duplicating it;
                    cross-agent, with the reinforcing agent recorded
    RELATIONSHIP    facts whose class is 'relational' (works_at_*, uses_*)
    PATTERN/GENERALIZED  an engine assertion by agent:omem-consolidation whose
                    DERIVATION antecedents are the supporting assertions.
                    Provenance is engine-native, never a metadata claim

"Supported by N observations" is a count of real rows. No confidence numbers
are invented anywhere: the frozen model defines none, so this layer reports
counts and timestamps, not fabricated certainty.

──────────────────────────────────────────────────────────────────────────────
P3 GENERALIZATION POLICY (explicit, intelligence-layer policy, NOT normative
OMEM semantics; documented here because the frozen model does not define one):

  A proposition P generalizes into `pattern_P` on subject `cohort:P` only if:
  1. EVIDENCE      >= MIN_SUBJECTS (3) OPEN assertions of P exist. Three is
                   the smallest count where "several independent entities"
                   is defensible; one or two is coincidence.
  2. DIVERSITY     the supporters cover >= MIN_SUBJECTS DISTINCT subject
                   entities (restatements about one entity never generalize).
  3. TEMPORALITY   supporters span >= 2 distinct assertion times (a single
                   batch import is one event, not a pattern).
  4. SCOPE         every supporter is org-visible. Agent-/team-/user-private
                   knowledge NEVER leaks into shared generalizations.
  5. CONTRADICTION if a declared-contradiction counterpart Q has supporters
                   amounting to >= half of P's, no generalization forms: the
                   organisation's experience is genuinely split.
  6. BOUNDS        at most MAX_NEW_PER_RUN (20) new generalizations per run,
                   deterministic order (proposition ascending).

  Idempotency: consolidation_state keys each generalization by proposition
  and stores the fingerprint of its supporting set. Re-running with unchanged
  state does nothing; new supporters become reinforcements of the existing
  generalization (never a duplicate); if supporters fall below policy the
  generalization is RETRACTED through the engine (history preserved).
──────────────────────────────────────────────────────────────────────────────
"""
from __future__ import annotations
import hashlib
import json
import time

MIN_SUBJECTS = 3
MIN_DISTINCT_TIMES = 2
MAX_NEW_PER_RUN = 20
MAX_SUPPORT_ANTECEDENTS = 20
CONSOLIDATION_AGENT = "agent:omem-consolidation"

P3_SCHEMA = """
CREATE TABLE IF NOT EXISTS memory_reinforcements(
  id INTEGER PRIMARY KEY AUTOINCREMENT, project_id TEXT NOT NULL,
  assertion_id TEXT NOT NULL, observed_by TEXT NOT NULL,
  source TEXT, ts REAL NOT NULL);
CREATE INDEX IF NOT EXISTS reinf_assertion
  ON memory_reinforcements(project_id, assertion_id);
CREATE TABLE IF NOT EXISTS memory_class(
  project_id TEXT NOT NULL, assertion_id TEXT NOT NULL,
  mclass TEXT NOT NULL, ttl REAL, created REAL NOT NULL,
  PRIMARY KEY(project_id, assertion_id));
CREATE TABLE IF NOT EXISTS consolidation_state(
  project_id TEXT NOT NULL, key TEXT NOT NULL,
  assertion_id TEXT NOT NULL, support_fp TEXT NOT NULL,
  support_count INTEGER NOT NULL, support_ids TEXT NOT NULL,
  ts REAL NOT NULL,
  PRIMARY KEY(project_id, key));
"""

MEMORY_CLASSES = ("transient", "episodic", "semantic", "relational", "generalized")

_RELATIONAL_HINTS = ("works_at_", "uses_", "managed_by_", "integration_",
                     "partner_of_", "reports_to_")


def classify_proposition(prop: str) -> str:
    """Default memory class for a proposition. Explicit rows override."""
    if prop.startswith("pattern_"):
        return "generalized"
    if any(h in prop for h in _RELATIONAL_HINTS):
        return "relational"
    return "semantic"


def reinforce(db, project_id: str, assertion_id: str, observed_by: str,
              source: str | None = None):
    """One more independent observation supports an existing fact."""
    db.execute("INSERT INTO memory_reinforcements(project_id, assertion_id, "
               "observed_by, source, ts) VALUES(?,?,?,?,?)",
               (project_id, assertion_id, observed_by, source, time.time()))
    db.commit()


def reinforcement_rows(db, project_id: str, assertion_id: str) -> list[dict]:
    return [dict(r) for r in db.execute(
        "SELECT observed_by, source, ts FROM memory_reinforcements "
        "WHERE project_id=? AND assertion_id=? ORDER BY id", (project_id, assertion_id))]


def set_class(db, project_id: str, assertion_id: str, mclass: str,
              ttl: float | None = None):
    if mclass not in MEMORY_CLASSES:
        raise ValueError(f"unknown memory class {mclass!r}")
    db.execute("INSERT OR REPLACE INTO memory_class VALUES(?,?,?,?,?)",
               (project_id, assertion_id, mclass, ttl, time.time()))
    db.commit()


def class_of(db, project_id: str, assertion_id: str, prop: str) -> tuple[str, float | None]:
    r = db.execute("SELECT mclass, ttl FROM memory_class WHERE project_id=? AND assertion_id=?",
                   (project_id, assertion_id)).fetchone()
    if r:
        return r["mclass"], r["ttl"]
    return classify_proposition(prop), None


def _canon(prop: str) -> str:
    from extraction import canonical_proposition
    return canonical_proposition(prop)


def _contradiction_counterparts(p, prop: str) -> set[str]:
    """Declared counterparts of a proposition, read defensively from the
    engine's registry (never modified here)."""
    for attr in ("contradiction_pairs", "contradictions", "_contradictions"):
        reg = getattr(p.engine, attr, None) or getattr(getattr(p.engine, "canon", None), attr, None)
        if reg:
            out = set()
            try:
                for pair in reg:
                    a, b = tuple(pair)[:2]
                    if a == prop:
                        out.add(b)
                    if b == prop:
                        out.add(a)
                return out
            except Exception:
                continue
    return set()


def consolidate(p, db, scopes, record, mint, contradictions=None) -> dict:
    """One deterministic, idempotent consolidation pass. Real counts only."""
    T = p.now()
    # 1. gather open, org-visible facts grouped by canonical proposition
    scope_map = scopes.bulk(p.id)
    groups: dict[str, list] = {}
    for a in p.engine.store.assertions():
        if a.agent == CONSOLIDATION_AGENT or a.proposition.startswith("pattern_"):
            continue
        try:
            if not p.engine.ledger.is_open_at(a, T):
                continue
        except Exception:
            continue
        if scope_map.get(a.id, "org") != "org":
            continue  # POLICY 4: private knowledge never generalizes
        groups.setdefault(_canon(a.proposition), []).append(a)

    result = {"examined_propositions": len(groups), "generalizations_created": 0,
              "generalizations_reinforced": 0, "generalizations_retracted": 0,
              "skipped_insufficient": 0, "skipped_contradicted": 0,
              "unchanged": 0, "details": []}

    created = 0
    for prop in sorted(groups):
        support = groups[prop]
        by_subject: dict[str, object] = {}
        for a in sorted(support, key=lambda x: (x.assertion_time, x.id)):
            for s in a.subjects:
                by_subject.setdefault(s, a)
        supporters = sorted({a.id for a in by_subject.values()})
        subjects = sorted(by_subject)
        # TEMPORAL DIVERSITY: prefer event_time (when the supporting events
        # actually happened) and fall back to assertion_time when no event
        # time is known. Since P8 distinguishes event_time from assertion_time,
        # this preserves the original "not one batch" intent - which was
        # event-time diversity before the two fields were split.
        def _when(a):
            et = getattr(a, "event_time", None)
            return et if et is not None else a.assertion_time
        times = {_when(by_subject[s]) for s in subjects}
        state = db.execute(
            "SELECT * FROM consolidation_state WHERE project_id=? AND key=?",
            (p.id, prop)).fetchone()

        qualifies = (len(subjects) >= MIN_SUBJECTS
                     and len(times) >= MIN_DISTINCT_TIMES)
        declared = set()
        for pair in (contradictions or []):
            a2, b2 = tuple(pair)[:2]
            if a2 == prop:
                declared.add(b2)
            if b2 == prop:
                declared.add(a2)
        declared |= _contradiction_counterparts(p, prop)
        if qualifies:
            for q in declared:
                q_support = {s for a in groups.get(q, []) for s in a.subjects}
                if len(q_support) * 2 >= len(subjects):
                    qualifies = False  # POLICY 5: experience genuinely split
                    result["skipped_contradicted"] += 1
                    break

        fp = hashlib.sha256("|".join(supporters).encode()).hexdigest()[:16]

        if state is None:
            if not qualifies:
                result["skipped_insufficient"] += 1 if not any(
                    d.get("prop") == prop for d in result["details"]) else 0
                continue
            if created >= MAX_NEW_PER_RUN:
                continue  # POLICY 6: bounded per run
            cohort = f"cohort:{prop}"
            if cohort not in p.labels:
                record(p, "entity", {"id": cohort, "type": "cohort",
                                     "label": f"entities sharing {prop}"})
            if CONSOLIDATION_AGENT not in p.labels:
                record(p, "agent", {"id": CONSOLIDATION_AGENT, "kind": "system",
                                    "label": "OMEM consolidation"})
            gid = mint("a")
            record(p, "assert", {
                "id": gid, "agent": CONSOLIDATION_AGENT, "subjects": [cohort],
                "proposition": f"pattern_{prop}", "assertion_time": p.tick(),
                "label": f"Pattern: {len(subjects)} entities independently show {prop}"})
            record(p, "derive", {"id": mint("d"), "consequent": gid,
                                 "antecedents": supporters[:MAX_SUPPORT_ANTECEDENTS],
                                 "dkind": "generalization"})
            scopes.set(p.id, gid, "org", granted_by=CONSOLIDATION_AGENT)
            set_class(db, p.id, gid, "generalized")
            db.execute("INSERT OR IGNORE INTO consolidation_state VALUES(?,?,?,?,?,?,?)",
                       (p.id, prop, gid, fp, len(supporters),
                        json.dumps(supporters), time.time()))
            db.commit()
            created += 1
            result["generalizations_created"] += 1
            result["details"].append({"prop": prop, "action": "created",
                                      "generalization": gid, "supporters": len(supporters)})
            continue

        gid = state["assertion_id"]
        g = p.engine.store.assertion(gid)
        g_open = g is not None and p.engine.ledger.is_open_at(g, T)
        if not qualifies:
            if g_open:
                # POLICY: evidence no longer supports the pattern -> engine
                # retraction; canonical history preserved
                record(p, "retract", {"id": mint("a"), "agent": CONSOLIDATION_AGENT,
                                      "subjects": list(g.subjects),
                                      "assertion_time": p.tick(),
                                      "old": gid, "did": mint("d")})
                db.execute("UPDATE consolidation_state SET support_fp=?, support_count=?, "
                           "support_ids=?, ts=? WHERE project_id=? AND key=?",
                           (fp, len(supporters), json.dumps(supporters), time.time(), p.id, prop))
                db.commit()
                result["generalizations_retracted"] += 1
                result["details"].append({"prop": prop, "action": "retracted",
                                          "generalization": gid})
            else:
                result["unchanged"] += 1
            continue
        if state["support_fp"] == fp:
            result["unchanged"] += 1
            continue
        # supporters changed but pattern still holds: new evidence reinforces
        # the EXISTING generalization - never a duplicate assertion
        old_ids = set(json.loads(state["support_ids"] or "[]"))
        for new_id in [s for s in supporters if s not in old_ids]:
            na = p.engine.store.assertion(new_id)
            reinforce(db, p.id, gid, observed_by=(na.agent if na else CONSOLIDATION_AGENT),
                      source=new_id)
        db.execute("UPDATE consolidation_state SET support_fp=?, support_count=?, "
                   "support_ids=?, ts=? WHERE project_id=? AND key=?",
                   (fp, len(supporters), json.dumps(supporters), time.time(), p.id, prop))
        db.commit()
        result["generalizations_reinforced"] += 1
        result["details"].append({"prop": prop, "action": "reinforced",
                                  "generalization": gid, "supporters": len(supporters)})
    return result


def chain(p, db, assertion_id: str) -> dict | None:
    """The flagship "why do you know this?" trace: belief -> evidence ->
    reinforcements -> generalizations, every hop from real state."""
    a = p.engine.store.assertion(assertion_id)
    if a is None:
        return None
    T = p.now()
    prov_ids, grounded = p.engine.provenance(assertion_id)
    conflicts = []
    for pair in p.engine.conflicts(T):
        if assertion_id in pair:
            other = [x for x in pair if x != assertion_id][0]
            oa = p.engine.store.assertion(other)
            if oa is not None:
                conflicts.append({"assertion": other, "proposition": oa.proposition,
                                  "agent": oa.agent})
    generalized_into = [
        {"proposition": r["key"], "generalization": r["assertion_id"]}
        for r in db.execute("SELECT key, assertion_id, support_ids FROM consolidation_state "
                            "WHERE project_id=?", (p.id,))
        if assertion_id in json.loads(r["support_ids"] or "[]")]
    mclass, ttl = class_of(db, p.id, assertion_id, a.proposition)
    label_meta = p.labels.get(assertion_id)
    return {
        "assertion": assertion_id,
        "content": (label_meta.get("label") if isinstance(label_meta, dict) else None)
                   or f"{', '.join(sorted(a.subjects))}: {a.proposition}",
        "subjects": sorted(a.subjects),
        "proposition": a.proposition,
        "state_now": p.engine.proposition_state(list(a.subjects), a.proposition, T),
        "currently_believed": bool(p.engine.ledger.is_open_at(a, T)),
        "learned_by": a.agent,
        "learned_at": a.assertion_time,
        "event_time": getattr(a, "event_time", None),
        "memory_class": mclass,
        "ttl": ttl,
        "reinforcements": reinforcement_rows(db, p.id, assertion_id),
        "provenance": {"ids": sorted(prov_ids), "grounded": grounded},
        "conflicts": conflicts,
        "generalized_into": generalized_into,
    }
