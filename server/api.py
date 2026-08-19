"""OMEM Cloud API — a thin HTTP layer over the authoritative OMEM engine.

DESIGN RULE (enforced): this server invents NO memory semantics. Every memory
operation delegates to exactly one method on omem_engine.Engine (the CTS-verified
reference). The only things this layer adds are (a) multi-tenant store management
(projects/environments each own an Engine instance) and (b) response *shaping* that
assembles existing query results into UI-friendly objects. Where a UI needs a value,
it is always computed by calling a frozen query — never recomputed here.

Stdlib only (http.server) so it runs with no pip install. JSON in/out. CORS enabled
for the Next.js dev frontend.
"""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from store import Store
from ingest import Ingestor
from connectors import (OAuthStore, GmailConnector, MockGmailTransport, GmailTransport,
                        LLMExtractor, MockLLMClient, EntityResolver)
from scheduler import Scheduler
from enterprise import Enterprise, role_allows, ROLES, PLANS
import providers
from omem_engine.engine import Engine, ACCEPTED  # the authoritative engine
from omem_engine.reasons import Rejected
from omem_engine.primitives import Assertion
from omem_engine.canon import RETRACTED


# ── Store management (the only stateful thing this layer owns) ───────────────
class Project:
    """A project/environment = one OMEM store = one Engine (Model §2.5)."""
    def __init__(self, pid: str, name: str, env: str = "development",
                 org_id: str = "", is_demo: bool = False):
        self.org_id = org_id
        self.is_demo = is_demo
        self.id = pid
        self.name = name
        self.env = env
        self.engine = Engine()
        self.clock = 0            # server-managed logical clock for "now"
        self.created_at = time.time()
        self.log: list[dict] = []  # request log (activity), platform metadata only
        # human-facing labels captured at write time (platform metadata, not semantics)
        self.labels: dict[str, dict] = {}

    def now(self) -> int:
        return self.clock

    def tick(self) -> int:
        self.clock += 1
        return self.clock


PROJECTS: dict[str, Project] = {}
CONTRADICTIONS: dict[str, list] = {}  # per-project declared contradiction pairs (audit/UI)
# The same pairs as a set, purely so auto-declaration can test membership in
# constant time. CONTRADICTIONS stays a list because the UI and the ops log
# read it as one; this is the index over it, not a second source of truth.
_DECLARED_PAIRS: dict[str, set] = {}

# Load .env / .env.local before any module reads configuration.
from env_loader import load_env as _load_env
_ENV_FILES = _load_env()

DB_PATH = os.environ.get("OMEM_DB", os.path.join(os.path.dirname(__file__), "data", "omem.db"))
STORE = Store(DB_PATH)


NEGATION_PREFIX = "not:"


def _negation_counterpart(token: str):
    """The `not:` counterpart of a proposition token, or None if there isn't one.

    `likes_tea` <-> `not:likes_tea`. Involutive, so both directions produce the
    same unordered pair however the two claims arrive.
    """
    if not isinstance(token, str) or not token or token == RETRACTED:
        return None
    if token.startswith(NEGATION_PREFIX):
        base = token[len(NEGATION_PREFIX):]
        return base or None            # `not:` alone is not a negation of anything
    return NEGATION_PREFIX + token


def _auto_declare_negation(p: Project, proposition: str) -> None:
    """Declare `X` and `not:X` mutually exclusive when either one is asserted.

    WHY THIS IS NOT A VIOLATION OF THE ENGINE'S RULE. The engine decides
    contradiction only from explicitly declared token pairs and never from
    parsing text, and that is what makes a belief state reproducible without a
    model in the loop. This does not weaken it: it is a documented syntactic
    convention applied by the layer ABOVE the engine, which then declares the
    pair through the ordinary path. The engine still knows only what it was
    told. Nothing here inspects meaning, and `omem_engine/` is untouched.

    WHY IT HAS TO EXIST. Without it, `conflicts()` returns an empty list on
    first use no matter what a caller stores, because nothing had ever declared
    a pair and the SDK offered no way to. The product's headline behaviour was
    unreachable through its own documented interface.

    Declared on every assert rather than only when both sides are present: the
    registry is a set, declaring is idempotent, and a pair whose other half never
    arrives changes no answer. That keeps this a pure function of the op being
    applied, so a boot replay reconstructs exactly the same registry in the same
    order without needing to look at what else the log contains.

    An explicit contradict() between arbitrary tokens remains the general case;
    this only covers the one convention that can be recognised without judgment.
    """
    other = _negation_counterpart(proposition)
    if other is None:
        return
    p.engine.declare_contradiction(proposition, other)
    # Membership through a set, not a scan of the list. This runs on every
    # assert, and a linear check would make ingestion quadratic in the number of
    # distinct propositions — the exact shape of the performance problem this
    # engine already has, and not one worth adding another instance of.
    seen = _DECLARED_PAIRS.setdefault(p.id, set())
    pair = frozenset((proposition, other))
    if pair in seen:
        return
    seen.add(pair)
    CONTRADICTIONS.setdefault(p.id, []).append([proposition, other])


def apply_op(p: Project, kind: str, a: dict):
    """Single dispatch for every engine write. Used by live requests, seeding,
    and boot replay, so persisted history and live behavior can never diverge."""
    e = p.engine
    if kind == "entity":
        e.put_entity(a["id"], a["type"])
        p.labels[a["id"]] = {"kind": "entity", "type": a["type"], "label": a.get("label")}
    elif kind == "agent":
        e.put_agent(a["id"], a.get("kind", "system"), a.get("recorded_existence", 0))
        p.labels[a["id"]] = {"kind": "agent", "agent_kind": a.get("kind", "system"), "label": a.get("label")}
    elif kind == "event":
        e.put_event(a["id"], a["ekind"], a["event_time"], a.get("event_end"))
        p.labels[a["id"]] = {"kind": "event", "event_kind": a["ekind"], "label": a.get("label"), "event_time": a["event_time"]}
    elif kind == "assert":
        e.assert_(a["id"], a["agent"], a["subjects"], a["proposition"], a["assertion_time"],
                  a.get("event_time"), a.get("confidence"))
        p.labels[a["id"]] = {"kind": "assertion", "label": a.get("label")}
        _auto_declare_negation(p, a["proposition"])
    elif kind == "derive":
        e.derive(a["consequent"], a["antecedents"], a.get("dkind", "inference"), a["id"])
    elif kind == "supersede":
        e.supersede(Assertion(a["id"], a["agent"], tuple(a["subjects"]), a["proposition"],
                              a["assertion_time"], None, a.get("confidence")), a["olds"], a["did"])
        p.labels[a["id"]] = {"kind": "assertion", "label": a.get("label")}
        _auto_declare_negation(p, a["proposition"])
    elif kind == "retract":
        e.retract(Assertion(a["id"], a["agent"], tuple(a["subjects"]), RETRACTED,
                            a["assertion_time"]), a["old"], a["did"])
    elif kind == "corefer":
        e.corefer(a["id"], a["entity_a"], a["entity_b"], a["agent"], a["assertion_time"])
    elif kind == "split":
        e.split(a["cor"], a["agent"], a["assertion_time"], a["id"], a["did"])
    elif kind == "declare":
        e.declare_contradiction(a["token_a"], a["token_b"])
        CONTRADICTIONS.setdefault(p.id, []).append([a["token_a"], a["token_b"]])
    else:
        raise ValueError(f"unknown op kind {kind}")


def record(p: Project, kind: str, a: dict):
    """Apply through the engine; persist only if accepted (engine raises otherwise)."""
    apply_op(p, kind, a)
    STORE.record_op(p.id, kind, a, p.clock)
    # P7 candidate index: keep the above-engine projection in lockstep with
    # every accepted assert/supersede. Pure projection of identity + subjects
    # + proposition; never decides belief. Best-effort — the index is
    # rebuildable from the engine and its absence only falls back to scanning.
    if kind in ("assert", "supersede"):
        try:
            _cand_index.index_assertion(STORE.db, p.id, a["id"], a["subjects"],
                                        a["proposition"], a["assertion_time"])
        except Exception:
            pass


def source_view(src, connector=None):
    """Readable rendering of stored source material (the original email/message).
    Values come straight from the persisted payload — nothing is reconstructed."""
    if not src:
        return None
    from connectors import readable_body
    payload = json.loads(src["payload"]) if isinstance(src["payload"], str) else src["payload"]
    # Legacy records were stored before MIME/HTML handling existed, so clean the
    # body at read time too. Never mutates the immutable source record.
    body = readable_body(payload.get("body") or "")
    subject = (payload.get("subject") or payload.get("title") or "").strip()
    return {
        "kind": connector["kind"] if connector else "unknown",
        "connector": connector["name"] if connector else src["connector_id"],
        "external_id": src["external_id"],
        "received": src["received"],
        "title": subject or "(no subject)",
        "from": payload.get("from") or payload.get("author") or payload.get("customer"),
        "from_name": payload.get("from_name"),
        "from_email": payload.get("from_email"),
        "to": payload.get("to"),
        "sent_at": payload.get("date") or payload.get("created_at"),
        "body": body,
        "snippet": (body[:300] if body else (payload.get("snippet") or "")),
        "link": payload.get("gmail_url") or payload.get("url"),
    }


def e_state(p, subjects, proposition):
    """Thin pass-through to the frozen engine's proposition_state. The engine is
    the sole authority; this never computes state itself."""
    return p.engine.proposition_state(subjects, proposition, p.now())


def boot():
    """Rehydrate every project by replaying its op log through a fresh engine,
    then reconcile above-engine PROJECTIONS (P5 graph edges, P7 candidate index)
    from the replayed engine state. The op log is the source of truth; the
    projections are disposable and rebuilt to match it — so a crash between an
    op write and a projection write, or a partial DB restore, self-heals at
    boot instead of leaving a projection silently diverged."""
    for row in STORE.projects_all():
        p = Project(row["id"], row["name"], row["env"], row["org_id"], bool(row["is_demo"]))
        PROJECTS[row["id"]] = p
        CONTRADICTIONS.setdefault(row["id"], [])
        _DECLARED_PAIRS.setdefault(row["id"], set())
        for op in STORE.ops_for(row["id"]):
            p.clock = max(p.clock, op["clock"])
            apply_op(p, op["kind"], op["args"])
        _reconcile_projections(p)
    # first boot: optionally create a labeled demo project. OFF by default so a
    # tester's dashboard shows ONLY their own real data — never placeholder rows.
    # Set OMEM_SEED_DEMO=1 to restore the sample project (e.g. for a screenshot).
    if os.environ.get("OMEM_SEED_DEMO", "0") == "1" and "demo" not in PROJECTS:
        STORE.create_project("org_demo", "Demo (shared sandbox)", "development",
                             pid="demo", is_demo=True)
        _seed_demo()


PROJECTION_DRIFT = {}  # project_id -> last reconciliation report (observability)


def _reconcile_projections(p):
    """Rebuild the candidate index from engine state, and rebuild graph edges
    from open relational assertions, so both match the replayed engine. Both
    rebuilds are idempotent and cheap (single pass over assertions); failures
    are non-fatal — a missing projection only degrades to the scan path.

    P8-hardening (observability): capture projection row counts before and after
    the rebuild. If they differ, drift was actually repaired — record it in
    PROJECTION_DRIFT and log it so an operator can tell recovery occurred,
    rather than the repair being silent. This changes no engine state."""
    def _count(table):
        try:
            return STORE.db.execute(
                f"SELECT COUNT(*) n FROM {table} WHERE project_id=?", (p.id,)).fetchone()["n"]
        except Exception:
            return None
    before = {"candidate_subjects": _count("candidate_subjects"),
              "memory_edges": _count("memory_edges")}
    try:
        _cand_index.rebuild(STORE.db, p)
    except Exception:
        pass
    try:
        _graph.rebuild_projection(STORE.db, p)
    except Exception:
        pass
    after = {"candidate_subjects": _count("candidate_subjects"),
             "memory_edges": _count("memory_edges")}
    repaired = {k: {"before": before[k], "after": after[k]}
                for k in after if before.get(k) != after.get(k)}
    if repaired:
        PROJECTION_DRIFT[p.id] = {"repaired": repaired, "at": time.time()}
        try:
            import logging as _logging
            _logging.getLogger("omem").warning(
                "projection drift repaired for project %s: %s", p.id, repaired)
        except Exception:
            pass
    return {"drift_repaired": bool(repaired), "detail": repaired}


def _seed_demo():
    """The shared demo scenario, written through the normal recorded path so it
    replays identically on boot. Lives ONLY in the is_demo project."""
    p = Project("demo", "Demo (shared sandbox)", "development", "org_demo", True)
    PROJECTS["demo"] = p
    CONTRADICTIONS["demo"] = []
    _DECLARED_PAIRS["demo"] = set()
    t1 = p.tick()
    record(p, "entity", {"id": "customer:alice", "type": "person", "label": "Alice Chen"})
    record(p, "entity", {"id": "customer:bob", "type": "person", "label": "Bob Rivera"})
    record(p, "entity", {"id": "plan:enterprise", "type": "plan", "label": "Enterprise Plan"})
    record(p, "agent", {"id": "support-bot@v2.1", "kind": "system", "label": "Support Bot v2.1"})
    record(p, "agent", {"id": "import-bot@v1", "kind": "system", "label": "CRM Import v1"})
    record(p, "agent", {"id": "human:sam", "kind": "human", "label": "Sam (Support Lead)"})
    record(p, "event", {"id": "ticket:8842", "ekind": "support_ticket", "event_time": t1,
                        "label": "Ticket #8842, 'prefer email please'"})
    record(p, "assert", {"id": "a:alice-email", "agent": "support-bot@v2.1",
                         "subjects": ["customer:alice"], "proposition": "prefers_email_over_phone",
                         "assertion_time": t1, "confidence": 0.62,
                         "label": "Alice prefers email over phone"})
    record(p, "derive", {"id": "d:1", "consequent": "a:alice-email",
                         "antecedents": ["ticket:8842"], "dkind": "extraction"})
    t2 = p.tick()
    record(p, "event", {"id": "ticket:8850", "ekind": "support_ticket", "event_time": t2,
                        "label": "Ticket #8850, upgrade request"})
    record(p, "assert", {"id": "a:alice-enterprise", "agent": "support-bot@v2.1",
                         "subjects": ["customer:alice"], "proposition": "is_enterprise_customer",
                         "assertion_time": t2, "label": "Alice is an enterprise customer"})
    record(p, "derive", {"id": "d:2", "consequent": "a:alice-enterprise",
                         "antecedents": ["ticket:8850"], "dkind": "extraction"})
    record(p, "declare", {"token_a": "prefers_email_over_phone",
                          "token_b": "not:prefers_email_over_phone"})
    t3 = p.tick()
    record(p, "event", {"id": "crm:sync:19", "ekind": "crm_sync", "event_time": t3,
                        "label": "CRM sync, phone preferred flag"})
    record(p, "assert", {"id": "a:alice-notemail", "agent": "import-bot@v1",
                         "subjects": ["customer:alice"], "proposition": "not:prefers_email_over_phone",
                         "assertion_time": t3, "label": "Alice does NOT prefer email (CRM)"})
    record(p, "derive", {"id": "d:3", "consequent": "a:alice-notemail",
                         "antecedents": ["crm:sync:19"], "dkind": "extraction"})
    t4 = p.tick()
    record(p, "assert", {"id": "a:bob-free", "agent": "support-bot@v2.1",
                         "subjects": ["customer:bob"], "proposition": "on_free_plan",
                         "assertion_time": t4, "label": "Bob is on the free plan"})
    t6 = p.tick(); p.tick()
    record(p, "supersede", {"id": "a:bob-pro", "agent": "support-bot@v2.1",
                            "subjects": ["customer:bob"], "proposition": "on_pro_plan",
                            "assertion_time": t6, "olds": ["a:bob-free"], "did": "d:sup1",
                            "label": "Bob upgraded to the pro plan"})


INGEST = Ingestor(STORE, record, None, lambda pid: PROJECTS.get(pid))
OAUTH = OAuthStore(STORE.db)
RESOLVER = EntityResolver(STORE.db)
INGEST.resolver = RESOLVER

# Extractor selection: env OMEM_LLM=1 uses a (mock) LLM extractor; default rules.
# Real deployment injects a urllib-backed LLMClient here.
def _extractor_for(conn):
    import os as _os
    pid = conn.get("project_id") if isinstance(conn, dict) else None
    # project-level model config (set via /v1/settings); falls back to env/global
    if pid and ENT.setting(pid, "llm_enabled") == "1":
        if providers.llm_configured():
            model = ENT.setting(pid, "llm_model")
            cl = providers.OpenAICompatClient(
                usage_cb=lambda m, t: ENT.meter(pid, "llm_tokens", t))
            if model:
                cl.model = model
            return LLMExtractor(cl)
        # Enabled but no credentials: fall back to the DETERMINISTIC extractor.
        # Substituting a mock model here would fabricate production behaviour.
        return None
    if _os.environ.get("OMEM_LLM") == "1" and _os.environ.get("OMEM_ALLOW_MOCK_LLM") == "1":
        # TESTS ONLY: the deterministic mock model. Requires the explicit
        # OMEM_ALLOW_MOCK_LLM flag so a production deployment that sets
        # OMEM_LLM=1 without credentials can never ingest via keyword-mock
        # extraction (this was a real source of junk memories).
        return LLMExtractor(MockLLMClient("smart"))
    return None  # connector's default (contextual extractor for gmail)

# Connector factory: builds gmail with stored creds + transport, attaches extractor.
GMAIL_TRANSPORT_FACTORY = None  # tests set this to inject MockGmailTransport
SLACK_TRANSPORT_FACTORY = None
SFDC_TRANSPORT_FACTORY = None
GITHUB_TRANSPORT_FACTORY = None
RATE_LIMIT_RESETS: dict[str, float] = {}  # connector_id -> provider reset epoch

def _connector_factory(conn):
    kind = conn["kind"]
    ext = _extractor_for(conn)
    if kind in ("push", "webhook", "documents"):
        from ingest import PushConnector
        return PushConnector(STORE.db, conn["id"], ext)
    if kind == "github":
        from connectors import GitHubConnector, GitHubTransport, GitHubIssueExtractor
        creds = OAUTH.get(conn["id"], include_secrets=True)
        cfg = json.loads(conn["config"])
        transport = GITHUB_TRANSPORT_FACTORY(conn) if GITHUB_TRANSPORT_FACTORY else GitHubTransport()
        return GitHubConnector(transport, creds["access_token"] if creds else None,
                               cfg.get("repo", ""), ext or GitHubIssueExtractor())
    if kind == "slack":
        from connectors import SlackConnector, SlackTransport
        creds = OAUTH.get(conn["id"], include_secrets=True)
        cfg = json.loads(conn["config"])
        transport = SLACK_TRANSPORT_FACTORY(conn) if SLACK_TRANSPORT_FACTORY else SlackTransport()
        from ingest import RuleExtractor
        return SlackConnector(transport, creds["access_token"] if creds else None,
                              cfg.get("channel", "general"), ext or RuleExtractor())
    if kind == "salesforce":
        from connectors import SalesforceConnector, SalesforceTransport
        creds = OAUTH.get(conn["id"], include_secrets=True)
        transport = SFDC_TRANSPORT_FACTORY(conn) if SFDC_TRANSPORT_FACTORY else SalesforceTransport(
            os.environ.get("SFDC_INSTANCE_URL"))
        from ingest import RuleExtractor
        return SalesforceConnector(transport, creds["access_token"] if creds else None,
                                   ext or RuleExtractor())
    if kind == "gmail":
        creds = OAUTH.get(conn["id"], include_secrets=True)
        token = creds["access_token"] if creds else None
        if GMAIL_TRANSPORT_FACTORY:
            transport = GMAIL_TRANSPORT_FACTORY(conn)
        elif providers.google_configured() and creds and creds.get("refresh_token"):
            # REAL production path: hits gmail.googleapis.com. config.query lets a
            # customer narrow ingestion further (e.g. a label or a domain).
            # The transport owns token lifecycle: it reuses the stored access
            # token while valid, refreshes via the refresh token when expired
            # (a NORMAL hourly event, not a reauth condition), and persists
            # the fresh token so the next poll reuses it.
            transport = providers.RealGmailTransport(
                creds["refresh_token"], json.loads(conn["config"]).get("query"),
                access_token=creds.get("access_token"),
                expires=creds.get("expires"),
                on_token=lambda a, exp, _cid=conn["id"]: OAUTH.update_access(_cid, a, exp))
        else:
            transport = GmailTransport()  # raises ProviderNotConfigured on poll
        # Extractor choice is explicit: the SEMANTIC LLM extractor (full-email
        # reading with identity/roles/memories/thread context) when a REAL
        # provider is configured and the project enabled it; else the
        # direction-aware contextual extractor anchored on the org identity.
        # A mock model is NEVER substituted in a live deployment.
        from extraction import ContextualBusinessExtractor
        owner = _owner_identity_for(conn)
        pid = conn.get("project_id")
        if pid and ENT.setting(pid, "llm_enabled") == "1" and providers.llm_configured():
            ext = _semantic_extractor_for(conn, owner)
        c = GmailConnector(transport, token, ext or ContextualBusinessExtractor(owner))
        return c
    if kind == "support_inbox" and ext is not None:
        import json as _j
        from ingest import SupportInboxConnector
        return SupportInboxConnector(_j.loads(conn["config"]).get("items"), extractor=ext)
    return None

INGEST.connector_factory = _connector_factory
INGEST.extraction_logger = lambda pid, srid, ext, facts, ok, err: ENT.log_extraction(
    pid, srid, ext, facts=facts, ok=ok, error=err)

from classifier import (ClassificationStore, classify as classify_message,
                        thread_context_for, relationship_history, _address_of,
                        ClassificationResult)
CLASSIFICATIONS = ClassificationStore(STORE.db)


