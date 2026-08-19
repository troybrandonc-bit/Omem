"""OMEM self-healing subsystem — infrastructure for agent self-repair.

This is OMEM capability, not per-agent application logic. It provides the memory
(failures, diagnoses, recovery history), the safety boundary (policy + risk
classes + capability registry), the concurrency control (atomic claim), and the
lifecycle (detect -> capture -> diagnose -> plan -> policy -> execute -> verify ->
record -> rollback/retry -> escalate). The LLM is a *reasoning* component that may
PROPOSE a plan; OMEM decides what is permitted, safe, and executable, and whether
it actually succeeded.

Design invariants:
  * Retrieved memory and error text are DATA, never instructions. An error string
    cannot select or invent an executable action.
  * Only registered action handlers execute. No shell, eval, or dynamic import.
  * Risk classes gate execution; high-risk never auto-executes.
  * One active recovery per (project, component) via atomic claim.
  * Fingerprint idempotency + finite budget prevent repair loops/storms.
  * Every persisted context is redacted of secrets.
  * Every row is scoped by org_id + project_id (tenant isolation).
  * Fails closed: an internal error records + escalates, never self-retries wild.

Stdlib only. Reuses store.py (durable tables + atomic claim), enterprise.py
(RBAC + audit). It invents no memory semantics in the engine.
"""
from __future__ import annotations
import hashlib
import json
import re
import time
import uuid

# ── risk classes ────────────────────────────────────────────────────────────
RISK_LOW, RISK_MEDIUM, RISK_HIGH = "low", "medium", "high"
_RISK_RANK = {RISK_LOW: 0, RISK_MEDIUM: 1, RISK_HIGH: 2}

# recovery state machine
S_FAILED, S_CLAIMED, S_DIAGNOSING, S_REPAIRING, S_VERIFYING, S_RECOVERED, S_ESCALATED = (
    "failed", "claimed", "diagnosing", "repairing", "verifying", "recovered", "escalated")

SEVERITIES = ("info", "warning", "error", "critical")
HEALTH_STATES = ("healthy", "degraded", "failed", "recovering", "unknown")

# hard safety limits
MAX_ATTEMPTS_PER_FINGERPRINT = 3      # same strategy for same failure signature
MAX_ACTIONS_PER_PLAN = 12
BUDGET_WINDOW_S = 300                  # repair-storm window
BUDGET_MAX_RECOVERIES = 8             # per component per window
HEALER_SELF_COMPONENT_PREFIX = "omem.healing"  # depth guard for healer-of-healer


class HealingError(Exception):
    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


# ── redaction ────────────────────────────────────────────────────────────────
class Redactor:
    """Strip secrets/credentials/tokens before anything is persisted. Failure
    context routinely contains request bodies, headers, and env — none of which
    should land in durable failure memory."""
    _KEY_RE = re.compile(
        r"(?i)(pass(word)?|secret|token|api[_-]?key|authorization|bearer|credential|"
        r"private[_-]?key|access[_-]?key|refresh[_-]?token|cookie|session|otp|mfa|"
        r"client[_-]?secret|signing[_-]?key)")
    # value patterns that look like secrets even without a telltale key
    _VALUE_RES = [
        re.compile(r"(?i)bearer\s+[A-Za-z0-9._\-]{8,}"),
        re.compile(r"omem_sk_[A-Za-z0-9]{4,}"),
        re.compile(r"sk-[A-Za-z0-9]{8,}"),
        re.compile(r"AKIA[0-9A-Z]{12,}"),
        re.compile(r"(?i)\b[A-Za-z0-9._%+\-]+:[^@\s/]{6,}@"),  # user:pass@host
        re.compile(r"eyJ[A-Za-z0-9._\-]{20,}"),               # JWT-ish
    ]
    # inline "key = value" secret assignments in free text / error strings: keep
    # the key name (useful for debugging), redact only the value.
    _ASSIGN_RE = re.compile(
        r"(?i)\b(pass(?:word)?|secret|token|api[_-]?key|apikey|access[_-]?key|"
        r"refresh[_-]?token|client[_-]?secret|private[_-]?key|signing[_-]?key)"
        r"(\s*[=:]\s*)([^\s,;'\"]{3,})")
    REDACTED = "[REDACTED]"

    @classmethod
    def scrub_text(cls, s: str) -> str:
        if not isinstance(s, str):
            return s
        # redact secret values in "key=value" assignments, keeping the key name
        s = cls._ASSIGN_RE.sub(lambda m: m.group(1) + m.group(2) + cls.REDACTED, s)
        for rx in cls._VALUE_RES:
            s = rx.sub(cls.REDACTED, s)
        return s

    @classmethod
    def scrub(cls, obj, _depth=0):
        if _depth > 12:
            return cls.REDACTED
        if isinstance(obj, dict):
            out = {}
            for k, v in obj.items():
                if isinstance(k, str) and cls._KEY_RE.search(k):
                    out[k] = cls.REDACTED
                else:
                    out[k] = cls.scrub(v, _depth + 1)
            return out
        if isinstance(obj, (list, tuple)):
            return [cls.scrub(v, _depth + 1) for v in obj]
        if isinstance(obj, str):
            return cls.scrub_text(obj)
        return obj


