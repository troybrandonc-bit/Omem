"""Automatic ingestion layer for OMEM.

Design principle (non-negotiable): this layer produces valid OMEM primitives and
hands them to the existing recorded write path. It never decides truth, state,
contradiction, or coreference itself. The frozen engine does. Ingestion is a
*producer* of assertions/entities/events/derivations; the engine remains the
sole authority on what they mean.

Flow:
  connector.poll() -> raw items
    -> source_record (persisted, immutable, the provenance anchor)
      -> extract() -> candidate facts
        -> resolve entities (create or reuse)
          -> emit event (the source record's real-world moment)
            -> record assertion grounded in that event (engine call)
              -> dedup (skip if identical open belief already exists)

Contradiction/revision are NOT computed here. Once an assertion lands, the engine
already flips proposition_state to CONTRADICTED when a competing token is open.
We surface that; we do not compute it.
"""
from __future__ import annotations

from secrets_provider import (  # noqa: E402
    decrypt_content, encrypt_content,
)
import hashlib
import json
import time
from typing import Callable

INGEST_SCHEMA = """
CREATE TABLE IF NOT EXISTS connectors(
  id TEXT PRIMARY KEY, project_id TEXT NOT NULL, kind TEXT NOT NULL,
  name TEXT NOT NULL, config TEXT NOT NULL, agent_id TEXT NOT NULL,
  authority REAL NOT NULL DEFAULT 0.5, status TEXT NOT NULL DEFAULT 'active',
  cursor TEXT, created REAL NOT NULL, last_run REAL);
CREATE TABLE IF NOT EXISTS source_records(
  id TEXT PRIMARY KEY, project_id TEXT NOT NULL, connector_id TEXT NOT NULL,
  external_id TEXT NOT NULL, payload TEXT NOT NULL, content_hash TEXT NOT NULL,
  event_id TEXT, received REAL NOT NULL,
  UNIQUE(connector_id, external_id));
CREATE TABLE IF NOT EXISTS ingest_jobs(
  id INTEGER PRIMARY KEY AUTOINCREMENT, project_id TEXT NOT NULL,
  connector_id TEXT NOT NULL, source_record_id TEXT NOT NULL,
  state TEXT NOT NULL DEFAULT 'pending', attempts INTEGER NOT NULL DEFAULT 0,
  last_error TEXT, produced TEXT, correlation_id TEXT, next_attempt REAL,
  heartbeat REAL, created REAL NOT NULL, updated REAL NOT NULL);
CREATE INDEX IF NOT EXISTS jobs_state ON ingest_jobs(project_id, state);
CREATE TABLE IF NOT EXISTS assertion_evidence(
  assertion_id TEXT PRIMARY KEY, project_id TEXT NOT NULL,
  source_record_id TEXT, evidence TEXT, confidence REAL,
  extractor TEXT, created REAL NOT NULL);
CREATE TABLE IF NOT EXISTS fact_fingerprints(
  project_id TEXT NOT NULL, fingerprint TEXT NOT NULL, assertion_id TEXT NOT NULL,
  PRIMARY KEY(project_id, fingerprint));
"""

MAX_ATTEMPTS = 3
# Full job lifecycle. pending -> running -> completed | failed(->retrying->pending) | dead_lettered; cancelled from any non-terminal.
JOB_STATES = ["pending", "running", "completed", "failed", "retrying", "dead_lettered", "cancelled"]
BACKOFF_BASE = 2.0  # seconds; exponential


def _addr_of_sender(payload: dict) -> str | None:
    """Bare sender address for the indexed from_addr column."""
    from email.utils import parseaddr
    e = payload.get("from_email") or parseaddr(payload.get("from") or "")[1]
    return e.lower() if e else None


def _now() -> float:
    return time.time()