def _classify_for_pipeline(project_id, conn, payload, source_record_id):
    """Stage 1 gate. Judges the message in its thread, with relationship history,
    records the verdict, and returns it. Never raises into the pipeline."""
    try:
        thread = thread_context_for(STORE.db, project_id, payload.get("thread_id"),
                                    exclude_source_id=source_record_id)
        history = relationship_history(STORE.db, project_id,
                                       _address_of(payload.get("from", "")))
        judge = None
        if ENT.setting(project_id, "llm_enabled") == "1" and providers.llm_configured():
            judge = providers.OpenAICompatClient(
                usage_cb=lambda m, t: ENT.meter(project_id, "llm_tokens", t))
        result = classify_message(payload, thread, history, llm=judge)
        # ── user corrections are ground truth about the relationship ──────
        sender_addr = _address_of(payload.get("from", ""))
        role = _role_for(project_id, email=sender_addr)
        if role in ("IGNORE", "MARKETING", "PERSONAL"):
            result = ClassificationResult({
                **result,
                "classification": "AUTOMATED_NOISE" if role == "MARKETING" else "NON_BUSINESS",
                "confidence": 0.95,
                "reasons": [f"User marked this sender/domain as {role}"] + list(result.get("reasons", []))[:2],
            })
        elif role in ("CUSTOMER", "PROSPECT", "SUPPLIER", "PARTNER",
                      "OTHER_BUSINESS", "CONTRACTOR") and \
                result.get("classification") in ("NON_BUSINESS", "POSSIBLY_BUSINESS",
                                                  "AUTOMATED_NOISE"):
            result = ClassificationResult({
                **result,
                "classification": "BUSINESS_RELEVANT",
                "confidence": max(float(result.get("confidence") or 0), 0.75),
                "business_type": role if role != "OTHER_BUSINESS" else result.get("business_type"),
                "reasons": [f"User confirmed this counterparty as {role}"] + list(result.get("reasons", []))[:2],
            })
        CLASSIFICATIONS.record(project_id, conn["id"], source_record_id, payload,
                               result, entered_pipeline=result.allowed)
        # fine-grained category for EVERY message, including excluded ones —
        # the quality view must account for the whole mailbox, not just winners
        try:
            from email_analysis import analyze as _analyze
            owner = _owner_identity_for(conn)
            rd = result.to_dict() if hasattr(result, "to_dict") else dict(result or {})
            sc = rd.get("scores", {})
            an = _analyze(payload, owner,
                          business_score=sc.get("business", 0.0),
                          automated_score=sc.get("automated", 0.0),
                          business_signals=rd.get("signals", []))
            STORE.db.execute(
                "UPDATE message_classifications SET category=? WHERE source_record_id=?",
                (an["category"], source_record_id))
            STORE.db.commit()
        except Exception:
            pass
        ENT.meter(project_id, "messages_classified")
        return result
    except Exception:
        return None  # a classifier failure must not silently discard mail


INGEST.classifier = _classify_for_pipeline
INGEST.classification_store = CLASSIFICATIONS

# ── memory quality gate (app side) ───────────────────────────────────────────
# Every candidate fact from Gmail is graded before the engine sees it. The
# decision (and its reasons) is persisted so the product can answer both
# "why was this stored?" and "why was this NOT stored?" with real records.
FACT_DECISION_SCHEMA = """
CREATE TABLE IF NOT EXISTS fact_decisions(
  id INTEGER PRIMARY KEY AUTOINCREMENT, project_id TEXT NOT NULL,
  connector_id TEXT, source_record_id TEXT, subject TEXT NOT NULL,
  proposition TEXT NOT NULL, speech_act TEXT, quality TEXT NOT NULL,
  score REAL, reasons TEXT, category TEXT, stored INTEGER NOT NULL,
  evidence TEXT, ts REAL NOT NULL);
CREATE INDEX IF NOT EXISTS fd_project ON fact_decisions(project_id, ts);
CREATE INDEX IF NOT EXISTS fd_source ON fact_decisions(source_record_id);
CREATE TABLE IF NOT EXISTS relationship_overrides(
  project_id TEXT NOT NULL, key_type TEXT NOT NULL, key TEXT NOT NULL,
  role TEXT NOT NULL, source TEXT NOT NULL DEFAULT 'user', note TEXT,
  ts REAL NOT NULL, PRIMARY KEY(project_id, key_type, key));
"""

RELATIONSHIP_ROLES = ("CUSTOMER", "PROSPECT", "SUPPLIER", "PARTNER",
                      "SERVICE_PROVIDER", "EMPLOYEE", "CONTRACTOR",
                      "OTHER_BUSINESS", "PERSONAL", "MARKETING", "IGNORE")


def _org_identity(project_id: str) -> dict:
    """The configured 'who is us' for a project, merged with every connected
    Gmail account so the mailbox owner is always part of SELF."""
    raw = ENT.setting(project_id, "org_identity")
    ident = {"company_name": None, "emails": [], "domains": []}
    if raw:
        try:
            d = json.loads(raw)
            ident["company_name"] = d.get("company_name") or None
            ident["emails"] = [str(x).lower() for x in d.get("emails", []) if x]
            ident["domains"] = [str(x).lower().lstrip("@") for x in d.get("domains", []) if x]
        except Exception:
            pass
    for r in STORE.db.execute(
            "SELECT oc.account FROM oauth_creds oc JOIN connectors c ON c.id=oc.connector_id "
            "WHERE c.project_id=? AND oc.account IS NOT NULL", (project_id,)):
        a = (r["account"] or "").lower()
        if a and a not in ident["emails"]:
            ident["emails"].append(a)
    return ident


def _relationship_overrides(project_id: str) -> dict:
    """{('domain'|'email'|'entity', key): role}"""
    out = {}
    for r in STORE.db.execute(
            "SELECT key_type, key, role FROM relationship_overrides WHERE project_id=?",
            (project_id,)):
        out[(r["key_type"], r["key"])] = r["role"]
    return out


def _role_for(project_id: str, email: str | None = None,
              entity_id: str | None = None, overrides: dict | None = None) -> str | None:
    """User corrections first (they are ground truth about the relationship),
    else None — we do not guess roles."""
    ov = overrides if overrides is not None else _relationship_overrides(project_id)
    if entity_id and ("entity", entity_id) in ov:
        return ov[("entity", entity_id)]
    if email:
        e = email.lower()
        if ("email", e) in ov:
            return ov[("email", e)]
        dom = e.split("@")[-1]
        if ("domain", dom) in ov:
            return ov[("domain", dom)]
    return None
STORE.db.executescript(FACT_DECISION_SCHEMA)
try:  # idempotent migration: fine-grained category on classification records
    STORE.db.execute("ALTER TABLE message_classifications ADD COLUMN category TEXT")
except Exception:
    pass
STORE.db.commit()

# ── semantic LLM layer (proposes; the frozen engine decides) ────────────────
import semantic as _semantic
STORE.db.executescript(_semantic.SEMANTIC_ANALYSES_SCHEMA)
STORE.db.commit()
import recall as _recall
SCOPES = _recall.ScopeStore(STORE.db)
import consolidation as _consol
import conflict as _conflict
import graph as _graph
import brief as _brief
import candidate_index as _cand_index
STORE.db.executescript(_cand_index.INDEX_SCHEMA)
STORE.db.commit()
STORE.db.executescript(_graph.GRAPH_SCHEMA)
STORE.db.commit()
INGEST.on_edge = lambda pid, aid, s, rel, d: _graph.record_edge(STORE.db, pid, aid, s, rel, d)
STORE.db.executescript(_consol.P3_SCHEMA)
STORE.db.commit()
INGEST.on_reinforce = lambda pid, aid, agent, source: _consol.reinforce(
    STORE.db, pid, aid, agent, source)


def _consolidate_all_projects():
    for pid, p in list(PROJECTS.items()):
        if p.is_demo:
            continue
        _consol.consolidate(p, STORE.db, SCOPES, record, _mint_global,
                            contradictions=CONTRADICTIONS.get(pid, []))





def _clamp_limit(raw, default: int, maximum: int = 1000) -> int:
    """Bound a caller-supplied list limit to [1, maximum] (P8 hardening: an
    authenticated caller must not request unbounded work). Malformed -> default."""
    try:
        n = int(raw)
    except (TypeError, ValueError):
        return default
    if n < 1:
        return default
    return min(n, maximum)


def _key_bound_agent(auth) -> str | None:
    """The agent an API key is bound to, or None for an unbound key / session.
    A bound key makes agent-private scope a real security boundary: requests on
    that key are forced to its agent and cannot impersonate another."""
    if auth and "key" in auth:
        return (auth["key"] or {}).get("agent_id")
    return None


def _viewer_scope_ok(pid: str, assertion_id: str, viewer: str | None,
                     acting_user: str | None = None) -> bool:
    """Scope check for agent-parameterized reads. Reads WITHOUT a viewer are
    the human control plane (org operators) and see org-scope plus everything
    — governance requires it; agent-facing paths always pass a viewer."""
    scope = SCOPES.of(pid, assertion_id)
    if viewer is None:
        return True
    teams = SCOPES.teams_of(pid, viewer)
    return SCOPES.visible(scope, viewer, teams, acting_user)


def _memories_for_entities(project_id: str, entity_ids: list[str]) -> list[dict]:
    """Open beliefs about these entities, given to the model as context so it
    can recognise confirmations, changes and reversals (§existing memory)."""
    p = PROJECTS.get(project_id)
    if p is None or not entity_ids:
        return []
    wanted = set(entity_ids)
    T = p.now()
    out = []
    for a in p.engine.store.assertions():
        if getattr(a, "is_retraction", False) or not (set(a.subjects) & wanted):
            continue
        try:
            if not p.engine.ledger.is_open_at(a, T):
                continue
        except Exception:
            continue
        out.append({"subject": next(iter(set(a.subjects) & wanted)),
                    "proposition": a.proposition, "since": a.assertion_time})
        if len(out) >= 20:
            break
    return out


def _semantic_sink_for(project_id: str, connector_id: str, model_name: str):
    """Persists each analysed email's decision (reasoning summary, rejection
    reason, dropped candidates) — the observability the model owes us. Source
    id is recomputed from the connector + message id, matching ingest."""
    def sink(payload: dict, analysis: dict, raw: str):
        ext_id = payload.get("message_id") or payload.get("external_id") or ""
        row = STORE.db.execute(
            "SELECT id FROM source_records WHERE connector_id=? AND external_id=?",
            (connector_id, ext_id)).fetchone()
        srid = row["id"] if row else f"obs:{ext_id}"
        try:
            STORE.db.execute(
                "INSERT INTO semantic_analyses(project_id, source_record_id, "
                "business_relevance, memory_candidate, rejection_reason, "
                "reasoning_summary, candidates, dropped, model, error, ts) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (project_id, srid,
                 analysis.get("business_relevance"),
                 1 if analysis.get("memory_candidate") else 0,
                 analysis.get("rejection_reason"),
                 analysis.get("reasoning_summary"),
                 len(analysis.get("candidates") or []),
                 json.dumps(analysis.get("dropped") or [])[:2000],
                 model_name, analysis.get("error"), time.time()))
            STORE.db.commit()
        except Exception:
            pass  # observability must never break ingestion
    return sink


def _semantic_extractor_for(conn: dict, owner_identity: dict):
    """The LLM-primary Gmail extractor with full context wiring. Only built
    when a REAL provider is configured and the project enabled it; the
    deterministic ContextualBusinessExtractor is both fallback and guard."""
    pid = conn.get("project_id")
    from extraction import ContextualBusinessExtractor
    fallback = ContextualBusinessExtractor(owner_identity)
    model = ENT.setting(pid, "llm_model")
    cl = providers.OpenAICompatClient(
        usage_cb=lambda m, t: ENT.meter(pid, "llm_tokens", t))
    if model:
        cl.model = model
    return _semantic.SemanticGmailExtractor(
        cl, owner_identity,
        role_lookup=lambda email, _p=pid: _role_for(_p, email=email),
        thread_lookup=lambda thread_id, external_id, _p=pid:
            CLASSIFICATIONS and thread_context_for(STORE.db, _p, thread_id) or "",
        memories_lookup=lambda entity_ids, _p=pid: _memories_for_entities(_p, entity_ids),
        analysis_sink=_semantic_sink_for(pid, conn.get("id") or "", getattr(cl, "model", "?")),
        fallback=fallback)


def _owner_email_for(connector_id: str) -> str | None:
    creds = OAUTH.get(connector_id)
    return (creds or {}).get("account")


def _owner_identity_for(conn: dict) -> dict:
    """Full org identity for the connector's project (configured identity +
    the connected mailbox address)."""
    ident = _org_identity(conn["project_id"]) if conn.get("project_id") else \
        {"company_name": None, "emails": [], "domains": []}
    acct = _owner_email_for(conn["id"]) if conn.get("id") else None
    if acct and acct.lower() not in ident["emails"]:
        ident["emails"].append(acct.lower())
    return ident


def _quality_gate(project_id, conn, payload, facts, verdict, source_record_id):
    """Grade candidates; persist every decision; return only HIGH/MEDIUM facts."""
    from email_analysis import analyze
    from extraction import memory_quality
    owner = _owner_identity_for(conn)
    scores = (verdict or {}).get("scores", {}) if isinstance(verdict, dict) else {}
    analysis = analyze(payload, owner,
                       business_score=scores.get("business", 0.0),
                       automated_score=scores.get("automated", 0.0),
                       business_signals=(verdict or {}).get("signals", []) if verdict else [])
    # record the fine category on the classification row (real data, no guess)
    try:
        STORE.db.execute(
            "UPDATE message_classifications SET category=? WHERE source_record_id=?",
            (analysis["category"], source_record_id))
    except Exception:
        pass
    kept = []
    for f in facts:
        f_analysis = analysis
        if f.get("reasoning_summary") is not None:
            # Semantic-layer fact: the model read the FULL email. A blunt
            # category label ("this looks like marketing") may not kill a
            # candidate whose evidence is a verbatim quote of genuine business
            # prose — the §mixed case (marketing footer + real discussion in
            # one mail). It becomes a penalty the candidate must overcome.
            # The saas_self block stays absolute: notifications about the
            # owner's own account are never relationship memory.
            if (analysis.get("is_noise_category") or
                    analysis.get("marketing_score", 0) >= 0.9) and \
                    not analysis.get("saas_self_notification"):
                f_analysis = dict(analysis)
                f_analysis["is_noise_category"] = False
                f_analysis["marketing_score"] = min(
                    analysis.get("marketing_score", 0), 0.89)
            f = dict(f)
            f["confidence"] = max(0.0, float(f.get("confidence") or 0) - (
                0.25 if f_analysis is not analysis else 0.0))
            f_verdict = verdict if isinstance(verdict, dict) else None
            if f.get("business_relevance") in ("high", "medium"):
                # The model read the whole email; its relevance judgment stands
                # in for the keyword category/verdict it escalated past. The
                # confidence penalty above still applies when noise flags were
                # overridden — the model must EARN the storage.
                if not f_analysis.get("is_business_category"):
                    if f_analysis is analysis:
                        f_analysis = dict(analysis)
                    f_analysis["is_business_category"] = True
                    f_analysis["category"] = f_analysis.get("category") or "SEMANTIC_BUSINESS"
                if f_verdict and f_verdict.get("classification") in ("NON_BUSINESS", "AUTOMATED_NOISE"):
                    f_verdict = None  # escalated past the blunt verdict; graded on merits
        q = memory_quality(f, f_analysis,
                           f_verdict if f.get("reasoning_summary") is not None
                           else (verdict if isinstance(verdict, dict) else None))
        if f.get("reasoning_summary"):
            q["reasons"] = list(q["reasons"]) + [f"Model: {f['reasoning_summary'][:180]}"]
        stored = q["quality"] in ("HIGH_CONFIDENCE_MEMORY", "MEDIUM_CONFIDENCE_MEMORY")
        STORE.db.execute(
            "INSERT INTO fact_decisions(project_id,connector_id,source_record_id,"
            "subject,proposition,speech_act,quality,score,reasons,category,stored,evidence,ts) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (project_id, conn["id"], source_record_id,
             f.get("subject", {}).get("id", ""), f.get("proposition", ""),
             f.get("speech_act"), q["quality"], q["score"],
             json.dumps(q["reasons"]), analysis["category"],
             1 if stored else 0, (f.get("evidence") or "")[:400], time.time()))
        if stored:
            kept.append(f)
    STORE.db.commit()
    return kept


INGEST.quality_gate = _quality_gate
INGEST.semantic_active = lambda pid: (ENT.setting(pid, "llm_enabled") == "1"
                                      and providers.llm_configured())
SCHEDULER = Scheduler(INGEST)
SCHEDULER.consolidator = _consolidate_all_projects
SCHEDULER.consolidation_interval = 300
SCHEDULER.backup_manager = None  # set post-BACKUPS init below
ENT = Enterprise(STORE.db)
# ── self-healing subsystem (infrastructure singletons) ──────────────────────
import healing as HEAL
HEAL_ACTIONS = HEAL.default_action_registry()   # built-in low-risk repairs
HEAL_COMPONENTS = HEAL.ComponentRegistry()      # agents register their components
HEAL_STORE = HEAL.HealingStore(STORE.db)
from security import RateLimiter, OAuthStateStore, totp_secret, totp_code, totp_verify
from backups import BackupManager
AUTH_LIMITER = RateLimiter(capacity=5, refill_per_sec=0.2)

# P9.4: per-tenant rate limit for authenticated DATA endpoints. Protects against
# an authenticated caller exhausting server resources with expensive recall /
# brief / graph / conflict operations. This is a DEFAULT, not a product policy:
# the burst/sustained numbers below are a sensible starting point and are meant
# to be overridden per-plan via governance (P9.5). Env-tunable so ops can adjust
# without a code change. Keyed by (project, api-key) so one tenant/key cannot
# starve others; sessions (human operators) are keyed by user.
_TENANT_RL_CAPACITY = float(os.environ.get("OMEM_TENANT_RL_BURST", "60"))
_TENANT_RL_REFILL = float(os.environ.get("OMEM_TENANT_RL_RPS", "20"))
TENANT_LIMITER = RateLimiter(capacity=_TENANT_RL_CAPACITY, refill_per_sec=_TENANT_RL_REFILL)


class _Metrics:
    """Tiny in-process operational counters. Not a metrics platform — just the
    highest-value signals an operator needs (request volume, rate-limit
    rejections, auth failures, and coarse latency) exposed via /v1/observability.
    In-process only: correct for a single node; a multi-node deployment would
    scrape each instance. Thread-safe via a lock; bounded memory (fixed keys)."""
    def __init__(self):
        import threading as _th
        self._lock = _th.Lock()
        self.boot_time = time.time()
        self.requests_total = 0
        self.rate_limited_total = 0        # 429s from the tenant limiter
        self.auth_failures_total = 0       # 401s
        self.authz_denials_total = 0       # 403s
        self.errors_5xx_total = 0
        self._latency_sum = 0.0            # seconds, for a running mean
        self._latency_count = 0
        self._latency_max = 0.0

    def record_request(self, seconds, status):
        with self._lock:
            self.requests_total += 1
            self._latency_sum += seconds
            self._latency_count += 1
            if seconds > self._latency_max:
                self._latency_max = seconds
            if status == 429:
                self.rate_limited_total += 1
            elif status == 401:
                self.auth_failures_total += 1
            elif status == 403:
                self.authz_denials_total += 1
            elif status >= 500:
                self.errors_5xx_total += 1

    def snapshot(self):
        with self._lock:
            mean_ms = (self._latency_sum / self._latency_count * 1000.0) if self._latency_count else 0.0
            return {
                "uptime_seconds": round(time.time() - self.boot_time, 1),
                "requests_total": self.requests_total,
                "rate_limited_total": self.rate_limited_total,
                "auth_failures_total": self.auth_failures_total,
                "authz_denials_total": self.authz_denials_total,
                "errors_5xx_total": self.errors_5xx_total,
                "latency_ms_mean": round(mean_ms, 2),
                "latency_ms_max": round(self._latency_max * 1000.0, 2),
            }


METRICS = _Metrics()

# P9.4: per-field text cap for observe/learn. A single interaction/learn text far
# above this is abuse (drives extraction cost), not a real message. 100 KB is
# generous for legitimate content; env-tunable.
MAX_TEXT_CHARS = int(os.environ.get("OMEM_MAX_TEXT_CHARS", str(100_000)))
BACKUPS = BackupManager(STORE.db)
SCHEDULER.backup_manager = BACKUPS
STORE.apply_hardening()  # all module schemas now exist; FKs/indexes can apply


def _backfill_owner_memberships():
    """Organisations created before RBAC existed have no membership rows, which
    locks their creator out of member/audit/retention management. Grant the
    recorded org owner the owner role once, idempotently."""
    granted = []
    try:
        rows = STORE.db.execute(
            "SELECT id, user_id FROM orgs WHERE user_id IS NOT NULL").fetchall()
    except Exception:
        return granted
    for r in rows:
        if not ENT.role_of(r["id"], r["user_id"]):
            ENT.set_role(r["id"], r["user_id"], "owner")
            granted.append((r["id"], r["user_id"]))
    return granted


_BACKFILLED = _backfill_owner_memberships()
OAUTH_STATE = OAuthStateStore()

# NOTE: extractor selection lives in _extractor_for() above and is project-aware
# (Settings -> Extraction). An earlier global override here forced the LLM on
# every connector whenever OMEM_LLM_API_KEY existed, ignoring per-project config
# and raising KeyError when the caller passed no project_id. Removed.


def _mint_global(prefix):
    import uuid as _u
    return f"{prefix}_{_u.uuid4().hex[:10]}"


INGEST.mint = _mint_global
boot()

# ── Memory scanner (initialised after boot so project objects exist) ─────────
from memory_scanner import MemoryScanner

# _scanner_for() creates a per-request scanner bound to the live project.
# The scanner only needs DB + project; classifier and record_fn are injected
# so it can apply corrections through the frozen retract path.
def _scanner_for(project) -> MemoryScanner:
    def _plain_classify(payload):
        from classifier import classify as _cls
        return _cls(payload)
    def _identity(connector_id):
        conn = STORE.db.execute("SELECT id, project_id FROM connectors WHERE id=?",
                                (connector_id,)).fetchone()
        return _owner_identity_for(dict(conn)) if conn else None
    return MemoryScanner(
        db=STORE.db,
        project=project,
        classifier_fn=_plain_classify,
        record_fn=record,
        mint_fn=_mint_global,
        identity_fn=_identity,
    )

