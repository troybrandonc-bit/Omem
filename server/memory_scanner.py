"""Memory scanner: traces every active assertion back to its source and re-evaluates
whether it should still exist.

Design rules:
- The frozen engine is the sole authority on memory state. We inspect it; we never
  bypass it. Corrections go through the existing recorded retract path.
- Scans are append-only: a scan result is a record, not a mutation. Application is
  explicit and separate.
- Everything is auditable: why each conclusion was reached, what evidence was
  examined, which source record was found or missing.
- Dry-run is the default. Nothing changes until apply=True is called on a completed scan.

Classification outcomes:
  VALID          - assertion is supported by its source evidence and still warranted
  DUPLICATE      - an open assertion with the same (subjects, proposition) already exists
  UNSUPPORTED    - the source record exists but the evidence no longer supports the fact
  IRRELEVANT     - the source was business content but the fact has no durability
  AUTOMATED_NOISE - the source is a machine-generated notification; the fact should not exist
  LOW_VALUE      - fact is technically supported but below durability threshold
  SUPERSEDED     - a later assertion supersedes this one (it should be closed)
  CONTRADICTED   - the engine already reports CONTRADICTED on this proposition
  STALE          - source record missing, evidence missing, or no provenance
  UNKNOWN        - could not determine (scan error, ambiguous state)
"""
from __future__ import annotations
import json
import time
import hashlib
import secrets
from typing import Callable

SCAN_CLASSIFICATIONS = (
    "VALID", "DUPLICATE", "UNSUPPORTED", "IRRELEVANT", "AUTOMATED_NOISE",
    "LOW_VALUE", "SUPERSEDED", "CONTRADICTED", "STALE", "UNKNOWN",
)

# Outcomes that warrant retraction (when corrections are applied)
RETRACT_ON = frozenset({"DUPLICATE", "UNSUPPORTED", "AUTOMATED_NOISE", "STALE"})

# Outcomes that go to the review queue rather than auto-retract
REVIEW_ON = frozenset({"IRRELEVANT", "LOW_VALUE"})

SCAN_SCHEMA = """
CREATE TABLE IF NOT EXISTS memory_scans(
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL,
  triggered_by TEXT,
  scope TEXT NOT NULL DEFAULT 'all',
  state TEXT NOT NULL DEFAULT 'running',
  total INTEGER NOT NULL DEFAULT 0,
  examined INTEGER NOT NULL DEFAULT 0,
  started REAL NOT NULL,
  finished REAL,
  summary TEXT,
  applied INTEGER NOT NULL DEFAULT 0,
  apply_ts REAL
);
CREATE INDEX IF NOT EXISTS ms_project ON memory_scans(project_id, started);

CREATE TABLE IF NOT EXISTS memory_scan_results(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  scan_id TEXT NOT NULL,
  project_id TEXT NOT NULL,
  assertion_id TEXT NOT NULL,
  classification TEXT NOT NULL,
  reason TEXT NOT NULL,
  source_record_id TEXT,
  evidence TEXT,
  original_evidence TEXT,
  classifier_verdict TEXT,
  extractor_name TEXT,
  confidence REAL,
  proposed_action TEXT,
  applied INTEGER NOT NULL DEFAULT 0,
  apply_error TEXT,
  ts REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS msr_scan ON memory_scan_results(scan_id);
CREATE INDEX IF NOT EXISTS msr_assertion ON memory_scan_results(project_id, assertion_id);
CREATE INDEX IF NOT EXISTS msr_classification ON memory_scan_results(project_id, classification);

CREATE TABLE IF NOT EXISTS review_queue(
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL,
  assertion_id TEXT NOT NULL,
  scan_id TEXT NOT NULL,
  scan_result_id INTEGER NOT NULL,
  classification TEXT NOT NULL,
  reason TEXT NOT NULL,
  subjects TEXT NOT NULL,
  proposition TEXT NOT NULL,
  source_evidence TEXT,
  status TEXT NOT NULL DEFAULT 'pending',
  reviewer TEXT,
  reviewed_ts REAL,
  created REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS rq_project ON review_queue(project_id, status);
CREATE INDEX IF NOT EXISTS rq_assertion ON review_queue(project_id, assertion_id);
"""