# ── action registry (the ONLY things that can execute) ───────────────────────
class ActionRegistry:
    """Maps action_type -> (risk_class, handler). Handlers are registered in code,
    never derived from LLM output or error text. A proposed action executes only
    if its exact action_type is registered; its risk class comes from the registry,
    NOT from the plan (so a plan cannot downgrade its own risk)."""

    def __init__(self):
        self._actions = {}

    def register(self, action_type: str, risk: str, handler, description: str = ""):
        if risk not in _RISK_RANK:
            raise HealingError("bad_risk", f"unknown risk {risk}")
        self._actions[action_type] = {"risk": risk, "handler": handler, "desc": description}

    def known(self, action_type: str) -> bool:
        return action_type in self._actions

    def risk_of(self, action_type: str) -> str | None:
        a = self._actions.get(action_type)
        return a["risk"] if a else None

    def handler_of(self, action_type: str):
        a = self._actions.get(action_type)
        return a["handler"] if a else None

    def describe(self):
        return {k: {"risk": v["risk"], "desc": v["desc"]} for k, v in self._actions.items()}


class ComponentRegistry:
    """Agents register their own components (extensible, not app-specific). A
    component exposes optional callables used by built-in low-risk handlers and
    by verification: retry(), clear_cache(), rebuild_index(), reconnect(),
    reload_config(), restart(), health() -> (status, reason)."""

    def __init__(self):
        self._components = {}

    def register(self, name: str, **hooks):
        self._components[name] = hooks

    def get(self, name: str):
        return self._components.get(name)

    def names(self):
        return list(self._components.keys())


# ── policy (OMEM is the authority, not the LLM) ──────────────────────────────
class Policy:
    """Evaluates a plan against RBAC + risk class + capability boundary. Returns a
    decision with per-action permits and reasons. The plan cannot self-authorize:
    risk comes from the registry, high-risk requires explicit approval + the
    highest permission, unknown actions are denied outright."""

    # risk -> required permission
    _PERM_FOR_RISK = {
        RISK_LOW: "heal.execute.low",
        RISK_MEDIUM: "heal.execute.medium",
        RISK_HIGH: "heal.execute.high",
    }

    def __init__(self, registry: ActionRegistry, can_fn):
        # can_fn(permission) -> bool, already bound to the request's org/user/role.
        self.registry = registry
        self.can = can_fn

    def evaluate(self, plan: dict, approved_by=None) -> dict:
        decisions = []
        permitted = []
        actions = plan.get("actions") or []
        if not isinstance(actions, list):
            return {"permitted": [], "decisions": [{"reason": "actions not a list", "permit": False}],
                    "ok": False}
        if len(actions) > MAX_ACTIONS_PER_PLAN:
            return {"permitted": [], "decisions": [{"reason": "too many actions", "permit": False}],
                    "ok": False}
        for i, act in enumerate(actions):
            d = self._evaluate_action(act, approved_by)
            d["index"] = i
            decisions.append(d)
            if d["permit"]:
                permitted.append(act)
        return {"permitted": permitted, "decisions": decisions,
                "ok": len(permitted) == len(actions) and len(actions) > 0}

    def _evaluate_action(self, act, approved_by) -> dict:
        if not isinstance(act, dict) or "type" not in act:
            return {"permit": False, "reason": "malformed action"}
        at = act["type"]
        # 1. must be a registered, executable action — error text can't invent one
        if not self.registry.known(at):
            return {"permit": False, "reason": f"unknown action type '{at}' (not registered)"}
        risk = self.registry.risk_of(at)       # authoritative risk (not from plan)
        perm = self._PERM_FOR_RISK[risk]
        # 2. RBAC gate
        if not self.can(perm):
            return {"permit": False, "reason": f"missing permission {perm}", "risk": risk}
        # 3. high-risk never auto-executes: needs explicit approval
        if risk == RISK_HIGH and not approved_by:
            return {"permit": False, "reason": "high-risk action requires explicit approval",
                    "risk": risk, "requires_approval": True}
        return {"permit": True, "reason": "permitted", "risk": risk}


