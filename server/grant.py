"""Grant organisation roles directly, for when you need to fix your own access.

    python3 grant.py --list
    python3 grant.py --email you@company.com --role owner
    python3 grant.py --email teammate@company.com --role developer

Roles (most to least powerful): owner, admin, developer, viewer.
  owner      everything, including project deletion and billing
  admin      members, retention, audit log; not deletion or billing
  developer  memories, keys, connectors
  viewer     read-only
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from env_loader import load_env  # noqa: E402
load_env()
from store import Store  # noqa: E402
from enterprise import Enterprise, ROLES, PERMISSIONS, role_allows  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description="Manage OMEM organisation roles")
    ap.add_argument("--list", action="store_true", help="show users and their roles")
    ap.add_argument("--email", help="user to change")
    ap.add_argument("--role", choices=ROLES, help="role to grant")
    ap.add_argument("--org", help="organisation id (defaults to the user's own)")
    ap.add_argument("--permissions", action="store_true", help="print the permission matrix")
    args = ap.parse_args()

    store = Store(os.environ.get("OMEM_DB", os.path.join(os.path.dirname(__file__), "data", "omem.db")))
    ent = Enterprise(store.db)

    if args.permissions:
        width = max(len(p) for p in PERMISSIONS)
        print(f"{'permission':<{width}}  " + "  ".join(f"{r:<9}" for r in ROLES))
        for perm in PERMISSIONS:
            marks = "  ".join(f"{('yes' if role_allows(r, perm) else '-'):<9}" for r in ROLES)
            print(f"{perm:<{width}}  {marks}")
        return

    if args.list or not (args.email and args.role):
        rows = store.db.execute(
            "SELECT u.id, u.email, m.org_id, m.role FROM users u "
            "LEFT JOIN memberships m ON m.user_id = u.id ORDER BY u.created").fetchall()
        if not rows:
            print("No users yet. Sign up in the dashboard first.")
            return
        print(f"{'EMAIL':<34} {'ROLE':<11} ORG")
        for r in rows:
            print(f"{r['email']:<34} {(r['role'] or 'none'):<11} {r['org_id'] or '-'}")
        if not (args.email and args.role):
            print("\nGrant a role:  python3 grant.py --email you@company.com --role owner")
        return

    user = store.user_by_email(args.email)
    if not user:
        print(f"No user with email {args.email}. Sign up in the dashboard first.")
        sys.exit(1)
    org = args.org
    if not org:
        o = store.org_for_user(user["id"])
        if not o:
            row = store.db.execute("SELECT id FROM orgs ORDER BY created LIMIT 1").fetchone()
            if not row:
                print("No organisation exists yet.")
                sys.exit(1)
            org = row["id"]
        else:
            org = o["id"]
    before = ent.role_of(org, user["id"]) or "none"
    ent.set_role(org, user["id"], args.role)
    ent.audit("member.role_changed", actor="cli", org_id=org, resource=args.email,
              metadata={"role": args.role, "via": "grant.py"})
    print(f"{args.email}: {before} -> {args.role}  (org {org})")
    print("Sign out and back in if the dashboard still shows the old role.")


if __name__ == "__main__":
    main()