def _hash(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()[:16]


# ── connector abstraction ────────────────────────────────────────────────
class Extractor:
    """Candidate-fact generator. NOT an authority. Turns a raw payload into
    candidate facts of shape:
      {subject:{id,type,label}, proposition:str, confidence:float,
       event_kind:str, event_time:'now'|int, label:str, evidence:str}
    Subclasses: RuleExtractor (deterministic) and LLMExtractor (model-backed).
    Neither touches the engine; both only propose shapes."""
    def extract(self, payload: dict) -> list[dict]:
        raise NotImplementedError


class Connector:
    """A source. poll() yields (external_id, payload dict). Stateless re: OMEM.
    Real connectors (Gmail, Slack, Salesforce) subclass this; the pipeline does
    not care which, because everything downstream speaks source_records. The
    connector owns an Extractor; the pipeline calls connector.extract()."""
    kind = "abstract"
    extractor: Extractor | None = None

    def poll(self, cursor: str | None) -> tuple[list[tuple[str, dict]], str | None]:
        raise NotImplementedError

    def extract(self, payload: dict) -> list[dict]:
        if self.extractor is None:
            raise NotImplementedError("connector has no extractor")
        return self.extractor.extract(payload)


SUPPORT_RULES = [
    ("prefer email", "prefers_email_over_phone", 0.7),
    ("prefer phone", "not:prefers_email_over_phone", 0.7),
    ("cancel", "intends_to_cancel", 0.8),
    ("upgrade", "intends_to_upgrade", 0.75),
    ("annual billing", "prefers_annual_billing", 0.65),
    ("enterprise", "is_enterprise_customer", 0.6),
]

# Phrases where an action word is boilerplate, not a statement by the writer:
# "you can cancel at any time", "cancel anytime", "upgrade now", CTA questions.
_BOILERPLATE_GUARDS = [
    r"\b(?:you )?can (?:cancel|upgrade|downgrade|unsubscribe)\b",
    r"\b(?:cancel|upgrade)\s+(?:at any time|anytime|now|today)\b",
    r"\bwant to (?:cancel|upgrade)\b.{0,40}\b(?:click|tap|visit|here)\b",
    r"\bto (?:cancel|unsubscribe)[, ].{0,30}\b(?:click|visit|go to)\b",
]


class RuleExtractor(Extractor):
    """Deterministic keyword extractor. Fully testable, no model dependency."""
    def __init__(self, rules=SUPPORT_RULES):
        self.rules = rules

    @staticmethod
    def identity_of(payload: dict) -> str | None:
        """Derive a stable subject identity from a source payload.
        Order: explicit customer id -> sender email local-part -> author.
        Returns None when no real identity exists (we never invent one)."""
        cust = (payload.get("customer") or "").strip()
        if cust:
            return cust
        email_addr = (payload.get("from_email") or "").strip()
        if not email_addr:
            import re as _re
            m = _re.search(r"([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+)", payload.get("from") or "")
            email_addr = m.group(1) if m else ""
        if email_addr and "@" in email_addr:
            return email_addr.split("@", 1)[0].lower()
        author = (payload.get("author") or "").strip()
        return author.lower() or None

    def extract(self, payload: dict) -> list[dict]:
        import re as _re
        text = (payload.get("body", "") + " " + payload.get("subject", "")).lower()
        cust = self.identity_of(payload)
        if not cust:
            return []
        # boilerplate contexts ("you can cancel at any time") never count
        guarded = text
        for g in _BOILERPLATE_GUARDS:
            guarded = _re.sub(g, " ", guarded)
        facts = []
        for needle, prop, conf in self.rules:
            # WORD-BOUNDARY match: "cancel" must be the word, not a fragment of
            # "cancelar"/"cancellation-policy" boilerplate
            if _re.search(r"\b" + _re.escape(needle) + r"\b", guarded):
                facts.append({
                    "subject": {"id": f"customer:{cust}", "type": "person", "label": f"Customer {cust}"},
                    "proposition": prop, "confidence": conf,
                    "event_kind": "support_ticket",
                    "event_time": payload.get("at", "now"),
                    "label": (payload.get("subject") or "message") + " \u2192 " + prop,
                    "evidence": f"matched '{needle}' in message text",
                })
        return facts


class SupportInboxConnector(Connector):
    """Email/ticket inbox connector. Holds a RuleExtractor by default."""
    kind = "support_inbox"

    def __init__(self, items: list[dict] | None = None, extractor: Extractor | None = None):
        self._items = items or []
        self.extractor = extractor or RuleExtractor()

    def poll(self, cursor):
        start = int(cursor) if cursor else 0
        batch = [(str(i), it) for i, it in enumerate(self._items) if i >= start]
        return batch, str(len(self._items))


class PushConnector(Connector):
    """DB-backed push connector: powers webhooks and document uploads. Items are
    appended by the API (push_item) and drained by poll() via cursor, the same
    pipeline path as every other source. No external dependency."""
    kind = "push"

    def __init__(self, db, connector_id, extractor: Extractor | None = None):
        self.db = db
        self.connector_id = connector_id
        self.extractor = extractor or RuleExtractor()

    def poll(self, cursor):
        start = int(cursor) if cursor else 0
        rows = self.db.execute(
            "SELECT seq, external_id, payload FROM push_items WHERE connector_id=? AND seq>? ORDER BY seq",
            (self.connector_id, start)).fetchall()
        items = [(r["external_id"], json.loads(r["payload"])) for r in rows]
        last = rows[-1]["seq"] if rows else start
        return items, str(last)


FILTER_SCHEMA = """
CREATE TABLE IF NOT EXISTS filtered_items(
  id INTEGER PRIMARY KEY AUTOINCREMENT, connector_id TEXT NOT NULL,
  project_id TEXT NOT NULL, external_id TEXT, subject TEXT,
  reason TEXT NOT NULL, ts REAL NOT NULL);
CREATE INDEX IF NOT EXISTS filtered_proj ON filtered_items(project_id, ts);
"""

PUSH_SCHEMA = """
CREATE TABLE IF NOT EXISTS push_items(
  seq INTEGER PRIMARY KEY AUTOINCREMENT, connector_id TEXT NOT NULL,
  external_id TEXT NOT NULL, payload TEXT NOT NULL, received REAL NOT NULL);
CREATE INDEX IF NOT EXISTS push_conn ON push_items(connector_id, seq);
"""


CONNECTOR_TYPES: dict[str, type[Connector]] = {
    "support_inbox": SupportInboxConnector,
}


# ── the pipeline ──────────────────────────────────────────────────────────
class Ingestor:
    """Owns the async-style job lifecycle. `record_fn` is the app's recorded
    write path (record(project, kind, args)); `mint_fn` mints ids. The Ingestor
    NEVER imports the engine directly. It only produces primitives through
    record_fn, which keeps the engine authoritative."""

    def __init__(self, store, record_fn: Callable, mint_fn: Callable, project_getter: Callable):
        self.store = store
        self.db = store.db
        self.record = record_fn
        self.mint = mint_fn
        self.project = project_getter
        self.connector_factory = None  # set by app: (conn_row) -> Connector
        self.resolver = None           # set by app: EntityResolver
        self.extraction_logger = None  # set by app: fn(project_id, srid, extractor, facts, ok, error)
        self.classifier = None         # set by app: fn(project_id, connector, payload, srid) -> result
        self.classification_store = None
        self.quality_gate = None       # set by app: fn(project_id, conn, payload, facts, verdict, srid) -> kept facts
        self.semantic_active = None    # set by app: fn(project_id) -> bool; when the
                                       # semantic LLM extractor is live, low-confidence
                                       # noise verdicts ESCALATE to it instead of dying
        self.db.executescript(INGEST_SCHEMA)
        self.db.executescript(PUSH_SCHEMA)
        self.db.executescript(FILTER_SCHEMA)
        self._migrate_source_columns()

    def _migrate_source_columns(self):
        """Indexed thread_id/from_addr on source_records so thread context and
        relationship history are SQL lookups instead of scanning and
        JSON-parsing hundreds of full email payloads per processed message
        (which serialised the whole API behind the DB lock on real mailboxes).
        Idempotent: guarded ALTERs, one-time backfill of NULL rows, indexes."""
        for col in ("thread_id TEXT", "from_addr TEXT"):
            try:
                self.db.execute(f"ALTER TABLE source_records ADD COLUMN {col}")
            except Exception:
                pass
        pending = self.db.execute(
            "SELECT id, payload FROM source_records WHERE thread_id IS NULL AND from_addr IS NULL"
        ).fetchall()
        for r in pending:
            try:
                pl = json.loads(decrypt_content(r["payload"]))
            except Exception:
                continue
            self.db.execute(
                "UPDATE source_records SET thread_id=?, from_addr=? WHERE id=?",
                (pl.get("thread_id"),
                 _addr_of_sender(pl) or "",  # '' sentinel: parsed, no sender,
                 r["id"]))                    # never re-scanned on next boot
        self.db.execute(
            "CREATE INDEX IF NOT EXISTS sr_thread ON source_records(project_id, thread_id)")
        self.db.execute(
            "CREATE INDEX IF NOT EXISTS sr_from ON source_records(project_id, from_addr)")
        self.db.commit()
        self.db.commit()

    # -- connector management --
    def add_connector(self, project_id, kind, name, config, agent_id, authority=0.5):
        cid = "conn_" + hashlib.sha1(f"{project_id}{name}{_now()}".encode()).hexdigest()[:8]
        self.db.execute(
            "INSERT INTO connectors(id,project_id,kind,name,config,agent_id,authority,created) VALUES(?,?,?,?,?,?,?,?)",
            (cid, project_id, kind, name, json.dumps(config), agent_id, authority, _now()))
        self.db.commit()
        # the connector is an OMEM agent - its assertions are attributed to it
        p = self.project(project_id)
        if p and agent_id not in p.labels:
            self.record(p, "agent", {"id": agent_id, "kind": "system", "label": name})
        return self.connector(cid)

    def connector(self, cid):
        r = self.db.execute("SELECT * FROM connectors WHERE id=?", (cid,)).fetchone()
        return dict(r) if r else None

    def connectors_for(self, project_id):
        rows = self.db.execute("SELECT * FROM connectors WHERE project_id=? ORDER BY created", (project_id,))
        return [dict(r) for r in rows]

    def _instance(self, conn) -> Connector:
        # app-provided factory handles gmail/LLM wiring (needs creds + clients)
        if self.connector_factory is not None:
            inst = self.connector_factory(conn)
            if inst is not None:
                return inst
        cls = CONNECTOR_TYPES[conn["kind"]]
        cfg = json.loads(conn["config"])
        return cls(cfg.get("items")) if conn["kind"] == "support_inbox" else cls()

    # -- ingestion: poll -> source_records -> jobs --
    def poll_connector(self, cid) -> int:
        conn = self.connector(cid)
        if not conn or conn["status"] != "active":
            return 0
        inst = self._instance(conn)
        items, cursor = inst.poll(conn["cursor"])
        # record what the connector excluded, so the filter is auditable
        for sk in getattr(inst, "skipped", []) or []:
            try:
                self.db.execute(
                    "INSERT INTO filtered_items(connector_id,project_id,external_id,subject,reason,ts) "
                    "VALUES(?,?,?,?,?,?)",
                    (cid, conn["project_id"], sk.get("external_id"),
                     (sk.get("subject") or "")[:300], sk.get("reason", ""), time.time()))
            except Exception:
                pass
        self.db.commit()
        queued = 0
        for external_id, payload in items:
            body = json.dumps(payload, sort_keys=True)
            # content_hash is computed over the PLAINTEXT below, so dedup keeps
            # working: encrypting is randomised (fresh salt+nonce per row), so a
            # hash of ciphertext would differ every time and re-ingest everything.
            stored_body = encrypt_content(body)
            chash = _hash(body)
            srid = "src_" + hashlib.sha1(f"{cid}{external_id}".encode()).hexdigest()[:10]
            exists = self.db.execute(
                "SELECT 1 FROM source_records WHERE connector_id=? AND external_id=?",
                (cid, external_id)).fetchone()
            if exists:
                continue  # source-level dedup: never re-ingest the same item
            self.db.execute(
                "INSERT INTO source_records(id,project_id,connector_id,external_id,payload,content_hash,received,thread_id,from_addr) VALUES(?,?,?,?,?,?,?,?,?)",
                (srid, conn["project_id"], cid, external_id, stored_body, chash, _now(),
                 payload.get("thread_id"),
                 _addr_of_sender(payload)))
            self.db.execute(
                "INSERT INTO ingest_jobs(project_id,connector_id,source_record_id,created,updated) VALUES(?,?,?,?,?)",
                (conn["project_id"], cid, srid, _now(), _now()))
            queued += 1
        self.db.execute("UPDATE connectors SET cursor=?, last_run=? WHERE id=?", (cursor, _now(), cid))
        self.db.commit()
        return queued

    # -- async worker: drain pending jobs, produce OMEM primitives --
    def process_pending(self, project_id, limit=50, time_budget: float = 15.0) -> dict:
        """Drain up to `limit` jobs but never run longer than `time_budget`
        seconds: a synchronous HTTP request must respond before proxies and
        browsers give up, even on a large real-mailbox backlog. Whatever is
        left stays pending; the background scheduler (or another call) drains
        it. Returns `remaining` so callers can show honest progress."""
        now = time.time()
        deadline = now + max(1.0, float(time_budget))
        rows = self.db.execute(
            "SELECT * FROM ingest_jobs WHERE project_id=? AND state IN ('pending','retrying') "
            "AND (next_attempt IS NULL OR next_attempt<=?) ORDER BY id LIMIT ?",
            (project_id, now, limit)).fetchall()
        done = failed = produced = 0
        for job in rows:
            if time.time() >= deadline:
                break
            r = self._process_one(dict(job))
            if r["ok"]:
                done += 1
                produced += r["produced"]
            else:
                failed += 1
        remaining = self.db.execute(
            "SELECT COUNT(*) n FROM ingest_jobs WHERE project_id=? AND state IN ('pending','retrying')",
            (project_id,)).fetchone()["n"]
        return {"processed": done, "failed": failed, "assertions": produced,
                "remaining": remaining}

    def _process_one(self, job) -> dict:
        conn = self.connector(job["connector_id"])
        sr = self.db.execute("SELECT * FROM source_records WHERE id=?", (job["source_record_id"],)).fetchone()
        p = self.project(job["project_id"])
        # claim the job: pending/retrying -> running (with heartbeat for crash recovery)
        self.db.execute("UPDATE ingest_jobs SET state='running', heartbeat=?, updated=? WHERE id=?",
                        (time.time(), time.time(), job["id"]))
        self.db.commit()
        try:
            payload = json.loads(decrypt_content(sr["payload"]))
            inst = self._instance(conn)

            # ── STAGE 1: business relevance ────────────────────────────────
            # A message must earn its way into memory. Source records are kept
            # regardless, so an exclusion can always be explained.
            min_fact_confidence = 0.0
            verdict = None
            if self.classifier is not None and conn["kind"] == "gmail":
                verdict = self.classifier(job["project_id"], conn, payload, sr["id"])
                if verdict is not None:
                    cls = verdict["classification"]
                    if cls in ("NON_BUSINESS", "AUTOMATED_NOISE"):
                        sem = False
                        try:
                            sem = bool(self.semantic_active
                                       and conn["kind"] == "gmail"
                                       and self.semantic_active(job["project_id"]))
                        except Exception:
                            sem = False
                        try:
                            vconf = float(verdict.get("confidence") or 0)
                        except (TypeError, ValueError):
                            vconf = 0.0
                        # The whole point of the LLM is the ambiguous middle:
                        # a blunt classifier verdict may only kill mail when it
                        # is CONFIDENT noise; otherwise the model reads it.
                        if not sem or vconf >= 0.75:
                            self.db.execute(
                                "UPDATE ingest_jobs SET state='completed', attempts=attempts+1, "
                                "produced=?, last_error=NULL, heartbeat=NULL, updated=? WHERE id=?",
                                (json.dumps([]), _now(), job["id"]))
                            self.db.commit()
                            return {"ok": True, "produced": 0, "classified_out": True}
                    if cls == "POSSIBLY_BUSINESS":
                        # Medium confidence proceeds, but only strongly-evidenced
                        # facts may become memory (per the relevance policy).
                        min_fact_confidence = 0.8

            # ── STAGE 2: extraction ────────────────────────────────────────
            try:
                facts = inst.extract(payload)
            except Exception as ex:
                # A provider outage must fail the JOB (so it retries/dead-letters
                # with a visible error), not silently produce zero facts.
                if self.extraction_logger:
                    try:
                        self.extraction_logger(job["project_id"], sr["id"],
                                               type(getattr(inst, "extractor", None) or inst).__name__,
                                               0, False, f"{type(ex).__name__}: {ex}")
                    except Exception:
                        pass
                raise
            if min_fact_confidence and not (self.quality_gate is not None
                                            and conn["kind"] == "gmail"):
                # blunt pre-filter only when no quality gate exists; the gate
                # judges act/category/direction and is strictly smarter than a
                # confidence threshold (a customer "considering cancelling" is
                # churn-risk memory even at moderate confidence)
                facts = [f for f in facts
                         if float(f.get("confidence") or 0) >= min_fact_confidence]
            # ── STAGE 2.5: memory quality gate ─────────────────────────────
            # A fact must EARN storage. The gate re-analyses the mail (category,
            # marketing density, SaaS self-notification, direction) and grades
            # each candidate; DO_NOT_STORE/LOW never reach the engine. Every
            # decision is persisted so "why was this (not) stored" is answerable.
            if self.quality_gate is not None and conn["kind"] == "gmail":
                facts = self.quality_gate(job["project_id"], conn, payload,
                                          facts, verdict, sr["id"]) or []
            if self.extraction_logger:
                try:
                    self.extraction_logger(job["project_id"], sr["id"],
                                           type(getattr(inst, "extractor", None) or inst).__name__,
                                           len(facts), True, None)
                except Exception:
                    pass
            produced_ids = []

            # one event per source record: the real-world moment, grounding anchor
            event_id = sr["event_id"]
            _event_T = None
            if facts and not event_id:
                event_id = self.mint("evt")
                ek = facts[0].get("event_kind", "ingested")
                _event_T = self._time(p, facts[0].get("event_time", "now"))
                self.record(p, "event", {"id": event_id, "ekind": ek,
                                         "event_time": _event_T,
                                         "label": payload.get("subject", conn["name"])})
                self.db.execute("UPDATE source_records SET event_id=? WHERE id=?", (event_id, sr["id"]))

            for f in facts:
                subj = f["subject"]
                # entity resolution (auditable): produce a valid OMEM entity id
                if self.resolver is not None and subj.get("id", "").startswith("customer:"):
                    res = self.resolver.resolve(p.id, subj["id"], p.labels, sr["id"])
                    subj = {**subj, "id": res["entity_id"]}
                if subj["id"] not in p.labels:
                    self.record(p, "entity", {"id": subj["id"], "type": subj["type"], "label": subj.get("label")})

                # fact-level dedup: identical (subject, CANONICAL proposition,
                # agent) open belief -> skip. Canonicalisation collapses synonym
                # spellings (wants_/would_like_/prefers_annual_billing) so the
                # same idea never becomes several memories.
                try:
                    from extraction import canonical_proposition as _canon
                except Exception:
                    def _canon(x):
                        return x
                fp = _hash(f"{subj['id']}|{_canon(f['proposition'])}|{conn['agent_id']}")
                dup = self.db.execute(
                    "SELECT assertion_id FROM fact_fingerprints WHERE project_id=? AND fingerprint=?",
                    (p.id, fp)).fetchone()

                aid = self.mint("a")
                # ── stale-intent supersession (above the engine, via ITS op) ──
                # A stronger fact ("has_renewed") replaces open weaker/opposite
                # beliefs about the same subject ("considering_cancel") through
                # the engine's supersede: old belief closes, history preserved.
                # Computed BEFORE the dedup skip: "ignore my previous email -
                # we've decided to renew" may re-state an already-known decision
                # (a duplicate assertion) while STILL needing to close the
                # cancellation intent it reverses.
                olds: list[str] = []
                try:
                    from extraction import SUPERSEDES as _sup
                    weaker = set(_sup.get(_canon(f["proposition"]), ()))
                    rel = f.get("existing_memory_relationship") or {}
                    if isinstance(rel, dict) and rel.get("relation") == "supersedes" \
                            and rel.get("target_proposition"):
                        # The semantic model recognised a reversal/change of an
                        # existing belief ("ignore my previous email - we've
                        # decided to renew"). It only NAMES the target; the
                        # engine's supersede op does the actual revision, and
                        # only for a belief that genuinely exists on this
                        # subject. "contradicts"/"confirms" deliberately do
                        # nothing here.
                        weaker.add(_canon(rel["target_proposition"]))
                    if weaker:
                        Tnow = p.now()
                        for a_open in p.engine.store.assertions():
                            if (a_open.proposition in weaker
                                    and subj["id"] in a_open.subjects
                                    and p.engine.ledger.is_open_at(a_open, Tnow)):
                                olds.append(a_open.id)
                except Exception:
                    olds = []

                if dup and not olds:
                    # duplicate of an existing belief: record it as
                    # REINFORCEMENT (one more independent observation) rather
                    # than dropping the signal on the floor
                    if getattr(self, "on_reinforce", None):
                        try:
                            self.on_reinforce(p.id, dup["assertion_id"],
                                              conn["agent_id"], sr["id"])
                        except Exception:
                            pass
                    continue
                _rt = f.get("relation_target")
                _subjects = [subj["id"]]
                if isinstance(_rt, dict) and _rt.get("id"):
                    if _rt["id"] not in p.labels:
                        self.record(p, "entity", {"id": _rt["id"],
                                                  "type": _rt.get("type", "entity"),
                                                  "label": _rt.get("label")})
                    _subjects = [subj["id"], _rt["id"]]
                if olds:
                    self.record(p, "supersede", {
                        "id": aid, "agent": conn["agent_id"], "subjects": _subjects,
                        "proposition": f["proposition"],
                        "assertion_time": p.tick(),
                        "event_time": _event_T,
                        "confidence": f.get("confidence"), "label": f.get("label"),
                        "olds": olds, "did": self.mint("d")})
                else:
                    self.record(p, "assert", {
                        "id": aid, "agent": conn["agent_id"], "subjects": _subjects,
                        "proposition": f["proposition"],
                        "assertion_time": p.tick(),
                        "event_time": _event_T,
                        "confidence": f.get("confidence"), "label": f.get("label")})
                if f.get("relation") and isinstance(_rt, dict) and _rt.get("id") \
                        and getattr(self, "on_edge", None):
                    try:
                        self.on_edge(p.id, aid, subj["id"], f["relation"], _rt["id"])
                    except Exception:
                        pass
                # provenance: derive the assertion from the source event
                # dkind comes from the fact. Almost everything here is read
                # out of the message ("extraction"); an employment relation is
                # concluded from the sender's address ("inference"), and /why
                # should not present the two as the same kind of knowing.
                self.record(p, "derive", {"id": self.mint("d"), "consequent": aid,
                                          "antecedents": [event_id],
                                          "dkind": f.get("dkind") or "extraction"})
                self.db.execute(
                    "INSERT OR REPLACE INTO fact_fingerprints VALUES(?,?,?)", (p.id, fp, aid))
                # persist the extractor's evidence so the "why" surface can show
                # the ACTUAL text that produced this memory (never regenerated)
                self.db.execute(
                    "INSERT OR REPLACE INTO assertion_evidence VALUES(?,?,?,?,?,?,?)",
                    (aid, p.id, sr["id"], encrypt_content(f.get("evidence")), f.get("confidence"),
                     type(getattr(inst, "extractor", None) or inst).__name__, _now()))
                produced_ids.append(aid)

            self.db.execute(
                "UPDATE ingest_jobs SET state='completed', attempts=attempts+1, produced=?, "
                "last_error=NULL, heartbeat=NULL, updated=? WHERE id=?",
                (json.dumps(produced_ids), _now(), job["id"]))
            self.db.commit()
            if self.classification_store is not None:
                try:
                    self.classification_store.set_facts(sr["id"], len(produced_ids))
                except Exception:
                    pass
            return {"ok": True, "produced": len(produced_ids)}

        except Exception as e:  # engine rejection (R_DANGLING etc.) or extractor bug
            attempts = job["attempts"] + 1
            if attempts >= MAX_ATTEMPTS:
                state, next_at = "dead_lettered", None
            else:
                state, next_at = "retrying", time.time() + BACKOFF_BASE ** attempts  # exponential backoff
            self.db.execute(
                "UPDATE ingest_jobs SET state=?, attempts=?, last_error=?, next_attempt=?, heartbeat=NULL, updated=? WHERE id=?",
                (state, attempts, f"{type(e).__name__}: {e}", next_at, _now(), job["id"]))
            self.db.commit()
            return {"ok": False, "produced": 0}

    def _time(self, p, v):
        if v == "now" or v is None:
            return p.tick()
        return int(v)

    # -- observability --
    def stats(self, project_id) -> dict:
        def n(state):
            return self.db.execute(
                "SELECT COUNT(*) c FROM ingest_jobs WHERE project_id=? AND state=?",
                (project_id, state)).fetchone()["c"]
        srcs = self.db.execute(
            "SELECT COUNT(*) c FROM source_records WHERE project_id=?", (project_id,)).fetchone()["c"]
        return {"sources": srcs, "pending": n("pending"), "running": n("running"),
                "completed": n("completed"), "retrying": n("retrying"),
                "dead": n("dead_lettered"), "cancelled": n("cancelled"),
                "connectors": len(self.connectors_for(project_id))}

    def dead_letters(self, project_id):
        rows = self.db.execute(
            "SELECT j.*, s.external_id FROM ingest_jobs j JOIN source_records s ON s.id=j.source_record_id "
            "WHERE j.project_id=? AND j.state='dead_lettered' ORDER BY j.id", (project_id,))
        return [dict(r) for r in rows]

    def filtered_for(self, project_id, limit=100):
        rows = self.db.execute(
            "SELECT external_id, subject, reason, ts FROM filtered_items "
            "WHERE project_id=? ORDER BY id DESC LIMIT ?", (project_id, limit))
        return [dict(r) for r in rows]

    def push_item(self, connector_id, external_id, payload: dict) -> int:
        """Append an item for a push connector (webhook delivery / doc upload)."""
        cur = self.db.execute(
            "INSERT INTO push_items(connector_id,external_id,payload,received) VALUES(?,?,?,?)",
            (connector_id, external_id, json.dumps(payload), time.time()))
        self.db.commit()
        return cur.lastrowid

    def recover_stale(self, older_than=60.0):
        """Crash recovery: jobs stuck in 'running' with a stale heartbeat (the
        worker died mid-flight) are returned to 'pending' for safe reprocessing.
        Idempotent because source-level dedup prevents double-ingest."""
        cutoff = time.time() - older_than
        cur = self.db.execute(
            "UPDATE ingest_jobs SET state='pending', heartbeat=NULL, updated=? "
            "WHERE state='running' AND heartbeat IS NOT NULL AND heartbeat<?",
            (time.time(), cutoff))
        self.db.commit()
        return cur.rowcount

    def delete_connector(self, connector_id, project_id) -> dict:
        """Remove a source and everything derived from its RAW MATERIAL: its jobs,
        source records, push items and filter log.

        The engine's memories are NOT deleted. Assertions are immutable history
        and other sources may corroborate them; removing a connector is a
        storage/lifecycle action, never a memory-semantic one. Provenance that
        pointed at deleted source material will report the source as removed."""
        counts = {}
        for table, col in (("ingest_jobs", "connector_id"),
                           ("source_records", "connector_id"),
                           ("push_items", "connector_id"),
                           ("filtered_items", "connector_id")):
            try:
                cur = self.db.execute(
                    f"DELETE FROM {table} WHERE {col}=?", (connector_id,))
                counts[table] = cur.rowcount
            except Exception:
                counts[table] = 0
        cur = self.db.execute(
            "DELETE FROM connectors WHERE id=? AND project_id=?",
            (connector_id, project_id))
        counts["connectors"] = cur.rowcount
        self.db.commit()
        return counts

    def delete_connectors(self, project_id, kind=None, only_inactive=False) -> dict:
        """Bulk removal, for clearing out duplicate or abandoned sources."""
        q = "SELECT id FROM connectors WHERE project_id=?"
        args = [project_id]
        if kind:
            q += " AND kind=?"
            args.append(kind)
        if only_inactive:
            q += " AND status <> 'active'"
        ids = [r["id"] for r in self.db.execute(q, args).fetchall()]
        total = {"connectors": 0}
        for cid in ids:
            counts = self.delete_connector(cid, project_id)
            for k, v in counts.items():
                total[k] = total.get(k, 0) + v
        return {**total, "ids": ids}

    def clear_connector_errors(self, connector_id) -> int:
        """Drop stale failures for a connector (e.g. after reconnecting). Only
        terminal failures are cleared; live jobs are untouched."""
        cur = self.db.execute(
            "UPDATE ingest_jobs SET last_error=NULL WHERE connector_id=? "
            "AND state <> 'running'", (connector_id,))
        self.db.commit()
        return cur.rowcount

    def retry_dead_letters(self, project_id) -> int:
        """Requeue dead-lettered jobs after an outage is fixed. Attempts reset so
        the normal retry budget applies again; source-level dedup makes this
        safe to run repeatedly."""
        cur = self.db.execute(
            "UPDATE ingest_jobs SET state='pending', attempts=0, next_attempt=NULL, "
            "last_error=NULL, updated=? WHERE project_id=? AND state='dead_lettered'",
            (time.time(), project_id))
        self.db.commit()
        return cur.rowcount

    def cancel_job(self, job_id):
        cur = self.db.execute(
            "UPDATE ingest_jobs SET state='cancelled', updated=? "
            "WHERE id=? AND state IN ('pending','retrying','failed')",
            (time.time(), job_id))
        self.db.commit()
        return cur.rowcount > 0

    def connector_detail(self, project_id, connector_id) -> dict:
        """Per-connector real counts: items ingested, job states, memories
        generated (assertions whose source record came from this connector),
        last successful sync, and last error. All from persisted state."""
        def one(sql, *a):
            r = self.db.execute(sql, a).fetchone()
            return (r["c"] if r and "c" in r.keys() else (r[0] if r else 0)) or 0
        states = {}
        for st in ["pending", "running", "completed", "retrying", "dead_lettered", "cancelled"]:
            states[st] = one("SELECT COUNT(*) c FROM ingest_jobs WHERE connector_id=? AND state=?",
                             connector_id, st)
        # memories generated: distinct assertion ids produced by this connector's jobs
        produced = self.db.execute(
            "SELECT produced FROM ingest_jobs WHERE connector_id=? AND state='completed' "
            "AND produced IS NOT NULL", (connector_id,)).fetchall()
        mem = 0
        for r in produced:
            try:
                mem += len(json.loads(r["produced"]) or [])
            except Exception:
                pass
        last_err = self.db.execute(
            # Only surface errors from jobs that are ACTUALLY failing. A job that
            # errored once and then succeeded must not haunt the card forever.
            "SELECT last_error, updated FROM ingest_jobs WHERE connector_id=? "
            "AND last_error IS NOT NULL AND state IN ('retrying','dead_lettered','failed') "
            "ORDER BY updated DESC LIMIT 1", (connector_id,)).fetchone()
        conn = self.connector(connector_id)
        return {
            "connector_id": connector_id,
            "items_ingested": one("SELECT COUNT(*) c FROM source_records WHERE connector_id=?", connector_id),
            "memories_generated": mem,
            "jobs": states,
            "last_sync": conn["last_run"] if conn else None,
            "cursor": conn["cursor"] if conn else None,
            "status": conn["status"] if conn else "unknown",
            "last_error": (last_err["last_error"] if last_err else None),
        }

    def jobs_for(self, project_id, limit=100):
        rows = self.db.execute(
            "SELECT id, connector_id, state, attempts, last_error, next_attempt, created, updated "
            "FROM ingest_jobs WHERE project_id=? ORDER BY id DESC LIMIT ?", (project_id, limit))
        return [dict(r) for r in rows]

    def evidence_for(self, project_id, assertion_id):
        r = self.db.execute(
            "SELECT * FROM assertion_evidence WHERE project_id=? AND assertion_id=?",
            (project_id, assertion_id)).fetchone()
        if not r:
            return None
        # SELECT * hands back the stored column, so the decryption has to happen
        # here rather than at each caller - this row goes straight to the "why"
        # surface, where ciphertext would be displayed as if it were the quoted
        # evidence that produced the memory.
        d = dict(r)
        d["evidence"] = decrypt_content(d.get("evidence"))
        return d

    def source_for_assertion(self, project_id, assertion_id):
        """Reverse provenance: which source record produced this belief."""
        rows = self.db.execute(
            "SELECT produced, source_record_id FROM ingest_jobs WHERE project_id=? AND state='completed'",
            (project_id,))
        for r in rows:
            if assertion_id in json.loads(r["produced"] or "[]"):
                sr = self.db.execute("SELECT * FROM source_records WHERE id=?", (r["source_record_id"],)).fetchone()
                return dict(sr) if sr else None
        return None
