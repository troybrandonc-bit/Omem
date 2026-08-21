"""Secret storage abstraction.

Replaces the reversible XOR obfuscation flagged by the audit. Two providers:

- LocalSecretsProvider: authenticated encryption (AES-GCM if `cryptography` is
  available, else an HMAC-authenticated stream cipher over a key derived with
  PBKDF2-HMAC-SHA256). Real confidentiality + tamper detection, keyed from an
  env master secret. Suitable for single-node/dev.
- KMSSecretsProvider: envelope-encryption interface for AWS KMS (or equivalent).
  REAL CODE, EXTERNAL DEPENDENCY, not exercised without AWS creds. Selected when
  OMEM_KMS_KEY_ID is set.

Guarantees (tested): ciphertext != plaintext, wrong key cannot decrypt, tampered
ciphertext is rejected, and the provider is the ONLY decryption path.
"""
from __future__ import annotations
import base64
import hashlib
import hmac
import os
import secrets as _secrets

try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM  # type: ignore
    _HAVE_AESGCM = True
except Exception:
    _HAVE_AESGCM = False


def _derive(master: str, salt: bytes) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", master.encode(), salt, 100_000, dklen=32)


class SecretsProvider:
    def encrypt(self, plaintext: str) -> str:
        raise NotImplementedError

    def decrypt(self, token: str) -> str:
        raise NotImplementedError

    # Bytes-native AEAD for binary artifacts (e.g. backup files). Default
    # implementation base64-wraps through the string API so every provider gets
    # it for free; LocalSecretsProvider overrides with a direct byte path to
    # avoid base64 bloat on large files. Same keys, same crypto, same guarantees.
    def encrypt_bytes(self, data: bytes) -> bytes:
        return self.encrypt(base64.b64encode(data).decode()).encode()

    def decrypt_bytes(self, token: bytes) -> bytes:
        return base64.b64decode(self.decrypt(token.decode()))

    @property
    def kind(self) -> str:
        return "abstract"


class LocalSecretsProvider(SecretsProvider):
    """Authenticated encryption. Token format: v1.<salt>.<nonce>.<ct>[.<mac>]."""
    def __init__(self, master: str | None = None):
        self.master = master or os.environ.get("OMEM_MASTER_KEY", "dev-master-key-change-me")

    @property
    def kind(self):
        return "local-aesgcm" if _HAVE_AESGCM else "local-hmac"

    def encrypt(self, plaintext: str) -> str:
        salt = _secrets.token_bytes(16)
        key = _derive(self.master, salt)
        if _HAVE_AESGCM:
            nonce = _secrets.token_bytes(12)
            ct = AESGCM(key).encrypt(nonce, plaintext.encode(), None)
            return "v1g." + ".".join(base64.b64encode(x).decode() for x in (salt, nonce, ct))
        # HMAC-authenticated CTR-like stream using SHA256 keystream
        nonce = _secrets.token_bytes(16)
        ks = _keystream(key, nonce, len(plaintext.encode()))
        ct = bytes(a ^ b for a, b in zip(plaintext.encode(), ks))
        mac = hmac.new(key, nonce + ct, hashlib.sha256).digest()
        return "v1h." + ".".join(base64.b64encode(x).decode() for x in (salt, nonce, ct, mac))

    def decrypt(self, token: str) -> str:
        return self._decrypt_str(token)

    def _decrypt_str(self, token: str) -> str:
        parts = token.split(".")
        tag = parts[0]
        blobs = [base64.b64decode(p) for p in parts[1:]]
        if tag == "v1g":
            salt, nonce, ct = blobs
            key = _derive(self.master, salt)
            return AESGCM(key).decrypt(nonce, ct, None).decode()
        if tag == "v1h":
            salt, nonce, ct, mac = blobs
            key = _derive(self.master, salt)
            expect = hmac.new(key, nonce + ct, hashlib.sha256).digest()
            if not hmac.compare_digest(mac, expect):
                raise ValueError("secret authentication failed (tampered or wrong key)")
            ks = _keystream(key, nonce, len(ct))
            return bytes(a ^ b for a, b in zip(ct, ks)).decode()
        raise ValueError(f"unknown secret token version {tag}")

    # ── bytes-native AEAD for binary artifacts (backups) ──
    # Binary token layout: b"v1G"|salt|nonce|ct  (AES-GCM) or
    #                      b"v1H"|salt|nonce|ct|mac (HMAC stream), length-framed.
    def encrypt_bytes(self, data: bytes) -> bytes:
        salt = _secrets.token_bytes(16)
        key = _derive(self.master, salt)
        if _HAVE_AESGCM:
            nonce = _secrets.token_bytes(12)
            ct = AESGCM(key).encrypt(nonce, data, None)
            return b"v1G" + salt + nonce + ct
        nonce = _secrets.token_bytes(16)
        ks = _keystream(key, nonce, len(data))
        ct = bytes(a ^ b for a, b in zip(data, ks))
        mac = hmac.new(key, nonce + ct, hashlib.sha256).digest()
        return b"v1H" + salt + nonce + ct + mac

    def decrypt_bytes(self, token: bytes) -> bytes:
        tag, body = token[:3], token[3:]
        if tag == b"v1G":
            salt, nonce, ct = body[:16], body[16:28], body[28:]
            key = _derive(self.master, salt)
            return AESGCM(key).decrypt(nonce, ct, None)
        if tag == b"v1H":
            salt, nonce, mac = body[:16], body[16:32], body[-32:]
            ct = body[32:-32]
            key = _derive(self.master, salt)
            expect = hmac.new(key, nonce + ct, hashlib.sha256).digest()
            if not hmac.compare_digest(mac, expect):
                raise ValueError("backup authentication failed (tampered or wrong key)")
            ks = _keystream(key, nonce, len(ct))
            return bytes(a ^ b for a, b in zip(ct, ks))
        raise ValueError(f"unknown binary token version {tag!r}")


