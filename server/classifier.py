"""Business-relevance classification: the gate between Gmail ingestion and memory.

Two stages, deliberately separated:

  STAGE 1 (this module)  "Should this message enter the memory pipeline?"
  STAGE 2 (extractors)   "What durable facts, if any, does it contain?"

A message can be BUSINESS_RELEVANT and still produce zero memories, "sounds
good, let's talk tomorrow" is real business correspondence with nothing durable
in it. Relevance is not evidence.

Design rules taken from the product brief:

* Domains and automated-mail headers are SIGNALS, never verdicts. A contract
  amendment sent from a noreply@ address is still business; a marketing blast
  from a supplier you negotiate with daily is still noise.
* Threads are judged as units. "Yes, we can do EUR 24,000" is meaningless alone
  and obviously commercial in context, so a message inherits thread context.
* Relationship history (substantive two-way exchange over time) is evidence of a
  real business relationship, but is never on its own a reason to remember.
* Scores are coarse on purpose. Inventing two decimal places of confidence from
  keyword counts would be fake precision.

The frozen engine is untouched: this layer only decides what gets proposed.
"""
from __future__ import annotations

from secrets_provider import (  # noqa: E402
    content_encryption_enabled, decrypt_content,
)

import json
import re
import time

# ── vocabulary ─────────────────────────────────────────────────────────────
CLASSIFICATIONS = ("BUSINESS_RELEVANT", "POSSIBLY_BUSINESS", "NON_BUSINESS", "AUTOMATED_NOISE")
BUSINESS_TYPES = ("CUSTOMER", "PROSPECT", "SUPPLIER", "VENDOR", "PARTNER", "CONTRACT",
                  "NEGOTIATION", "PROJECT", "FINANCE", "LEGAL", "EMPLOYEE",
                  "PROFESSIONAL_CONTACT", "OTHER_BUSINESS")

# Thresholds. Conservative by design: uncertain mail must not become memory.
THRESHOLD_RELEVANT = 0.70      # enters extraction
THRESHOLD_POSSIBLE = 0.45      # classified, but extraction demands stronger evidence

