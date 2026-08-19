"""Connector cleanup, straight against the database. Use when the dashboard
cannot do it for you.

    python3 cleanup.py --list
    python3 cleanup.py --delete-kind gmail
    python3 cleanup.py --delete-inactive
    python3 cleanup.py --delete conn_abc123

Only source material (connectors, their jobs, stored messages, filter log) is
removed. Memories already recorded stay: they are immutable engine history.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from env_loader import load_env  # noqa: E402
load_env()
from store import Store  # noqa: E402
from ingest import Ingestor  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description="Remove OMEM connectors")
    ap.add_argument("--list", action="store_true", help="show all connectors")
    ap.add_argument("--delete", metavar="ID", help="delete one connector by id")
    ap.add_argument("--delete-kind", metavar="KIND", help="delete every connector of a kind, e.g. gmail")
    ap.add_argument("--delete-inactive", action="store_true", help="delete every non-active connector")
    ap.add_argument("--project", help="limit to one project id")
    args = ap.parse_args()

    store = Store(os.environ.get("OMEM_DB", os.path.join(os.path.dirname(__file__), "data", "omem.db")))
    ing = Ingestor(store, lambda *a, **k: None, lambda p: p, lambda pid: None)
    rows = store.db.execute(
        "SELECT id, project_id, kind, name, status FROM connectors ORDER BY project_id, kind").fetchall()

    if args.list or not (args.delete or args.delete_kind or args.delete_inactive):
        if not rows:
            print("No connectors.")
            return
        print(f"{'ID':<20} {'PROJECT':<22} {'KIND':<10} {'STATUS':<14} NAME")
        for r in rows:
            print(f"{r['id']:<20} {r['project_id']:<22} {r['kind']:<10} {r['status']:<14} {r['name']}")
        print(f"\n{len(rows)} connector(s).")
        return

    targets = []
    for r in rows:
        if args.project and r["project_id"] != args.project:
            continue
        if args.delete and r["id"] == args.delete:
            targets.append(r)
        elif args.delete_kind and r["kind"] == args.delete_kind:
            targets.append(r)
        elif args.delete_inactive and r["status"] != "active":
            targets.append(r)

    if not targets:
        print("Nothing matched.")
        return
    print("About to remove:")
    for r in targets:
        print(f"  {r['id']}  {r['kind']:<8} {r['status']:<14} {r['name']}")
    if input(f"\nRemove {len(targets)} connector(s)? [y/N] ").strip().lower() != "y":
        print("Cancelled.")
        return
    total = {}
    for r in targets:
        counts = ing.delete_connector(r["id"], r["project_id"])
        for k, v in counts.items():
            total[k] = total.get(k, 0) + v
    print(f"\nRemoved: {total}")
    print("Memories already recorded were NOT deleted (immutable engine history).")


if __name__ == "__main__":
    main()
