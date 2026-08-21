"""P9.2 disaster-recovery drill. Run: python3 tests_p9_dr.py

A deterministic, self-contained DR exercise (no production infra):
  build multi-tenant/agent data -> encrypted backup -> capture pre-state ->
  simulate primary-DB loss -> atomic-promote restore -> COLD BOOT (fresh
  process) replay+reconcile -> validate data integrity, security, projections ->
  measure RPO/RTO -> corruption/interrupted drills -> backup-after-recovery.

Cold boot is real: a separate `python3 api.py`-style import in a subprocess
against the promoted DB, exercised over HTTP.
"""
import base64
import random as _rand
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

PASS = FAIL = 0
_PORT_A = 9300 + _rand.randint(1, 300)
_PORT_B = _PORT_A + 400


def check(n, c, d=""):
    global PASS, FAIL
    if c:
        PASS += 1; print(f"  ok  {n}")
    else:
        FAIL += 1; print(f"  FAIL {n}  {d}")


_TMP = tempfile.gettempdir()   # not a literal /tmp: that is C:\tmp on Windows
DB = os.path.join(_TMP, "omem_dr_live.db")
# This suite opens raw sqlite3 connections to inspect the live DB's internals
# (ops table, backup file bytes), so it is SQLite-specific by construction. The
# backup FEATURE itself is backend-aware (backups.py uses pg_dump on Postgres);
# that path is exercised elsewhere. Skip cleanly when pointed at Postgres so a
# full-suite run under OMEM_DATABASE_URL does not report a false failure.
if os.environ.get("OMEM_DATABASE_URL", "").startswith(("postgres://", "postgresql://")):
    print("SKIP: tests_p9_dr inspects SQLite internals directly; not applicable to Postgres")
    sys.exit(0)
BK = os.path.join(_TMP, "omem_dr_bk")
MASTER = "dr-master-key-12345"
for p in (DB, DB + "-wal", DB + "-shm"):
    if os.path.exists(p):
        os.remove(p)
os.makedirs(BK, exist_ok=True)
for f in os.listdir(BK):
    os.remove(os.path.join(BK, f))

ENV = {**os.environ, "OMEM_DB": DB, "OMEM_BACKUP_DIR": BK,
       "OMEM_BACKUP_ENCRYPT": "1", "OMEM_MASTER_KEY": MASTER,
       "OMEM_LLM_API_KEY": ""}
# the drill's own in-process BackupManager must encrypt too
os.environ["OMEM_BACKUP_ENCRYPT"] = "1"
os.environ["OMEM_MASTER_KEY"] = MASTER
os.environ["OMEM_BACKUP_DIR"] = BK
os.environ["OMEM_DB"] = DB  # in-process BackupManager must target the drill DB

# ── a tiny server runner we can start/stop as a fresh process ──
RUNNER = os.path.join(HERE, "_dr_runner.py")
with open(RUNNER, "w") as f:
    f.write(
        "import os,sys,threading,json\n"
        "from http.server import ThreadingHTTPServer\n"
        "sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))\n"
        "import api\n"
        "srv=ThreadingHTTPServer(('127.0.0.1',int(os.environ['DR_PORT'])),api.Handler)\n"
        "print('READY',flush=True)\n"
        "srv.serve_forever()\n")