# ── durable store for healing state (reuses the Store's DB + atomic claim) ────
class HealingStore:
    """CRUD + atomic claim over the heal_* tables. Every method is scoped by
    org_id + project_id so a recovery can never touch another tenant's rows."""

    def __init__(self, db):
        self.db = db

    # -- failures --
    def record_failure(self, org_id, project_id, rec: dict) -> dict:
        fid = rec.get("id") or "fail_" + uuid.uuid4().hex[:12]
        fp = rec["fingerprint"]
        # idempotency: same fingerprint in same project increments occurrences
        existing = self.db.execute(
            "SELECT id, occurrences FROM heal_failures WHERE project_id=? AND fingerprint=? AND resolved=0 "
            "ORDER BY ts DESC LIMIT 1", (project_id, fp)).fetchone()
        now = time.time()
        if existing:
            self.db.execute("UPDATE heal_failures SET occurrences=occurrences+1, ts=? WHERE id=?",
                            (now, existing["id"]))
            self.db.commit()
            return self.failure(org_id, project_id, existing["id"])
        self.db.execute(
            "INSERT INTO heal_failures(id,org_id,project_id,fingerprint,component,error_type,message,"
            "severity,context,occurrences,resolved,ts) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (fid, org_id, project_id, fp, rec.get("component", "unknown"),
             rec.get("error_type", "unknown"), rec.get("message", "")[:4000],
             rec.get("severity", "error"), json.dumps(rec.get("context") or {}), 1, 0, now))
        self.db.commit()
        return self.failure(org_id, project_id, fid)

    def failure(self, org_id, project_id, fid) -> dict | None:
        r = self.db.execute(
            "SELECT * FROM heal_failures WHERE id=? AND org_id=? AND project_id=?",
            (fid, org_id, project_id)).fetchone()
        return _row_to_failure(r) if r else None

    def failures(self, org_id, project_id, limit=100, component=None) -> list[dict]:
        if component:
            rows = self.db.execute(
                "SELECT * FROM heal_failures WHERE org_id=? AND project_id=? AND component=? "
                "ORDER BY ts DESC LIMIT ?", (org_id, project_id, component, limit)).fetchall()
        else:
            rows = self.db.execute(
                "SELECT * FROM heal_failures WHERE org_id=? AND project_id=? ORDER BY ts DESC LIMIT ?",
                (org_id, project_id, limit)).fetchall()
        return [_row_to_failure(r) for r in rows]

    def resolve_failure(self, org_id, project_id, fid):
        self.db.execute("UPDATE heal_failures SET resolved=1 WHERE id=? AND org_id=? AND project_id=?",
                        (fid, org_id, project_id))
        self.db.commit()

    # -- prior diagnosis/repair memory (the "gets better next time" part) --
    def prior_successful(self, org_id, project_id, fingerprint) -> dict | None:
        """The last successful diagnosis+repair for this failure signature."""
        r = self.db.execute(
            "SELECT d.* FROM heal_diagnoses d WHERE d.org_id=? AND d.project_id=? AND d.fingerprint=? "
            "AND d.outcome='recovered' ORDER BY d.ts DESC LIMIT 1",
            (org_id, project_id, fingerprint)).fetchone()
        if not r:
            return None
        return {"diagnosis": r["diagnosis"], "confidence": r["confidence"],
                "plan": json.loads(r["plan"] or "{}"), "outcome": r["outcome"]}

    def record_diagnosis(self, org_id, project_id, failure_id, fingerprint, diagnosis,
                         confidence, plan, outcome):
        self.db.execute(
            "INSERT INTO heal_diagnoses(id,org_id,project_id,failure_id,fingerprint,diagnosis,"
            "confidence,plan,outcome,ts) VALUES(?,?,?,?,?,?,?,?,?,?)",
            ("diag_" + uuid.uuid4().hex[:12], org_id, project_id, failure_id, fingerprint,
             str(diagnosis)[:4000], float(confidence or 0.0), json.dumps(plan or {}),
             outcome, time.time()))
        self.db.commit()

    # -- recovery claim (atomic; one active recovery per component) --
    def claim_recovery(self, org_id, project_id, failure_id, component, owner, fingerprint) -> str | None:
        """Atomically claim recovery for a component. Returns recovery_id if this
        caller won the claim, else None (another recovery already active, budget
        exceeded, or this strategy exhausted).

        Single-active-claim is DB-ENFORCED via heal_active_claims' primary key
        (org,project,component): two instances racing on separate connections both
        try INSERT ... ON CONFLICT DO NOTHING, and only one row can exist, so only
        one wins. This is race-free on both SQLite and Postgres — unlike a
        check-then-insert, which two independent connections can interleave."""
        # advisory guards first (cheap; not the correctness-critical part)
        since = time.time() - BUDGET_WINDOW_S
        n = self.db.execute(
            "SELECT COUNT(*) AS c FROM heal_recoveries WHERE org_id=? AND project_id=? AND component=? AND ts>=?",
            (org_id, project_id, component, since)).fetchone()
        if n and (n["c"] if "c" in n.keys() else n[0]) >= BUDGET_MAX_RECOVERIES:
            return None
        tried = self.db.execute(
            "SELECT COUNT(*) AS c FROM heal_recoveries WHERE org_id=? AND project_id=? AND fingerprint=?",
            (org_id, project_id, fingerprint)).fetchone()
        if tried and (tried["c"] if "c" in tried.keys() else tried[0]) >= MAX_ATTEMPTS_PER_FINGERPRINT:
            return None

        rid = "rec_" + uuid.uuid4().hex[:12]
        # ATOMIC single-winner claim: only one row can exist per component slot.
        self.db.execute(
            "INSERT INTO heal_active_claims(org_id,project_id,component,recovery_id,owner,ts) "
            "VALUES(?,?,?,?,?,?) ON CONFLICT DO NOTHING",
            (org_id, project_id, component, rid, owner, time.time()))
        self.db.commit()
        # did WE win the slot? read back the owner of the active claim.
        won = self.db.execute(
            "SELECT recovery_id FROM heal_active_claims WHERE org_id=? AND project_id=? AND component=?",
            (org_id, project_id, component)).fetchone()
        if not won or won["recovery_id"] != rid:
            return None  # another instance holds the claim

        # we own the slot -> create the recovery row
        self.db.execute(
            "INSERT INTO heal_recoveries(id,org_id,project_id,failure_id,component,fingerprint,"
            "state,owner,plan,actions_run,verification,outcome,attempts,ts) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (rid, org_id, project_id, failure_id, component, fingerprint, S_CLAIMED, owner,
             "{}", "[]", "{}", "", 0, time.time()))
        self.db.commit()
        return rid

    def release_recovery(self, org_id, project_id, component, recovery_id):
        """Release the single-active-claim slot when a recovery terminates, so the
        component can be recovered again later. Only the owner recovery releases
        its own slot (guards against releasing a successor's claim)."""
        self.db.execute(
            "DELETE FROM heal_active_claims WHERE org_id=? AND project_id=? AND component=? AND recovery_id=?",
            (org_id, project_id, component, recovery_id))
        self.db.commit()

    # Column names are interpolated into the UPDATE below, so they are checked
    # against this list rather than trusted. Every caller today passes a literal
    # keyword, so nothing is exploitable — but "no caller passes user input yet"
    # is a property of today's callers, not of this function, and it is one
    # refactor away from being untrue.
    RECOVERY_COLUMNS = frozenset({
        "failure_id", "component", "fingerprint", "state", "owner",
        "plan", "actions_run", "verification", "outcome", "attempts", "ts",
    })

    def set_recovery(self, org_id, project_id, rid, **fields):
        cols, vals = [], []
        for k, v in fields.items():
            if k not in self.RECOVERY_COLUMNS:
                raise ValueError(f"set_recovery: unknown column {k!r}")
            if k in ("plan", "actions_run", "verification"):
                v = json.dumps(v)
            cols.append(f"{k}=?")
            vals.append(v)
        if not cols:
            return
        vals += [rid, org_id, project_id]
        self.db.execute(f"UPDATE heal_recoveries SET {','.join(cols)} WHERE id=? AND org_id=? AND project_id=?",
                        tuple(vals))
        self.db.commit()

    def recovery(self, org_id, project_id, rid) -> dict | None:
        r = self.db.execute("SELECT * FROM heal_recoveries WHERE id=? AND org_id=? AND project_id=?",
                            (rid, org_id, project_id)).fetchone()
        return _row_to_recovery(r) if r else None

    def recoveries_for(self, org_id, project_id, failure_id) -> list[dict]:
        rows = self.db.execute(
            "SELECT * FROM heal_recoveries WHERE org_id=? AND project_id=? AND failure_id=? ORDER BY ts",
            (org_id, project_id, failure_id)).fetchall()
        return [_row_to_recovery(r) for r in rows]

    # -- health --
    def report_health(self, org_id, project_id, component, status, reason="", metadata=None):
        if status not in HEALTH_STATES:
            status = "unknown"
        self.db.execute(
            "INSERT INTO heal_health(id,org_id,project_id,component,status,reason,metadata,ts) "
            "VALUES(?,?,?,?,?,?,?,?)",
            ("hlth_" + uuid.uuid4().hex[:12], org_id, project_id, component, status,
             str(reason)[:1000], json.dumps(Redactor.scrub(metadata or {})), time.time()))
        self.db.commit()

    def health(self, org_id, project_id) -> dict:
        # latest status per component
        rows = self.db.execute(
            "SELECT component, status, reason, ts FROM heal_health WHERE org_id=? AND project_id=? "
            "ORDER BY ts DESC", (org_id, project_id)).fetchall()
        seen, comps = set(), []
        for r in rows:
            if r["component"] in seen:
                continue
            seen.add(r["component"])
            comps.append({"component": r["component"], "status": r["status"],
                          "reason": r["reason"], "ts": r["ts"]})
        # aggregate
        order = {"failed": 3, "degraded": 2, "recovering": 1, "healthy": 0, "unknown": 1}
        overall = "healthy"
        worst = 0
        for c in comps:
            w = order.get(c["status"], 1)
            if w > worst:
                worst, overall = w, c["status"]
        return {"overall": overall if comps else "unknown", "components": comps}

    # -- snapshots (known-good states) --
    def record_snapshot(self, org_id, project_id, label, kind, payload):
        sid = "snap_" + uuid.uuid4().hex[:12]
        self.db.execute(
            "INSERT INTO heal_snapshots(id,org_id,project_id,label,kind,payload,ts) VALUES(?,?,?,?,?,?,?)",
            (sid, org_id, project_id, label, kind, json.dumps(Redactor.scrub(payload or {})), time.time()))
        self.db.commit()
        return sid

    def latest_snapshot(self, org_id, project_id, kind) -> dict | None:
        r = self.db.execute(
            "SELECT * FROM heal_snapshots WHERE org_id=? AND project_id=? AND kind=? ORDER BY ts DESC LIMIT 1",
            (org_id, project_id, kind)).fetchone()
        if not r:
            return None
        return {"id": r["id"], "label": r["label"], "kind": r["kind"],
                "payload": json.loads(r["payload"] or "{}"), "ts": r["ts"]}