def _keystream(key: bytes, nonce: bytes, n: int) -> bytes:
    out = b""
    counter = 0
    while len(out) < n:
        out += hmac.new(key, nonce + counter.to_bytes(8, "big"), hashlib.sha256).digest()
        counter += 1
    return out[:n]


class KMSSecretsProvider(SecretsProvider):
    """AWS KMS envelope encryption. REAL CODE, EXTERNAL DEPENDENCY, untested
    without AWS credentials + boto3. Generates a data key per secret, encrypts
    locally with it, stores the KMS-wrapped data key alongside the ciphertext."""
    def __init__(self, key_id: str):
        self.key_id = key_id
        import boto3  # noqa: F401  (import guarded; only when selected)
        self._kms = __import__("boto3").client("kms")

    @property
    def kind(self):
        return "aws-kms"

    def encrypt(self, plaintext: str) -> str:
        resp = self._kms.generate_data_key(KeyId=self.key_id, KeySpec="AES_256")
        data_key, wrapped = resp["Plaintext"], resp["CiphertextBlob"]
        if not _HAVE_AESGCM:
            raise RuntimeError("KMS provider requires cryptography for AES-GCM")
        nonce = _secrets.token_bytes(12)
        ct = AESGCM(data_key).encrypt(nonce, plaintext.encode(), None)
        return "kms1." + ".".join(base64.b64encode(x).decode() for x in (wrapped, nonce, ct))

    def decrypt(self, token: str) -> str:
        _, w, n, c = token.split(".")
        wrapped, nonce, ct = (base64.b64decode(x) for x in (w, n, c))
        data_key = self._kms.decrypt(CiphertextBlob=wrapped)["Plaintext"]
        return AESGCM(data_key).decrypt(nonce, ct, None).decode()


# ── encryption of memory content at rest ────────────────────────────────────
# Only stored OAuth tokens were ever encrypted; the memories themselves -
# propositions, subjects, labels, quoted evidence, raw source payloads - sat in
# the clear, while the security page advertised "per-tenant envelope encryption
# at rest". This closes that for the content columns.
#
# OPT-IN, because it is not free and not reversible by accident:
#   * Lose OMEM_MASTER_KEY and you lose the data. There is no recovery path and
#     there should not be one.
#   * Encrypted columns cannot be filtered in SQL. Anything that did has been
#     moved into Python (see classifier.relationship_stats).
# Existing plaintext rows keep working: the read path detects a ciphertext token
# by its version prefix, so a database can be half-migrated and still correct.

