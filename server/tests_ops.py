"""Operational hardening tests. Run: python3 tests_ops.py
Backups (success/failure/retention/verify-restore), TOTP MFA end-to-end,
session expiry + revocation, hardening migrations, operator plan changes,
observability additions. PG-specific FK cascade + concurrency covered in
tests_postgres additions."""
import os
import sys
import json
import threading
import time
import urllib.request
import urllib.error

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
DB = "/tmp/omem_ops_tests.db"
for f in (DB,):
    if os.path.exists(f):
        os.remove(f)
os.environ["OMEM_DB"] = DB
os.environ["OMEM_ADMIN_EMAILS"] = "founder@omem.dev"
os.environ["OMEM_BACKUP_DIR"] = "/tmp/omem-ops-backups"
import shutil
shutil.rmtree("/tmp/omem-ops-backups", ignore_errors=True)

import os as _os_seed
_os_seed.environ['OMEM_SEED_DEMO']='1'
import api  # noqa: E402
from security import totp_code  # noqa: E402
from http.server import ThreadingHTTPServer  # noqa: E402

srv = ThreadingHTTPServer(("127.0.0.1", 0), api.Handler)
PORT = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()
time.sleep(0.2)
BASE = f"http://127.0.0.1:{PORT}"
PASS = FAIL = 0


def check(n, c, d=""):
    global PASS, FAIL
    if c:
        PASS += 1; print(f"  ok  {n}")
    else:
        FAIL += 1; print(f"  FAIL {n}  {d}")


