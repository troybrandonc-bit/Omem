"""Email understanding layer: who is talking to whom, about what, and how strongly.

This module sits ABOVE the frozen engine and BEFORE extraction. It answers the
questions a competent assistant asks before deciding whether a mail matters:

  - Who sent this, to whom? Is the sender the connected account's owner?
  - Is this a person writing, or a platform's template?
  - Is this the user's own SaaS subscription talking to them?
  - What kind of mail is it (the fine A-W taxonomy)?
  - For each sentence: is it a question, a request, marketing copy, a
    consideration, a decision, or a completed action?

Nothing here touches memory state. Output is evidence for the classifier,
the extractor, and the quality gate. When the analysis is unsure it says so
(UNKNOWN / low scores) rather than guessing.
"""
from __future__ import annotations
import re
from email.utils import parseaddr, getaddresses

# ── fine-grained email categories (product taxonomy) ───────────────────────
# Mapped down to the pipeline's 4-way classification for compatibility:
#   BUSINESS_*            -> BUSINESS_RELEVANT / POSSIBLY_BUSINESS
#   MARKETING/NEWSLETTER/PROMOTIONAL/AUTOMATED_NOTIFICATION/RECEIPT/
#   SUBSCRIPTION_NOTIFICATION/SOCIAL_NOTIFICATION -> AUTOMATED_NOISE
#   PERSONAL/LOW_VALUE/UNKNOWN -> NON_BUSINESS (unless evidence says otherwise)
CATEGORIES = (
    "BUSINESS_RELATIONSHIP", "BUSINESS_TRANSACTION", "BUSINESS_CONTRACT",
    "BUSINESS_NEGOTIATION", "BUSINESS_CUSTOMER_COMMUNICATION",
    "BUSINESS_SUPPLIER_COMMUNICATION", "BUSINESS_PARTNER_COMMUNICATION",
    "BUSINESS_OPERATIONAL", "BUSINESS_INTERNAL", "BUSINESS_FINANCIAL",
    "BUSINESS_LEGAL", "BUSINESS_PROJECT", "BUSINESS_SUPPORT",
    "PERSONAL", "MARKETING", "NEWSLETTER", "AUTOMATED_NOTIFICATION",
    "RECEIPT", "SUBSCRIPTION_NOTIFICATION", "PROMOTIONAL",
    "SOCIAL_NOTIFICATION", "LOW_VALUE", "UNKNOWN",
)

NOISE_CATEGORIES = frozenset({
    "MARKETING", "NEWSLETTER", "AUTOMATED_NOTIFICATION", "RECEIPT",
    "SUBSCRIPTION_NOTIFICATION", "PROMOTIONAL", "SOCIAL_NOTIFICATION",
})

BUSINESS_CATEGORIES = frozenset(c for c in CATEGORIES if c.startswith("BUSINESS_"))


def _addr(value: str) -> str:
    return (parseaddr(value or "")[1] or "").lower().strip()


def _name(value: str) -> str:
    n, a = parseaddr(value or "")
    return (n or (a.split("@")[0] if a else "")).strip()


def _domain(email: str) -> str:
    return email.split("@")[-1].lower() if "@" in (email or "") else ""


def _addr_list(value: str) -> list[str]:
    if not value:
        return []
    return [a.lower() for _, a in getaddresses([value]) if a]


# ── participants & direction ───────────────────────────────────────────────
def normalize_identity(owner: "str | dict | None") -> dict:
    """Accepts the legacy owner-email string or a full identity dict
    {company_name, emails: [...], domains: [...]} and returns a normalized
    {company_name, emails: set, domains: set}. The connected mailbox address
    is always part of `emails`; configured domains make every colleague at
    the same organisation part of SELF."""
    if owner is None:
        return {"company_name": None, "emails": set(), "domains": set()}
    if isinstance(owner, str):
        e = owner.lower().strip()
        return {"company_name": None, "emails": {e} if e else set(),
                "domains": set()}
    emails = {str(x).lower().strip() for x in (owner.get("emails") or []) if x}
    domains = {str(x).lower().strip().lstrip("@") for x in (owner.get("domains") or []) if x}
    return {"company_name": (owner.get("company_name") or None),
            "emails": emails, "domains": domains}


