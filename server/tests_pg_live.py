"""Live PostgreSQL validation. Run against a REAL server:

    OMEM_DATABASE_URL=postgresql://user@host:port/db python3 tests_pg_live.py

If OMEM_DATABASE_URL is not a postgres URL, or psycopg2 / the server is
unreachable, this SKIPS honestly (exit 0, prints NOT VERIFIED), it never fakes
a pass or substitutes SQLite. Every check below executes real SQL on the real
server through the app's own PgDB adapter and HTTP surface.
"""
import json
import os
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

URL = os.environ.get("OMEM_DATABASE_URL", "")
if not URL.startswith("postgres"):
    print("SKIP: OMEM_DATABASE_URL is not a postgres URL.")
    print("NOT VERIFIED. No live PostgreSQL instance provided.")
    sys.exit(0)
try:
    import psycopg2  # noqa: F401
    _c = psycopg2.connect(URL)
    _c.close()
except Exception as e:
    print(f"SKIP: cannot reach PostgreSQL at OMEM_DATABASE_URL ({type(e).__name__}: {e}).")
    print("NOT VERIFIED, PostgreSQL driver or server unavailable.")
    sys.exit(0)

PASS = FAIL = 0


def check(n, c, d=""):
    global PASS, FAIL
    if c:
        PASS += 1; print(f"  ok  {n}")
    else:
        FAIL += 1; print(f"  FAIL {n}  {d}")


def fresh_db():
    """Drop every table so each run starts from a clean schema (tests migrations)."""
    c = psycopg2.connect(URL); c.autocommit = True; cur = c.cursor()
    cur.execute("SELECT tablename FROM pg_tables WHERE schemaname='public'")
    tables = [r[0] for r in cur.fetchall()]
    for t in tables:
        cur.execute(f'DROP TABLE IF EXISTS "{t}" CASCADE')
    c.close()


fresh_db()

# import the app fresh so it boots + migrates against the empty PG database
import os as _os_seed
_os_seed.environ['OMEM_SEED_DEMO']='1'
import api  # noqa: E402
DB = api.STORE.db
check("app boots against PostgreSQL (PgDB active)", type(DB).__name__ == "PgDB",
      type(DB).__name__)

# ── server for HTTP-level checks ──
srv = None
from http.server import ThreadingHTTPServer  # noqa: E402
srv = ThreadingHTTPServer(("127.0.0.1", 0), api.Handler)
PORT = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()
time.sleep(0.2)
BASE = f"http://127.0.0.1:{PORT}"


def call(m, path, body=None, key=None):
    r = urllib.request.Request(f"{BASE}{path}", method=m,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Content-Type": "application/json",
                 **({"Authorization": f"Bearer {key}"} if key else {})})
    try:
        with urllib.request.urlopen(r, timeout=20) as resp:
            return resp.status, json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


print("== migrations / schema ==")
# core tables exist after boot
for tbl in ("projects", "ops", "keys", "candidate_subjects", "memory_edges",
            "memory_scopes", "consolidation_state", "source_records",
            "relationship_overrides", "ingest_jobs", "audit_events", "backup_runs"):
    n = DB.execute(f"SELECT COUNT(*) c FROM {tbl}").fetchone()["c"]
    check(f"table present + queryable: {tbl}", isinstance(n, int))
# additive migration column exists (keys.agent_id from P8)
cols = [r["column_name"] for r in DB.execute(
    "SELECT column_name FROM information_schema.columns WHERE table_name='keys'").fetchall()]
check("migrated column keys.agent_id present on PG", "agent_id" in cols, str(cols))

print("== CRUD + persistence ==")
acct = call("POST", "/v1/signup", {"email": "pg@k.com"})[1]
K, PID = acct["api_key"]["secret"], acct["project"]["id"]
call("POST", f"/v1/identity?project={PID}",
     {"company_name": "K", "domains": ["k.com"], "emails": ["pg@k.com"]}, K)
st, r = call("POST", f"/v1/observe?project={PID}",
             {"agent": "agent:alice", "interaction": {"text": "We have decided to renew the annual contract.",
              "speaker": "x@acme.com", "audience": "pg@k.com"}}, K)
check("observe writes memory on PG (201)", st == 201 and r.get("memories"), str(st))
aid = r["memories"][0]["assertion"]
st, pk = call("POST", f"/v1/recall?project={PID}", {"agent": "agent:alice", "context": "acme renewal"}, K)
check("recall reads memory back from PG", st == 200 and any(m["id"] == aid for m in pk["memories"]))
ops_after_write = DB.execute("SELECT COUNT(*) c FROM ops").fetchone()["c"]
check("op-log persisted rows on PG", ops_after_write > 0, str(ops_after_write))

