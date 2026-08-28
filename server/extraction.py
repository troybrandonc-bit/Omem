"""Context-aware extraction: turns understood email into candidate facts.

Replaces keyword-spotting with a pipeline that mirrors how an assistant reads:

  sentence -> speech act -> whose action is it -> is it durable -> propose

Rules enforced here (from the product brief):
  * Questions, marketing CTAs and suggestions NEVER become flat facts.
  * Requests become requested_*; considerations considering_*; only decisions,
    completed actions and plain statements are strong.
  * The proposition's SUBJECT is whoever the sentence is about, not blindly
    the sender. Inbound "we want to cancel" is about the counterparty; the
    owner's outbound "we've extended your subscription" is about the owner's
    action on the counterparty's account; "John has approved" is about John.
  * Second-person template mail ("Your trial has started") yields nothing.
  * Every fact carries a verbatim evidence sentence.
  * A quality decision (HIGH/MEDIUM/LOW/DO_NOT_STORE) is attached BEFORE the
    engine sees anything; DO_NOT_STORE and LOW never become assertions.

Above the frozen engine only: this module proposes; the engine decides.
"""
from __future__ import annotations
import re
from email_analysis import (split_sentences, speech_act, sentence_party,
                            ACT_POLICY, analyze, parse_participants)
from ingest import Extractor

# ── the actions we understand in the subscription/commercial domain ────────
# verb -> canonical action token used to build propositions. Ordered most
# specific first: "move to annual billing from next renewal" must match the
# billing preference, not the incidental "renewal" time reference.
_ACTIONS = [
    (r"switch(?:ing|ed)?\s+to\s+annual|mov(?:e|ing|ed)\s+to\s+(?:the\s+)?annual|annual(?:ly)?\s+billing|facturaci[oó]n anual", "annual_billing"),
    (r"switch(?:ing|ed)?\s+to\s+monthly|stay(?:ing)?\s+(?:on\s+)?monthly|monthly\s+billing|facturaci[oó]n mensual", "monthly_billing"),
    (r"cancell?(?:ing|ation|ed)?|terminat\w*|cancelar|cancelado|cancelamos", "cancel"),
    # "renewal" preceded by next/the/at/until/our is a point in time, not an action
    (r"renew(?:ing|ed|s)?\b|(?<!next )(?<!the )(?<!our )(?<!at )renewal\b|renovar|renovado|renovamos|renovaci[oó]n del contrato", "renew"),
    (r"extend(?:ing|ed)?\b|extender|ampliar el (?:contrato|acuerdo)", "extend"),
    (r"upgrad(?:e|ing|ed)\b|mejorar el plan|subir (?:de|al) plan", "upgrade"),
    (r"downgrad(?:e|ing|ed)\b|bajar (?:de|al) plan", "downgrade"),
    (r"expand(?:ing|ed)?\b|expansion\b|ampliar(?:emos)? (?:a|en|la producci)", "expand"),
    (r"approv(?:e|ed|ing|al)\b|aprobar|aprobado", "approve"),
    (r"sign(?:ed|ing)?\s+(?:the\s+)?(?:contract|agreement|amendment|off)\b|firmar|firmado|firmamos", "sign"),
]

# canonical proposition families: variants that mean the same durable fact map
# to one canonical form so the engine never receives four spellings of one idea
_CANONICAL = {
    "prefers_annual_billing": "prefers_annual_billing",
    "wants_annual_billing": "prefers_annual_billing",
    "would_like_annual_billing": "prefers_annual_billing",
    "interested_in_annual_billing": "prefers_annual_billing",
    "intends_to_annual_billing": "prefers_annual_billing",
    "decided_to_annual_billing": "prefers_annual_billing",
    "prefers_monthly_billing": "prefers_monthly_billing",
    "decided_to_monthly_billing": "prefers_monthly_billing",
    "intends_to_monthly_billing": "prefers_monthly_billing",
}


def canonical_proposition(prop: str) -> str:
    return _CANONICAL.get(prop, prop)


_VALID_PROP = re.compile(r"^(not:)?[a-z][a-z0-9_]{2,63}$")


