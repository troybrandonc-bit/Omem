"""Persistence for OMEM. SQLite, stdlib only.

Design: the engine stays authoritative and in-memory. Durability comes from an
append-only operations log per project: every accepted write is recorded here and
replayed through the engine at boot. This mirrors OMEM's own log-fold model and
adds zero semantics. Also stores the SaaS layer: users, sessions, orgs, projects,
API keys (hashed, reveal-once).
"""
from __future__ import annotations
import hashlib
import hmac
import json
import os
import secrets
import socket
import sqlite3
import threading
import time

SCHEMA = """
CREATE TABLE IF NOT EXISTS users(
  id TEXT PRIMARY KEY, email TEXT UNIQUE NOT NULL, created REAL NOT NULL,
  pw_hash TEXT);
CREATE TABLE IF NOT EXISTS sessions(
  token TEXT PRIMARY KEY, user_id TEXT NOT NULL, created REAL NOT NULL,
  expires REAL, revoked INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS user_mfa(
  user_id TEXT PRIMARY KEY, secret TEXT NOT NULL, enabled INTEGER NOT NULL DEFAULT 0,
  created REAL NOT NULL);
CREATE TABLE IF NOT EXISTS orgs(
  id TEXT PRIMARY KEY, name TEXT NOT NULL, user_id TEXT NOT NULL, created REAL NOT NULL);
CREATE TABLE IF NOT EXISTS projects(
  id TEXT PRIMARY KEY, org_id TEXT NOT NULL, name TEXT NOT NULL,
  env TEXT NOT NULL DEFAULT 'development', is_demo INTEGER NOT NULL DEFAULT 0,
  created REAL NOT NULL);
CREATE TABLE IF NOT EXISTS ops(
  seq INTEGER PRIMARY KEY AUTOINCREMENT, project_id TEXT NOT NULL,
  kind TEXT NOT NULL, args TEXT NOT NULL, clock INTEGER NOT NULL, ts REAL NOT NULL);
CREATE INDEX IF NOT EXISTS ops_proj ON ops(project_id, seq);
CREATE TABLE IF NOT EXISTS keys(
  id TEXT PRIMARY KEY, project_id TEXT NOT NULL, name TEXT NOT NULL,
  prefix TEXT NOT NULL, hash TEXT NOT NULL, role TEXT NOT NULL DEFAULT 'developer',
  created REAL NOT NULL, last_used REAL, revoked INTEGER NOT NULL DEFAULT 0,
  expires REAL, agent_id TEXT);
"""


from secrets_provider import (  # noqa: E402
    decrypt_content, encrypt_content,
)


def _now() -> float:
    return time.time()


