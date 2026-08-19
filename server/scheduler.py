"""Background sync scheduler. A daemon thread that periodically polls active
connectors and drains their jobs, so the product works without 'Run now'.

Per-project rate limiting (a minimum interval between runs) provides backpressure.
Idempotency comes for free from the pipeline's source-level dedup: re-polling a
connector never re-ingests an already-seen external id. Observable: every run
updates connectors.last_run and the ingest_jobs table the dashboard reads.
"""
from __future__ import annotations
import threading
import time
import time as _time


class Scheduler:
    def __init__(self, ingestor, interval=15.0, min_project_gap=5.0):
        self.ingestor = ingestor
        self.interval = interval          # seconds between scheduler ticks
        self.min_gap = min_project_gap    # min seconds between runs of one project
        self._last_run: dict[str, float] = {}
        self.backup_manager = None  # set by app
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self.runs = 0

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()

    def _loop(self):
        while not self._stop.wait(self.interval):
            try:
                self.tick()
            except Exception:
                pass  # a bad connector must never kill the scheduler

    def tick(self) -> dict:
        try:
            self.ingestor.recover_stale()
        except Exception:
            pass
        # P3 background consolidation ("sleep"): patterns form off the agent's
        # hot path. Throttled; a failure never harms the scheduler or agents.
        if getattr(self, "consolidator", None) is not None:
            now = _time.time()
            if now - getattr(self, "_last_consolidation", 0) >=                     getattr(self, "consolidation_interval", 300):
                self._last_consolidation = now
                try:
                    self.consolidator()
                except Exception:
                    pass
        if self.backup_manager is not None:
            try:
                if self.backup_manager.due():
                    self.backup_manager.run()
            except Exception:
                pass
        """One scheduling pass. Rate-limited per project. Returns what it did."""
        now = time.time()
        acted = {}
        conns = self.ingestor.db.execute(
            "SELECT id, project_id FROM connectors WHERE status='active'").fetchall()
        by_project: dict[str, list[str]] = {}
        for c in conns:
            by_project.setdefault(c["project_id"], []).append(c["id"])
        for pid, cids in by_project.items():
            if now - self._last_run.get(pid, 0) < self.min_gap:
                continue  # backpressure: skip projects run too recently
            queued = 0
            for cid in cids:
                try:
                    queued += self.ingestor.poll_connector(cid)
                except Exception:
                    pass
            res = self.ingestor.process_pending(pid)
            self._last_run[pid] = now
            acted[pid] = {"queued": queued, **res}
        self.runs += 1
        return acted