def call(m, path, body=None, key=None):
    req = urllib.request.Request(BASE + path, method=m,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Content-Type": "application/json", **({"Authorization": f"Bearer {key}"} if key else {})})
    try:
        with urllib.request.urlopen(req, timeout=8) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


print("== migrations applied ==")
vers = [r["version"] for r in api.STORE.db.execute("SELECT version FROM schema_migrations ORDER BY version")]
check("v1+v2 applied on sqlite", "v1-baseline" in vers and "v2-indexes" in vers)

print("== legacy database upgrade (regression: 'no such column: s.expires') ==")
import sqlite3 as _sq, re as _re
import tempfile as _tempfile
import store as _store
# tempfile, not a hardcoded /tmp: on Windows that resolves to C:	mp, which
# may not exist and is not where a temporary file belongs on any platform.
_legacy = os.path.join(_tempfile.gettempdir(), "omem_legacy_upgrade.db")
if os.path.exists(_legacy):
    os.remove(_legacy)
_schema = _store.SCHEMA
_schema = _schema.replace("""  token TEXT PRIMARY KEY, user_id TEXT NOT NULL, created REAL NOT NULL,
  expires REAL, revoked INTEGER NOT NULL DEFAULT 0);""",
                          "  token TEXT PRIMARY KEY, user_id TEXT NOT NULL, created REAL NOT NULL);")
_schema = _re.sub(r"CREATE TABLE IF NOT EXISTS user_mfa\(.*?\);", "", _schema, flags=_re.S)
_schema = _schema.replace("""  created REAL NOT NULL, last_used REAL, revoked INTEGER NOT NULL DEFAULT 0,
  expires REAL, agent_id TEXT);""", "  created REAL NOT NULL, last_used REAL, revoked INTEGER NOT NULL DEFAULT 0);")
_d = _sq.connect(_legacy)
_d.executescript(_schema)
_d.execute("INSERT INTO users VALUES('u_leg','leg@corp.com',?)", (time.time(),))
_d.execute("INSERT INTO sessions VALUES('omem_sess_leg','u_leg',?)", (time.time(),))
_d.commit()
_pre = {r[1] for r in _d.execute("PRAGMA table_info(sessions)")}
_d.close()
check("fixture really is an old schema", "expires" not in _pre and "revoked" not in _pre)

# this scenario is SQLite-specific: force the sqlite path even when the suite
# is running against Postgres (Store honours OMEM_DATABASE_URL when present)
_saved_url = os.environ.pop("OMEM_DATABASE_URL", None)
_legacy_store = _store.Store(_legacy)
check("boot upgraded the legacy columns",
      "sessions.expires" in _legacy_store.upgraded_columns and
      "sessions.revoked" in _legacy_store.upgraded_columns and
      "keys.expires" in _legacy_store.upgraded_columns and
      "keys.agent_id" in _legacy_store.upgraded_columns,
      str(_legacy_store.upgraded_columns))
_u = _legacy_store.user_for_session("omem_sess_leg")
check("pre-existing session still works (NULL expires != expired)",
      _u is not None and _u["email"] == "leg@corp.com")
_second_boot = _store.Store(_legacy)
check("second boot is a no-op (idempotent)", _second_boot.upgraded_columns == [])
_k = _legacy_store.create_key("p1", "k", ttl_days=30)
check("new expiry column usable after upgrade", _k["expires"] is not None)
if _saved_url:
    os.environ["OMEM_DATABASE_URL"] = _saved_url
# Close the connections before deleting the file. POSIX allows unlinking a file
# that is still open and Windows does not, so leaving these to the garbage
# collector passed here and raised PermissionError there — the whole suite died
# on cleanup, after every assertion in it had already succeeded.
for _s in (_legacy_store, _second_boot):
    _s.db.close()          # Store holds the connection as .db; it has no close() of its own
os.remove(_legacy)
# WAL mode leaves -wal/-shm beside the database. They are part of the fixture and
# deleting only the main file would leave two stray files in the temp directory
# on every run.
for _sidecar in (_legacy + "-wal", _legacy + "-shm"):
    if os.path.exists(_sidecar):
        os.remove(_sidecar)

print("== backups: run / status / failure / retention / verify ==")
_, facct = call("POST", "/v1/signup", {"email": "founder@omem.dev"})
FTOK = facct["token"]
st, b = call("POST", "/v1/admin/backups/run", {}, FTOK)
check("backup run completed", st == 200 and not b["failing"] and b["completed_count"] == 1, str(b))
check("backup file exists with real bytes", b["last_successful"]["bytes"] > 100)
st, v = call("POST", "/v1/admin/backups/verify", {}, FTOK)
check("restore verification matches ops count", v["verified"] is True, str(v))
# forced failure: unwritable backup directory
old_dir = api.BACKUPS.dir
api.BACKUPS.dir = "/proc/definitely/not/writable"
st, b2 = call("POST", "/v1/admin/backups/run", {}, FTOK)
api.BACKUPS.dir = old_dir
check("backup failure recorded, not silent", b2["failing"] is True and b2["last_run"]["status"] == "failed")
check("failure did not overwrite last_successful", b2["last_successful"] is not None)
# retention: run several, keep retain=7 default -> use small retain
api.BACKUPS.retain = 2
for _ in range(3):
    call("POST", "/v1/admin/backups/run", {}, FTOK)
kept = api.STORE.db.execute("SELECT COUNT(*) c FROM backup_runs WHERE status='completed'").fetchone()["c"]
check("retention prunes old backups", kept <= 2, str(kept))
st, _ = call("GET", "/v1/admin/backups", None, FTOK)
check("backup status endpoint (operator)", st == 200)
_, cust = call("POST", "/v1/signup", {"email": "cust@x.com"})
st, _ = call("GET", "/v1/admin/backups", None, cust["token"])
check("customer blocked from backups", st == 403)

print("== scheduler runs due backups ==")
api.BACKUPS.interval = 0  # always due
api.BACKUPS.retain = 10   # don't let retention mask the new run
before = api.STORE.db.execute("SELECT COUNT(*) c FROM backup_runs WHERE status='completed'").fetchone()["c"]
api.SCHEDULER.tick()
after = api.STORE.db.execute("SELECT COUNT(*) c FROM backup_runs WHERE status='completed'").fetchone()["c"]
check("tick performed a due backup", after == before + 1, f"{before}->{after}")
api.BACKUPS.interval = 3600

print("== dead-letter recovery after a provider outage ==")
import providers as _pv3
_dl_conn = api.INGEST.add_connector("demo", "webhook", "dl-test", {}, agent_id="connector:dl")
for _i in range(4):
    api.STORE.db.execute(
        "INSERT INTO ingest_jobs(project_id,connector_id,source_record_id,state,attempts,"
        "last_error,created,updated) VALUES(?,?,?,'dead_lettered',3,?,?,?)",
        ("demo", _dl_conn["id"], f"srcdl{_i}", "ProviderUnreachable: DNS failed",
         time.time(), time.time()))
api.STORE.db.commit()
check("dead letters present", api.INGEST.stats("demo")["dead"] >= 4)
_n = api.INGEST.retry_dead_letters("demo")
check("retry requeues every dead letter", _n >= 4, str(_n))
check("none left dead-lettered", api.INGEST.stats("demo")["dead"] == 0)
check("they are pending again", api.INGEST.stats("demo")["pending"] >= 4)
check("retrying twice is safe", api.INGEST.retry_dead_letters("demo") == 0)

print("== DNS diagnosis distinguishes config errors from network failures ==")
_bad_url = _pv3.dns_check("api.groq.com/openai/v1")   # missing scheme
check("malformed URL reported as config error",
      _bad_url["ok"] is False and "valid http(s) URL" in _bad_url["error"])
_bad_host = _pv3.dns_check("https://definitely-not-a-real-host.invalid/v1")
check("unresolvable host reported as DNS failure",
      _bad_host["ok"] is False and "DNS lookup" in _bad_host["error"])
check("DNS error names the host", "definitely-not-a-real-host.invalid" in _bad_host["error"])

print("== every provider call names the failing host ==")
import urllib.request as _ur
for _host in ("oauth2.googleapis.invalid", "gmail.googleapis.invalid",
              "api.groq.invalid"):
    _req = _ur.Request(f"https://{_host}/x", data=b"y")
    try:
        _pv3._open_or_explain(_req, timeout=5)
        check(f"{_host} raises", False)
    except _pv3.ProviderUnreachable as _e:
        check(f"failure names {_host}", _host in str(_e))
    except Exception as _e:
        check(f"{_host} classified", False, type(_e).__name__)

st, _diag = call("GET", "/v1/providers/check", None, FTOK)
check("diagnostic checks the Google hosts too",
      set(_diag["google"]["hosts"]) == {"oauth2.googleapis.com", "gmail.googleapis.com"})
check("diagnostic gives an actionable summary", isinstance(_diag["summary"], str) and _diag["summary"])

print("== provider rejection is reported with the provider's own words ==")
import io as _io, urllib.error as _uerr


def _http_err(code, body):
    return _uerr.HTTPError("https://api.groq.com/openai/v1/chat/completions", code,
                           "err", {}, _io.BytesIO(body))


check("json error message extracted",
      _pv3._provider_error_text(_http_err(403, b'{"error":{"message":"Invalid API Key"}}'))
      == "Invalid API Key")
check("plain-text error body extracted",
      "denied" in _pv3._provider_error_text(_http_err(403, b"access denied by firewall")))
check("unreadable body degrades safely",
      _pv3._provider_error_text(_http_err(403, b"")) == "")


class _Refusing(_pv3.OpenAICompatClient):
    def __init__(self):
        os.environ.setdefault("OMEM_LLM_API_KEY", "k")
        super().__init__()

    def complete(self, system, user):
        raise RuntimeError(
            "api.groq.com refused the request (HTTP 403): Invalid API Key. "
            "Usual causes: the API key is wrong or revoked")


try:
    _Refusing().complete("s", "u")
    check("refusal raises", False)
except RuntimeError as _e:
    check("message names the host", "api.groq.com" in str(_e))
    check("message includes the provider's reason", "Invalid API Key" in str(_e))
    check("message suggests causes", "revoked" in str(_e))
os.environ.pop("OMEM_LLM_API_KEY", None)

print("== json_object mode only when the prompt asks for JSON ==")
import urllib.request as _ur2, json as _j4
from connectors import EXTRACTION_SYSTEM as _ES

check("extraction prompt contains the json trigger word", "json" in _ES.lower())

_cap = {}


class _FakeResp:
    def read(self):
        return b'{"choices":[{"message":{"content":"{}"}}]}'

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


_real_urlopen = _ur2.urlopen


def _fake_urlopen(req, timeout=30):
    _cap["body"] = _j4.loads(req.data)
    _cap["ua"] = req.headers.get("User-agent")
    return _FakeResp()


os.environ["OMEM_LLM_API_KEY"] = "k"
_ur2.urlopen = _fake_urlopen
try:
    _cl = _pv3.OpenAICompatClient()
    _cl.complete("Reply with the single word: ok", "ping")
    check("no response_format when the prompt never mentions json",
          "response_format" not in _cap["body"])
    _cl.complete(_ES, "From: a@b.com\nSubject: x\n\nbody")
    check("response_format requested for the real extraction prompt",
          _cap["body"].get("response_format", {}).get("type") == "json_object")
    check("a real User-Agent is sent (WAFs reject the urllib default)",
          _cap["ua"] == "omem-cloud/1.0")
finally:
    _ur2.urlopen = _real_urlopen
    os.environ.pop("OMEM_LLM_API_KEY", None)

print("== concurrent writes on one sqlite connection (regression) ==")
# regression for: OperationalError: cannot commit - no transaction is active
_errs = []


def _hammer(n):
    try:
        for _ in range(30):
            api.STORE.db.execute(
                "INSERT INTO usage_events(project_id,metric,quantity,ts) VALUES(?,?,?,?)",
                (f"conc{n}", "m", 1, time.time()))
            api.STORE.db.commit()
            api.STORE.db.execute("SELECT COUNT(*) c FROM usage_events").fetchone()
    except Exception as _e:
        _errs.append(f"{type(_e).__name__}: {_e}")


_threads = [threading.Thread(target=_hammer, args=(i,)) for i in range(6)]
[t.start() for t in _threads]
[t.join() for t in _threads]
check("no errors under concurrent writes", not _errs, str(_errs[:1]))
_written = api.STORE.db.execute(
    "SELECT COUNT(*) c FROM usage_events WHERE metric='m' AND project_id LIKE 'conc%'").fetchone()["c"]
check("no lost writes (6 threads x 30)", _written == 180, str(_written))

print("== owner membership backfill for pre-RBAC installs ==")
_org_row = api.STORE.db.execute("SELECT id, user_id FROM orgs LIMIT 1").fetchone()
api.STORE.db.execute("DELETE FROM memberships WHERE org_id=? AND user_id=?",
                     (_org_row["id"], _org_row["user_id"]))
api.STORE.db.commit()
check("membership removed (simulating an old install)",
      api.ENT.role_of(_org_row["id"], _org_row["user_id"]) is None)
_granted = api._backfill_owner_memberships()
check("boot grants the org creator owner",
      api.ENT.role_of(_org_row["id"], _org_row["user_id"]) == "owner")
check("backfill reports what it changed", len(_granted) >= 1)
check("running it again changes nothing", api._backfill_owner_memberships() == [])
check("owner can now manage members",
      api.ENT.can(_org_row["id"], _org_row["user_id"], "member.manage"))

print("== MFA: enroll -> activate -> enforced ==")
SESS = cust["token"]
st, en = call("POST", "/v1/mfa/enroll", {}, SESS)
check("enroll returns secret + otpauth", st == 200 and en["secret"] and en["otpauth"].startswith("otpauth://totp/"))
st, _ = call("POST", "/v1/mfa/activate", {"code": "000000"}, SESS)
check("wrong code cannot activate", st == 403)
good = totp_code(en["secret"])
st, act = call("POST", "/v1/mfa/activate", {"code": good}, SESS)
check("correct TOTP activates", st == 200 and act["enabled"])
st, _ = call("POST", "/v1/session", {"email": "cust@x.com"})
check("session without code -> 401 mfa_required", st == 401)
st, s2 = call("POST", "/v1/session", {"email": "cust@x.com", "code": totp_code(en["secret"])})
check("session with valid TOTP succeeds", st == 200 and "token" in s2)

print("== session revocation + expiry ==")
tok = s2["token"]
st, _ = call("GET", "/v1/me", None, tok)
check("fresh session works", st == 200)
call("POST", "/v1/sessions/revoke", {}, tok)
st, _ = call("GET", "/v1/me", None, tok)
check("revoked session -> 401", st == 401)
# expiry: force an expired session
st, s3 = call("POST", "/v1/session", {"email": "cust@x.com", "code": totp_code(en["secret"])})
api.STORE.db.execute("UPDATE sessions SET expires=? WHERE token=?", (time.time() - 10, s3["token"]))
api.STORE.db.commit()
st, _ = call("GET", "/v1/me", None, s3["token"])
check("expired session -> 401", st == 401)

print("== operator plan change (entitlements, no fake payment) ==")
OID = api.STORE.org_for_user(api.STORE.user_by_email("cust@x.com")["id"])["id"]
st, bp = call("POST", f"/v1/admin/orgs/{OID}/plan", {"plan": "business"}, FTOK)
check("operator sets plan", st == 200 and bp["plan"] == "business")
st, _ = call("POST", f"/v1/admin/orgs/{OID}/plan", {"plan": "platinum"}, FTOK)
check("invalid plan -> 422", st == 422)
ev = api.ENT.billing_events(OID)
check("plan change recorded as billing event", any(e["kind"] == "plan.set_by_operator" for e in ev))

print("== observability additions ==")
st, obs = call("GET", "/v1/observability", None, FTOK)
check("queue depth exposed", "queue_depth" in obs)
check("backup state exposed", obs["backup"]["last_successful"] is not None)

print("== persistence: MFA + revocation + backups survive restart ==")
srv.shutdown()
import importlib
sys.modules.pop("api")
api2 = importlib.import_module("api")
u = api2.STORE.user_by_email("cust@x.com")
check("mfa enabled persisted", api2.STORE.mfa_state(u["id"])["enabled"] == 1)
check("backup history persisted", api2.BACKUPS.status()["completed_count"] >= 1)
check("revoked session stays revoked", api2.STORE.user_for_session(tok) is None)

print(f"\n{PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