# demo: a connector with three inbound tickets, fully processed, so the demo
# project shows real ingested memory with source provenance (labeled demo).
def _seed_ingestion_demo():
    if "demo" not in PROJECTS or INGEST.connectors_for("demo"):
        return
    p = PROJECTS["demo"]
    conn = INGEST.add_connector("demo", "support_inbox", "Support Inbox (demo)",
        {"items": [
            {"customer": "alice", "subject": "Re: contact preference", "body": "please prefer email going forward", "at": "now"},
            {"customer": "carol", "subject": "Upgrade question", "body": "we want to upgrade to annual billing", "at": "now"},
            {"customer": "dave", "subject": "Cancelation", "body": "considering to cancel our plan", "at": "now"},
        ]}, agent_id="connector:support-inbox", authority=0.7)
    INGEST.poll_connector(conn["id"])
    INGEST.process_pending("demo")

if os.environ.get("OMEM_SEED_DEMO", "0") == "1":
    _seed_ingestion_demo()



# ── Response shaping (assembles frozen-query results; no new semantics) ──────
def shape_assertion(p: Project, aid: str, T: int | None = None) -> dict:
    """Assemble a UI assertion object entirely from the engine's own records."""
    e = p.engine
    a = e.store.assertion(aid)
    if a is None:
        return None
    T = p.now() if T is None else T
    close = e.ledger.close_time(aid)
    open_now = e.ledger.is_open_at(a, T)
    prov_ids, grounded = e.provenance(aid)
    lbl = p.labels.get(aid, {})
    return {
        "id": a.id,
        "label": lbl.get("label"),
        "agent": a.agent,
        "subjects": list(a.subjects),
        "proposition": a.proposition,
        "assertion_time": a.assertion_time,
        "event_time": a.event_time,
        "confidence": a.confidence,
        "belief_interval": {"start": a.assertion_time, "end": close},
        "open": open_now,
        "grounded": grounded,
        "provenance_count": len(prov_ids),
        "is_retraction": a.proposition == RETRACTED,
        "object": "assertion",
    }


def shape_entity(p: Project, eid: str) -> dict:
    lbl = p.labels.get(eid, {})
    ent = p.engine.store.entity(eid)
    return {"id": eid, "type": getattr(ent, "type", lbl.get("type")),
            "label": lbl.get("label"), "object": "entity"} if ent else None


def shape_agent(p: Project, aid: str) -> dict:
    lbl = p.labels.get(aid, {})
    ag = p.engine.store.agent(aid)
    return {"id": aid, "kind": getattr(ag, "kind", lbl.get("agent_kind")),
            "label": lbl.get("label"),
            "recorded_existence": getattr(ag, "recorded_existence", 0),
            "object": "agent"} if ag else None


def shape_event(p: Project, vid: str) -> dict:
    lbl = p.labels.get(vid, {})
    ev = p.engine.store.event(vid)
    return {"id": vid, "kind": getattr(ev, "kind", lbl.get("event_kind")),
            "label": lbl.get("label"), "event_time": getattr(ev, "event_time", None),
            "object": "event"} if ev else None


