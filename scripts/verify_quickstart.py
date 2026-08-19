#!/usr/bin/env python3
"""Run QUICKSTART.md against a live server and fail if any of it is untrue.

The quickstart is the first five minutes of the product, and it is the easiest
documentation to break without noticing: it exercises the SDK, the HTTP API and
the engine together, and none of the unit suites check that the specific code
printed in a markdown file still runs.

Two things it has caught, both of which made OMEM look broken to a new user
while every test passed:
  - `omem-server` started an API and printed nothing usable, so getting to a
    first memory meant hand-writing a signup request.
  - the dashboard defaulted to a project named "demo" that does not exist
    unless OMEM_SEED_DEMO=1, so memories written here were invisible there.

Usage:
    python3 scripts/verify_quickstart.py                  # boots its own server
    python3 scripts/verify_quickstart.py --url ... --key ... --project ...
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request

_failed = 0


def check(name, cond, detail=""):
    global _failed
    if cond:
        print(f"  ok  {name}")
    else:
        _failed += 1
        print(f"  FAIL {name} {detail}")


def wait_for_key(logfile: str, timeout=60):
    """The first-run banner is the product's onboarding. If it stops printing a
    key, a new user has nothing to paste, so this is a hard failure."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if os.path.exists(logfile):
            text = open(logfile, encoding="utf-8", errors="replace").read()
            k = re.search(r"omem_sk_[a-f0-9]+", text)
            p = re.search(r"proj_[a-f0-9]+", text)
            if k and p:
                return k.group(0), p.group(0), text
        time.sleep(1)
    raise SystemExit(
        "omem-server printed no API key within "
        f"{timeout}s — the first-run quickstart is broken.\n"
        + (open(logfile, encoding="utf-8", errors="replace").read()
           if os.path.exists(logfile) else "(no output)"))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url")
    ap.add_argument("--key")
    ap.add_argument("--project")
    ap.add_argument("--port", type=int, default=8787)
    args = ap.parse_args()

    proc = None
    if args.url:
        url, key, project = args.url, args.key, args.project
    else:
        log = "omem-quickstart-boot.log"
        with open(log, "w") as fh:
            proc = subprocess.Popen(["omem-server", str(args.port)],
                                    stdout=fh, stderr=subprocess.STDOUT)
        key, project, banner = wait_for_key(log)
        url = f"http://127.0.0.1:{args.port}"
        print(banner.strip()[-400:])
        print()
        check("first run prints an API key", bool(key))
        check("first run prints a project id", bool(project))

    try:
        from omem import Memory
    except ImportError:
        raise SystemExit("the omem package is not importable — install the wheel first")

    mem = Memory(api_key=key, base_url=url, project=project)

    print("== QUICKSTART.md ==")
    mem.remember(agent="support-bot", about="customer:alice",
                 claim="prefers_annual_billing")
    check("remember + believes",
          mem.believes(about="customer:alice", claim="prefers_annual_billing")
          == "BELIEVED_TRUE")

    r = mem.recall(about="customer:alice")
    check("an agent can recall what it stored",
          r.get("count") == 1 and
          r["memories"][0]["proposition"] == "prefers_annual_billing", str(r)[:160])

    # Spelling is normalised at the boundary, so these are one claim. This is
    # the behaviour the quickstart promises and the reason 0.2.0 renormalises
    # stored propositions on upgrade.
    check("spelling does not create a second fact",
          mem.believes(about="customer:alice", claim="Prefers Annual Billing")
          == "BELIEVED_TRUE")

    # The part a vector store cannot do.
    mem.contradict("prefers_annual_billing", "prefers_monthly_billing")
    mem.remember(agent="sales", about="customer:alice",
                 claim="prefers_monthly_billing")
    check("a contradiction is surfaced, not overwritten",
          mem.believes(about="customer:alice", claim="prefers_annual_billing")
          == "CONTRADICTED")

    beliefs = mem.about("customer:alice")
    check("both claims are still on record", len(beliefs) >= 2, str(len(beliefs)))
    why = mem.why(beliefs[0]["id"])
    check("why returns a provenance chain",
          "provenance" in why and "state" in why, str(list(why))[:120])

    # What the dashboard does on load: pick a project that actually exists.
    req = urllib.request.Request(f"{url}/v1/projects",
                                 headers={"Authorization": f"Bearer {key}"})
    try:
        projects = json.loads(urllib.request.urlopen(req, timeout=10).read())["data"]
    except urllib.error.HTTPError as e:
        projects = []
        print(f"  (could not list projects: {e})")
    check("the workspace is visible to the dashboard's project list",
          any(p["id"] == project for p in projects),
          f"{[p['id'] for p in projects]} lacks {project}")
    mine = next((p for p in projects if p["id"] == project), None)
    check("and it reports the memories that were written",
          bool(mine) and mine.get("assertions", 0) >= 2,
          str(mine)[:160])

    if proc:
        proc.terminate()
    print(f"\n{'FAILED' if _failed else 'quickstart verified'}"
          f" ({_failed} failed)")
    return 1 if _failed else 0


if __name__ == "__main__":
    sys.exit(main())
