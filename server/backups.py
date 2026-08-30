"""Automated backups. Real scheduled backups with retention, explicit
success/failure state, and restore verification, not just documentation.

PostgreSQL: pg_dump via subprocess (custom scratch-db restore verification).
SQLite: the online .backup API.

Every run writes a backup_runs row (status running/completed/failed, path,
bytes, error). A failure is NEVER silent: the row says failed, the error is
recorded, and health/observability expose last_backup + failure state.
"""
from __future__ import annotations
import os
import subprocess
import time

BACKUP_SCHEMA = """
CREATE TABLE IF NOT EXISTS backup_runs(
  id INTEGER PRIMARY KEY AUTOINCREMENT, started REAL NOT NULL,
  finished REAL, status TEXT NOT NULL, path TEXT, bytes INTEGER,
  error TEXT, kind TEXT NOT NULL);
"""


def _shred(path: str):
    """Best-effort removal of a plaintext temp artifact: overwrite once, then
    unlink. Not a forensic wipe (that needs OS/FS support), but ensures the
    plaintext file does not linger in the backup directory."""
    try:
        if os.path.exists(path):
            n = os.path.getsize(path)
            with open(path, "r+b") as f:
                f.write(os.urandom(min(n, 1 << 20)))
                f.flush()
                os.fsync(f.fileno())
            os.remove(path)
    except OSError:
        try:
            os.remove(path)
        except OSError:
            pass