# ── commercial content signals ─────────────────────────────────────────────
# Weighted phrases. Weight reflects how strongly the phrase implies a real
# commercial relationship rather than a platform event.
_BUSINESS_PATTERNS: list[tuple[str, float, str, str]] = [
    # (regex, weight, signal name, business type hint)
    (r"\b(quote|quotation|quoted price|pro ?forma)\b", 0.30, "pricing", "SUPPLIER"),
    (r"\b(unit price|price per|per unit|price list|pricing)\b", 0.28, "pricing", "SUPPLIER"),
    (r"\b(discount|reduce the price|lower the price|best price|negotiat\w+)\b", 0.34, "negotiation", "NEGOTIATION"),
    (r"\b(purchase order|\bPO\b|order quantity|minimum order|MOQ)\b", 0.30, "purchasing", "SUPPLIER"),
    (r"\b(lead time|delivery date|shipment schedule|production time)\b", 0.26, "logistics_terms", "SUPPLIER"),
    (r"\b(contract|agreement|amendment|addendum|term sheet|SOW|statement of work)\b", 0.32, "contract", "CONTRACT"),
    (r"\b(payment terms|net ?\d{1,3}\b|invoice dispute|outstanding balance|overdue)\b", 0.30, "payment_terms", "FINANCE"),
    (r"\b(renew\w*|renewal|auto-?renew)\b.{0,40}\b(contract|subscription|term|annually|year)\b", 0.30, "renewal", "CONTRACT"),
    (r"\b(proposal|scope of work|deliverable|milestone|requirements?)\b", 0.31, "project", "PROJECT"),
    (r"\b(partnership|reseller|distributor|integration partner|joint)\b", 0.30, "partnership", "PARTNER"),
    (r"\b(onboard\w*|kick-?off|implementation plan|rollout)\b", 0.22, "project", "PROJECT"),
    (r"\b(complaint|not acceptable|unacceptable|refund|escalat\w+|defect|faulty)\b", 0.26, "issue", "CUSTOMER"),
    (r"\b(sign(ed)? off|approve[ds]?|approval|we agreed|as agreed|confirm(ed|ing)?)\b", 0.22, "commitment", "OTHER_BUSINESS"),
    (r"\b(budget|cost|EUR|USD|GBP|€|\$|£)\s?[\d.,]{2,}", 0.26, "commercial_terms", "FINANCE"),
    (r"\b(decision ?maker|procurement|legal team|our CFO|our CTO|account manager)\b", 0.24, "roles", "PROFESSIONAL_CONTACT"),
    (r"\b(meeting|call)\b.{0,30}\b(agenda|minutes|follow[- ]?up|action items?|outcome)\b", 0.24, "meeting_outcome", "OTHER_BUSINESS"),
    (r"\b(SLA|uptime|compliance|GDPR|DPA|security review|questionnaire)\b", 0.24, "compliance", "LEGAL"),
    # Account expansion and billing cadence are core customer signals. Their
    # absence was a real false negative: "we want to upgrade to the enterprise
    # tier" scored 0.28 and was excluded.
    (r"\b(upgrade|downgrade|expand|scale up)\b[^.]{0,40}\b(plan|tier|licen[cs]e|seats?|subscription|account)\b",
     0.32, "plan_change", "CUSTOMER"),
    (r"\b(?:would like to|want to|plan(?:ning)? to|intend to|looking to)\s+(upgrade|downgrade|renew|cancel|switch)\b",
     0.32, "commercial_intent", "CUSTOMER"),
    # A customer ASKING about a plan action is relationship-relevant even though
    # the question itself never becomes a fact (extraction refuses questions).
    (r"\b(?:can|could|may) we\s+(?:cancel|renew|upgrade|downgrade|extend)\b[^.?]{0,40}\b(?:subscription|contract|plan|agreement|account)\b",
     0.34, "commercial_inquiry", "CUSTOMER"),
    (r"\b(?:decided|deciding|agreed)\s+to\s+(?:cancel|renew|upgrade|downgrade|extend|switch)\b",
     0.34, "commercial_intent", "CUSTOMER"),
    (r"\b(?:considering|thinking about|weighing)\s+(?:cancell?ing|leaving|switching|renewing|downgrading|upgrading)\b",
     0.32, "commercial_intent", "CUSTOMER"),
    (r"\b(?:we|i)(?:'ve| have)\s+(?:renewed|cancell?ed|signed|upgraded|downgraded)\b",
     0.32, "commitment", "CUSTOMER"),
    (r"(?<!you can )(?<!can be )\b(?:cancel(?:ling)?|renew(?:ing)?|extend(?:ing)?)\s+(?:our|the|this|my)\s+(?:subscription|contract|agreement|plan)\b",
     0.30, "plan_change", "CUSTOMER"),
    (r"\b(annual|monthly|quarterly)\s+billing\b|\bbilling (?:cycle|cadence|frequency)\b",
     0.32, "billing_terms", "FINANCE"),
    (r"\b(enterprise|business|professional|pro)\s+(tier|plan)\b", 0.26, "plan_change", "CUSTOMER"),
    (r"\b(seats?|licen[cs]es?|users?)\b[^.]{0,25}\b(add|increase|more|additional)\b",
     0.26, "expansion", "CUSTOMER"),
    # How a counterparty wants the relationship conducted is durable relationship
    # information (another real false negative found in testing).
    (r"\bprefers?\b[^.]{0,20}\b(email|phone|call|slack|teams)\b[^.]{0,30}\b(over|instead of|for)\b",
     0.30, "contact_preference", "PROFESSIONAL_CONTACT"),
    (r"\b(?:contact|reach) (?:me|us)\b[^.]{0,25}\b(?:on|via|by)\b", 0.24, "contact_preference", "PROFESSIONAL_CONTACT"),
    (r"\b(?:account|contract|billing) discussions?\b", 0.24, "account_management", "CUSTOMER"),
    (r"\b(samples?|specification|tolerance|材料|manufactur\w+|factory)\b", 0.24, "manufacturing", "SUPPLIER"),
    # Spanish-language business correspondence (customer base in ES/CAT markets)
    (r"\b(contrato|factura|presupuesto|pedido|renovaci[oó]n|precio unitario|condiciones de pago)\b",
     0.30, "commercial_terms_es", "OTHER_BUSINESS"),
    (r"\b(?:queremos|quiero|nos gustar[ií]a|hemos decidido|vamos a)\s+(?:cancelar|renovar|ampliar|firmar|contratar)\b",
     0.34, "commercial_intent", "CUSTOMER"),
    (r"\bhemos (?:cancelado|renovado|firmado|pagado)\b", 0.32, "commitment", "CUSTOMER"),
    (r"\bdescuento del?\s+\d{1,2}\s?%|\bfacturaci[oó]n (?:anual|mensual)\b", 0.30, "billing_terms", "FINANCE"),
]

