#!/usr/bin/env python3
"""Score OMEM's calibration against its own record.

    python3 run.py                      the default database
    python3 run.py --db path/to.db      a specific one
    python3 run.py --project proj_x     one project, not all
    python3 run.py --json               machine readable

Reads resolved hypotheses -- the ones reality has already labelled -- and
scores the strength each was born with against what happened. Nothing is
written and no network call is made.

This is the baseline the commons has to beat. Run it before the pooled bank
reaches inference and after, and the difference is the whole argument for
contributing: either an install that shares gets better at reading people, or
the commons is a donation and should be described as one.
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import score  # noqa: E402


def pairs_from(db, project: str | None):
    """(birth strength, outcome) for every hypothesis reality has decided.

    `strength` is the birth value in the schema and is not rewritten on
    resolution, which is what makes this a forecast score rather than a
    hindsight one."""
    sql = ("SELECT strength, status FROM hypotheses "
           "WHERE status IN ('supported','refuted')")
    args: tuple = ()
    if project:
        sql += " AND project_id=?"
        args = (project,)
    return [(r["strength"], r["status"] == "supported")
            for r in db.execute(sql, args)]


def default_db() -> str:
    return (os.environ.get("OMEM_DB")
            or os.path.join(os.path.expanduser("~"), ".omem", "omem.db"))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=None)
    ap.add_argument("--project", default=None)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    path = args.db or default_db()
    if not os.path.exists(path):
        print("no database at %s\n"
              "Point --db at an OMEM database, or set OMEM_DB." % path)
        return 1

    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    try:
        rows = pairs_from(con, args.project)
    except sqlite3.OperationalError as e:
        print("this database has no hypotheses table (%s)" % e)
        return 1

    rep = score.report(rows)
    rep["database"] = os.path.basename(path)
    if args.project:
        rep["project"] = args.project
    print(json.dumps(rep, indent=1) if args.json else score.render(rep))
    return 0


if __name__ == "__main__":
    sys.exit(main())
