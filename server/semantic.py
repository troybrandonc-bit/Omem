"""Semantic email understanding: the LLM reads the WHOLE email like a person.

Layer architecture (the engine remains the only authority):

  1 deterministic pre-filter   (only removes very-high-confidence noise)
  2 normalization + identity   (participants, roles, thread, existing memory)
  3 LLM semantic analysis      (this module: full email + full context)
  4 candidate validation       (schema, entity allow-list, exact evidence)
  5 frozen OMEM engine         (assert / supersede / contradict)
  6 provenance + storage
  7 UI (diagnostics, why-view)

The LLM PROPOSES structured candidates; every proposal is validated against
the actual stored email before the engine ever sees it:

  * evidence quotes must be EXACT substrings of the stored message
  * actors/subjects must come from the allow-list built from the real
    participants + configured identity + known entities (no invented people)
  * propositions must be valid slugs; speech acts from the fixed ladder
  * questions / marketing CTAs never become facts, whatever the model says

Without an LLM credential the deterministic ContextualBusinessExtractor is
the fallback; that path is what most tests exercise. The REAL provider path
requires OMEM_LLM_API_KEY and is exercised through the same interface.
"""
from __future__ import annotations
import json
import re
import time

from ingest import Extractor
from email_analysis import parse_participants, normalize_identity, SPEECH_ACTS
from extraction import (ContextualBusinessExtractor, canonical_proposition,
                        strip_quoted, SUPERSEDES)

_VALID_PROP = re.compile(r"^(not:)?[a-z][a-z0-9_]{2,63}$")
_VALID_ENTITY = re.compile(r"^(company|customer|person|self):[a-z0-9][a-z0-9_.@-]{0,80}$")

SEMANTIC_SYSTEM = """You are the semantic analyst of a business relationship-memory system.
You read ONE email (with its thread and context) the way a sharp executive assistant would,
and decide what — if anything — deserves to become durable relationship memory.

Return ONLY a JSON object, no prose, matching exactly:

{
  "business_relevance": "high" | "medium" | "low" | "none",
  "memory_candidate": true | false,
  "rejection_reason": null | "non_business" | "marketing" | "automated_notification"
                    | "temporary_context" | "insufficient_evidence" | "irrelevant"
                    | "ambiguous" | "duplicate",
  "reasoning_summary": "<one or two sentences, no hidden reasoning>",
  "candidates": [
    {
      "memory_type": "<e.g. customer_decision, supplier_terms, self_intent>",
      "actor": "<entity id from ALLOWED ENTITIES>",
      "subject": "<entity id from ALLOWED ENTITIES>",
      "proposition": "<snake_case fact, e.g. decided_to_renew, unit_price_usd_3_90>",
      "speech_act": "QUESTION"|"REQUEST"|"SUGGESTION"|"CONSIDERATION"|"INTENTION"
                   |"DECISION"|"COMPLETED"|"STATEMENT",
      "certainty": "high"|"medium"|"low",
      "temporal_status": "current"|"past"|"future",
      "relation": null | {"name": "works_at"|"uses"|"managed_by"|"reports_to"|"partner_of",
                          "target": "<entity id from ALLOWED ENTITIES, or product:<name-in-email>>"},
      "evidence": [{"quote": "<EXACT verbatim substring of the email body or subject>"}],
      "confidence": 0.0-1.0,
      "existing_memory_relationship": null | {
          "relation": "supersedes"|"confirms"|"contradicts",
          "target_proposition": "<proposition of the existing memory>"
      }
    }
  ]
}

Hard rules:
- The writer of the email is the ACTOR of first-person statements. If the writer is
  the account owner (SELF), first-person intents are about the OWNER's organisation,
  never about a customer.
- "you/your" statements written BY the owner concern the counterparty; written TO the
  owner by a platform they concern the owner (usually not memory).
- Questions, suggestions and marketing calls-to-action are never facts.
- Requests become requested_*; considerations considering_*; intentions intends_to_*;
  decisions decided_to_*; completed actions has_*.
- Only durable, future-useful relationship information is memory. "I'll send the PDF
  in five minutes" is not memory. Payment terms, contract values, renewal decisions,
  churn risk, preferences ARE memory.
- Every candidate MUST quote exact verbatim evidence from THIS email. If you cannot
  quote it, do not propose it.
- Use ONLY entity ids from ALLOWED ENTITIES. Never invent people or companies.
- If existing memories are shown and this email changes one, set
  existing_memory_relationship accordingly.
- Ignore quoted/forwarded earlier messages: judge only what THIS sender wrote."""