# ── automated / bulk signals (evidence, not verdicts) ──────────────────────
_AUTOMATED_HEADERS = (
    ("list-unsubscribe", 0.45, "list_unsubscribe"),
    ("list-id", 0.40, "mailing_list"),
    ("feedback-id", 0.30, "bulk_sender_id"),
    ("x-campaign-id", 0.40, "marketing_campaign"),
    ("x-mailer-campaign", 0.40, "marketing_campaign"),
    ("auto-submitted", 0.35, "auto_submitted"),
    ("x-auto-response-suppress", 0.30, "auto_response"),
)
_AUTOMATED_LOCALPARTS = (
    "noreply", "no-reply", "donotreply", "do-not-reply", "notifications",
    "notification", "mailer-daemon", "postmaster", "bounce", "bounces",
    "newsletter", "news", "marketing", "alerts", "updates", "automated",
    "system", "daemon", "support-noreply", "billing-noreply", "info",
)
_NOISE_SUBJECT_PATTERNS = [
    (r"^(out of office|automatic reply|undeliverable|delivery status)", 0.55, "auto_reply"),
    (r"\b(unsubscribe|view (this )?in browser|manage preferences)\b", 0.40, "marketing_body"),
    (r"\b(password reset|reset your password|verify your (email|account)|security alert|new sign-?in)\b", 0.55, "account_notification"),
    (r"\b(your (receipt|order|shipment)|order (confirmation|shipped)|tracking (number|info))\b", 0.45, "transactional_notice"),
    (r"\b(webinar|free trial|limited time|% off|black friday|special offer|newsletter)\b", 0.45, "marketing"),
    (r"\b(pull request|issue #\d+|commit [0-9a-f]{6,}|commits? pushed|build (passed|failed)|workflow run)\b", 0.50, "dev_platform_notification"),
    (r"\b(invited you to|viewed your profile|new connection|endorsed you|people you may know)\b", 0.50, "social_notification"),
    (r"\b(calendar|invitation:|accepted:|declined:|has been (updated|cancelled))\b", 0.35, "calendar_notification"),
]


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip()


def _address_of(sender: str) -> str:
    from email.utils import parseaddr
    return (parseaddr(sender or "")[1] or "").lower()


def automated_signals(payload: dict) -> tuple[float, list[str]]:
    """Evidence that a message was machine-generated. Returns (score, signals).
    Never decisive on its own: business content can outweigh it."""
    score, signals = 0.0, []
    headers = {k.lower(): (v or "") for k, v in (payload.get("headers") or {}).items()}
    for name, weight, label in _AUTOMATED_HEADERS:
        val = headers.get(name, "")
        if val and not (name == "auto-submitted" and val.lower() == "no"):
            score += weight
            signals.append(label)
    if headers.get("precedence", "").lower() in ("bulk", "list", "junk"):
        score += 0.40
        signals.append("precedence_bulk")

    local = _address_of(payload.get("from", "")).split("@")[0]
    if local in _AUTOMATED_LOCALPARTS:
        score += 0.35
        signals.append(f"automated_sender:{local}")

    blob = _norm(f"{payload.get('subject','')} {payload.get('body','')}").lower()
    for pattern, weight, label in _NOISE_SUBJECT_PATTERNS:
        if re.search(pattern, blob, re.I):
            score += weight
            if label not in signals:
                signals.append(label)

    # A message nobody could reply to is usually a broadcast.
    if headers.get("reply-to") and "noreply" in headers["reply-to"].lower():
        score += 0.20
        signals.append("noreply_replyto")
    return min(score, 1.5), signals


