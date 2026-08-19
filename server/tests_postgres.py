"""PostgreSQL persistence + durable worker tests.
Run: OMEM_DATABASE_URL=postgres://omem:omem-dev@127.0.0.1/omem python3 tests_postgres.py
Skips (exit 0 with notice) if no OMEM_DATABASE_URL is set or PG is unreachable —
the SQLite suites remain the credential-free path.

Verifies: boot + demo seed on PG, engine replay across process-equivalent
restart, adapter upsert/lastrowid/rowcount semantics, multi-worker SKIP LOCKED
claiming with zero double-claims, and cross-backend semantic equivalence."""
import os
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

URL = os.environ.get("OMEM_DATABASE_URL", "")

# ── credential-free: verify the SQL TRANSLATION for P3–P7 upsert tables ──
# Does NOT require a live Postgres server — checks that db_adapter produces
# valid ON CONFLICT SQL for the tables added after the adapter was written
# (the P7 audit found these missing from the upsert maps).
import db_adapter as _dba  # noqa: E402
_tx_pass = _tx_fail = 0


def _tx(name, cond):
    global _tx_pass, _tx_fail
    if cond:
        _tx_pass += 1
    else:
        _tx_fail += 1
        print(f"  FAIL translate: {name}")


for _tbl, _pk in [("candidate_subjects", "project_id,subject,assertion_id"),
                  ("candidate_tokens", "project_id,token,assertion_id"),
                  ("memory_edges", "project_id,assertion_id"),
                  ("memory_scopes", "project_id,assertion_id"),
                  ("memory_class", "project_id,assertion_id"),
                  ("relationship_overrides", "project_id,key_type,key"),
                  ("team_members", "project_id,team_id,agent_id")]:
    _out = _dba.translate(f"INSERT OR REPLACE INTO {_tbl} VALUES(?,?,?,?)")
    _tx(f"{_tbl} REPLACE->ON CONFLICT", f"ON CONFLICT ({_pk}) DO UPDATE" in _out)
_out = _dba.translate("INSERT OR IGNORE INTO consolidation_state VALUES(?,?,?,?,?,?,?)")
_tx("consolidation_state IGNORE->DO NOTHING",
    "ON CONFLICT (project_id,key) DO NOTHING" in _out)
_out = _dba.translate("INSERT OR IGNORE INTO source_records VALUES(?,?,?,?,?,?,?,?)")
_tx("source_records IGNORE->DO NOTHING on UNIQUE",
    "ON CONFLICT (connector_id,external_id) DO NOTHING" in _out)

# COMPLETENESS GUARD: every table written via INSERT OR REPLACE/IGNORE anywhere
# in the codebase MUST be in both Postgres maps. This stops the P7/P8 bug class
# (a new projection table shipped without a PG mapping) from recurring silently.
import glob as _glob  # noqa: E402
import re as _re  # noqa: E402
_upsert_tables = set()
for _f in _glob.glob(os.path.join(os.path.dirname(os.path.abspath(__file__)), "*.py")):
    _bn = os.path.basename(_f)
    if _bn.startswith("tests_") or _bn == "db_adapter.py":
        continue  # db_adapter documents the syntax in comments ('INTO t')
    # encoding is explicit: open() defaults to the locale codec, which is
    # cp1252 on a Western Windows install and raises UnicodeDecodeError on
    # the first source file containing a box-drawing character. Source is
    # UTF-8 regardless of who is reading it.
    with open(_f, encoding="utf-8") as _fh:
        _src = _fh.read()
    for _m in _re.finditer(r"INSERT OR (?:REPLACE|IGNORE) INTO ([a-z_]+)", _src):
        _upsert_tables.add(_m.group(1))
_unmapped_pk = sorted(t for t in _upsert_tables if t not in _dba._UPSERT_PK)
_unmapped_cols = sorted(t for t in _upsert_tables if t not in _dba._columns_of)
_tx(f"every upsert table has a PK mapping (unmapped: {_unmapped_pk})", not _unmapped_pk)
_tx(f"every upsert table has a column mapping (unmapped: {_unmapped_cols})", not _unmapped_cols)
print(f"translation checks: {_tx_pass} passed, {_tx_fail} failed")
if _tx_fail:
    sys.exit(1)

if not URL.startswith("postgres"):
    print("SKIP: OMEM_DATABASE_URL not set to a postgres URL; SQLite suites cover the default path.")
    print("NOT VERIFIED — no Postgres instance available (live-DB checks skipped).")
    sys.exit(0)
try:
    import psycopg2
    psycopg2.connect(URL).close()
