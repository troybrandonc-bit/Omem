"""Hardening tests. Run: python3 tests_hardening.py
Secrets provider (encryption at rest, tamper detection, no-leak), full job state
machine (running/completed/retrying/dead_lettered/cancelled + crash recovery),
API-key expiry, auth rate limiting, secure OAuth state."""
import os
import sys
import json
import threading
import time
import urllib.request
import urllib.error

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
DB = "/tmp/omem_hard_tests.db"
if os.path.exists(DB):
    os.remove(DB)
os.environ["OMEM_DB"] = DB
os.environ["OMEM_MASTER_KEY"] = "test-master-key-abc"

import api  # noqa: E402
from secrets_provider import LocalSecretsProvider  # noqa: E402
from security import RateLimiter, OAuthStateStore  # noqa: E402
from http.server import ThreadingHTTPServer  # noqa: E402

srv = ThreadingHTTPServer(("127.0.0.1", 0), api.Handler)
PORT = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()
time.sleep(0.2)
PASS = FAIL = 0


def _fails(fn):
    try:
        fn(); return False
    except Exception:
        return True


def check(n, c, d=""):
    global PASS, FAIL
    if c:
        PASS += 1; print(f"  ok  {n}")
    else:
        FAIL += 1; print(f"  FAIL {n}  {d}")


def call(m, path, body=None, token=None):
    req = urllib.request.Request(f"http://127.0.0.1:{PORT}{path}", method=m,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Content-Type": "application/json", **({"Authorization": f"Bearer {token}"} if token else {})})
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, dict(r.headers), json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), json.loads(e.read() or b"{}")


print("== secrets provider ==")
sp = LocalSecretsProvider("master-1")
tok = sp.encrypt("refresh-token-xyz")
check("ciphertext differs from plaintext", "refresh-token-xyz" not in tok)
check("round-trips through provider", sp.decrypt(tok) == "refresh-token-xyz")
check("wrong master cannot decrypt", _fails(lambda: LocalSecretsProvider("master-2").decrypt(tok)))
# tamper the ciphertext
parts = tok.split(".")
import base64
raw = bytearray(base64.b64decode(parts[-1] if sp.kind == "local-aesgcm" else parts[-2]))
raw[0] ^= 0xFF
parts[-1 if sp.kind == "local-aesgcm" else -2] = base64.b64encode(bytes(raw)).decode()
check("tampered ciphertext rejected", _fails(lambda: sp.decrypt(".".join(parts))))

print("== oauth token never leaked by API ==")
_, _, acct = call("POST", "/v1/signup", {"email": "sec@corp.com"})
SESS = acct["token"]; PID = acct["project"]["id"]
# create a gmail connector + store tokens
api.GMAIL_TRANSPORT_FACTORY = lambda conn: None
conn = api.INGEST.add_connector(PID, "gmail", "Gmail", {}, agent_id="connector:gmail")
api.OAUTH.save(conn["id"], "gmail", "SECRET_ACCESS", "SECRET_REFRESH", 9e9, "scope", "u@gmail.com")
st, _, status = call("GET", f"/v1/connectors/{conn['id']}/status?project={PID}", token=SESS)
blob = json.dumps(status)
check("status endpoint hides tokens", "SECRET_ACCESS" not in blob and "SECRET_REFRESH" not in blob)
raw_creds = api.OAUTH.get(conn["id"])
check("default get() hides tokens", "access_token" not in raw_creds or raw_creds.get("access_token") is None)
check("tokens stored encrypted at rest",
      "SECRET_REFRESH" not in api.STORE.db.execute("SELECT refresh_token FROM oauth_creds WHERE connector_id=?", (conn["id"],)).fetchone()[0])
check("include_secrets=True decrypts for internal use",
      api.OAUTH.get(conn["id"], include_secrets=True)["refresh_token"] == "SECRET_REFRESH")

print("== full job state machine ==")
# a poison extractor that always raises -> should retry then dead_letter
from connectors import Extractor

class Poison(Extractor):
    def extract(self, payload):
        raise RuntimeError("boom")

from ingest import SupportInboxConnector
api.INGEST.connector_factory = lambda conn: SupportInboxConnector(
    json.loads(conn["config"]).get("items"), extractor=Poison()) if conn["kind"] == "support_inbox" else None
pc = api.INGEST.add_connector(PID, "support_inbox", "Poison",
    {"items": [{"customer": "z", "subject": "s", "body": "prefer email"}]}, agent_id="connector:p")
api.INGEST.poll_connector(pc["id"])
r1 = api.INGEST.process_pending(PID)
check("first failure -> retrying (not dead yet)", r1["failed"] == 1)
jobs = api.INGEST.jobs_for(PID)
check("job in retrying state with backoff", any(j["state"] == "retrying" and j["next_attempt"] for j in jobs))
# force backoff to pass and exhaust attempts
api.STORE.db.execute("UPDATE ingest_jobs SET next_attempt=0 WHERE project_id=?", (PID,)); api.STORE.db.commit()
api.INGEST.process_pending(PID)
api.STORE.db.execute("UPDATE ingest_jobs SET next_attempt=0 WHERE project_id=?", (PID,)); api.STORE.db.commit()
api.INGEST.process_pending(PID)
stats = api.INGEST.stats(PID)
check("exhausted retries -> dead_lettered", stats["dead"] >= 1, str(stats))