def _row_to_failure(r) -> dict:
    return {"id": r["id"], "component": r["component"], "error_type": r["error_type"],
            "message": r["message"], "severity": r["severity"], "fingerprint": r["fingerprint"],
            "occurrences": r["occurrences"], "resolved": bool(r["resolved"]),
            "context": json.loads(r["context"] or "{}"), "ts": r["ts"]}


def _row_to_recovery(r) -> dict:
    return {"id": r["id"], "failure_id": r["failure_id"], "component": r["component"],
            "state": r["state"], "owner": r["owner"], "outcome": r["outcome"],
            "attempts": r["attempts"], "plan": json.loads(r["plan"] or "{}"),
            "actions_run": json.loads(r["actions_run"] or "[]"),
            "verification": json.loads(r["verification"] or "{}"), "ts": r["ts"]}


# ── fingerprinting ───────────────────────────────────────────────────────────
def fingerprint(component: str, error_type: str, plan_signature: str = "") -> str:
    h = hashlib.sha256()
    h.update((component or "").encode())
    h.update(b"\x00")
    h.update((error_type or "").encode())
    h.update(b"\x00")
    h.update((plan_signature or "").encode())
    return h.hexdigest()[:24]


def plan_signature(plan: dict) -> str:
    """Stable signature of a plan's action types (order-independent) so the same
    repair strategy for the same failure is recognised as a retry."""
    types = sorted(a.get("type", "") for a in (plan.get("actions") or []) if isinstance(a, dict))
    return ",".join(types)