def _slug(v: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", (v or "").lower()).strip("_")
    return re.sub(r"_+", "_", s)[:40]


# A free-mail address names a person, never an organisation. Deciding this in
# one place because three separate copies of the list is how they stop agreeing.
FREE_MAIL = frozenset({
    "gmail.com", "hotmail.com", "outlook.com", "yahoo.com", "icloud.com",
    "googlemail.com",
})

# Addresses a company sends FROM, not addresses a person has. An inference that
# "Support works at Acme" is noise that never stops being wrong.
ROLE_LOCALS = frozenset({
    "noreply", "no-reply", "donotreply", "do-not-reply", "bounce", "bounces",
    "mailer-daemon", "postmaster", "abuse", "security", "support", "help",
    "helpdesk", "info", "hello", "hi", "contact", "enquiries", "inquiries",
    "sales", "billing", "accounts", "accounting", "invoices", "admin",
    "team", "office", "notifications", "notification", "alerts", "news",
    "newsletter", "marketing", "careers", "jobs", "hr", "recruiting",
    "service", "customerservice", "success", "feedback", "orders",
})

# The same words in a DISPLAY name. "Acme Support" is two capitalised words and
# would otherwise pass for a person.
ROLE_WORDS = frozenset({
    "support", "team", "sales", "billing", "info", "admin", "notifications",
    "service", "success", "marketing", "accounts", "accounting", "security",
    "careers", "jobs", "help", "helpdesk", "desk", "hr", "office", "news",
    "newsletter", "alerts", "noreply", "mail", "mailer", "bot", "system",
    "customer", "care", "group", "department", "dept", "inc", "ltd", "llc",
    "gmbh", "corp", "company", "the",
})

# Lowercase particles that are part of a name, not a word in a sentence.
# Without these "Maria de Souza Lima" and "Ludwig van Beethoven" fail a
# capitalised-words test, which would quietly make this work for English names
# and not for most others.
NAME_PARTICLES = frozenset({
    "de", "del", "dela", "della", "der", "den", "des", "di", "da", "do",
    "dos", "das", "du", "la", "le", "lo", "van", "von", "ter", "ten", "af",
    "av", "bin", "ibn", "al", "el", "mc", "mac", "op", "in", "'t", "y", "e",
})


def _name_shaped(part: str) -> bool:
    """A capitalised word made of letters, apostrophes and hyphens.

    Deliberately not a regex over [A-Za-z]: that spells "works for English
    names", and would refuse María, Gómez, Müller and Škoda while accepting
    Smith. isupper()/isalpha() are Unicode-aware and cost nothing.
    """
    core = part.rstrip(".")
    if not core or len(core) > 20 or not core[0].isupper():
        return False
    return all(c.isalpha() or c in "'’-" for c in core)


def _looks_like_person(name: str) -> bool:
    """One to four name-shaped words, no role vocabulary.

    Capitalisation is required on purpose. _name() falls back to the local part
    of the address when a message carries no display name, so "sarah@acme.com"
    arrives as "sarah" and is refused: we claim employment only when a human
    actually presented themselves by name. Particles are the exception, and the
    first word must still be a capitalised name.
    """
    parts = (name or "").replace(",", " ").split()
    if not 1 <= len(parts) <= 4:
        return False
    if any(p.lower().strip(".") in ROLE_WORDS for p in parts):
        return False
    if not _name_shaped(parts[0]):
        return False
    return all(_name_shaped(p) or p.lower() in NAME_PARTICLES
               for p in parts[1:])


def infer_employment(pp: dict) -> dict | None:
    """A person wrote from a company address, so they work there.

    This is the one relation between a memory and a PERSON that is derivable
    from data OMEM already resolves and was throwing away. Every party in
    _subject_for() collapses to a company, so an email from sarah@acme.com
    became memories about company:acme and Sarah was never a node at all.
    Nothing linked the human to the organisation, which left the graph too
    sparse for traversal to be worth much.

    It is an INFERENCE, not something anyone said, and it is recorded as one:
    the fact carries dkind="inference" so /why distinguishes what was read in a
    message from what was concluded from an address. It is defeasible like any
    other belief -- the same person writing later from another company yields a
    competing works_at that supersession and contradiction handle normally.

    Deliberately conservative, in the spirit of the rest of this module:

      inbound only            outbound mail carries the recipient's address but
                              rarely their name, so there is nothing to name
      never internal          a colleague is the owner's own org chart, which
                              needs configured identity to be about anyone
      never free-mail         gmail.com is not an employer
      never a role address    support@ and noreply@ are not people
      a real display name     capitalised, no role words

    Returns a fact dict in exactly the shape extract_relations() produces, so
    both ingest paths turn it into a two-subject assertion and an edge with no
    special casing anywhere downstream.
    """
    if pp.get("direction") != "inbound" or pp.get("internal"):
        return None
    email = (pp.get("counterparty_email") or "").lower()
    dom = (pp.get("counterparty_domain") or "").lower()
    if not email or "@" not in email or not dom or dom in FREE_MAIL:
        return None
    local = email.split("@", 1)[0]
    if local in ROLE_LOCALS or any(local.startswith(r + "+") for r in ROLE_LOCALS):
        return None
    name = (pp.get("sender_name") or "").strip()
    if not _looks_like_person(name):
        return None

    slug = re.sub(r"[^a-z0-9]+", "-", dom.split(".")[0].lower())
    # "Acme" writing from acme.com is the company signing its own mail.
    if any(_slug(part) == _slug(slug) for part in name.split()):
        return None

    # Same id shape as the third_party person in _subject_for(), so a human
    # mentioned in a body and a human who wrote the mail are ONE node.
    person = {"id": f"person:{_slug(name)}@{dom.split('.')[0]}",
              "type": "person", "label": name}
    company = {"id": f"company:{slug}", "type": "organization", "label": dom}
    return {
        "subject": person,
        "proposition": f"rel_works_at_{company['id'].split(':', 1)[1]}",
        "relation": "works_at",
        "relation_target": company,
        # Below the 0.75 the explicit relation patterns carry: an address is
        # good evidence of employment and not as good as someone saying so.
        "confidence": 0.7,
        "event_kind": "email",
        "speech_act": "STATEMENT",
        "sentence_party": "relation",
        "dkind": "inference",
        "evidence": f'wrote from {email} ("{name}")',
        "label": f"{name} works at {dom}",
    }


# value-bearing statement patterns (unchanged in spirit from BusinessFactExtractor
# but only applied to STATEMENT/DECISION/COMPLETED sentences)
_VALUE_PATTERNS = [
    (r"(?:contract|agreement)\b[^.]{0,60}?\b(?:will be|is|at)\s*((?:EUR|USD|GBP|€|\$|£)\s?[\d.,]+)",
     "contract_value_{v}", 0.9),
    (r"\bpayment terms?\b[^.]{0,30}?\b(net\s?\d{1,3})", "payment_terms_{v}", 0.88),
    (r"\bunit price\b[^.]{0,30}?((?:EUR|USD|GBP|€|\$|£)\s?[\d.,]+)", "unit_price_{v}", 0.88),
    (r"\blead time\b[^.]{0,30}?(\d{1,3}\s*(?:days?|weeks?))", "lead_time_{v}", 0.85),
    (r"\b(?:MOQ|minimum order)\b[^.]{0,30}?(\d[\d.,]*)", "minimum_order_{v}", 0.85),
    (r"\brenews?\b[^.]{0,40}?\b(every\s+\w+|annually|monthly|quarterly)", "renews_{v}", 0.85),
    (r"\b(?:renewal|contract)\b[^.]{0,30}?\b(?:due|expires?)\b[^.]{0,20}?\b(January|February|March|April|May|June|July|August|September|October|November|December)\b",
     "renewal_due_{v}", 0.8),
    (r"\b(?:need|require|requires?)\b[^.]{0,25}\b(SSO|SAML|SOC ?2|ISO ?27001)\b", "requires_{v}", 0.85),
    (r"\breduce\b[^.]{0,40}?\bprice\b[^.]{0,25}?\bby\s+(\d{1,2}\s?%)", "offers_price_reduction_{v}", 0.85),
    (r"\b(\d{1,2}\s?%)\s+discount\b|\bdiscount of\s+(\d{1,2}\s?%)|\bdescuento del?\s+(\d{1,2}\s?%)", "offers_discount_{v}", 0.85),
    (r"\bprecio unitario\b[^.]{0,30}?((?:EUR|USD|€|\$)\s?[\d.,]+)", "unit_price_{v}", 0.88),
]


_QUOTED_BLOCK = re.compile(
    r"(?ms)^\s*(?:-{2,}\s*(?:Forwarded message|Original Message)\s*-{2,}.*"  # forward blocks
    r"|On .{0,80}wrote:\s*$.*"                                              # reply headers
    r"|From:\s*.+\r?\nSent:\s*.+\r?\n.*"                                    # Outlook-style header block
    r")")
_QUOTED_LINES = re.compile(r"(?m)^\s*>.*$")


def strip_quoted(body: str) -> str:
    """Remove quoted replies and forwarded originals. Extraction judges only
    what THIS sender actually wrote; quoted text belongs to its own message
    (which has its own source record if it was ingested)."""
    body = _QUOTED_BLOCK.sub("", body or "")
    body = _QUOTED_LINES.sub("", body)
    return body


# When a STRONGER fact arrives, these open WEAKER-or-opposite beliefs about the
# same subject are superseded through the engine's supersede op (never deleted):
# the customer who "was considering cancelling" and then "renewed" should show
# the renewal as current belief, with the old intent visibly closed in history.
SUPERSEDES: dict[str, tuple[str, ...]] = {
    "decided_to_renew":     ("considering_cancel", "intends_to_cancel", "requested_cancel"),
    "has_renewed":          ("considering_cancel", "intends_to_cancel", "requested_cancel",
                             "decided_to_renew", "intends_to_renew"),
    "decided_to_cancel":    ("considering_cancel", "intends_to_cancel"),
    "has_cancelled":        ("considering_cancel", "intends_to_cancel", "requested_cancel",
                             "decided_to_cancel"),
    "decided_to_downgrade": ("intends_to_cancel", "considering_cancel", "requested_cancel",
                             "intends_to_downgrade"),
    "has_downgraded":       ("decided_to_downgrade", "intends_to_downgrade"),
    "has_upgraded":         ("intends_to_upgrade", "decided_to_upgrade", "requested_upgrade"),
    "has_extended":         ("intends_to_extend", "requested_extend"),
    "has_signed":           ("intends_to_sign",),
    "prefers_annual_billing":  ("considering_annual_billing",),
    "prefers_monthly_billing": ("considering_monthly_billing",),
}


# ── P5 relationship extraction (deterministic, conservative) ────────────────
# Each pattern yields a RELATIONAL fact: two-subject engine assertion + a
# directed edge (src --relation--> dst). Person entities require a capitalised
# name in the text; products get a product: id from the captured name. The
# writer's organisation anchors the relation, so identity/direction rules
# from P0 apply unchanged.
import re as _re_p5

RELATION_PATTERNS = [
    # "we use Salesforce" / "we are using HubSpot for CRM"
    (_re_p5.compile(r"(?i:\b(?:we|our team)\s+(?:use|are using|run|rely on)\s+)"
                    r"([A-Z][A-Za-z0-9]{2,20})\b"),
     "uses", "product"),
    # "our Salesforce integration is managed by Sarah"
    (_re_p5.compile(r"(?i:\b(?:integration|account|project|rollout)s?\s+(?:is|are)\s+"
                    r"managed by\s+)([A-Z][a-z]{2,20})\b"),
     "managed_by", "person"),
    # "Sarah reports to David"
    (_re_p5.compile(r"\b([A-Z][a-z]{2,20})\s+reports to\s+([A-Z][a-z]{2,20})\b"),
     "reports_to", "person_pair"),
]


def extract_relations(sentence: str, party_entity: dict | None) -> list[dict]:
    """Relational facts anchored on the writer's organisation. Returns fact
    dicts carrying relation metadata; the pipeline turns them into two-subject
    assertions + graph edges. Conservative: no anchor entity, no relation."""
    if not party_entity:
        return []
    out = []
    for rx, relation, kind in RELATION_PATTERNS:
        m = rx.search(sentence)
        if not m:
            continue
        if kind == "product":
            name = m.group(1)
            target = {"id": f"product:{name.lower()}", "type": "product", "label": name}
            src_ent, dst_ent = party_entity, target
        elif kind == "person":
            name = m.group(1)
            target = {"id": f"person:{name.lower()}", "type": "person", "label": name}
            src_ent, dst_ent = party_entity, target
        else:  # person_pair: "A reports to B", anchored people, org context only
            a_name, b_name = m.group(1), m.group(2)
            src_ent = {"id": f"person:{a_name.lower()}", "type": "person", "label": a_name}
            dst_ent = {"id": f"person:{b_name.lower()}", "type": "person", "label": b_name}
        out.append({
            "subject": src_ent,
            "proposition": f"rel_{relation}_{dst_ent['id'].split(':', 1)[1]}",
            "relation": relation,
            "relation_target": dst_ent,
            "confidence": 0.75,
            "event_kind": "email",
            "speech_act": "STATEMENT",
            "sentence_party": "relation",
            "evidence": f'"{m.group(0)}"',
            "label": f"{src_ent.get('label') or src_ent['id']} {relation.replace('_', ' ')} "
                     f"{dst_ent.get('label') or dst_ent['id']}",
        })
    return out


class ContextualBusinessExtractor(Extractor):
    """Direction- and speech-act-aware extractor. Owner email is injected by the
    pipeline (from the connector's oauth account); without it, direction is
    unknown and attribution falls back conservatively to the counterparty of
    inbound mail only."""

    def __init__(self, owner_email: str | None = None):
        self.owner_email = owner_email

    def _self_entity(self, pp: dict) -> dict | None:
        """The owner organisation as a memory subject, only when an explicit
        identity is configured (company name or domain). Without configuration
        we refuse to guess who 'we' are."""
        name = pp.get("self_company")
        dom = pp.get("owner_domain") or ""
        if name:
            slug = _slug(name)
            return {"id": f"company:{slug}", "type": "organization",
                    "label": f"{name} (our company)"}
        if dom and dom not in FREE_MAIL:
            slug = re.sub(r"[^a-z0-9]+", "-", dom.split(".")[0].lower())
            return {"id": f"company:{slug}", "type": "organization",
                    "label": f"{dom} (our company)"}
        return None

    # ── subject resolution honouring direction & party ──────────────────
    def _subject_for(self, party: str, sentence: str, pp: dict) -> dict | None:
        """Map the sentence's grammatical party onto an entity. None = drop."""
        counter = pp.get("counterparty_email")
        counter_dom = pp.get("counterparty_domain") or ""
        direction = pp.get("direction")

        def company_of(email_or_dom: str) -> dict | None:
            dom = email_or_dom.split("@")[-1] if "@" in email_or_dom else email_or_dom
            if not dom or dom in FREE_MAIL:
                # free-mail: attach to the person, not a fictitious company
                local = email_or_dom.split("@")[0] if "@" in email_or_dom else ""
                if not local:
                    return None
                return {"id": f"customer:{local}", "type": "person",
                        "label": f"Customer {local}"}
            slug = re.sub(r"[^a-z0-9]+", "-", dom.split(".")[0].lower())
            return {"id": f"company:{slug}", "type": "organization", "label": dom}

        if party == "sender_party":
            if direction == "inbound" and counter:
                return company_of(counter)          # counterparty speaking about itself
            if direction == "outbound":
                # The owner speaking. If the action's object is the reader's
                # account ("I've extended YOUR subscription"), the durable fact
                # concerns the counterparty. Otherwise it is the owner's own
                # intent/action ("I'd like to upgrade our subscription") -
                # that becomes a memory about OUR company, never about a
                # customer, and only when an org identity is configured.
                if counter and re.search(r"\byour\b", sentence.lower()):
                    return company_of(counter)
                return self._self_entity(pp)
            if direction == "unknown" and pp.get("sender_email"):
                return company_of(pp["sender_email"])  # best effort: sender's org
            return None
        if party == "recipient_party":
            if direction == "outbound" and counter:
                return company_of(counter)          # owner writing about the counterparty
            # inbound "you/your ..." is about the OWNER - platform notifications
            # land here and must not become counterparty memory
            return None
        if party == "third_party":
            m = re.match(r"^([A-Z][a-z]+)(?: [A-Z][a-z]+)?\b", sentence.strip())
            if m and counter_dom:
                name = _slug(m.group(0))
                return {"id": f"person:{name}@{counter_dom.split('.')[0]}",
                        "type": "person",
                        "label": f"{m.group(0)} ({counter_dom})"}
            return None
        return None

    # ── main entry ──────────────────────────────────────────────────────
    def extract(self, payload: dict) -> list[dict]:
        subject_line = payload.get("subject") or ""
        body = strip_quoted(payload.get("body") or "")
        pp = parse_participants(payload, self.owner_email)

        facts: list[dict] = []
        seen: set[tuple] = set()
        last_party = None  # elliptical continuations ("Payment terms Net 30.")
                           # inherit the party of the preceding resolved sentence

        # Who wrote this, and where they work. Derived from the participants
        # rather than any sentence, so it holds for a message whose body says
        # nothing durable at all -- which is most of them. Deduplication
        # downstream (fact_fingerprints) means repeated mail from the same
        # person reinforces one memory instead of creating many.
        _emp = infer_employment(pp)
        if _emp:
            _emp["event_time"] = payload.get("at", "now")
            seen.add((_emp["subject"]["id"], _emp["proposition"]))
            facts.append(_emp)

        for sentence in split_sentences(f"{subject_line}. {body}")[:80]:
            act = speech_act(sentence)
            policy = ACT_POLICY[act]
            if not policy["store"]:
                last_party = None
                continue
            party = sentence_party(sentence, pp)
            # relation patterns are self-evidencing (explicit verb phrases,
            # capitalised names); the anchor only needs a resolvable
            # correspondence context, so grammatically ambiguous sentences
            # ("Sarah reports to David.") still qualify
            _rel_party = self._subject_for("sender_party", sentence, pp) \
                if party in ("sender_party", "third_party", "unknown") else None
            for rf in extract_relations(sentence, _rel_party):
                rf["event_time"] = payload.get("at", "now")
                key = (rf["subject"]["id"], rf["proposition"])
                if key not in seen:
                    seen.add(key)
                    facts.append(rf)
            if party == "unknown" and act == "REQUEST":
                # An imperative request ("Please cancel our contract") has no
                # grammatical subject - the REQUESTER is by definition the
                # writer. requested_* attaches to the sender's side.
                party = "sender_party"
            if party == "unknown" and last_party in ("sender_party",) and \
               act == "STATEMENT" and len(sentence) < 120:
                party = last_party  # short factual continuation of the writer's statement
            if party in ("sender_party", "recipient_party"):
                last_party = party
            subj = self._subject_for(party, sentence, pp)
            if subj is None:
                continue

            low = sentence.lower()

            # A) subscription/commercial-action facts, strength-graded.
            #    Plain STATEMENTs never yield bare action verbs: "renews every
            #    January" is a contract ATTRIBUTE (captured by the value
            #    patterns below), not anyone's act of renewing.
            if act != "STATEMENT":
                for verb_pat, action in _ACTIONS:
                    if not re.search(rf"\b(?:{verb_pat})\b", low):
                        continue
                    prefix = policy["prefix"]
                    if action in ("annual_billing", "monthly_billing"):
                        # preferences: decided/intends/requested all collapse to the
                        # canonical preference; considerations stay weak
                        prop = ("considering_" + action if act == "CONSIDERATION"
                                else "prefers_" + action)
                    elif act == "COMPLETED":
                        prop = {"cancel": "has_cancelled", "renew": "has_renewed",
                                "extend": "has_extended", "upgrade": "has_upgraded",
                                "downgrade": "has_downgraded", "expand": "has_expanded",
                                "approve": "has_approved", "sign": "has_signed"}.get(
                                    action, f"has_{action}")
                    elif prefix:
                        prop = f"{prefix}_{action}"
                    else:
                        prop = f"{action}"
                    prop = canonical_proposition(prop)
                    if not _VALID_PROP.match(prop):
                        continue
                    key = (subj["id"], prop)
                    if key in seen:
                        continue
                    seen.add(key)
                    facts.append(self._fact(subj, prop, policy["confidence"],
                                            sentence, subject_line, act, party, payload))
                    break  # one action per sentence

            # B) value-bearing plain statements
            if act in ("STATEMENT", "DECISION", "COMPLETED"):
                for pat, template, conf in _VALUE_PATTERNS:
                    m = re.search(pat, sentence, re.I)
                    if not m:
                        continue
                    value = next((g for g in reversed(m.groups() or ()) if g), "")
                    prop = template.replace("{v}", _slug(value)) if "{v}" in template else template
                    if not _VALID_PROP.match(prop):
                        continue
                    key = (subj["id"], prop)
                    if key in seen:
                        continue
                    seen.add(key)
                    facts.append(self._fact(subj, prop, conf, sentence,
                                            subject_line, act, party, payload))
        return facts

    def _fact(self, subj, prop, conf, sentence, subject_line, act, party, payload):
        return {
            "subject": subj,
            "proposition": prop,
            "confidence": conf,
            "event_kind": "email",
            "event_time": payload.get("at", "now"),
            "label": (subject_line or "message")[:80] + " \u2192 " + prop,
            "evidence": f'"{sentence[:180]}"',
            "speech_act": act,
            "sentence_party": party,
        }


# ── memory quality gate ────────────────────────────────────────────────────
QUALITY_LEVELS = ("HIGH_CONFIDENCE_MEMORY", "MEDIUM_CONFIDENCE_MEMORY",
                  "LOW_CONFIDENCE", "DO_NOT_STORE")


def memory_quality(fact: dict, analysis: dict, classification: dict | None) -> dict:
    """Decide whether a candidate fact deserves to become an assertion.
    PRECISION OVER RECALL: uncertainty lowers the grade, never raises it."""
    reasons: list[str] = []
    score = 0.0

    cat = analysis.get("category", "UNKNOWN")
    if analysis.get("saas_self_notification"):
        return {"quality": "DO_NOT_STORE", "score": 0.0,
                "reasons": ["Third-party platform notification about the owner's own account"]}
    if analysis.get("is_noise_category"):
        return {"quality": "DO_NOT_STORE", "score": 0.0,
                "reasons": [f"Source categorised as {cat}"]}
    if analysis.get("marketing_score", 0) >= 0.9:
        return {"quality": "DO_NOT_STORE", "score": 0.0,
                "reasons": ["Template/marketing mail. Commercial vocabulary is copy, not a relationship"]}

    if analysis.get("is_business_category"):
        score += 0.35
        reasons.append(f"Business category: {cat}")
    elif cat == "UNKNOWN":
        reasons.append("Category unknown, graded down")
    conf = float(fact.get("confidence") or 0)
    score += conf * 0.4
    reasons.append(f"Extraction confidence {conf:.2f} ({fact.get('speech_act', 'STATEMENT')})")

    act = fact.get("speech_act")
    if act in ("DECISION", "COMPLETED", "STATEMENT"):
        score += 0.2
        reasons.append("Strong speech act")
    elif act == "CONSIDERATION":
        score -= 0.1
        reasons.append("Consideration only, weak language")

    direction = analysis.get("participants", {}).get("direction")
    if direction in ("inbound", "outbound"):
        score += 0.1
        reasons.append(f"Direction resolved ({direction})")
    else:
        reasons.append("Owner identity unavailable, direction unknown")

    cls = (classification or {}).get("classification")
    if cls == "BUSINESS_RELEVANT":
        score += 0.1
    elif cls == "POSSIBLY_BUSINESS":
        score += 0.05
    elif cls in ("NON_BUSINESS", "AUTOMATED_NOISE"):
        return {"quality": "DO_NOT_STORE", "score": round(score, 2),
                "reasons": reasons + [f"Message classified {cls}"]}

    if score >= 0.75:
        q = "HIGH_CONFIDENCE_MEMORY"
    elif score >= 0.55:
        q = "MEDIUM_CONFIDENCE_MEMORY"
    elif score >= 0.4:
        q = "LOW_CONFIDENCE"
    else:
        q = "DO_NOT_STORE"
    return {"quality": q, "score": round(score, 2), "reasons": reasons}
