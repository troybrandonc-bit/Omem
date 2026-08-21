"""Password-mode authentication.

The defect these cover: `POST /v1/session {"email": "..."}` used to return a
valid 30-day session for ANY address, with no password, no verification and no
second factor. Knowing an email address was the entire credential, including
for the addresses in OMEM_ADMIN_EMAILS, which reach every tenant's data through
/v1/admin. Enrolling TOTP did not help either, because /v1/signup returned a
session for an existing address without ever consulting MFA.

Run: OMEM_AUTH=password python3 tests_auth_password.py
(the suite sets that itself; it is listed here because the mode is the subject).
"""
import json
import os
import sys
import threading
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))

# A fresh database per run, and password mode, before api is imported: both are
# read at import time.
_DB = os.path.join(HERE, "data", "test_auth_password.db")
for _stale in (_DB, _DB + "-wal", _DB + "-shm"):
    if os.path.exists(_stale):
        os.remove(_stale)
os.environ["OMEM_DB"] = _DB
os.environ["OMEM_AUTH"] = "password"
os.environ["OMEM_MASTER_KEY"] = "test-master-key-not-the-default-one"
os.environ["OMEM_SEED_DEMO"] = "0"

sys.path.insert(0, HERE)
import api  # noqa: E402
import store as store_mod  # noqa: E402
from security import totp_code, totp_secret  # noqa: E402

PORT = 8814
BASE = f"http://127.0.0.1:{PORT}"

_passed = _failed = 0


def check(name, cond, detail=""):
    global _passed, _failed
    if cond:
        _passed += 1
        print(f"  ok  {name}")
    else:
        _failed += 1
        print(f"  FAIL {name} {detail}")


def reset_limits():
    """Drop the per-IP auth buckets.

    /v1/signup and /v1/session are rate limited to a 5-request burst per client
    IP, which is exactly right in production and means a suite hammering both
    from 127.0.0.1 starts collecting 429s a third of the way in. The limiter has
    its own coverage in tests_p9_abuse; here it is noise, so it is cleared
    between phases rather than worked around by sleeping for a minute."""
    api.AUTH_LIMITER._buckets.clear()


def call(method, path, body=None, key=None):
    req = urllib.request.Request(
        BASE + path, method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Content-Type": "application/json",
                 **({"Authorization": f"Bearer {key}"} if key else {})})
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


srv = api.ThreadingHTTPServer(("127.0.0.1", PORT), api.Handler)
threading.Thread(target=srv.serve_forever, daemon=True).start()
time.sleep(0.3)

PW = "correct-horse-battery"

print("== the hole itself: an email is not a credential ==")
st, r = call("POST", "/v1/signup", {"email": "owner@corp.com", "password": PW, "org": "Corp"})
check("signup with a password creates the account", st == 201 and r.get("token"), str(st))
OWNER_TOKEN = r.get("token")

st, r = call("POST", "/v1/session", {"email": "owner@corp.com"})
check("session with NO password is refused", st == 401, str(st))
check("  and does not leak whether the address is registered",
      r.get("error", {}).get("message") == "Invalid email or password.")

st, r = call("POST", "/v1/session", {"email": "owner@corp.com", "password": "wrong-password-x"})
check("session with the wrong password is refused", st == 401, str(st))

st, r = call("POST", "/v1/session", {"email": "owner@corp.com", "password": PW})
check("session with the right password succeeds", st == 200 and r.get("token"), str(st))

st, r = call("POST", "/v1/session", {"email": "stranger@corp.com", "password": PW})
check("an unregistered address cannot sign in", st == 401, str(st))

reset_limits()
print("== signup is not a back door into an existing account ==")
st, r = call("POST", "/v1/signup", {"email": "owner@corp.com", "password": "another-password"})
check("signup on a registered address is 409, not a session", st == 409, str(st))
check("  and returns no token", "token" not in r)
st, r = call("POST", "/v1/session", {"email": "owner@corp.com", "password": PW})
check("  and the original password still works", st == 200)

reset_limits()
print("== password rules ==")
st, r = call("POST", "/v1/signup", {"email": "short@corp.com", "password": "abc"})
check("a too-short password is refused", st == 422, str(st))
st, _ = call("POST", "/v1/signup", {"email": "nopw@corp.com"})
check("signup with no password at all is refused", st == 422, str(st))

print("== hashing ==")
row = api.STORE.db.execute("SELECT pw_hash FROM users WHERE email=?",
                           ("owner@corp.com",)).fetchone()
check("the password is not stored in plaintext", PW not in (row["pw_hash"] or ""))
check("stored as pbkdf2_sha256 with its iteration count",
      (row["pw_hash"] or "").startswith("pbkdf2_sha256$"), row["pw_hash"][:24])
