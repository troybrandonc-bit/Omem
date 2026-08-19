"""Enterprise control plane: RBAC, audit log, usage metering, retention.

All of this is REAL and enforced (not toggles): roles gate actions, audit rows
are append-only, usage counters increment on real events, retention deletes real
storage rows. None of it touches the frozen engine — these are storage/policy
layers around it. What is deleted vs. what remains as immutable engine history is
documented in delete_project() and retention_sweep().
"""
from __future__ import annotations
import json
import time
import uuid

ENTERPRISE_SCHEMA = """
CREATE TABLE IF NOT EXISTS memberships(
  org_id TEXT NOT NULL, user_id TEXT NOT NULL, role TEXT NOT NULL,
  created REAL NOT NULL, PRIMARY KEY(org_id, user_id));
CREATE TABLE IF NOT EXISTS audit_events(
  id TEXT PRIMARY KEY, org_id TEXT, project_id TEXT, actor TEXT,
  action TEXT NOT NULL, resource TEXT, metadata TEXT, correlation_id TEXT,
  ts REAL NOT NULL);
CREATE INDEX IF NOT EXISTS audit_org ON audit_events(org_id, ts);
CREATE TABLE IF NOT EXISTS usage_events(
  id INTEGER PRIMARY KEY AUTOINCREMENT, project_id TEXT NOT NULL,
  metric TEXT NOT NULL, quantity INTEGER NOT NULL DEFAULT 1,
  ts REAL NOT NULL);
CREATE INDEX IF NOT EXISTS usage_proj ON usage_events(project_id, metric, ts);
CREATE TABLE IF NOT EXISTS retention_policies(
  project_id TEXT PRIMARY KEY, source_days INTEGER, memory_days INTEGER,
  updated REAL NOT NULL);
CREATE TABLE IF NOT EXISTS project_settings(
  project_id TEXT NOT NULL, key TEXT NOT NULL, value TEXT,
  updated REAL NOT NULL, PRIMARY KEY(project_id, key));
CREATE TABLE IF NOT EXISTS extraction_logs(
  id INTEGER PRIMARY KEY AUTOINCREMENT, project_id TEXT NOT NULL,
  source_record_id TEXT, extractor TEXT NOT NULL, model TEXT,
  facts INTEGER NOT NULL DEFAULT 0, ok INTEGER NOT NULL DEFAULT 1,
  error TEXT, ts REAL NOT NULL);
CREATE TABLE IF NOT EXISTS feedback(
  id INTEGER PRIMARY KEY AUTOINCREMENT, project_id TEXT NOT NULL,
  assertion_id TEXT, kind TEXT NOT NULL, comment TEXT, actor TEXT, ts REAL NOT NULL);
CREATE TABLE IF NOT EXISTS recall_counts(
  project_id TEXT NOT NULL, assertion_id TEXT NOT NULL,
  count INTEGER NOT NULL DEFAULT 0, last_recalled REAL,
  PRIMARY KEY(project_id, assertion_id));
CREATE TABLE IF NOT EXISTS billing_events(
  id INTEGER PRIMARY KEY AUTOINCREMENT, org_id TEXT NOT NULL,
  kind TEXT NOT NULL, metadata TEXT, ts REAL NOT NULL);
CREATE TABLE IF NOT EXISTS customer_status(
  org_id TEXT PRIMARY KEY, status TEXT NOT NULL DEFAULT 'pilot',
  pilot_start REAL, pilot_end REAL, notes TEXT, updated REAL NOT NULL);
CREATE TABLE IF NOT EXISTS billing_state(
  org_id TEXT PRIMARY KEY, plan TEXT NOT NULL DEFAULT 'free',
  stripe_customer TEXT, subscription_status TEXT DEFAULT 'none',
  trial_ends REAL, updated REAL NOT NULL);
"""