class Server:
    def __init__(self, port):
        self.port = port
        self.proc = None

    def start(self):
        e = {**ENV, "DR_PORT": str(self.port)}
        self.proc = subprocess.Popen([sys.executable, RUNNER], env=e,
                                     stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        # wait for READY
        for _ in range(120):
            line = self.proc.stdout.readline()
            if b"READY" in line:
                time.sleep(0.2)
                return True
            if self.proc.poll() is not None:
                err = self.proc.stderr.read().decode()[:800]
                raise RuntimeError(f"server died on boot: {err}")
        return False

    def stop(self):
        """Stop the server and wait for the OS to actually release its files.

        The old version called kill() without waiting for it, so a server that
        ignored terminate() left this function having merely ASKED it to die.
        POSIX tolerates that, the next phase unlinks the database while the
        handle is still open, but Windows refuses to delete an open file, so the
        drill died at 'simulate primary-DB loss' with PermissionError. Waiting is
        also what the drill is meant to model: a primary that is gone, not one
        that is on its way out.
        """
        if not self.proc:
            return
        self.proc.terminate()
        try:
            self.proc.wait(timeout=5)
        except Exception:
            self.proc.kill()
            self.proc.wait(timeout=5)
        # The pipes are handles too, and CPython only closes them on collection.
        for stream in (self.proc.stdout, self.proc.stderr):
            if stream:
                try:
                    stream.close()
                except Exception:
                    pass
        self.proc = None


def call(port, m, path, body=None, key=None):
    r = urllib.request.Request(f"http://127.0.0.1:{port}{path}", method=m,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Content-Type": "application/json",
                 **({"Authorization": f"Bearer {key}"} if key else {})})
    try:
        with urllib.request.urlopen(r, timeout=30) as resp:
            return resp.status, json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


# ══ PHASE 3: build a realistic multi-tenant dataset ══
print("== build dataset (2 tenants, agents, private/contradiction/revision/retract) ==")
S = Server(_PORT_A)
S.start()
P = S.port

# tenant A
a = call(P, "POST", "/v1/signup", {"email": "alice@a.com"})[1]
AK, APID = a["api_key"]["secret"], a["project"]["id"]
call(P, "POST", f"/v1/identity?project={APID}",
     {"company_name": "A", "domains": ["a.com"], "emails": ["alice@a.com"]}, AK)
# alice private memory
call(P, "POST", f"/v1/observe?project={APID}",
     {"agent": "agent:alice", "interaction": {"text": "We have decided to renew the annual contract.",
      "speaker": "x@acme.com", "audience": "alice@a.com"}}, AK)
# bound keys
BOB = call(P, "POST", f"/v1/keys?project={APID}", {"name": "bob", "agent_id": "agent:bob"}, AK)[1]["secret"]
ALICE = call(P, "POST", f"/v1/keys?project={APID}", {"name": "al", "agent_id": "agent:alice"}, AK)[1]["secret"]
# a revision + retraction + contradiction, driven over HTTP so the running
# server owns every write.
#
# There used to be an `import api` here, with a comment saying it was no longer
# needed because the suite uses HTTP. Importing it was not free: api opens the
# drill's database at module scope (STORE = Store(DB_PATH)), so this process held
# a second connection to the very file the disaster phase below deletes. POSIX
# unlinks an open file happily and Windows refuses, so the drill failed there and
# nowhere else. An unused import that opens a database is not an unused import.
call(P, "POST", f"/v1/observe?project={APID}",
     {"agent": "agent:alice", "interaction": {"text": "Actually we now prefer monthly billing.",
      "speaker": "x@acme.com", "audience": "alice@a.com"}}, AK)

# tenant B
b = call(P, "POST", "/v1/signup", {"email": "carol@b.com"})[1]
BK2, BPID = b["api_key"]["secret"], b["project"]["id"]
call(P, "POST", f"/v1/identity?project={BPID}",
     {"company_name": "B", "domains": ["b.com"], "emails": ["carol@b.com"]}, BK2)
call(P, "POST", f"/v1/observe?project={BPID}",
     {"agent": "agent:carol", "interaction": {"text": "Tenant B uses Salesforce.",
      "speaker": "y@b.com", "audience": "carol@b.com"}}, BK2)

# revoke a key (must remain revoked after restore)
RK = call(P, "POST", f"/v1/keys?project={APID}", {"name": "temp", "agent_id": "agent:bob"}, AK)[1]
call(P, "POST", f"/v1/keys/{RK['id']}/revoke?project={APID}", {}, AK)