def _now() -> float:
    return time.time()


def _id(prefix: str) -> str:
    return f"{prefix}_{secrets.token_hex(6)}"


class MemoryScanner:
    """Examines active assertions, traces them to their source, and re-evaluates quality.

    Requires:
      db          - the shared SQLite/PG connection (STORE.db)
      project     - a live Project object (engine + labels)
      classifier  - classifier.classify function (optional; used for automated-noise re-eval)
      record_fn   - api.record() — the authoritative write path for retractions
      mint_fn     - id minter (api.mint)
    """

    def __init__(self, db, project, classifier_fn=None, record_fn=None, mint_fn=None,
                 identity_fn=None):
        self.db = db
        self.project = project
        self.classifier_fn = classifier_fn
        self.identity_fn = identity_fn  # fn(connector_id) -> org identity dict
        self.record_fn = record_fn
        self.mint_fn = mint_fn
        db.executescript(SCAN_SCHEMA)
        db.commit()

    # ── public interface ────────────────────────────────────────────────────

    def start_scan(self, triggered_by: str = "system", scope: str = "all") -> str:
        """Create a scan record and run it synchronously. Returns scan_id.

        scope: 'all' | 'recent' (last 30 days of source records)
        """
        scan_id = _id("scan")
        self.db.execute(
            "INSERT INTO memory_scans(id,project_id,triggered_by,scope,state,started) VALUES(?,?,?,?,?,?)",
            (scan_id, self.project.id, triggered_by, scope, "running", _now()))
        self.db.commit()
        try:
            summary = self._run_scan(scan_id, scope)
            self.db.execute(
                "UPDATE memory_scans SET state='complete',finished=?,total=?,examined=?,summary=? WHERE id=?",
                (_now(), summary["total"], summary["examined"], json.dumps(summary), scan_id))
        except Exception as e:
            self.db.execute(
                "UPDATE memory_scans SET state='error',finished=?,summary=? WHERE id=?",
                (_now(), json.dumps({"error": str(e)}), scan_id))
            raise
        finally:
            self.db.commit()
        return scan_id

    def get_scan(self, scan_id: str) -> dict | None:
        r = self.db.execute(
            "SELECT * FROM memory_scans WHERE id=?", (scan_id,)).fetchone()
        if not r:
            return None
        d = dict(r)
        d["summary"] = json.loads(d["summary"] or "{}")
        return d

    def scan_results(self, scan_id: str, classification: str | None = None,
                     limit: int = 200, offset: int = 0) -> list[dict]:
        q = "SELECT * FROM memory_scan_results WHERE scan_id=?"
        args: list = [scan_id]
        if classification:
            q += " AND classification=?"
            args.append(classification)
        q += " ORDER BY id LIMIT ? OFFSET ?"
        args += [limit, offset]
        out = []
        for r in self.db.execute(q, args):
            d = dict(r)
            if d.get("classifier_verdict"):
                try:
                    d["classifier_verdict"] = json.loads(d["classifier_verdict"])
                except Exception:
                    pass
            out.append(d)
        return out

    def list_scans(self, limit: int = 20) -> list[dict]:
        rows = self.db.execute(
            "SELECT * FROM memory_scans WHERE project_id=? ORDER BY started DESC LIMIT ?",
            (self.project.id, limit)).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["summary"] = json.loads(d["summary"] or "{}")
            out.append(d)
        return out

    def _ensure_scanner_agent(self, agent_id: str) -> None:
        """Register the scanner agent in the engine if not already present."""
        p = self.project
        if agent_id not in p.labels and self.record_fn is not None:
            self.record_fn(p, "agent", {"id": agent_id, "kind": "system",
                                         "label": "Memory Scanner"})

    def apply_corrections(self, scan_id: str, agent_id: str = "scanner:system") -> dict:
        """Apply all proposed retractions from a completed scan. Idempotent.
        Never deletes; always goes through the frozen retract path.
        Results that go to review_queue get a pending entry instead of a retraction.
        """
        scan = self.get_scan(scan_id)
        if not scan:
            raise ValueError(f"scan {scan_id} not found")
        if scan["state"] != "complete":
            raise ValueError(f"scan is not complete (state={scan['state']})")
        if self.record_fn is None or self.mint_fn is None:
            raise RuntimeError("record_fn and mint_fn required to apply corrections")

        self._ensure_scanner_agent(agent_id)

        rows = self.db.execute(
            "SELECT * FROM memory_scan_results WHERE scan_id=? AND applied=0",
            (scan_id,)).fetchall()

        retracted = review_added = skipped = errors = 0
        for row in rows:
            row = dict(row)
            action = row.get("proposed_action")
            try:
                if action == "retract":
                    self._apply_retract(row, agent_id)
                    self.db.execute(
                        "UPDATE memory_scan_results SET applied=1 WHERE id=?", (row["id"],))
                    retracted += 1
                elif action == "review":
                    self._add_to_review_queue(row, scan_id)
                    self.db.execute(
                        "UPDATE memory_scan_results SET applied=1 WHERE id=?", (row["id"],))
                    review_added += 1
                else:
                    self.db.execute(
                        "UPDATE memory_scan_results SET applied=1 WHERE id=?", (row["id"],))
                    skipped += 1
            except Exception as e:
                self.db.execute(
                    "UPDATE memory_scan_results SET apply_error=? WHERE id=?",
                    (str(e)[:300], row["id"]))
                errors += 1
            self.db.commit()

        self.db.execute(
            "UPDATE memory_scans SET applied=1, apply_ts=? WHERE id=?",
            (_now(), scan_id))
        self.db.commit()
        return {"retracted": retracted, "review_added": review_added,
                "skipped": skipped, "errors": errors, "scan_id": scan_id}

    # ── review queue ────────────────────────────────────────────────────────

    def review_queue(self, status: str = "pending", limit: int = 100) -> list[dict]:
        rows = self.db.execute(
            "SELECT * FROM review_queue WHERE project_id=? AND status=? ORDER BY created DESC LIMIT ?",
            (self.project.id, status, limit)).fetchall()
        return [dict(r) for r in rows]

    def review_decision(self, queue_id: str, decision: str, reviewer: str = "") -> dict:
        """decision: 'approve' (retract) | 'reject' (keep)"""
        row = self.db.execute(
            "SELECT * FROM review_queue WHERE id=? AND project_id=?",
            (queue_id, self.project.id)).fetchone()
        if not row:
            raise ValueError(f"queue item {queue_id} not found")
        row = dict(row)
        if row["status"] != "pending":
            raise ValueError(f"already reviewed (status={row['status']})")
        if decision == "approve":
            # retract the assertion
            self._ensure_scanner_agent("scanner:system")
            if self.record_fn and self.mint_fn:
                aid = row["assertion_id"]
                p = self.project
                a = p.engine.store.assertion(aid)
                if a:
                    nid = self.mint_fn("a")
                    did = self.mint_fn("d")
                    self.record_fn(p, "retract", {
                        "id": nid, "agent": "scanner:system",
                        "subjects": list(a.subjects),
                        "proposition": a.proposition,
                        "assertion_time": p.tick(),
                        "old": aid, "did": did,
                    })
        self.db.execute(
            "UPDATE review_queue SET status=?,reviewer=?,reviewed_ts=? WHERE id=?",
            (decision + "d", reviewer, _now(), queue_id))
        self.db.commit()
        return {"id": queue_id, "decision": decision, "assertion_id": row["assertion_id"]}

    # ── internal: scan execution ────────────────────────────────────────────

    def _run_scan(self, scan_id: str, scope: str) -> dict:
        p = self.project
        e = p.engine
        T = p.now()

        from omem_engine.canon import RETRACTED

        # All assertions in the engine (in-memory). Filter to this project.
        all_assertions = list(e.store.assertions())

        # For 'recent' scope: only assertions whose source record was received
        # in the last 30 days. We derive this from assertion_evidence.ts.
        recent_cutoff = _now() - 30 * 86400 if scope == "recent" else None

        counts: dict[str, int] = {c: 0 for c in SCAN_CLASSIFICATIONS}
        examined = 0

        # Build a duplicate-detection index: (frozenset(subjects), proposition)
        # -> list of open assertion ids. We populate this as we go so we can
        # detect duplicates within the scan itself.
        seen_props: dict[tuple, str] = {}

        for a in all_assertions:
            # Skip retractions themselves (they are not memories)
            if a.proposition == RETRACTED:
                continue
            # Skip assertions not in this project (engine is per-project, but be safe)

            # Skip assertions that are already closed
            if not e.ledger.is_open_at(a, T):
                continue

            if recent_cutoff:
                ev_row = self.db.execute(
                    "SELECT created FROM assertion_evidence WHERE assertion_id=? AND project_id=?",
                    (a.id, p.id)).fetchone()
                if ev_row and ev_row["created"] < recent_cutoff:
                    continue

            examined += 1
            result = self._evaluate_assertion(a, T, seen_props, scan_id)
            cls = result["classification"]
            counts[cls] = counts.get(cls, 0) + 1

            # Track for duplicate detection
            key = (frozenset(a.subjects), a.proposition)
            if cls == "VALID" and key not in seen_props:
                seen_props[key] = a.id

            # Persist result
            self.db.execute(
                "INSERT INTO memory_scan_results"
                "(scan_id,project_id,assertion_id,classification,reason,"
                "source_record_id,evidence,original_evidence,classifier_verdict,"
                "extractor_name,confidence,proposed_action,ts) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (scan_id, p.id, a.id, cls,
                 result["reason"][:500],
                 result.get("source_record_id"),
                 (result.get("evidence") or "")[:800],
                 (result.get("original_evidence") or "")[:800],
                 json.dumps(result.get("classifier_verdict")) if result.get("classifier_verdict") else None,
                 result.get("extractor_name"),
                 result.get("confidence"),
                 result.get("proposed_action"),
                 _now()))
        self.db.commit()

        total = len([a for a in all_assertions
                     if a.proposition != RETRACTED and e.ledger.is_open_at(a, T)])

        return {
            "total": total,
            "examined": examined,
            "scope": scope,
            "by_classification": counts,
            "proposed_retractions": counts.get("DUPLICATE", 0)
                                   + counts.get("UNSUPPORTED", 0)
                                   + counts.get("AUTOMATED_NOISE", 0)
                                   + counts.get("STALE", 0),
            "proposed_review": counts.get("IRRELEVANT", 0) + counts.get("LOW_VALUE", 0),
        }

    def _evaluate_assertion(self, a, T: int, seen_props: dict, scan_id: str) -> dict:
        """Evaluate one assertion. Returns a result dict."""
        p = self.project
        e = p.engine
        aid = a.id

        # ── 1. Duplicate check (must happen before evidence checks) ────────
        key = (frozenset(a.subjects), a.proposition)
        if key in seen_props and seen_props[key] != aid:
            return {
                "classification": "DUPLICATE",
                "reason": f"Open assertion {seen_props[key]} already expresses the same belief",
                "proposed_action": "retract",
            }

        # ── 2. CONTRADICTED by engine ──────────────────────────────────────
        state = e.proposition_state(list(a.subjects), a.proposition, T)
        if state == "CONTRADICTED":
            return {
                "classification": "CONTRADICTED",
                "reason": "Engine reports CONTRADICTED — a competing assertion exists",
                "proposed_action": None,  # engine already handles this; no action needed
            }

        # ── 3. Trace provenance to source ─────────────────────────────────
        prov_ids, grounded = e.provenance(aid)
        derivations = e.store.derivations_for_consequent(aid)

        evidence_row = self.db.execute(
            "SELECT * FROM assertion_evidence WHERE assertion_id=? AND project_id=?",
            (aid, p.id)).fetchone()

        # No evidence record at all: decide based on what provenance exists.
        if evidence_row is None:
            if not derivations:
                # Completely ungrounded and not derived: manually asserted via SDK/API
                # without going through the ingestion pipeline. Treat as VALID —
                # the user wrote it intentionally. Mark so in the reason.
                return {
                    "classification": "VALID",
                    "reason": "Directly asserted (no pipeline evidence required for SDK/API writes)",
                    "proposed_action": None,
                }
            # Has a derivation chain but no evidence record: either pre-evidence-table
            # ingestion or a derived fact. Try to trace the source record.
            src = self._find_source_record(aid, p.id)
            if src is None:
                # Could be a derivation-only fact (no source record by design)
                # Only mark STALE if it was grounded to an event (expected source)
                if grounded:
                    return {
                        "classification": "STALE",
                        "reason": "Grounded assertion has derivation but no evidence record and no traceable source record",
                        "proposed_action": "retract",
                    }
                return {
                    "classification": "VALID",
                    "reason": "Derived assertion with no source record (pipeline derivation without Gmail source)",
                    "proposed_action": None,
                }
            return self._evaluate_from_source(a, src, evidence=None)

        evidence_row = dict(evidence_row)
        original_evidence = evidence_row.get("evidence") or ""
        extractor_name = evidence_row.get("extractor") or ""
        confidence = evidence_row.get("confidence")
        source_record_id = evidence_row.get("source_record_id")

        # ── 4. Source record check ─────────────────────────────────────────
        if source_record_id:
            src = self.db.execute(
                "SELECT * FROM source_records WHERE id=? AND project_id=?",
                (source_record_id, p.id)).fetchone()
        else:
            src = self._find_source_record(aid, p.id)

        if src is None:
            return {
                "classification": "STALE",
                "reason": "Source record referenced by evidence no longer exists",
                "source_record_id": source_record_id,
                "evidence": original_evidence,
                "proposed_action": "retract",
            }

        src = dict(src)
        return self._evaluate_from_source(
            a, src,
            evidence=original_evidence,
            extractor_name=extractor_name,
            confidence=confidence,
        )

    def _evaluate_from_source(self, a, src: dict, evidence: str | None,
                               extractor_name: str = "", confidence: float | None = None) -> dict:
        """Evaluate an assertion given its source record payload."""
        try:
            payload = json.loads(src["payload"])
        except Exception:
            return {
                "classification": "STALE",
                "reason": "Source record payload is malformed JSON",
                "source_record_id": src["id"],
                "proposed_action": "retract",
            }

        connector_id = src.get("connector_id")
        connector_kind = self._connector_kind(connector_id)

        # ── 5. Re-analyse the source with the current understanding layer ──
        if connector_kind == "gmail":
            try:
                from email_analysis import analyze, speech_act as _speech_act
                owner = None
                if self.identity_fn is not None and connector_id:
                    try:
                        owner = self.identity_fn(connector_id)
                    except Exception:
                        owner = None
                if owner is None and connector_id:
                    cr = self.db.execute(
                        "SELECT account FROM oauth_creds WHERE connector_id=?",
                        (connector_id,)).fetchone()
                    owner = cr["account"] if cr else None
                # feed the deterministic classifier's scores into the analysis
                verdict = None
                if self.classifier_fn is not None:
                    try:
                        verdict = self.classifier_fn(payload)
                    except Exception:
                        verdict = None
                scores = (verdict or {}).get("scores", {}) if verdict else {}
                analysis = analyze(payload, owner,
                                   business_score=scores.get("business", 0.0),
                                   automated_score=scores.get("automated", 0.0),
                                   business_signals=(verdict or {}).get("signals", []))
            except Exception:
                analysis, verdict = None, None

            if analysis is not None:
                if analysis["saas_self_notification"]:
                    return {
                        "classification": "IRRELEVANT",
                        "reason": ("Source is a third-party platform notification about "
                                   "the owner's own account — not a business relationship"),
                        "source_record_id": src["id"],
                        "evidence": evidence,
                        "original_evidence": evidence,
                        "proposed_action": "retract",
                    }
                if analysis["is_noise_category"]:
                    return {
                        "classification": "AUTOMATED_NOISE",
                        "reason": f"Source re-categorised as {analysis['category']}",
                        "source_record_id": src["id"],
                        "evidence": evidence,
                        "original_evidence": evidence,
                        "classifier_verdict": verdict,
                        "proposed_action": "retract",
                    }
                # speech-act recheck: a memory whose evidence sentence is a
                # question or marketing CTA was extracted from non-assertive
                # language and is unsupported
                if evidence:
                    ev_sentence = evidence.strip().strip('"').strip()
                    if ev_sentence:
                        act = _speech_act(ev_sentence)
                        if act in ("QUESTION", "MARKETING_CTA", "SUGGESTION"):
                            return {
                                "classification": "UNSUPPORTED",
                                "reason": (f"Evidence is a {act.lower().replace('_', ' ')}, "
                                           f"not a statement: \"{ev_sentence[:80]}\""),
                                "source_record_id": src["id"],
                                "evidence": evidence,
                                "original_evidence": evidence,
                                "proposed_action": "retract",
                            }

            if verdict is not None:
                cls_name = verdict.get("classification", "")
                if cls_name == "AUTOMATED_NOISE":
                    return {
                        "classification": "AUTOMATED_NOISE",
                        "reason": (
                            "Source re-classified as automated noise: "
                            + "; ".join((verdict.get("reasons") or [])[:2])
                        ),
                        "source_record_id": src["id"],
                        "evidence": evidence,
                        "original_evidence": evidence,
                        "classifier_verdict": verdict,
                        "proposed_action": "retract",
                    }

        # ── 6. Evidence support check ──────────────────────────────────────
        if evidence:
            # Strip the surrounding quotes added by extractors
            ev_text = evidence.strip('"').strip()
            source_text = f"{payload.get('subject', '')} {payload.get('body', '')}"
            import re as _re
            normalised_ev = _re.sub(r"\s+", " ", ev_text.lower()).strip()
            normalised_src = _re.sub(r"\s+", " ", source_text.lower()).strip()
            evidence_found = normalised_ev and (normalised_ev[:40] in normalised_src)
            if not evidence_found and len(ev_text) > 10:
                # Evidence quoted in the record is not in the source text.
                # This can happen if the source was updated or if the extractor
                # drifted. Mark as unsupported.
                return {
                    "classification": "UNSUPPORTED",
                    "reason": (
                        f"Evidence span not found in source: "
                        f"\"{ev_text[:80]}\" is absent from the message text"
                    ),
                    "source_record_id": src["id"],
                    "evidence": evidence,
                    "original_evidence": evidence,
                    "extractor_name": extractor_name,
                    "proposed_action": "retract",
                }

        # ── 7. Durability / low-value check ───────────────────────────────
        proposition = a.proposition
        low_value_props = {
            "scheduling_call", "meeting_tomorrow", "sounds_good",
            "acknowledged", "thanks", "noted",
        }
        if any(lv in proposition for lv in ("scheduling", "tomorrow", "acknowledged")):
            return {
                "classification": "LOW_VALUE",
                "reason": f"Proposition '{proposition}' appears to be low-durability scheduling/acknowledgement",
                "source_record_id": src["id"],
                "evidence": evidence,
                "proposed_action": "review",
            }

        conf = confidence if confidence is not None else 1.0
        if conf < 0.5:
            return {
                "classification": "LOW_VALUE",
                "reason": f"Original extraction confidence {conf:.2f} is below durability threshold (0.5)",
                "source_record_id": src["id"],
                "evidence": evidence,
                "confidence": conf,
                "proposed_action": "review",
            }

        # ── 8. Passes all checks ───────────────────────────────────────────
        return {
            "classification": "VALID",
            "reason": "Assertion is supported by its source evidence and passes all quality checks",
            "source_record_id": src["id"],
            "evidence": evidence,
            "extractor_name": extractor_name,
            "confidence": conf,
            "proposed_action": None,
        }

    def _find_source_record(self, assertion_id: str, project_id: str) -> dict | None:
        """Reverse-lookup: find the source record that produced this assertion."""
        rows = self.db.execute(
            "SELECT produced, source_record_id FROM ingest_jobs "
            "WHERE project_id=? AND state='completed' AND produced IS NOT NULL",
            (project_id,)).fetchall()
        for r in rows:
            try:
                produced = json.loads(r["produced"] or "[]")
            except Exception:
                continue
            if assertion_id in produced:
                src = self.db.execute(
                    "SELECT * FROM source_records WHERE id=? AND project_id=?",
                    (r["source_record_id"], project_id)).fetchone()
                return dict(src) if src else None
        return None

    def _connector_kind(self, connector_id: str | None) -> str:
        if not connector_id:
            return ""
        r = self.db.execute(
            "SELECT kind FROM connectors WHERE id=?", (connector_id,)).fetchone()
        return r["kind"] if r else ""

    def _apply_retract(self, row: dict, agent_id: str) -> None:
        p = self.project
        aid = row["assertion_id"]
        a = p.engine.store.assertion(aid)
        if a is None:
            return  # already gone
        if not p.engine.ledger.is_open_at(a, p.now()):
            return  # already closed
        from omem_engine.canon import RETRACTED
        if a.proposition == RETRACTED:
            return  # it is already a retraction
        nid = self.mint_fn("a")
        did = self.mint_fn("d")
        self.record_fn(p, "retract", {
            "id": nid, "agent": agent_id,
            "subjects": list(a.subjects),
            "proposition": a.proposition,
            "assertion_time": p.tick(),
            "old": aid, "did": did,
        })

    def _add_to_review_queue(self, row: dict, scan_id: str) -> None:
        p = self.project
        aid = row["assertion_id"]
        a = p.engine.store.assertion(aid)
        subjects_str = json.dumps(list(a.subjects) if a else [])
        proposition = a.proposition if a else ""
        # Avoid duplicate queue entries for the same assertion
        existing = self.db.execute(
            "SELECT id FROM review_queue WHERE project_id=? AND assertion_id=? AND status='pending'",
            (p.id, aid)).fetchone()
        if existing:
            return
        qid = _id("rq")
        self.db.execute(
            "INSERT INTO review_queue(id,project_id,assertion_id,scan_id,scan_result_id,"
            "classification,reason,subjects,proposition,source_evidence,created) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (qid, p.id, aid, scan_id, row["id"],
             row["classification"], row["reason"][:400],
             subjects_str, proposition,
             (row.get("evidence") or "")[:600], _now()))

    # ── Gmail source rescan ─────────────────────────────────────────────────

    def rescan_gmail_sources(self, connector_id: str | None = None,
                              limit: int = 500, window_days: int | None = None) -> dict:
        """Re-run the current classifier over stored source records to identify:
        - messages that were previously excluded but should now enter the pipeline
        - messages that were included but are now classified as noise

        window_days limits the rescan to sources received within the last N days
        (7/30/90/365); None = all stored mail.

        Does NOT re-fetch from Gmail. Does NOT create new source records.
        Returns a summary; actual re-ingestion requires explicit trigger.
        """
        if self.classifier_fn is None:
            return {"error": "classifier not available"}

        p = self.project
        q = ("SELECT sr.* FROM source_records sr "
             "JOIN connectors c ON c.id=sr.connector_id "
             "WHERE sr.project_id=? AND c.kind='gmail'")
        args: list = [p.id]
        if connector_id:
            q += " AND sr.connector_id=?"
            args.append(connector_id)
        if window_days:
            q += " AND sr.received >= ?"
            args.append(_now() - int(window_days) * 86400)
        q += " ORDER BY sr.id DESC LIMIT ?"
        args.append(limit)

        rows = self.db.execute(q, args).fetchall()

        reclassified_include = []
        reclassified_exclude = []
        unchanged = 0

        for row in rows:
            row = dict(row)
            srid = row["id"]
            try:
                payload = json.loads(row["payload"])
            except Exception:
                continue

            new_verdict = self.classifier_fn(payload)
            new_cls = new_verdict.get("classification", "")

            old_cls_row = self.db.execute(
                "SELECT classification, entered_pipeline FROM message_classifications "
                "WHERE source_record_id=? ORDER BY id DESC LIMIT 1", (srid,)).fetchone()

            if old_cls_row is None:
                old_cls = "UNKNOWN"
                was_in_pipeline = False
            else:
                old_cls = old_cls_row["classification"]
                was_in_pipeline = bool(old_cls_row["entered_pipeline"])

            now_in = new_cls == "BUSINESS_RELEVANT"
            now_out = new_cls in ("NON_BUSINESS", "AUTOMATED_NOISE")

            if now_in and not was_in_pipeline:
                reclassified_include.append({
                    "source_record_id": srid,
                    "external_id": row.get("external_id"),
                    "subject": payload.get("subject", "")[:120],
                    "from": payload.get("from", ""),
                    "old_classification": old_cls,
                    "new_classification": new_cls,
                    "new_confidence": new_verdict.get("confidence"),
                    "reasons": new_verdict.get("reasons", []),
                })
            elif now_out and was_in_pipeline:
                reclassified_exclude.append({
                    "source_record_id": srid,
                    "external_id": row.get("external_id"),
                    "subject": payload.get("subject", "")[:120],
                    "from": payload.get("from", ""),
                    "old_classification": old_cls,
                    "new_classification": new_cls,
                    "new_confidence": new_verdict.get("confidence"),
                    "reasons": new_verdict.get("reasons", []),
                })
            else:
                unchanged += 1

        return {
            "sources_examined": len(rows),
            "newly_relevant": len(reclassified_include),
            "newly_excluded": len(reclassified_exclude),
            "unchanged": unchanged,
            "reclassified_include": reclassified_include[:50],
            "reclassified_exclude": reclassified_exclude[:50],
            # full id list (not truncated) so reprocessing can requeue them
            "newly_relevant_ids": [r["source_record_id"] for r in reclassified_include],
        }

    # ── aggregate health metrics ────────────────────────────────────────────

    def health_summary(self) -> dict:
        """Real database-backed memory health metrics for the dashboard."""
        p = self.project
        e = p.engine
        T = p.now()

        from omem_engine.canon import RETRACTED

        all_a = list(e.store.assertions())
        open_a = [a for a in all_a
                  if a.proposition != RETRACTED and e.ledger.is_open_at(a, T)]

        # Pull latest scan for this project
        latest = self.db.execute(
            "SELECT * FROM memory_scans WHERE project_id=? AND state='complete' "
            "ORDER BY started DESC LIMIT 1",
            (p.id,)).fetchone()

        by_cls: dict[str, int] = {c: 0 for c in SCAN_CLASSIFICATIONS}
        scan_id = None
        scan_ts = None
        if latest:
            latest = dict(latest)
            scan_id = latest["id"]
            scan_ts = latest["started"]
            summary = json.loads(latest["summary"] or "{}")
            by_cls = summary.get("by_classification", by_cls)

        # Review queue counts
        pending_review = self.db.execute(
            "SELECT COUNT(*) c FROM review_queue WHERE project_id=? AND status='pending'",
            (p.id,)).fetchone()["c"]

        # Recent corrections (retractions that originated from scanner)
        recent_retractions = self._recent_scanner_corrections(limit=10)

        return {
            "active_memories": len(open_a),
            "total_assertions_ever": len(all_a),
            "last_scan_id": scan_id,
            "last_scan_ts": scan_ts,
            "by_classification": by_cls,
            "pending_review": pending_review,
            "recent_corrections": recent_retractions,
            "needs_scan": scan_id is None or (scan_ts and (_now() - scan_ts) > 86400),
        }

    def _recent_scanner_corrections(self, limit: int = 10) -> list[dict]:
        """Retractions that came from the scanner (agent='scanner:system')."""
        # We can identify scanner-originated retractions from the ops log.
        rows = self.db.execute(
            "SELECT seq, kind, args, ts FROM ops WHERE project_id=? AND kind='retract' "
            "ORDER BY seq DESC LIMIT ?",
            (self.project.id, limit * 3)).fetchall()
        out = []
        for r in rows:
            try:
                args = json.loads(r["args"])
            except Exception:
                continue
            if args.get("agent") != "scanner:system":
                continue
            out.append({
                "assertion_id": args.get("old"),
                "proposition": args.get("proposition"),
                "subjects": args.get("subjects", []),
                "ts": r["ts"],
            })
            if len(out) >= limit:
                break
        return out
