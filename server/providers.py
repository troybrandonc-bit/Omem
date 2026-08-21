"""Production provider transports, env-gated.

Each is REAL code that calls the real external API. None can run in this sandbox
(no network egress to Google/OpenAI/Stripe, no credentials), so each is selected
only when its env vars are present; otherwise the app falls back to the injectable
mock used in tests. This keeps the boundary honest: the production path exists and
is wired, but is exercised only where credentials are configured.

Env:
  GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET / GOOGLE_REDIRECT_URI  -> real Gmail
  OMEM_LLM_API_KEY / OMEM_LLM_BASE_URL / OMEM_LLM_MODEL          -> real extractor
  STRIPE_SECRET_KEY                                              -> real billing
"""
from __future__ import annotations
import json
import os
import time
import urllib.parse
import urllib.request
import urllib.error

from connectors import GmailTransport, LLMClient


# ── Real Google OAuth + Gmail ──────────────────────────────────────────────
class ProviderUnreachable(Exception):
    """DNS/connection failure reaching a provider. Distinct from an auth or quota
    error: the request never arrived, so configuration or the network is at
    fault, not the credentials. Always names the host that failed."""
    def __init__(self, host, url, detail, hint=""):
        self.host = host
        self.url = url
        super().__init__(
            f"Could not reach {host} (DNS or network failure: {detail}). "
            f"The request never left this machine. Verify this host resolves "
            f"and is not blocked by a proxy, VPN or firewall."
            + (f" {hint}" if hint else ""))


class ProviderConfigError(Exception):
    """The OPERATOR's provider credentials are wrong (bad client id/secret).
    Not a user problem: reconnecting the account cannot fix it."""
    def __init__(self, provider, detail=""):
        self.provider = provider
        self.detail = detail
        super().__init__(
            f"{provider} rejected this deployment's OAuth client credentials"
            f"{': ' + detail if detail else ''}. Fix GOOGLE_CLIENT_ID / "
            "GOOGLE_CLIENT_SECRET in the server environment; reconnecting the "
            "account will not help. This is an operator configuration problem, "
            "not a credential problem with the connected mailbox.")


class ProviderApiDisabled(Exception):
    """The provider API is not enabled for the configured cloud project. No
    amount of reconnecting fixes this: the API must be switched on, and Google
    caches the negative result for a minute or two afterwards."""
    def __init__(self, provider, detail=""):
        self.provider = provider
        self.detail = detail
        # Google puts the exact console URL in its message; surface it verbatim.
        url = ""
        for token in (detail or "").split():
            if token.startswith("https://console."):
                url = token.rstrip(".")
                break
        self.console_url = url
        super().__init__(
            f"The Gmail API is not enabled for this Google Cloud project. "
            f"Enable it{' at ' + url if url else ''}, wait a minute for Google to "
            f"propagate the change, then sync again. Reconnecting will not help, "
            f"this is a project setting, not a credential problem.")


class ProviderScopeError(Exception):
    """The grant is valid but lacks the scope the request needs."""
    def __init__(self, provider, detail=""):
        self.provider = provider
        super().__init__(
            f"{provider} accepted the credentials but the grant is missing the "
            f"required scope (gmail.readonly){': ' + detail if detail else ''}. "
            f"Reconnect and approve the mailbox-reading permission.")


class NeedsReauth(Exception):
    """The stored OAuth grant is no longer valid (expired, revoked, password
    change, or consent withdrawn). Retrying cannot fix it: the user must
    reconnect the account."""
    def __init__(self, provider, detail=""):
        self.provider = provider
        super().__init__(
            f"{provider} rejected the stored credentials{': ' + detail if detail else ''}. "
            "The account must be reconnected. The refresh token is no longer valid "
            "(revoked, expired, or consent withdrawn).")


def _open_or_explain(req, timeout=15):
    """urlopen that converts a network failure into a message naming the exact
    host. A bare 'getaddrinfo failed' tells an operator nothing about which of
    several providers is unreachable."""
    import urllib.error as _ue
    import urllib.parse as _up
    try:
        return urllib.request.urlopen(req, timeout=timeout)
    except _ue.HTTPError as e:
        host = _up.urlsplit(req.full_url).hostname or ""
        if "googleapis.com" in host and e.code in (401, 403):
            detail = _provider_error_text(e)
            low = (detail or "").lower()
            # Distinguish "the project is misconfigured" from "the grant is dead".
            # Only the latter is fixed by reconnecting.
            api_disabled = any(k in low for k in (
                "has not been used in project", "is disabled", "accessnotconfigured",
                "service_disabled", "api has not been used", "enable it by visiting"))
            if api_disabled:
                raise ProviderApiDisabled("Google", detail) from None
            if e.code == 403 and "insufficient" in low:
                raise ProviderScopeError("Google", detail) from None
            raise NeedsReauth("Google", detail) from None
        raise
    except _ue.URLError as e:
        host = _up.urlsplit(req.full_url).hostname or req.full_url
        raise ProviderUnreachable(host, req.full_url, getattr(e, "reason", e)) from None