# ── HTTP handler ─────────────────────────────────────────────────────────────
class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):  # quiet
        pass

    def _close_conn_header(self):
        # Force connection close each request: avoids stdlib keep-alive blocking and
        # is fine for a dev API. Also set on every response via send_header below.
        self.close_connection = True

    def _security_headers(self):
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Correlation-Id", getattr(self, "_cid", "") or self._corr())

    def _send(self, code, body=None):
        # P9.6: record operational metrics at the single response choke point.
        try:
            _start = getattr(self, "_req_start", None)
            if _start is not None and not getattr(self, "_metrics_recorded", False):
                METRICS.record_request(time.perf_counter() - _start, code)
                self._metrics_recorded = True
        except Exception:
            pass
        try:
            payload = b"" if body is None else json.dumps(body).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET,POST,DELETE,OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type,Authorization")
            self.send_header("OMEM-Protocol", "1.0")
            self.send_header("OMEM-CTS-Digest", "cts-v1-29")
            self._security_headers()
            self.send_header("Connection", "close")
            self.close_connection = True
            self.end_headers()
            if payload:
                self.wfile.write(payload)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _err(self, code, typ, message, reason_code=None, param=None):
        self._send(code, {"error": {
            "type": typ, "reason_code": reason_code, "message": message,
            "param": param,
            "doc_url": (f"https://docs.omem.dev/errors/{reason_code}" if reason_code else None),
            "request_id": "req_" + uuid.uuid4().hex[:16]}})

    MAX_BODY_BYTES = int(os.environ.get("OMEM_MAX_BODY_BYTES", str(1_000_000)))  # 1 MB default

    def _body(self):
        try:
            n = int(self.headers.get("Content-Length", 0) or 0)
        except (TypeError, ValueError):
            return {}
        if n <= 0:
            return {}
        # P9.4: reject oversized bodies rather than silently truncating. 1 MB is
        # ample for observe/recall/brief payloads; env-tunable for unusual needs.
        if n > self.MAX_BODY_BYTES:
            self._oversized = True
            try:  # drain a bounded amount so the socket stays consistent
                self.rfile.read(min(n, self.MAX_BODY_BYTES + 1))
            except Exception:
                pass
            return {}
        try:
            return json.loads(self.rfile.read(n) or b"{}")
        except Exception:
            return {}

    PUBLIC = {("v1","health"), ("v1","signup"), ("v1","session")}

    def _effective_agent(self, auth, requested):
        """Resolve the agent identity for this request.
        - Unbound key / session: the caller-supplied value is used as before
          (backward compatible; agent scope is an organizing boundary).
        - Agent-bound key: the key's agent is authoritative. A missing caller
          value is filled in; a MISMATCHED caller value is rejected (403) so a
          bound key cannot impersonate another agent. Returns (agent, error_sent).
        """
        bound = _key_bound_agent(auth)
        if bound is None:
            return requested, False
        if requested is not None and requested != bound:
            self._err(403, "permission",
                      "This API key is bound to a specific agent and cannot act as another.")
            return None, True
        return bound, False

    def _auth(self):
        """Returns {'user':..} for sessions or {'key':..} for API keys, else None."""
        h = self.headers.get("Authorization", "")
        if not h.startswith("Bearer "):
            return None
        tok = h[7:].strip()
        if tok.startswith("omem_sess_"):
            u = STORE.user_for_session(tok)
            return {"user": u} if u else None
        if tok.startswith("omem_sk_"):
            k = STORE.key_lookup(tok)
            return {"key": k} if k else None
        return None

    def _meter_request(self, parts, qs):
        pid = qs.get("project", [None])[0]
        if pid and PROJECTS.get(pid):
            try:
                ENT.meter(pid, "api_requests")
                if len(parts) >= 3 and parts[1] == "queries":
                    ENT.meter(pid, "agent_queries")
                if len(parts) == 4 and parts[3] == "why":
                    ENT.meter(pid, "provenance_queries")
            except Exception:
                pass

    def _observability(self):
        # real counts from the SaaS tables — no synthetic metrics
        db = STORE.db
        def c(sql, *a):
            return db.execute(sql, a).fetchone()[0]
        return {
            "projects": c("SELECT COUNT(*) FROM projects"),
            "source_records": c("SELECT COUNT(*) FROM source_records"),
            "jobs_pending": c("SELECT COUNT(*) FROM ingest_jobs WHERE state='pending'"),
            "jobs_dead": c("SELECT COUNT(*) FROM ingest_jobs WHERE state='dead'"),
            "audit_events": c("SELECT COUNT(*) FROM audit_events"),
            "scheduler_runs": SCHEDULER.runs,
            "queue_depth": c("SELECT COUNT(*) FROM ingest_jobs WHERE state IN ('pending','retrying')"),
            "backup": {"failing": BACKUPS.status()["failing"],
                        "last_successful": (BACKUPS.status()["last_successful"] or {}).get("started")},
            "providers": {
                "google": providers.google_configured(),
                "llm": providers.llm_configured(),
                "stripe": providers.stripe_configured(),
            },
            # P9.6 additions: runtime metrics, DB health, and abuse-control config
            "runtime": METRICS.snapshot(),
            "database": {
                "backend": type(db).__name__,
                "reachable": self._db_reachable(),
            },
            "rate_limit": {
                "tenant_burst": _TENANT_RL_CAPACITY,
                "tenant_rps": _TENANT_RL_REFILL,
                "rate_limited_total": METRICS.snapshot()["rate_limited_total"],
            },
            "projection_drift": {pid: v.get("repaired", {})
                                 for pid, v in PROJECTION_DRIFT.items()},
        }

    def _db_reachable(self):
        try:
            STORE.db.execute("SELECT 1")
            return True
        except Exception:
            return False

    def _guard(self, parts, qs):
        """401 without credentials; 403 when a key targets a foreign project;
        403 when a session targets a project outside the user's org (demo is shared).
        Auth endpoints are rate limited per client IP. The Stripe webhook is
        public by design: its HMAC signature is the authentication."""
        if parts == ["v1", "billing", "webhook"]:
            return "public"
        if parts[:3] == ["oauth", "gmail", "callback"]:
            return "public"  # browser redirect from Google; signed state is the auth
        if tuple(parts[:2]) in self.PUBLIC:
            if parts[:2] in (["v1", "signup"], ["v1", "session"]):
                ip = self.client_address[0] if self.client_address else "unknown"
                if not AUTH_LIMITER.allow(f"{ip}:{parts[1]}"):
                    self._err(429, "rate_limited", "Too many attempts. Slow down.")
                    return None
            return "public"
        auth = self._auth()
        if auth is None:
            self._err(401, "authentication", "Missing or invalid credentials. Pass Authorization: Bearer <session or API key>.")
            return None
        self._meter_request(parts, qs)
        pid = qs.get("project", [None])[0]
        if "key" in auth:
            if pid and pid != auth["key"]["project_id"]:
                self._err(403, "permission", "This API key is scoped to a different project.")
                return None
            if not pid:
                qs["project"] = [auth["key"]["project_id"]]
        elif "user" in auth and pid:
            if not STORE.user_can_access(auth["user"]["id"], pid):
                self._err(403, "permission", "You do not have access to this project.")
                return None
        # P9.4: per-tenant data-endpoint rate limit. Applied to authenticated,
        # project-scoped requests (the expensive surface). Keyed by project + the
        # specific credential so one key can't exhaust the server or starve other
        # tenants. Non-project/admin/public routes are unaffected.
        rl_pid = qs.get("project", [None])[0]
        if rl_pid:
            if "key" in auth:
                rl_key = f"{rl_pid}:k:{auth['key'].get('id', '?')}"
            elif "user" in auth:
                rl_key = f"{rl_pid}:u:{auth['user'].get('id', '?')}"
            else:
                rl_key = f"{rl_pid}:anon"
            if not TENANT_LIMITER.allow(rl_key):
                self._err(429, "rate_limited",
                          "Too many requests for this project. Slow down and retry.")
                return None
        return auth

    def _intelligence(self, pid):
        """Enterprise memory intelligence. Every number is derived from the engine
        and the ops/source logs. Nothing synthesized."""
        p = PROJECTS.get(pid)
        if not p:
            return {}
        e = p.engine
        T = p.now()
        assertions = list(e.store.assertions())
        total = len(assertions)
        grounded = with_prov = 0
        for a in assertions:
            try:
                prov_ids, is_grounded = e.provenance(a.id)
                if is_grounded == "GROUNDED" or is_grounded is True:
                    grounded += 1
                if len(prov_ids) > 0:
                    with_prov += 1
            except Exception:
                pass
        conflicts = []
        seen = set()
        for pair in CONTRADICTIONS.get(pid, []):
            for a in assertions:
                if a.proposition == pair[0]:
                    key = (tuple(a.subjects), pair[0])
                    if key in seen:
                        continue
                    if e.proposition_state(list(a.subjects), pair[0], T) == "CONTRADICTED":
                        conflicts.append({"subjects": list(a.subjects), "proposition": pair[0]})
                        seen.add(key)
        conns = INGEST.connectors_for(pid)
        istats = INGEST.stats(pid)
        return {
            "memory_health": {
                "total_assertions": total,
                "grounding_coverage": round(grounded / total, 3) if total else 0,
                "provenance_coverage": round(with_prov / total, 3) if total else 0,
                "unresolved_conflicts": len(conflicts),
            },
            "conflicts": conflicts,
            "ingestion": istats,
            "sources": [{"name": c["name"], "kind": c["kind"], "authority": c["authority"],
                         "status": c["status"], "last_run": c["last_run"]} for c in conns],
        }

    def _corr(self):
        return self.headers.get("X-Correlation-Id") or uuid.uuid4().hex[:12]

    def _is_readonly_key(self, auth):
        """A key explicitly created with role='viewer' is read-only (P9.7).
        Sessions and non-viewer keys are unaffected. Backward-compatible:
        keys default to 'developer', so existing keys keep write access."""
        return ("key" in auth
                and (auth["key"].get("role") or "developer").lower() == "viewer")

    def _require(self, auth, permission, org_id, project_id=None):
        """Enforce RBAC. Session callers resolve their org role. API keys are
        project-scoped and now honor their STORED role (P9.7): previously every
        key acted developer-equivalent regardless of keys.role — a 'viewer' key
        could still write. A key's role gates its permissions within its project.
        Unknown/legacy roles default to developer for backward compatibility."""
        if "key" in auth:
            # permissions a key may hold, by role. 'developer' == the prior
            # fixed behavior (unchanged); 'viewer' is read-only; 'admin'/'owner'
            # keys additionally manage keys/connectors within their project.
            READ = {"memory.read", "project.read", "usage.read", "heal.read"}
            WRITE = READ | {"memory.write", "heal.report", "heal.execute.low"}
            MANAGE = WRITE | {"connector.manage", "key.create", "key.revoke",
                              "heal.execute.medium"}
            ADMIN = MANAGE | {"heal.execute.high"}
            role = (auth["key"].get("role") or "developer").lower()
            if role == "viewer":
                allowed = READ
            elif role in ("developer", "member"):
                allowed = WRITE | {"connector.manage", "key.create", "key.revoke"}
            elif role in ("admin", "owner"):
                allowed = ADMIN
            else:
                allowed = MANAGE  # legacy/unknown -> prior behavior
            return permission in allowed
        role = ENT.role_of(org_id, auth["user"]["id"]) if org_id else None
        return role_allows(role or "", permission)

    def _is_operator(self, auth):
        """Internal operator console guard. NOT customer-facing: only emails listed
        in OMEM_ADMIN_EMAILS may access /v1/admin/*."""
        admins = {e.strip() for e in os.environ.get("OMEM_ADMIN_EMAILS", "").split(",") if e.strip()}
        return "user" in auth and auth["user"]["email"] in admins

    def _org_of_project(self, pid):
        p = STORE.project(pid)
        return p["org_id"] if p else None

    def _healing_actor(self, auth):
        """Stable actor id for audit/claim ownership. Agent-bound keys use their
        agent; sessions use the user id; unbound keys use the key id."""
        if "key" in auth:
            return _key_bound_agent(auth) or ("key:" + str(auth["key"].get("id", "unknown")))
        if "user" in auth:
            return "user:" + str(auth["user"]["id"])
        return "unknown"

    def _make_healer(self, can_fn):
        """Build a Healer bound to this request's authorization. Reuses the shared
        action + component registries and the shared healing store; the policy is
        bound to the caller's permissions so RBAC is enforced per request."""
        policy = HEAL.Policy(HEAL_ACTIONS, can_fn)
        audit = lambda action, resource=None, metadata=None: ENT.audit(
            action, actor=None, resource=resource, metadata=metadata)
        return HEAL.Healer(HEAL_STORE, HEAL_ACTIONS, HEAL_COMPONENTS, policy, audit_fn=audit)

    def resolver_enabled(self):
        return RESOLVER is not None

    def _proj(self, qs):
        pid = (qs.get("project", ["demo"])[0])
        return PROJECTS.get(pid)

    def _T(self, qs, p):
        v = qs.get("as_of", [None])[0]
        if v is None or v == "now":
            return p.now()
        try:
            return int(v)
        except ValueError:
            return p.now()

    def _logreq(self, p, method, path, status, summary, reason=None):
        p.log.insert(0, {"id": "log_" + uuid.uuid4().hex[:10], "ts": time.time(),
                         "method": method, "path": path, "status": status,
                         "summary": summary, "reason_code": reason})
        p.log[:] = p.log[:500]

    def do_OPTIONS(self):
        self._send(204)

    # ---- GET ----
    def do_GET(self):
        self._req_start = time.perf_counter(); self._metrics_recorded = False
        u = urlparse(self.path)
        parts = [x for x in u.path.split("/") if x]
        qs = parse_qs(u.query)
        try:
            auth = self._guard(parts, qs)
            if auth is None:
                return
            self._route_get(parts, qs, u, auth)
        except Rejected as r:
            self._err(422, "invalid_request", str(r), reason_code=r.code)
        except Exception as ex:
            self._err(500, "server", f"{type(ex).__name__}: {ex}")

    def _route_get(self, parts, qs, u, auth):
        # ── self-healing reads (RBAC-gated, project-scoped) ──
        if len(parts) >= 2 and parts[0] == "v1" and parts[1] == "healing":
            p = self._proj(qs)
            if p is None:
                return self._err(404, "not_found", "project not found")
            org_id = self._org_of_project(p.id)
            if not self._require(auth, "heal.read", org_id, p.id):
                return self._err(403, "permission", "requires heal.read")
            # GET /v1/healing/health
            if parts[2:] == ["health"]:
                return self._send(200, HEAL_STORE.health(org_id, p.id))
            # GET /v1/healing/failures[?component=]
            if parts[2:] == ["failures"]:
                comp = qs.get("component", [None])[0]
                return self._send(200, {"data": HEAL_STORE.failures(org_id, p.id, component=comp)})
            # GET /v1/healing/failures/{id} -> failure + diagnosis/recovery history
            if len(parts) == 4 and parts[2] == "failures":
                fid = parts[3]
                failure = HEAL_STORE.failure(org_id, p.id, fid)
                if not failure:
                    return self._err(404, "not_found", "failure not found")
                return self._send(200, {"failure": failure,
                                        "recoveries": HEAL_STORE.recoveries_for(org_id, p.id, fid)})
            return self._err(404, "not_found", "unknown healing route")
        # /v1/health
        if parts == ["v1", "health"]:
            # P9.6: a REAL readiness probe (load balancers / k8s rely on this),
            # not a static string. Checks DB reachability and surfaces degraded
            # conditions. Returns 200 when ready, 503 when a hard dependency
            # (the database) is unreachable.
            db_ok = True
            db_error = None
            try:
                STORE.db.execute("SELECT 1")
            except Exception as ex:
                db_ok = False
                db_error = f"{type(ex).__name__}"
            backup_failing = False
            try:
                backup_failing = bool(BACKUPS.status().get("failing"))
            except Exception:
                pass
            ready = db_ok
            status = "ok" if ready else "unavailable"
            if ready and backup_failing:
                status = "degraded"
            body = {
                "status": status,
                "ready": ready,
                "checks": {
                    "database": {"ok": db_ok, "backend": type(STORE.db).__name__,
                                 **({"error": db_error} if db_error else {})},
                    "backups": {"ok": not backup_failing},
                },
                "uptime_seconds": METRICS.snapshot()["uptime_seconds"],
                "protocol": "1.0",
            }
            return self._send(200 if ready else 503, body)
        # ── Google redirects the BROWSER here after consent ──
        if parts == ["oauth", "gmail", "callback"] or parts == ["v1", "oauth", "gmail", "callback"]:
            code = qs.get("code", [None])[0]
            state = qs.get("state", [None])[0]
            verified = OAUTH_STATE.verify(state) if state else None
            if not code or not verified:
                return self._send(400, {"connected": False,
                                        "error": "Missing code or invalid/expired OAuth state."})
            cid = verified["connector_id"]
            try:
                tok = providers.google_exchange_code(code)
            except Exception as ex:
                return self._send(502, {"connected": False,
                                        "error": f"Google token exchange failed: {ex}"})
            OAUTH.save(cid, "gmail", tok.get("access_token"), tok.get("refresh_token"),
                       time.time() + tok.get("expires_in", 3600),
                       tok.get("scope", "gmail.readonly"), "")
            INGEST.db.execute("UPDATE connectors SET status='active' WHERE id=?", (cid,))
            INGEST.db.commit()
            INGEST.clear_connector_errors(cid)  # a successful reconnect clears stale failures
            ENT.audit("connector.connected", resource=cid, metadata={"provider": "google"},
                      correlation_id=self._corr())
            # send the operator back to the dashboard
            self.send_response(302)
            self.send_header("Location", os.environ.get("OMEM_APP_URL", "http://localhost:3000") + "/sources?connected=gmail")
            self._security_headers()
            self.end_headers()
            return

        # ── connector oauth status ──
        if len(parts) == 4 and parts[:2] == ["v1", "connectors"] and parts[3] == "detail":
            d = INGEST.connector_detail(qs.get("project", [None])[0], parts[2])
            reset = RATE_LIMIT_RESETS.get(parts[2])
            if reset:
                d["rate_limit_reset"] = reset
            return self._send(200, d)
        if len(parts) == 4 and parts[:2] == ["v1", "connectors"] and parts[3] == "status":
            creds = OAUTH.get(parts[2])
            c = INGEST.connector(parts[2])
            # explicit integration-status state machine
            if c and c["status"] == "needs_reauth":
                st_label = "NEEDS_REAUTH"
            elif c and c["status"] == "not_configured":
                st_label = "NOT_CONFIGURED"
            elif c and c["status"] == "rate_limited":
                st_label = "RATE_LIMITED"
            elif not creds or creds["status"] == "disconnected":
                st_label = "DISCONNECTED"
            elif creds.get("expires") and creds["expires"] < time.time() and not creds.get("has_tokens"):
                st_label = "NEEDS_REAUTH"
            else:
                dead = STORE.db.execute(
                    "SELECT COUNT(*) c FROM ingest_jobs WHERE connector_id=? AND state='dead_lettered'",
                    (parts[2],)).fetchone()
                pend = STORE.db.execute(
                    "SELECT COUNT(*) c FROM ingest_jobs WHERE connector_id=? AND state IN ('pending','running','retrying')",
                    (parts[2],)).fetchone()
                st_label = "ERROR" if dead["c"] > 0 else ("SYNCING" if pend["c"] > 0 else "HEALTHY")
            processed = STORE.db.execute(
                "SELECT COUNT(*) c FROM ingest_jobs WHERE connector_id=? AND state='completed'", (parts[2],)).fetchone()
            return self._send(200, {"connected": bool(creds and creds["status"] == "connected"),
                                     "account": creds["account"] if creds else None,
                                     "status": st_label,
                                     "last_run": c["last_run"] if c else None,
                                     "messages_processed": processed["c"]})
        # ── entity resolution audit: why did X become this entity ──
        if len(parts) == 4 and parts[:2] == ["v1", "entities"] and parts[3] == "resolution":
            return self._send(200, {"data": RESOLVER.history_for(qs.get("project", ["demo"])[0], parts[2])})
        if parts == ["v1", "scheduler", "status"]:
            return self._send(200, {"runs": SCHEDULER.runs, "interval": SCHEDULER.interval})
        # ── ingestion: connectors ──
        if parts == ["v1", "connectors"]:
            return self._send(200, {"data": INGEST.connectors_for(qs.get("project", ["demo"])[0])})
        if parts == ["v1", "ingest", "stats"]:
            return self._send(200, INGEST.stats(qs.get("project", ["demo"])[0]))
        if parts == ["v1", "jobs"]:
            return self._send(200, {"data": INGEST.jobs_for(qs.get("project", ["demo"])[0])})
        if parts == ["v1", "ingest", "dead-letters"]:
            return self._send(200, {"data": INGEST.dead_letters(qs.get("project", ["demo"])[0])})
        if len(parts) == 4 and parts[:2] == ["v1", "assertions"] and parts[3] == "source":
            pid_s = qs.get("project", ["demo"])[0]
            src = INGEST.source_for_assertion(pid_s, parts[2])
            if not src:
                return self._send(200, {})
            conn = INGEST.connector(src["connector_id"])
            return self._send(200, {**src, "view": source_view(src, conn),
                                    "payload_json": json.loads(src["payload"])})
        if parts == ["v1", "intelligence"]:
            return self._send(200, self._intelligence(qs.get("project", ["demo"])[0]))

        # ── backups (operator) ──
        if parts == ["v1", "admin", "backups"]:
            if not self._is_operator(auth):
                return self._err(403, "permission", "Operator access only.")
            return self._send(200, BACKUPS.status())

        # ── internal operator console (founder-only; real DB counts) ──
        if parts[:2] == ["v1", "admin"]:
            if not self._is_operator(auth):
                return self._err(403, "permission", "Operator access only.")
            db = STORE.db
            def c(sql, *a):
                return db.execute(sql, a).fetchone()[0]
            if parts == ["v1", "admin", "metrics"]:
                import os as _os
                dbsize = _os.path.getsize(_os.environ.get("OMEM_DB", "data/omem.db")) if _os.path.exists(_os.environ.get("OMEM_DB", "data/omem.db")) else 0
                return self._send(200, {
                    "organizations": c("SELECT COUNT(*) FROM orgs"),
                    "users": c("SELECT COUNT(*) FROM users"),
                    "projects": c("SELECT COUNT(*) FROM projects"),
                    "api_requests": c("SELECT COALESCE(SUM(quantity),0) FROM usage_events WHERE metric='api_requests'"),
                    "assertions_created": c("SELECT COUNT(*) FROM ops WHERE kind='assert'"),
                    "recalls": c("SELECT COALESCE(SUM(quantity),0) FROM usage_events WHERE metric='agent_recalls'"),
                    "learn_calls": c("SELECT COALESCE(SUM(quantity),0) FROM usage_events WHERE metric='learn_requests'"),
                    "connected_sources": c("SELECT COUNT(*) FROM connectors"),
                    "source_records": c("SELECT COUNT(*) FROM source_records"),
                    "jobs": {s: c("SELECT COUNT(*) FROM ingest_jobs WHERE state=?", s)
                             for s in ["pending", "running", "completed", "retrying", "dead_lettered", "cancelled"]},
                    "audit_events": c("SELECT COUNT(*) FROM audit_events"),
                    "db_bytes": dbsize,
                    "scheduler_runs": SCHEDULER.runs,
                    "revenue_note": "estimated from billing_state plans; no Stripe verification",
                    "estimated_mrr": sum((PLANS.get(r["plan"], {}).get("price") or 0)
                                         for r in db.execute("SELECT plan FROM billing_state WHERE subscription_status IN ('active','trialing')")),
                })
            if len(parts) == 4 and parts[:3] == ["v1", "admin", "orgs"]:
                oid = parts[3]
                projs = [dict(r) for r in db.execute("SELECT id, name FROM projects WHERE org_id=?", (oid,))]
                detail = {"org": oid, "status": ENT.customer_status(oid), "projects": []}
                for pr in projs:
                    pid = pr["id"]
                    pp = PROJECTS.get(pid)
                    detail["projects"].append({
                        **pr,
                        "usage": ENT.usage(pid),
                        "jobs": {st: c("SELECT COUNT(*) FROM ingest_jobs WHERE project_id=? AND state=?", pid, st)
                                 for st in ["pending", "running", "completed", "retrying", "dead_lettered", "cancelled"]},
                        "dead_letters": [dict(r) for r in db.execute(
                            "SELECT id, last_error, attempts FROM ingest_jobs WHERE project_id=? AND state='dead_lettered' LIMIT 10", (pid,))],
                        "source_records": c("SELECT COUNT(*) FROM source_records WHERE project_id=?", pid),
                        "memories": sum(1 for _ in pp.engine.store.assertions()) if pp else 0,
                        "conflicts": len(CONTRADICTIONS.get(pid, [])),
                        "feedback": ENT.feedback_summary(pid),
                        "top_recalled": ENT.top_recalled(pid, 5),
                    })
                return self._send(200, detail)
            if parts == ["v1", "admin", "orgs"]:
                rows = db.execute("""
                    SELECT o.id, o.name, o.created,
                      (SELECT COUNT(*) FROM projects p WHERE p.org_id=o.id) projects,
                      (SELECT COUNT(*) FROM memberships m WHERE m.org_id=o.id) members,
                      (SELECT COALESCE(SUM(u.quantity),0) FROM usage_events u JOIN projects p ON p.id=u.project_id WHERE p.org_id=o.id) usage_total,
                      (SELECT MAX(u.ts) FROM usage_events u JOIN projects p ON p.id=u.project_id WHERE p.org_id=o.id) last_activity,
                      COALESCE((SELECT b.plan FROM billing_state b WHERE b.org_id=o.id), 'free') plan
                    FROM orgs o ORDER BY o.created DESC""").fetchall()
                out = []
                for r in rows:
                    d = dict(r)
                    d["customer"] = ENT.customer_status(d["id"])
                    out.append(d)
                return self._send(200, {"data": out})

        # ── data export (customer-facing, real data) ──
        if parts == ["v1", "export", "memories"]:
            p = self._proj(qs)
            if p is None:
                return self._err(404, "not_found", "project not found")
            T = p.now()
            out = []
            for a in p.engine.store.assertions():
                row = shape_assertion(p, a.id, T)
                prov_ids, grounded = p.engine.provenance(a.id)
                row.update({"state": e_state(p, list(a.subjects), a.proposition),
                            "grounded": grounded, "provenance": list(prov_ids)})
                out.append(row)
            ENT.audit("export.memories", actor=auth.get("user", {}).get("id") if isinstance(auth, dict) else None,
                      org_id=self._org_of_project(p.id), project_id=p.id,
                      metadata={"count": len(out)})
            return self._send(200, {"project": p.id, "exported_at": time.time(), "memories": out})
        if parts == ["v1", "export", "audit"]:
            oid = STORE.org_for_user(auth["user"]["id"])["id"] if isinstance(auth, dict) and "user" in auth else None
            if not oid or not self._require(auth, "audit.read", oid):
                return self._err(403, "permission", "Requires admin.")
            return self._send(200, {"org": oid, "exported_at": time.time(),
                                    "events": ENT.audit_log(oid, limit=10000)})
        if parts == ["v1", "billing", "events"]:
            oid = STORE.org_for_user(auth["user"]["id"])["id"] if isinstance(auth, dict) and "user" in auth else None
            if not oid or not self._require(auth, "billing.manage", oid):
                return self._err(403, "permission", "Requires owner.")
            return self._send(200, {"data": ENT.billing_events(oid)})

        # ── provider connectivity check (no ingestion, no memory written) ──
        if parts == ["v1", "providers", "check"]:
            out = {"llm": {"configured": providers.llm_configured()}}
            if providers.llm_configured():
                out["llm"]["base_url"] = os.environ.get("OMEM_LLM_BASE_URL", "https://api.openai.com/v1")
                out["llm"]["model"] = os.environ.get("OMEM_LLM_MODEL", "gpt-4o-mini")
                out["llm"]["dns"] = providers.dns_check(out["llm"]["base_url"])
                try:
                    # a minimal round-trip that exercises the real request path
                    txt = providers.OpenAICompatClient().complete(
                        'Reply with the JSON object {"ok": true} and nothing else.',
                        'Health check. Respond in JSON.')
                    out["llm"]["reachable"] = True
                    out["llm"]["sample"] = (txt or "")[:80]
                except Exception as ex:
                    out["llm"]["reachable"] = False
                    out["llm"]["error"] = f"{type(ex).__name__}: {ex}"
            out["google"] = {"configured": providers.google_configured(),
                             "hosts": {h: providers.dns_check("https://" + h)
                                       for h in ("oauth2.googleapis.com",
                                                 "gmail.googleapis.com")}}
            out["stripe"] = {"configured": providers.stripe_configured()}
            # a single line an operator can act on
            problems = []
            if out["llm"].get("configured") and not out["llm"].get("dns", {}).get("ok", True):
                problems.append(f"LLM host unreachable: {out['llm']['dns'].get('host')}")
            for h, d in out["google"]["hosts"].items():
                if not d.get("ok"):
                    problems.append(f"Google host unreachable: {h}")
            out["summary"] = ("all configured providers reachable" if not problems
                              else "; ".join(problems))
            return self._send(200, out)

        # ── project settings (LLM config etc.) ──
        if parts == ["v1", "settings"]:
            pid = qs.get("project", [None])[0]
            keys = ["llm_enabled", "llm_model"]
            return self._send(200, {k: ENT.setting(pid, k) for k in keys})
        if parts == ["v1", "filtered"]:
            pid = qs.get("project", [None])[0]
            return self._send(200, {"data": INGEST.filtered_for(pid)})
        if parts == ["v1", "classifications", "summary"]:
            pid = qs.get("project", [None])[0]
            return self._send(200, CLASSIFICATIONS.summary(pid, qs.get("connector", [None])[0]))
        if parts == ["v1", "classifications"]:
            pid = qs.get("project", [None])[0]
            return self._send(200, {"data": CLASSIFICATIONS.list(
                pid, qs.get("classification", [None])[0],
                _clamp_limit(qs.get("limit", ["100"])[0], 100))})
        if len(parts) == 4 and parts[:2] == ["v1", "sources"] and parts[3] == "classification":
            return self._send(200, CLASSIFICATIONS.for_source(parts[2]) or {})
        if parts == ["v1", "extraction-logs"]:
            pid = qs.get("project", [None])[0]
            return self._send(200, {"data": ENT.extraction_logs(pid)})

        # ── memory scanner ────────────────────────────────────────────────
        if parts == ["v1", "memory", "health"]:
            pid = qs.get("project", [None])[0]
            p = PROJECTS.get(pid)
            if not p:
                return self._send(404, {"error": "project not found"})
            _h = _scanner_for(p).health_summary()
            # P8-hardening: expose whether boot reconciliation repaired projection
            # drift for this project, so operators can see silent recovery.
            _h["projection_drift"] = PROJECTION_DRIFT.get(pid, {"drift_repaired": False})
            return self._send(200, _h)

        if parts == ["v1", "memory", "scans"]:
            pid = qs.get("project", [None])[0]
            p = PROJECTS.get(pid)
            if not p:
                return self._send(404, {"error": "project not found"})
            return self._send(200, {"data": _scanner_for(p).list_scans()})

        if len(parts) == 4 and parts[:2] == ["v1", "memory"] and parts[2] == "scans":
            pid = qs.get("project", [None])[0]
            p = PROJECTS.get(pid)
            if not p:
                return self._send(404, {"error": "project not found"})
            scan = _scanner_for(p).get_scan(parts[3])
            if not scan:
                return self._send(404, {"error": "scan not found"})
            cls_filter = qs.get("classification", [None])[0]
            limit = _clamp_limit(qs.get("limit", ["200"])[0], 200)
            offset = int(qs.get("offset", ["0"])[0])
            results = _scanner_for(p).scan_results(parts[3], cls_filter, limit, offset)
            return self._send(200, {"scan": scan, "results": results, "count": len(results)})

        if parts == ["v1", "memory", "review-queue"]:
            pid = qs.get("project", [None])[0]
            p = PROJECTS.get(pid)
            if not p:
                return self._send(404, {"error": "project not found"})
            status = qs.get("status", ["pending"])[0]
            return self._send(200, {"data": _scanner_for(p).review_queue(status)})

        # ── memory quality funnel: every number from persisted state ─────
        if parts == ["v1", "memory", "quality"]:
            pid = qs.get("project", [None])[0]
            p = PROJECTS.get(pid)
            if not p:
                return self._send(404, {"error": "project not found"})
            db = STORE.db
            def c(sql, *a):
                r = db.execute(sql, a).fetchone()
                return (r[0] if r else 0) or 0
            cls_sum = CLASSIFICATIONS.summary(pid)
            cats = {}
            for r in db.execute(
                    "SELECT category, COUNT(*) n FROM message_classifications "
                    "WHERE project_id=? AND category IS NOT NULL GROUP BY category", (pid,)):
                cats[r["category"]] = r["n"]
            fd = {}
            for r in db.execute(
                    "SELECT quality, COUNT(*) n FROM fact_decisions "
                    "WHERE project_id=? GROUP BY quality", (pid,)):
                fd[r["quality"]] = r["n"]
            scanner = _scanner_for(p)
            health = scanner.health_summary()
            return self._send(200, {
                "emails_scanned": cls_sum["messages_scanned"],
                "by_classification": cls_sum["by_classification"],
                "by_category": cats,
                "candidate_facts": c("SELECT COUNT(*) FROM fact_decisions WHERE project_id=?", pid),
                "facts_stored": c("SELECT COUNT(*) FROM fact_decisions WHERE project_id=? AND stored=1", pid),
                "facts_rejected": c("SELECT COUNT(*) FROM fact_decisions WHERE project_id=? AND stored=0", pid),
                "by_quality": fd,
                "active_memories": health["active_memories"],
                "retracted_by_scanner": len(health["recent_corrections"]),
                "pending_review": health["pending_review"],
                "entities_resolved": c("SELECT COUNT(*) FROM entity_resolutions WHERE project_id=?", pid),
            })

        # ── org identity: who is "us" ────────────────────────────────────
        if parts == ["v1", "identity"]:
            pid = qs.get("project", [None])[0]
            if pid not in PROJECTS:
                return self._send(404, {"error": "project not found"})
            return self._send(200, _org_identity(pid))

        # ── relationship overrides (user corrections = reusable intelligence) ──
        if parts == ["v1", "relationships"]:
            pid = qs.get("project", [None])[0]
            if pid not in PROJECTS:
                return self._send(404, {"error": "project not found"})
            out = []
            for r in STORE.db.execute(
                    "SELECT key_type, key, role, source, note, ts FROM relationship_overrides "
                    "WHERE project_id=? ORDER BY ts DESC", (pid,)):
                out.append(dict(r))
            return self._send(200, {"data": out, "roles": list(RELATIONSHIP_ROLES)})

        # ── P5: the memory graph around an entity (scope-safe, bounded) ──
        if parts == ["v1", "memory", "graph"]:
            pid = qs.get("project", [None])[0]
            entity = qs.get("entity", [None])[0]
            p = PROJECTS.get(pid)
            if not p or not entity:
                return self._send(404, {"error": "project or entity not found"})
            viewer = qs.get("viewer", [None])[0]
            viewer, _err = self._effective_agent(auth, viewer)
            if _err:
                return
            teams = SCOPES.teams_of(pid, viewer) if viewer else set()
            try:
                depth = max(1, min(_graph.MAX_DEPTH, int(qs.get("depth", ["1"])[0])))
            except (TypeError, ValueError):
                depth = 1
            _asof = qs.get("as_of", [None])[0]
            _T = None
            if _asof not in (None, "now"):
                try:
                    _T = int(_asof)
                except (TypeError, ValueError):
                    return self._err(422, "invalid_request", "as_of must be an integer or 'now'")
            return self._send(200, _graph.subgraph(
                STORE.db, p, entity, depth=depth, T=_T, scopes=SCOPES, viewer=viewer,
                teams=teams, user=qs.get("user", [None])[0]))

        # ── P4: open conflicts with evidence sides + recommendation ──
        if parts == ["v1", "memory", "conflicts"]:
            pid = qs.get("project", [None])[0]
            p = PROJECTS.get(pid)
            if not p:
                return self._send(404, {"error": "project not found"})
            _cv_viewer, _err = self._effective_agent(auth, qs.get("viewer", [None])[0])
            if _err:
                return
            data = _conflict.conflicts_overview(
                p, STORE.db, SCOPES,
                viewer=_cv_viewer,
                acting_user=qs.get("user", [None])[0])
            return self._send(200, {"data": data, "count": len(data)})

        # Which claims are declared mutually exclusive. Exists so "why is
        # conflicts() empty" is answerable without reading the ops log: either
        # the pair is here and the two claims are not about the same referent,
        # or it was never declared.
        if parts == ["v1", "contradictions"]:
            pid = qs.get("project", [None])[0]
            p = PROJECTS.get(pid)
            if not p:
                return self._send(404, {"error": "project not found"})
            pairs = [{"token_a": a, "token_b": b} for a, b in CONTRADICTIONS.get(p.id, [])]
            return self._send(200, {"data": pairs, "count": len(pairs)})

        # ── P3: the "why do you know this?" chain ──
        if parts == ["v1", "memory", "chain"]:
            pid = qs.get("project", [None])[0]
            aid = qs.get("assertion", [None])[0]
            p = PROJECTS.get(pid)
            if not p or not aid:
                return self._send(404, {"error": "project or assertion not found"})
            viewer = qs.get("viewer", [None])[0]
            viewer, _err = self._effective_agent(auth, viewer)
            if _err:
                return
            if not _viewer_scope_ok(pid, aid, viewer, qs.get("user", [None])[0]):
                return self._err(404, "not_found", "assertion not found")
            c = _consol.chain(p, STORE.db, aid)
            if c is None:
                return self._err(404, "not_found", "assertion not found")
            c["scope"] = SCOPES.of(pid, aid)
            return self._send(200, c)

        # ── contacts: persistent people/orgs derived from real interaction ──
        if parts == ["v1", "contacts"]:
            pid = qs.get("project", [None])[0]
            if pid not in PROJECTS:
                return self._send(404, {"error": "project not found"})
            ident = _org_identity(pid)
            self_addrs = set(ident["emails"])
            self_doms = set(ident["domains"])
            overrides = _relationship_overrides(pid)
            # aggregate in SQL over the indexed from_addr column — never parse
            # the whole mailbox in Python (real mailboxes made this endpoint
            # a multi-second full-table JSON scan)
            rows = STORE.db.execute(
                "SELECT sr.from_addr, COUNT(*) n, MIN(sr.received) first_c, "
                "MAX(sr.received) last_c, COUNT(DISTINCT sr.thread_id) threads, "
                "MAX(sr.id) latest_id "
                "FROM source_records sr JOIN connectors c ON c.id=sr.connector_id "
                "WHERE sr.project_id=? AND c.kind='gmail' AND sr.from_addr IS NOT NULL "
                "GROUP BY sr.from_addr ORDER BY last_c DESC LIMIT 300", (pid,)).fetchall()
            out = []
            for r in rows:
                frm = r["from_addr"]
                if not frm or frm in self_addrs or frm.split("@")[-1] in self_doms:
                    continue
                name = None
                pr = STORE.db.execute(
                    "SELECT payload FROM source_records WHERE id=?", (r["latest_id"],)).fetchone()
                if pr:
                    try:
                        name = json.loads(pr["payload"]).get("from_name") or None
                    except Exception:
                        name = None
                dom = frm.split("@")[-1]
                slug = __import__("re").sub(r"[^a-z0-9]+", "-", dom.split(".")[0].lower())
                entity_id = f"company:{slug}"
                facts = STORE.db.execute(
                    "SELECT COUNT(*) n FROM fact_decisions WHERE project_id=? "
                    "AND subject IN (?, ?) AND stored=1",
                    (pid, entity_id, f"customer:{frm.split('@')[0]}")).fetchone()["n"]
                out.append({
                    "email": frm, "name": name, "domain": dom,
                    "role": _role_for(pid, email=frm, overrides=overrides),
                    "messages": r["n"], "threads": r["threads"],
                    "first_contact": r["first_c"], "last_contact": r["last_c"],
                    "entity_id": entity_id, "facts_stored": facts,
                })
            return self._send(200, {"data": out[:200]})

        # ── per-email pipeline diagnostics: the full decision trace ──────
        if parts == ["v1", "diagnostics", "email"]:
            pid = qs.get("project", [None])[0]
            srid = qs.get("source", [None])[0]
            p = PROJECTS.get(pid)
            if not p or not srid:
                return self._send(404, {"error": "project or source not found"})
            sr = STORE.db.execute(
                "SELECT * FROM source_records WHERE id=? AND project_id=?",
                (srid, pid)).fetchone()
            if not sr:
                return self._send(404, {"error": "source record not found"})
            sr = dict(sr)
            try:
                payload = json.loads(sr["payload"])
            except Exception:
                payload = {}
            conn_row = STORE.db.execute("SELECT * FROM connectors WHERE id=?",
                                        (sr["connector_id"],)).fetchone()
            conn = dict(conn_row) if conn_row else {"id": sr["connector_id"], "project_id": pid}
            from email_analysis import analyze, parse_participants, split_sentences, speech_act
            from classifier import classify as _cls
            ident = _owner_identity_for(conn)
            pp = parse_participants(payload, ident)
            verdict = _cls(payload,
                           thread_context=thread_context_for(STORE.db, pid,
                                                             payload.get("thread_id"),
                                                             exclude_source_id=srid))
            sc = verdict.get("scores", {})
            an = analyze(payload, ident, business_score=sc.get("business", 0.0),
                         automated_score=sc.get("automated", 0.0),
                         business_signals=verdict.get("signals", []))
            sentences = []
            from extraction import strip_quoted
            for s in split_sentences(strip_quoted(payload.get("body") or ""))[:40]:
                sentences.append({"text": s[:200], "speech_act": speech_act(s)})
            cls_row = STORE.db.execute(
                "SELECT classification, confidence, category, reasons, signals, entered_pipeline "
                "FROM message_classifications WHERE source_record_id=?", (srid,)).fetchone()
            decisions = []
            for r in STORE.db.execute(
                    "SELECT * FROM fact_decisions WHERE source_record_id=? ORDER BY id", (srid,)):
                d = dict(r)
                d["reasons"] = json.loads(d["reasons"] or "[]")
                decisions.append(d)
            assertions = []
            for r in STORE.db.execute(
                    "SELECT assertion_id, evidence, confidence, extractor FROM assertion_evidence "
                    "WHERE source_record_id=? AND project_id=?", (srid, pid)):
                a = p.engine.store.assertion(r["assertion_id"])
                assertions.append({
                    "assertion_id": r["assertion_id"],
                    "evidence": r["evidence"], "confidence": r["confidence"],
                    "extractor": r["extractor"],
                    "open": bool(a and p.engine.ledger.is_open_at(a, p.now())),
                    "proposition": a.proposition if a else None,
                    "subjects": list(a.subjects) if a else [],
                })
            sender_role = _role_for(pid, email=pp.get("sender_email"))
            return self._send(200, {
                "source": {"id": srid, "external_id": sr["external_id"],
                            "received": sr["received"],
                            "from": payload.get("from"), "to": payload.get("to"),
                            "cc": (payload.get("headers") or {}).get("cc") or
                                  (payload.get("headers") or {}).get("Cc"),
                            "subject": payload.get("subject"),
                            "body": (payload.get("body") or "")[:5000],
                            "thread_id": payload.get("thread_id")},
                "identity": ident,
                "participants": pp,
                "sender_role_override": sender_role,
                "classification_stored": dict(cls_row) if cls_row else None,
                "classification_now": dict(verdict),
                "analysis": {k: v for k, v in an.items() if k != "participants"},
                "semantic": (lambda r: dict(r) if r else None)(STORE.db.execute(
                    "SELECT business_relevance, memory_candidate, rejection_reason, "
                    "reasoning_summary, candidates, dropped, model, error, ts "
                    "FROM semantic_analyses WHERE source_record_id=? "
                    "ORDER BY id DESC LIMIT 1", (srid,)).fetchone()),
                "sentences": sentences,
                "fact_decisions": decisions,
                "assertions": assertions,
            })

        # ── per-source fact decisions ("why was this stored / not stored") ──
        if parts == ["v1", "fact-decisions"]:
            pid = qs.get("project", [None])[0]
            srid = qs.get("source", [None])[0]
            stored_f = qs.get("stored", [None])[0]
            q = "SELECT * FROM fact_decisions WHERE project_id=?"
            args = [pid]
            if srid:
                q += " AND source_record_id=?"
                args.append(srid)
            if stored_f in ("0", "1"):
                q += " AND stored=?"
                args.append(int(stored_f))
            q += " ORDER BY id DESC LIMIT ?"
            try:
                lim = max(1, min(500, int(qs.get("limit", ["100"])[0])))
            except (TypeError, ValueError):
                lim = 100
            args.append(lim)
            out = []
            for r in STORE.db.execute(q, args):
                d = dict(r)
                d["reasons"] = json.loads(d["reasons"] or "[]")
                out.append(d)
            return self._send(200, {"data": out})

        # ── pilot onboarding checklist (every step computed from real state) ──
        if parts == ["v1", "onboarding"]:
            pid = qs.get("project", [None])[0]
            uid = auth["user"]["id"] if isinstance(auth, dict) and "user" in auth else None
            oid = STORE.org_for_user(uid)["id"] if uid else self._org_of_project(pid)
            db = STORE.db
            def c(sql, *a):
                return db.execute(sql, a).fetchone()[0]
            has_project = bool(pid and STORE.project(pid))
            p = PROJECTS.get(pid) if has_project else None
            steps = [
                {"id": "org", "label": "Organization created", "done": bool(oid)},
                {"id": "project", "label": "Project created", "done": has_project},
                {"id": "key", "label": "API key created",
                 "done": has_project and c("SELECT COUNT(*) FROM keys WHERE project_id=? AND revoked=0", pid) > 0},
                {"id": "source", "label": "First source connected",
                 "done": has_project and c("SELECT COUNT(*) FROM connectors WHERE project_id=?", pid) > 0},
                {"id": "record", "label": "First source record received",
                 "done": has_project and c("SELECT COUNT(*) FROM source_records WHERE project_id=?", pid) > 0},
                {"id": "memory", "label": "First memory created",
                 "done": bool(p and any(True for _ in p.engine.store.assertions()))},
                {"id": "recall", "label": "First recall performed",
                 "done": has_project and (ENT.usage(pid).get("agent_recalls", 0) > 0)},
                {"id": "agent", "label": "Agent connected",
                 "done": bool(p and any(True for _ in p.engine.store.agents()))},
            ]
            return self._send(200, {"steps": steps,
                                    "completed": sum(1 for s_ in steps if s_["done"]),
                                    "total": len(steps)})

        # ── pilot feedback (read) ──
        if parts == ["v1", "feedback"]:
            pid = qs.get("project", [None])[0]
            return self._send(200, {"data": ENT.feedback_for(pid),
                                    "summary": ENT.feedback_summary(pid)})

        # ── memory quality: top-recalled ──
        if parts == ["v1", "memory", "top-recalled"]:
            pid = qs.get("project", [None])[0]
            return self._send(200, {"data": ENT.top_recalled(pid)})

        # ── enterprise reads ──
        if parts == ["v1", "members"]:
            oid = self._org_of_project(qs.get("project", [None])[0]) if qs.get("project") else \
                  (STORE.org_for_user(auth["user"]["id"])["id"] if "user" in auth else None)
            if "user" in auth and not self._require(auth, "member.manage", oid):
                return self._err(403, "permission", "Requires admin.")
            return self._send(200, {"data": ENT.members(oid)})
        if parts == ["v1", "audit"]:
            oid = STORE.org_for_user(auth["user"]["id"])["id"] if "user" in auth else None
            if not oid or not self._require(auth, "audit.read", oid):
                return self._err(403, "permission", "Requires admin.")
            return self._send(200, {"data": ENT.audit_log(oid)})
        if parts == ["v1", "usage"]:
            pid = qs.get("project", [None])[0]
            return self._send(200, {"metrics": ENT.usage(pid),
                                    "series": {m: ENT.usage_series(pid, m) for m in
                                               ["assertions_created", "source_records", "agent_queries", "api_requests"]}})
        if parts == ["v1", "retention"]:
            return self._send(200, ENT.retention(qs.get("project", [None])[0]))
        if parts == ["v1", "billing"]:
            oid = STORE.org_for_user(auth["user"]["id"])["id"] if "user" in auth else None
            b = ENT.billing(oid) if oid else {}
            return self._send(200, {**b, "plans": PLANS,
                                    "stripe_live": providers.stripe_configured()})
        if parts == ["v1", "observability"]:
            return self._send(200, self._observability())

        # /v1/me
        if parts == ["v1", "me"]:
            if "user" not in auth:
                return self._err(403, "permission", "Session required.")
            org = STORE.org_for_user(auth["user"]["id"])
            return self._send(200, {"email": auth["user"]["email"], "org": org})

        # /v1/keys?project=
        if parts == ["v1", "keys"]:
            pid = qs.get("project", [None])[0]
            if not pid or not STORE.project(pid):
                return self._err(404, "not_found", "project not found")
            return self._send(200, {"data": STORE.keys_for(pid)})

        # /v1/projects (scoped: a session sees its org's projects + the labeled demo)
        if parts == ["v1", "projects"]:
            if "user" in auth:
                rows = STORE.projects_for_user(auth["user"]["id"])
                allowed = {r["id"] for r in rows}
                meta = {r["id"]: r for r in rows}
            else:
                allowed = {auth["key"]["project_id"]}
                meta = {pid: STORE.project(pid) for pid in allowed}
            return self._send(200, {"data": [
                {"id": p.id, "name": p.name, "env": p.env, "now": p.now(),
                 "entities": len(list(p.engine.store.entities())),
                 "agents": len(list(p.engine.store.agents())),
                 "assertions": len(list(p.engine.store.assertions())),
                 "events": len(list(p.engine.store.events())),
                 "is_demo": p.is_demo}
                for p in PROJECTS.values() if p.id in allowed]})

        p = self._proj(qs)
        if p is None:
            return self._err(404, "not_found", "project not found")
        e = p.engine
        T = self._T(qs, p)

        # /v1/overview
        if parts == ["v1", "overview"]:
            assertions = list(e.store.assertions())
            open_beliefs = [a for a in assertions if e.ledger.is_open_at(a, p.now())
                            and a.proposition != RETRACTED]
            grounded = sum(1 for a in open_beliefs if e.provenance(a.id)[1] == "GROUNDED")
            conflicts = e.conflicts(p.now())
            return self._send(200, {
                "now": p.now(),
                "counts": {
                    "entities": len(list(e.store.entities())),
                    "agents": len(list(e.store.agents())),
                    "events": len(list(e.store.events())),
                    "assertions": len(assertions),
                    "open_beliefs": len(open_beliefs),
                    "conflicts": len(conflicts),
                },
                "grounded_ratio": (grounded / len(open_beliefs)) if open_beliefs else 1.0,
                "activity": p.log[:12],
            })

        # /v1/assertions
        if parts == ["v1", "assertions"]:
            subj = qs.get("subject", [None])[0]
            agent = qs.get("agent", [None])[0]
            viewer = qs.get("viewer", [None])[0]
            viewer, _err = self._effective_agent(auth, viewer)
            if _err:
                return
            open_only = qs.get("open", [None])[0] == "true"
            rows = []
            for a in e.store.assertions():
                if subj and subj not in a.subjects:
                    continue
                if agent and a.agent != agent:
                    continue
                if not _viewer_scope_ok(p.id, a.id, viewer):
                    continue
                if open_only and not e.ledger.is_open_at(a, T):
                    continue
                rows.append(shape_assertion(p, a.id, T))
            rows.sort(key=lambda r: r["assertion_time"])
            return self._send(200, {"as_of": T, "data": rows})

        # /v1/assertions/{id}
        if len(parts) == 3 and parts[:2] == ["v1", "assertions"]:
            _v = qs.get("viewer", [None])[0]
            _v, _err = self._effective_agent(auth, _v)
            if _err:
                return
            if not _viewer_scope_ok(p.id, parts[2], _v, qs.get("user", [None])[0]):
                return self._err(404, "not_found", "assertion not found")
            sa = shape_assertion(p, parts[2], T)
            return self._send(200, sa) if sa else self._err(404, "not_found", "assertion not found")

        # /v1/assertions/{id}/why  — the signature explanation, all from frozen queries
        if len(parts) == 4 and parts[:2] == ["v1", "assertions"] and parts[3] == "why":
            aid = parts[2]
            a = e.store.assertion(aid)
            if a is None:
                return self._err(404, "not_found", "assertion not found")
            _v = qs.get("viewer", [None])[0]
            _v, _err = self._effective_agent(auth, _v)
            if _err:
                return
            if not _viewer_scope_ok(p.id, aid, _v, qs.get("user", [None])[0]):
                return self._err(404, "not_found", "assertion not found")
            prov_ids, grounded = e.provenance(aid)
            state = e.proposition_state(list(a.subjects), a.proposition, T)
            chain = e.revision_chain(aid)
            # contradictions: open assertions conflicting with THIS assertion at
            # T. Use the P7 narrow query (only aid's neighbourhood) instead of
            # the full O(n²) engine.conflicts(T) — byte-identical for pairs
            # touching aid (tests_p7_conflict_equiv.py), scope-filtered so the
            # explanation never leaks private memory.
            contradictory = []
            try:
                import conflict_narrow as _cn
                _pairs = _cn.conflicts_for(e, [aid], T)
            except Exception:
                _pairs = {pr for pr in e.conflicts(T) if aid in pr}
            for pair in _pairs:
                other = [x for x in pair if x != aid][0]
                if not _viewer_scope_ok(p.id, other, _v, qs.get("user", [None])[0]):
                    continue
                contradictory.append(shape_assertion(p, other, T))
            prov_nodes = []
            for pid in prov_ids:
                kind = ("event" if e.store.event(pid) else
                        "assertion" if e.store.assertion(pid) else "primitive")
                prov_nodes.append({"id": pid, "kind": kind,
                                   "label": p.labels.get(pid, {}).get("label")})
            # derivation edges among prov + this assertion (consequent -> antecedent)
            edges = []
            for d in e.store.derivations():
                if d.consequent == aid or d.consequent in prov_ids:
                    for anc in d.antecedents:
                        edges.append({"from": d.consequent, "to": anc, "kind": d.kind})
            return self._send(200, {
                "assertion": shape_assertion(p, aid, T),
                "as_of": T,
                "state": state,
                "grounded": grounded == "GROUNDED",
                "provenance": {"nodes": prov_nodes, "edges": edges},
                "revision_chain": [shape_assertion(p, c, T) for c in chain],
                "evidence": INGEST.evidence_for(p.id, aid),
                "source": (lambda sr: {
                    "id": sr["id"], "external_id": sr["external_id"],
                    "connector_id": sr["connector_id"], "received": sr["received"],
                    "payload": json.loads(sr["payload"]),
                    "view": source_view(sr, INGEST.connector(sr["connector_id"]))} if sr else None)(
                        INGEST.source_for_assertion(p.id, aid)),
                "contradictions": contradictory,
                "subjects": [shape_entity(p, s) for s in a.subjects],
                "agent": shape_agent(p, a.agent),
            })

        # /v1/assertions/{id}/provenance
        if len(parts) == 4 and parts[:2] == ["v1", "assertions"] and parts[3] == "provenance":
            aid = parts[2]
            if e.store.assertion(aid) is None:
                return self._err(404, "not_found", "assertion not found")
            _v = qs.get("viewer", [None])[0]
            _v, _err = self._effective_agent(auth, _v)
            if _err:
                return
            if not _viewer_scope_ok(p.id, aid, _v, qs.get("user", [None])[0]):
                return self._err(404, "not_found", "assertion not found")
            prov_ids, grounded = e.provenance(aid)
            nodes = [{"id": aid, "kind": "assertion", "root": False,
                      "label": p.labels.get(aid, {}).get("label")}]
            for pid in prov_ids:
                kind = ("event" if e.store.event(pid) else "assertion")
                nodes.append({"id": pid, "kind": kind, "root": kind == "event",
                              "label": p.labels.get(pid, {}).get("label")})
            edges = []
            for d in e.store.derivations():
                if d.consequent == aid or d.consequent in prov_ids:
                    for anc in d.antecedents:
                        edges.append({"from": d.consequent, "to": anc, "kind": d.kind})
            return self._send(200, {"assertion": aid, "grounded": grounded == "GROUNDED",
                                    "nodes": nodes, "edges": edges})

        # /v1/assertions/{id}/revision-chain
        if len(parts) == 4 and parts[:2] == ["v1", "assertions"] and parts[3] == "revision-chain":
            aid = parts[2]
            _v = qs.get("viewer", [None])[0]
            _v, _err = self._effective_agent(auth, _v)
            if _err:
                return
            _u = qs.get("user", [None])[0]
            # hide existence of the target if the viewer can't see it
            if not _viewer_scope_ok(p.id, aid, _v, _u):
                return self._err(404, "not_found", "assertion not found")
            chain = e.revision_chain(aid)
            return self._send(200, {"chain": [shape_assertion(p, c, T) for c in chain
                                              if _viewer_scope_ok(p.id, c, _v, _u)]})

        # /v1/entities , /v1/entities/{id} , /v1/entities/{id}/beliefs
        if parts == ["v1", "entities"]:
            return self._send(200, {"data": [shape_entity(p, en.id) for en in e.store.entities()]})
        if len(parts) == 3 and parts[:2] == ["v1", "entities"]:
            se = shape_entity(p, parts[2])
            return self._send(200, se) if se else self._err(404, "not_found", "entity not found")
        if len(parts) == 4 and parts[:2] == ["v1", "entities"] and parts[3] == "beliefs":
            ids = e.beliefs_about(parts[2], T)
            _v = qs.get("viewer", [None])[0]
            _v, _err = self._effective_agent(auth, _v)
            if _err:
                return
            _u = qs.get("user", [None])[0]
            return self._send(200, {"as_of": T,
                                    "data": [shape_assertion(p, i, T) for i in sorted(ids)
                                             if _viewer_scope_ok(p.id, i, _v, _u)]})

        # /v1/agents , /v1/agents/{id}
        if parts == ["v1", "agents"]:
            return self._send(200, {"data": [shape_agent(p, ag.id) for ag in e.store.agents()]})
        if len(parts) == 3 and parts[:2] == ["v1", "agents"]:
            # include the agent's asserted claims (accountability view), but
            # only those the authenticated viewer is permitted to see — an
            # agent-bound key must not read another agent's private memory here.
            sa = shape_agent(p, parts[2])
            if not sa:
                return self._err(404, "not_found", "agent not found")
            _v = qs.get("viewer", [None])[0]
            _v, _err = self._effective_agent(auth, _v)
            if _err:
                return
            _u = qs.get("user", [None])[0]
            claims = [shape_assertion(p, a.id, T) for a in e.store.assertions()
                      if a.agent == parts[2] and _viewer_scope_ok(p.id, a.id, _v, _u)]
            sa["claims"] = claims
            return self._send(200, sa)

        # /v1/events
        if parts == ["v1", "events"]:
            return self._send(200, {"data": [shape_event(p, ev.id) for ev in e.store.events()]})

        # /v1/timeline
        if parts == ["v1", "timeline"]:
            ids = e.timeline(T)
            return self._send(200, {"as_of": T, "events": [shape_event(p, i) for i in ids]})

        # /v1/conflicts
        if parts == ["v1", "conflicts"]:
            _v = qs.get("viewer", [None])[0]
            _v, _err = self._effective_agent(auth, _v)
            if _err:
                return
            _u = qs.get("user", [None])[0]
            out = []
            # Use the P7 narrow query over the open-assertion candidate set: it
            # reproduces the entire engine.conflicts(T) set (proven in
            # tests_p7_conflict_equiv.py) but evaluates only same-subject
            # neighbourhoods, avoiding the dense full O(n²) pairwise scan that
            # made this route a ~43s DoS at 5k assertions.
            try:
                import conflict_narrow as _cn
                import partition_view as _pvmod
                _open_ids = [x.id for x in e.prop._open_assertions_at(T)]
                _pview = _pvmod.PartitionView(e, T)
                _pairs = _cn.conflicts_for(e, _open_ids, T, pview=_pview)
            except Exception:
                _pairs = e.conflicts(T)
            for pair in _pairs:
                a, b = tuple(pair)
                # a conflict pair is only visible if the caller may see BOTH
                # sides — otherwise it leaks the existence/content of private
                # memory. Unbound/operator callers (viewer=None) still see all.
                if not (_viewer_scope_ok(p.id, a, _v, _u)
                        and _viewer_scope_ok(p.id, b, _v, _u)):
                    continue
                out.append({"pair": [shape_assertion(p, a, T), shape_assertion(p, b, T)]})
            return self._send(200, {"as_of": T, "conflicts": out})

        # /v1/coreference/partition
        if parts == ["v1", "coreference", "partition"]:
            part = [sorted(list(c)) for c in e.referent_partition(T)]
            return self._send(200, {"as_of": T, "partition": part})

        # /v1/graph — nodes+edges assembled from primitives (for the memory graph)
        if parts == ["v1", "graph"]:
            nodes, edges = [], []
            for en in e.store.entities():
                nodes.append({"id": en.id, "kind": "entity", "label": p.labels.get(en.id, {}).get("label")})
            for ag in e.store.agents():
                nodes.append({"id": ag.id, "kind": "agent", "label": p.labels.get(ag.id, {}).get("label")})
            for ev in e.store.events():
                nodes.append({"id": ev.id, "kind": "event", "label": p.labels.get(ev.id, {}).get("label")})
            for a in e.store.assertions():
                if not e.ledger.is_open_at(a, T):
                    continue
                nodes.append({"id": a.id, "kind": "assertion",
                              "label": p.labels.get(a.id, {}).get("label"),
                              "proposition": a.proposition})
                edges.append({"from": a.agent, "to": a.id, "kind": "asserts"})
                for s in a.subjects:
                    edges.append({"from": a.id, "to": s, "kind": "about"})
            for d in e.store.derivations():
                for anc in d.antecedents:
                    edges.append({"from": d.consequent, "to": anc, "kind": d.kind})
            return self._send(200, {"as_of": T, "nodes": nodes, "edges": edges})

        # /v1/logs
        if parts == ["v1", "logs"]:
            return self._send(200, {"data": p.log[:200]})

        return self._err(404, "not_found", f"no route: /{'/'.join(parts)}")

    # ---- POST ----
    def do_DELETE(self):
        self.do_POST()

    def do_POST(self):
        self._req_start = time.perf_counter(); self._metrics_recorded = False
        u = urlparse(self.path)
        parts = [x for x in u.path.split("/") if x]
        qs = parse_qs(u.query)
        try:
            self._oversized = False
            body = self._body()
            if getattr(self, "_oversized", False):
                self._err(413, "payload_too_large",
                          f"Request body exceeds the {self.MAX_BODY_BYTES}-byte limit.")
                return
            auth = self._guard(parts, qs)
            if auth is None:
                return
            # P9.7: a read-only (viewer) key may not mutate memory/state. Read
            # POSTs (recall/brief are reads expressed as POST) remain allowed.
            if self._is_readonly_key(auth):
                _READ_POSTS = {("v1", "recall"), ("v1", "brief")}
                if tuple(parts[:2]) not in _READ_POSTS:
                    self._err(403, "permission",
                              "This API key is read-only (viewer role).")
                    return
            self._route_post(parts, qs, body, auth)
        except Rejected as r:
            code = 409 if r.code in ("R_MUTATION", "R_REOPEN") else 422
            p = self._proj(qs)
            if p:
                self._logreq(p, "POST", u.path, code, str(r), reason=r.code)
            self._err(code, "invalid_request" if code == 422 else "conflict",
                      str(r), reason_code=r.code)
        except Exception as ex:
            self._err(500, "server", f"{type(ex).__name__}: {ex}")

    def _route_post(self, parts, qs, body, auth):
        # ── account ──
        if parts == ["v1", "signup"]:
            email = (body.get("email") or "").strip()
            if "@" not in email:
                return self._err(422, "invalid_request", "A valid email is required.", param="email")
            res = STORE.signup(email, body.get("org") or "")
            org = STORE.org_for_user(res["user_id"])
            if not ENT.role_of(org["id"], res["user_id"]):
                ENT.set_role(org["id"], res["user_id"], "owner")
                ENT.audit("user.signup", actor=res["user_id"], org_id=org["id"],
                          resource=res["user_id"])
            out = {"token": res["token"], "email": res["email"], "org": org, "existing": res["existing"]}
            if not res["existing"]:
                pr = STORE.create_project(org["id"], body.get("project") or "My first project")
                PROJECTS[pr["id"]] = Project(pr["id"], pr["name"], pr["env"], org["id"])
                CONTRADICTIONS[pr["id"]] = []
                _DECLARED_PAIRS[pr["id"]] = set()
                key = STORE.create_key(pr["id"], "Development key")
                out["project"] = {"id": pr["id"], "name": pr["name"], "env": pr["env"]}
                out["api_key"] = key  # secret included ONCE, at creation
            return self._send(201, out)

        if parts == ["v1", "session"]:
            _u = STORE.user_by_email((body or {}).get("email", ""))
            if _u:
                _m = STORE.mfa_state(_u["id"])
                if _m and _m["enabled"]:
                    code = str((body or {}).get("code", ""))
                    if not totp_verify(_m["secret"], code):
                        return self._err(401, "mfa_required", "MFA code required or invalid.")
            email = (body.get("email") or "").strip()
            if "@" not in email:
                return self._err(422, "invalid_request", "A valid email is required.", param="email")
            res = STORE.signup(email, "")
            return self._send(200, {"token": res["token"], "email": res["email"]})

        if parts == ["v1", "keys"]:
            pid = qs.get("project", [None])[0]
            p = self._proj(qs)
            if p is None:
                return self._err(404, "not_found", "project not found")
            bind_agent = body.get("agent_id")
            if bind_agent is not None:
                bind_agent = str(bind_agent)
                if not bind_agent.startswith("agent:") or len(bind_agent) > 80:
                    return self._err(422, "invalid_request",
                                     "agent_id must be an 'agent:<id>' identifier", param="agent_id")
            key = STORE.create_key(pid, body.get("name") or "API key",
                                   body.get("role", "developer"), agent_id=bind_agent)
            ENT.audit("key.created", actor=auth.get("user", {}).get("id"),
                      org_id=self._org_of_project(pid), project_id=pid,
                      resource=key["prefix"],
                      metadata={"agent_bound": bind_agent} if bind_agent else None,
                      correlation_id=self._corr())
            self._logreq(p, "POST", "/v1/keys", 201,
                         f"key created: {key['prefix']}…" +
                         (f" bound to {bind_agent}" if bind_agent else ""))
            return self._send(201, key)

        if len(parts) == 4 and parts[:2] == ["v1", "keys"] and parts[3] == "revoke":
            pid = qs.get("project", [None])[0]
            ok = STORE.revoke_key(parts[2], pid)
            if ok:
                ENT.audit("key.revoked", actor=auth.get("user", {}).get("id"),
                          org_id=self._org_of_project(pid), project_id=pid,
                          resource=parts[2], correlation_id=self._corr())
            return self._send(200, {"revoked": ok}) if ok else self._err(404, "not_found", "key not found")

        # ── enterprise writes (RBAC-enforced, audited) ──
        if parts == ["v1", "members", "role"]:
            oid = STORE.org_for_user(auth["user"]["id"])["id"] if "user" in auth else None
            if not self._require(auth, "member.manage", oid):
                return self._err(403, "permission", "Requires admin.")
            target = STORE.signup(body["email"], "")  # ensures user exists
            ENT.set_role(oid, target["user_id"], body["role"])
            ENT.audit("member.role_changed", actor=auth["user"]["id"], org_id=oid,
                      resource=body["email"], metadata={"role": body["role"]}, correlation_id=self._corr())
            return self._send(200, {"ok": True})
        if parts == ["v1", "retention"]:
            pid = qs.get("project", [None])[0]
            oid = self._org_of_project(pid)
            if not self._require(auth, "retention.manage", oid):
                return self._err(403, "permission", "Requires admin.")
            ENT.set_retention(pid, body.get("source_days"), body.get("memory_days"))
            ENT.audit("retention.changed", actor=auth.get("user", {}).get("id"), org_id=oid,
                      project_id=pid, metadata=body, correlation_id=self._corr())
            return self._send(200, ENT.retention(pid))
        if parts == ["v1", "retention", "sweep"]:
            pid = qs.get("project", [None])[0]
            oid = self._org_of_project(pid)
            if not self._require(auth, "retention.manage", oid):
                return self._err(403, "permission", "Requires admin.")
            res = ENT.retention_sweep(pid)
            ENT.audit("retention.sweep", actor=auth.get("user", {}).get("id"), org_id=oid,
                      project_id=pid, metadata=res, correlation_id=self._corr())
            return self._send(200, res)
        if len(parts) == 3 and parts[:2] == ["v1", "projects"] and self.command == "DELETE":
            pid = parts[2]
            oid = self._org_of_project(pid)
            if not self._require(auth, "project.delete", oid):
                return self._err(403, "permission", "Requires owner.")
            mode = qs.get("mode", ["soft"])[0]
            if mode == "erase":
                # COMPLETE tenant erasure (GDPR right-to-erasure at tenant grain).
                # Log the erasure at the ORG level FIRST — the project's own audit
                # rows are about to be removed, so the durable record must live on
                # the org, not inside the deleted project.
                ENT.audit("project.erased", actor=auth.get("user", {}).get("id"),
                          org_id=oid, project_id=None,
                          metadata={"erased_project": pid}, correlation_id=self._corr())
                report = ENT.delete_project(pid, actor=auth.get("user", {}).get("id"))
                # drop in-memory engine/project state so nothing serves stale data
                PROJECTS.pop(pid, None)
                return self._send(200, {
                    "erased": True, "project_id": pid, "report": report,
                    "note": ("complete tenant erasure: all project-scoped tables, "
                             "connector OAuth credentials, and the op-log were removed; "
                             "reboot replay cannot resurrect this project. Backups taken "
                             "before erasure still contain the data — see governance notes.")})
            # default: documented soft delete (source material + jobs), history retained
            STORE.db.execute("DELETE FROM source_records WHERE project_id=?", (pid,))
            STORE.db.execute("DELETE FROM ingest_jobs WHERE project_id=?", (pid,))
            ENT.audit("project.deleted", actor=auth.get("user", {}).get("id"), org_id=oid,
                      project_id=pid, correlation_id=self._corr())
            return self._send(200, {"deleted": True,
                "note": ("source material and jobs removed; engine memory history is "
                         "immutable and retained in the ops log. Use ?mode=erase for "
                         "complete tenant erasure.")})
        if parts == ["v1", "billing", "checkout"]:
            oid = STORE.org_for_user(auth["user"]["id"])["id"]
            if not self._require(auth, "billing.manage", oid):
                return self._err(403, "permission", "Requires owner.")
            if not providers.stripe_configured():
                return self._err(503, "unavailable", "Billing is not configured on this deployment (no STRIPE_SECRET_KEY).")
            email = auth["user"]["email"]
            cust = providers.stripe_create_customer(email)
            ENT.set_billing(oid, stripe_customer=cust["id"], plan=body.get("plan", "pro"))
            ENT.audit("billing.customer_created", actor=auth["user"]["id"], org_id=oid, correlation_id=self._corr())
            return self._send(200, {"customer": cust["id"]})

        # ── stripe webhooks: signature-verified billing lifecycle ──
        if parts == ["v1", "billing", "webhook"]:
            secret = os.environ.get("STRIPE_WEBHOOK_SECRET")
            if not secret:
                return self._err(503, "unavailable", "Billing webhooks not configured (no STRIPE_WEBHOOK_SECRET).")
            sig = self.headers.get("Stripe-Signature", "")
            raw = json.dumps(body).encode()  # raw body reconstructed from parsed JSON
            if not providers.stripe_verify_signature(raw, sig, secret):
                return self._err(400, "invalid_signature", "Stripe signature verification failed.")
            etype = body.get("type", "")
            obj = (body.get("data") or {}).get("object") or {}
            org_id = (obj.get("metadata") or {}).get("org_id")
            if org_id:
                if etype in ("customer.subscription.created", "customer.subscription.updated"):
                    ENT.set_billing(org_id, subscription_status=obj.get("status", "active"),
                                    plan=(obj.get("metadata") or {}).get("plan", "pro"),
                                    stripe_customer=obj.get("customer"))
                    ENT.billing_event(org_id, "subscription." + obj.get("status", "updated"), {"event": etype})
                elif etype == "customer.subscription.deleted":
                    ENT.set_billing(org_id, subscription_status="cancelled")
                    ENT.billing_event(org_id, "subscription.cancelled", {"event": etype})
                elif etype == "invoice.payment_failed":
                    ENT.set_billing(org_id, subscription_status="past_due")
                    ENT.billing_event(org_id, "payment.failed", {"event": etype})
            return self._send(200, {"received": True, "type": etype})

        # ── gmail oauth: begin returns an auth url; callback exchanges code ──
        if parts == ["v1", "oauth", "gmail", "begin"]:
            pid = qs.get("project", [None])[0]
            c = INGEST.add_connector(pid, "gmail", body.get("name", "Gmail"),
                                     {}, agent_id="connector:gmail", authority=body.get("authority", 0.8))
            if providers.google_configured():
                # REAL flow: signed single-use state bound to this connector,
                # then Google's actual consent screen.
                state = OAUTH_STATE.issue(pid or "", c["id"])
                return self._send(201, {"connector_id": c["id"],
                    "auth_url": providers.google_auth_url(state),
                    "state": state, "real": True})
            return self._send(201, {"connector_id": c["id"],
                "auth_url": None, "real": False,
                "note": "Google is not configured. Set GOOGLE_CLIENT_ID, "
                        "GOOGLE_CLIENT_SECRET and GOOGLE_REDIRECT_URI on the API "
                        "server (server/.env.local), then restart and reconnect.",
                "required_env": ["GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "GOOGLE_REDIRECT_URI"]})
        if parts == ["v1", "oauth", "gmail", "callback"]:
            cid = body.get("connector_id")
            state = body.get("state")
            if state is not None:
                verified = OAUTH_STATE.verify(state)
                if verified is None:
                    return self._err(403, "invalid_state", "OAuth state invalid, expired, or reused.")
                # state binds the connector, so the caller need not supply it
                cid = cid or verified["connector_id"]
            if not cid:
                return self._err(422, "invalid_request",
                                 "connector_id or a valid state is required", param="state")
            if providers.google_configured() and body.get("code"):
                # REAL path: exchange the authorization code with Google.
                try:
                    tok = providers.google_exchange_code(body["code"])
                except Exception as ex:
                    return self._err(502, "provider_error", f"Google token exchange failed: {ex}")
                OAUTH.save(cid, "gmail", tok.get("access_token"), tok.get("refresh_token"),
                           time.time() + tok.get("expires_in", 3600),
                           tok.get("scope", "gmail.readonly"), body.get("account", ""))
            else:
                # local build (no GOOGLE_* env): exercisable stub, clearly not a real exchange
                OAUTH.save(cid, "gmail", body.get("access_token", "local-dev-token"),
                           body.get("refresh_token", "local-dev-refresh"),
                           time.time() + 3600, "gmail.readonly", body.get("account", "user@gmail.com"))
            ENT.audit("connector.connected", org_id=self._org_of_project(INGEST.connector(cid)["project_id"]) if INGEST.connector(cid) else None,
                      resource=cid, correlation_id=self._corr())
            return self._send(200, {"connected": True, "connector_id": cid,
                                     "real_exchange": bool(providers.google_configured() and body.get("code"))})
        if parts == ["v1", "connectors", "bulk-delete"]:
            pid = qs.get("project", [None])[0]
            oid = self._org_of_project(pid)
            if not self._require(auth, "connector.manage", oid):
                return self._err(403, "permission", "Requires developer or above.")
            res = INGEST.delete_connectors(pid, body.get("kind"),
                                           bool(body.get("only_inactive")))
            ENT.audit("connector.bulk_deleted", org_id=oid, project_id=pid,
                      metadata={"removed": len(res.get("ids", []))}, correlation_id=self._corr())
            return self._send(200, {"deleted": len(res.get("ids", [])), "removed": res})

        if len(parts) == 3 and parts[:2] == ["v1", "connectors"] and self.command == "DELETE":
            pid = qs.get("project", [None])[0]
            conn = INGEST.connector(parts[2])
            if not conn or conn["project_id"] != pid:
                return self._err(404, "not_found", "connector not found in this project")
            oid = self._org_of_project(pid)
            if not self._require(auth, "connector.manage", oid):
                return self._err(403, "permission", "Requires developer or above.")
            try:
                OAUTH.disconnect(parts[2])
            except Exception:
                pass
            counts = INGEST.delete_connector(parts[2], pid)
            ENT.audit("connector.deleted", actor=auth.get("user", {}).get("id") if isinstance(auth, dict) else None,
                      org_id=oid, project_id=pid, resource=parts[2],
                      metadata=counts, correlation_id=self._corr())
            return self._send(200, {"deleted": True, "removed": counts,
                "note": "source material and jobs removed; memories already recorded "
                        "remain as immutable engine history"})

        if len(parts) == 4 and parts[:2] == ["v1", "connectors"] and parts[3] == "clear-errors":
            INGEST.clear_connector_errors(parts[2])
            INGEST.db.execute("UPDATE connectors SET status='active' WHERE id=? AND status IN ('needs_reauth','rate_limited','not_configured')", (parts[2],))
            INGEST.db.commit()
            return self._send(200, {"cleared": True})

        if len(parts) == 4 and parts[:2] == ["v1", "connectors"] and parts[3] == "resync":
            INGEST.db.execute("UPDATE connectors SET cursor=NULL, status='active' WHERE id=?", (parts[2],))
            INGEST.db.commit()
            RATE_LIMIT_RESETS.pop(parts[2], None)
            ENT.audit("connector.resync", org_id=self._org_of_project(qs.get("project", [None])[0]),
                      resource=parts[2], correlation_id=self._corr())
            return self._send(200, {"resync": True, "note": "cursor cleared; next sync re-reads from the beginning"})
        if len(parts) == 4 and parts[:2] == ["v1", "connectors"] and parts[3] == "disconnect":
            OAUTH.disconnect(parts[2])
            INGEST.db.execute("UPDATE connectors SET status='paused' WHERE id=?", (parts[2],))
            INGEST.db.commit()
            return self._send(200, {"disconnected": True})
        if parts == ["v1", "scheduler", "tick"]:
            return self._send(200, {"acted": SCHEDULER.tick()})

        # ── ingestion: create connector, poll, process ──
        if parts == ["v1", "connectors"]:
            pid = qs.get("project", [None])[0]
            if pid and PROJECTS.get(pid) and not PROJECTS[pid].is_demo:
                allowed, info = ENT.check_entitlement(self._org_of_project(pid), pid, "sources")
                if not allowed:
                    return self._err(402, "quota_exceeded",
                                     f"Plan '{info['plan']}' source quota reached ({info['used']}/{info['quota']}).")
            if not self._proj(qs):
                return self._err(404, "not_found", "project not found")
            c = INGEST.add_connector(pid, body["kind"], body["name"], body.get("config", {}),
                                     body.get("agent_id") or f"connector:{body['kind']}",
                                     body.get("authority", 0.5))
            return self._send(201, c)
        if len(parts) == 4 and parts[:2] == ["v1", "connectors"] and parts[3] == "poll":
            try:
                queued = INGEST.poll_connector(parts[2])
            except Exception as ex:
                from connectors import ProviderRateLimited, ProviderNotConfigured
                if isinstance(ex, providers.ProviderApiDisabled):
                    INGEST.db.execute("UPDATE connectors SET status='not_configured' WHERE id=?", (parts[2],))
                    INGEST.db.commit()
                    return self._send(503, {"error": {"type": "api_not_enabled",
                        "message": str(ex), "provider": ex.provider,
                        "console_url": ex.console_url,
                        "action": "Enable the Gmail API for this Google Cloud project, "
                                  "then sync again. Reconnecting will not help."}})
                if isinstance(ex, providers.ProviderScopeError):
                    INGEST.db.execute("UPDATE connectors SET status='needs_reauth' WHERE id=?", (parts[2],))
                    INGEST.db.commit()
                    return self._send(409, {"error": {"type": "missing_scope",
                        "message": str(ex), "provider": ex.provider,
                        "action": "Reconnect and approve mailbox read access."}})
                if isinstance(ex, providers.ProviderUnreachable):
                    # Network problem between this server and Google — not a
                    # credential problem on either side. Keep status untouched
                    # so a transient outage doesn't demand reconnection.
                    return self._send(503, {"error": {"type": "provider_unreachable",
                        "message": str(ex),
                        "action": "Check this server's network access to "
                                  "googleapis.com, then sync again."}})
                if isinstance(ex, providers.ProviderConfigError):
                    # Operator credentials are wrong. Deliberately NOT
                    # 'needs_reauth': telling the user to reconnect for a
                    # server-side misconfiguration wastes their consent flow.
                    INGEST.db.execute("UPDATE connectors SET status='not_configured' WHERE id=?", (parts[2],))
                    INGEST.db.commit()
                    return self._send(503, {"error": {"type": "provider_config",
                        "message": str(ex), "provider": ex.provider,
                        "action": "Fix GOOGLE_CLIENT_ID/GOOGLE_CLIENT_SECRET in the "
                                  "server environment, restart, then sync again."}})
                if isinstance(ex, providers.NeedsReauth):
                    INGEST.db.execute("UPDATE connectors SET status='needs_reauth' WHERE id=?", (parts[2],))
                    INGEST.db.commit()
                    ENT.audit("connector.needs_reauth", org_id=self._org_of_project(qs.get("project", [None])[0]),
                              resource=parts[2], correlation_id=self._corr())
                    return self._send(409, {"error": {"type": "needs_reauth",
                        "message": str(ex), "provider": ex.provider,
                        "action": "Reconnect this source to grant access again."}})
                if isinstance(ex, ProviderNotConfigured):
                    INGEST.db.execute("UPDATE connectors SET status='not_configured' WHERE id=?", (parts[2],))
                    INGEST.db.commit()
                    return self._send(503, {"error": {"type": "not_configured",
                        "message": str(ex), "provider": ex.provider,
                        "required_env": ex.env_vars}})
                if isinstance(ex, ProviderRateLimited):
                    INGEST.db.execute("UPDATE connectors SET status='rate_limited' WHERE id=?", (parts[2],))
                    INGEST.db.commit()
                    if ex.reset_epoch:
                        RATE_LIMIT_RESETS[parts[2]] = ex.reset_epoch
                    return self._send(429, {"error": {"type": "rate_limited",
                        "message": str(ex), "provider": ex.provider,
                        "reset_epoch": ex.reset_epoch}})
                raise
            if queued:
                ENT.meter(qs.get("project", [None])[0], "source_records", queued)
            return self._send(200, {"queued": queued})
        if parts == ["v1", "jobs", "retry-dead"]:
            pid = qs.get("project", [None])[0]
            n = INGEST.retry_dead_letters(pid)
            ENT.audit("jobs.retry_dead_letters", org_id=self._org_of_project(pid),
                      project_id=pid, metadata={"requeued": n}, correlation_id=self._corr())
            return self._send(200, {"requeued": n})
        if len(parts) == 4 and parts[:2] == ["v1", "jobs"] and parts[3] == "cancel":
            ok = INGEST.cancel_job(int(parts[2]))
            return self._send(200, {"cancelled": ok})
        # ── project settings write ──
        if parts == ["v1", "settings"]:
            p = self._proj(qs)
            if p is None:
                return self._err(404, "not_found", "project not found")
            for k in ("llm_enabled", "llm_model"):
                if k in body:
                    ENT.set_setting(p.id, k, str(body[k]))
            ENT.audit("settings.changed", org_id=self._org_of_project(p.id), project_id=p.id,
                      metadata={k: body[k] for k in body if k in ("llm_enabled", "llm_model")},
                      correlation_id=self._corr())
            return self._send(200, {k: ENT.setting(p.id, k) for k in ("llm_enabled", "llm_model")})

        # ── org identity: configure who "we" are ─────────────────────────
        if parts == ["v1", "identity"]:
            p = self._proj(qs)
            if p is None:
                return self._err(404, "not_found", "project not found")
            emails_in = body.get("emails") or []
            domains_in = body.get("domains") or []
            if not isinstance(emails_in, list) or not isinstance(domains_in, list):
                return self._err(400, "invalid_request", "emails and domains must be lists of strings")
            ident = {
                "company_name": (str(body.get("company_name") or "")).strip() or None,
                "emails": [str(x).lower().strip() for x in emails_in if str(x).strip()],
                "domains": [str(x).lower().strip().lstrip("@") for x in domains_in if str(x).strip()],
            }
            for e in ident["emails"]:
                if "@" not in e:
                    return self._err(400, "invalid_email", f"'{e}' is not an email address")
            ENT.set_setting(p.id, "org_identity", json.dumps(ident))
            ENT.audit("identity.changed", org_id=self._org_of_project(p.id),
                      project_id=p.id, metadata=ident, correlation_id=self._corr())
            return self._send(200, _org_identity(p.id))

        # ── relationship correction: reusable intelligence, engine untouched ──
        if parts == ["v1", "relationships"]:
            p = self._proj(qs)
            if p is None:
                return self._err(404, "not_found", "project not found")
            key_type = body.get("key_type")
            key = (body.get("key") or "").lower().strip()
            role = body.get("role")
            if key_type not in ("domain", "email", "entity"):
                return self._err(400, "invalid_key_type", "key_type must be domain, email or entity")
            if not key:
                return self._err(400, "invalid_key", "key required")
            if key_type == "domain":
                key = key.lstrip("@")
            if role is None:
                STORE.db.execute(
                    "DELETE FROM relationship_overrides WHERE project_id=? AND key_type=? AND key=?",
                    (p.id, key_type, key))
                STORE.db.commit()
                return self._send(200, {"removed": True, "key_type": key_type, "key": key})
            if role not in RELATIONSHIP_ROLES:
                return self._err(400, "invalid_role",
                                 f"role must be one of {', '.join(RELATIONSHIP_ROLES)}")
            STORE.db.execute(
                "INSERT OR REPLACE INTO relationship_overrides"
                "(project_id, key_type, key, role, source, note, ts) VALUES(?,?,?,?,?,?,?)",
                (p.id, key_type, key, role, "user", (body.get("note") or "")[:300], time.time()))
            STORE.db.commit()
            ENT.audit("relationship.corrected", org_id=self._org_of_project(p.id),
                      project_id=p.id, metadata={"key_type": key_type, "key": key, "role": role},
                      correlation_id=self._corr())
            return self._send(200, {"key_type": key_type, "key": key, "role": role})

        # ── backups: run now / verify restore (operator) ──
        if parts == ["v1", "admin", "backups", "run"]:
            if not self._is_operator(auth):
                return self._err(403, "permission", "Operator access only.")
            st_ = BACKUPS.run()
            ENT.audit("backup.run", actor=auth["user"]["id"],
                      metadata={"failing": st_["failing"]}, correlation_id=self._corr())
            return self._send(200, st_)
        if parts == ["v1", "admin", "backups", "verify"]:
            if not self._is_operator(auth):
                return self._err(403, "permission", "Operator access only.")
            return self._send(200, BACKUPS.verify_restore())

        # ── MFA: enroll -> activate -> enforced at session creation ──
        if parts == ["v1", "mfa", "enroll"]:
            if "user" not in auth:
                return self._err(401, "auth", "Session required.")
            sec = totp_secret()
            STORE.mfa_enroll(auth["user"]["id"], sec)
            return self._send(200, {"secret": sec,
                "otpauth": f"otpauth://totp/OMEM:{auth['user']['email']}?secret={sec}&issuer=OMEM"})
        if parts == ["v1", "mfa", "activate"]:
            if "user" not in auth:
                return self._err(401, "auth", "Session required.")
            st_ = STORE.mfa_state(auth["user"]["id"])
            if not st_ or not totp_verify(st_["secret"], str(body.get("code", ""))):
                return self._err(403, "mfa_invalid", "Invalid MFA code.")
            STORE.mfa_activate(auth["user"]["id"])
            ENT.audit("mfa.activated", actor=auth["user"]["id"], correlation_id=self._corr())
            return self._send(200, {"enabled": True})
        if parts == ["v1", "sessions", "revoke"]:
            tok = (self.headers.get("Authorization") or "").replace("Bearer ", "")
            ok = STORE.revoke_session(tok)
            return self._send(200, {"revoked": ok})

        # ── operator: set customer/pilot status ──
        if len(parts) == 5 and parts[:3] == ["v1", "admin", "orgs"] and parts[4] == "status":
            if not self._is_operator(auth):
                return self._err(403, "permission", "Operator access only.")
            try:
                st_ = ENT.set_customer_status(parts[3], status=body.get("status"),
                                              pilot_start=body.get("pilot_start"),
                                              pilot_end=body.get("pilot_end"), notes=body.get("notes"))
            except AssertionError:
                return self._err(422, "invalid_request", f"status must be one of {list(ENT.STATUSES)}")
            ENT.audit("customer.status_changed", actor=auth["user"]["id"], org_id=parts[3],
                      metadata=body, correlation_id=self._corr())
            return self._send(200, st_)

        # ── operator: set plan (entitlement change; billing truth stays with Stripe) ──
        if len(parts) == 5 and parts[:3] == ["v1", "admin", "orgs"] and parts[4] == "plan":
            if not self._is_operator(auth):
                return self._err(403, "permission", "Operator access only.")
            plan = body.get("plan")
            if plan not in PLANS:
                return self._err(422, "invalid_request", f"plan must be one of {list(PLANS)}")
            ENT.set_billing(parts[3], plan=plan)
            ENT.billing_event(parts[3], "plan.set_by_operator", {"plan": plan})
            ENT.audit("billing.plan_changed", actor=auth["user"]["id"], org_id=parts[3],
                      metadata={"plan": plan}, correlation_id=self._corr())
            return self._send(200, ENT.billing(parts[3]))

        # ── pilot feedback (write; product telemetry outside the engine) ──
        if parts == ["v1", "feedback"]:
            p = self._proj(qs)
            if p is None:
                return self._err(404, "not_found", "project not found")
            kind = body.get("kind")
            if kind not in ENT.FEEDBACK_KINDS:
                return self._err(422, "invalid_request",
                                 f"kind must be one of {list(ENT.FEEDBACK_KINDS)}", param="kind")
            ENT.add_feedback(p.id, kind, body.get("assertion_id"), body.get("comment"),
                             auth.get("user", {}).get("id") if isinstance(auth, dict) else None)
            ENT.meter(p.id, "feedback_submitted")
            return self._send(201, {"recorded": True})

        # ── automatic memory: webhook receiver (push -> pipeline) ──
        if len(parts) == 3 and parts[:2] == ["v1", "webhooks"]:
            cid = parts[2]
            conn = INGEST.connector(cid)
            if conn is None:
                return self._err(404, "not_found", "webhook connector not found")
            ext_id = body.get("id") or _mint_global("wh")
            INGEST.push_item(cid, ext_id, body)
            queued = INGEST.poll_connector(cid)
            ENT.meter(conn["project_id"], "webhook_deliveries")
            if queued:
                ENT.meter(conn["project_id"], "source_records", queued)
            return self._send(202, {"accepted": True, "queued": queued})

        # ── automatic memory: document upload (text -> pipeline) ──
        if parts == ["v1", "documents"]:
            p = self._proj(qs)
            if p is None:
                return self._err(404, "not_found", "project not found")
            text = body.get("text")
            if not text:
                return self._err(422, "invalid_request", "text is required", param="text")
            # find-or-create the project's documents connector
            docs = [c for c in INGEST.connectors_for(p.id) if c["kind"] == "documents"]
            conn = docs[0] if docs else INGEST.add_connector(
                p.id, "documents", "Uploaded documents", {}, agent_id="connector:documents", authority=0.7)
            ext_id = body.get("filename") or _mint_global("doc")
            INGEST.push_item(conn["id"], ext_id, {
                "customer": body.get("customer", ""), "subject": body.get("filename", "document"),
                "body": text, "at": "now"})
            queued = INGEST.poll_connector(conn["id"])
            res = INGEST.process_pending(p.id)
            ENT.meter(p.id, "documents_uploaded")
            return self._send(201, {"connector": conn["id"], "queued": queued, **res})

        # ── managed agent DX: learn (text -> candidate facts -> engine) ──
        if parts == ["v1", "learn"]:
            p = self._proj(qs)
            if p is None:
                return self._err(404, "not_found", "project not found")
            if not p.is_demo:
                allowed, info = ENT.check_entitlement(self._org_of_project(p.id), p.id, "memories")
                if not allowed:
                    return self._err(402, "quota_exceeded",
                                     f"Plan '{info['plan']}' memory quota reached ({info['used']}/{info['quota']}).")
            agent = body.get("agent")
            agent, _err = self._effective_agent(auth, agent)
            if _err:
                return
            agent = agent or "agent:default"
            text = body.get("text", "")
            if len(text or "") > MAX_TEXT_CHARS:
                return self._err(413, "text_too_large",
                                 f"text exceeds the {MAX_TEXT_CHARS}-character limit.", param="text")
            source = body.get("source") or _mint_global("src")
            about = body.get("about")  # optional explicit subject hint
            if not text:
                return self._err(422, "invalid_request", "text is required", param="text")
            # ensure the agent exists (managed convenience)
            if agent not in p.labels:
                record(p, "agent", {"id": agent, "kind": "system", "label": agent})
            # extraction: reuse the same extractor the ingestion pipeline uses
            from ingest import RuleExtractor
            ext = _extractor_for({"project_id": p.id}) or RuleExtractor()
            payload = {"customer": about.split(":")[-1] if about else body.get("customer", ""),
                       "subject": source, "body": text, "from": body.get("from", ""), "at": "now"}
            try:
                facts = ext.extract(payload)
            except Exception as ex:
                # Provider failure must be legible and recorded — never a bare 500,
                # and never a memory invented to paper over the outage.
                ENT.log_extraction(p.id, None, type(ext).__name__,
                                   model=ENT.setting(p.id, "llm_model"),
                                   facts=0, ok=False, error=f"{type(ex).__name__}: {ex}")
                return self._send(502, {"error": {
                    "type": "extraction_failed",
                    "message": f"The configured extraction provider failed: {ex}. "
                               "No memory was created. Check the API key and model in "
                               "Settings, or disable LLM extraction to fall back to rules.",
                    "extractor": type(ext).__name__,
                    "model": ENT.setting(p.id, "llm_model")}})
            ENT.meter(p.id, "learn_requests")
            if not facts:
                return self._send(200, {"learned": [], "note": "no durable facts found in text",
                                        "source": source})
            # one event = the source moment (grounding anchor)
            ev = _mint_global("evt")
            record(p, "event", {"id": ev, "ekind": "learned", "event_time": p.tick(), "label": source})
            learned = []
            for f in facts:
                subj = f["subject"]
                if self.resolver_enabled() and subj["id"].startswith("customer:"):
                    res = RESOLVER.resolve(p.id, subj["id"], p.labels, ev)
                    subj = {**subj, "id": res["entity_id"]}
                if subj["id"] not in p.labels:
                    record(p, "entity", {"id": subj["id"], "type": subj["type"], "label": subj.get("label")})
                aid = _mint_global("a")
                record(p, "assert", {"id": aid, "agent": agent, "subjects": [subj["id"]],
                                     "proposition": f["proposition"], "assertion_time": p.now(),
                                     "confidence": f.get("confidence"), "label": f.get("label")})
                record(p, "derive", {"id": _mint_global("d"), "consequent": aid,
                                     "antecedents": [ev], "dkind": "extraction"})
                ENT.meter(p.id, "assertions_created")
                # the engine decides the resulting state; we just report it
                st = e_state(p, [subj["id"]], f["proposition"])
                learned.append({"assertion": aid, "subject": subj["id"],
                                "proposition": f["proposition"], "state": st,
                                "evidence": f.get("evidence")})
            return self._send(201, {"learned": learned, "source": source, "event": ev})

        # ── P3: consolidation pass (also run by the background scheduler) ──
        if parts == ["v1", "memory", "index", "rebuild"]:
            p = self._proj(qs)
            if p is None:
                return self._err(404, "not_found", "project not found")
            return self._send(200, _cand_index.rebuild(STORE.db, p))

        if parts == ["v1", "memory", "graph", "rebuild"]:
            p = self._proj(qs)
            if p is None:
                return self._err(404, "not_found", "project not found")
            return self._send(200, _graph.rebuild_projection(STORE.db, p))

        if parts == ["v1", "memory", "consolidate"]:
            p = self._proj(qs)
            if p is None:
                return self._err(404, "not_found", "project not found")
            result = _consol.consolidate(p, STORE.db, SCOPES, record, _mint_global,
                                         contradictions=CONTRADICTIONS.get(p.id, []))
            ENT.audit("memory.consolidated", org_id=self._org_of_project(p.id),
                      metadata={k: v for k, v in result.items() if k != "details"},
                      correlation_id=self._corr())
            return self._send(200, result)

        # ── scopes: explicit promotion + team membership ──
        if parts == ["v1", "memory", "share"]:
            p = self._proj(qs)
            if p is None:
                return self._err(404, "not_found", "project not found")
            aid = body.get("assertion_id")
            scope = body.get("scope")
            if not aid or p.engine.store.assertion(aid) is None:
                return self._err(404, "not_found", "assertion not found")
            if not _recall.valid_scope(scope or ""):
                return self._err(422, "invalid_request",
                                 "scope must be org, team:<id>, agent:<id> or user:<id>",
                                 param="scope")
            SCOPES.set(p.id, aid, scope, granted_by=body.get("granted_by"))
            ENT.audit("memory.scope_changed", org_id=self._org_of_project(p.id),
                      resource=aid, metadata={"scope": scope}, correlation_id=self._corr())
            return self._send(200, {"assertion_id": aid, "scope": scope,
                                    "note": "visibility changed; attribution and provenance are immutable"})

        if parts == ["v1", "memory", "class"]:
            p = self._proj(qs)
            if p is None:
                return self._err(404, "not_found", "project not found")
            aid = body.get("assertion_id")
            if not aid or p.engine.store.assertion(aid) is None:
                return self._err(404, "not_found", "assertion not found")
            try:
                _consol.set_class(STORE.db, p.id, aid, str(body.get("mclass") or ""),
                                  ttl=float(body["ttl"]) if body.get("ttl") is not None else None)
            except (ValueError, TypeError) as ex:
                return self._err(422, "invalid_request", str(ex), param="mclass")
            return self._send(200, {"assertion_id": aid,
                                    "mclass": body.get("mclass"),
                                    "ttl": body.get("ttl"),
                                    "note": "memory class affects retrieval only; canonical history is immutable"})

        if parts == ["v1", "teams"]:
            p = self._proj(qs)
            if p is None:
                return self._err(404, "not_found", "project not found")
            team = body.get("team_id")
            agents = body.get("agents")
            if not team or not isinstance(agents, list):
                return self._err(422, "invalid_request", "team_id and agents[] required")
            SCOPES.set_team(p.id, str(team), [str(a) for a in agents][:200])
            return self._send(200, {"team_id": team, "agents": agents})

        # ── observe(): the agent-experience entry point. Feed a raw
        # interaction; OMEM decides what (if anything) becomes memory.
        # Semantic LLM when configured, deterministic contextual extractor
        # otherwise. The engine remains the sole authority.
        # ── self-healing subsystem (RBAC-gated, audited, project-scoped) ──
        if len(parts) >= 2 and parts[0] == "v1" and parts[1] == "healing":
            p = self._proj(qs)
            if p is None:
                return self._err(404, "not_found", "project not found")
            org_id = self._org_of_project(p.id)
            actor = self._healing_actor(auth)

            def _bound_can(permission):
                return self._require(auth, permission, org_id, p.id)

            # POST /v1/healing/failures — report a failure, get prior memory back
            if parts[2:] == ["failures"]:
                if not _bound_can("heal.report"):
                    return self._err(403, "permission", "requires heal.report")
                healer = self._make_healer(_bound_can)
                failure = healer.capture(org_id, p.id, body if isinstance(body, dict) else {})
                memory = healer.recall(org_id, p.id, failure)
                ENT.audit("healing.failure.reported", actor=actor, org_id=org_id, project_id=p.id,
                          resource=failure["id"], metadata={"component": failure["component"]})
                return self._send(201, {"failure": failure, "memory": HEAL._memory_summary(memory)})

            # POST /v1/healing/handle — full autonomous loop (no LLM here; server
            # side uses prior memory. An LLM-in-the-loop is driven client-side and
            # submits a plan via this same endpoint's optional 'plan' field.)
            if parts[2:] == ["handle"]:
                if not _bound_can("heal.execute.low"):
                    return self._err(403, "permission", "requires at least heal.execute.low")
                healer = self._make_healer(_bound_can)
                error = body.get("error") if isinstance(body, dict) else None
                if not isinstance(error, dict) or not error.get("component"):
                    return self._err(422, "invalid_request", "error{component,error_type,...} required")
                approved_by = body.get("approved_by")
                submitted_plan = body.get("plan") if isinstance(body.get("plan"), dict) else None
                diagnose = (lambda f, m: submitted_plan) if submitted_plan else None
                result = healer.handle(org_id, p.id, error, owner=actor,
                                       diagnose_fn=diagnose, approved_by=approved_by)
                ENT.audit("healing.handle", actor=actor, org_id=org_id, project_id=p.id,
                          resource=result.get("failure_id"), metadata={"status": result["status"]})
                return self._send(200, result)

            # POST /v1/healing/health — component health report
            if parts[2:] == ["health"]:
                if not _bound_can("heal.report"):
                    return self._err(403, "permission", "requires heal.report")
                comp = body.get("component")
                if not comp:
                    return self._err(422, "invalid_request", "component required")
                HEAL_STORE.report_health(org_id, p.id, str(comp), str(body.get("status", "unknown")),
                                         reason=str(body.get("reason", "")), metadata=body.get("metadata"))
                return self._send(201, {"ok": True})

            # POST /v1/healing/snapshots — record a known-good state
            if parts[2:] == ["snapshots"]:
                if not _bound_can("heal.report"):
                    return self._err(403, "permission", "requires heal.report")
                sid = HEAL_STORE.record_snapshot(org_id, p.id, str(body.get("label", "")),
                                                 str(body.get("kind", "state")), body.get("payload") or {})
                return self._send(201, {"id": sid})

            return self._err(404, "not_found", "unknown healing route")

        if parts == ["v1", "observe"]:
            p = self._proj(qs)
            if p is None:
                return self._err(404, "not_found", "project not found")
            if not p.is_demo:
                allowed, info = ENT.check_entitlement(self._org_of_project(p.id), p.id, "memories")
                if not allowed:
                    return self._err(402, "quota_exceeded",
                                     f"Plan '{info['plan']}' memory quota reached ({info['used']}/{info['quota']}).")
            agent = body.get("agent")
            agent, _err = self._effective_agent(auth, agent)
            if _err:
                return
            agent = agent or "agent:default"
            inter = body.get("interaction")
            if not isinstance(inter, dict) or not (inter.get("text") or "").strip():
                return self._err(422, "invalid_request",
                                 "interaction.text is required", param="interaction")
            if len(inter.get("text") or "") > MAX_TEXT_CHARS:
                return self._err(413, "text_too_large",
                                 f"interaction.text exceeds the {MAX_TEXT_CHARS}-character limit.",
                                 param="interaction")
            text = inter["text"]
            speaker = inter.get("speaker") or ""
            audience = inter.get("audience") or ""
            at = inter.get("at") or "now"
            if at != "now":
                try:
                    at = int(at)
                except (TypeError, ValueError):
                    at = "now"  # malformed event time -> treat as observed-now
            source = body.get("source") or _mint_global("obs")
            if agent not in p.labels:
                record(p, "agent", {"id": agent, "kind": "system", "label": agent})

            ident = _org_identity(p.id)
            payload = {"subject": inter.get("topic") or source, "body": text,
                       "from": speaker, "to": audience, "at": at,
                       "thread_id": inter.get("thread_id"),
                       "message_id": source, "headers": {}}
            if ENT.setting(p.id, "llm_enabled") == "1" and providers.llm_configured():
                ext = _semantic_extractor_for(
                    {"project_id": p.id, "id": f"observe:{agent}"}, ident)
            else:
                from extraction import ContextualBusinessExtractor
                ext = ContextualBusinessExtractor(ident)
            try:
                facts = ext.extract(payload)
            except Exception as ex:
                ENT.log_extraction(p.id, None, type(ext).__name__,
                                   model=ENT.setting(p.id, "llm_model"),
                                   facts=0, ok=False, error=f"{type(ex).__name__}: {ex}")
                return self._send(502, {"error": {
                    "type": "extraction_failed",
                    "message": f"The configured extraction provider failed: {ex}. "
                               "No memory was created.",
                    "extractor": type(ext).__name__}})
            ENT.meter(p.id, "observe_requests")
            if not facts:
                return self._send(200, {"observed": True, "memories": [],
                                        "note": "nothing in this interaction met the bar for durable memory",
                                        "source": source})
            ev = _mint_global("evt")
            # event_time = when the interaction happened. For 'now' we advance
            # the logical clock (p.tick) so each observation gets a fresh,
            # distinct time — matching the prior behaviour that consolidation's
            # temporal-diversity policy depends on. For an explicit 'at', use it.
            _obs_event_T = p.tick() if at in ("now", None) else int(at)
            record(p, "event", {"id": ev, "ekind": "observation",
                                "event_time": _obs_event_T, "label": source})
            out = []
            for f in facts:
                subj = f["subject"]
                if self.resolver_enabled() and subj["id"].startswith("customer:"):
                    res = RESOLVER.resolve(p.id, subj["id"], p.labels, ev)
                    subj = {**subj, "id": res["entity_id"]}
                if subj["id"] not in p.labels:
                    record(p, "entity", {"id": subj["id"], "type": subj["type"],
                                         "label": subj.get("label")})
                # supersession: a stronger observation closes open weaker
                # beliefs about the same subject — via the ENGINE's op
                olds = []
                try:
                    from extraction import SUPERSEDES as _sup, canonical_proposition as _cp
                    weaker = set(_sup.get(_cp(f["proposition"]), ()))
                    rel = f.get("existing_memory_relationship") or {}
                    if isinstance(rel, dict) and rel.get("relation") == "supersedes" \
                            and rel.get("target_proposition"):
                        weaker.add(_cp(rel["target_proposition"]))
                    Tnow = p.now()
                    for a_open in p.engine.store.assertions():
                        if (a_open.proposition in weaker and subj["id"] in a_open.subjects
                                and p.engine.ledger.is_open_at(a_open, Tnow)):
                            olds.append(a_open.id)
                except Exception:
                    olds = []
                # duplicate control: an OPEN identical belief by the same
                # agent is confirmation, not new memory (growth stays bounded);
                # it still participates in supersession above
                if not olds:
                    from extraction import canonical_proposition as _cp2
                    Td = p.now()
                    # Duplicate control + REINFORCEMENT: an open identical
                    # belief that THIS AGENT CAN SEE is confirmation of one
                    # underlying fact — recorded as a reinforcement row with
                    # the reinforcing agent, never a duplicate assertion.
                    # Invisible (out-of-scope) beliefs are never matched:
                    # matching them would leak their existence, so the agent
                    # forms its own memory instead.
                    _teams = SCOPES.teams_of(p.id, agent)
                    dup_open = next(
                        (x for x in sorted(p.engine.store.assertions(),
                                           key=lambda y: (y.assertion_time, y.id))
                         if subj["id"] in x.subjects
                         and _cp2(x.proposition) == _cp2(f["proposition"])
                         and p.engine.ledger.is_open_at(x, Td)
                         and SCOPES.visible(SCOPES.of(p.id, x.id), agent, _teams,
                                            body.get("user"))), None)
                    if dup_open is not None:
                        _consol.reinforce(STORE.db, p.id, dup_open.id,
                                          observed_by=agent, source=source)
                        st = e_state(p, [subj["id"]], f["proposition"])
                        out.append({"assertion": dup_open.id, "subject": subj["id"],
                                    "proposition": f["proposition"], "state": st,
                                    "superseded": [], "scope": SCOPES.of(p.id, dup_open.id),
                                    "duplicate": True, "reinforced": True,
                                    "learned_by": dup_open.agent,
                                    "supported_by": 1 + len(_consol.reinforcement_rows(
                                        STORE.db, p.id, dup_open.id)),
                                    "evidence": f.get("evidence"),
                                    "reasoning": f.get("reasoning_summary")})
                        continue
                aid = _mint_global("a")
                _rt = f.get("relation_target")
                _subjects = [subj["id"]]
                if isinstance(_rt, dict) and _rt.get("id"):
                    if _rt["id"] not in p.labels:
                        record(p, "entity", {"id": _rt["id"],
                                             "type": _rt.get("type", "entity"),
                                             "label": _rt.get("label")})
                    _subjects = [subj["id"], _rt["id"]]
                base = {"id": aid, "agent": agent, "subjects": _subjects,
                        "proposition": f["proposition"], "assertion_time": p.now(),
                        "event_time": _obs_event_T,
                        "confidence": f.get("confidence"), "label": f.get("label")}
                if olds:
                    record(p, "supersede", {**base, "olds": olds, "did": _mint_global("d")})
                else:
                    record(p, "assert", base)
                    record(p, "derive", {"id": _mint_global("d"), "consequent": aid,
                                         "antecedents": [ev], "dkind": "extraction"})
                ENT.meter(p.id, "assertions_created")
                if f.get("relation") and isinstance(_rt, dict) and _rt.get("id"):
                    _graph.record_edge(STORE.db, p.id, aid, subj["id"],
                                       f["relation"], _rt["id"])
                # PRIVATE BY DEFAULT: an agent's observation is its own memory
                # unless the caller explicitly widens it. Sharing later is an
                # explicit promotion (POST /v1/memory/share).
                mem_scope = body.get("scope") or f"agent:{agent}"
                if not _recall.valid_scope(mem_scope):
                    mem_scope = f"agent:{agent}"
                SCOPES.set(p.id, aid, mem_scope, granted_by=agent)
                st = e_state(p, [subj["id"]], f["proposition"])
                out.append({"assertion": aid, "subject": subj["id"],
                            "proposition": f["proposition"], "state": st,
                            "superseded": olds, "scope": mem_scope,
                            "evidence": f.get("evidence"),
                            "reasoning": f.get("reasoning_summary")})
            return self._send(201, {"observed": True, "memories": out,
                                    "source": source, "event": ev})

        # ── managed agent DX: recall (search finds; engine decides state) ──
        if parts == ["v1", "brief"]:
            p = self._proj(qs)
            if p is None:
                return self._err(404, "not_found", "project not found")
            agent = body.get("agent")
            agent, _err = self._effective_agent(auth, agent)
            if _err:
                return
            as_of = body.get("as_of")
            if as_of is not None and as_of != "now":
                try:
                    as_of = int(as_of)
                except (TypeError, ValueError):
                    return self._err(422, "invalid_request", "as_of must be int or 'now'")
            else:
                as_of = None
            try:
                limit = _clamp_limit(body.get("limit"), 12)
            except (TypeError, ValueError):
                limit = 12
            try:
                budget = int(body["max_chars"]) if body.get("max_chars") else None
            except (TypeError, ValueError):
                budget = None

            def _extras_b(aid, _p=p):
                a = _p.engine.store.assertion(aid)
                mclass, ttl = _consol.class_of(STORE.db, _p.id, aid,
                                               a.proposition if a else "")
                n = STORE.db.execute("SELECT COUNT(*) n FROM memory_reinforcements "
                                     "WHERE project_id=? AND assertion_id=?",
                                     (_p.id, aid)).fetchone()["n"]
                return {"mclass": mclass, "ttl": ttl, "reinforcements": n}

            ENT.meter(p.id, "agent_briefs")
            brief = _brief.build_situation_brief(
                p, STORE.db, SCOPES, agent=agent,
                context=str(body.get("context") or ""),
                task=str(body.get("task") or ""),
                about=body.get("about"), user=body.get("user"),
                entities=[e for e in (body.get("entities") or []) if isinstance(e, str)],
                as_of=as_of, limit=limit, max_chars=budget,
                extras_lookup=_extras_b,
                conflict_analyzer=lambda pair, _p=p: _conflict.analyze_pair(_p, STORE.db, pair),
                source_lookup=lambda aid: (lambda s: {"source_record": s["id"],
                    "connector": s["connector_id"], "external_id": s["external_id"]}
                    if s else None)(INGEST.source_for_assertion(p.id, aid)))
            for sec in brief["sections"].values():
                for m in sec:
                    ENT.count_recall(p.id, m["id"])
            return self._send(200, brief)

        if parts == ["v1", "recall"]:
            p = self._proj(qs)
            if p is None:
                return self._err(404, "not_found", "project not found")
            # ── intelligent recall: context/task in, MemoryPack out ──
            if body.get("context") is not None or body.get("task") is not None \
                    or body.get("entities") is not None:
                agent = body.get("agent")
                agent, _err = self._effective_agent(auth, agent)
                if _err:
                    return
                as_of = body.get("as_of")
                if as_of is not None and as_of != "now":
                    try:
                        as_of = int(as_of)
                    except (TypeError, ValueError):
                        return self._err(422, "invalid_request",
                                         "as_of must be a logical time integer or 'now'")
                else:
                    as_of = None
                try:
                    limit = _clamp_limit(body.get("limit"), 10)
                except (TypeError, ValueError):
                    limit = 10
                ENT.meter(p.id, "agent_recalls")
                def _extras(aid, _p=p):
                    a = _p.engine.store.assertion(aid)
                    mclass, ttl = _consol.class_of(STORE.db, _p.id, aid,
                                                   a.proposition if a else "")
                    n = STORE.db.execute(
                        "SELECT COUNT(*) n FROM memory_reinforcements "
                        "WHERE project_id=? AND assertion_id=?",
                        (_p.id, aid)).fetchone()["n"]
                    return {"mclass": mclass, "ttl": ttl, "reinforcements": n}
                _ents = [e for e in (body.get("entities") or []) if isinstance(e, str)]
                if isinstance(body.get("about"), str) and body["about"]:
                    _ents = [body["about"]] + _ents  # about= works WITH context
                try:
                    _budget = int(body["max_chars"]) if body.get("max_chars") else None
                except (TypeError, ValueError):
                    _budget = None
                pack = _recall.build_memory_pack(
                    p, STORE.db, SCOPES, agent=agent, extras_lookup=_extras,
                    conflict_analyzer=lambda pair, _p=p: _conflict.analyze_pair(_p, STORE.db, pair),
                    max_chars=_budget,
                    context=str(body.get("context") or ""),
                    task=str(body.get("task") or ""),
                    user=body.get("user"),
                    entities=_ents,
                    as_of=as_of, limit=limit,
                    source_lookup=lambda aid: (lambda s: {
                        "source_record": s["id"],
                        "connector": s["connector_id"],
                        "external_id": s["external_id"]} if s else None)(
                            INGEST.source_for_assertion(p.id, aid)))
                for m in pack["memories"]:
                    ENT.count_recall(p.id, m["id"])
                return self._send(200, pack)
            about = body.get("about")
            if not about:
                return self._err(422, "invalid_request", "about is required", param="about")
            ENT.meter(p.id, "agent_recalls")
            T = p.now()
            viewer = body.get("agent")
            viewer, _err = self._effective_agent(auth, viewer)
            if _err:
                return
            memories = []
            for a in p.engine.store.assertions():
                if about in a.subjects:
                    if not _viewer_scope_ok(p.id, a.id, viewer, body.get("user")):
                        continue
                    st = e_state(p, list(a.subjects), a.proposition)
                    prov_ids, grounded = p.engine.provenance(a.id)
                    src = INGEST.source_for_assertion(p.id, a.id)
                    ENT.count_recall(p.id, a.id)
                    memories.append({
                        "assertion": a.id, "proposition": a.proposition,
                        "subjects": list(a.subjects), "state": st,
                        "assertion_time": a.assertion_time,
                        "grounded": grounded == "GROUNDED" or grounded is True,
                        "provenance_count": len(prov_ids),
                        "source": (json.loads(src["payload"]).get("subject") if src else None),
                    })
            return self._send(200, {"about": about, "memories": memories,
                                    "count": len(memories),
                                    "note": "belief state is determined by the frozen engine"})

        if parts == ["v1", "ingest", "process"]:
            pid = qs.get("project", [None])[0]
            return self._send(200, INGEST.process_pending(pid))

        # ── memory scanner: scan / apply / review-queue ───────────────────
        if parts == ["v1", "memory", "scan"]:
            pid = qs.get("project", [None])[0]
            p = PROJECTS.get(pid)
            if not p:
                return self._send(404, {"error": "project not found"})
            scope = body.get("scope", "all")
            if scope not in ("all", "recent"):
                return self._err(400, "invalid_scope", "scope must be 'all' or 'recent'")
            scanner = _scanner_for(p)
            scan_id = scanner.start_scan(triggered_by="api", scope=scope)
            scan = scanner.get_scan(scan_id)
            self._logreq(p, "POST", "/v1/memory/scan", 201, f"scan {scan_id}")
            return self._send(201, scan)

        if len(parts) == 5 and parts[:2] == ["v1", "memory"] and parts[2] == "scans" and parts[4] == "apply":
            pid = qs.get("project", [None])[0]
            p = PROJECTS.get(pid)
            if not p:
                return self._send(404, {"error": "project not found"})
            scan_id = parts[3]
            scanner = _scanner_for(p)
            result = scanner.apply_corrections(scan_id)
            self._logreq(p, "POST", f"/v1/memory/scans/{scan_id}/apply", 200,
                         f"applied {result['retracted']} retractions")
            return self._send(200, result)

        if parts == ["v1", "memory", "gmail-rescan"]:
            pid = qs.get("project", [None])[0]
            p = PROJECTS.get(pid)
            if not p:
                return self._send(404, {"error": "project not found"})
            connector_id = body.get("connector_id")
            window = body.get("window_days")
            if window is not None:
                try:
                    window = int(window)
                except (TypeError, ValueError):
                    return self._err(400, "invalid_window", "window_days must be a number")
                if window not in (7, 30, 90, 365):
                    return self._err(400, "invalid_window", "window_days must be 7, 30, 90 or 365")
            scanner = _scanner_for(p)
            result = scanner.rescan_gmail_sources(connector_id=connector_id,
                                                  window_days=window)
            if body.get("reprocess"):
                # Re-run the CURRENT extraction pipeline (semantic when
                # configured) over historical sources the rescan now considers
                # relevant. Fresh pending jobs; fact-fingerprint dedup keeps
                # already-known beliefs from duplicating; supersession still
                # applies. Numbers are real row counts.
                requeued = 0
                for srid in (result.get("newly_relevant_ids") or [])[:500]:
                    sr = STORE.db.execute(
                        "SELECT connector_id FROM source_records WHERE id=? AND project_id=?",
                        (srid, pid)).fetchone()
                    if not sr:
                        continue
                    pending = STORE.db.execute(
                        "SELECT id FROM ingest_jobs WHERE source_record_id=? "
                        "AND state IN ('pending','retrying','running')", (srid,)).fetchone()
                    if pending:
                        continue
                    STORE.db.execute(
                        "INSERT INTO ingest_jobs(project_id,connector_id,source_record_id,"
                        "state,attempts,created,updated) VALUES(?,?,?,?,0,?,?)",
                        (pid, sr["connector_id"], srid, "pending", time.time(), time.time()))
                    requeued += 1
                STORE.db.commit()
                result["reprocess_queued"] = requeued
                if requeued:
                    result["note"] = ("Queued for re-extraction with the current pipeline; "
                                      "run ingest processing (or wait for the scheduler) "
                                      "to complete it.")
            return self._send(200, result)

        if len(parts) == 5 and parts[:2] == ["v1", "memory"] and parts[2] == "review-queue" and parts[4] == "decide":
            pid = qs.get("project", [None])[0]
            p = PROJECTS.get(pid)
            if not p:
                return self._send(404, {"error": "project not found"})
            decision = body.get("decision")
            if decision not in ("approve", "reject"):
                return self._err(400, "invalid_decision", "decision must be 'approve' or 'reject'")
            reviewer = (auth.get("user", {}) or {}).get("email", "") if isinstance(auth, dict) else ""
            scanner = _scanner_for(p)
            result = scanner.review_decision(parts[3], decision, reviewer)
            return self._send(200, result)

        # project creation (session-scoped to the caller's org)
        if parts == ["v1", "projects"]:
            if "user" not in auth:
                return self._err(403, "permission", "Creating projects requires a user session.")
            org = STORE.org_for_user(auth["user"]["id"])
            pr = STORE.create_project(org["id"], body.get("name", "New Project"), body.get("env", "development"))
            PROJECTS[pr["id"]] = Project(pr["id"], pr["name"], pr["env"], org["id"])
            CONTRADICTIONS[pr["id"]] = []
            _DECLARED_PAIRS[pr["id"]] = set()
            return self._send(201, {"id": pr["id"], "name": pr["name"], "env": pr["env"]})

        p = self._proj(qs)
        if p is None:
            return self._err(404, "not_found", "project not found")
        e = p.engine

        def mint(prefix):
            return f"{prefix}_{uuid.uuid4().hex[:10]}"
        def resolve_time(v):
            return p.tick() if (v is None or v == "now") else int(v)

        if parts == ["v1", "entities"]:
            eid = body.get("id") or mint("ent")
            record(p, "entity", {"id": eid, "type": body["type"], "label": body.get("label")})
            self._logreq(p, "POST", "/v1/entities", 201, f"entity {eid}")
            return self._send(201, shape_entity(p, eid))

        if parts == ["v1", "agents"]:
            aid = body.get("id") or mint("agent")
            record(p, "agent", {"id": aid, "kind": body.get("kind", "system"),
                                "recorded_existence": body.get("recorded_existence", 0),
                                "label": body.get("label")})
            self._logreq(p, "POST", "/v1/agents", 201, f"agent {aid}")
            return self._send(201, shape_agent(p, aid))

        if parts == ["v1", "events"]:
            vid = body.get("id") or mint("evt")
            t = resolve_time(body.get("event_time"))
            record(p, "event", {"id": vid, "ekind": body["kind"], "event_time": t,
                                "event_end": body.get("event_end"), "label": body.get("label")})
            self._logreq(p, "POST", "/v1/events", 201, f"event {vid}")
            return self._send(201, shape_event(p, vid))

        if parts == ["v1", "assertions"]:
            if not p.is_demo:
                allowed, qinfo = ENT.check_entitlement(self._org_of_project(p.id), p.id, "memories")
                if not allowed:
                    return self._err(402, "quota_exceeded",
                                     f"Plan '{qinfo['plan']}' memory quota reached ({qinfo['used']}/{qinfo['quota']}). Upgrade to continue.")
            aid = body.get("id") or mint("a")
            at = resolve_time(body.get("assertion_time"))
            record(p, "assert", {"id": aid, "agent": body["agent"], "subjects": body["subjects"],
                                 "proposition": body["proposition"], "assertion_time": at,
                                 "event_time": body.get("event_time"),
                                 "confidence": body.get("confidence"), "label": body.get("label")})
            because = body.get("because") or []
            if because:
                record(p, "derive", {"id": mint("d"), "consequent": aid,
                                     "antecedents": because, "dkind": "extraction"})
            # Optional explicit scope for cross-agent memory control. Absent => org
            # (backward compatible: a direct assertion is organisational knowledge
            # visible to every agent). A caller may pass scope="agent:<id>" to keep
            # a fact private, "team:<id>" to share with a team, or "user:<id>".
            _scope = body.get("scope")
            if _scope:
                if not _recall.valid_scope(_scope):
                    return self._err(422, "invalid_request",
                                     "scope must be org, team:<id>, agent:<id> or user:<id>")
                SCOPES.set(p.id, aid, _scope, granted_by=body.get("agent"))
            ENT.meter(p.id, "assertions_created")
            self._logreq(p, "POST", "/v1/assertions", 201, f"belief {body['proposition']}")
            return self._send(201, shape_assertion(p, aid))

        if parts == ["v1", "derivations"]:
            did = body.get("id") or mint("d")
            record(p, "derive", {"id": did, "consequent": body["consequent"],
                                 "antecedents": body["antecedents"],
                                 "dkind": body.get("kind", "inference")})
            self._logreq(p, "POST", "/v1/derivations", 201, f"derivation {did}")
            return self._send(201, {"id": did, "object": "derivation"})

        if len(parts) == 4 and parts[:2] == ["v1", "assertions"] and parts[3] == "supersede":
            old = parts[2]
            nw = body["new"]
            nid = nw.get("id") or mint("a")
            at = resolve_time(nw.get("assertion_time"))
            record(p, "supersede", {"id": nid, "agent": nw["agent"], "subjects": nw["subjects"],
                                    "proposition": nw["proposition"], "assertion_time": at,
                                    "confidence": nw.get("confidence"), "olds": [old],
                                    "did": mint("d"), "label": nw.get("label")})
            self._logreq(p, "POST", f"/v1/assertions/{old}/supersede", 201, "revised belief")
            return self._send(201, shape_assertion(p, nid))

        if len(parts) == 4 and parts[:2] == ["v1", "assertions"] and parts[3] == "retract":
            old = parts[2]
            at = resolve_time(body.get("assertion_time"))
            nid = mint("a")
            a = e.store.assertion(old)
            if a is None:
                return self._err(404, "not_found", "assertion not found")
            record(p, "retract", {"id": nid, "agent": body["agent"], "subjects": list(a.subjects),
                                  "assertion_time": at, "old": old, "did": mint("d")})
            self._logreq(p, "POST", f"/v1/assertions/{old}/retract", 201, "retracted belief")
            return self._send(201, {"id": nid, "retracted": old, "object": "assertion"})

        if parts == ["v1", "contradictions"]:
            # Declare two claims mutually exclusive. The general case behind the
            # `not:` convention: any two tokens, named by the caller, for the
            # cases a prefix cannot express (annual vs monthly, open vs closed).
            ta, tb = body.get("token_a"), body.get("token_b")
            if not isinstance(ta, str) or not isinstance(tb, str) or not ta or not tb:
                return self._err(422, "invalid_request",
                                 "token_a and token_b must both be non-empty strings")
            if ta == tb:
                return self._err(422, "invalid_request",
                                 "a claim cannot contradict itself")
            record(p, "declare", {"token_a": ta, "token_b": tb})
            self._logreq(p, "POST", "/v1/contradictions", 201, f"{ta} vs {tb}")
            return self._send(201, {"token_a": ta, "token_b": tb, "object": "contradiction"})

        if parts == ["v1", "coreference"]:
            aid = body.get("id") or mint("cor")
            at = resolve_time(body.get("assertion_time"))
            record(p, "corefer", {"id": aid, "entity_a": body["entity_a"],
                                  "entity_b": body["entity_b"], "agent": body["agent"],
                                  "assertion_time": at})
            self._logreq(p, "POST", "/v1/coreference", 201, "coreference")
            return self._send(201, {"id": aid, "object": "assertion"})

        if parts == ["v1", "coreference", "split"] or (
                len(parts) == 4 and parts[:2] == ["v1", "coreference"] and parts[3] == "split"):
            cor = body.get("coreference_id") or parts[2]
            at = resolve_time(body.get("assertion_time"))
            record(p, "split", {"cor": cor, "agent": body["agent"], "assertion_time": at,
                                "id": mint("a"), "did": mint("d")})
            self._logreq(p, "POST", "/v1/coreference/split", 201, "split")
            return self._send(201, {"split": cor, "object": "assertion"})

        if parts == ["v1", "queries", "proposition-state"]:
            T = self._T(qs, p) if qs.get("as_of") else (p.now() if body.get("as_of") in (None, "now") else int(body["as_of"]))
            state = e.proposition_state(body["subjects"], body["proposition"], T)
            return self._send(200, {"state": state, "as_of": T})

        if parts == ["v1", "queries", "trust-order"]:
            T = p.now() if body.get("as_of") in (None, "now") else int(body["as_of"])
            order = e.trust_order(body["assertions"], T)
            return self._send(200, {"as_of": T, "order": [list(x) for x in order]})

        if parts == ["v1", "declare-contradiction"]:
            record(p, "declare", {"token_a": body["token_a"], "token_b": body["token_b"]})
            return self._send(201, {"declared": [body["token_a"], body["token_b"]]})

        return self._err(404, "not_found", f"no route: POST /{'/'.join(parts)}")


def validate_env():
    """Environment validation: warn (not fail) about optional integrations so the
    operator knows exactly which production paths are active vs. falling back."""
    status = {
        "google_oauth": providers.google_configured(),
        "llm_provider": providers.llm_configured(),
        "stripe_billing": providers.stripe_configured(),
    }
    for name, on in status.items():
        print(f"  {name}: {'CONFIGURED' if on else 'not configured (mock/fallback)'}")
    if status["llm_provider"]:
        base = os.environ.get("OMEM_LLM_BASE_URL", "https://api.openai.com/v1")
        print(f"    model: {os.environ.get('OMEM_LLM_MODEL', 'gpt-4o-mini')}")
        d = providers.dns_check(base)
        if d.get("ok"):
            print(f"    endpoint: {base} (resolves to {', '.join(d['addresses'][:2])})")
        else:
            print(f"    endpoint: {base}")
            print(f"    WARNING: {d.get('error')}")
            print("    Extraction will fail until this resolves; jobs will dead-letter.")
    return status


def main(port=8787):
    import signal
    host = os.environ.get("OMEM_HOST", "127.0.0.1")
    print(f"OMEM Cloud API starting on http://{host}:{port}")
    if _BACKFILLED:
        print(f"  granted owner role to {len(_BACKFILLED)} pre-existing org owner(s)")
    if _ENV_FILES:
        for _f in _ENV_FILES:
            print(f"  env file: {_f}")
    else:
        print("  env file: none found (looked for server/.env.local, .env, repo .env*)")
    print("  engine: authoritative reference, CTS 29/29")
    validate_env()
    SCHEDULER.start()
    Handler.timeout = 60          # a hung/half-open socket frees its thread
    srv = ThreadingHTTPServer((host, port), Handler)
    srv.daemon_threads = True     # in-flight handlers never block shutdown

    def shutdown(*_):
        print("\n  graceful shutdown: stopping scheduler + server")
        SCHEDULER.stop()
        srv.shutdown()
    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        shutdown()


if __name__ == "__main__":
    import sys as _sys
    main(int(_sys.argv[1]) if len(_sys.argv) > 1 else 8787)