class BackupManager:
    def __init__(self, db, backup_dir=None, interval=3600.0, retain=7, secrets=None):
        self.db = db
        self.dir = backup_dir or os.environ.get("OMEM_BACKUP_DIR", "/tmp/omem-backups")
        self.interval = float(os.environ.get("OMEM_BACKUP_INTERVAL", interval))
        self.retain = int(os.environ.get("OMEM_BACKUP_RETAIN", retain))
        # P9.1: optionally encrypt the backup ARTIFACT at rest (a distinct file
        # from the source volume, so volume encryption doesn't automatically
        # cover it). Reuses the existing SecretsProvider - no new key system.
        # Off by default so local dev stays simple; enabled with
        # OMEM_BACKUP_ENCRYPT=1 (requires OMEM_MASTER_KEY or OMEM_KMS_KEY_ID).
        self.encrypt_backups = os.environ.get("OMEM_BACKUP_ENCRYPT", "0") == "1"
        self._secrets = secrets
        # Optional callable(dest_dir) invoked after every successful backup, so
        # derived artifacts (the intelligence-bank export) ride the same
        # retention-protected, offsite-syncable directory as the database.
        self.extra_writer = None
        os.makedirs(self.dir, exist_ok=True)
        try:
            os.chmod(self.dir, 0o700)  # backups are sensitive: owner-only
        except OSError:
            pass
        db.executescript(BACKUP_SCHEMA)
        db.commit()

    @property
    def secrets(self):
        if self._secrets is None:
            from secrets_provider import get_secrets_provider
            self._secrets = get_secrets_provider()
        return self._secrets

    @property
    def is_pg(self):
        return type(self.db).__name__ == "PgDB"

    def due(self) -> bool:
        r = self.db.execute(
            "SELECT MAX(started) m FROM backup_runs WHERE status='completed'").fetchone()
        last = r["m"] if r and r["m"] else 0
        return (time.time() - last) >= self.interval

    def run(self) -> dict:
        """Perform one backup. Returns the run row. Failures are recorded, never
        swallowed into a fake success."""
        started = time.time()
        kind = "pg_dump" if self.is_pg else "sqlite_backup"
        cur = self.db.execute(
            "INSERT INTO backup_runs(started,status,kind) VALUES(?,?,?)",
            (started, "running", kind))
        run_id = cur.lastrowid
        self.db.commit()
        path = os.path.join(self.dir, f"omem-{int(started)}.{'sql' if self.is_pg else 'db'}")
        enc = self.encrypt_backups
        # When encrypting, the DB tool writes a plaintext temp; we then encrypt
        # to the final .enc artifact and shred the temp. The temp lives in the
        # same 0700 backup dir so it never escapes the protected boundary.
        work_path = path + ".tmp" if enc else path
        final_path = path + ".enc" if enc else path
        try:
            if self.is_pg:
                url = os.environ["OMEM_DATABASE_URL"]
                with open(work_path, "w") as f:
                    proc = subprocess.run(["pg_dump", "--no-owner", "--dbname", url],
                                          stdout=f, stderr=subprocess.PIPE, timeout=300)
                if proc.returncode != 0:
                    raise RuntimeError(f"pg_dump rc={proc.returncode}: {proc.stderr.decode()[:300]}")
            else:
                import sqlite3
                src_path = os.environ.get("OMEM_DB", "data/omem.db")
                # Closed in `finally`, not after the copy. These used to be closed
                # only on the success path, so every failed backup leaked two
                # connections - and a backup fails for exactly the reasons that
                # repeat (disk full, a locked database), on a schedule that runs
                # forever. The handle to the LIVE database is the costly half: on
                # Windows it also blocks anything that needs to replace the file.
                src = dest = None
                try:
                    src = sqlite3.connect(src_path)
                    # Ensure all committed WAL pages are folded into the main DB so
                    # the online backup captures the full durable state (DR
                    # correctness: a WAL-resident write must not be lost from the
                    # backup artifact).
                    try:
                        src.execute("PRAGMA wal_checkpoint(FULL)")
                    except sqlite3.OperationalError:
                        pass
                    dest = sqlite3.connect(work_path)
                    src.backup(dest)
                finally:
                    for _conn in (dest, src):
                        if _conn is not None:
                            try:
                                _conn.close()
                            except Exception:
                                pass
            if enc:
                # encrypt the artifact via the existing SecretsProvider, then
                # remove the plaintext temp. Key material is NEVER written here.
                with open(work_path, "rb") as f:
                    blob = self.secrets.encrypt_bytes(f.read())
                with open(final_path, "wb") as f:
                    f.write(blob)
                try:
                    os.chmod(final_path, 0o600)
                except OSError:
                    pass
                _shred(work_path)
            else:
                try:
                    os.chmod(final_path, 0o600)
                except OSError:
                    pass
            size = os.path.getsize(final_path)
            if size < 100:
                raise RuntimeError(f"backup suspiciously small ({size} bytes)")
            self.db.execute(
                "UPDATE backup_runs SET finished=?, status='completed', path=?, bytes=? WHERE id=?",
                (time.time(), final_path, size, run_id))
            self.db.commit()
            self._apply_retention()
            # The intelligence bank rides every backup: whatever offsite
            # strategy protects the database (a synced folder, a mounted
            # drive) also protects the bank, so losing the machine loses
            # neither. Best-effort -- an export failure never fails a backup.
            if self.extra_writer:
                try:
                    self.extra_writer(self.dir)
                except Exception:
                    pass
            return self.status()
        except Exception as e:
            self.db.execute(
                "UPDATE backup_runs SET finished=?, status='failed', error=? WHERE id=?",
                (time.time(), f"{type(e).__name__}: {e}", run_id))
            self.db.commit()
            for _p in (work_path, final_path):
                if os.path.exists(_p):
                    try:
                        os.remove(_p)
                    except OSError:
                        pass
            return self.status()

    def _apply_retention(self):
        rows = self.db.execute(
            "SELECT id, path FROM backup_runs WHERE status='completed' ORDER BY started DESC").fetchall()
        for r in rows[self.retain:]:
            if r["path"] and os.path.exists(r["path"]):
                try:
                    os.remove(r["path"])
                except OSError:
                    pass
            self.db.execute("UPDATE backup_runs SET status='pruned' WHERE id=?", (r["id"],))
        self.db.commit()

    def status(self) -> dict:
        last_ok = self.db.execute(
            "SELECT * FROM backup_runs WHERE status='completed' ORDER BY started DESC LIMIT 1").fetchone()
        last_any = self.db.execute(
            "SELECT * FROM backup_runs ORDER BY started DESC LIMIT 1").fetchone()
        failing = bool(last_any and last_any["status"] == "failed")
        return {
            "last_successful": dict(last_ok) if last_ok else None,
            "last_run": dict(last_any) if last_any else None,
            "failing": failing,  # alertable: latest run failed
            "interval_seconds": self.interval,
            "retain": self.retain,
            "encrypted": self.encrypt_backups,
            "encryption": self.encryption_status(),
            "completed_count": self.db.execute(
                "SELECT COUNT(*) c FROM backup_runs WHERE status='completed'").fetchone()["c"],
        }

    def encryption_status(self) -> dict:
        """Observable, non-secret view of the backup-encryption configuration.
        Never returns key material. Flags an insecure production config where
        encryption is on but the master key is still the built-in dev default."""
        if not self.encrypt_backups:
            return {"enabled": False, "provider": None, "insecure_default_key": False}
        prov = self.secrets
        insecure = (getattr(prov, "master", None) == "dev-master-key-change-me"
                    and os.environ.get("OMEM_ENV") == "production")
        return {"enabled": True, "provider": prov.kind, "insecure_default_key": insecure}

    def restore_to(self, target_path: str, path=None, min_ops: int = 0) -> dict:
        """DR restore for SQLite: decrypt (if needed) + materialize the backup to
        a TEMP file next to target_path, VALIDATE it (readable, ops table, row
        count >= min_ops), then ATOMICALLY promote it over target_path via
        os.replace. An invalid or partial restore is NEVER promoted; the temp is
        shredded and the existing target is left untouched. Returns a report.

        Postgres restore is a managed-DB operation (pg_restore/psql into a fresh
        database), out of scope here and covered by verify_restore's PG path;
        this atomic-promote flow is SQLite-specific by design."""
        import sqlite3
        if self.is_pg:
            return {"promoted": False, "error": "restore_to is SQLite-only; "
                    "use managed-DB restore for Postgres (see verify_restore)"}
        if path is None:
            r = self.db.execute(
                "SELECT path FROM backup_runs WHERE status='completed' "
                "ORDER BY started DESC LIMIT 1").fetchone()
            if not r:
                return {"promoted": False, "error": "no completed backup"}
            path = r["path"]
        tmp = target_path + ".restore.tmp"
        try:
            # 1. materialize (decrypt if the artifact is encrypted)
            if path.endswith(".enc"):
                with open(path, "rb") as f:
                    plain = self.secrets.decrypt_bytes(f.read())
                with open(tmp, "wb") as f:
                    f.write(plain)
            else:
                import shutil
                shutil.copyfile(path, tmp)
            try:
                os.chmod(tmp, 0o600)
            except OSError:
                pass
            # 2. VALIDATE the temp before promoting
            c = sqlite3.connect(tmp)
            try:
                integrity = c.execute("PRAGMA integrity_check").fetchone()[0]
                if integrity != "ok":
                    raise RuntimeError(f"integrity_check failed: {integrity}")
                restored_ops = c.execute("SELECT COUNT(*) FROM ops").fetchone()[0]
            finally:
                c.close()
            if restored_ops < min_ops:
                raise RuntimeError(
                    f"restored ops {restored_ops} < required minimum {min_ops}")
            # 3. ATOMIC promote (same-filesystem os.replace)
            os.replace(tmp, target_path)
            try:
                os.chmod(target_path, 0o600)
            except OSError:
                pass
            return {"promoted": True, "restored_ops": restored_ops,
                    "target": target_path, "source": path,
                    "encrypted": path.endswith(".enc")}
        except Exception as e:
            _shred(tmp)  # never leave a partial/invalid DB behind
            return {"promoted": False, "error": f"{type(e).__name__}: {e}",
                    "source": path, "target": target_path}

    def verify_restore(self, path=None) -> dict:
        """Restore the latest (or given) backup into a scratch target and verify
        the ops log row count matches the live database. Real verification, not
        an existence check."""
        if path is None:
            r = self.db.execute(
                "SELECT path FROM backup_runs WHERE status='completed' ORDER BY started DESC LIMIT 1").fetchone()
            if not r:
                return {"verified": False, "error": "no completed backup"}
            path = r["path"]
        live_ops = self.db.execute("SELECT COUNT(*) c FROM ops").fetchone()["c"]
        _tmp_dec = None
        try:
            # P9.1: transparently decrypt an encrypted artifact into a temp file
            # inside the protected backup dir, verify from it, then shred it.
            if path.endswith(".enc"):
                with open(path, "rb") as f:
                    plain = self.secrets.decrypt_bytes(f.read())
                _tmp_dec = path + ".verify.tmp"
                with open(_tmp_dec, "wb") as f:
                    f.write(plain)
                try:
                    os.chmod(_tmp_dec, 0o600)
                except OSError:
                    pass
                scan_path = _tmp_dec
            else:
                scan_path = path
            if self.is_pg:
                url = os.environ["OMEM_DATABASE_URL"]
                scratch_url = url.rsplit("/", 1)[0] + "/omem_verify"
                subprocess.run(["psql", "--dbname", url.rsplit("/", 1)[0] + "/postgres", "-q", "-c",
                                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='omem_verify'"],
                               capture_output=True, timeout=60)
                subprocess.run(["psql", "--dbname", url.rsplit("/", 1)[0] + "/postgres",
                                "-q", "-c", "DROP DATABASE IF EXISTS omem_verify"],
                               capture_output=True, timeout=60)
                subprocess.run(["psql", "--dbname", url.rsplit("/", 1)[0] + "/postgres",
                                "-q", "-c", "CREATE DATABASE omem_verify"],
                               capture_output=True, timeout=60, check=True)
                proc = subprocess.run(["psql", "-q", "--dbname", scratch_url, "-f", scan_path],
                                      capture_output=True, timeout=300)
                if proc.returncode != 0:
                    raise RuntimeError(proc.stderr.decode()[:300])
                import psycopg2
                c = psycopg2.connect(scratch_url)
                cur = c.cursor()
                cur.execute("SELECT COUNT(*) FROM ops")
                restored_ops = cur.fetchone()[0]
                c.close()
            else:
                import sqlite3
                c = sqlite3.connect(scan_path)
                restored_ops = c.execute("SELECT COUNT(*) FROM ops").fetchone()[0]
                c.close()
            ok = restored_ops == live_ops
            return {"verified": ok, "live_ops": live_ops, "restored_ops": restored_ops,
                    "path": path, "encrypted": path.endswith(".enc")}
        except Exception as e:
            return {"verified": False, "error": f"{type(e).__name__}: {e}", "path": path}
        finally:
            if _tmp_dec:
                _shred(_tmp_dec)