def parse_participants(payload: dict, owner_email: "str | dict | None" = None) -> dict:
    """Extract every party on the mail and establish direction relative to the
    connected account owner. owner_email is either the oauth account address or
    a full org identity ({company_name, emails, domains}). The identity is the
    anchor for 'who is us': any configured address or domain counts as SELF.

    direction:
      inbound   sender is not us (someone wrote TO the organisation)
      outbound  sender IS us (the owner or a configured org address)
      unknown   owner identity unavailable
    """
    headers = {k.lower(): v for k, v in (payload.get("headers") or {}).items()}
    sender = payload.get("from") or headers.get("from") or ""
    sender_email = payload.get("from_email") or _addr(sender)
    sender_domain = _domain(sender_email)
    to_list = _addr_list(payload.get("to") or headers.get("to") or "")
    cc_list = _addr_list(headers.get("cc") or "")
    reply_to = _addr(headers.get("reply-to") or "")

    ident = normalize_identity(owner_email)
    self_emails, self_domains = ident["emails"], ident["domains"]

    def is_self(addr: str) -> bool:
        return bool(addr) and (addr in self_emails or _domain(addr) in self_domains)

    have_identity = bool(self_emails or self_domains)
    if have_identity and is_self(sender_email):
        direction = "outbound"
    elif have_identity:
        direction = "inbound"
    else:
        direction = "unknown"

    counterparty = None
    if direction == "outbound":
        # the first recipient outside our organisation is the counterparty
        counterparty = next((a for a in to_list + cc_list if not is_self(a)), None)
    elif direction == "inbound":
        counterparty = sender_email or None

    owner_primary = next(iter(sorted(self_emails)), None)
    return {
        "sender_email": sender_email,
        "sender_name": _name(sender),
        "sender_domain": sender_domain,
        "sender_is_self": is_self(sender_email),
        "to": to_list,
        "cc": cc_list,
        "reply_to": reply_to,
        "owner_email": owner_primary,
        "owner_domain": _domain(owner_primary) if owner_primary else
                        (next(iter(sorted(self_domains)), "")),
        "self_company": ident["company_name"],
        "direction": direction,
        "counterparty_email": counterparty,
        "counterparty_domain": _domain(counterparty or ""),
        "thread_id": payload.get("thread_id"),
        "message_id": payload.get("message_id") or payload.get("external_id"),
        "in_reply_to": headers.get("in-reply-to"),
        "references": headers.get("references"),
        # internal: correspondence that stays inside our organisation -
        # a colleague writing to the owner, or the owner writing to a colleague
        "internal": bool(have_identity and (
            (direction == "inbound" and self_domains and sender_domain in self_domains) or
            (direction == "outbound" and counterparty is None and
             any(is_self(a) for a in to_list)))),
    }


# ── SaaS self-notification detection ───────────────────────────────────────
# "Your Stripe subscription renewed" is the OWNER's relationship with a vendor,
# not a customer relationship. Detected from second-person template shape plus
# platform-sender evidence - never from a domain blacklist alone.
_SELF_NOTIFICATION_SUBJECT = re.compile(
    r"^(your|you'?re|welcome to|thanks for (?:joining|subscribing)|"
    r"get(?:ting)? started|confirm(?:ing)? your|verify your|"
    r"tu[s]?\b|vuestr[oa]s?\b)", re.I)
_SELF_NOTIFICATION_BODY = re.compile(
    r"\byour (?:subscription|trial|plan|account|order|invoice|receipt|payment|"
    r"membership|free (?:trial|month)|renewal|purchase|shipment|delivery|card)\b", re.I)
_PLATFORM_SENDER = re.compile(
    r"^(noreply|no-reply|donotreply|do-not-reply|notifications?|billing|"
    r"receipts?|accounts?|support|hello|hi|team|news|newsletter|updates?|"
    r"alerts?|info|contact|help|welcome|onboarding|success|trial|deals?|"
    r"marketing|offers?|brief|digest)(\+[^@]*)?$", re.I)


