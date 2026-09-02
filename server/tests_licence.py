"""Does the licence check actually check anything?
Run: python3 tests_licence.py

Hand-written crypto that only round-trips against itself proves nothing: sign
and verify can be wrong in the same direction and agree perfectly. So the first
section runs the RFC 8032 vectors, which are the only opinion that counts.

The rest is the commercial logic, and the case that matters most is the one
that nearly shipped: the first draft carried a placeholder issuer key that
turned out to be the public key for the all-zero seed, so anyone could have
minted a licence with thirty-two zero bytes. A stock build now trusts no key
and unlocks nothing, and the test below fails if that ever regresses.
"""
import binascii
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, ".."))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import licence as L  # noqa: E402
from sign_licence import public_key, sign, _b64  # noqa: E402

PASS = FAIL = 0


def check(n, c, d=""):
    global PASS, FAIL
    if c:
        PASS += 1
        print("  ok  " + n)
    else:
        FAIL += 1
        print("  FAIL " + n + "  " + str(d)[:220])


print("== RFC 8032, the only opinion that counts ==")
VECTORS = [
    ("9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60",
     "d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a", "",
     "e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e06522490155"
     "5fb8821590a33bacc61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b"),
    ("4ccd089b28ff96da9db6c346ec114e0f5b8a319f35aba624da8cf6ed4fb8a6fb",
     "3d4017c3e843895a92b70aa74d1b7ebc9c982ccf2ec4968cc0cd55f12af4660c", "72",
     "92a009a9f0d4cab8720e820b5f642540a2b27b5416503f8fb3762223ebdb69da"
     "085ac1e43e15996e458f3613d0f11d8c387b2eaeb4302aeeb00d291612bb0c00"),
    ("c5aa8df43f9f837bedb7442f31dcb7b166d38535076f094b85ce3a2e0b4458f7",
     "fc51cd8e6218a1a38da47ed00230f0580816ed13ba3303ac5deb911548908025", "af82",
     "6291d657deec24024827e69c3abe01a30ce548a284743a445e3680d7db5ac3ac"
     "18ff9b538d16f290ae67f760984dc6594a7c15e9716ed28dc027beceea1ec40a"),
]
for seed_h, pub_h, msg_h, sig_h in VECTORS:
    seed, msg = binascii.unhexlify(seed_h), binascii.unhexlify(msg_h)
    check("vector %r derives the published public key" % (msg_h or "empty"),
          binascii.hexlify(public_key(seed)).decode() == pub_h)
    check("vector %r produces the published signature" % (msg_h or "empty"),
          binascii.hexlify(sign(seed, msg)).decode() == sig_h)
    check("vector %r verifies" % (msg_h or "empty"),
          L.ed25519_verify(binascii.unhexlify(pub_h), msg,
                           binascii.unhexlify(sig_h)))

print("== a signature that should not verify, does not ==")
SEED = binascii.unhexlify(
    "9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60")
PUB = public_key(SEED)
good = sign(SEED, b"the message")
check("a tampered message is rejected",
      not L.ed25519_verify(PUB, b"the messagf", good))
check("a tampered signature is rejected",
      not L.ed25519_verify(PUB, b"the message", good[:-1] + bytes([good[-1] ^ 1])))
check("another key's signature is rejected",
      not L.ed25519_verify(public_key(b"\x01" * 32), b"the message", good))
check("a truncated signature is rejected, not crashed on",
      not L.ed25519_verify(PUB, b"the message", good[:60]))
check("garbage bytes are rejected, not crashed on",
      not L.ed25519_verify(PUB, b"the message", b"\xff" * 64))

print("== the key that nearly shipped ==")
ZERO_SEED_PUB = binascii.hexlify(public_key(b"\x00" * 32)).decode()
check("the all-zero seed's public key is the one that was almost hardcoded",
      ZERO_SEED_PUB == "3b6a27bcceb6a42d62a3a8d02a6f0d73653215771de243a63ac048"
                       "a18b59da29", ZERO_SEED_PUB)
check("a stock build trusts no issuer key at all",
      L.ISSUER_PUBLIC_KEY == "" or
      L.ISSUER_PUBLIC_KEY != ZERO_SEED_PUB, L.ISSUER_PUBLIC_KEY)


def mint(seed, **claims):
    payload = json.dumps(claims, sort_keys=True, separators=(",", ":")).encode()
    return _b64(payload) + "." + _b64(sign(seed, payload))