def business_signals(text: str) -> tuple[float, list[str], dict[str, float]]:
    """Evidence of real commercial content. Returns (score, signals, type_votes).

    Every distinct pattern contributes, and repeated hits of the same pattern add
    a little more: a message saying "complaint ... defect ... refund ... escalate"
    is more clearly commercial than one that mentions a defect in passing.
    """
    score, signals, votes = 0.0, [], {}
    blob = _norm(text)
    for pattern, weight, label, btype in _BUSINESS_PATTERNS:
        hits = len(re.findall(pattern, blob, re.I))
        if not hits:
            continue
        # first hit full weight, each further hit a third, capped at 2x
        contribution = weight * min(1 + (hits - 1) / 3.0, 2.0)
        score += contribution
        if label not in signals:
            signals.append(label)
        votes[btype] = votes.get(btype, 0.0) + contribution
    return min(score, 2.0), signals, votes


def human_correspondence_score(payload: dict, auto_score: float) -> tuple[float, list[str]]:
    """A written-by-a-person message to a named recipient is the baseline shape of
    business correspondence. This does not make it memorable, extraction still
    has to find a durable fact, but it separates real mail from broadcasts."""
    if auto_score >= 0.5:
        return 0.0, []
    body = _norm(payload.get("body", ""))
    subject = _norm(payload.get("subject", ""))
    score, signals = 0.0, []
    if 20 <= len(body) <= 6000:
        score += 0.18
        signals.append("written_message")
    if re.match(r"^(re|fwd?|aw|tr)\s*:", subject, re.I):
        score += 0.14
        signals.append("reply_in_conversation")
    # addressed to a person and signed off, rather than templated
    if re.search(r"\b(hi|hello|dear|thanks|regards|best|cheers)\b", body, re.I):
        score += 0.10
        signals.append("personal_tone")
    return score, signals


def relationship_signals(history: dict | None) -> tuple[float, list[str]]:
    """Evidence that a real two-way relationship exists with this counterparty.
    Supports classification; never justifies a memory by itself."""
    if not history:
        return 0.0, []
    score, signals = 0.0, []
    msgs = history.get("message_count", 0)
    if msgs >= 20:
        score += 0.25; signals.append("long_history")
    elif msgs >= 5:
        score += 0.15; signals.append("repeat_correspondent")
    elif msgs >= 2:
        score += 0.07; signals.append("prior_contact")
    if history.get("two_way"):
        score += 0.18; signals.append("two_way_conversation")
    if history.get("max_thread_depth", 0) >= 3:
        score += 0.12; signals.append("threaded_discussion")
    return min(score, 0.5), signals


class ClassificationResult(dict):
    """Structured, JSON-serialisable classification."""
    @property
    def allowed(self) -> bool:
        return self["classification"] == "BUSINESS_RELEVANT"

    @property
    def possible(self) -> bool:
        return self["classification"] == "POSSIBLY_BUSINESS"