def is_saas_self_notification(payload: dict, participants: dict) -> tuple[bool, list[str]]:
    """The platform is talking to the owner about the OWNER'S OWN account.
    Requires template shape evidence; a human at billing@acme.com writing a
    real sentence about a shared contract does not trip this."""
    signals = []
    subject = payload.get("subject") or ""
    body = payload.get("body") or ""
    local = participants["sender_email"].split("@")[0] if participants["sender_email"] else ""

    if _PLATFORM_SENDER.match(local):
        signals.append(f"platform_sender:{local}")
    if _SELF_NOTIFICATION_SUBJECT.search(subject.strip()):
        signals.append("second_person_subject")
    body_hits = len(_SELF_NOTIFICATION_BODY.findall(body[:3000]))
    if body_hits:
        signals.append(f"your_account_language:{body_hits}")
    # first-person plural from the sender's side + no question to the reader is
    # a human letter; templates rarely ask nothing and say "we agreed"
    human_marks = len(re.findall(r"\b(we agreed|as discussed|per our|following up"
                                 r"|as promised|attached is|please find)\b", body, re.I))
    is_self = (len(signals) >= 2 and body_hits >= 1 and human_marks == 0)
    return is_self, signals


# ── marketing / template density ───────────────────────────────────────────
_MARKETING_PHRASES = [
    r"\bunsubscribe\b", r"\bview (?:this |it )?in (?:your )?browser\b",
    r"\bmanage (?:your )?preferences\b", r"\blimited[- ]time\b", r"\b\d{1,2}% off\b",
    r"\bsale ends?\b", r"\bshop now\b", r"\bbuy now\b", r"\bclick here\b",
    r"\bexclusive (?:offer|deal|access)\b", r"\bfree (?:trial|shipping|gift)\b",
    r"\bdon'?t miss\b", r"\blast chance\b", r"\bnew (?:arrivals?|season|collection)\b",
    r"\bupgrade (?:now|today)\b", r"\bsave (?:up to )?[\d$€£%]", r"\bblack friday\b",
    r"\bdeals?\b", r"\boferta", r"\bdescuento", r"\bdate de baja\b", r"\bcancelar? (?:tu|la) suscripci",
    r"\btop stories\b", r"\bthis week(?:'s)?\b.{0,20}\b(?:issue|roundup|digest|newsletter)\b",
    r"\bwebinar\b", r"\bfollow us\b", r"\bhttps?://\S*(?:utm_|track|click\.)",
]
_EMOJI = re.compile("[\U0001F300-\U0001FAFF\u2600-\u27BF\u2B00-\u2BFF\uFE0F]")


def marketing_density(payload: dict) -> tuple[float, list[str]]:
    """How template/promotional the mail reads. 0 = plain human letter."""
    subject = payload.get("subject") or ""
    body = (payload.get("body") or "")[:6000]
    blob = f"{subject}\n{body}"
    signals, score = [], 0.0
    hits = 0
    for pat in _MARKETING_PHRASES:
        n = len(re.findall(pat, blob, re.I))
        if n:
            hits += n
    if hits:
        score += min(0.25 * hits, 1.0)
        signals.append(f"marketing_phrases:{hits}")
    emoji_subject = len(_EMOJI.findall(subject))
    if emoji_subject >= 1:
        score += 0.25 * min(emoji_subject, 3)
        signals.append(f"emoji_subject:{emoji_subject}")
    # link farms are template mail; a human letter rarely carries 5+ links
    links = len(re.findall(r"https?://", body))
    if links >= 5:
        score += 0.3
        signals.append(f"link_farm:{links}")
    if re.search(r"\b(?:©|copyright)\s*20\d\d\b", body, re.I):
        score += 0.15
        signals.append("footer_copyright")
    return min(score, 2.0), signals