def with_issuer(pub_hex, fn):
    """Run fn with a given issuer key installed, then put it back."""
    before = L.ISSUER_PUBLIC_KEY
    L.ISSUER_PUBLIC_KEY = pub_hex
    try:
        return fn()
    finally:
        L.ISSUER_PUBLIC_KEY = before


print("== licence tokens ==")
NOW = time.time()
ISSUER = binascii.hexlify(PUB).decode()
valid = mint(SEED, customer="Acme Ltd", issued=round(NOW),
             expires=round(NOW + 86400), features=["approval_policy"])

lic, why = with_issuer(ISSUER, lambda: L.parse(valid))
check("a licence signed by the issuer verifies", lic is not None and why is None, why)
check("and carries the customer it was issued to",
      lic and lic.customer == "Acme Ltd")
check("it unlocks the feature it names", lic and lic.has("approval_policy"))
check("and nothing it does not name", lic and not lic.has("auditor_export"))

forged = mint(b"\x02" * 32, customer="Acme Ltd", expires=round(NOW + 86400),
              features=["approval_policy", "auditor_export"])
lic2, why2 = with_issuer(ISSUER, lambda: L.parse(forged))
check("a licence signed by anyone else is refused",
      lic2 is None and "verify" in (why2 or ""), why2)

# the shape of the attack that matters: keep the signature, edit the claims
body, _, sig = valid.partition(".")
edited = _b64(json.dumps({"customer": "Acme Ltd", "expires": round(NOW + 86400),
                          "features": ["approval_policy", "auditor_export",
                                       "multi_project"]},
                         sort_keys=True, separators=(",", ":")).encode())
lic3, why3 = with_issuer(ISSUER, lambda: L.parse(edited + "." + sig))
check("adding features to a real licence invalidates it", lic3 is None, why3)

expired = mint(SEED, customer="Acme Ltd", expires=round(NOW - 60),
               features=["approval_policy"])
lic4, why4 = with_issuer(ISSUER, lambda: L.parse(expired))
check("an expired licence is reported as expired", why4 == "licence expired", why4)
check("and unlocks nothing", lic4 is not None and not lic4.has("approval_policy"))

print("== failing closed ==")
for junk in ("", "not-a-token", "aaa.bbb", "." , "a." + "b" * 88):
    got, reason = with_issuer(ISSUER, lambda j=junk: L.parse(j))
    check("junk %r is refused with a reason" % junk[:14],
          got is None and bool(reason), reason)
check("with no issuer key configured, even a real licence is refused",
      with_issuer("", lambda: L.parse(valid))[0] is None)
check("has() is false when nothing is configured", not L.has("approval_policy"))

print("== the status a human or auditor reads ==")
s = with_issuer(ISSUER, L.status)
check("an unlicensed install says so plainly, and names no secret",
      s["licensed"] is False and "reason" in s and "customer" not in s, s)
check("the catalogue lists what a licence could unlock",
      set(s["catalogue"]) == set(L.FEATURES))

os.environ["OMEM_LICENCE"] = valid
try:
    s2 = with_issuer(ISSUER, L.status)
    check("a licensed install reports the customer and the live features",
          s2["licensed"] and s2["customer"] == "Acme Ltd"
          and s2["features"] == ["approval_policy"], s2)
finally:
    os.environ.pop("OMEM_LICENCE", None)

print("== the server cannot issue a licence to itself ==")
src = open(os.path.join(HERE, "licence.py"), encoding="utf-8").read()
check("licence.py contains no signing routine",
      "def sign(" not in src and "_secret_scalar" not in src)

# Read the imports rather than grepping the text: the first version of this
# check searched the source for "socket" and failed on the docstring promising
# there wasn't one.
import ast  # noqa: E402
imported = set()
for node in ast.walk(ast.parse(src)):
    if isinstance(node, ast.Import):
        imported.update(a.name.split(".")[0] for a in node.names)
    elif isinstance(node, ast.ImportFrom) and node.module:
        imported.add(node.module.split(".")[0])
NETWORK = {"socket", "urllib", "http", "requests", "ssl", "asyncio", "ftplib",
           "telnetlib", "smtplib", "subprocess"}
check("it imports nothing that can reach the network, so the airgap holds",
      not (imported & NETWORK), sorted(imported))
check("and imports only the standard library it needs",
      imported <= {"base64", "binascii", "hashlib", "json", "os", "time",
                   "__future__"}, sorted(imported))

print("\n%d passed, %d failed" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)