def google_configured() -> bool:
    return bool(os.environ.get("GOOGLE_CLIENT_ID") and os.environ.get("GOOGLE_CLIENT_SECRET"))


def google_auth_url(state: str) -> str:
    params = {
        "client_id": os.environ["GOOGLE_CLIENT_ID"],
        "redirect_uri": os.environ.get("GOOGLE_REDIRECT_URI", "http://localhost:8787/oauth/gmail/callback"),
        "response_type": "code",
        "scope": "https://www.googleapis.com/auth/gmail.readonly",
        "access_type": "offline",
        "prompt": "consent",
        "state": state,
    }
    return "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode(params)


def google_exchange_code(code: str) -> dict:
    """Authorization-code exchange. Returns access/refresh tokens. Real HTTP."""
    data = urllib.parse.urlencode({
        "code": code,
        "client_id": os.environ["GOOGLE_CLIENT_ID"],
        "client_secret": os.environ["GOOGLE_CLIENT_SECRET"],
        "redirect_uri": os.environ.get("GOOGLE_REDIRECT_URI", "http://localhost:8787/oauth/gmail/callback"),
        "grant_type": "authorization_code",
    }).encode()
    req = urllib.request.Request("https://oauth2.googleapis.com/token", data=data)
    with _open_or_explain(req) as r:
        return json.loads(r.read())


def google_refresh(refresh_token: str) -> dict:
    data = urllib.parse.urlencode({
        "refresh_token": refresh_token,
        "client_id": os.environ["GOOGLE_CLIENT_ID"],
        "client_secret": os.environ["GOOGLE_CLIENT_SECRET"],
        "grant_type": "refresh_token",
    }).encode()
    req = urllib.request.Request("https://oauth2.googleapis.com/token", data=data)
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        detail = _provider_error_text(e)
        low = (detail or "").lower()
        if "invalid_grant" in low:
            # THE genuine reconnect case: Google's token endpoint says the
            # refresh token itself is dead (revoked / expired / consent
            # withdrawn / password change).
            raise NeedsReauth("Google", "token endpoint returned invalid_grant "
                              "(the refresh token was revoked or has expired)") from None
        if "invalid_client" in low or "unauthorized_client" in low:
            # Operator misconfiguration, NOT a user problem. Reconnecting
            # cannot fix a wrong client id/secret.
            raise ProviderConfigError("Google", detail or "invalid_client") from None
        raise
    except urllib.error.URLError as e:
        raise ProviderUnreachable("oauth2.googleapis.com",
                                  "https://oauth2.googleapis.com/token",
                                  getattr(e, "reason", e)) from None


class RealGmailTransport(GmailTransport):
    """Calls gmail.googleapis.com users.messages. Handles pagination and 429
    backoff. Cursor is Gmail's pageToken (list) chained with a stored historyId
    for incremental sync in a fuller implementation; here we page list results."""
    # Gmail-side filter. Excludes the bulk categories and automated senders that
    # dominate a real mailbox, so we never even download them. Overridable per
    # connector via config.query.
    DEFAULT_QUERY = ("-in:chats -category:promotions -category:social "
                     "-category:forums -category:updates "
                     "-from:noreply -from:no-reply -from:donotreply "
                     "-from:notifications -from:mailer-daemon")

    def __init__(self, refresh_token: str, query: str | None = None,
                 access_token: str | None = None, expires: float | None = None,
                 on_token=None):
        self.refresh_token = refresh_token
        self.query = query if query is not None else self.DEFAULT_QUERY
        # Google access tokens live ~1 hour. We use the stored one only while
        # it is still valid (60s safety margin), refresh via the refresh token
        # otherwise, and persist the fresh token through on_token so the next
        # poll inside the hour reuses it. THE STORED ACCESS TOKEN EXPIRING IS
        # NORMAL and must never be reported as "reconnect the account".
        self._access_token = access_token
        try:
            self._expires = float(expires or 0)
        except (TypeError, ValueError):
            self._expires = 0.0
        self._on_token = on_token

    def _ensure_access(self, force: bool = False) -> str:
        if not force and self._access_token and time.time() < self._expires - 60:
            return self._access_token
        tok = google_refresh(self.refresh_token)  # NeedsReauth ONLY on invalid_grant
        self._access_token = tok["access_token"]
        self._expires = time.time() + float(tok.get("expires_in", 3600))
        if self._on_token is not None:
            try:
                self._on_token(self._access_token, self._expires)
            except Exception:
                pass  # persistence failure must not break the sync
        return self._access_token

    def _access(self):
        return self._ensure_access()

    def _gmail_get(self, url: str, retried: bool = False) -> dict:
        """One authenticated Gmail API GET. A 401 with a possibly-stale token
        triggers exactly one forced refresh + retry; only if a FRESH token is
        also rejected do we surface reauth (and say so honestly)."""
        req = urllib.request.Request(
            url, headers={"Authorization": f"Bearer {self._ensure_access()}"})
        try:
            with _open_or_explain(req) as r:
                return json.loads(r.read())
        except NeedsReauth:
            if retried:
                raise NeedsReauth(
                    "Google", "Gmail rejected even a freshly refreshed access "
                    "token, the grant's scopes or account state changed") from None
            self._ensure_access(force=True)
            return self._gmail_get(url, retried=True)

    def list_messages(self, access_token, after_cursor):
        # NOTE: the access_token argument is the value stored at connect time
        # and is usually EXPIRED. Token lifecycle is owned here; the argument
        # is ignored by design (kept for interface compatibility).
        base = "https://gmail.googleapis.com/gmail/v1/users/me/messages"
        params = {"maxResults": "25"}
        if self.query:
            params["q"] = self.query
        if after_cursor:
            params["pageToken"] = after_cursor
        listing = {}
        for attempt in range(4):
            try:
                listing = self._gmail_get(base + "?" + urllib.parse.urlencode(params))
                break
            except urllib.error.HTTPError as e:
                if e.code in (429, 500, 503) and attempt < 3:
                    time.sleep(2 ** attempt)
                    continue
                raise
        next_token = listing.get("nextPageToken")
        out = []
        for m in listing.get("messages", []):
            out.append(self._gmail_get(f"{base}/{m['id']}?format=raw"))
        return out, next_token