def build_semantic_input(payload: dict, participants: dict, identity: dict,
                         sender_role: str | None, thread_context: str,
                         existing_memories: list[dict],
                         allowed_entities: list[dict]) -> str:
    """The full context pack. The complete cleaned body is always included —
    context is trimmed around it, never the email itself."""
    lines = []
    lines.append("=== EMAIL ===")
    lines.append(f"From: {payload.get('from', '')}")
    lines.append(f"To: {payload.get('to', '')}")
    cc = (payload.get("headers") or {}).get("cc") or (payload.get("headers") or {}).get("Cc")
    if cc:
        lines.append(f"Cc: {cc}")
    lines.append(f"Date: {payload.get('date', payload.get('at', ''))}")
    lines.append(f"Subject: {payload.get('subject', '')}")
    lines.append(f"Message-Id: {payload.get('message_id') or payload.get('external_id', '')}")
    lines.append(f"Thread-Id: {payload.get('thread_id', '')}")
    lines.append("")
    lines.append(strip_quoted(payload.get("body") or ""))
    lines.append("")
    lines.append("=== WHO IS US (the account owner's organisation) ===")
    lines.append(f"Company: {identity.get('company_name') or 'unknown'}")
    lines.append(f"Our domains: {', '.join(identity.get('domains') or []) or 'none configured'}")
    lines.append(f"Our addresses: {', '.join(identity.get('emails') or []) or 'none'}")
    lines.append(f"Direction of this email: {participants.get('direction')}"
                 + (" (the WRITER IS US)" if participants.get("direction") == "outbound" else ""))
    if participants.get("counterparty_email"):
        role_txt = f" — user-confirmed role: {sender_role}" if sender_role else ""
        lines.append(f"Counterparty: {participants['counterparty_email']}{role_txt}")
    if participants.get("internal"):
        lines.append("This is INTERNAL mail (both sides are our organisation).")
    lines.append("")
    lines.append("=== ALLOWED ENTITIES (use ONLY these ids) ===")
    for e in allowed_entities:
        lines.append(f"- {e['id']}  ({e.get('label', '')})")
    if existing_memories:
        lines.append("")
        lines.append("=== EXISTING MEMORIES ABOUT THESE ENTITIES ===")
        for m in existing_memories[:20]:
            lines.append(f"- {m['subject']} {m['proposition']} "
                         f"(currently believed since t={m.get('since', '?')})")
    if thread_context:
        lines.append("")
        lines.append("=== EARLIER MESSAGES IN THIS THREAD (context only) ===")
        lines.append(thread_context[:6000])
    return "\n".join(lines)


def allowed_entities_for(participants: dict, identity: dict) -> list[dict]:
    """The closed set of entities the model may attribute facts to. Built from
    REAL participants + the configured identity — the anti-invention boundary."""
    out, seen = [], set()

    def add(eid, label):
        if eid and eid not in seen and _VALID_ENTITY.match(eid):
            seen.add(eid)
            out.append({"id": eid, "label": label})

    # SELF organisation
    name = identity.get("company_name")
    dom = next(iter(sorted(identity.get("domains") or [])), None) or \
        (participants.get("owner_domain") or "")
    if name:
        add("company:" + re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_"),
            f"{name} (our company)")
    elif dom and dom not in ("gmail.com", "hotmail.com", "outlook.com", "yahoo.com"):
        add("company:" + re.sub(r"[^a-z0-9]+", "-", dom.split(".")[0].lower()),
            f"{dom} (our company)")

    # counterparty organisation / person
    counter = participants.get("counterparty_email") or ""
    cdom = participants.get("counterparty_domain") or ""
    if counter:
        if cdom in ("gmail.com", "hotmail.com", "outlook.com", "yahoo.com",
                    "icloud.com", "googlemail.com"):
            add(f"customer:{counter.split('@')[0]}", f"Customer {counter}")
        elif cdom:
            add("company:" + re.sub(r"[^a-z0-9]+", "-", cdom.split(".")[0].lower()),
                cdom)
        # named third parties at the counterparty: person:<first>@<orgslug>
        # (the model may only use ones it can QUOTE a first name for; validation
        # re-checks the name appears in the email)
        if cdom:
            add(f"person:any@{cdom.split('.')[0]}",
                f"a NAMED person at {cdom} — replace 'any' with their lowercase first name")
    return out


class SemanticValidationError(Exception):
    pass