print("== crash recovery ==")
# simulate a crashed worker: a job stuck 'running' with an old heartbeat.
# use a real connector id so FK constraints (production) are satisfied.
_hb_conn = api.INGEST.add_connector(PID, "webhook", "hb", {}, agent_id="connector:hb")
api.STORE.db.execute(
    "INSERT INTO ingest_jobs(project_id,connector_id,source_record_id,state,heartbeat,created,updated) "
    "VALUES(?,?,?,'running',?,?,?)", (PID, _hb_conn["id"], "s", time.time() - 300, time.time(), time.time()))
api.STORE.db.commit()
recovered = api.INGEST.recover_stale(older_than=60)
check("stale running job recovered to pending", recovered >= 1)

print("== cancellation ==")
api.STORE.db.execute(
    "INSERT INTO ingest_jobs(project_id,connector_id,source_record_id,state,created,updated) "
    "VALUES(?,?,?,'pending',?,?)", (PID, _hb_conn["id"], "s", time.time(), time.time()))
api.STORE.db.commit()
jid = api.STORE.db.execute("SELECT id FROM ingest_jobs WHERE project_id=? AND state='pending' ORDER BY id DESC LIMIT 1", (PID,)).fetchone()["id"]
check("pending job can be cancelled", api.INGEST.cancel_job(jid))
check("cancelled job stays cancelled", not api.INGEST.cancel_job(jid))

print("== API key expiry ==")
k = api.STORE.create_key(PID, "short", ttl_days=None)
api.STORE.db.execute("UPDATE keys SET expires=? WHERE id=?", (time.time() - 10, k["id"])); api.STORE.db.commit()
check("expired key rejected at lookup", api.STORE.key_lookup(k["secret"]) is None)
st, _, _ = call("GET", f"/v1/overview?project={PID}", token=k["secret"])
check("expired key -> 401 over HTTP", st == 401)
kv = api.STORE.create_key(PID, "valid")
st, _, _ = call("GET", f"/v1/overview?project={PID}", token=kv["secret"])
check("valid key -> 200", st == 200)

print("== auth rate limiting ==")
codes = [call("POST", "/v1/session", {"email": "rl@x.com"})[0] for _ in range(12)]
check("rapid auth requests eventually 429", 429 in codes, str(codes))
check("first requests allowed (burst)", codes[0] == 200)

print("== security headers ==")
_, headers, _ = call("GET", "/v1/health")
check("X-Content-Type-Options present", headers.get("X-Content-Type-Options") == "nosniff")
check("X-Frame-Options present", headers.get("X-Frame-Options") == "DENY")
check("correlation id present", bool(headers.get("X-Correlation-Id")))

print("== secure oauth state ==")
oss = OAuthStateStore("s")
st_val = oss.issue("proj_1", "conn_1")
v = oss.verify(st_val)
check("valid state verifies + binds project", v and v["project_id"] == "proj_1")
check("state is single-use", oss.verify(st_val) is None)
check("forged state rejected", oss.verify("proj_1:conn_1:9999999999:deadbeef:badsig") is None)

print("== rate limiter unit ==")
rl = RateLimiter(capacity=3, refill_per_sec=0)
check("burst of 3 allowed", all(rl.allow("k") for _ in range(3)))
check("4th blocked", not rl.allow("k"))

print("== persistence: hardened state survives restart ==")
srv.shutdown()
import importlib
sys.modules.pop("api")
api2 = importlib.import_module("api")
check("dead-lettered jobs persist", api2.INGEST.stats(PID)["dead"] >= 1)
check("encrypted tokens still decrypt after restart",
      api2.OAUTH.get(conn["id"], include_secrets=True)["refresh_token"] == "SECRET_REFRESH")

print("== SSRF guard (tenant-configured connector URLs) ==")
from security import safe_url, SSRFError
def _blocked(u):
    try:
        safe_url(u); return False
    except SSRFError:
        return True
check("cloud metadata IP blocked", _blocked("http://169.254.169.254/latest/meta-data/"))
check("loopback blocked", _blocked("http://127.0.0.1:8787/admin"))
check("private range blocked", _blocked("https://10.0.0.5/x"))
check("non-https scheme blocked", _blocked("file:///etc/passwd"))
check("internal hostname blocked", _blocked("https://metadata.google.internal/"))
try:
    ok = safe_url("https://login.salesforce.com") == "https://login.salesforce.com"
except SSRFError:
    ok = False
check("legitimate public https allowed", ok)

print(f"\n{PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