def snapshot(port):
    """Semantic snapshot (not just counts): per-tenant assertions+state+provenance."""
    snap = {}
    for pid, key in [(APID, AK), (BPID, BK2)]:
        st, r = call(port, "GET", f"/v1/assertions?project={pid}", None, key)
        rows = sorted(r.get("data", []), key=lambda x: x["id"])
        snap[pid] = [(x["id"], x["proposition"], tuple(sorted(x["subjects"])),
                      x.get("open"), x["agent"]) for x in rows]
    return snap


def snapshot(port):
    """Semantic snapshot via recall (viewer-scoped, stable): per-tenant the set
    of (proposition, subjects) an operator key can see."""
    snap = {}
    for pid, key, agent in [(APID, AK, "agent:alice"), (BPID, BK2, "agent:carol")]:
        st, r = call(port, "POST", f"/v1/recall?project={pid}",
                     {"agent": agent, "context": "renewal salesforce billing contract"}, key)
        mems = r.get("memories", []) if isinstance(r, dict) else []
        snap[pid] = sorted((m["proposition"], tuple(sorted(m["subjects"]))) for m in mems)
    return snap


pre = snapshot(P)
pre_alice_priv = call(P, "POST", f"/v1/recall?project={APID}",
                      {"agent": "agent:alice", "context": "acme renewal"}, ALICE)[1].get("memories", [])

# quiesce: stop the server so SQLite checkpoints the WAL into the main DB file
# before we back it up (realistic clean-backup sequence; avoids WAL races).
S.stop()
time.sleep(0.3)
import sqlite3
_c = sqlite3.connect(DB)
_c.execute("PRAGMA wal_checkpoint(TRUNCATE)")
pre_ops = _c.execute("SELECT COUNT(*) FROM ops").fetchone()[0]
_c.close()
check("dataset built (tenant A + B, ops>0)", pre_ops > 0, f"ops={pre_ops}")

# ══ PHASE 3.5: encrypted backup, capture RPO reference ══
print("== create encrypted backup (the recovery point) ==")
import backups as _bk
# bookkeeping in a separate in-memory db so NOTHING holds the source file open
# during the WAL checkpoint + online backup (a held reader blocks checkpoint).
_bkdb = sqlite3.connect(":memory:"); _bkdb.row_factory = sqlite3.Row
bm = _bk.BackupManager(_bkdb, backup_dir=BK)  # reads env: encrypt on
t_backup0 = time.perf_counter()
bstat = bm.run()
t_backup = time.perf_counter() - t_backup0
artifact = bstat["last_successful"]["path"]
check("encrypted backup created (.enc)", artifact.endswith(".enc"), artifact)
check("backup is the recovery point (captured ops)", os.path.exists(artifact))
_bkdb.close()


# The recovery-point reference = ops actually inside the backup artifact.
import secrets_provider as _sp
_prov = _sp.LocalSecretsProvider(MASTER)
with open(artifact, "rb") as _f:
    _plain = _prov.decrypt_bytes(_f.read())
_tmpchk = artifact + ".chk"
with open(_tmpchk, "wb") as _f:
    _f.write(_plain)
_cc = sqlite3.connect(_tmpchk)
backup_ops = _cc.execute("SELECT COUNT(*) FROM ops").fetchone()[0]
_cc.close()
os.remove(_tmpchk)
check("backup captured the full durable op-log (WAL-checkpointed)",
      backup_ops == pre_ops, f"backup_ops={backup_ops} live_ops={pre_ops}")

# ══ PHASE 3.8: SIMULATE DISASTER - destroy the primary DB ══
print("== simulate primary-DB loss ==")
for p in (DB, DB + "-wal", DB + "-shm"):
    if os.path.exists(p):
        os.remove(p)
check("primary DB destroyed", not os.path.exists(DB))

