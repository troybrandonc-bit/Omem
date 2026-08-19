"""Secret storage abstraction.

Replaces the reversible XOR obfuscation flagged by the audit. Two providers:

- LocalSecretsProvider: authenticated encryption (AES-GCM if `cryptography` is
  available, else an HMAC-authenticated stream cipher over a key derived with
  PBKDF2-HMAC-SHA256). Real confidentiality + tamper detection, keyed from an
  env master secret. Suitable for single-node/dev.
- KMSSecretsProvider: envelope-encryption interface for AWS KMS (or equivalent).
  REAL CODE, EXTERNAL DEPENDENCY — not exercised without AWS creds. Selected when
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
    """AWS KMS envelope encryption. REAL CODE, EXTERNAL DEPENDENCY — untested
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


def get_secrets_provider() -> SecretsProvider:
    kid = os.environ.get("OMEM_KMS_KEY_ID")
    if kid:
        return KMSSecretsProvider(kid)
    return LocalSecretsProvider()
