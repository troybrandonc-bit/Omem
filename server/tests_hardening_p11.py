"""TLS, audit hash chain, encryption at rest, and the single-writer lock.

These four were the "not yet" list on the security page: the server spoke only
plaintext HTTP, memory content sat in the clear, the audit log was append-only
by convention with nothing detecting an edit, and two processes against one
database silently kept two different engines.

Run: python3 tests_hardening_p11.py
"""
import json
import os
import ssl
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
os.makedirs(DATA, exist_ok=True)

_DB = os.path.join(DATA, "test_p11.db")
for _s in (_DB, _DB + "-wal", _DB + "-shm"):
    if os.path.exists(_s):
        os.remove(_s)
os.environ["OMEM_DB"] = _DB
os.environ["OMEM_SEED_DEMO"] = "0"
os.environ["OMEM_MASTER_KEY"] = "p11-test-key-definitely-not-the-default"

sys.path.insert(0, HERE)
import api  # noqa: E402
import enterprise as ent_mod  # noqa: E402
import secrets_provider  # noqa: E402
import store as store_mod  # noqa: E402

_passed = _failed = 0


def check(name, cond, detail=""):
    global _passed, _failed
    if cond:
        _passed += 1
        print(f"  ok  {name}")
    else:
        _failed += 1
        print(f"  FAIL {name} {detail}")


# ── the audit hash chain ────────────────────────────────────────────────────
print("== audit log is tamper-evident, not merely append-only ==")
E = api.ENT
ORG = "org_chain_test"
for i in range(6):
    E.audit("thing.happened", actor="u1", org_id=ORG, resource=f"r{i}",
            metadata={"i": i})

v = E.verify_audit_chain(ORG)
check("a fresh chain verifies", v["ok"] and v["checked"] == 6, str(v))
check("it reports a head hash to anchor off-system", bool(v["head"]))
HEAD = v["head"]

check("each row links to its predecessor",
      all(r["prev_hash"] for r in api.STORE.db.execute(
          "SELECT prev_hash FROM audit_events WHERE org_id=? AND seq>1", (ORG,)).fetchall()))

# editing a row in place - what someone with database access would do
api.STORE.db.execute("UPDATE audit_events SET resource='COVERED-UP' WHERE org_id=? AND seq=3", (ORG,))
api.STORE.db.commit()
v = E.verify_audit_chain(ORG)
check("an edited row is detected", not v["ok"], str(v))
check("  and named by sequence", (v["broken_at"] or {}).get("seq") == 3, str(v["broken_at"]))
check("  with the reason given", "altered" in (v["reason"] or ""), v["reason"])
check("  reporting how far it got", v["checked"] == 2, str(v["checked"]))

# put it back, then delete a row instead
api.STORE.db.execute("UPDATE audit_events SET resource='r2' WHERE org_id=? AND seq=3", (ORG,))
api.STORE.db.commit()
check("restoring the value restores the chain", E.verify_audit_chain(ORG)["ok"])

api.STORE.db.execute("DELETE FROM audit_events WHERE org_id=? AND seq=4", (ORG,))
api.STORE.db.commit()
v = E.verify_audit_chain(ORG)
check("a deleted row is detected", not v["ok"])
check("  and reported as a deletion", "deleted" in (v["reason"] or ""), v["reason"])

print("== chains are per-org, so one tenant cannot break another's ==")
OTHER = "org_untouched"
for i in range(3):
    E.audit("other.thing", org_id=OTHER, resource=str(i))
check("the untouched org still verifies", E.verify_audit_chain(OTHER)["ok"])

print("== rows written before hashing existed are not claimed as verified ==")
api.STORE.db.execute(
    "INSERT INTO audit_events(id,org_id,project_id,actor,action,resource,metadata,"
    "correlation_id,ts,seq,prev_hash,hash) VALUES('legacy1',?,NULL,NULL,'old.action',"
    "NULL,'{}',NULL,?,NULL,NULL,NULL)", (OTHER, time.time()))
api.STORE.db.commit()
v = E.verify_audit_chain(OTHER)
check("legacy rows counted separately, not as a break",
      v["ok"] and v["predates_chain"] == 1, str(v))

print("== the digest actually depends on the contents ==")
row = {"id": "x", "seq": 1, "org_id": "o", "project_id": None, "actor": "a",
       "action": "act", "resource": "r", "metadata": "{}", "correlation_id": None,
       "ts": 1234.5}
