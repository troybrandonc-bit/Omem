"""Durable job worker. Runs as its own process (python3 worker.py), separate
from the API, claiming jobs from the ingest_jobs table.

On PostgreSQL, claiming uses FOR UPDATE SKIP LOCKED, the standard production
DB-queue pattern, so any number of worker processes can run concurrently
without double-claiming. On SQLite (dev), the single-writer model already
serializes claims. The pipeline itself (extraction -> primitives -> frozen
engine) is untouched: workers just drive Ingestor.process_pending safely.

States, retries/backoff, heartbeats, stale recovery, cancellation, and
dead-lettering all come from the existing job machine in ingest.py.
"""
from __future__ import annotations
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def claim_batch(db, limit=5, per_project_cap=3):
    """Atomically claim pending/retrying jobs. PG: SKIP LOCKED across workers.
    per_project_cap bounds concurrent running jobs per tenant (fairness)."""
    is_pg = type(db).__name__ == "PgDB"
    now = time.time()
    if is_pg:
        rows = db.execute(
            "UPDATE ingest_jobs SET state='running', heartbeat=?, updated=? "
            "WHERE id IN (SELECT j.id FROM ingest_jobs j "
            "WHERE j.state IN ('pending','retrying') "
            "AND (j.next_attempt IS NULL OR j.next_attempt<=?) "
            "AND (SELECT COUNT(*) FROM ingest_jobs r WHERE r.project_id=j.project_id AND r.state='running')<? "
            "ORDER BY j.id LIMIT ? FOR UPDATE SKIP LOCKED) RETURNING id, project_id",
            (now, now, now, per_project_cap, limit)).fetchall()
        return [(r["id"], r["project_id"]) for r in rows]
    rows = db.execute(
        "SELECT id, project_id FROM ingest_jobs WHERE state IN ('pending','retrying') "
        "AND (next_attempt IS NULL OR next_attempt<=?) ORDER BY id LIMIT ?",
        (now, limit)).fetchall()
    out = []
    for r in rows:
        cur = db.execute(
            "UPDATE ingest_jobs SET state='running', heartbeat=?, updated=? "
            "WHERE id=? AND state IN ('pending','retrying')", (now, now, r["id"]))
        if cur.rowcount:
            out.append((r["id"], r["project_id"]))
    db.commit()
    return out


def run_worker(worker_id="w1", interval=1.0, once=False):
    import api  # boots store + engine replay + ingestor
    db = api.STORE.db
    processed = 0
    while True:
        api.INGEST.recover_stale()
        claims = claim_batch(db)
        for jid, pid in claims:
            job = db.execute("SELECT * FROM ingest_jobs WHERE id=?", (jid,)).fetchone()
            # process_pending path expects pending; we hold the claim, so drive
            # the single-job processor directly (same code the API uses).
            res = api.INGEST._process_one(job)
            processed += 1
            print(f"[{worker_id}] job {jid} project {pid} -> {'ok' if res['ok'] else 'retry/dead'}")
        if once and not claims:
            return processed
        if not claims:
            time.sleep(interval)


if __name__ == "__main__":
    run_worker(worker_id=os.environ.get("WORKER_ID", "w1"),
               once=os.environ.get("WORKER_ONCE") == "1")