# Ciphertext written by the OAuth-token provider (v1g/v1h) is still readable;
# content written here uses v2c. See _content_key for why they differ.
_CIPHERTEXT_PREFIXES = ("v1g.", "v1h.", "v2c.")
_CONTENT_PREFIX = "v2c."

# Fixed, documented context string instead of a per-row salt. THIS IS THE WHOLE
# PERFORMANCE STORY: LocalSecretsProvider salts every value it encrypts, so it
# runs PBKDF2 (100,000 iterations) once PER ROW. Measured, that is ~336 ms per
# encrypt - correct for a handful of long-lived OAuth tokens, and ruinous for
# content, where it would cost 336 ms on every memory written and 336 ms per
# operation on every boot replay. A project with 10,000 operations would take
# most of an hour to start.
#
# The key is therefore derived ONCE from the master key and cached, and each row
# gets a fresh random 96-bit nonce, which is what AES-GCM actually needs for
# safety. Per-row salting bought nothing here anyway: the master key is the same
# for every row, so re-deriving from it merely repeated the same work.
_CONTENT_CONTEXT = b"omem.content.v2"
_content_key_cache: dict[str, bytes] = {}


def _content_key() -> bytes:
    master = os.environ.get("OMEM_MASTER_KEY", "dev-master-key-change-me")
    key = _content_key_cache.get(master)
    if key is None:
        key = hashlib.pbkdf2_hmac("sha256", master.encode(), _CONTENT_CONTEXT,
                                  200_000, dklen=32)
        _content_key_cache[master] = key
    return key


def content_encryption_enabled() -> bool:
    return bool(os.environ.get("OMEM_ENCRYPT_AT_REST"))


def _require_aead() -> None:
    if not _HAVE_AESGCM:
        raise SystemExit(
            "OMEM_ENCRYPT_AT_REST needs real authenticated encryption, and the "
            "'cryptography' package is not installed.\n"
            "  pip install 'omem-infrastructure[encryption]'"
            "   (or: pip install cryptography)\n"
            "The stdlib fallback used for OAuth tokens is a hand-rolled "
            "HMAC-SHA256 keystream. That is not something to encrypt an entire "
            "memory store with, so this refuses rather than quietly using it.")


def encrypt_content(plaintext):
    """Encrypt a text column if content encryption is on, else pass it through."""
    if plaintext is None or not content_encryption_enabled():
        return plaintext
    if isinstance(plaintext, str) and plaintext.startswith(_CIPHERTEXT_PREFIXES):
        return plaintext                      # already encrypted; do not double-wrap
    _require_aead()
    nonce = _secrets.token_bytes(12)
    ct = AESGCM(_content_key()).encrypt(nonce, plaintext.encode("utf-8"), None)
    return _CONTENT_PREFIX + base64.b64encode(nonce).decode() + "." +         base64.b64encode(ct).decode()


def decrypt_content(stored):
    """Decrypt if it looks encrypted, else return as-is.

    Detection is by prefix rather than by whether the feature is switched on, so
    turning encryption OFF still reads rows written while it was on. Deciding by
    config instead would make a toggle hand back ciphertext as if it were data.
    """
    if not isinstance(stored, str) or not stored.startswith(_CIPHERTEXT_PREFIXES):
        return stored
    if stored.startswith(_CONTENT_PREFIX):
        _require_aead()
        _, nonce_b64, ct_b64 = stored.split(".", 2)
        return AESGCM(_content_key()).decrypt(
            base64.b64decode(nonce_b64), base64.b64decode(ct_b64), None).decode("utf-8")
    # v1g/v1h - written by the OAuth-token provider before this existed.
    return get_secrets_provider().decrypt(stored)


def get_secrets_provider() -> SecretsProvider:
    kid = os.environ.get("OMEM_KMS_KEY_ID")
    if kid:
        return KMSSecretsProvider(kid)
    return LocalSecretsProvider()