h1 = ent_mod._audit_digest("", row)
h2 = ent_mod._audit_digest("", {**row, "actor": "b"})
h3 = ent_mod._audit_digest("different-parent", row)
check("changing a field changes the hash", h1 != h2)
check("changing the parent changes the hash", h1 != h3)
check("the same input gives the same hash", h1 == ent_mod._audit_digest("", dict(row)))

# ── encryption of memory content at rest ────────────────────────────────────
print("== memory content encryption ==")
# This suite must not depend on the ambient environment: it runs both on its own
# and inside the encrypted CI job, where OMEM_ENCRYPT_AT_REST is already set.
# Asserting "off by default" against the real environment made it fail there,
# which is a bug in the test rather than in the thing under test.
_ambient = os.environ.pop("OMEM_ENCRYPT_AT_REST", None)
check("off unless asked for", not secrets_provider.content_encryption_enabled())
os.environ["OMEM_ENCRYPT_AT_REST"] = "1"
check("on when asked", secrets_provider.content_encryption_enabled())

# Content encryption REFUSES to run on the stdlib HMAC fallback, so without the
# `cryptography` extra there is nothing to round-trip. That is the correct
# behaviour and the default install, not a broken environment - so assert the
# refusal is clean and skip the rest. Asserting otherwise made this suite fail
# in every CI job that did not install the extra, which is most of them.
if not secrets_provider._HAVE_AESGCM:
    _refused = False
    try:
        secrets_provider.encrypt_content("x")
    except SystemExit as e:
        _refused = "cryptography" in str(e)
    check("without an AEAD library, encryption refuses rather than "
          "silently using the HMAC fallback", _refused)
    if _ambient is not None:
        os.environ["OMEM_ENCRYPT_AT_REST"] = _ambient
    else:
        os.environ.pop("OMEM_ENCRYPT_AT_REST", None)
    print("  (skipping the encryption round-trip: cryptography is not installed)")
    _SKIP_CRYPTO = True
else:
    _SKIP_CRYPTO = False

if not _SKIP_CRYPTO:
    ct = secrets_provider.encrypt_content('{"proposition":"prefers_annual_billing"}')
    check("ciphertext does not contain the plaintext", "prefers_annual_billing" not in ct)
    check("it is a versioned token", ct.startswith("v2c."), ct[:8])
    check("it round-trips", json.loads(secrets_provider.decrypt_content(ct))["proposition"]
          == "prefers_annual_billing")
    check("encrypting twice gives different ciphertext (fresh nonce)",
          secrets_provider.encrypt_content("same") != secrets_provider.encrypt_content("same"))
    check("already-encrypted input is not double-wrapped",
          secrets_provider.encrypt_content(ct) == ct)
    check("None passes through", secrets_provider.encrypt_content(None) is None)

    # The property that lets a database be half-migrated: plaintext still reads.
    # The reason v2c exists: LocalSecretsProvider salts per value and so runs
    # PBKDF2 per row (~336 ms measured). Content derives the key once and uses a
    # fresh nonce per row instead. If this regresses, every write and every boot
    # replay gets ~4 orders of magnitude slower, so it is worth a test.
    secrets_provider.encrypt_content("warm the key cache")
    _t = time.perf_counter()
    for _ in range(200):
        secrets_provider.encrypt_content("x" * 400)
    _per_ms = (time.perf_counter() - _t) / 200 * 1000
    check(f"encryption derives its key once, not per row ({_per_ms:.3f} ms/row)",
          _per_ms < 5.0, f"{_per_ms:.1f} ms per row suggests a KDF in the hot path")

    check("plaintext rows still read when encryption is ON",
          secrets_provider.decrypt_content('{"plain":true}') == '{"plain":true}')
    os.environ.pop("OMEM_ENCRYPT_AT_REST")
    check("ciphertext still reads when encryption is switched OFF again",
          json.loads(secrets_provider.decrypt_content(ct))["proposition"] == "prefers_annual_billing")
    if _ambient is not None:
        os.environ["OMEM_ENCRYPT_AT_REST"] = _ambient   # leave the run as we found it

# ── the single-writer lock ──────────────────────────────────────────────────
print("== one writer per database ==")
LOCK_DB = os.path.join(DATA, "test_p11_lock.db")
for _s in (LOCK_DB, LOCK_DB + "-wal", LOCK_DB + "-shm"):
    if os.path.exists(_s):
        os.remove(_s)
