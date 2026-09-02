#!/usr/bin/env python3
"""Mint a licence token. Runs on your machine, never on a server.

    # once. Writes the private key to a file with mode 0600 and prints only
    # the public half, because a secret printed to a terminal lives on in
    # scrollback and in session logs.
    python3 scripts/sign_licence.py --keygen --out ~/omem-licence.key

    # per customer
    python3 scripts/sign_licence.py --key <private-hex> \
        --customer "Acme Ltd" --days 365 \
        --features approval_policy,auditor_export

The customer sets OMEM_LICENCE to the printed token, or points
OMEM_LICENCE_FILE at a file containing it. Verification happens offline in
server/licence.py against the public half.

This file is the only place in the repository that can produce a valid licence,
and it is not part of the server or the wheel. That separation is deliberate:
someone who reads all of the shipped product still cannot issue themselves a
licence for it, and there is no key material anywhere near a running process.

Copyright 2026 Michael Brandon Clifford. MIT licensed.
"""
from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
import json
import os
import secrets
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "server"))
from licence import (_B, _L, _encodepoint, _scalarmult,  # noqa: E402
                     ed25519_verify, FEATURES, ISSUER_PUBLIC_KEY)


def _secret_scalar(seed: bytes) -> tuple:
    """The clamped scalar RFC 8032 derives from the seed hash: low three bits
    cleared so it is a multiple of the cofactor, bit 254 set and bit 255 clear
    so it sits in the right range. Getting this wrong produces signatures that
    verify locally and nowhere else."""
    h = hashlib.sha512(seed).digest()
    a = int.from_bytes(h[:32], "little")
    a &= (1 << 254) - 8
    a |= (1 << 254)
    return a, h


def public_key(seed: bytes) -> bytes:
    a, _ = _secret_scalar(seed)
    return _encodepoint(_scalarmult(_B, a))


def sign(seed: bytes, message: bytes) -> bytes:
    a, h = _secret_scalar(seed)
    pub = _encodepoint(_scalarmult(_B, a))
    r = int.from_bytes(hashlib.sha512(h[32:] + message).digest(), "little") % _L
    big_r = _encodepoint(_scalarmult(_B, r))
    k = int.from_bytes(hashlib.sha512(big_r + pub + message).digest(), "little") % _L
    s = (r + k * a) % _L
    return big_r + s.to_bytes(32, "little")


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def main() -> int:
    ap = argparse.ArgumentParser(description="Mint an OMEM licence token.")
    ap.add_argument("--keygen", action="store_true",
                    help="write a fresh key pair and exit")
    ap.add_argument("--out", default="omem-licence-private.key",
                    help="where to write the private key (never stdout)")
    ap.add_argument("--print-private", action="store_true",
                    help="print the private key to the terminal anyway. Do not "
                         "use this: terminals keep scrollback and sessions keep "
                         "transcripts, and both outlive your attention")
    ap.add_argument("--key-file", dest="key_file",
                    help="file holding the private key. Prefer this: a key "
                         "passed as an argument lands in your shell history, "
                         "the process list, and any transcript of the session")
    ap.add_argument("--key", help="private key as hex. Avoid; use --key-file")
    ap.add_argument("--customer", help="the organisation the licence is for")
    ap.add_argument("--days", type=int, default=365)
    ap.add_argument("--features", default="approval_policy,auditor_export")
    ap.add_argument("--note", default="")
    a = ap.parse_args()

    if a.keygen:
        seed = secrets.token_bytes(32)
        priv = binascii.hexlify(seed).decode()
        if a.print_private:
            print("private (now in your scrollback and this session's log):")
            print("  " + priv)
        else:
            # A secret printed to a terminal is a secret in scrollback, in the
            # session transcript, and in whatever ships those somewhere else.
            # The first version of this tool printed it, which is how the
            # first key ever generated with it had to be thrown away.
            if os.path.exists(a.out):
                print("refusing to overwrite %s" % a.out, file=sys.stderr)
                return 2
            fd = os.open(a.out, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "w") as f:
                f.write(priv + chr(10))
            # Report what the filesystem actually did rather than what was
            # asked for. Windows does not honour the POSIX mode, so the first
            # version of this line promised 0600 and delivered 0644, which is
            # a worse failure than saying nothing: it tells someone their key
            # is protected when it is readable by every account on the box.
            mode = os.stat(a.out).st_mode & 0o777
            print("private key written to %s" % a.out)
            if mode & 0o077:
                print("WARNING: that file is mode %o, readable beyond you." % mode)
                if os.name == "nt":
                    # Resolve the account name here rather than emitting
                    # %USERNAME%, which expands in cmd.exe and stays literal in
                    # bash and PowerShell. A command that only works in one of
                    # the three shells someone might paste it into is a command
                    # that fails, quietly, on their key file.
                    who = (os.environ.get("USERNAME")
                           or os.environ.get("USER") or "YOUR-ACCOUNT")
                    print("Windows ignores the POSIX mode. Restrict it with:")
                    print('  icacls "%s" /inheritance:r /grant:r "%s:F"'
                          % (os.path.abspath(a.out), who))
                else:
                    print("  chmod 600 %s" % a.out)
            print("Back it up once, somewhere that is not this repository, and")
            print("do not paste it anywhere. Losing it means reissuing every")
            print("licence; leaking it means anyone can mint their own.")
        print("public (paste into ISSUER_PUBLIC_KEY in server/licence.py):")
        print("  " + binascii.hexlify(public_key(seed)).decode())
        return 0

    if a.key_file:
        try:
            with open(os.path.expanduser(a.key_file), encoding="utf-8") as f:
                a.key = f.read().strip()
        except OSError as e:
            ap.error("could not read %s: %s" % (a.key_file, e))
    if not a.key or not a.customer:
        ap.error("--key-file (or --key) and --customer are required, "
                 "or --keygen to make a key")

    features = [f.strip() for f in a.features.split(",") if f.strip()]
    unknown = [f for f in features if f not in FEATURES]
    if unknown:
        # A typo here sells someone a feature that can never switch on, and
        # they would find out in production rather than at purchase.
        ap.error("unknown feature(s): %s\nknown: %s"
                 % (", ".join(unknown), ", ".join(sorted(FEATURES))))

    now = time.time()
    claims = {"customer": a.customer, "issued": round(now),
              "expires": round(now + a.days * 86400), "features": features}
    if a.note:
        claims["note"] = a.note
    # Sorted and compact so the same claims always produce the same bytes, and
    # a customer comparing two tokens sees a real difference or none.
    payload = json.dumps(claims, sort_keys=True, separators=(",", ":")).encode()

    seed = binascii.unhexlify(a.key.strip())
    signature = sign(seed, payload)
    if not ed25519_verify(public_key(seed), payload, signature):
        print("refusing to issue: the signature did not verify", file=sys.stderr)
        return 2

    token = _b64(payload) + "." + _b64(signature)
    print("# licence for %s, %d days, features: %s"
          % (a.customer, a.days, ", ".join(features)))
    print(token)
    if binascii.hexlify(public_key(seed)).decode() != ISSUER_PUBLIC_KEY:
        print("\nNOTE: this key is not the one compiled into server/licence.py,"
              "\nso this token will not verify on a stock build.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