# ── speech acts ────────────────────────────────────────────────────────────
# The strength ladder from the brief:
#   QUESTION       "Can you send the contract?"       -> never a flat fact
#   REQUEST        "Please extend our subscription."  -> requested_*, not done_*
#   MARKETING_CTA  "Want to upgrade? Click here."     -> never a fact
#   SUGGESTION     "Maybe we should expand."          -> not stored
#   CONSIDERATION  "We're considering cancelling."    -> considering_*, weak
#   INTENTION      "We plan to cancel."               -> intends_*, medium
#   DECISION       "We've decided to cancel."         -> decided_*, strong
#   COMPLETED      "We have cancelled."               -> completed, strong
#   STATEMENT      "Our unit price is $4.20."         -> plain fact, strong
SPEECH_ACTS = ("QUESTION", "REQUEST", "MARKETING_CTA", "SUGGESTION",
               "CONSIDERATION", "INTENTION", "DECISION", "COMPLETED", "STATEMENT")

_CTA_TAIL = re.compile(r"\b(click|tap|shop|browse|visit|sign up|register|book|"
                       r"claim|redeem|start (?:your|a) (?:free )?trial|learn more)\b", re.I)
_SECOND_PERSON_OPEN = re.compile(
    r"^(?:do you|would you|want to|wanna|ready to|looking to|need to|"
    r"why not|don'?t (?:want|forget)|interested in)\b", re.I)


def split_sentences(text: str) -> list[str]:
    """Cheap sentence splitter good enough for extraction gating."""
    text = re.sub(r"\s+", " ", text or "").strip()
    if not text:
        return []
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z¿¡\"'(])|\n+", text)
    return [p.strip() for p in parts if len(p.strip()) >= 3]


def speech_act(sentence: str) -> str:
    s = (sentence or "").strip()
    low = s.lower()

    if s.endswith("?") or re.match(r"^(can|could|would|will|shall|do|does|did|is|are|"
                                   r"may|might|what|when|where|who|why|how)\b", low):
        # a question aimed at the reader that sells something is a CTA
        if _SECOND_PERSON_OPEN.match(low) and _CTA_TAIL.search(low):
            return "MARKETING_CTA"
        return "QUESTION"
    if _SECOND_PERSON_OPEN.match(low):
        # "Want to upgrade? Click here" without the '?' kept - still a CTA shape
        return "MARKETING_CTA" if _CTA_TAIL.search(low) else "QUESTION"
    if re.match(r"^(please|kindly|could you please|por favor)\b", low) or \
       re.search(r"\b(please|kindly)\s+(send|share|forward|extend|confirm|review|sign|update|cancel|renew)\b", low) or \
       re.search(r"\bpor favor\b.{0,30}\b(?:cancel|renov|env[ií]|firm|confirm)", low):
        return "REQUEST"
    if re.search(r"\b(maybe|perhaps|possibly)\s+we\b|\bwe (?:could|might)\b(?! have)", low):
        return "SUGGESTION"
    if re.search(r"\b(?:we|i)(?:'re| are| am)?\s*(?:currently\s+)?(?:considering|"
                 r"thinking about|exploring|evaluating|weighing)\b", low):
        return "CONSIDERATION"
    if re.search(r"\b(?:we|i)(?:\s+have|'ve)\s+(?:decided|chosen|agreed|opted)\b", low) or \
       re.search(r"\b(?:we|i)\s+(?:decided|chose|agreed|opted)\s+to\b", low):
        return "DECISION"
    if re.search(r"\b(?:we|i)(?:\s+(?:have|had)|'ve)\s+(?:cancell?ed|renewed|signed|"
                 r"upgraded|downgraded|extended|terminated|paid|approved|completed|"
                 r"expanded|switched|moved)\b", low) or \
       re.search(r"\b(?:we|i)\s+(?:already\s+|just\s+|then\s+)?(?:cancell?ed|renewed|"
                 r"signed|upgraded|downgraded|extended|terminated|paid)\b", low) or \
       re.search(r"\bhas been (?:cancell?ed|renewed|signed|processed|approved|"
                 r"completed|extended|upgraded|downgraded|terminated|paid)\b", low) or \
       re.search(r"\b[a-z]+ has (?:approved|signed|cancell?ed|renewed|confirmed|"
                 r"paid|completed|terminated)\b", low) or \
       re.search(r"\bhemos (?:cancelado|renovado|firmado|pagado|ampliado)\b"
                 r"|\bya (?:cancelamos|renovamos|firmamos|pagamos)\b", low):
        return "COMPLETED"
    if re.search(r"\bhemos decidido\b|\bdecidimos\s+(?:cancelar|renovar|firmar|ampliar)\b", low):
        return "DECISION"
    if re.search(r"\bestamos (?:considerando|pensando en|valorando)\b", low):
        return "CONSIDERATION"
    if re.search(r"\b(?:we|i)\s+(?:plan|intend|want|would like|wish|aim)\s+to\b", low) or \
       re.search(r"\b(?:we|i)(?:'re| are| am)\s+(?:planning|going|looking)\s+to\b", low) or \
       re.search(r"\b(?:we|i)(?:'re| are| am)\s+(?:cancell?ing|renewing|upgrading|"
                 r"downgrading|extending|switching|moving)\b", low) or \
       re.search(r"\b(?:we|i)\s+will\s+(?:cancel|renew|sign|upgrade|downgrade|"
                 r"extend|pay|terminate)\b", low) or \
       re.search(r"\b(?:queremos|quiero|vamos a|nos gustar[ií]a|me gustar[ií]a)\s+"
                 r"(?:cancelar|renovar|ampliar|firmar|extender|cambiar|mejorar)\b", low) or \
       re.search(r"\b(?:we|i)(?:'d| would)\s+(?:like|prefer)\s+to\b", low):
        return "INTENTION"
    return "STATEMENT"