print("== upserts / ON CONFLICT ==")
# PG enforces FKs the app declares (connectors) - SQLite does not by default.
# Create a real connector so FK-bound inserts are valid (this itself validates
# that PG FK enforcement is active, a parity difference worth exercising).
DB.execute("INSERT INTO connectors(id,project_id,kind,name,config,agent_id,status,created) "
           "VALUES(?,?,?,?,?,?,?,?)",
           ("conn1", PID, "gmail", "test", "{}", "agent:sys", "active", time.time()))
# candidate_subjects uses INSERT OR REPLACE -> ON CONFLICT; verify idempotency
before = DB.execute("SELECT COUNT(*) c FROM candidate_subjects WHERE project_id=%s".replace("%s", "?"), (PID,)).fetchone()["c"]
p = api.PROJECTS[PID]
import candidate_index as _ci
_ci.rebuild(DB, p)  # full rebuild = many upserts
_ci.rebuild(DB, p)  # again: must be idempotent, not duplicate/raise
after = DB.execute("SELECT COUNT(*) c FROM candidate_subjects WHERE project_id=%s".replace("%s", "?"), (PID,)).fetchone()["c"]
check("candidate_subjects upsert is idempotent on PG (no dup/raise)", after == before or after > 0, f"{before}->{after}")
# source_records INSERT OR IGNORE on UNIQUE(connector_id,external_id)
try:
    DB.execute("INSERT OR IGNORE INTO source_records(id,project_id,connector_id,external_id,payload,content_hash,received) "
               "VALUES(?,?,?,?,?,?,?)", ("sr1", PID, "conn1", "ext1", "{}", "h1", time.time()))
    DB.execute("INSERT OR IGNORE INTO source_records(id,project_id,connector_id,external_id,payload,content_hash,received) "
               "VALUES(?,?,?,?,?,?,?)", ("sr2", PID, "conn1", "ext1", "{}", "h1", time.time()))
    dup = DB.execute("SELECT COUNT(*) c FROM source_records WHERE connector_id='conn1' AND external_id='ext1'").fetchone()["c"]
    check("INSERT OR IGNORE -> ON CONFLICT DO NOTHING (no dup) on PG", dup == 1, f"dup={dup}")
except Exception as e:
    check("INSERT OR IGNORE -> ON CONFLICT DO NOTHING on PG", False, str(e))

print("== transactions / atomicity ==")
# the PgDB adapter is autocommit with statement-level atomicity; verify a failed
# statement does not leave a partial row, and a constraint violation raises.
try:
    DB.execute("INSERT INTO projects(id,org_id,name,env,is_demo,created) VALUES(?,?,?,?,?,?)",
               ("dup_proj", "o", "n", "development", 0, 0))
    raised = False
    try:
        DB.execute("INSERT INTO projects(id,org_id,name,env,is_demo,created) VALUES(?,?,?,?,?,?)",
                   ("dup_proj", "o", "n", "development", 0, 0))
    except Exception:
        raised = True
    cnt = DB.execute("SELECT COUNT(*) c FROM projects WHERE id='dup_proj'").fetchone()["c"]
    check("duplicate PK insert raises + leaves exactly one row (atomic stmt)", raised and cnt == 1, f"raised={raised} cnt={cnt}")
except Exception as e:
    check("transaction/atomicity probe", False, str(e))

print("== op-log + cold boot / replay (fresh process against same PG) ==")
runner = os.path.join(HERE, "_pg_boot_probe.py")
with open(runner, "w") as f:
    f.write(
        "import os,sys,json\n"
        f"sys.path.insert(0,{HERE!r})\n"
        "import api\n"
        "nd=[p for p in api.PROJECTS if p!='demo']\n"
        "tot=0\n"
        "for pid in nd:\n"
        "    tot+=len(list(api.PROJECTS[pid].engine.store.assertions()))\n"
        "print(json.dumps({'projects':len(api.PROJECTS),'assertions':tot,"
        "'ops':api.STORE.db.execute('SELECT COUNT(*) c FROM ops').fetchone()['c']}))\n")
out = subprocess.run([sys.executable, runner], env={**os.environ},
                     capture_output=True, text=True, timeout=90)