class WriterLock:
    """One writer per database, enforced instead of documented.

    THE HAZARD. The engine is authoritative IN MEMORY and rebuilt by replaying
    the ops log at boot. Two API processes against one database therefore hold
    two independent engines: writes through process A are invisible to process B
    until B restarts, and both keep appending to the same ops log. Nothing
    errors. Both answer `believes()` confidently and differently, and the
    disagreement survives into whatever the agents did about it. For a system
    whose entire claim is that the same question has the same answer, silently
    returning two answers is the worst failure available to it.

    Running a second replica or a rolling deploy did exactly this, and the only
    thing standing between an operator and it was a sentence in DEPLOYMENT.md.
    Now the second process refuses to start and says why. That is not high
    availability. It is the honest version of not having it, and it converts a
    silent correctness failure into a loud startup failure.

    Ownership is host:pid, so re-opening the database in the SAME process (which
    the restart-replay tests do) re-acquires rather than deadlocking, while a
    genuinely separate process is refused.

    Takeover is a compare-and-swap on the heartbeat the holder was last seen at,
    so if two processes both find a stale lock exactly one of them wins.
    """

    STALE_AFTER = 90.0     # missed heartbeats before a holder is presumed dead
    HEARTBEAT_EVERY = 20.0

    def __init__(self, db):
        self.db = db
        self.owner = f"{socket.gethostname()}:{os.getpid()}"
        self.held = False
        db.executescript(
            "CREATE TABLE IF NOT EXISTS writer_lock("
            "  id INTEGER PRIMARY KEY, owner TEXT NOT NULL,"
            "  acquired REAL NOT NULL, heartbeat REAL NOT NULL)")
        db.commit()

    def current(self):
        r = self.db.execute("SELECT * FROM writer_lock WHERE id=1").fetchone()
        return dict(r) if r else None

    def acquire(self) -> None:
        if os.environ.get("OMEM_ALLOW_MULTIPLE_WRITERS"):
            # Deliberately not a silent option: whoever sets this is choosing the
            # divergence described above, and should see it said out loud.
            print("  WARNING: OMEM_ALLOW_MULTIPLE_WRITERS is set. Two processes on "
                  "one database keep two different engines and will disagree.")
            return
        now = _now()
        held = self.current()
        if held is None:
            self.db.execute(
                "INSERT INTO writer_lock(id,owner,acquired,heartbeat) VALUES(1,?,?,?)",
                (self.owner, now, now))
            self.db.commit()
            self.held = True
            return
        if held["owner"] == self.owner:
            self.beat()
            self.held = True
            return
        age = now - held["heartbeat"]
        if age < self.STALE_AFTER:
            raise SystemExit(
                f"OMEM refuses to start: {held['owner']} is already serving this "
                f"database (last seen {age:.0f}s ago).\n"
                "The engine is authoritative in memory, so a second process would "
                "hold a second copy of it and the two would answer differently "
                "without either of them erroring.\n"
                "  Stop the other process first, or point this one at another "
                "OMEM_DB / OMEM_DATABASE_URL.")
        # Stale. Take it, but only if nobody else took it in the meantime.
        self.db.execute(
            "UPDATE writer_lock SET owner=?, acquired=?, heartbeat=? "
            "WHERE id=1 AND owner=? AND heartbeat=?",
            (self.owner, now, now, held["owner"], held["heartbeat"]))
        self.db.commit()
        if (self.current() or {}).get("owner") != self.owner:
            raise SystemExit(
                "OMEM refuses to start: another process claimed this database "
                "while we were taking over a stale lock. Retry.")
        print(f"  writer lock: took over from {held['owner']} "
              f"(stale for {age:.0f}s)")
        self.held = True

    def beat(self) -> None:
        if not self.held and not os.environ.get("OMEM_ALLOW_MULTIPLE_WRITERS"):
            return
        self.db.execute("UPDATE writer_lock SET heartbeat=? WHERE id=1 AND owner=?",
                        (_now(), self.owner))
        self.db.commit()

    def release(self) -> None:
        """Hand the lock back on a clean shutdown so a redeploy does not have to
        wait out STALE_AFTER. A crash skips this, which is what the staleness
        timeout is for."""
        if not self.held:
            return
        self.db.execute("DELETE FROM writer_lock WHERE id=1 AND owner=?", (self.owner,))
        self.db.commit()
        self.held = False


def _id(prefix: str) -> str:
    return f"{prefix}_{secrets.token_hex(6)}"


def hash_key(secret: str) -> str:
    return hashlib.sha256(secret.encode()).hexdigest()


# ── password hashing ────────────────────────────────────────────────────────
# PBKDF2-HMAC-SHA256, stdlib only, because "zero third-party dependencies" is a
# product promise and bcrypt/argon2 would break it.
#
# 210,000 iterations rather than OWASP's 600,000 for SHA-256: this server is a
# single Python process, and a password hash is the one endpoint an unauthenticated
# caller can force it to run. Measured here, 600k costs 857 ms of CPU per attempt -
# a dozen concurrent sign-in attempts would stall every other request in the
# process. 210k costs ~300 ms, which is still a serious brute-force cost when
# combined with the per-IP limiter on the auth routes, and leaves the server
# able to answer anyone else. Raise it if you put OMEM behind more CPU.
PBKDF2_ITERATIONS = 210_000
MIN_PASSWORD_LENGTH = 10


def hash_password(password: str, *, iterations: int = PBKDF2_ITERATIONS) -> str:
    """Returns 'pbkdf2_sha256$<iterations>$<salt_hex>$<hash_hex>'.

    The iteration count travels with the hash so raising it later does not
    invalidate existing passwords: verification uses whatever each row records.
    """
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return f"pbkdf2_sha256${iterations}${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str | None) -> bool:
    """Constant-time check. A missing or malformed hash is False, never True."""
    if not stored or not password:
        return False
    try:
        algo, iters, salt_hex, want_hex = stored.split("$", 3)
        if algo != "pbkdf2_sha256":
            return False
        dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"),
                                 bytes.fromhex(salt_hex), int(iters))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(dk.hex(), want_hex)