# strength -> extraction policy. QUESTION/CTA/SUGGESTION never yield the flat
# fact. REQUEST yields requested_*. CONSIDERATION yields considering_* at low
# confidence. INTENTION intends_*. DECISION/COMPLETED/STATEMENT are strong.
ACT_POLICY = {
    "QUESTION":      {"store": False},
    "MARKETING_CTA": {"store": False},
    "SUGGESTION":    {"store": False},
    "REQUEST":       {"store": True, "prefix": "requested", "confidence": 0.7},
    "CONSIDERATION": {"store": True, "prefix": "considering", "confidence": 0.55},
    "INTENTION":     {"store": True, "prefix": "intends_to", "confidence": 0.8},
    "DECISION":      {"store": True, "prefix": "decided_to", "confidence": 0.9},
    "COMPLETED":     {"store": True, "prefix": "has", "confidence": 0.92},
    "STATEMENT":     {"store": True, "prefix": None, "confidence": 0.85},
}


# ── grammatical party of a sentence ────────────────────────────────────────
def sentence_party(sentence: str, participants: dict) -> str:
    """Whose action/state does this sentence describe?
      sender_party    "we/I ..." -> the writer's side
      recipient_party "you/your ..." -> the reader's side
      third_party     a named other ("John has approved", "Sarah cancelled")
      unknown         can't tell
    """
    low = (sentence or "").lower().strip()
    # strip a leading greeting ("Hi Troy,", "Hola,", "Estimada Sra. -") so the
    # grammatical subject that follows is judged, not the salutation
    low = re.sub(r"^(?:hi|hello|hey|dear|hola|buenos d[ií]as|buenas|estimad[oa]s?)"
                 r"\b[^,.!-]{0,30}[,.!-]\s*", "", low)
    if re.match(r"^(?:we|i|our|nosotros|nuestr[oa]|queremos|quiero|hemos)\b", low) or \
       re.search(r"\b(?:we|i)(?:'ve|'re|'d| have| are| am| will| would| want| plan"
                 r"| intend| need| prefer| decided| chose| agreed| can offer)\b", low[:70]) or \
       re.search(r"\b(?:queremos|quiero|hemos|vamos a|nos gustar[ií]a|decidimos|"
                 r"firmamos|cancelamos|renovamos|pagamos|podemos|ofrecemos)\b", low[:70]):
        return "sender_party"
    if re.match(r"^(?:you|your)\b", low) or re.search(r"^.{0,25}\byour\b", low):
        return "recipient_party"
    m = re.match(r"^([A-Z][a-z]+(?: [A-Z][a-z]+)?)\s+(?:has|have|had|is|was|will|from)\b",
                 (sentence or "").strip())
    if m and m.group(1).lower() not in ("the", "this", "that", "please", "thanks",
                                         "thank", "attached", "regards", "best"):
        return "third_party"
    return "unknown"