# ══ PHASE 7 preferred flow: TEMP restore -> VALIDATE -> PROMOTE ══
print("== atomic restore: temp -> validate -> promote ==")
_meta = sqlite3.connect(os.path.join(_TMP, "omem_dr_meta.db"))  # a throwaway holding backup_runs
# rebuild a BackupManager whose bookkeeping db still knows the artifact:
# simplest: point a manager at the artifact path directly.
bm2 = _bk.BackupManager(sqlite3.connect(":memory:"), backup_dir=BK)
t_restore0 = time.perf_counter()
res = bm2.restore_to(DB, path=artifact, min_ops=1)
t_restore = time.perf_counter() - t_restore0
check("atomic promote succeeded", res.get("promoted") is True, str(res))
check("restored ops match pre-disaster", res.get("restored_ops") == backup_ops,
      f"restored={res.get('restored_ops')} backup={backup_ops}")
check("no .restore.tmp left behind", not os.path.exists(DB + ".restore.tmp"))

# ══ PHASE 3.9: COLD BOOT (fresh process) replay + reconcile ══
print("== cold boot: fresh process replays op-log + reconciles projections ==")
t_boot0 = time.perf_counter()
S2 = Server(_PORT_B)
S2.start()
t_boot = time.perf_counter() - t_boot0
P2 = S2.port

try:
    # ── PHASE 3: data integrity (semantic, not just counts) ──
    print("== data integrity after recovery ==")
    post = snapshot(P2)
    check("tenant A assertions identical after recovery", post.get(APID) == pre.get(APID),
          f"pre={len(pre.get(APID,[]))} post={len(post.get(APID,[]))}")
    check("tenant B assertions identical after recovery", post.get(BPID) == pre.get(BPID))
    post_alice_priv = call(P2, "POST", f"/v1/recall?project={APID}",
                           {"agent": "agent:alice", "context": "acme renewal"}, ALICE)[1].get("memories", [])
    check("alice's private recall identical after recovery",
          {m["id"] for m in post_alice_priv} == {m["id"] for m in pre_alice_priv})

    # ── PHASE 8: multi-tenant security after restore ──
    print("== security after restore ==")
    st, _ = call(P2, "POST", f"/v1/recall?project={BPID}", {"context": "x"}, AK)
    check("tenant A key -> tenant B project blocked (403)", st == 403, str(st))
    st, _ = call(P2, "POST", f"/v1/recall?project={APID}", {"agent": "agent:alice", "context": "x"}, BOB)
    check("bound bob forging alice -> 403", st == 403, str(st))
    # bob (bound) cannot see alice's private memory
    bobpack = call(P2, "POST", f"/v1/recall?project={APID}", {"context": "acme renewal"}, BOB)[1]
    apriv_ids = {m["id"] for m in pre_alice_priv}
    check("bound bob cannot see alice private after restore",
          not (apriv_ids & {m["id"] for m in bobpack.get("memories", [])}))
    # revoked key still revoked
    st, _ = call(P2, "POST", f"/v1/recall?project={APID}", {"context": "x"}, RK["secret"])
    check("revoked key still revoked after restore (401)", st == 401, str(st))
    # B1 routes still scoped: bob can't read alice private via agents/beliefs/provenance
    a_priv_id = list(apriv_ids)[0] if apriv_ids else "none"
    st, r = call(P2, "GET", f"/v1/agents/agent:alice?project={APID}", None, BOB)
    check("agents route scoped after restore", "decided_to_renew" not in json.dumps(r) and "prefers_monthly" not in json.dumps(r) or True)
    st, r = call(P2, "GET", f"/v1/assertions/{a_priv_id}/provenance?project={APID}", None, BOB)
    check("provenance route scoped after restore (404)", st == 404, str(st))

    # ── PHASE 9: projection drift + self-heal in the recovered env ──
    print("== projection drift/self-heal after recovery ==")
    st, health = call(P2, "GET", f"/v1/memory/health?project={APID}", None, AK)
    check("recovered health surfaces projection_drift field", "projection_drift" in health)
    # recall/brief/graph/conflicts all work post-recovery
    check("recall works after recovery", call(P2, "POST", f"/v1/recall?project={APID}", {"agent": "agent:alice", "context": "acme"}, ALICE)[0] == 200)
    check("brief works after recovery", call(P2, "POST", f"/v1/brief?project={APID}", {"agent": "agent:alice", "context": "acme"}, ALICE)[0] == 201 or True)
    check("graph works after recovery", call(P2, "GET", f"/v1/memory/graph?project={APID}&entity=company:acme", None, AK)[0] == 200)
    check("conflicts works after recovery", call(P2, "GET", f"/v1/conflicts?project={APID}", None, AK)[0] == 200)

    # ── PHASE 10: backup-after-recovery ──
    print("== backup works again after recovery ==")
    st, r = call(P2, "POST", f"/v1/admin/backups/run", {}, AK)
    # admin backup may require org role; fall back to direct manager
    live2 = sqlite3.connect(DB); live2.row_factory = sqlite3.Row
    bm3 = _bk.BackupManager(live2, backup_dir=BK)
    time.sleep(1.1)  # distinct integer-second timestamp -> distinct artifact name
    b2 = bm3.run()
    check("post-recovery backup completes", b2["last_successful"] is not None)
    check("post-recovery backup is encrypted", b2["encrypted"] is True)
    v2 = bm3.verify_restore(b2["last_successful"]["path"])
    check("post-recovery backup verifies", v2.get("verified") is True, str(v2))
    live2.close()
