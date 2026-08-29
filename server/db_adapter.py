"""PostgreSQL adapter for the OMEM persistence layer.

Exposes the same API surface the codebase already uses on sqlite3
(execute / executescript / commit, rows addressable by name AND index,
lastrowid, rowcount), so store/ingest/enterprise/connectors run unchanged.
Selected when OMEM_DATABASE_URL is set (postgres://user:pass@host/db);
otherwise SQLite remains the development/test default.

The frozen engine is untouched: this adapts the SaaS storage layer only.
Engine state remains an append-only ops log replayed through the engine.

Translation performed:
- '?' placeholders          -> '%s'
- INTEGER PRIMARY KEY AUTOINCREMENT -> BIGSERIAL PRIMARY KEY
- REAL                      -> DOUBLE PRECISION
- INSERT OR REPLACE INTO t  -> INSERT ... ON CONFLICT (pk) DO UPDATE (pk map below)
- executescript             -> statement-by-statement execution

Transaction model (documented honestly): the adapter runs in autocommit, so
each statement is atomic (matching how the codebase uses sqlite: write+commit
per operation). Multi-statement transactions can be added via explicit BEGIN
blocks where needed; the append-only ops log makes single-statement atomicity
sufficient for engine-state correctness.
"""
from __future__ import annotations
import re
import threading

# primary keys for INSERT OR REPLACE translation
_UPSERT_PK = {
    "oauth_creds": ["connector_id"],
    "memberships": ["org_id", "user_id"],
    "retention_policies": ["project_id"],
    "billing_state": ["org_id"],
    "customer_status": ["org_id"],
    "recall_counts": ["project_id", "assertion_id"],
    "fact_fingerprints": ["project_id", "fingerprint"],
    "project_settings": ["project_id", "key"],
    "assertion_evidence": ["assertion_id"],
    "user_mfa": ["user_id"],
    # P3-P7 above-engine projections (all use INSERT OR REPLACE/IGNORE);
    # PKs mirror each table's own PRIMARY KEY declaration.
    "memory_scopes": ["project_id", "assertion_id"],
    "team_members": ["project_id", "team_id", "agent_id"],
    "memory_class": ["project_id", "assertion_id"],
    "consolidation_state": ["project_id", "key"],
    "memory_edges": ["project_id", "assertion_id"],
    "candidate_subjects": ["project_id", "subject", "assertion_id"],
    "candidate_tokens": ["project_id", "token", "assertion_id"],
    # relationship_overrides (P5-era) - PK is the composite below
    "relationship_overrides": ["project_id", "key_type", "key"],
    # source_records uses INSERT OR IGNORE with the UNIQUE(connector_id,
    # external_id) constraint as the conflict target (NOT the 'id' primary key)
    "source_records": ["connector_id", "external_id"],
    # identity resolution proposals (INSERT OR IGNORE keeps first-writer wins)
    "merge_proposals": ["project_id", "id"],
    # declared inference rules + their recorded conclusions
    "inference_rules": ["project_id", "id"],
    "rule_conclusions": ["project_id", "fp"],
    # declared relation constraints + the tensions they detect
    "relation_constraints": ["project_id", "id"],
    "constraint_tensions": ["project_id", "id"],
    # the intuition layer: hypotheses + per-generator learning record
    "hypotheses": ["project_id", "id"],
    "leap_generators": ["project_id", "generator"],
}


class Row:
    """sqlite3.Row-alike: index and key access + dict()/'in' support."""
    __slots__ = ("_cols", "_vals")

    def __init__(self, cols, vals):
        self._cols = cols
        self._vals = vals

    def __getitem__(self, k):
        if isinstance(k, int):
            return self._vals[k]
        return self._vals[self._cols.index(k)]

    def __contains__(self, k):
        return k in self._cols

    def keys(self):
        return list(self._cols)

    def __iter__(self):
        return iter(self._vals)

    def get(self, k, default=None):
        return self[k] if k in self._cols else default


def _dictable(row):
    return {c: row._vals[i] for i, c in enumerate(row._cols)}


# make dict(Row) work
Row.keys = Row.keys  # noqa
setattr(Row, "items", lambda self: list(_dictable(self).items()))


class _Result:
    """Cursor-result wrapper carrying rows + rowcount + lastrowid."""
    def __init__(self, rows, rowcount, lastrowid):
        self._rows = rows
        self.rowcount = rowcount
        self.lastrowid = lastrowid
        self._i = 0

    def fetchone(self):
        if self._i < len(self._rows):
            r = self._rows[self._i]
            self._i += 1
            return r
        return None

    def fetchall(self):
        rows = self._rows[self._i:]
        self._i = len(self._rows)
        return rows

    def __iter__(self):
        while True:
            r = self.fetchone()
            if r is None:
                return
            yield r