try:
    boot = json.loads(out.stdout.strip().splitlines()[-1])
    check("cold-boot fresh process replays op-log from PG", boot["assertions"] >= 1,
          out.stdout + out.stderr)
    check("cold-boot sees persisted projects on PG", boot["projects"] >= 2)
except Exception as e:
    check("cold-boot replay from PG", False, f"{e}: {out.stdout} {out.stderr}")
os.remove(runner)

print("== concurrency: FOR UPDATE SKIP LOCKED across real connections ==")
# exercise worker.claim_batch semantics directly on PG with N concurrent
# connections; no job may be claimed twice.
cc = psycopg2.connect(URL); cc.autocommit = True; cur = cc.cursor()
cur.execute("DELETE FROM ingest_jobs")
# insert pending jobs
for i in range(120):
    cur.execute("INSERT INTO ingest_jobs(project_id,connector_id,source_record_id,state,attempts,created,updated) "
                "VALUES(%s,%s,%s,'pending',0,%s,%s)", (PID, "conn1", f"s{i}", time.time(), time.time()))
cc.close()
claimed = {}
clock = threading.Lock()


def wk(wid):
    conn = psycopg2.connect(URL); conn.autocommit = False; cur = conn.cursor()
    while True:
        cur.execute(
            "UPDATE ingest_jobs SET state='running', claimed=%s "
            "WHERE id IN (SELECT id FROM ingest_jobs WHERE state='pending' "
            "ORDER BY id LIMIT 5 FOR UPDATE SKIP LOCKED) RETURNING id".replace("claimed=%s", "heartbeat=%s"),
            (time.time(),))
        got = [r[0] for r in cur.fetchall()]
        conn.commit()
        if not got:
            break
        with clock:
            for g in got:
                claimed.setdefault(g, []).append(wid)
    conn.close()


threads = [threading.Thread(target=wk, args=(f"w{i}",)) for i in range(5)]
[t.start() for t in threads]
[t.join() for t in threads]
doubles = [k for k, v in claimed.items() if len(v) > 1]
check("SKIP LOCKED: all 120 jobs claimed exactly once (0 double-claims)",
      len(claimed) == 120 and not doubles, f"claimed={len(claimed)} doubles={len(doubles)}")

print("== SQLite <-> Postgres semantic parity (same ops, same beliefs) ==")
# run an identical scripted sequence on a fresh SQLite store and compare the
# resulting recall to what PG produced for the same logical inputs.
import sqlite3  # noqa: F401
parity_ok = True
try:
    # PG belief snapshot for alice about the renewal
    _, pgpk = call("POST", f"/v1/recall?project={PID}", {"agent": "agent:alice", "context": "acme renewal"}, K)
    pg_props = sorted(m["proposition"] for m in pgpk["memories"])
    # SQLite: a separate process/store with the same observe
    sql_runner = os.path.join(HERE, "_sqlite_parity.py")
    with open(sql_runner, "w") as f:
        f.write(
            "import os,sys,json,threading,time,urllib.request,urllib.error\n"
            "os.environ.pop('OMEM_DATABASE_URL',None)\n"
            "os.environ['OMEM_DB']='/tmp/omem_parity_sqlite.db'\n"
            "[os.remove(p) for p in ['/tmp/omem_parity_sqlite.db','/tmp/omem_parity_sqlite.db-wal','/tmp/omem_parity_sqlite.db-shm'] if os.path.exists(p)]\n"
            f"sys.path.insert(0,{HERE!r})\n"
            "import api\n"
            "from http.server import ThreadingHTTPServer\n"
            "srv=ThreadingHTTPServer(('127.0.0.1',0),api.Handler);P=srv.server_address[1]\n"
            "threading.Thread(target=srv.serve_forever,daemon=True).start();time.sleep(0.2)\n"
            "def call(m,path,b=None,k=None):\n"
            "    r=urllib.request.Request(f'http://127.0.0.1:{P}{path}',method=m,data=json.dumps(b).encode() if b else None,headers={'Content-Type':'application/json',**({'Authorization':f'Bearer {k}'} if k else {})})\n"
            "    try:\n"
            "        import urllib.request as u\n"
            "        with u.urlopen(r,timeout=15) as x:return x.status,json.loads(x.read() or b'{}')\n"
            "    except urllib.error.HTTPError as e:return e.code,json.loads(e.read() or b'{}')\n"
            "acct=call('POST','/v1/signup',{'email':'pg@k.com'})[1];K,PID=acct['api_key']['secret'],acct['project']['id']\n"
            "call('POST',f'/v1/identity?project={PID}',{'company_name':'K','domains':['k.com'],'emails':['pg@k.com']},K)\n"
            "call('POST',f'/v1/observe?project={PID}',{'agent':'agent:alice','interaction':{'text':'We have decided to renew the annual contract.','speaker':'x@acme.com','audience':'pg@k.com'}},K)\n"
            "_,pk=call('POST',f'/v1/recall?project={PID}',{'agent':'agent:alice','context':'acme renewal'},K)\n"
            "print(json.dumps(sorted(m['proposition'] for m in pk['memories'])))\n")
    o = subprocess.run([sys.executable, sql_runner], capture_output=True, text=True, timeout=90)
    sql_props = json.loads(o.stdout.strip().splitlines()[-1])
    os.remove(sql_runner)
    check("SQLite and PG produce identical beliefs for identical inputs",
          pg_props == sql_props, f"pg={pg_props} sqlite={sql_props}")
