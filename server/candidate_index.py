"""P7 candidate index. Makes candidate generation an INDEXED LOOKUP instead
of a full scan of the engine's in-memory assertion map.

Strict boundary: the index only answers "which assertion ids MIGHT be
relevant?". It never decides belief state, scope, conflict, or ordering,
the engine and the decision layer remain authoritative. Every id the index
returns is re-validated against the engine (open state, scope) exactly as
before, so results are semantically identical to the scan path (proven by
tests_p7_equivalence.py).

Two projections, populated when an assertion is recorded (assert / supersede),
mirroring what CandidateRetriever computed on the fly:

    candidate_subjects(project_id, subject, assertion_id)
        one row per (subject, assertion), the 'entity' signal
    candidate_tokens(project_id, token, assertion_id)
        one row per (proposition token, assertion), the 'lexical' signal

Both are pure projections of assertion identity + subjects + proposition; they
carry no truth. Rebuildable from the engine at any time (rebuild()).
"""
from __future__ import annotations

INDEX_SCHEMA = """
CREATE TABLE IF NOT EXISTS candidate_subjects(
  project_id TEXT NOT NULL, subject TEXT NOT NULL, assertion_id TEXT NOT NULL,
  assertion_time INTEGER NOT NULL,
  PRIMARY KEY(project_id, subject, assertion_id));
CREATE INDEX IF NOT EXISTS cand_subj_lookup
  ON candidate_subjects(project_id, subject, assertion_time DESC);
CREATE TABLE IF NOT EXISTS candidate_tokens(
  project_id TEXT NOT NULL, token TEXT NOT NULL, assertion_id TEXT NOT NULL,
  assertion_time INTEGER NOT NULL,
  PRIMARY KEY(project_id, token, assertion_id));
CREATE INDEX IF NOT EXISTS cand_tok_lookup
  ON candidate_tokens(project_id, token, assertion_time DESC);
"""

# proposition tokens are split exactly as the scan path did: underscores->spaces
def _prop_tokens(prop: str) -> list[str]:
    return [t for t in (prop or "").replace("_", " ").split() if t]


def index_assertion(db, project_id: str, assertion_id: str, subjects, prop: str,
                    assertion_time: int):
    """Record the projection rows for one assertion. Idempotent (PK upsert)."""
    at = int(assertion_time)
    for s in subjects:
        db.execute("INSERT OR REPLACE INTO candidate_subjects VALUES(?,?,?,?)",
                   (project_id, s, assertion_id, at))
    for tok in set(_prop_tokens(prop)):
        db.execute("INSERT OR REPLACE INTO candidate_tokens VALUES(?,?,?,?)",
                   (project_id, tok, assertion_id, at))


def candidates_by_entities(db, project_id: str, entities, limit: int) -> list[str]:
    """Assertion ids whose subjects include any of these entities, newest
    first. Indexed: uses cand_subj_lookup."""
    if not entities:
        return []
    qmarks = ",".join("?" * len(entities))
    rows = db.execute(
        f"SELECT DISTINCT assertion_id, assertion_time FROM candidate_subjects "
        f"WHERE project_id=? AND subject IN ({qmarks}) "
        f"ORDER BY assertion_time DESC, assertion_id LIMIT ?",
        (project_id, *entities, limit)).fetchall()
    return [r["assertion_id"] for r in rows]


def candidates_by_tokens(db, project_id: str, tokens, limit: int) -> list[str]:
    """Assertion ids whose proposition shares any of these tokens, newest
    first. Indexed: uses cand_tok_lookup."""
    toks = [t for t in tokens if t]
    if not toks:
        return []
    qmarks = ",".join("?" * len(toks))
    rows = db.execute(
        f"SELECT DISTINCT assertion_id, assertion_time FROM candidate_tokens "
        f"WHERE project_id=? AND token IN ({qmarks}) "
        f"ORDER BY assertion_time DESC, assertion_id LIMIT ?",
        (project_id, *toks, limit)).fetchall()
    return [r["assertion_id"] for r in rows]


def newest(db, project_id: str, limit: int) -> list[str]:
    """Cold-start recency window (only used when nothing else matched)."""
    rows = db.execute(
        "SELECT assertion_id, MAX(assertion_time) at FROM candidate_subjects "
        "WHERE project_id=? GROUP BY assertion_id ORDER BY at DESC, assertion_id LIMIT ?",
        (project_id, limit)).fetchall()
    return [r["assertion_id"] for r in rows]


def rebuild(db, p) -> dict:
    """Rebuild both projections from the engine. Restart/repair path; the
    index is disposable and always reconstructable from engine truth."""
    db.execute("DELETE FROM candidate_subjects WHERE project_id=?", (p.id,))
    db.execute("DELETE FROM candidate_tokens WHERE project_id=?", (p.id,))
    n = 0
    for a in p.engine.store.assertions():
        index_assertion(db, p.id, a.id, a.subjects, a.proposition, a.assertion_time)
        n += 1
    db.commit()
    return {"indexed_assertions": n}