# ── fine category ──────────────────────────────────────────────────────────
def categorize(payload: dict, participants: dict, business_score: float,
               automated_score: float, mk_score: float,
               business_signals: list[str], type_votes: dict | None = None) -> str:
    """Fine-grained A-W category from the accumulated evidence. Conservative:
    UNKNOWN beats a guess."""
    subject = (payload.get("subject") or "").lower()
    body = (payload.get("body") or "")[:4000].lower()
    saas_self, _ = is_saas_self_notification(payload, participants)

    if saas_self:
        return "SUBSCRIPTION_NOTIFICATION"
    if mk_score >= 0.9:
        if re.search(r"\bnewsletter\b|\bdigest\b|\bweekly\b.{0,20}\b(brief|roundup|issue)\b"
                     r"|\bmorning brief\b|\btop stories\b", subject + " " + body[:500]):
            return "NEWSLETTER"
        return "MARKETING" if mk_score >= 1.2 else "PROMOTIONAL"
    if automated_score >= 0.5 and business_score < 0.35:
        if re.search(r"\breceipt\b|\byour (?:order|payment|invoice)\b", subject):
            return "RECEIPT"
        if re.search(r"\b(?:invited you|viewed your profile|new connection|"
                     r"followed you|mentioned you)\b", subject + body[:300]):
            return "SOCIAL_NOTIFICATION"
        return "AUTOMATED_NOTIFICATION"

    if business_score >= 0.30:
        votes = type_votes or {}
        top = max(votes, key=votes.get) if votes else None
        sig = set(business_signals or [])
        if participants.get("internal"):
            return "BUSINESS_INTERNAL"
        if "contract" in sig or top == "CONTRACT":
            return "BUSINESS_CONTRACT"
        if "negotiation" in sig or top == "NEGOTIATION":
            return "BUSINESS_NEGOTIATION"
        if top == "SUPPLIER" or {"pricing", "purchasing", "logistics_terms",
                                  "manufacturing"} & sig:
            return "BUSINESS_SUPPLIER_COMMUNICATION"
        if top == "PARTNER" or "partnership" in sig:
            return "BUSINESS_PARTNER_COMMUNICATION"
        if top == "FINANCE" or {"payment_terms", "billing_terms"} & sig:
            return "BUSINESS_FINANCIAL"
        if top == "LEGAL" or "compliance" in sig:
            return "BUSINESS_LEGAL"
        if top == "PROJECT" or "project" in sig:
            return "BUSINESS_PROJECT"
        if top == "CUSTOMER" or {"plan_change", "commercial_intent",
                                  "expansion", "issue"} & sig:
            return "BUSINESS_CUSTOMER_COMMUNICATION"
        return "BUSINESS_RELATIONSHIP"

    if automated_score < 0.3 and mk_score < 0.4 and business_score < 0.2:
        # a short human note with no commercial or template evidence
        if re.search(r"\b(dinner|birthday|weekend|holiday|family|love you)\b", body):
            return "PERSONAL"
        if len(body) < 400:
            return "LOW_VALUE"
    return "UNKNOWN"


def analyze(payload: dict, owner_email: str | None = None,
            business_score: float = 0.0, automated_score: float = 0.0,
            business_signals: list[str] | None = None,
            type_votes: dict | None = None) -> dict:
    """One-call analysis bundle used by the pipeline and the scanner."""
    participants = parse_participants(payload, owner_email)
    mk_score, mk_signals = marketing_density(payload)
    saas_self, saas_signals = is_saas_self_notification(payload, participants)
    category = categorize(payload, participants, business_score, automated_score,
                          mk_score, business_signals or [], type_votes)
    return {
        "participants": participants,
        "marketing_score": round(mk_score, 2),
        "marketing_signals": mk_signals,
        "saas_self_notification": saas_self,
        "saas_signals": saas_signals,
        "category": category,
        "is_noise_category": category in NOISE_CATEGORIES,
        "is_business_category": category in BUSINESS_CATEGORIES,
    }