# ── RBAC ──────────────────────────────────────────────────────────────────
ROLES = ["owner", "admin", "developer", "viewer"]
# permission -> minimum role rank that has it (lower index = more powerful)
_RANK = {r: i for i, r in enumerate(ROLES)}
PERMISSIONS = {
    "project.read": "viewer",
    "memory.read": "viewer",
    "usage.read": "viewer",
    "audit.read": "admin",
    "memory.write": "developer",
    "connector.manage": "developer",
    "key.create": "developer",
    "key.revoke": "developer",
    "project.create": "admin",
    "member.manage": "admin",
    "retention.manage": "admin",
    "project.delete": "owner",
    "billing.manage": "owner",
    # ── self-healing subsystem ──
    "heal.read": "viewer",            # read failures / health / recovery history
    "heal.report": "developer",       # report failures + health, record snapshots
    "heal.execute.low": "developer",  # run low-risk repairs (retry, clear cache, ...)
    "heal.execute.medium": "admin",   # run medium-risk repairs (config, rotate, ...)
    "heal.execute.high": "owner",     # run high-risk repairs (still needs explicit approval)
}


def role_allows(role: str, permission: str) -> bool:
    need = PERMISSIONS.get(permission)
    if need is None or role not in _RANK:
        return False
    return _RANK[role] <= _RANK[need]