def classify(payload: dict, thread_context: str = "", history: dict | None = None,
             llm=None) -> ClassificationResult:
    """Classify one message, judged in the context of its thread.

    `thread_context` is the concatenated text of sibling messages, so a short
    reply inherits the commercial weight of the conversation it belongs to.
    `llm` is an optional judge; deterministic scoring always runs and bounds it.
    """
    subject = payload.get("subject", "") or ""
    body = payload.get("body", "") or ""
    own_text = f"{subject}\n{body}"

    auto_score, auto_sig = automated_signals(payload)
    own_score, own_sig, votes = business_signals(own_text)
    human_score, human_sig = human_correspondence_score(payload, auto_score)
    thread_score, thread_sig, thread_votes = business_signals(thread_context or "")
    rel_score, rel_sig = relationship_signals(history)

    # Thread context counts, but at a discount: the message must still belong to
    # a commercial conversation rather than merely sit near one.
    inherited = thread_score * 0.6
    for k, v in thread_votes.items():
        votes[k] = votes.get(k, 0.0) + v * 0.6

    business = own_score + inherited + rel_score + human_score
    # Automated evidence subtracts, but strong commercial content survives it -
    # this is what keeps "contract amendment from noreply@" in scope.
    net = business - (auto_score * 0.55)

    signals = own_sig + [s for s in thread_sig if s not in own_sig] + rel_sig + human_sig + auto_sig
    reasons: list[str] = []
    if own_sig:
        reasons.append("Message contains commercial content: " + ", ".join(own_sig[:4]))
    if thread_sig and not own_sig:
        reasons.append("Belongs to a business thread discussing " + ", ".join(thread_sig[:3]))
    if rel_sig:
        reasons.append("Established correspondence with this counterparty")
    if auto_sig:
        reasons.append("Automated-mail signals present: " + ", ".join(auto_sig[:3]))

    confidence = max(0.0, min(1.0, net))
    if confidence >= THRESHOLD_RELEVANT:
        classification = "BUSINESS_RELEVANT"
    elif confidence >= THRESHOLD_POSSIBLE:
        classification = "POSSIBLY_BUSINESS"
    elif auto_score >= 0.5 and business < 0.35:
        classification = "AUTOMATED_NOISE"
        confidence = max(confidence, min(1.0, auto_score))
        reasons.insert(0, "Machine-generated notification with no relationship content")
    else:
        classification = "NON_BUSINESS"
        if not reasons:
            reasons.append("No commercial or relationship content found")

    business_type = max(votes, key=votes.get) if votes else None
    if classification in ("NON_BUSINESS", "AUTOMATED_NOISE"):
        business_type = None

    result = ClassificationResult({
        "classification": classification,
        "confidence": round(confidence, 2),
        "business_type": business_type,
        "reasons": reasons,
        "signals": signals[:10],
        "scores": {"business": round(own_score + inherited, 2),
                   "human": round(human_score, 2),
                   "automated": round(auto_score, 2),
                   "relationship": round(rel_score, 2)},
        "method": "deterministic",
    })

    if llm is not None and result["confidence"] < 0.75:
        # Layered cost (§performance): the model is a second opinion for the
        # UNSURE middle. A verdict the deterministic layer is confident about
        # (unambiguous marketing at 0.9+, obvious business at 0.9+) never
        # spends an LLM call - that is what makes the expensive layer usable
        # on a whole mailbox.
        merged = _llm_review(llm, subject, body, thread_context, result)
        if merged is not None:
            return merged
    return result


LLM_CLASSIFY_SYSTEM = """You judge whether an email belongs in a company's \
business-relationship memory. Answer in JSON only.

Return: {"classification": "...", "confidence": 0.0-1.0, "business_type": "...",
"reasons": ["..."], "signals": ["..."]}

classification is one of BUSINESS_RELEVANT, POSSIBLY_BUSINESS, NON_BUSINESS,
AUTOMATED_NOISE.
business_type is one of CUSTOMER, PROSPECT, SUPPLIER, VENDOR, PARTNER, CONTRACT,
NEGOTIATION, PROJECT, FINANCE, LEGAL, EMPLOYEE, PROFESSIONAL_CONTACT,
OTHER_BUSINESS, or null.

BUSINESS_RELEVANT means the message carries information about a real commercial
or professional relationship: negotiations, pricing, contracts, projects,
requirements, complaints, partnerships, payment disputes, substantive meeting
outcomes.

AUTOMATED_NOISE means a platform generated it and it says nothing about a
relationship: newsletters, marketing, receipts, shipping and order notifications,
password resets, security alerts, social and developer-platform notifications.

Judge the CONTENT, not the sender's domain. A negotiation with a supplier hosted
on a large marketplace is business; that marketplace's order notification is not.
A genuine contract discussion sent from a no-reply address is still business.

A short reply inside a commercial thread inherits that thread's relevance."""


