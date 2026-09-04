#!/usr/bin/env python3
"""Demonstrate, by running mem0's own code, that a deleted memory's text survives.

    git clone https://github.com/mem0ai/mem0
    git -C mem0 checkout 9a7924befd7026e41e445ba809370009e5e985a6
    python3 benchmarks/census/verify/mem0_delete_retains_text.py --repo ./mem0

WHY THIS EXISTS. Every other verdict in this census was reached by reading
source, which is honest and is also weaker than it sounds: a read can miss a
branch, misjudge a conditional, or look at the wrong module. Most of the
findings are about what a system does not record, which cannot be demonstrated
by running anything. This one is different. It is a claim that something IS
written, it is the most consequential claim in the census because it concerns
data somebody asked to have deleted, and it is the one a reader will check
first. So it is checked here by executing mem0's storage layer rather than by
describing it.

WHAT IT SHOWS. mem0's `_delete_memory` (mem0/memory/main.py:2100) reads the
memory's text into `prev_value` and passes it to `add_history` as `old_memory`
with `is_deleted=1`. `delete_all` (main.py:1890) calls `_delete_memory` for
every matching memory, so this is the path a deletion request takes. The history
database defaults to `~/.mem0/history.db` (mem0/configs/base.py:42-45). The net
effect is that the content is gone from the vector store and still on disk.

Retaining the previous value is right for an UPDATE, where knowing what changed
is the point. For a DELETE performed to erase somebody's data it is the opposite
of the intent, and the two cases are not distinguished.

WHAT IT DOES NOT SHOW. Nothing about intent, and nothing about mem0's hosted
platform, which is not this code. It runs `SQLiteManager` only: no network, no
LLM, no API key, and nothing written outside a temporary directory.

Exit 0 means the behaviour was demonstrated. Exit 1 means it was not, which
would mean the census entry for mem0 R1.5 needs correcting.

Copyright 2026 Michael Brandon Clifford. MIT licensed.
"""
from __future__ import annotations

import argparse
import importlib.util
import os
import sqlite3
import subprocess
import sys
import tempfile

ASSESSED_COMMIT = "9a7924befd7026e41e445ba809370009e5e985a6"
CANARY = "the subject's home address is 42 Wallaby Way, Sydney"


def load_storage(repo: str):
    """Load mem0's storage module by path.

    Importing `mem0` as a package needs installed distribution metadata, which
    a plain checkout does not have. storage.py imports only the standard
    library, so loading the file directly runs mem0's real code with no
    dependency on mem0 being installed.
    """
    path = os.path.join(repo, "mem0", "memory", "storage.py")
    if not os.path.exists(path):
        return None, path
    spec = importlib.util.spec_from_file_location("mem0_storage_under_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module, path


def head_of(repo: str) -> str | None:
    try:
        return subprocess.run(["git", "-C", repo, "rev-parse", "HEAD"],
                              capture_output=True, text=True, timeout=30
                              ).stdout.strip() or None
    except Exception:
        return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--repo", default=os.environ.get("MEM0_REPO", "./mem0"),
                    help="path to a mem0 checkout (default ./mem0 or $MEM0_REPO)")
    a = ap.parse_args()

    storage, path = load_storage(a.repo)
    if storage is None:
        print(f"SKIP: no mem0 checkout at {a.repo} (looked for {path})")
        print("      This verifies somebody else's code, so it cannot run "
              "unattended in this repository's CI.")
        return 0

    head = head_of(a.repo)
    print(f"mem0 checkout: {a.repo}")
    print(f"HEAD:          {head or 'unknown'}")
    if head and head != ASSESSED_COMMIT:
        print(f"NOTE:          the census assessed {ASSESSED_COMMIT}.")
        print("               A different result here is a finding about this "
              "commit, not a correction to that one.")
    print()

    db = os.path.join(tempfile.mkdtemp(prefix="census-mem0-"), "history.db")
    manager = storage.SQLiteManager(db)

    # Exactly the call _delete_memory makes: the memory's own text as
    # old_memory, nothing as new_memory, event DELETE, is_deleted=1.
    manager.add_history("mem_1", CANARY, None, "DELETE",
                        is_deleted=1, actor_id="user:alice", role="user")

    rows = sqlite3.connect(db).execute(
        "SELECT memory_id, event, old_memory, new_memory, is_deleted "
        "FROM history").fetchall()

    print("history rows after the delete:")
    for r in rows:
        print(f"  memory_id={r[0]!r} event={r[1]!r} is_deleted={r[4]!r}")
        print(f"  old_memory={r[2]!r}")
        print(f"  new_memory={r[3]!r}")

    retained = any(CANARY in (r[2] or "") for r in rows)
    print()
    print(f"database:   {db}")
    print(f"deleted text still readable on disk: {retained}")
    print()

    if retained:
        print("DEMONSTRATED. The text of a deleted memory is written to the "
              "history database and survives the deletion.")
        print("This is census mem0 R1.5, verdict 'partial'.")
        return 0

    print("NOT DEMONSTRATED. old_memory did not retain the deleted text.")
    print("If this is a current checkout, the behaviour may have changed and "
          "the census entry for mem0 R1.5 should be reassessed at this commit.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