# ── the Healer (lifecycle orchestrator) ──────────────────────────────────────
class Healer:
    """Orchestrates the self-healing lifecycle for one request scope. The LLM
    (diagnose_fn) may propose a plan; OMEM enforces policy, executes only
    registered handlers, verifies, records, and rolls back/retries within a finite
    budget. Fails closed."""

    def __init__(self, store: HealingStore, actions: ActionRegistry, components: ComponentRegistry,
                 policy: Policy, audit_fn=None):
        self.store = store
        self.actions = actions
        self.components = components
        self.policy = policy
        self.audit = audit_fn or (lambda *a, **k: None)

    # -- capture --
    def capture(self, org_id, project_id, error: dict) -> dict:
        component = str(error.get("component", "unknown"))
        error_type = str(error.get("error_type") or error.get("type") or "unknown")
        fp = fingerprint(component, error_type)
        rec = {
            "component": component, "error_type": error_type,
            "message": Redactor.scrub_text(str(error.get("message", "")))[:4000],
            "severity": error.get("severity") if error.get("severity") in SEVERITIES else "error",
            "fingerprint": fp,
            "context": Redactor.scrub(error.get("context") or {}),
        }
        failure = self.store.record_failure(org_id, project_id, rec)
        self.audit("healing.failure.captured", resource=failure["id"],
                   metadata={"component": component, "error_type": error_type})
        return failure

    def recall(self, org_id, project_id, failure: dict) -> dict:
        """Retrieve prior memory for this failure signature. Returned as DATA."""
        prior = self.store.prior_successful(org_id, project_id, failure["fingerprint"])
        history = self.store.recoveries_for(org_id, project_id, failure["id"])
        return {"prior_successful": prior, "history": history,
                "occurrences": failure["occurrences"]}

    # -- full autonomous loop --
    def handle(self, org_id, project_id, error: dict, *, owner: str, diagnose_fn=None,
               approved_by=None) -> dict:
        """The high-level entry: capture -> recall -> diagnose -> plan -> policy ->
        claim -> execute -> verify -> record -> rollback/retry -> structured result.
        diagnose_fn(failure, memory) -> plan dict (the LLM reasoning hook). If None,
        a known prior successful plan is reused; if neither, we escalate."""
        try:
            return self._handle_inner(org_id, project_id, error, owner, diagnose_fn, approved_by)
        except HealingError:
            raise
        except Exception as e:  # fail closed — never self-retry uncontrolled
            self.audit("healing.internal_error", metadata={"error": Redactor.scrub_text(str(e))[:300]})
            return {"status": "escalated", "reason": "healer internal error (failed closed)",
                    "error": Redactor.scrub_text(str(e))[:300]}

    def _handle_inner(self, org_id, project_id, error, owner, diagnose_fn, approved_by) -> dict:
        component = str(error.get("component", "unknown"))

        # healer-of-healer depth guard: the healing subsystem may be recovered, but
        # a recovery cannot itself trigger a recovery of the healing subsystem.
        if component.startswith(HEALER_SELF_COMPONENT_PREFIX) and error.get("_healer_depth", 0) >= 1:
            return {"status": "escalated", "reason": "healer self-recovery depth limit (fail closed)"}

        failure = self.capture(org_id, project_id, error)
        memory = self.recall(org_id, project_id, failure)

        # choose a plan: prior successful repair first (memory), else the LLM
        plan = None
        source = None
        if memory["prior_successful"] and memory["prior_successful"].get("plan", {}).get("actions"):
            plan = memory["prior_successful"]["plan"]
            source = "memory"
        elif diagnose_fn is not None:
            proposed = diagnose_fn(dict(failure), dict(memory))  # LLM proposes (untrusted)
            plan = _coerce_plan(proposed)
            source = "llm"
        if not plan or not plan.get("actions"):
            self.store.record_diagnosis(org_id, project_id, failure["id"], failure["fingerprint"],
                                        "no plan available", 0.0, plan or {}, "escalated")
            self.audit("healing.escalated", resource=failure["id"], metadata={"reason": "no plan"})
            return {"status": "escalated", "reason": "no repair plan available",
                    "failure_id": failure["id"], "memory": _memory_summary(memory)}

        # policy: OMEM decides, not the LLM
        decision = self.policy.evaluate(plan, approved_by=approved_by)
        if not decision["ok"]:
            self.store.record_diagnosis(org_id, project_id, failure["id"], failure["fingerprint"],
                                        plan.get("diagnosis", ""), plan.get("confidence", 0.0),
                                        plan, "denied")
            self.audit("healing.plan.denied", resource=failure["id"],
                       metadata={"decisions": decision["decisions"]})
            return {"status": "denied", "reason": "plan not permitted by policy",
                    "failure_id": failure["id"], "decisions": decision["decisions"]}

        # concurrency: atomic claim (also enforces budget + fingerprint cap)
        sig = plan_signature(plan)
        fp_full = fingerprint(component, failure["error_type"], sig)
        rid = self.store.claim_recovery(org_id, project_id, failure["id"], component, owner, fp_full)
        if rid is None:
            self.audit("healing.claim.rejected", resource=failure["id"],
                       metadata={"component": component})
            return {"status": "throttled",
                    "reason": "recovery already active, budget exceeded, or strategy already exhausted",
                    "failure_id": failure["id"]}

        self.store.set_recovery(org_id, project_id, rid, state=S_REPAIRING, plan=plan)

        # execute permitted actions (registered handlers only)
        actions_run = []
        executed_ok = True
        for act in decision["permitted"]:
            res = self._execute_action(component, act)
            actions_run.append(res)
            if not res["ok"]:
                executed_ok = False
                break
        self.store.set_recovery(org_id, project_id, rid, actions_run=actions_run)

        # verify — explicit, never assume success from a returned-ok action
        self.store.set_recovery(org_id, project_id, rid, state=S_VERIFYING)
        verification = self._verify(component, plan)
        verified = executed_ok and verification["ok"]

        if verified:
            self.store.set_recovery(org_id, project_id, rid, state=S_RECOVERED,
                                    outcome="recovered", verification=verification)
            self.store.record_diagnosis(org_id, project_id, failure["id"], failure["fingerprint"],
                                        plan.get("diagnosis", ""), plan.get("confidence", 0.0),
                                        plan, "recovered")
            self.store.resolve_failure(org_id, project_id, failure["id"])
            self.store.report_health(org_id, project_id, component, "healthy",
                                     reason="recovered by self-healing")
            self.store.release_recovery(org_id, project_id, component, rid)
            self.audit("healing.recovered", resource=failure["id"],
                       metadata={"recovery_id": rid, "source": source})
            return {"status": "recovered", "failure_id": failure["id"], "recovery_id": rid,
                    "plan_source": source, "actions_run": actions_run, "verification": verification}

        # rollback + escalate (retry budget is enforced by the fingerprint cap on
        # the next handle() call for the same signature)
        rollback = self._rollback(component, plan, actions_run)
        self.store.set_recovery(org_id, project_id, rid, state=S_ESCALATED,
                                outcome="failed", verification=verification)
        self.store.record_diagnosis(org_id, project_id, failure["id"], failure["fingerprint"],
                                    plan.get("diagnosis", ""), plan.get("confidence", 0.0),
                                    plan, "failed")
        self.store.report_health(org_id, project_id, component, "failed",
                                 reason="self-healing verification failed")
        self.store.release_recovery(org_id, project_id, component, rid)
        self.audit("healing.failed", resource=failure["id"],
                   metadata={"recovery_id": rid, "verification": verification})
        return {"status": "failed", "failure_id": failure["id"], "recovery_id": rid,
                "actions_run": actions_run, "verification": verification, "rollback": rollback,
                "escalated": True}

    # -- execution: only registered handlers, on registered components --
    def _execute_action(self, component, act) -> dict:
        at = act["type"]
        handler = self.actions.handler_of(at)
        if handler is None:  # defense in depth (policy already checked)
            return {"type": at, "ok": False, "error": "unknown action"}
        comp = self.components.get(component)
        try:
            out = handler(comp, act.get("args") or {})
            return {"type": at, "ok": bool(out.get("ok", True)) if isinstance(out, dict) else True,
                    "detail": Redactor.scrub(out) if isinstance(out, dict) else str(out)[:300]}
        except Exception as e:
            return {"type": at, "ok": False, "error": Redactor.scrub_text(str(e))[:300]}

    def _verify(self, component, plan) -> dict:
        """Explicit verification. Prefer the component's health() hook; a repair is
        only successful if health is healthy/recovering, not merely because an
        action returned ok."""
        comp = self.components.get(component)
        checks = []
        ok = True
        if comp and callable(comp.get("health")):
            try:
                status, reason = comp["health"]()
            except Exception as e:
                status, reason = "unknown", Redactor.scrub_text(str(e))[:200]
            checks.append({"check": "component.health", "status": status, "reason": reason})
            ok = status in ("healthy", "recovering")
        else:
            # no health hook -> cannot positively verify; require an explicit
            # verification action to have run and returned ok
            ok = False
            checks.append({"check": "component.health", "status": "unknown",
                           "reason": "no health hook registered; cannot verify"})
        return {"ok": ok, "checks": checks}

    def _rollback(self, component, plan, actions_run) -> dict:
        comp = self.components.get(component)
        steps = []
        for step in (plan.get("rollback") or []):
            at = step.get("type") if isinstance(step, dict) else None
            handler = self.actions.handler_of(at) if at else None
            if handler is None:
                steps.append({"type": at, "ok": False, "error": "no rollback handler"})
                continue
            try:
                out = handler(comp, step.get("args") or {})
                steps.append({"type": at, "ok": isinstance(out, dict) and out.get("ok", True)})
            except Exception as e:
                steps.append({"type": at, "ok": False, "error": Redactor.scrub_text(str(e))[:200]})
        return {"steps": steps}