# ── Real OpenAI-compatible LLM ─────────────────────────────────────────────
def llm_configured() -> bool:
    return bool(os.environ.get("OMEM_LLM_API_KEY"))


def dns_check(url: str) -> dict:
    """Resolve the host of a provider URL. Separates 'bad config' from 'network
    blocked', the two causes of getaddrinfo failures."""
    import socket
    import urllib.parse as _up
    parts = _up.urlsplit(url or "")
    host = parts.hostname
    out = {"url": url, "host": host, "scheme": parts.scheme}
    if parts.scheme not in ("http", "https"):
        out["ok"] = False
        out["error"] = (f"OMEM_LLM_BASE_URL is not a valid http(s) URL: {url!r}. "
                        "It must look like https://api.groq.com/openai/v1")
        return out
    if not host:
        out["ok"] = False
        out["error"] = f"No hostname could be parsed from {url!r}."
        return out
    try:
        infos = socket.getaddrinfo(host, parts.port or (443 if parts.scheme == "https" else 80))
        out["ok"] = True
        out["addresses"] = sorted({i[4][0] for i in infos})
    except Exception as e:
        out["ok"] = False
        out["error"] = (f"DNS lookup for {host} failed ({e}). Either the hostname "
                        "is misspelled, or this machine cannot resolve it "
                        "(VPN, corporate DNS, or firewall).")
    return out


def _provider_error_text(err) -> str:
    """Providers return a JSON body explaining a rejection. Discarding it forces
    the operator to guess, so surface the provider's own words."""
    try:
        raw = err.read()
    except Exception:
        return ""
    try:
        data = json.loads(raw)
    except Exception:
        return (raw or b"").decode("utf-8", "replace")[:200].strip()
    if isinstance(data, dict):
        e = data.get("error")
        if isinstance(e, dict):
            return str(e.get("message") or e.get("code") or "")[:200]
        if isinstance(e, str):
            return e[:200]
        return str(data.get("message") or "")[:200]
    return str(data)[:200]


def _host_of(url: str) -> str:
    try:
        return urllib.parse.urlsplit(url).netloc or url
    except Exception:
        return url