def validate_semantic_output(raw: str, payload: dict,
                             allowed: list[dict]) -> dict:
    """Strict validation. Anything invalid is DROPPED with a recorded reason —
    never partially trusted."""
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.S)
    try:
        data = json.loads(text)
    except Exception as e:
        raise SemanticValidationError(f"model returned non-JSON: {e}")
    if not isinstance(data, dict):
        raise SemanticValidationError("model output is not an object")

    allowed_ids = {e["id"] for e in allowed}
    body = strip_quoted(payload.get("body") or "")
    haystack = f"{payload.get('subject') or ''}\n{body}"
    hay_norm = re.sub(r"\s+", " ", haystack)

    out = {
        "business_relevance": str(data.get("business_relevance") or "none"),
        "memory_candidate": bool(data.get("memory_candidate")),
        "rejection_reason": data.get("rejection_reason"),
        "reasoning_summary": str(data.get("reasoning_summary") or "")[:500],
        "candidates": [],
        "dropped": [],
    }
    if out["business_relevance"] not in ("high", "medium", "low", "none"):
        out["business_relevance"] = "none"

    for c in (data.get("candidates") or [])[:12]:
        if not isinstance(c, dict):
            continue
        drop = None
        prop = str(c.get("proposition") or "").strip()
        act = str(c.get("speech_act") or "").strip()
        actor = str(c.get("actor") or "").strip()
        subject = str(c.get("subject") or "").strip()
        quotes = [str(q.get("quote") or "").strip()
                  for q in (c.get("evidence") or []) if isinstance(q, dict)]
        quotes = [q for q in quotes if q]

        if not _VALID_PROP.match(prop):
            drop = f"invalid proposition {prop!r}"
        elif act not in SPEECH_ACTS:
            drop = f"invalid speech act {act!r}"
        elif act in ("QUESTION", "MARKETING_CTA", "SUGGESTION"):
            drop = f"{act} never becomes a fact"
        elif not quotes:
            drop = "no evidence quote"
        else:
            # exact-substring evidence against the REAL stored email
            for q in quotes:
                if q not in haystack and re.sub(r"\s+", " ", q) not in hay_norm:
                    drop = f"evidence not found verbatim in the stored email: {q[:60]!r}"
                    break
        if drop is None:
            # entity allow-list (person:any@org is a template: accept
            # person:<name>@org only when <name> appears in the email)
            def entity_ok(eid):
                if eid in allowed_ids:
                    return True
                m = re.match(r"^person:([a-z]+)@([a-z0-9-]+)$", eid)
                if m and f"person:any@{m.group(2)}" in allowed_ids:
                    return m.group(1) in haystack.lower()
                return False
            if not entity_ok(subject):
                drop = f"subject {subject!r} is not an allowed entity"
            elif actor and not entity_ok(actor):
                drop = f"actor {actor!r} is not an allowed entity"
        try:
            conf = max(0.0, min(1.0, float(c.get("confidence", 0.5))))
        except (TypeError, ValueError):
            conf = 0.5
        if drop is None and conf < 0.4:
            drop = f"confidence too low ({conf})"

        relation_out = None
        relc = c.get("relation")
        if drop is None and isinstance(relc, dict) and relc.get("name") and relc.get("target"):
            from graph import RELATIONS as _RELS
            tgt = str(relc["target"])
            tname = tgt.split(":", 1)[-1] if ":" in tgt else ""
            ok_t = entity_ok(tgt) or (tgt.startswith("product:")
                                      and tname and tname in haystack.lower())
            if relc["name"] in _RELS and ok_t:
                relation_out = {"name": relc["name"], "target": tgt}
        if drop is None and relation_out is None and \
                str(c.get("proposition") or "").startswith("rel_"):
            # a rel_* proposition IS its relation: without an evidenced,
            # allow-listed target the whole candidate is a hallucination
            drop = "relation_target_not_evidenced"
        rel = c.get("existing_memory_relationship")
        rel_ok = None
        if isinstance(rel, dict) and rel.get("relation") in ("supersedes", "confirms", "contradicts"):
            tp = str(rel.get("target_proposition") or "")
            if _VALID_PROP.match(tp):
                rel_ok = {"relation": rel["relation"], "target_proposition": tp}

        if drop:
            out["dropped"].append({"proposition": prop, "reason": drop})
            continue
        out["candidates"].append({
            "relation": relation_out,
            "memory_type": str(c.get("memory_type") or "")[:60],
            "actor": actor or subject,
            "subject": subject,
            "proposition": canonical_proposition(prop),
            "speech_act": act,
            "certainty": c.get("certainty") if c.get("certainty") in ("high", "medium", "low") else "medium",
            "temporal_status": c.get("temporal_status") if c.get("temporal_status") in ("current", "past", "future") else "current",
            "evidence_quote": quotes[0][:300],
            "confidence": conf,
            "existing_memory_relationship": rel_ok,
        })
    return out