def translate(sql: str) -> str:
    # psycopg2 treats '%' as a placeholder marker, so any LITERAL percent (e.g.
    # LIKE 'abc%') must be doubled BEFORE '?' becomes '%s'. Doing it in the other
    # order would corrupt the placeholders we just inserted.
    out = sql.replace("%", "%%").replace("?", "%s")
    out = re.sub(r"INTEGER PRIMARY KEY AUTOINCREMENT", "BIGSERIAL PRIMARY KEY", out)
    out = re.sub(r"\bREAL\b", "DOUBLE PRECISION", out)
    m = re.match(r"\s*INSERT OR REPLACE INTO (\w+)", out, re.I)
    if m:
        table = m.group(1)
        pk = _UPSERT_PK.get(table)
        if pk is None:
            raise ValueError(f"INSERT OR REPLACE on unmapped table {table}")
        out = re.sub(r"INSERT OR REPLACE INTO", "INSERT INTO", out, flags=re.I)
        # build DO UPDATE SET for all columns (excluded.*)
        cols = _columns_of.get(table, [])
        setters = ", ".join(f"{c}=EXCLUDED.{c}" for c in cols if c not in pk) or f"{pk[0]}=EXCLUDED.{pk[0]}"
        out = out.rstrip().rstrip(";") + f" ON CONFLICT ({','.join(pk)}) DO UPDATE SET {setters}"
    mi = re.match(r"\s*INSERT OR IGNORE INTO (\w+)", out, re.I)
    if mi:
        table = mi.group(1)
        pk = _UPSERT_PK.get(table)
        if pk is None:
            raise ValueError(f"INSERT OR IGNORE on unmapped table {table}")
        out = re.sub(r"INSERT OR IGNORE INTO", "INSERT INTO", out, flags=re.I)
        out = out.rstrip().rstrip(";") + f" ON CONFLICT ({','.join(pk)}) DO NOTHING"
    return out


# column lists for upsert tables (kept in sync with schemas)
_columns_of = {
    "oauth_creds": ["connector_id", "provider", "access_token", "refresh_token", "expires", "scope", "account", "connected", "status"],
    "memberships": ["org_id", "user_id", "role", "created"],
    "retention_policies": ["project_id", "source_days", "memory_days", "updated"],
    "billing_state": ["org_id", "plan", "stripe_customer", "subscription_status", "trial_ends", "updated"],
    "customer_status": ["org_id", "status", "pilot_start", "pilot_end", "notes", "updated"],
    "recall_counts": ["project_id", "assertion_id", "count", "last_recalled"],
    "fact_fingerprints": ["project_id", "fingerprint", "assertion_id"],
    "project_settings": ["project_id", "key", "value", "updated"],
    "assertion_evidence": ["assertion_id", "project_id", "source_record_id", "evidence", "confidence", "extractor", "created"],
    "user_mfa": ["user_id", "secret", "enabled", "created"],
    # P3-P7 above-engine projection tables (column order matches CREATE TABLE)
    "memory_scopes": ["project_id", "assertion_id", "scope", "granted_by", "created"],
    "team_members": ["project_id", "team_id", "agent_id"],
    "memory_class": ["project_id", "assertion_id", "mclass", "ttl", "created"],
    "consolidation_state": ["project_id", "key", "assertion_id", "support_fp",
                            "support_count", "support_ids", "ts"],
    "memory_edges": ["project_id", "assertion_id", "src", "relation", "dst", "created"],
    "candidate_subjects": ["project_id", "subject", "assertion_id", "assertion_time"],
    "candidate_tokens": ["project_id", "token", "assertion_id", "assertion_time"],
    "relationship_overrides": ["project_id", "key_type", "key", "role", "source", "note", "ts"],
    "source_records": ["id", "project_id", "connector_id", "external_id", "payload",
                       "content_hash", "event_id", "received"],
    "merge_proposals": ["id", "project_id", "entity_a", "entity_b", "confidence",
                        "evidence", "support", "status", "created", "decided",
                        "decided_by", "coreference_id"],
    "inference_rules": ["id", "project_id", "when_a", "dir_a", "when_b", "dir_b",
                        "then_rel", "then_dir", "active", "created", "created_by"],
    "rule_conclusions": ["project_id", "fp", "rule_id", "assertion_id",
                         "premise_a", "premise_b", "created"],
    "relation_constraints": ["id", "project_id", "relation", "kind", "active",
                             "created", "created_by"],
    "constraint_tensions": ["id", "project_id", "constraint_id", "relation",
                            "entity", "holders", "fp", "status", "created",
                            "decided", "decided_by", "kept"],
    "hypotheses": ["id", "project_id", "subject", "proposition", "born_from",
                   "generator", "because", "strength", "status", "docket",
                   "passes", "fp", "created", "decided"],
    "leap_generators": ["project_id", "generator", "wins", "losses"],
}


class PgDB:
    """Postgres connection with the sqlite3-shaped API the codebase uses."""
    def __init__(self, url: str):
        try:
            import psycopg2
        except ModuleNotFoundError:
            raise SystemExit(
                "OMEM_DATABASE_URL is set, but the PostgreSQL driver is not installed.\n"
                "  pip install 'omem-infrastructure[postgres]'"
                "   (or: pip install psycopg2-binary)\n"
                "Unset OMEM_DATABASE_URL to use the SQLite default instead.")
        self._pg = psycopg2
        self.url = url
        self._lock = threading.Lock()  # serialize like sqlite's single connection
        self._conn = psycopg2.connect(url)
        self._conn.autocommit = True

    def execute(self, sql: str, params=()):
        tsql = translate(sql)
        with self._lock:
            cur = self._conn.cursor()
            try:
                cur.execute(tsql, tuple(params))
            except self._pg.Error:
                cur.close()
                raise
            rows = []
            lastrowid = None
            if cur.description is not None:
                cols = [d[0] for d in cur.description]
                rows = [Row(cols, list(v)) for v in cur.fetchall()]
            elif tsql.lstrip().upper().startswith("INSERT"):
                try:
                    c2 = self._conn.cursor()
                    c2.execute("SELECT lastval()")
                    lastrowid = c2.fetchone()[0]
                    c2.close()
                except self._pg.Error:
                    lastrowid = None  # no sequence used in this insert
            rc = cur.rowcount
            cur.close()
            return _Result(rows, rc, lastrowid)

    def executescript(self, script: str):
        for stmt in [s.strip() for s in script.split(";") if s.strip()]:
            self.execute(stmt)
        return None

    def commit(self):
        pass  # autocommit; statement-level atomicity (see module docstring)

    def close(self):
        self._conn.close()