class _ThreadSafeSqlite:
    """A single SQLite connection is shared by every request thread and the
    scheduler. Without serialisation two threads interleave statements on the
    same connection, producing errors such as
    'cannot commit - no transaction is active' and, worse, lost writes.

    This wrapper serialises access behind one lock and exposes the same surface
    the codebase already uses (execute / executescript / commit / rowcount /
    lastrowid), matching the Postgres adapter's behaviour."""

    def __init__(self, path):
        self._conn = sqlite3.connect(path, check_same_thread=False, timeout=30)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")   # concurrent readers
        self._conn.execute("PRAGMA busy_timeout=30000")
        self._conn.commit()
        self._lock = threading.RLock()

    def execute(self, sql, params=()):
        with self._lock:
            cur = self._conn.execute(sql, params)
            # materialise rows inside the lock so callers cannot interleave
            # cursor consumption with another thread's statements
            rows = cur.fetchall() if cur.description is not None else []
            return _Result(rows, cur.rowcount, cur.lastrowid)

    def executescript(self, script):
        with self._lock:
            self._conn.executescript(script)

    def commit(self):
        with self._lock:
            try:
                self._conn.commit()
            except sqlite3.OperationalError:
                pass  # another thread already committed this unit of work

    def close(self):
        with self._lock:
            self._conn.close()


class _Result:
    """Cursor-shaped result carrying pre-fetched rows."""
    __slots__ = ("_rows", "rowcount", "lastrowid", "_i")

    def __init__(self, rows, rowcount, lastrowid):
        self._rows = rows
        self.rowcount = rowcount
        self.lastrowid = lastrowid
        self._i = 0

    def fetchone(self):
        if self._i < len(self._rows):
            r = self._rows[self._i]
            self._i += 1
            return r
        return None

    def fetchall(self):
        rows = self._rows[self._i:]
        self._i = len(self._rows)
        return rows

    def __iter__(self):
        while True:
            r = self.fetchone()
            if r is None:
                return
            yield r