st = store_mod.Store(LOCK_DB)
st.writer_lock.acquire()
check("the first writer acquires", st.writer_lock.held)
st.writer_lock.acquire()
check("the same process re-acquires (restart replay does this)", st.writer_lock.held)

# a different, live process
st.db.execute("UPDATE writer_lock SET owner='elsewhere:4242', heartbeat=? WHERE id=1",
              (time.time(),))
st.db.commit()
second = store_mod.WriterLock(st.db)
refused = False
try:
    second.acquire()
except SystemExit as e:
    refused = True
    msg = str(e)
check("a second process is refused", refused)
check("  and told who holds it", refused and "elsewhere:4242" in msg)
check("  and why it matters", refused and "answer" in msg.lower())

# a dead holder must not block forever
st.db.execute("UPDATE writer_lock SET heartbeat=? WHERE id=1",
              (time.time() - store_mod.WriterLock.STALE_AFTER - 10,))
st.db.commit()
second.acquire()
check("a stale lock is taken over", second.held)
check("  and ownership moved", st.writer_lock.current()["owner"] == second.owner)

second.release()
check("release frees it for the next process", st.writer_lock.current() is None)

# heartbeating keeps a live holder alive
st.writer_lock.acquire()
before = st.writer_lock.current()["heartbeat"]
time.sleep(0.05)
st.writer_lock.beat()
check("a heartbeat refreshes the lock", st.writer_lock.current()["heartbeat"] > before)
st.writer_lock.release()

# ── TLS ─────────────────────────────────────────────────────────────────────
print("== TLS ==")
CRT, KEY = os.path.join(DATA, "p11.crt"), os.path.join(DATA, "p11.key")
# A missing binary raises FileNotFoundError rather than returning non-zero,
# so on a machine with no openssl at all (a stock Windows box) the guard
# below never got to say "skipped" -- the whole suite crashed instead.
try:
    have_openssl = subprocess.run(
        ["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-keyout", KEY,
         "-out", CRT, "-days", "1", "-subj", "/CN=localhost"],
        capture_output=True).returncode == 0
except FileNotFoundError:
    have_openssl = False

if not have_openssl:
    print("  skipped (no openssl available to make a test certificate)")
else:
    class _Srv:
        def __init__(self):
            self.socket = None

    os.environ["OMEM_TLS_CERT"] = CRT
    os.environ["OMEM_TLS_KEY"] = KEY
    srv = api.ThreadingHTTPServer(("127.0.0.1", 8817), api.Handler)
    check("wrap_tls reports that it wrapped the socket", api.wrap_tls(srv) is True)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    time.sleep(0.4)

    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    with urllib.request.urlopen("https://127.0.0.1:8817/v1/health", context=ctx, timeout=8) as r:
        body = json.loads(r.read())
    check("HTTPS serves the API", body.get("status") == "ok", str(body)[:120])

    # plaintext to a TLS port must not be answered as if it were fine
    plain_failed = False
    try:
        urllib.request.urlopen("http://127.0.0.1:8817/v1/health", timeout=5).read()
    except Exception:
        plain_failed = True
    check("plaintext HTTP to the TLS port fails", plain_failed)
    srv.shutdown()

    # half-configured TLS is a startup error, not a silent fallback to HTTP
    os.environ.pop("OMEM_TLS_KEY")
    half = False
    try:
        api.wrap_tls(api.ThreadingHTTPServer(("127.0.0.1", 8818), api.Handler))
    except SystemExit:
        half = True
    check("cert without key refuses to start", half)
    os.environ.pop("OMEM_TLS_CERT", None)

    missing = False
    os.environ["OMEM_TLS_CERT"] = os.path.join(DATA, "nope.crt")
    os.environ["OMEM_TLS_KEY"] = KEY
    try:
        api.wrap_tls(api.ThreadingHTTPServer(("127.0.0.1", 8819), api.Handler))
    except SystemExit:
        missing = True
    check("a missing certificate file refuses to start", missing)
    os.environ.pop("OMEM_TLS_CERT", None)
    os.environ.pop("OMEM_TLS_KEY", None)

check("no TLS configured means no wrapping (plain HTTP stays the default)",
      api.wrap_tls(api.ThreadingHTTPServer(("127.0.0.1", 8820), api.Handler)) is False)

print(f"\n{_passed} passed, {_failed} failed")
sys.exit(1 if _failed else 0)