except Exception as e:
    print(f"SKIP: postgres unreachable ({e})")
    sys.exit(0)

# fresh schema
_admin = psycopg2.connect(URL)
_admin.autocommit = True
_c = _admin.cursor()
_c.execute("DROP SCHEMA public CASCADE")
_c.execute("CREATE SCHEMA public")
_admin.close()

import os as _os_seed
_os_seed.environ['OMEM_SEED_DEMO']='1'
import api  # noqa: E402  (boots on PG)
from worker import claim_batch  # noqa: E402

PASS = FAIL = 0


def check(n, c, d=""):
    global PASS, FAIL
    if c:
        PASS += 1; print(f"  ok  {n}")
    else:
        FAIL += 1; print(f"  FAIL {n}  {d}")


print("== boot on postgres ==")
check("adapter selected", type(api.STORE.db).__name__ == "PgDB")
check("demo project seeded through engine replay", "demo" in api.PROJECTS)
demo = api.PROJECTS["demo"]
check("demo contradiction decided by engine",
      demo.engine.proposition_state(["customer:alice"], "prefers_email_over_phone", demo.now()) == "CONTRADICTED")

print("== adapter semantics ==")
db = api.STORE.db
db.execute("CREATE TABLE IF NOT EXISTS t_adapter(id INTEGER PRIMARY KEY AUTOINCREMENT, v TEXT)")
r = db.execute("INSERT INTO t_adapter(v) VALUES(?)", ("a",))
check("lastrowid from serial", r.lastrowid == 1)
r = db.execute("UPDATE t_adapter SET v=? WHERE v=?", ("b", "a"))
check("rowcount on update", r.rowcount == 1)
row = db.execute("SELECT id, v FROM t_adapter").fetchone()
check("row by name and index", row["v"] == "b" and row[1] == "b")
api.ENT.count_recall("pgp", "a1")
api.ENT.count_recall("pgp", "a1")
check("qualified upsert increments", api.ENT.top_recalled("pgp")[0]["count"] == 2)

print("== engine state survives restart (replay from PG ops log) ==")
org = api.STORE.signup("pg@corp.com", "PG")
proj = api.STORE.create_project(api.STORE.org_for_user(org["user_id"])["id"], "PG")
PID = proj["id"]
api.PROJECTS[PID] = api.Project(PID, "PG", "development", proj["org_id"])
api.CONTRADICTIONS[PID] = []
p = api.PROJECTS[PID]
api.record(p, "agent", {"id": "a1", "kind": "system"})
api.record(p, "entity", {"id": "customer:pg", "type": "person"})
api.record(p, "assert", {"id": "as1", "agent": "a1", "subjects": ["customer:pg"],
                          "proposition": "runs_on_postgres", "assertion_time": p.now()})
import importlib
sys.modules.pop("api")
api2 = importlib.import_module("api")
p2 = api2.PROJECTS.get(PID)
check("belief replayed after fresh boot on PG", p2 is not None and
      p2.engine.proposition_state(["customer:pg"], "runs_on_postgres", p2.now()) == "BELIEVED_TRUE")

print("== multi-worker SKIP LOCKED (no double-claims) ==")
conn = api2.INGEST.add_connector(PID, "webhook", "wh", {}, agent_id="connector:wh")
for i in range(12):
    api2.INGEST.push_item(conn["id"], f"e{i}", {"customer": f"c{i}", "subject": "s", "body": "prefer email"})
api2.INGEST.poll_connector(conn["id"])
claims = {"w1": [], "w2": []}


def work(wid):
    empty = 0
    while empty < 5:  # brief retry window: per-tenant cap can starve a worker momentarily
        got = claim_batch(api2.STORE.db, limit=2)
        if not got:
            empty += 1
            time.sleep(0.02)
            continue
        empty = 0
        for jid, _ in got:
            job = api2.STORE.db.execute("SELECT * FROM ingest_jobs WHERE id=?", (jid,)).fetchone()
            api2.INGEST._process_one(job)
            claims[wid].append(jid)


t1 = threading.Thread(target=work, args=("w1",))
t2 = threading.Thread(target=work, args=("w2",))
t1.start(); t2.start(); t1.join(); t2.join()
allc = claims["w1"] + claims["w2"]
check("all 12 jobs processed", len(allc) == 12)
check("zero double-claims", len(set(allc)) == 12)
check("both workers participated", len(claims["w1"]) > 0 and len(claims["w2"]) > 0,
      f"w1={len(claims['w1'])} w2={len(claims['w2'])}")