def _llm_review(llm, subject, body, thread_context, deterministic):
    """Ask a model to judge, then bound its answer with deterministic evidence.
    A model failure must never block ingestion, so errors fall back silently."""
    try:
        raw = llm.complete(
            LLM_CLASSIFY_SYSTEM,
            f"Subject: {subject}\n\nBody:\n{body[:4000]}\n\n"
            f"Thread context:\n{(thread_context or '(none)')[:2000]}")
        data = json.loads(_strip_fence(raw))
        if not isinstance(data, dict):
            return None
        cls = data.get("classification")
        if cls not in CLASSIFICATIONS:
            return None
        try:
            conf = float(data.get("confidence", 0.5))
        except (TypeError, ValueError):
            conf = 0.5
        btype = data.get("business_type")
        if btype not in BUSINESS_TYPES:
            btype = deterministic["business_type"]
        # Guard-rail: the model may not promote mail that carries strong
        # automated evidence and no commercial content of its own.
        if (cls == "BUSINESS_RELEVANT"
                and deterministic["scores"]["automated"] >= 0.75
                and deterministic["scores"]["business"] < 0.25):
            cls = "POSSIBLY_BUSINESS"
            conf = min(conf, 0.6)
        reasons = [str(r)[:200] for r in (data.get("reasons") or [])][:5]
        signals = [str(s)[:40] for s in (data.get("signals") or [])][:10]
        return ClassificationResult({
            "classification": cls,
            "confidence": round(max(0.0, min(1.0, conf)), 2),
            "business_type": btype,
            "reasons": reasons or deterministic["reasons"],
            "signals": signals or deterministic["signals"],
            "scores": deterministic["scores"],
            "method": "llm+deterministic",
        })
    except Exception:
        return None


def _strip_fence(text: str) -> str:
    m = re.search(r"```(?:json)?\s*(.*?)```", text or "", re.S)
    return (m.group(1) if m else (text or "")).strip()


# ── persistence ────────────────────────────────────────────────────────────
CLASSIFICATION_SCHEMA = """
CREATE TABLE IF NOT EXISTS message_classifications(
  id INTEGER PRIMARY KEY AUTOINCREMENT, project_id TEXT NOT NULL,
  connector_id TEXT, source_record_id TEXT, external_id TEXT, thread_id TEXT,
  subject TEXT, sender TEXT, classification TEXT NOT NULL, confidence REAL,
  business_type TEXT, reasons TEXT, signals TEXT, method TEXT,
  entered_pipeline INTEGER NOT NULL DEFAULT 0, facts_extracted INTEGER NOT NULL DEFAULT 0,
  ts REAL NOT NULL);
CREATE INDEX IF NOT EXISTS mc_project ON message_classifications(project_id, ts);
CREATE INDEX IF NOT EXISTS mc_thread ON message_classifications(project_id, thread_id);
"""


class ClassificationStore:
    def __init__(self, db):
        self.db = db
        db.executescript(CLASSIFICATION_SCHEMA)
        db.commit()

    def record(self, project_id, connector_id, source_record_id, payload,
               result, entered_pipeline, facts=0):
        self.db.execute(
            "INSERT INTO message_classifications(project_id,connector_id,source_record_id,"
            "external_id,thread_id,subject,sender,classification,confidence,business_type,"
            "reasons,signals,method,entered_pipeline,facts_extracted,ts) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (project_id, connector_id, source_record_id,
             payload.get("message_id") or payload.get("external_id"),
             payload.get("thread_id"), (payload.get("subject") or "")[:300],
             payload.get("from", "")[:200], result["classification"],
             result["confidence"], result["business_type"],
             json.dumps(result["reasons"]), json.dumps(result["signals"]),
             result.get("method", "deterministic"),
             1 if entered_pipeline else 0, facts, time.time()))
        self.db.commit()

    def set_facts(self, source_record_id, facts):
        self.db.execute(
            "UPDATE message_classifications SET facts_extracted=? WHERE source_record_id=?",
            (facts, source_record_id))
        self.db.commit()

    def summary(self, project_id, connector_id=None):
        q = ("SELECT classification, COUNT(*) n, SUM(facts_extracted) f "
             "FROM message_classifications WHERE project_id=?")
        args = [project_id]
        if connector_id:
            q += " AND connector_id=?"
            args.append(connector_id)
        q += " GROUP BY classification"
        rows = self.db.execute(q, args).fetchall()
        out = {c: 0 for c in CLASSIFICATIONS}
        facts = 0
        for r in rows:
            out[r["classification"]] = r["n"]
            facts += (r["f"] or 0)
        threads = self.db.execute(
            "SELECT COUNT(DISTINCT thread_id) t FROM message_classifications WHERE project_id=?"
            + (" AND connector_id=?" if connector_id else ""), args).fetchone()
        return {"by_classification": out,
                "messages_scanned": sum(out.values()),
                "threads": threads["t"] if threads else 0,
                "facts_extracted": facts}

    def list(self, project_id, classification=None, limit=100):
        q = ("SELECT * FROM message_classifications WHERE project_id=?")
        args = [project_id]
        if classification:
            q += " AND classification=?"
            args.append(classification)
        q += " ORDER BY id DESC LIMIT ?"
        args.append(limit)
        out = []
        for r in self.db.execute(q, args):
            d = dict(r)
            d["reasons"] = json.loads(d["reasons"] or "[]")
            d["signals"] = json.loads(d["signals"] or "[]")
            out.append(d)
        return out

    def for_source(self, source_record_id):
        r = self.db.execute(
            "SELECT * FROM message_classifications WHERE source_record_id=? ORDER BY id DESC LIMIT 1",
            (source_record_id,)).fetchone()
        if not r:
            return None
        d = dict(r)
        d["reasons"] = json.loads(d["reasons"] or "[]")
        d["signals"] = json.loads(d["signals"] or "[]")
        return d