check("verify accepts the right password", store_mod.verify_password(PW, row["pw_hash"]))
check("verify rejects the wrong one", not store_mod.verify_password("nope", row["pw_hash"]))
check("verify rejects a NULL hash rather than waving it through",
      not store_mod.verify_password(PW, None))
check("verify rejects an empty password against a NULL hash",
      not store_mod.verify_password("", None))
check("two hashes of one password differ (salted)",
      store_mod.hash_password(PW) != store_mod.hash_password(PW))

reset_limits()
print("== an invited member is not a live session ==")
st, r = call("POST", "/v1/members/role",
             {"email": "invited@corp.com", "role": "admin"}, key=OWNER_TOKEN)
check("inviting a member succeeds", st == 200, str(st))
inv = api.STORE.user_by_email("invited@corp.com")
check("  the user row exists", bool(inv))
check("  with no password yet", not api.STORE.has_password("invited@corp.com"))
n_sessions = api.STORE.db.execute(
    "SELECT COUNT(*) c FROM sessions WHERE user_id=?", (inv["id"],)).fetchone()["c"]
check("  and NO session was minted for them", n_sessions == 0, str(n_sessions))
st, _ = call("POST", "/v1/session", {"email": "invited@corp.com", "password": PW})
check("  a credential-less account cannot sign in", st == 401, str(st))

reset_limits()
print("== claiming a credential-less account ==")
st, r = call("POST", "/v1/signup", {"email": "invited@corp.com", "password": "invited-password-1"})
check("the invitee can claim it by setting a password", st == 201 and r.get("token"), str(st))
st, _ = call("POST", "/v1/session", {"email": "invited@corp.com", "password": "invited-password-1"})
check("  and can then sign in", st == 200)
st, _ = call("POST", "/v1/signup", {"email": "invited@corp.com", "password": "third-party-pw"})
check("  after which nobody else can claim it", st == 409, str(st))

reset_limits()
print("== MFA is not bypassable via signup ==")
u = api.STORE.user_by_email("owner@corp.com")
secret = totp_secret()
api.STORE.mfa_enroll(u["id"], secret)
api.STORE.mfa_activate(u["id"])

st, _ = call("POST", "/v1/session", {"email": "owner@corp.com", "password": PW})
check("an MFA-enrolled account needs a code at session", st == 401, str(st))
st, _ = call("POST", "/v1/session",
             {"email": "owner@corp.com", "password": PW, "code": totp_code(secret)})
check("  and a valid code is accepted", st == 200, str(st))
st, _ = call("POST", "/v1/session",
             {"email": "owner@corp.com", "password": PW, "code": "000000"})
check("  while a wrong code is not", st == 401, str(st))

# The old bug: /v1/signup returned a session for an existing address without
# ever consulting MFA, so enrolling a second factor protected nothing.
reset_limits()
st, r = call("POST", "/v1/signup", {"email": "owner@corp.com", "password": "bypass-attempt-1"})
check("signup cannot mint a session for an MFA-protected account", st == 409, str(st))
check("  and hands back no token", "token" not in r)

# Claiming a credential-less account must satisfy that account's MFA too,
# or the claim path becomes the same bypass by another name.
reset_limits()
api.STORE.ensure_user("mfa-invite@corp.com")
_iu = api.STORE.user_by_email("mfa-invite@corp.com")
_isec = totp_secret()
api.STORE.mfa_enroll(_iu["id"], _isec)
api.STORE.mfa_activate(_iu["id"])
st, _ = call("POST", "/v1/signup", {"email": "mfa-invite@corp.com", "password": "claim-attempt-99"})
check("claiming an MFA-protected credential-less account needs the code", st == 401, str(st))
st, r = call("POST", "/v1/signup", {"email": "mfa-invite@corp.com",
                                    "password": "claim-attempt-99", "code": totp_code(_isec)})
check("  and succeeds with it", st == 201 and r.get("token"), str(st))

print("== the mode is discoverable before sign-in ==")
st, r = call("GET", "/v1/health")
check("health reports the auth mode", r.get("auth") == "password", str(r.get("auth")))

print("== boot guards ==")
try:
    old = os.environ.pop("OMEM_MASTER_KEY")
    api.enforce_auth_safety("0.0.0.0")
    check("password mode refuses the default master key", False, "started anyway")
except SystemExit:
    check("password mode refuses the default master key", True)
finally:
    os.environ["OMEM_MASTER_KEY"] = old

srv.shutdown()
print(f"\n{_passed} passed, {_failed} failed")
sys.exit(1 if _failed else 0)