class SemanticGmailExtractor(Extractor):
    """Pipeline-facing extractor: LLM analysis primary, deterministic extractor
    as the guard/fallback. Context fetchers are injected so this module stays
    free of app globals."""

    def __init__(self, llm_client, owner_identity, *,
                 role_lookup=None, thread_lookup=None, memories_lookup=None,
                 analysis_sink=None, fallback: Extractor | None = None):
        self.client = llm_client
        self.identity = normalize_identity(owner_identity) if not isinstance(owner_identity, dict) \
            or "emails" not in owner_identity or not isinstance(owner_identity.get("emails"), set) \
            else owner_identity
        # keep the raw dict form for prompt building
        self._identity_raw = owner_identity if isinstance(owner_identity, dict) else \
            {"company_name": None, "emails": [owner_identity] if owner_identity else [], "domains": []}
        self.role_lookup = role_lookup or (lambda email: None)
        self.thread_lookup = thread_lookup or (lambda thread_id, external_id: "")
        self.memories_lookup = memories_lookup or (lambda entity_ids: [])
        self.analysis_sink = analysis_sink or (lambda payload, analysis, raw: None)
        self.fallback = fallback

    def extract(self, payload: dict) -> list[dict]:
        pp = parse_participants(payload, self._identity_raw)
        allowed = allowed_entities_for(pp, self._identity_raw
                                        if isinstance(self._identity_raw, dict)
                                        else {"company_name": None, "domains": [], "emails": []})
        entity_ids = [e["id"] for e in allowed if not e["id"].startswith("person:any@")]
        existing = self.memories_lookup(entity_ids) or []
        thread_ctx = self.thread_lookup(payload.get("thread_id"),
                                        payload.get("external_id")) or ""
        sender_role = self.role_lookup(pp.get("counterparty_email"))
        user_input = build_semantic_input(payload, pp, self._identity_raw
                                          if isinstance(self._identity_raw, dict)
                                          else {"company_name": None, "domains": [],
                                                "emails": []},
                                          sender_role, thread_ctx, existing, allowed)
        raw = self.client.complete(SEMANTIC_SYSTEM, user_input)
        try:
            analysis = validate_semantic_output(raw, payload, allowed)
        except SemanticValidationError as e:
            # A malformed model response must not silently drop mail: fall back
            # to the deterministic extractor and record why.
            self.analysis_sink(payload, {"error": str(e)}, raw)
            if self.fallback is not None:
                return self.fallback.extract(payload)
            raise
        self.analysis_sink(payload, analysis, raw)

        facts = []
        seen = set()
        for c in analysis["candidates"]:
            key = (c["subject"], c["proposition"])
            if key in seen:
                continue
            seen.add(key)
            label_map = {e["id"]: e.get("label") for e in allowed}
            subj_label = label_map.get(c["subject"]) or c["subject"].split(":", 1)[1]
            etype = "organization" if c["subject"].startswith("company:") else "person"
            facts.append({
                "subject": {"id": c["subject"], "type": etype, "label": subj_label},
                "proposition": c["proposition"],
                "confidence": c["confidence"],
                "event_kind": "email",
                "event_time": payload.get("at", "now"),
                "label": (payload.get("subject") or "message")[:80] + " \u2192 " + c["proposition"],
                "evidence": f'"{c["evidence_quote"]}"',
                "speech_act": c["speech_act"],
                "sentence_party": "semantic",
                "memory_type": c["memory_type"],
                "certainty": c["certainty"],
                "reasoning_summary": analysis["reasoning_summary"],
                "business_relevance": analysis["business_relevance"],
                "existing_memory_relationship": c["existing_memory_relationship"],
                "relation": (c.get("relation") or {}).get("name"),
                "relation_target": ({"id": c["relation"]["target"],
                                     "type": "product" if c["relation"]["target"].startswith("product:")
                                     else "person" if c["relation"]["target"].startswith("person:")
                                     else "organization",
                                     "label": c["relation"]["target"].split(":", 1)[-1]}
                                    if c.get("relation") else None),
            })
        return facts


SEMANTIC_ANALYSES_SCHEMA = """
CREATE TABLE IF NOT EXISTS semantic_analyses(
  id INTEGER PRIMARY KEY AUTOINCREMENT, project_id TEXT NOT NULL,
  source_record_id TEXT NOT NULL, business_relevance TEXT,
  memory_candidate INTEGER, rejection_reason TEXT, reasoning_summary TEXT,
  candidates INTEGER, dropped TEXT, model TEXT, error TEXT, ts REAL NOT NULL);
CREATE INDEX IF NOT EXISTS sa_source ON semantic_analyses(source_record_id);
CREATE INDEX IF NOT EXISTS sa_project ON semantic_analyses(project_id, ts);
"""