class Store:
    def __init__(self, path: str):
        # Pick the backend BEFORE touching the filesystem. Under PostgreSQL
        # `path` is never opened -- PgDB gets the URL from the environment --
        # so creating a directory for it is work done for a file that will not
        # exist, and it was being done unconditionally.
        #
        # That was invisible while every caller passed a real path: makedirs
        # just created the data directory it was going to need anyway. A caller
        # that passes the DATABASE URL as `path`, which is a reasonable thing to
        # write when the path is documented as unused, made it visible:
        #
        #   POSIX  os.path.dirname("postgres://u:p@host:5432/db")
        #            -> "postgres://u:p@host:5432", created SILENTLY as a
        #               directory tree, on every run
        #   Windows the colon is not legal in a path, so the same call is fatal:
        #            OSError [WinError 123]
        #
        # tests_healing_pg.py does exactly that, which is why it had never run
        # on Windows and had been quietly littering the Linux CI runners.
        _pg_url = os.environ.get("OMEM_DATABASE_URL")
        if _pg_url and _pg_url.startswith("postgres"):
            from db_adapter import PgDB
            self.db = PgDB(_pg_url)
        else:
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
            self.db = _ThreadSafeSqlite(path)
        self.db.executescript(SCHEMA)
        # repair pre-existing databases (columns added in later versions)
        self.upgraded_columns = self._add_missing_columns()
        # migrations bookkeeping: schema revisions applied idempotently at boot
        self.db.executescript("CREATE TABLE IF NOT EXISTS schema_migrations("
                              "version TEXT PRIMARY KEY, applied REAL NOT NULL)")
        self.db.execute("SELECT COUNT(*) FROM schema_migrations WHERE version=?", ("v1-baseline",))
        r = self.db.execute("SELECT COUNT(*) c FROM schema_migrations WHERE version=?", ("v1-baseline",)).fetchone()
        if (r["c"] if "c" in r.keys() else r[0]) == 0:
            self.db.execute("INSERT INTO schema_migrations(version, applied) VALUES(?, ?)",
                            ("v1-baseline", __import__("time").time()))
        self.db.commit()
        self._apply_migrations()
        # Constructed, not acquired. Building a Store to read (tests, scripts,
        # restore verification) must not claim the writer lock; only the process
        # that actually serves does, in main().
        self.writer_lock = WriterLock(self.db)

    # Columns added after the original schema. CREATE TABLE IF NOT EXISTS never
    # alters an existing table, so databases created by earlier versions must be
    # upgraded additively. Every entry is (table, column, DDL type + default).
    ADDED_COLUMNS = [
        ("sessions", "expires", "REAL"),
        ("sessions", "revoked", "INTEGER NOT NULL DEFAULT 0"),
        ("keys", "expires", "REAL"),
        ("keys", "agent_id", "TEXT"),
        ("ingest_jobs", "correlation_id", "TEXT"),
        ("ingest_jobs", "next_attempt", "REAL"),
        ("ingest_jobs", "heartbeat", "REAL"),
        ("source_records", "event_id", "TEXT"),
        ("connectors", "cursor", "TEXT"),
        ("connectors", "last_run", "REAL"),
        ("oauth_creds", "status", "TEXT NOT NULL DEFAULT 'connected'"),
        # Password authentication. Nullable on purpose: rows created before
        # passwords existed, and rows created by an invite, have no credential
        # yet. `verify_login` treats NULL as "cannot sign in", never as "any
        # password works" - the difference between the two is the whole point.
        ("users", "pw_hash", "TEXT"),
        # Audit hash chain. Rows written before this existed keep NULL here and
        # are reported as "predates hashing" rather than as a broken chain -
        # claiming to verify what was never hashed would be the same overstatement
        # the chain exists to remove.
        ("audit_events", "seq", "INTEGER"),
        ("audit_events", "prev_hash", "TEXT"),
        ("audit_events", "hash", "TEXT"),
        # Where a repair plan came from: "memory" (a prior repair for this
        # signature that verified) or "llm" (a fresh proposal). Nullable because
        # rows written before this existed cannot be attributed after the fact,
        # and guessing would be exactly the fabrication the audit trail exists to
        # prevent - the dashboard renders NULL as "not recorded", not as "llm".
        ("heal_recoveries", "plan_source", "TEXT"),
        # Who authorised a high-risk repair. `approved_by` gates the only actions
        # OMEM will not run on its own, and it was read from the request, used
        # once, and discarded - so the record of a dangerous repair did not say
        # who permitted it. Note what this is and is not: the caller asserts the
        # approver, so this records a claim, not a verified approval. Making it a
        # verified one needs a second party, which is the approval queue.
        ("heal_recoveries", "approved_by", "TEXT"),
        # The policy verdict, per proposed action, for plans that never ran. A
        # denied plan produces a diagnosis row and no recovery row, so without
        # this the most important thing OMEM does - refusing an action nobody
        # authorised - leaves no readable trace anywhere above the database.
        ("heal_diagnoses", "decisions", "TEXT"),
    ]

    def _existing_columns(self, table):
        """Column names for a table, or None when the table does not exist."""
        if type(self.db).__name__ == "PgDB":
            rows = self.db.execute(
                "SELECT column_name FROM information_schema.columns WHERE table_name=?",
                (table,)).fetchall()
            return {r[0] for r in rows} or None
        try:
            rows = self.db.execute(f"PRAGMA table_info({table})").fetchall()
        except Exception:
            return None
        return {r[1] for r in rows} or None

    def _add_missing_columns(self) -> list[str]:
        """Additive, idempotent upgrade of pre-existing databases. Runs on every
        boot (cheap: reads the catalog), so an old DB is repaired automatically
        instead of failing at query time with 'no such column'."""
        added = []
        for table, column, ddl in self.ADDED_COLUMNS:
            cols = self._existing_columns(table)
            if cols is None or column in cols:
                continue  # table absent (created fresh by SCHEMA) or already current
            try:
                self.db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")
                added.append(f"{table}.{column}")
            except Exception:
                pass  # concurrent boot may have added it
        if added:
            self.db.commit()
        return added

    def apply_hardening(self):
        """Re-attempt hardening migrations after all module schemas exist."""
        self._apply_migrations()

    def _has_migration(self, v):
        r = self.db.execute("SELECT COUNT(*) c FROM schema_migrations WHERE version=?", (v,)).fetchone()
        return (r["c"] if "c" in r.keys() else r[0]) > 0

    def _mark(self, v):
        self.db.execute("INSERT INTO schema_migrations(version, applied) VALUES(?, ?)",
                        (v, __import__("time").time()))
        self.db.commit()

    def _apply_migrations(self):
        """Versioned, idempotent hardening migrations. Never touch engine data."""
        is_pg = type(self.db).__name__ == "PgDB"
        if not self._has_migration("v2-indexes"):
            for ddl in [
                "CREATE INDEX IF NOT EXISTS idx_src_project ON source_records(project_id)",
                "CREATE INDEX IF NOT EXISTS idx_jobs_proj_state ON ingest_jobs(project_id, state)",
                "CREATE INDEX IF NOT EXISTS idx_jobs_claim ON ingest_jobs(state, next_attempt)",
                "CREATE INDEX IF NOT EXISTS idx_ops_project ON ops(project_id)",
                "CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id)",
                "CREATE INDEX IF NOT EXISTS idx_keys_project ON keys(project_id)",
            ]:
                try:
                    self.db.execute(ddl)
                except Exception:
                    pass
            self._mark("v2-indexes")
        if is_pg and not self._has_migration("v3-fks"):
            applied_all = True
            # FKs on PG only (SQLite legacy dev DBs skip; FK enforcement is a
            # production-database property). ON DELETE CASCADE matches the
            # project-deletion semantics already implemented in the API.
            fks = [
                ("keys", "fk_keys_project", "project_id", "projects(id)"),
                ("connectors", "fk_conn_project", "project_id", "projects(id)"),
                ("ingest_jobs", "fk_jobs_connector", "connector_id", "connectors(id)"),
                ("source_records", "fk_src_connector", "connector_id", "connectors(id)"),
            ]
            for table, name, col, ref in fks:
                exists = self.db.execute(
                    "SELECT COUNT(*) c FROM information_schema.table_constraints "
                    "WHERE constraint_name=?", (name,)).fetchone()
                if (exists["c"] if "c" in exists.keys() else exists[0]) == 0:
                    try:
                        self.db.execute(f"ALTER TABLE {table} ADD CONSTRAINT {name} "
                                        f"FOREIGN KEY ({col}) REFERENCES {ref} ON DELETE CASCADE")
                    except Exception:
                        applied_all = False  # table missing at this point in boot, or legacy rows
            if applied_all:
                # only mark complete when every constraint actually exists -
                # partial application must retry on the next boot/apply call
                self._mark("v3-fks")
        # v4: self-healing subsystem tables. Infrastructure metadata (failures,
        # diagnoses, recoveries, health, snapshots) - NOT engine memory, so kept
        # out of the ops log. All rows scoped by org_id+project_id for isolation.
        if not self._has_migration("v4-healing"):
            for ddl in [
                "CREATE TABLE IF NOT EXISTS heal_failures("
                "  id TEXT PRIMARY KEY, org_id TEXT NOT NULL, project_id TEXT NOT NULL,"
                "  fingerprint TEXT NOT NULL, component TEXT NOT NULL, error_type TEXT,"
                "  message TEXT, severity TEXT, context TEXT, occurrences INTEGER NOT NULL DEFAULT 1,"
                "  resolved INTEGER NOT NULL DEFAULT 0, ts REAL NOT NULL)",
                "CREATE INDEX IF NOT EXISTS idx_heal_fail_proj ON heal_failures(org_id, project_id, ts)",
                "CREATE INDEX IF NOT EXISTS idx_heal_fail_fp ON heal_failures(project_id, fingerprint, resolved)",
                "CREATE TABLE IF NOT EXISTS heal_diagnoses("
                "  id TEXT PRIMARY KEY, org_id TEXT NOT NULL, project_id TEXT NOT NULL,"
                "  failure_id TEXT NOT NULL, fingerprint TEXT NOT NULL, diagnosis TEXT,"
                "  confidence REAL, plan TEXT, outcome TEXT, decisions TEXT, ts REAL NOT NULL)",
                "CREATE INDEX IF NOT EXISTS idx_heal_diag_fp ON heal_diagnoses(org_id, project_id, fingerprint, outcome)",
                "CREATE TABLE IF NOT EXISTS heal_recoveries("
                "  id TEXT PRIMARY KEY, org_id TEXT NOT NULL, project_id TEXT NOT NULL,"
                "  failure_id TEXT NOT NULL, component TEXT NOT NULL, fingerprint TEXT NOT NULL,"
                "  state TEXT NOT NULL, owner TEXT, plan TEXT, actions_run TEXT, verification TEXT,"
                "  outcome TEXT, attempts INTEGER NOT NULL DEFAULT 0, plan_source TEXT,"
                "  approved_by TEXT, ts REAL NOT NULL)",
                "CREATE INDEX IF NOT EXISTS idx_heal_rec_comp ON heal_recoveries(org_id, project_id, component, state)",
                "CREATE INDEX IF NOT EXISTS idx_heal_rec_fail ON heal_recoveries(org_id, project_id, failure_id)",
                "CREATE TABLE IF NOT EXISTS heal_health("
                "  id TEXT PRIMARY KEY, org_id TEXT NOT NULL, project_id TEXT NOT NULL,"
                "  component TEXT NOT NULL, status TEXT NOT NULL, reason TEXT, metadata TEXT, ts REAL NOT NULL)",
                "CREATE INDEX IF NOT EXISTS idx_heal_health ON heal_health(org_id, project_id, ts)",
                "CREATE TABLE IF NOT EXISTS heal_snapshots("
                "  id TEXT PRIMARY KEY, org_id TEXT NOT NULL, project_id TEXT NOT NULL,"
                "  label TEXT, kind TEXT, payload TEXT, ts REAL NOT NULL)",
                "CREATE INDEX IF NOT EXISTS idx_heal_snap ON heal_snapshots(org_id, project_id, kind, ts)",
                # single-active-claim slot: the PRIMARY KEY (org,project,component)
                # makes "one active recovery per component" DB-enforced, so two
                # instances racing to claim cannot both win (INSERT ... ON CONFLICT
                # DO NOTHING - only one row can exist). Released when recovery ends.
                "CREATE TABLE IF NOT EXISTS heal_active_claims("
                "  org_id TEXT NOT NULL, project_id TEXT NOT NULL, component TEXT NOT NULL,"
                "  recovery_id TEXT NOT NULL, owner TEXT, ts REAL NOT NULL,"
                "  PRIMARY KEY (org_id, project_id, component))",
            ]:
                try:
                    self.db.execute(ddl)
                except Exception:
                    pass
            self._mark("v4-healing")
        self.db.commit()

    # ── users / sessions ─────────────────────────────────────────────
    def signup(self, email: str, org_name: str) -> dict:
        email = email.strip().lower()
        row = self.db.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
        if row:
            user_id = row["id"]
        else:
            user_id = _id("usr")
            self.db.execute("INSERT INTO users(id,email,created) VALUES(?,?,?)",
                            (user_id, email, _now()))
            self.db.execute("INSERT INTO orgs VALUES(?,?,?,?)",
                            (_id("org"), org_name or email.split("@")[0], user_id, _now()))
        token = "omem_sess_" + secrets.token_hex(24)
        self.db.execute("INSERT INTO sessions(token,user_id,created,expires) VALUES(?,?,?,?)", (token, user_id, _now(), _now() + self.SESSION_TTL))
        self.db.commit()
        return {"user_id": user_id, "email": email, "token": token, "existing": bool(row)}

    SESSION_TTL = 30 * 86400  # 30 days

    # ── password-mode accounts (OMEM_AUTH=password) ─────────────────────────
    # `signup` above is the LOCAL-mode path: it identifies a user by email alone
    # and hands back a session. That is safe only when the server is reachable
    # solely from the machine it runs on, which local mode enforces at bind time.
    # Everything below is the path used when the server is exposed, where a
    # bare email is a username and never a credential.

    def new_session(self, user_id: str) -> str:
        token = "omem_sess_" + secrets.token_hex(24)
        self.db.execute(
            "INSERT INTO sessions(token,user_id,created,expires) VALUES(?,?,?,?)",
            (token, user_id, _now(), _now() + self.SESSION_TTL))
        self.db.commit()
        return token

    def ensure_user(self, email: str) -> dict:
        """Create a credential-less user + org if the email is unknown. Mints NO
        session. That is what separates inviting somebody from becoming them.
        (`signup` returning a token is exactly why an invite could hand out a
        live session for the invitee's account.)"""
        email = email.strip().lower()
        row = self.db.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
        if row:
            return {"user_id": row["id"], "email": email, "existing": True}
        user_id = _id("usr")
        self.db.execute("INSERT INTO users(id,email,created) VALUES(?,?,?)",
                        (user_id, email, _now()))
        self.db.execute("INSERT INTO orgs VALUES(?,?,?,?)",
                        (_id("org"), email.split("@")[0], user_id, _now()))
        self.db.commit()
        return {"user_id": user_id, "email": email, "existing": False}

    def has_password(self, email: str) -> bool:
        r = self.db.execute("SELECT pw_hash FROM users WHERE email=?",
                            (email.strip().lower(),)).fetchone()
        return bool(r and r["pw_hash"])

    def set_password(self, user_id: str, password: str) -> None:
        self.db.execute("UPDATE users SET pw_hash=? WHERE id=?",
                        (hash_password(password), user_id))
        self.db.commit()

    def create_account(self, email: str, password: str, org_name: str = "") -> dict | None:
        """Register an email with a password. None when the address already has
        one. The caller turns that into 409 rather than a session, so signup can
        never be used as a way in to somebody else's account.

        An address that exists WITHOUT a password (invited, or created before
        passwords) is claimed here instead. That grants nothing new: such an
        account was already reachable by anyone who knew the address, and after
        this it is not. Real deployments should still verify the address by
        email before handing it over; OMEM has no mail transport, so this is
        documented as a limitation rather than pretended away."""
        email = email.strip().lower()
        row = self.db.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
        if row and row["pw_hash"]:
            return None
        if row:
            user_id, existing = row["id"], True
        else:
            user_id, existing = _id("usr"), False
            self.db.execute("INSERT INTO users(id,email,created) VALUES(?,?,?)",
                            (user_id, email, _now()))
            self.db.execute("INSERT INTO orgs VALUES(?,?,?,?)",
                            (_id("org"), org_name or email.split("@")[0], user_id, _now()))
        self.db.execute("UPDATE users SET pw_hash=? WHERE id=?",
                        (hash_password(password), user_id))
        self.db.commit()
        return {"user_id": user_id, "email": email, "existing": existing,
                "token": self.new_session(user_id)}

    def verify_login(self, email: str, password: str) -> dict | None:
        """The user row when the password matches, else None. A user with no
        pw_hash always fails: `verify_password` rejects a NULL hash outright."""
        row = self.db.execute("SELECT * FROM users WHERE email=?",
                              (email.strip().lower(),)).fetchone()
        if not row or not verify_password(password, row["pw_hash"]):
            return None
        return dict(row)

    def user_by_email(self, email: str):
        r = self.db.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
        return dict(r) if r else None

    def user_for_session(self, token: str):
        r = self.db.execute(
            "SELECT u.*, s.expires ex, s.revoked rv FROM sessions s "
            "JOIN users u ON u.id=s.user_id WHERE s.token=?",
            (token,)).fetchone()
        if not r:
            return None
        d = dict(r)
        if d.pop("rv", 0):
            return None  # revoked sessions stop working
        ex = d.pop("ex", None)
        if ex is not None and ex < _now():
            return None  # expired sessions stop working
        return d

    def revoke_session(self, token: str) -> bool:
        cur = self.db.execute("UPDATE sessions SET revoked=1 WHERE token=?", (token,))
        self.db.commit()
        return cur.rowcount > 0

    # -- MFA --
    def mfa_state(self, user_id):
        r = self.db.execute("SELECT secret, enabled FROM user_mfa WHERE user_id=?",
                            (user_id,)).fetchone()
        return dict(r) if r else None

    def mfa_enroll(self, user_id, secret):
        self.db.execute("INSERT OR REPLACE INTO user_mfa VALUES(?,?,0,?)",
                        (user_id, secret, _now()))
        self.db.commit()

    def mfa_activate(self, user_id):
        self.db.execute("UPDATE user_mfa SET enabled=1 WHERE user_id=?", (user_id,))
        self.db.commit()

    def org_for_user(self, user_id: str):
        r = self.db.execute("SELECT * FROM orgs WHERE user_id=?", (user_id,)).fetchone()
        return dict(r) if r else None

    # ── projects ─────────────────────────────────────────────────────
    def create_project(self, org_id: str, name: str, env: str = "development",
                       pid: str | None = None, is_demo: bool = False) -> dict:
        pid = pid or _id("proj")
        self.db.execute("INSERT INTO projects VALUES(?,?,?,?,?,?)",
                        (pid, org_id, name, env, 1 if is_demo else 0, _now()))
        self.db.commit()
        return {"id": pid, "org_id": org_id, "name": name, "env": env, "is_demo": is_demo}

    def projects_all(self) -> list[dict]:
        return [dict(r) for r in self.db.execute("SELECT * FROM projects ORDER BY created")]

    def projects_for_user(self, user_id: str) -> list[dict]:
        rows = self.db.execute("""
          SELECT p.* FROM projects p LEFT JOIN orgs o ON o.id=p.org_id
          WHERE p.is_demo=1 OR o.user_id=? ORDER BY p.is_demo, p.created""", (user_id,))
        return [dict(r) for r in rows]

    def project(self, pid: str):
        r = self.db.execute("SELECT * FROM projects WHERE id=?", (pid,)).fetchone()
        return dict(r) if r else None

    def user_can_access(self, user_id: str, pid: str) -> bool:
        p = self.project(pid)
        if not p:
            return False
        if p["is_demo"]:
            return True
        org = self.db.execute("SELECT * FROM orgs WHERE id=? AND user_id=?",
                              (p["org_id"], user_id)).fetchone()
        return org is not None

    # ── ops log (durability = replay through the engine) ─────────────
    # `args` is the memory itself - propositions, subjects, labels, agents - and
    # this log is the source of truth the engine is rebuilt from. It is the row
    # that matters most if someone reads the database file, so it is the row
    # OMEM_ENCRYPT_AT_REST covers first. `kind` and `clock` stay clear: they are
    # structure, they carry no content, and replay needs to order by them.
    def record_op(self, project_id: str, kind: str, args: dict, clock: int):
        self.db.execute("INSERT INTO ops(project_id,kind,args,clock,ts) VALUES(?,?,?,?,?)",
                        (project_id, kind, encrypt_content(json.dumps(args)), clock, _now()))
        self.db.commit()

    def ops_for(self, project_id: str) -> list[dict]:
        rows = self.db.execute(
            "SELECT kind, args, clock FROM ops WHERE project_id=? ORDER BY seq", (project_id,))
        return [{"kind": r["kind"], "args": json.loads(decrypt_content(r["args"])),
                 "clock": r["clock"]} for r in rows]

    # ── api keys ─────────────────────────────────────────────────────
    def create_key(self, project_id: str, name: str, role: str = "developer",
                   ttl_days: int | None = None, agent_id: str | None = None) -> dict:
        secret = "omem_sk_" + secrets.token_hex(20)
        kid = _id("key")
        expires = (_now() + ttl_days * 86400) if ttl_days else None
        self.db.execute("INSERT INTO keys(id,project_id,name,prefix,hash,role,created,expires,agent_id) VALUES(?,?,?,?,?,?,?,?,?)",
                        (kid, project_id, name, secret[:16], hash_key(secret), role, _now(), expires, agent_id))
        self.db.commit()
        return {"id": kid, "name": name, "prefix": secret[:16], "role": role,
                "created": _now(), "expires": expires, "agent_id": agent_id,
                "secret": secret}  # secret returned ONCE

    def keys_for(self, project_id: str) -> list[dict]:
        rows = self.db.execute(
            "SELECT id,name,prefix,role,created,last_used,revoked,expires FROM keys WHERE project_id=? ORDER BY created",
            (project_id,))
        return [dict(r) for r in rows]

    def key_lookup(self, secret: str):
        r = self.db.execute("SELECT * FROM keys WHERE hash=? AND revoked=0",
                            (hash_key(secret),)).fetchone()
        if r and r["expires"] is not None and r["expires"] < _now():
            return None  # expired keys stop working
        if r:
            self.db.execute("UPDATE keys SET last_used=? WHERE id=?", (_now(), r["id"]))
            self.db.commit()
        return dict(r) if r else None

    def revoke_key(self, kid: str, project_id: str) -> bool:
        cur = self.db.execute("UPDATE keys SET revoked=1 WHERE id=? AND project_id=?",
                              (kid, project_id))
        self.db.commit()
        return cur.rowcount > 0