check("all completed", api2.INGEST.stats(PID)["completed"] == 12)
p2 = api2.PROJECTS[PID]
check("engine decided states from worker-processed jobs",
      p2.engine.proposition_state(["customer:c3"], "prefers_email_over_phone", p2.now()) == "BELIEVED_TRUE")

print("== stale recovery on PG ==")
api2.STORE.db.execute(
    "INSERT INTO ingest_jobs(project_id,connector_id,source_record_id,state,heartbeat,created,updated) "
    "VALUES(?,?,?,'running',?,?,?)", (PID, conn["id"], "s", time.time() - 300, time.time(), time.time()))
check("stale running job recovered", api2.INGEST.recover_stale(older_than=60) >= 1)

print("== hardening migrations on PG ==")
vers = [r["version"] for r in api2.STORE.db.execute("SELECT version FROM schema_migrations ORDER BY version")]
check("v2-indexes + v3-fks applied", "v2-indexes" in vers and "v3-fks" in vers, str(vers))
fk = api2.STORE.db.execute(
    "SELECT COUNT(*) c FROM information_schema.table_constraints WHERE constraint_name='fk_keys_project'").fetchone()
check("FK constraint exists in catalog", fk["c"] == 1)

print("== FK cascade: deleting a connector removes its jobs/sources ==")
cX = api2.INGEST.add_connector(PID, "webhook", "fkc", {}, agent_id="connector:fk")
api2.INGEST.push_item(cX["id"], "fk1", {"customer": "fk", "subject": "s", "body": "prefer email"})
api2.INGEST.poll_connector(cX["id"])
n_src = api2.STORE.db.execute("SELECT COUNT(*) c FROM source_records WHERE connector_id=?", (cX["id"],)).fetchone()["c"]
check("source row exists pre-delete", n_src == 1)
api2.STORE.db.execute("DELETE FROM connectors WHERE id=?", (cX["id"],))
n_src2 = api2.STORE.db.execute("SELECT COUNT(*) c FROM source_records WHERE connector_id=?", (cX["id"],)).fetchone()["c"]
n_jobs = api2.STORE.db.execute("SELECT COUNT(*) c FROM ingest_jobs WHERE connector_id=?", (cX["id"],)).fetchone()["c"]
check("cascade removed sources + jobs", n_src2 == 0 and n_jobs == 0)

print("== concurrent writes: two projects, parallel assertions ==")
orgc = api2.STORE.signup("cc@corp.com", "CC")
pc = api2.STORE.create_project(api2.STORE.org_for_user(orgc["user_id"])["id"], "CC")
P2 = pc["id"]
api2.PROJECTS[P2] = api2.Project(P2, "CC", "development", pc["org_id"])
api2.CONTRADICTIONS[P2] = []
errors = []


def writer(pid, n):
    try:
        p_ = api2.PROJECTS[pid]
        api2.record(p_, "agent", {"id": f"w{n}", "kind": "system"})
        api2.record(p_, "entity", {"id": f"customer:w{n}", "type": "person"})
        for i in range(10):
            api2.record(p_, "assert", {"id": f"cw-{n}-{i}", "agent": f"w{n}",
                                        "subjects": [f"customer:w{n}"],
                                        "proposition": f"prop_{i}", "assertion_time": p_.now()})
    except Exception as e:
        errors.append(str(e))


tw1 = threading.Thread(target=writer, args=(PID, 1))
tw2 = threading.Thread(target=writer, args=(P2, 2))
tw1.start(); tw2.start(); tw1.join(); tw2.join()
check("no errors under concurrent writes", not errors, str(errors[:1]))
check("both projects committed all 10", 
      sum(1 for a in api2.PROJECTS[PID].engine.store.assertions() if a.id.startswith("cw-1-")) == 10 and
      sum(1 for a in api2.PROJECTS[P2].engine.store.assertions() if a.id.startswith("cw-2-")) == 10)

print("== adapter escapes literal percent signs (regression) ==")
from db_adapter import translate as _tr
check("literal % doubled, placeholders intact",
      _tr("SELECT * FROM t WHERE p LIKE 'abc%' AND x=?")
      == "SELECT * FROM t WHERE p LIKE 'abc%%' AND x=%s")
db.execute("CREATE TABLE IF NOT EXISTS t_pct(p TEXT)")
db.execute("INSERT INTO t_pct(p) VALUES(?)", ("concrete",))
db.execute("INSERT INTO t_pct(p) VALUES(?)", ("other",))
_hit = db.execute("SELECT COUNT(*) c FROM t_pct WHERE p LIKE 'conc%' AND p<>?", ("x",)).fetchone()
check("LIKE with a literal % executes on postgres", _hit["c"] == 1, str(_hit["c"]))

print(f"\n{PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