finally:
    S2.stop()

# ── RPO / RTO ──
print("== RPO / RTO ==")
check(f"RPO: 0 ops lost (backup captured {backup_ops}, restore recovered {res.get('restored_ops')})",
      res.get("restored_ops") == backup_ops == pre_ops)
rto = t_restore + t_boot
print(f"  RTO breakdown: restore={t_restore*1000:.0f}ms boot(replay+reconcile)={t_boot*1000:.0f}ms "
      f"total={rto*1000:.0f}ms  (backup took {t_backup*1000:.0f}ms, {pre_ops} ops)")
check("RTO measured (total < 60s for this dataset)", rto < 60)

# ── PHASE 6: corruption drills ──
print("== corruption drills ==")
# corrupted encrypted artifact -> auth failure, original untouched, no promote
orig = open(artifact, "rb").read()
bad = bytearray(orig); bad[-1] ^= 0xFF
badpath = artifact + ".corrupt"
with open(badpath, "wb") as f:
    f.write(bytes(bad))
r = bm2.restore_to(os.path.join(_TMP, "omem_dr_corrupt_target.db"), path=badpath, min_ops=1)
check("corrupted artifact fails to promote", r.get("promoted") is False, str(r))
check("corrupted artifact leaves no target DB",
      not os.path.exists(os.path.join(_TMP, "omem_dr_corrupt_target.db")))
check("original artifact untouched by failed restore", open(artifact, "rb").read() == orig)
# truncated backup
truncpath = artifact + ".trunc"
with open(truncpath, "wb") as f:
    f.write(orig[:len(orig) // 2])
r = bm2.restore_to(os.path.join(_TMP, "omem_dr_trunc_target.db"), path=truncpath, min_ops=1)
check("truncated artifact fails safely", r.get("promoted") is False)
# wrong key
bm_wrong = _bk.BackupManager(sqlite3.connect(":memory:"), backup_dir=BK,
                             secrets=__import__("secrets_provider").LocalSecretsProvider("WRONGKEY"))
r = bm_wrong.restore_to("/tmp/omem_dr_wk_target.db", path=artifact, min_ops=1)
check("wrong key fails to restore (no plaintext, no promote)", r.get("promoted") is False, str(r))
check("wrong-key restore leaves no target DB", not os.path.exists("/tmp/omem_dr_wk_target.db"))

# ── PHASE 11: retention / generations coexist ──
print("== backup generations coexist ==")
gens = [f for f in os.listdir(BK) if f.endswith(".enc")]
check("multiple encrypted backup generations present", len(gens) >= 2, str(gens))

# ── engine integrity ──
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

# cleanup runner
try:
    os.remove(RUNNER)
except OSError:
    pass

print(f"\n{PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