def thread_context_for(db, project_id, thread_id, exclude_source_id=None, limit=12) -> str:
    """Concatenate sibling messages in the same Gmail thread, so a short reply is
    judged in the conversation it belongs to. Uses the indexed thread_id column,
    never scans the whole source table."""
    if not thread_id:
        return ""
    rows = db.execute(
        "SELECT id, payload FROM source_records "
        "WHERE project_id=? AND thread_id=? ORDER BY id DESC LIMIT ?",
        (project_id, thread_id, limit + 1)).fetchall()
    parts = []
    for r in rows:
        if exclude_source_id and r["id"] == exclude_source_id:
            continue
        try:
            p = json.loads(decrypt_content(r["payload"]))
        except Exception:
            continue
        parts.append(f"{p.get('subject','')} {p.get('body','')}"[:1500])
        if len(parts) >= limit:
            break
    return "\n---\n".join(parts)


def relationship_history(db, project_id, counterparty_email: str) -> dict:
    """Historical interaction with one address. Inbound mail is an indexed
    from_addr lookup; outbound (they appear in To) uses a SQLite-side substring
    pre-filter so Python never JSON-parses the whole mailbox."""
    if not counterparty_email:
        return {}
    counterparty_email = counterparty_email.lower()
    count, threads, inbound, outbound = 0, {}, 0, 0
    # inbound: exact indexed match on the sender column
    for r in db.execute(
            "SELECT thread_id FROM source_records "
            "WHERE project_id=? AND from_addr=? ORDER BY id DESC LIMIT 400",
            (project_id, counterparty_email)):
        count += 1
        inbound += 1
        if r["thread_id"]:
            threads[r["thread_id"]] = threads.get(r["thread_id"], 0) + 1
    # outbound: the address appears in the payload's To.
    #
    # Normally pre-filtered in C with LIKE, parsing only the small candidate set.
    # That is impossible once the column is encrypted - ciphertext contains no
    # substring of the plaintext, so the LIKE would match nothing and this would
    # report zero outbound messages while looking like it worked. So when
    # encryption is on, the filter moves into Python: more rows are read and each
    # is decrypted, which is slower, and the scan is bounded so it stays bounded.
    if content_encryption_enabled():
        rows = db.execute(
            "SELECT payload, thread_id FROM source_records "
            "WHERE project_id=? AND (from_addr IS NULL OR from_addr!=?) "
            "ORDER BY id DESC LIMIT 2000",
            (project_id, counterparty_email))
    else:
        like = f'%{counterparty_email}%'
        rows = db.execute(
            "SELECT payload, thread_id FROM source_records "
            "WHERE project_id=? AND (from_addr IS NULL OR from_addr!=?) AND payload LIKE ? "
            "ORDER BY id DESC LIMIT 200",
            (project_id, counterparty_email, like))
    for r in rows:
        try:
            p = json.loads(decrypt_content(r["payload"]))
        except Exception:
            continue
        if counterparty_email not in (p.get("to") or "").lower():
            continue
        count += 1
        outbound += 1
        tid = r["thread_id"] or p.get("thread_id")
        if tid:
            threads[tid] = threads.get(tid, 0) + 1
    return {"message_count": count,
            "two_way": inbound > 0 and outbound > 0,
            "max_thread_depth": max(threads.values()) if threads else 0}