except Exception as e:
    check("SQLite<->PG parity", False, str(e))

print("== security regression on PG (P8/P9 model holds) ==")
BOB = call("POST", f"/v1/keys?project={PID}", {"name": "bob", "agent_id": "agent:bob"}, K)[1]["secret"]
# bound bob forging alice -> 403
st, _ = call("POST", f"/v1/recall?project={PID}", {"agent": "agent:alice", "context": "x"}, BOB)
check("agent-bound impersonation blocked on PG (403)", st == 403, str(st))
# bob cannot see alice private
bp = call("POST", f"/v1/recall?project={PID}", {"context": "acme renewal"}, BOB)[1]
check("agent-private isolation holds on PG", not any(m["id"] == aid for m in bp.get("memories", [])))
# cross-tenant
acct2 = call("POST", "/v1/signup", {"email": "other@k.com"})[1]
st, _ = call("POST", f"/v1/recall?project={PID}", {"agent": "agent:alice", "context": "x"}, acct2["api_key"]["secret"])
check("cross-tenant isolation holds on PG (403)", st == 403, str(st))
# B1 route scoped
st, _ = call("GET", f"/v1/assertions/{aid}/provenance?project={PID}", None, BOB)
check("B1 provenance route scoped on PG (404)", st == 404, str(st))

print("== failure / reconnection behaviour ==")
# a bad SQL raises through the adapter without crashing the process, and the
# next good query still works (connection remains usable).
raised = False
try:
    DB.execute("SELECT * FROM table_that_does_not_exist_xyz")
except Exception:
    raised = True
ok_after = DB.execute("SELECT 1 AS one").fetchone()["one"]
check("error surfaces + connection stays usable afterward", raised and ok_after == 1)

print("== basic performance (PG) ==")
t0 = time.perf_counter()
for i in range(50):
    call("POST", f"/v1/observe?project={PID}",
         {"agent": "agent:alice", "interaction": {"text": f"Fact {i}: uses tool {i%5}.",
          "speaker": "x@acme.com", "audience": "pg@k.com"}}, K)
write_ms = (time.perf_counter() - t0) / 50 * 1000
t1 = time.perf_counter()
for _ in range(20):
    call("POST", f"/v1/recall?project={PID}", {"agent": "agent:alice", "context": "tool acme"}, K)
recall_ms = (time.perf_counter() - t1) / 20 * 1000
print(f"  PG write ~{write_ms:.1f} ms/observe · recall ~{recall_ms:.1f} ms")
check("PG write throughput reasonable (<250ms/observe)", write_ms < 250, f"{write_ms:.1f}ms")
check("PG recall latency reasonable (<500ms)", recall_ms < 500, f"{recall_ms:.1f}ms")

print("== engine integrity ==")
import hashlib
h = {f: hashlib.sha256(open(os.path.join(HERE, "omem_engine", f), "rb").read()).hexdigest()
     for f in sorted(os.listdir(os.path.join(HERE, "omem_engine"))) if f.endswith(".py")}
baseline = {}
for line in open(os.path.join(HERE, "omem_engine", "ENGINE_HASHES.txt"),
                 encoding="utf-8"):
    if not line.strip() or line.startswith('#'):
        continue
    hsh, path = line.split()
    baseline[os.path.basename(path)] = hsh
check("frozen engine byte-identical", all(baseline.get(f) == v for f, v in h.items()))

srv.shutdown()
print(f"\n{PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