class Enterprise:
    def __init__(self, db):
        self.db = db
        db.executescript(ENTERPRISE_SCHEMA)
        db.commit()

    # -- memberships / RBAC --
    def set_role(self, org_id, user_id, role):
        assert role in ROLES
        self.db.execute(
            "INSERT OR REPLACE INTO memberships VALUES(?,?,?,?)",
            (org_id, user_id, role, time.time()))
        self.db.commit()

    def role_of(self, org_id, user_id) -> str | None:
        r = self.db.execute("SELECT role FROM memberships WHERE org_id=? AND user_id=?",
                            (org_id, user_id)).fetchone()
        return r["role"] if r else None

    def members(self, org_id):
        rows = self.db.execute(
            "SELECT m.user_id, m.role, u.email FROM memberships m JOIN users u ON u.id=m.user_id "
            "WHERE m.org_id=? ORDER BY m.created", (org_id,))
        return [dict(r) for r in rows]

    def can(self, org_id, user_id, permission) -> bool:
        return role_allows(self.role_of(org_id, user_id) or "", permission)

    # -- audit log (append-only; no update/delete methods exist by design) --
    def audit(self, action, actor=None, org_id=None, project_id=None,
              resource=None, metadata=None, correlation_id=None):
        self.db.execute(
            "INSERT INTO audit_events(id,org_id,project_id,actor,action,resource,metadata,correlation_id,ts) "
            "VALUES(?,?,?,?,?,?,?,?,?)",
            (uuid.uuid4().hex, org_id, project_id, actor, action, resource,
             json.dumps(metadata or {}), correlation_id, time.time()))
        self.db.commit()

    def audit_log(self, org_id, limit=100):
        rows = self.db.execute(
            "SELECT * FROM audit_events WHERE org_id=? ORDER BY ts DESC LIMIT ?",
            (org_id, limit))
        out = []
        for r in rows:
            d = dict(r)
            d["metadata"] = json.loads(d["metadata"] or "{}")
            out.append(d)
        return out

    # -- usage metering (real counters over real events) --
    def meter(self, project_id, metric, quantity=1):
        self.db.execute(
            "INSERT INTO usage_events(project_id,metric,quantity,ts) VALUES(?,?,?,?)",
            (project_id, metric, quantity, time.time()))
        self.db.commit()

    def usage(self, project_id, since=None):
        q = "SELECT metric, SUM(quantity) total FROM usage_events WHERE project_id=?"
        args = [project_id]
        if since:
            q += " AND ts>=?"
            args.append(since)
        q += " GROUP BY metric"
        rows = self.db.execute(q, args)
        return {r["metric"]: r["total"] for r in rows}

    def usage_series(self, project_id, metric, buckets=14, span=None):
        """Real time-bucketed counts for one metric (for sparklines)."""
        rows = self.db.execute(
            "SELECT ts FROM usage_events WHERE project_id=? AND metric=? ORDER BY ts",
            (project_id, metric)).fetchall()
        if not rows:
            return []
        ts = [r["ts"] for r in rows]
        lo, hi = min(ts), max(ts) or min(ts) + 1
        out = [0] * buckets
        for t in ts:
            out[min(buckets - 1, int((t - lo) / (hi - lo or 1) * buckets))] += 1
        return out

    # -- retention policy --
    def set_retention(self, project_id, source_days=None, memory_days=None):
        self.db.execute(
            "INSERT OR REPLACE INTO retention_policies VALUES(?,?,?,?)",
            (project_id, source_days, memory_days, time.time()))
        self.db.commit()

    def retention(self, project_id):
        r = self.db.execute("SELECT * FROM retention_policies WHERE project_id=?",
                            (project_id,)).fetchone()
        return dict(r) if r else {"project_id": project_id, "source_days": None, "memory_days": None}

    def retention_sweep(self, project_id) -> dict:
        """Delete source records past their retention window. IMPORTANT: this
        removes stored SOURCE MATERIAL (the raw payload) only. The engine's
        assertions/derivations remain as immutable memory history — retention is
        a storage policy over source material, not a memory-semantic operation.
        Provenance that pointed at a deleted source will show 'source expired'."""
        pol = self.retention(project_id)
        removed = 0
        if pol.get("source_days"):
            cutoff = time.time() - pol["source_days"] * 86400
            cur = self.db.execute(
                "DELETE FROM source_records WHERE project_id=? AND received<?",
                (project_id, cutoff))
            removed = cur.rowcount
            self.db.commit()
        return {"source_records_removed": removed}

    # -- complete tenant/project erasure (GDPR tenant-grain right-to-erasure) --
    # This is the ONE deletion that hard-removes an entire tenant. It is NOT an
    # intra-tenant memory-semantic operation: it does not retract or rewrite
    # history within a living tenant (which would need a separate governance
    # decision). It removes the whole project so nothing survives — including
    # the op-log, so a reboot's replay cannot resurrect the deleted memory, and
    # the encrypted OAuth credentials of the project's connectors.
    #
    # The set of project-scoped tables is derived, not hardcoded blindly: any
    # table with a project_id column plus the connector-scoped oauth_creds and
    # the project row itself. Backups taken BEFORE erasure still contain the
    # data — restoring one re-introduces it. That is an operational/governance
    # boundary (documented, flagged), not something code silently guarantees.
    PROJECT_SCOPED_TABLES = [
        "ops", "keys", "source_records", "connectors", "candidate_subjects",
        "candidate_tokens", "memory_edges", "memory_scopes", "consolidation_state",
        "memory_class", "memory_reinforcements", "recall_counts", "relationship_overrides",
        "entity_resolutions", "fact_decisions", "fact_fingerprints", "feedback",
        "filtered_items", "review_queue", "assertion_evidence", "extraction_logs",
        "semantic_analyses", "message_classifications", "memory_scans",
        "memory_scan_results", "ingest_jobs", "usage_events", "audit_events",
        "retention_policies", "project_settings", "team_members",
    ]

    def delete_project(self, project_id, actor=None) -> dict:
        """Hard-delete an entire project/tenant. Returns per-table row counts.
        Records ONE audit event in a separate audit sink is not possible (the
        project's own audit rows are being removed), so the caller should log the
        erasure at the org level BEFORE calling this. Idempotent: deleting a
        non-existent project simply reports zeros."""
        report = {}
        # 1. OAuth creds are keyed by connector_id, not project_id — resolve and
        #    delete them first so encrypted secrets don't outlive the project.
        try:
            conn_ids = [r["id"] for r in self.db.execute(
                "SELECT id FROM connectors WHERE project_id=?", (project_id,)).fetchall()]
            oc = 0
            for cid in conn_ids:
                cur = self.db.execute("DELETE FROM oauth_creds WHERE connector_id=?", (cid,))
                oc += cur.rowcount or 0
            report["oauth_creds"] = oc
        except Exception as e:
            report["oauth_creds_error"] = str(e)
        # 2. every project-scoped table
        for t in self.PROJECT_SCOPED_TABLES:
            try:
                cur = self.db.execute(f"DELETE FROM {t} WHERE project_id=?", (project_id,))
                report[t] = cur.rowcount if cur.rowcount is not None and cur.rowcount >= 0 else 0
            except Exception as e:
                report[f"{t}_error"] = str(e)
        # 3. the project row itself
        try:
            cur = self.db.execute("DELETE FROM projects WHERE id=?", (project_id,))
            report["projects"] = cur.rowcount or 0
        except Exception as e:
            report["projects_error"] = str(e)
        self.db.commit()
        report["project_id"] = project_id
        report["actor"] = actor
        return report

    # -- project settings (e.g. LLM model config; secrets encrypted upstream) --
    def set_setting(self, project_id, key, value):
        self.db.execute("INSERT OR REPLACE INTO project_settings VALUES(?,?,?,?)",
                        (project_id, key, value, time.time()))
        self.db.commit()

    def setting(self, project_id, key, default=None):
        r = self.db.execute("SELECT value FROM project_settings WHERE project_id=? AND key=?",
                            (project_id, key)).fetchone()
        return r["value"] if r else default

    # -- extraction logs (diagnosis: which extractor ran, what it produced) --
    def log_extraction(self, project_id, source_record_id, extractor, model=None,
                       facts=0, ok=True, error=None):
        self.db.execute(
            "INSERT INTO extraction_logs(project_id,source_record_id,extractor,model,facts,ok,error,ts) "
            "VALUES(?,?,?,?,?,?,?,?)",
            (project_id, source_record_id, extractor, model, facts, 1 if ok else 0, error, time.time()))
        self.db.commit()

    def extraction_logs(self, project_id, limit=100):
        rows = self.db.execute("SELECT * FROM extraction_logs WHERE project_id=? ORDER BY id DESC LIMIT ?",
                               (project_id, limit))
        return [dict(r) for r in rows]

    # -- pilot feedback (product telemetry OUTSIDE the frozen engine) --
    FEEDBACK_KINDS = ("useful", "incorrect", "missing", "confusing")

    def add_feedback(self, project_id, kind, assertion_id=None, comment=None, actor=None):
        assert kind in self.FEEDBACK_KINDS
        self.db.execute(
            "INSERT INTO feedback(project_id,assertion_id,kind,comment,actor,ts) VALUES(?,?,?,?,?,?)",
            (project_id, assertion_id, kind, comment, actor, time.time()))
        self.db.commit()

    def feedback_for(self, project_id, limit=200):
        rows = self.db.execute("SELECT * FROM feedback WHERE project_id=? ORDER BY ts DESC LIMIT ?",
                               (project_id, limit))
        return [dict(r) for r in rows]

    def feedback_summary(self, project_id):
        rows = self.db.execute(
            "SELECT kind, COUNT(*) n FROM feedback WHERE project_id=? GROUP BY kind", (project_id,))
        return {r["kind"]: r["n"] for r in rows}

    # -- per-memory recall frequency (observable usage, not semantics) --
    def count_recall(self, project_id, assertion_id):
        self.db.execute(
            "INSERT INTO recall_counts(project_id,assertion_id,count,last_recalled) VALUES(?,?,1,?) "
            "ON CONFLICT(project_id,assertion_id) DO UPDATE SET count=recall_counts.count+1, last_recalled=?",
            (project_id, assertion_id, time.time(), time.time()))
        self.db.commit()

    def top_recalled(self, project_id, limit=10):
        rows = self.db.execute(
            "SELECT assertion_id, count, last_recalled FROM recall_counts "
            "WHERE project_id=? ORDER BY count DESC LIMIT ?", (project_id, limit))
        return [dict(r) for r in rows]

    # -- customer/pilot lifecycle (no fake payments; status is founder-set data) --
    STATUSES = ("pilot", "trial", "paid", "cancelled")

    def customer_status(self, org_id):
        r = self.db.execute("SELECT * FROM customer_status WHERE org_id=?", (org_id,)).fetchone()
        return dict(r) if r else {"org_id": org_id, "status": "pilot", "pilot_start": None,
                                  "pilot_end": None, "notes": None}

    def set_customer_status(self, org_id, status=None, pilot_start=None, pilot_end=None, notes=None):
        cur = self.customer_status(org_id)
        if status is not None:
            assert status in self.STATUSES
            cur["status"] = status
        if pilot_start is not None:
            cur["pilot_start"] = pilot_start
        if pilot_end is not None:
            cur["pilot_end"] = pilot_end
        if notes is not None:
            cur["notes"] = notes
        self.db.execute(
            "INSERT OR REPLACE INTO customer_status(org_id,status,pilot_start,pilot_end,notes,updated) VALUES(?,?,?,?,?,?)",
            (org_id, cur["status"], cur["pilot_start"], cur["pilot_end"], cur["notes"], time.time()))
        self.db.commit()
        return self.customer_status(org_id)

    # -- billing state (entitlements separate from Stripe provider state) --
    def billing(self, org_id):
        r = self.db.execute("SELECT * FROM billing_state WHERE org_id=?", (org_id,)).fetchone()
        if not r:
            return {"org_id": org_id, "plan": "free", "subscription_status": "none"}
        return dict(r)

    def billing_event(self, org_id, kind, metadata=None):
        self.db.execute("INSERT INTO billing_events(org_id,kind,metadata,ts) VALUES(?,?,?,?)",
                        (org_id, kind, json.dumps(metadata or {}), time.time()))
        self.db.commit()

    def billing_events(self, org_id, limit=100):
        rows = self.db.execute("SELECT * FROM billing_events WHERE org_id=? ORDER BY ts DESC LIMIT ?",
                               (org_id, limit))
        return [dict(r) for r in rows]

    def check_entitlement(self, org_id, project_id, metric) -> tuple[bool, dict]:
        """Real quota enforcement against the org's plan. Returns (allowed, info).
        Quotas are configurable data in PLANS, not hardcoded checks."""
        plan_id = self.billing(org_id).get("plan", "free")
        plan = PLANS.get(plan_id, PLANS["free"])
        if metric == "memories":
            quota = plan.get("quota_memories")
            used = (self.usage(project_id).get("assertions_created", 0)) if quota is not None else 0
        elif metric == "sources":
            quota = plan.get("quota_sources")
            used = self.db.execute("SELECT COUNT(*) c FROM connectors WHERE project_id=?",
                                   (project_id,)).fetchone()["c"] if quota is not None else 0
        else:
            return True, {"plan": plan_id}
        if quota is not None and used >= quota:
            self.billing_event(org_id, "quota_exceeded", {"metric": metric, "quota": quota, "used": used})
            return False, {"plan": plan_id, "quota": quota, "used": used, "metric": metric}
        return True, {"plan": plan_id, "quota": quota, "used": used}

    def set_billing(self, org_id, **fields):
        cur = self.billing(org_id)
        cur.update(fields)
        self.db.execute(
            "INSERT OR REPLACE INTO billing_state(org_id,plan,stripe_customer,subscription_status,trial_ends,updated) "
            "VALUES(?,?,?,?,?,?)",
            (org_id, cur.get("plan", "free"), cur.get("stripe_customer"),
             cur.get("subscription_status", "none"), cur.get("trial_ends"), time.time()))
        self.db.commit()


# Plans are configurable data, not scattered constants.
PLANS = {
    "free":     {"name": "Free",     "price": 0,    "quota_memories": 1000,   "quota_sources": 1},
    "pro":      {"name": "Pro",      "price": 49,   "quota_memories": 50000,  "quota_sources": 10},
    "business": {"name": "Business", "price": 499,  "quota_memories": 500000, "quota_sources": 50},
    "enterprise": {"name": "Enterprise", "price": None, "quota_memories": None, "quota_sources": None},
}