class OpenAICompatClient(LLMClient):
    """Vendor-agnostic chat-completions client. Works with OpenAI, Together,
    Groq, local vLLM. Any /chat/completions endpoint. Records model + token
    usage via the usage callback. Timeout + retry + structured output."""
    def __init__(self, usage_cb=None):
        self.base = os.environ.get("OMEM_LLM_BASE_URL", "https://api.openai.com/v1")
        self.key = os.environ["OMEM_LLM_API_KEY"]
        self.model = os.environ.get("OMEM_LLM_MODEL", "gpt-4o-mini")
        self.usage_cb = usage_cb

    def complete(self, system: str, user: str) -> str:
        # OpenAI-compatible providers reject json_object mode unless the word
        # "json" appears in the messages. Only request structured output when
        # the prompt actually asks for JSON, so non-JSON calls (health checks)
        # remain valid.
        payload = {
            "model": self.model,
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": user}],
            "temperature": 0,
        }
        if "json" in f"{system}\n{user}".lower():
            payload["response_format"] = {"type": "json_object"}
        body = json.dumps(payload).encode()
        for attempt in range(3):
            req = urllib.request.Request(
                f"{self.base}/chat/completions", data=body,
                headers={"Content-Type": "application/json",
                         "Authorization": f"Bearer {self.key}",
                         # Several providers sit behind WAFs that reject the
                         # default python-urllib agent outright.
                         "User-Agent": "omem-cloud/1.0",
                         "Accept": "application/json"})
            try:
                with urllib.request.urlopen(req, timeout=30) as r:
                    resp = json.loads(r.read())
                break
            except urllib.error.HTTPError as e:
                if e.code in (429, 500, 502, 503) and attempt < 2:
                    time.sleep(2 ** attempt)
                    continue
                detail = _provider_error_text(e)
                if e.code in (401, 403):
                    raise RuntimeError(
                        f"{_host_of(self.base)} refused the request (HTTP {e.code})"
                        f"{': ' + detail if detail else ''}. Usual causes: the API key "
                        f"is wrong or revoked, the key is for a different provider, "
                        f"or the model {self.model!r} is not enabled for this key."
                    ) from None
                if e.code == 404:
                    raise RuntimeError(
                        f"{_host_of(self.base)} returned 404"
                        f"{': ' + detail if detail else ''}. Check OMEM_LLM_BASE_URL "
                        f"ends with the provider's OpenAI-compatible path and that "
                        f"model {self.model!r} exists.") from None
                raise RuntimeError(
                    f"{_host_of(self.base)} returned HTTP {e.code}"
                    f"{': ' + detail if detail else ''}") from None
            except urllib.error.URLError as e:
                # DNS / TCP failure: retrying a bad hostname never helps
                raise ProviderUnreachable(
                    _host_of(self.base), f"{self.base}/chat/completions",
                    getattr(e, "reason", e),
                    hint="Check OMEM_LLM_BASE_URL is exactly the provider's "
                         "OpenAI-compatible endpoint.") from None
        if self.usage_cb and "usage" in resp:
            self.usage_cb(self.model, resp["usage"].get("total_tokens", 0))
        return resp["choices"][0]["message"]["content"]


# ── Real Stripe (test mode) ────────────────────────────────────────────────
def stripe_configured() -> bool:
    return bool(os.environ.get("STRIPE_SECRET_KEY"))


def _stripe(path, data=None, method="POST"):
    key = os.environ["STRIPE_SECRET_KEY"]
    url = f"https://api.stripe.com/v1/{path}"
    body = urllib.parse.urlencode(data).encode() if data else None
    req = urllib.request.Request(url, data=body, method=method,
                                 headers={"Authorization": f"Bearer {key}"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())


def stripe_create_customer(email: str) -> dict:
    return _stripe("customers", {"email": email})


def stripe_create_checkout(customer: str, price_id: str, success_url: str, cancel_url: str) -> dict:
    return _stripe("checkout/sessions", {
        "customer": customer, "mode": "subscription",
        "line_items[0][price]": price_id, "line_items[0][quantity]": "1",
        "success_url": success_url, "cancel_url": cancel_url})


def stripe_billing_portal(customer: str, return_url: str) -> dict:
    return _stripe("billing_portal/sessions", {"customer": customer, "return_url": return_url})


# ── Stripe webhook signature verification (Stripe's documented scheme) ─────
def stripe_verify_signature(payload: bytes, sig_header: str, secret: str, tolerance=300) -> bool:
    """Verify per https://stripe.com/docs/webhooks/signatures:
    header 't=<ts>,v1=<hmac>'; signed_payload = f"{ts}.{payload}";
    v1 = HMAC-SHA256(secret, signed_payload). Constant-time compare + replay window."""
    import hmac as _hmac
    import hashlib as _hl
    try:
        parts = dict(kv.split("=", 1) for kv in sig_header.split(","))
        ts = int(parts["t"])
        v1 = parts["v1"]
    except Exception:
        return False
    if abs(time.time() - ts) > tolerance:
        return False
    signed = f"{ts}.".encode() + payload
    expect = _hmac.new(secret.encode(), signed, _hl.sha256).hexdigest()
    return _hmac.compare_digest(v1, expect)


def stripe_sign_payload(payload: bytes, secret: str, ts: int | None = None) -> str:
    """Build a valid Stripe-Signature header (used by tests to self-sign events)."""
    import hmac as _hmac
    import hashlib as _hl
    ts = ts or int(time.time())
    signed = f"{ts}.".encode() + payload
    return f"t={ts},v1={_hmac.new(secret.encode(), signed, _hl.sha256).hexdigest()}"
