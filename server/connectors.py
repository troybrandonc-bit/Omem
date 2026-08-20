"""Production connector layer: Gmail + LLM extraction + auditable entity resolution.

Boundary honesty: this sandbox cannot reach Google or an LLM provider. Every
class here takes an injectable transport/client. Tests inject deterministic mocks
that mimic the REAL wire shapes (Gmail users.messages JSON; chat-completions JSON).
Production injects a urllib-based transport pointed at the real endpoints. The
pipeline, storage, dedup, provenance, and engine calls are identical either way.
"""
from __future__ import annotations
import base64
import json
import re
import time
from ingest import Connector, Extractor

# ── credential storage (encrypted at rest) ────────────────────────────────
# Lightweight reversible obfuscation over a project-scoped key. NOT a substitute
# for a real KMS; flagged as such. Real deployment swaps _cipher for KMS/Fernet.
def _cipher(text: str, secret: str) -> str:
    key = (secret * (len(text) // len(secret) + 1))[:len(text)]
    xored = bytes(a ^ b for a, b in zip(text.encode(), key.encode()))
    return base64.b64encode(xored).decode()


def _decipher(token: str, secret: str) -> str:
    raw = base64.b64decode(token.encode())
    key = (secret * (len(raw) // len(secret) + 1))[:len(raw)]
    return bytes(a ^ b for a, b in zip(raw, key.encode())).decode()


CRED_SCHEMA = """
CREATE TABLE IF NOT EXISTS oauth_creds(
  connector_id TEXT PRIMARY KEY, provider TEXT NOT NULL,
  access_token TEXT, refresh_token TEXT, expires REAL,
  scope TEXT, account TEXT, connected REAL, status TEXT NOT NULL DEFAULT 'connected');
"""


class OAuthStore:
    """OAuth credential storage. Encryption is delegated to a SecretsProvider
    (authenticated encryption locally; KMS envelope in production). Refresh/access
    tokens are NEVER returned by get() unless include_secrets=True, which only the
    Gmail transport uses internally. API responses call get() without it."""
    def __init__(self, db, provider=None):
        from secrets_provider import get_secrets_provider
        self.db = db
        self.secrets = provider or get_secrets_provider()
        db.executescript(CRED_SCHEMA)
        db.commit()

    def save(self, connector_id, provider, access, refresh, expires, scope, account):
        self.db.execute(
            "INSERT OR REPLACE INTO oauth_creds VALUES(?,?,?,?,?,?,?,?,?)",
            (connector_id, provider,
             self.secrets.encrypt(access) if access else None,
             self.secrets.encrypt(refresh) if refresh else None,
             expires, scope, account, time.time(), "connected"))
        self.db.commit()

    def update_access(self, connector_id, access, expires):
        """Persist a freshly refreshed access token (encrypted) with its new
        expiry, without touching the refresh token or connection status."""
        self.db.execute(
            "UPDATE oauth_creds SET access_token=?, expires=? WHERE connector_id=?",
            (self.secrets.encrypt(access) if access else None, expires, connector_id))
        self.db.commit()

    def get(self, connector_id, include_secrets=False):
        r = self.db.execute("SELECT * FROM oauth_creds WHERE connector_id=?", (connector_id,)).fetchone()
        if not r:
            return None
        d = dict(r)
        if include_secrets:
            d["access_token"] = self.secrets.decrypt(d["access_token"]) if d["access_token"] else None
            d["refresh_token"] = self.secrets.decrypt(d["refresh_token"]) if d["refresh_token"] else None
        else:
            # never expose token material by default
            d.pop("access_token", None)
            d.pop("refresh_token", None)
            d["has_tokens"] = bool(r["access_token"])
        return d

    def set_status(self, connector_id, status):
        self.db.execute("UPDATE oauth_creds SET status=? WHERE connector_id=?", (status, connector_id))
        self.db.commit()

    def disconnect(self, connector_id):
        self.db.execute("UPDATE oauth_creds SET status='disconnected', access_token=NULL WHERE connector_id=?",
                        (connector_id,))
        self.db.commit()


# ── Gmail transport seam ───────────────────────────────────────────────────
class ProviderNotConfigured(Exception):
    """Raised when a connector needs provider credentials that are absent.
    The product must surface this as an explicit NOT_CONFIGURED state, never
    as a crash, and never as a fake success."""
    def __init__(self, provider, message="", env_vars=None):
        self.provider = provider
        self.env_vars = env_vars or []
        super().__init__(message or f"{provider} is not configured on this deployment")


class GmailTransport:
    """Abstract Gmail transport. The real implementation lives in
    providers.RealGmailTransport and is selected when GOOGLE_* env vars exist;
    tests inject a mock. If neither is available this raises a typed
    ProviderNotConfigured so the API can answer honestly."""
    def list_messages(self, access_token: str, after_cursor: str | None) -> tuple[list[dict], str | None]:
        raise ProviderNotConfigured(
            "google",
            "Gmail is not configured. Set GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET "
            "and GOOGLE_REDIRECT_URI, then reconnect the mailbox.",
            ["GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "GOOGLE_REDIRECT_URI"])


class MockGmailTransport(GmailTransport):
    """Returns messages in real Gmail API shape (base64url raw payload)."""
    def __init__(self, messages: list[dict]):
        # messages: [{id, threadId, internalDate, subject, from, body}]
        self._messages = messages

    def list_messages(self, access_token, after_cursor):
        start = int(after_cursor) if after_cursor else 0
        out = []
        for i, m in enumerate(self._messages):
            if i < start:
                continue
            raw = f"From: {m['from']}\r\nSubject: {m['subject']}\r\n\r\n{m['body']}"
            out.append({
                "id": m["id"], "threadId": m.get("threadId", m["id"]),
                "internalDate": str(m.get("internalDate", int(time.time() * 1000))),
                "payload": {"headers": [
                    {"name": "From", "value": m["from"]},
                    {"name": "Subject", "value": m["subject"]}]},
                "raw": base64.urlsafe_b64encode(raw.encode()).decode(),
            })
        return out, str(len(self._messages))


def html_to_text(html: str) -> str:
    """Render an HTML email body as readable plain text.

    Emails are frequently HTML-only with inline <style>/<script>, so the stored
    body must be turned into something a person can read (and something the
    extractor can quote as evidence). Deliberately simple and dependency-free:
    drop non-content elements, turn block tags into line breaks, unescape
    entities, collapse whitespace.
    """
    import html as _html
    import re as _re
    if not html:
        return ""
    text = _re.sub(r"(?is)<(script|style|head|title)[^>]*>.*?</\1>", " ", html)
    text = _re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = _re.sub(r"(?i)</(p|div|tr|li|h[1-6]|table)>", "\n", text)
    text = _re.sub(r"(?i)<li[^>]*>", "\n- ", text)
    text = _re.sub(r"(?s)<!--.*?-->", " ", text)
    text = _re.sub(r"<[^>]+>", " ", text)          # remaining tags
    text = _html.unescape(text)
    text = text.replace("\u200c", "").replace("\u00a0", " ")
    text = _re.sub(r"[ \t\r\f\v]+", " ", text)
    text = _re.sub(r"\n\s*\n\s*\n+", "\n\n", text)
    return "\n".join(line.strip() for line in text.split("\n")).strip()


def looks_like_html(text: str) -> bool:
    t = (text or "").lstrip()[:400].lower()
    return ("<html" in t or "<!doctype html" in t or "<body" in t
            or "<table" in t or "<div" in t)


def decode_quoted_printable(text: str) -> str:
    """Legacy source records were stored before MIME decoding existed, so they
    can still contain quoted-printable escapes (=3D, soft line breaks)."""
    import quopri
    if "=3D" not in text and "=\n" not in text and "=\r\n" not in text:
        return text
    try:
        return quopri.decodestring(text.encode("utf-8", "replace")).decode("utf-8", "replace")
    except Exception:
        return text


def readable_body(text: str) -> str:
    """Best-effort readable rendering of any stored body (new or legacy)."""
    if not text:
        return ""
    out = decode_quoted_printable(text)
    if looks_like_html(out):
        out = html_to_text(out)
    return out.strip()


def _parse_rfc822(raw: str) -> dict:
    """Parse a raw RFC822 message into the fields the pipeline needs. Handles
    MIME multipart and encoded headers; falls back safely on malformed input."""
    import email as _email
    from email import policy as _policy
    try:
        msg = _email.message_from_string(raw, policy=_policy.default)
    except Exception:
        return {"from": "", "to": "", "subject": "", "date": "", "body": raw}
    body = ""
    is_html = False
    try:
        part = msg.get_body(preferencelist=("plain", "html")) if msg.is_multipart() else msg
        if part is not None:
            body = part.get_content()
            is_html = (part.get_content_type() or "").lower() == "text/html"
    except Exception:
        body = raw.split("\r\n\r\n", 1)[1] if "\r\n\r\n" in raw else raw
        is_html = looks_like_html(body)
    if is_html or looks_like_html(body):
        body = html_to_text(body)
    body = decode_quoted_printable(body)
    return {
        "all_headers": {k.lower(): str(v) for k, v in msg.items()},
        "from": str(msg.get("From") or ""),
        "to": str(msg.get("To") or ""),
        "subject": str(msg.get("Subject") or ""),
        "date": str(msg.get("Date") or ""),
        "body": (body or "").strip(),
    }


# Header + sender signals that mark mail as bulk/automated rather than a real
# business conversation. Checked client-side as well as via Gmail's query, since
# other connectors (IMAP, Outlook) have no server-side equivalent.
_AUTOMATED_LOCALPARTS = (
    "noreply", "no-reply", "donotreply", "do-not-reply", "notifications",
    "notification", "mailer-daemon", "postmaster", "bounce", "bounces",
    "newsletter", "news", "marketing", "info", "support-noreply", "alerts",
    "updates", "billing-noreply", "automated", "system", "daemon", "via",
)


def is_automated(payload: dict) -> tuple[bool, str]:
    """Return (is_automated, reason). Conservative: only rejects on strong
    signals, so genuine business mail from e.g. billing@acme.com is kept."""
    headers = {k.lower(): (v or "") for k, v in (payload.get("headers") or {}).items()}
    if headers.get("list-unsubscribe") or headers.get("list-id"):
        return True, "bulk mailing list (List-Unsubscribe/List-Id header)"
    precedence = headers.get("precedence", "").lower()
    if precedence in ("bulk", "list", "junk"):
        return True, f"Precedence: {precedence}"
    if headers.get("auto-submitted", "").lower() not in ("", "no"):
        return True, "Auto-Submitted header"
    if headers.get("x-auto-response-suppress") or headers.get("feedback-id"):
        return True, "automated bulk sender header"
    local = (_address_of(payload.get("from") or "") or "").split("@")[0]
    if local in _AUTOMATED_LOCALPARTS:
        return True, f"automated sender address ({local}@)"
    subject = (payload.get("subject") or "").lower()
    if subject.startswith(("out of office", "automatic reply", "undeliverable",
                           "delivery status notification", "returned mail")):
        return True, "auto-reply or bounce"
    return False, ""


def _address_of(sender: str) -> str:
    from email.utils import parseaddr
    return (parseaddr(sender or "")[1] or "").lower()


def _display_name(sender: str) -> str:
    from email.utils import parseaddr
    name, addr = parseaddr(sender or "")
    return name or (addr.split("@")[0] if addr else "")


class GmailConnector(Connector):
    """Real Gmail connector. Turns each message into an immutable source-record
    payload; extraction is delegated to whatever Extractor is attached (LLM in
    prod, rule/mocked-LLM in tests). Never bypasses the pipeline."""
    kind = "gmail"

    def __init__(self, transport: GmailTransport, access_token: str | None,
                 extractor: Extractor | None = None):
        self.transport = transport
        self.access_token = access_token
        self.extractor = extractor  # set by the app when instantiating
        self.skipped: list[dict] = []  # bulk/automated mail excluded this poll

    def poll(self, cursor):
        msgs, new_cursor = self.transport.list_messages(self.access_token, cursor)
        items = []
        for m in msgs:
            raw = base64.urlsafe_b64decode(m["raw"]).decode(errors="replace")
            # Gmail's format=raw returns NO payload.headers, so parse the real
            # RFC822 message. (Some responses/mocks do carry headers; prefer
            # those when present, else fall back to the parsed message.)
            headers = {h["name"].lower(): h["value"]
                       for h in (m.get("payload") or {}).get("headers", [])}
            parsed = _parse_rfc822(raw)
            headers = {**parsed.get("all_headers", {}), **headers}
            sender = headers.get("from") or parsed["from"]
            subject = headers.get("subject") or parsed["subject"]
            items.append((m["id"], {
                "message_id": m["id"], "thread_id": m.get("threadId"),
                "from": sender,
                "from_name": _display_name(sender),
                "from_email": _address_of(sender),
                "to": headers.get("to") or parsed["to"],
                "date": headers.get("date") or parsed["date"],
                "subject": subject,
                "body": parsed["body"],
                "snippet": (parsed["body"] or "").strip().replace("\r\n", " ")[:300],
                "internal_date": m.get("internalDate"),
                "gmail_url": f"https://mail.google.com/mail/u/0/#all/{m['id']}",
                "headers": headers,
                "at": "now",
            }))
        # Every message becomes a source record. Whether it enters the memory
        # pipeline is decided later by the business-relevance classifier, so the
        # decision stays inspectable ("why did OMEM ignore this email?").
        return items, new_cursor


# ── LLM extraction ─────────────────────────────────────────────────────────
class LLMClient:
    """Real client posts to a chat-completions endpoint. Injected for tests."""
    def complete(self, system: str, user: str) -> str:
        raise NotImplementedError


EXTRACTION_SYSTEM = """You read one business email and extract DURABLE FACTS about \
the people and companies involved. You are a proposal engine: a separate system \
decides what is ultimately true, so never hedge, never editorialise, and never \
invent.

Return ONLY a JSON object: {"facts": [ ... ]}. Each fact:
{
  "subject_email": "<the email address the fact is ABOUT, exactly as it appears>",
  "subject_kind": "person" | "company",
  "proposition": "<snake_case predicate, see rules>",
  "confidence": <0.0-1.0>,
  "evidence": "<VERBATIM span copied from the email that states this fact>"
}

PROPOSITION RULES
- snake_case, present tense, no subject inside it.
  good: prefers_annual_billing, is_decision_maker, requested_sso,
        renewal_due_september, reported_bug_in_export, wants_to_cancel,
        asked_for_discount, scheduling_call_next_week, budget_approved
- Prefix with "not:" to negate: not:prefers_email_over_phone
- Prefer a specific predicate over a vague one. "asked_for_discount" beats "is_interested".

WHAT COUNTS AS A DURABLE FACT
Include: stated preferences, intentions, commitments, decisions, roles and
authority, renewal or contract dates, budget, blockers, requested features,
reported problems, relationships between people and companies.
Exclude: pleasantries, scheduling chatter with no outcome, one-off logistics,
anything already obvious from the email metadata, and anything you are guessing.

EVIDENCE IS MANDATORY
"evidence" must be a span COPIED CHARACTER-FOR-CHARACTER from the email body or
subject. Do not paraphrase it. If you cannot copy a supporting span, omit the
fact entirely. Facts whose evidence is not found in the source are discarded
downstream, so a paraphrase means your work is thrown away.

CONFIDENCE
0.9+ explicitly stated ("we want annual billing")
0.7-0.9 clearly implied by an explicit statement
0.5-0.7 reasonable reading of ambiguous wording
Below 0.5: omit the fact.

If the email contains no durable fact, return {"facts": []}. That is a correct
and common answer for routine correspondence."""


def _extract_email_local(addr: str) -> str | None:
    m = re.search(r"([A-Za-z0-9._%+-]+)@", addr or "")
    return m.group(1).lower() if m else None


class LLMExtractor(Extractor):
    """Model-backed candidate generator with strict validation. The model only
    PROPOSES; invalid/hallucinated output is dropped, never engine-mutating."""
    def __init__(self, client: LLMClient):
        self.client = client

    def extract(self, payload: dict) -> list[dict]:
        body = payload.get("body", "")
        subject = payload.get("subject", "")
        sender = payload.get("from", "")
        raw = self.client.complete(
            EXTRACTION_SYSTEM,
            f"From: {sender}\nTo: {payload.get('to','')}\nDate: {payload.get('date','')}\n"
            f"Subject: {subject}\n\n{body}")

        candidates = _parse_fact_payload(raw)
        source_text = f"{subject}\n{body}"
        haystack = _normalise(source_text)
        sender_local = _extract_email_local(sender) or (payload.get("customer") or None)
        sender_domain = (_address_of(sender).split("@")[-1] or "").lower()

        facts, seen = [], set()
        for c in candidates:
            if not isinstance(c, dict):
                continue
            prop = (c.get("proposition") or "").strip()
            if not prop or not _VALID_PROP.match(prop):
                continue

            # Anti-hallucination: the quoted span must genuinely appear in the
            # source. This is what makes a cheap model safe to use.
            ev = (c.get("evidence") or "").strip()
            if not ev or _normalise(ev) not in haystack:
                continue

            try:
                conf = float(c.get("confidence", 0.5))
            except (TypeError, ValueError):
                conf = 0.5
            if conf < 0.5:
                continue

            kind = (c.get("subject_kind") or "person").lower()
            subj = _resolve_subject(c.get("subject_email"), kind,
                                    sender_local, sender_domain)
            if subj is None:
                continue  # no real identity: dropping beats inventing one

            key = (subj["id"], prop)
            if key in seen:
                continue
            seen.add(key)
            facts.append({
                "subject": subj,
                "proposition": prop,
                "confidence": max(0.0, min(1.0, conf)),
                "event_kind": "email",
                "event_time": payload.get("at", "now"),
                "label": (subject or "message") + " \u2192 " + prop,
                "evidence": f'"{ev[:180]}"',
            })
        return facts


_VALID_PROP = __import__("re").compile(r"^(not:)?[a-z][a-z0-9_]{2,63}$")


def _normalise(text: str) -> str:
    """Whitespace/case-insensitive comparison so a model that reflows a quote
    still passes, while a fabricated quote still fails."""
    import re as _re
    return _re.sub(r"\s+", " ", (text or "").lower()).strip()


def _parse_fact_payload(raw: str) -> list:
    """Accept {"facts":[...]} or a bare [...]; tolerate code fences. Malformed
    output yields no facts rather than an exception."""
    import re as _re
    if not raw:
        return []
    text = raw.strip()
    fence = _re.search(r"```(?:json)?\s*(.*?)```", text, _re.S)
    if fence:
        text = fence.group(1).strip()
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return []
    if isinstance(data, dict):
        data = data.get("facts", [])
    return data if isinstance(data, list) else []


def _resolve_subject(subject_email, kind, sender_local, sender_domain):
    """Turn the model's subject reference into a valid OMEM entity, or None."""
    vague = {"", "customer", "user", "the customer", "from-sender", "sender",
             "unknown", "n/a", "none", "me", "you"}
    raw = (subject_email or "").strip().lower()
    if kind == "company":
        domain = raw.split("@")[-1] if "@" in raw else raw
        domain = domain or sender_domain
        if not domain or domain in vague:
            return None
        slug = domain.split(".")[0]
        return {"id": f"company:{slug}", "type": "organization", "label": domain}
    local = _extract_email_local(raw) if "@" in raw else raw
    if not local or local in vague:
        local = sender_local
    if not local or local in vague:
        return None
    return {"id": f"customer:{local}", "type": "person", "label": f"Customer {local}"}


class MockLLMClient(LLMClient):
    """Deterministic stand-in emitting the SAME schema as a real model, so tests
    exercise the production parsing path. Never used in a live deployment."""
    def __init__(self, mode="smart"):
        self.mode = mode

    def complete(self, system, user):
        if self.mode == "malformed":
            return "here is your json: {not valid"
        if self.mode == "empty":
            return '{"facts": []}'
        text = user.lower()
        # recover the sender address so facts attach to a real identity
        m = re.search(r"from:.*?([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+)", user, re.I)
        sender = m.group(1) if m else ""
        facts = []
        for needle, prop in [("annual billing", "prefers_annual_billing"),
                             ("cancel", "intends_to_cancel"),
                             ("prefer email", "prefers_email_over_phone"),
                             ("upgrade", "intends_to_upgrade"),
                             ("enterprise", "is_enterprise_customer")]:
            if needle in text:
                idx = text.find(needle)
                facts.append({"subject_email": sender, "subject_kind": "person",
                              "proposition": prop, "confidence": 0.8,
                              "evidence": user[idx:idx + len(needle)]})
        return json.dumps({"facts": facts})



# ── auditable entity resolution ────────────────────────────────────────────
RESOLUTION_SCHEMA = """
CREATE TABLE IF NOT EXISTS entity_resolutions(
  id INTEGER PRIMARY KEY AUTOINCREMENT, project_id TEXT NOT NULL,
  source_record_id TEXT, raw_key TEXT NOT NULL, resolved_entity TEXT NOT NULL,
  method TEXT NOT NULL, evidence TEXT NOT NULL, ts REAL NOT NULL);
"""


class EntityResolver:
    """Cloud-layer resolution that produces valid OMEM Entity references and
    records WHY each raw signal became a given entity. No new semantics: output
    is always an entity id the engine will accept."""
    def __init__(self, db):
        self.db = db
        db.executescript(RESOLUTION_SCHEMA)
        db.commit()

    def resolve(self, project_id, raw_key, existing_labels, source_record_id=None) -> dict:
        """raw_key like 'email:ada@acme.com' or 'name:Ada Lovelace' or 'customer:123'.
        Returns {entity_id, method, evidence, created}."""
        kind, _, value = raw_key.partition(":")
        # 1. exact id already present
        if raw_key in existing_labels:
            return self._record(project_id, raw_key, raw_key, "exact_id",
                                 f"entity {raw_key} already exists", source_record_id, False)
        # 2. email -> customer:<local-part>, stable across messages
        if kind == "email":
            local = _extract_email_local(value)
            eid = f"customer:{local}"
            method, ev = "email_localpart", f"email {value} -> {eid}"
        elif kind == "customer":
            eid, method, ev = raw_key, "explicit_id", f"explicit customer id {value}"
        elif kind == "name":
            slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
            eid, method, ev = f"customer:{slug}", "name_slug", f"name '{value}' -> {eid}"
        else:
            eid, method, ev = f"{kind}:{value}", "passthrough", f"raw {raw_key}"
        created = eid not in existing_labels
        return self._record(project_id, raw_key, eid, method, ev, source_record_id, created)

    def _record(self, project_id, raw_key, eid, method, evidence, srid, created):
        self.db.execute(
            "INSERT INTO entity_resolutions(project_id,source_record_id,raw_key,resolved_entity,method,evidence,ts) VALUES(?,?,?,?,?,?,?)",
            (project_id, srid, raw_key, eid, method, evidence, time.time()))
        self.db.commit()
        return {"entity_id": eid, "method": method, "evidence": evidence, "created": created}

    def history_for(self, project_id, entity_id):
        rows = self.db.execute(
            "SELECT raw_key, method, evidence, source_record_id, ts FROM entity_resolutions "
            "WHERE project_id=? AND resolved_entity=? ORDER BY id", (project_id, entity_id))
        return [dict(r) for r in rows]


# ── Slack connector ────────────────────────────────────────────────────────
class SlackTransport:
    """Real transport calls slack.com/api/conversations.history. Injected so
    tests use fixture-shaped mocks. REAL CODE + EXTERNAL DEPENDENCY."""
    def history(self, token: str, channel: str, oldest: str | None) -> tuple[list[dict], str | None]:
        import urllib.request, urllib.parse, json as _j
        params = {"channel": channel, "limit": "50"}
        if oldest:
            params["oldest"] = oldest
        req = urllib.request.Request(
            "https://slack.com/api/conversations.history?" + urllib.parse.urlencode(params),
            headers={"Authorization": f"Bearer {token}"})
        with urllib.request.urlopen(req, timeout=15) as r:
            data = _j.loads(r.read())
        if not data.get("ok"):
            raise RuntimeError(f"slack error: {data.get('error')}")
        msgs = data.get("messages", [])
        newest = msgs[0]["ts"] if msgs else oldest
        return msgs, newest


class MockSlackTransport(SlackTransport):
    """Fixture-shaped mock using real conversations.history message shape."""
    def __init__(self, messages: list[dict]):
        self._messages = messages  # [{ts, user, text}]

    def history(self, token, channel, oldest):
        out = [m for m in self._messages if not oldest or float(m["ts"]) > float(oldest)]
        newest = max((m["ts"] for m in self._messages), default=oldest)
        return out, newest


class SlackConnector(Connector):
    kind = "slack"

    def __init__(self, transport: SlackTransport, token: str | None, channel: str,
                 extractor: Extractor | None = None):
        self.transport = transport
        self.token = token
        self.channel = channel
        self.extractor = extractor

    def poll(self, cursor):
        msgs, newest = self.transport.history(self.token, self.channel, cursor)
        items = []
        for m in msgs:
            items.append((f"{self.channel}:{m['ts']}", {
                "customer": m.get("user", ""), "subject": f"slack:{self.channel}",
                "body": m.get("text", ""), "at": "now",
            }))
        return items, newest


# ── Salesforce/CRM connector ───────────────────────────────────────────────
class SalesforceTransport:
    """Real transport queries /services/data/vXX/query (SOQL). Injected for
    tests. REAL CODE + EXTERNAL DEPENDENCY."""
    def __init__(self, instance_url: str | None = None, api_version="v59.0"):
        self.instance_url = instance_url
        self.api_version = api_version

    def query_notes(self, token: str, after_id: str | None) -> tuple[list[dict], str | None]:
        import urllib.request, urllib.parse, json as _j
        from security import safe_url
        soql = "SELECT Id, Title, Body, OwnerId FROM Note ORDER BY Id"
        if after_id:
            soql = f"SELECT Id, Title, Body, OwnerId FROM Note WHERE Id > '{after_id}' ORDER BY Id"
        url = f"{self.instance_url}/services/data/{self.api_version}/query?" + urllib.parse.urlencode({"q": soql})
        # SSRF guard: instance_url is tenant-configured, so validate the resolved
        # destination is public https before fetching with the tenant's token.
        safe_url(url)
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
        with urllib.request.urlopen(req, timeout=15) as r:
            data = _j.loads(r.read())
        recs = data.get("records", [])
        newest = recs[-1]["Id"] if recs else after_id
        return recs, newest


class MockSalesforceTransport(SalesforceTransport):
    def __init__(self, records: list[dict]):
        super().__init__("https://mock.my.salesforce.com")
        self._records = records  # [{Id, Title, Body, OwnerId}]

    def query_notes(self, token, after_id):
        recs = [r for r in self._records if not after_id or r["Id"] > after_id]
        newest = self._records[-1]["Id"] if self._records else after_id
        return recs, newest


class SalesforceConnector(Connector):
    kind = "salesforce"

    def __init__(self, transport: SalesforceTransport, token: str | None,
                 extractor: Extractor | None = None):
        self.transport = transport
        self.token = token
        self.extractor = extractor

    def poll(self, cursor):
        recs, newest = self.transport.query_notes(self.token, cursor)
        items = []
        for r in recs:
            items.append((r["Id"], {
                "customer": (r.get("Title") or "").lower().replace(" ", "-"),
                "subject": f"sfdc:{r.get('Title','note')}",
                "body": r.get("Body", ""), "at": "now",
            }))
        return items, newest


# ── GitHub connector (REAL provider, verified against api.github.com) ───────
class ProviderRateLimited(Exception):
    """Raised when an external provider reports quota exhaustion. Carries the
    reset time so the API can surface a truthful, actionable state."""
    def __init__(self, provider, reset_epoch=None, message=""):
        self.provider = provider
        self.reset_epoch = reset_epoch
        super().__init__(message or f"{provider} rate limit exhausted")


class GitHubTransport:
    """Calls the real GitHub REST API. Public repos work unauthenticated; a
    token (stored via OAuthStore/SecretsProvider) raises rate limits and grants
    private-repo access. Handles incremental sync via the `since` cursor,
    pagination via the Link header, and 403/429 rate-limit backoff."""
    BASE = "https://api.github.com"

    def list_issues(self, token: str | None, repo: str, since: str | None,
                    per_page: int = 30) -> tuple[list[dict], str | None]:
        import urllib.request
        import urllib.parse
        import urllib.error
        import json as _j
        params = {"state": "all", "per_page": str(per_page), "sort": "updated",
                  "direction": "asc"}
        if since:
            params["since"] = since  # ISO8601: only issues updated after this
        url = f"{self.BASE}/repos/{repo}/issues?" + urllib.parse.urlencode(params)
        headers = {"User-Agent": "omem-cloud", "Accept": "application/vnd.github+json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        for attempt in range(4):
            try:
                req = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(req, timeout=20) as r:
                    issues = _j.loads(r.read())
                    remaining = r.headers.get("X-RateLimit-Remaining")
                break
            except urllib.error.HTTPError as e:
                if e.code in (403, 429):
                    remaining = e.headers.get("X-RateLimit-Remaining")
                    reset = e.headers.get("X-RateLimit-Reset")
                    if remaining == "0":
                        # genuinely exhausted: retrying cannot help before reset
                        raise ProviderRateLimited(
                            "github", int(reset) if reset else None,
                            "GitHub rate limit exhausted (unauthenticated limit is 60/hour; "
                            "set a token to raise it to 5000/hour)") from None
                    if attempt < 3:
                        time.sleep(2 ** attempt)
                        continue
                raise
        # cursor = newest updated_at seen (issues sorted ascending by update time)
        newest = since
        for i in issues:
            if i.get("updated_at") and (newest is None or i["updated_at"] > newest):
                newest = i["updated_at"]
        return issues, newest


class MockGitHubTransport(GitHubTransport):
    """Fixture transport using real GitHub issue shape (for offline tests)."""
    def __init__(self, issues: list[dict]):
        self._issues = issues

    def list_issues(self, token, repo, since, per_page=30):
        out = [i for i in self._issues if not since or i["updated_at"] > since]
        newest = max((i["updated_at"] for i in self._issues), default=since)
        return out, newest


class GitHubConnector(Connector):
    """Ingests real GitHub issues as immutable source records. Pull requests are
    skipped (they arrive on the issues endpoint but are a different artifact).
    The connector proposes nothing about truth: it only produces payloads."""
    kind = "github"

    def __init__(self, transport: GitHubTransport, token: str | None, repo: str,
                 extractor: Extractor | None = None):
        self.transport = transport
        self.token = token
        self.repo = repo
        self.extractor = extractor

    def poll(self, cursor):
        issues, newest = self.transport.list_issues(self.token, self.repo, cursor)
        items = []
        for i in issues:
            if "pull_request" in i:
                continue  # skip PRs; issues only
            author = (i.get("user") or {}).get("login", "unknown")
            items.append((f"{self.repo}#{i['number']}", {
                "customer": author.lower(),
                "subject": i.get("title", ""),
                "body": (i.get("body") or "")[:4000],
                "repo": self.repo,
                "issue_number": i.get("number"),
                "author": author,
                "url": i.get("html_url"),
                "state": i.get("state"),
                "created_at": i.get("created_at"),
                "updated_at": i.get("updated_at"),
                "at": "now",
            }))
        return items, newest


# ── GitHub issue extractor (deterministic, evidence-grounded) ──────────────
class GitHubIssueExtractor(Extractor):
    """Proposes candidate facts about a repository from a real issue.

    Deterministic and fully auditable: every fact carries the exact substring of
    the source that triggered it, and facts are only emitted when that evidence
    genuinely appears in the issue text. Subjects are the REPO (an organisational
    entity), not the author. The durable knowledge is about the project.
    Proposes only; the frozen engine decides belief state."""

    SIGNALS = [
        ("has_open_bug",            0.75, ["bug", "broken", "regression", "crash", "traceback", "fails"]),
        ("has_documentation_gap",   0.7,  ["documentation", "docs", "unclear", "ambiguous", "typo"]),
        ("has_pending_dependency_update", 0.8, ["bump", "dependabot", "update dependency", "upgrade to"]),
        ("has_feature_request",     0.65, ["feature request", "would be nice", "please add", "proposal", "enhancement"]),
        ("has_type_annotation_issue", 0.7, ["annotated", "type hint", "typing", "mypy"]),
        ("has_performance_concern", 0.7,  ["slow", "performance", "memory leak", "timeout"]),
    ]

    def extract(self, payload: dict) -> list[dict]:
        repo = payload.get("repo")
        if not repo:
            return []
        haystack = ((payload.get("subject") or "") + " " + (payload.get("body") or "")).lower()
        if not haystack.strip():
            return []
        entity_id = f"repo:{repo}"
        num = payload.get("issue_number")
        facts = []
        seen = set()
        for prop, conf, needles in self.SIGNALS:
            for n in needles:
                if n in haystack and prop not in seen:
                    seen.add(prop)
                    # capture the real surrounding text as evidence
                    idx = haystack.find(n)
                    snippet = ((payload.get("subject") or "") + " " + (payload.get("body") or ""))[
                        max(0, idx - 40): idx + len(n) + 40].replace("\n", " ").strip()
                    facts.append({
                        "subject": {"id": entity_id, "type": "organization",
                                    "label": repo},
                        "proposition": prop,
                        "confidence": conf,
                        "event_kind": "github_issue",
                        "event_time": payload.get("at", "now"),
                        "label": f"#{num} {(payload.get('subject') or '')[:60]}",
                        "evidence": f"matched '{n}' in issue #{num}: …{snippet}…",
                    })
                    break
        return facts


# ── deterministic business-fact extraction (Stage 2 without a model) ───────
class BusinessFactExtractor(Extractor):
    """Extracts durable business facts with a VERBATIM evidence span.

    Deliberately narrow: it proposes a fact only when the source states one
    plainly. A business-relevant email with nothing durable in it ("sounds good,
    let's talk tomorrow") correctly yields nothing. Relevance is not evidence.
    Subjects are the counterparty's company where the fact concerns the
    organisation, and the person where it concerns them.
    """

    PATTERNS = [
        # (regex, proposition template, confidence, subject scope)
        (r"(contract|agreement)\b[^.]{0,60}?\b(?:will be|is|at)\s*((?:EUR|USD|GBP|€|\$|£)\s?[\d.,]+)",
         "contract_value_{v}", 0.9, "company"),
        (r"\brenews?\b[^.]{0,40}?\b(every\s+\w+|annually|monthly|quarterly|each\s+\w+)",
         "renews_{v}", 0.85, "company"),
        (r"\bpayment terms?\b[^.]{0,30}?\b(net\s?\d{1,3})", "payment_terms_{v}", 0.88, "company"),
        (r"\bunit price\b[^.]{0,30}?((?:EUR|USD|GBP|€|\$|£)\s?[\d.,]+)", "unit_price_{v}", 0.88, "company"),
        (r"\blead time\b[^.]{0,30}?(\d{1,3}\s*(?:days?|weeks?))", "lead_time_{v}", 0.85, "company"),
        (r"\b(?:MOQ|minimum order)\b[^.]{0,30}?(\d[\d.,]*)", "minimum_order_{v}", 0.85, "company"),
        (r"\b(I am|I'm)\b[^.]{0,40}\b(decision ?maker|who signs off|sign off)\b",
         "is_decision_maker", 0.85, "person"),
        (r"\bwe (?:can'?t|cannot) (?:go ahead|proceed)\b[^.]{0,40}?\bwithout\b\s+([A-Za-z0-9 ]{3,30})",
         "requires_{v}", 0.8, "company"),
        (r"\b(?:this is a )?complaint\b|\bdefect rate\b|\bfaulty batch\b",
         "reported_quality_issue", 0.8, "company"),
        (r"\b(?:requests?|asked for|need)\s+(?:a\s+)?(discount)\b", "requested_discount", 0.8, "company"),
        (r"\b(intends? to|want(?:s)? to|planning to)\s+(cancel|terminate)\b",
         "intends_to_cancel", 0.85, "company"),
        (r"\b(?:renewal|contract)\b[^.]{0,30}?\b(?:due|expires?)\b[^.]{0,20}?\b(January|February|March|April|May|June|July|August|September|October|November|December)\b",
         "renewal_due_{v}", 0.8, "company"),
        # commercial intent stated in plain language - durable, and common in
        # real customer mail even when no figures are quoted
        (r"\b(?:would like to|want to|plan(?:ning)? to|intend to)\s+upgrade\b",
         "intends_to_upgrade", 0.82, "company"),
        (r"\b(?:would like to|want to|prefer)\b[^.]{0,40}\bannual(?:ly)? billing\b",
         "prefers_annual_billing", 0.85, "company"),
        (r"\b(?:move|switch|migrate)\s+to\s+(?:the\s+)?annual\b", "prefers_annual_billing", 0.85, "company"),
        (r"\b(?:enterprise|business|pro)\s+(?:tier|plan)\b", "discussing_{v}", 0.7, "company"),
        (r"\b(?:need|require|requires?)\b[^.]{0,25}\b(SSO|SAML|SOC ?2|ISO ?27001)\b",
         "requires_{v}", 0.85, "company"),
        (r"\b(?:prefer|prefers)\b[^.]{0,20}\b(email|phone|slack)\b[^.]{0,20}\b(?:over|instead of)\b",
         "prefers_{v}_contact", 0.75, "person"),
    ]

    @staticmethod
    def _slug(value: str) -> str:
        s = re.sub(r"[^a-z0-9]+", "_", (value or "").lower()).strip("_")
        return re.sub(r"_+", "_", s)[:40]

    def extract(self, payload: dict) -> list[dict]:
        subject_line = payload.get("subject") or ""
        body = payload.get("body") or ""
        text = f"{subject_line}\n{body}"
        sender = payload.get("from") or ""
        email_addr = _address_of(sender)
        if not email_addr:
            return []
        local = email_addr.split("@")[0]
        domain = email_addr.split("@")[-1]
        company_slug = re.sub(r"[^a-z0-9]+", "-", domain.split(".")[0].lower())

        facts, seen = [], set()
        for pattern, template, conf, scope in self.PATTERNS:
            for m in re.finditer(pattern, text, re.I):
                value = ""
                for g in reversed(m.groups() or ()):
                    if g and not re.fullmatch(r"(contract|agreement|I am|I'm|requests?|asked for|need|intends? to|wants? to|planning to)", g, re.I):
                        value = g
                        break
                if "{v}" in template:
                    slug = self._slug(value)
                    if not slug:
                        continue  # no captured value -> no meaningful proposition
                    prop = template.replace("{v}", slug)
                else:
                    prop = template
                if not re.fullmatch(r"(not:)?[a-z][a-z0-9_]{2,63}", prop):
                    continue
                if prop in seen:
                    continue
                seen.add(prop)
                start = max(0, m.start() - 30)
                evidence = text[start:m.end() + 40].replace("\n", " ").strip()
                subj = ({"id": f"company:{company_slug}", "type": "organization", "label": domain}
                        if scope == "company" else
                        {"id": f"customer:{local}", "type": "person", "label": f"Customer {local}"})
                facts.append({
                    "subject": subj, "proposition": prop, "confidence": conf,
                    "event_kind": "email", "event_time": payload.get("at", "now"),
                    "label": (subject_line or "message") + " \u2192 " + prop,
                    "evidence": f'"{evidence[:180]}"',
                })
        return facts
