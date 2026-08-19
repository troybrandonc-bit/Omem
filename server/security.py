"""Security primitives: auth rate limiting + secure OAuth state.

Both are REAL and enforced. The rate limiter is an in-memory token bucket keyed
by client ip+route (single-node; a Redis backend would swap in for multi-node).
OAuth state is a signed, single-use, expiring nonce that binds the callback to
the project that initiated it, preventing CSRF on the OAuth flow.
"""
from __future__ import annotations
import hmac
import hashlib
import os
import secrets
import time


def _safe_int(v: str) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0


class RateLimiter:
    def __init__(self, capacity=5, refill_per_sec=0.2):
        # 5 requests burst, then 1 every 5s per key (tuned for auth endpoints)
        self.capacity = capacity
        self.refill = refill_per_sec
        self._buckets: dict[str, tuple[float, float]] = {}  # key -> (tokens, last_ts)

    # A bucket is only interesting until it has refilled to capacity; after that
    # it is indistinguishable from a key never seen before. Without this the dict
    # grew forever — one entry per client IP on the auth routes, one per
    # project+credential on the data routes — in a process that is meant to stay
    # up for months. Anyone rotating source addresses could grow it deliberately.
    PRUNE_EVERY = 1024

    def _prune(self, now: float) -> None:
        full = self.capacity / self.refill if self.refill else 0
        self._buckets = {k: v for k, v in self._buckets.items()
                         if now - v[1] < full}

    def allow(self, key: str) -> bool:
        now = time.time()
        if len(self._buckets) >= self.PRUNE_EVERY:
            self._prune(now)
        tokens, last = self._buckets.get(key, (self.capacity, now))
        tokens = min(self.capacity, tokens + (now - last) * self.refill)
        if tokens < 1:
            self._buckets[key] = (tokens, now)
            return False
        self._buckets[key] = (tokens - 1, now)
        return True


class OAuthStateStore:
    """Signed, single-use, expiring OAuth state values. Binds callback to the
    initiating project so a stolen/forged callback cannot connect a foreign
    account. Signature uses an env secret; state expires in 10 minutes."""
    def __init__(self, secret: str | None = None, ttl=600):
        self.secret = (secret or os.environ.get("OMEM_MASTER_KEY", "dev-master-key-change-me")).encode()
        self.ttl = ttl
        self._used: set[str] = set()

    def issue(self, project_id: str, connector_id: str) -> str:
        nonce = secrets.token_hex(8)
        ts = str(int(time.time()))
        payload = f"{project_id}:{connector_id}:{ts}:{nonce}"
        sig = hmac.new(self.secret, payload.encode(), hashlib.sha256).hexdigest()[:16]
        return f"{payload}:{sig}"

    def verify(self, state: str) -> dict | None:
        try:
            project_id, connector_id, ts, nonce, sig = state.split(":")
        except ValueError:
            return None
        payload = f"{project_id}:{connector_id}:{ts}:{nonce}"
        expect = hmac.new(self.secret, payload.encode(), hashlib.sha256).hexdigest()[:16]
        if not hmac.compare_digest(sig, expect):
            return None
        if time.time() - int(ts) > self.ttl:
            return None
        if state in self._used:
            return None  # single-use
        # A state older than the TTL is already rejected above, so remembering
        # it past that point protects nothing — but the set had no eviction and
        # grew for the life of the process, one entry per OAuth attempt. Sweep
        # the expired entries whenever it gets big; replay is still impossible
        # because expiry catches anything old enough to have been dropped.
        if len(self._used) >= 4096:
            cutoff = time.time() - self.ttl
            self._used = {u for u in self._used
                          if len(u.split(":")) == 5 and _safe_int(u.split(":")[2]) > cutoff}
        self._used.add(state)
        return {"project_id": project_id, "connector_id": connector_id}


# ── TOTP MFA (RFC 6238; stdlib only) ───────────────────────────────────────
import base64
import struct


def totp_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")


def totp_code(secret: str, at: float | None = None, step=30, digits=6) -> str:
    key = base64.b32decode(secret + "=" * (-len(secret) % 8))
    counter = int((at if at is not None else time.time()) // step)
    msg = struct.pack(">Q", counter)
    digest = hmac.new(key, msg, hashlib.sha1).digest()
    off = digest[-1] & 0x0F
    code = (struct.unpack(">I", digest[off:off + 4])[0] & 0x7FFFFFFF) % (10 ** digits)
    return str(code).zfill(digits)


def totp_verify(secret: str, code: str, window=1) -> bool:
    """Accept the current step ± window (clock skew). Constant-time compare."""
    now = time.time()
    for w in range(-window, window + 1):
        if hmac.compare_digest(totp_code(secret, now + w * 30), str(code)):
            return True
    return False


# ── SSRF guard ──────────────────────────────────────────────────────────────
# Tenant-configured connector URLs (e.g. Salesforce instance_url) flow into
# outbound HTTP. Without validation a tenant could point OMEM at internal hosts
# or cloud metadata (169.254.169.254) — a classic SSRF. safe_url() enforces
# https + a public destination and is called before any tenant-URL fetch.
import ipaddress as _ipaddress
import socket as _socket
import urllib.parse as _urlparse


class SSRFError(Exception):
    pass


_BLOCKED_HOSTS = {"metadata.google.internal", "metadata", "localhost"}


def _ip_is_public(ip_str: str) -> bool:
    try:
        ip = _ipaddress.ip_address(ip_str)
    except ValueError:
        return False
    # Block loopback, private, link-local (169.254.x = cloud metadata),
    # multicast, reserved, unspecified.
    return not (ip.is_private or ip.is_loopback or ip.is_link_local
                or ip.is_multicast or ip.is_reserved or ip.is_unspecified)


def safe_url(url: str, *, allow_http: bool = False) -> str:
    """Validate a tenant-supplied URL for outbound fetch. Returns the URL if safe,
    else raises SSRFError. Enforces https (unless allow_http), a hostname that is
    not a known-internal name, and — after DNS resolution — a PUBLIC destination
    IP, so a hostname that resolves to a private/link-local/metadata address is
    rejected (defends against DNS-rebinding-style config)."""
    if not url or not isinstance(url, str):
        raise SSRFError("empty url")
    parts = _urlparse.urlparse(url)
    scheme = (parts.scheme or "").lower()
    if scheme not in ("https",) and not (allow_http and scheme == "http"):
        raise SSRFError(f"scheme not allowed: {scheme or '(none)'}")
    host = parts.hostname
    if not host:
        raise SSRFError("no host")
    if host.lower() in _BLOCKED_HOSTS:
        raise SSRFError(f"blocked host: {host}")
    # If the host is a literal IP, check it directly.
    try:
        _ipaddress.ip_address(host)
        if not _ip_is_public(host):
            raise SSRFError(f"non-public ip: {host}")
        return url
    except ValueError:
        pass  # not a literal IP — resolve it
    # Resolve every A/AAAA record; ALL must be public (a single private answer
    # is a rebinding vector).
    try:
        infos = _socket.getaddrinfo(host, parts.port or (443 if scheme == "https" else 80),
                                    proto=_socket.IPPROTO_TCP)
    except _socket.gaierror as e:
        raise SSRFError(f"dns resolution failed: {host}") from e
    resolved = {ai[4][0] for ai in infos}
    if not resolved:
        raise SSRFError(f"no addresses for host: {host}")
    for ip in resolved:
        if not _ip_is_public(ip):
            raise SSRFError(f"host resolves to non-public ip: {host} -> {ip}")
    return url