def _coerce_plan(proposed) -> dict:
    """Accept an LLM-proposed plan as DATA. Only structural fields survive; nothing
    here is executed. Risk is NOT taken from the plan (the registry decides)."""
    if not isinstance(proposed, dict):
        return {}
    actions = proposed.get("actions")
    if not isinstance(actions, list):
        actions = []
    clean_actions = []
    for a in actions:
        if isinstance(a, dict) and isinstance(a.get("type"), str):
            clean_actions.append({"type": a["type"], "args": a.get("args") if isinstance(a.get("args"), dict) else {}})
    rollback = proposed.get("rollback")
    clean_rollback = []
    if isinstance(rollback, list):
        for a in rollback:
            if isinstance(a, dict) and isinstance(a.get("type"), str):
                clean_rollback.append({"type": a["type"], "args": a.get("args") if isinstance(a.get("args"), dict) else {}})
    return {
        "diagnosis": str(proposed.get("diagnosis", ""))[:2000],
        "confidence": float(proposed.get("confidence", 0.0)) if _is_num(proposed.get("confidence")) else 0.0,
        "actions": clean_actions,
        "rollback": clean_rollback,
        "verification": proposed.get("verification") if isinstance(proposed.get("verification"), list) else [],
    }


def _is_num(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def _memory_summary(memory) -> dict:
    return {"occurrences": memory["occurrences"],
            "has_prior_successful": bool(memory["prior_successful"]),
            "history_count": len(memory["history"])}


# ── built-in low-risk handlers (operate ONLY on registered component hooks) ───
def _mk_hook_handler(hook_name):
    def handler(component, args):
        if not component or not callable(component.get(hook_name)):
            return {"ok": False, "error": f"component has no {hook_name} hook"}
        out = component[hook_name](args) if _accepts_arg(component[hook_name]) else component[hook_name]()
        return {"ok": True} if out is None else ({"ok": bool(out.get("ok", True))} if isinstance(out, dict) else {"ok": True})
    return handler


def _accepts_arg(fn):
    try:
        import inspect
        return len(inspect.signature(fn).parameters) >= 1
    except Exception:
        return False


def default_action_registry() -> ActionRegistry:
    """Built-in low-risk repairs. They only ever call a hook the agent explicitly
    registered on the component — OMEM gains no ambient capability. Medium/high
    actions are intentionally NOT built in: an agent must register its own handler
    and hold the permission, so OMEM never invents infrastructure access."""
    reg = ActionRegistry()
    reg.register("retry", RISK_LOW, _mk_hook_handler("retry"), "Retry the failed operation")
    reg.register("clear_cache", RISK_LOW, _mk_hook_handler("clear_cache"), "Clear an in-memory cache")
    reg.register("rebuild_index", RISK_LOW, _mk_hook_handler("rebuild_index"), "Rebuild an in-memory index")
    reg.register("reconnect", RISK_LOW, _mk_hook_handler("reconnect"), "Reconnect a dependency")
    reg.register("reload_config", RISK_LOW, _mk_hook_handler("reload_config"), "Reload configuration")
    reg.register("restart_worker", RISK_LOW, _mk_hook_handler("restart"), "Restart an internal worker")
    return reg
