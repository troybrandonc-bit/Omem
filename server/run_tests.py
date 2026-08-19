#!/usr/bin/env python3
"""Run every suite in server/ and report what actually ran.

WHY THIS EXISTS. Each suite is its own script, so "run the tests" meant a shell
loop, and a shell loop counts exit codes. The PostgreSQL suites exit 0 when no
database is configured — they print SKIP and stop — so a run with no database
was indistinguishable from a run that verified PostgreSQL. Three suites and
several hundred checks could quietly verify nothing while the summary said
everything passed, which is how DEPLOYMENT.md came to describe PostgreSQL as
"verified" on the strength of runs that never touched a database.

So: SKIPPED is its own outcome here, printed separately and never folded into
the pass count. `--strict` turns any skip into a failure, which is what CI uses
in the job that supplies a real Postgres.

    python3 run_tests.py                 # everything, honest summary
    python3 run_tests.py --strict        # a skip is a failure
    python3 run_tests.py -k postgres     # only suites matching a substring
"""
from __future__ import annotations

import argparse
import glob
import os
import re
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
# Per-suite ceiling. The slowest legitimate suite is well under this; anything
# that hits it is hung, and a hung suite must fail rather than stall the run.
TIMEOUT = 300

COUNTS = re.compile(r"(\d+)\s+passed,\s+(\d+)\s+failed")
SKIPPED = re.compile(r"^\s*(SKIP|NOT VERIFIED)", re.M | re.I)


def suites(pattern: str | None) -> list[str]:
    found = sorted(os.path.basename(p) for p in glob.glob(os.path.join(HERE, "tests_*.py")))
    if os.path.exists(os.path.join(HERE, "tests.py")):
        found.insert(0, "tests.py")
    return [f for f in found if not pattern or pattern in f]


def run(name: str) -> dict:
    started = time.perf_counter()
    env = dict(os.environ)
    # Windows consoles default to a codepage that cannot encode the characters
    # some suites print, which fails the suite for reasons unrelated to OMEM.
    env.setdefault("PYTHONIOENCODING", "utf-8")
    try:
        p = subprocess.run([sys.executable, name], cwd=HERE, env=env,
                           capture_output=True, text=True, timeout=TIMEOUT,
                           encoding="utf-8", errors="replace")
        out = (p.stdout or "") + (p.stderr or "")
        code = p.returncode
    except subprocess.TimeoutExpired:
        return {"name": name, "state": "TIMEOUT", "checks": 0, "failed": 0,
                "secs": TIMEOUT, "tail": f"exceeded {TIMEOUT}s"}

    m = COUNTS.search(out)
    checks, failed = (int(m.group(1)), int(m.group(2))) if m else (0, 0)
    # Three outcomes, not two, because "skipped" is not one thing:
    #   SKIPPED  ran nothing at all — the suite verified precisely zero.
    #   PARTIAL  ran real checks, then skipped an optional section. tests_github
    #            passes 41 offline checks and skips only the live api.github.com
    #            calls; filing that next to a suite that did nothing is the same
    #            conflation this runner exists to stop.
    if code != 0:
        state = "FAILED"
    elif SKIPPED.search(out):
        state = "PARTIAL" if checks > 0 else "SKIPPED"
    else:
        state = "PASSED"
    tail = " ".join(out.strip().splitlines()[-3:])[:200]
    return {"name": name, "state": state, "checks": checks, "failed": failed,
            "secs": time.perf_counter() - started, "tail": tail}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--strict", action="store_true",
                    help="treat a skipped suite as a failure")
    ap.add_argument("-k", dest="pattern", default=None,
                    help="only suites whose filename contains this")
    args = ap.parse_args()

    names = suites(args.pattern)
    if not names:
        print("no suites matched")
        return 1

    print(f"running {len(names)} suites\n")
    results = []
    for n in names:
        r = run(n)
        results.append(r)
        mark = {"PASSED": "ok  ", "PARTIAL": "part", "SKIPPED": "SKIP",
                "FAILED": "FAIL", "TIMEOUT": "HUNG"}[r["state"]]
        detail = f'{r["checks"]} checks' if r["checks"] else ""
        print(f'  {mark}  {r["name"]:<38} {detail:>12}  {r["secs"]:5.1f}s')
        if r["state"] in ("FAILED", "TIMEOUT"):
            print(f'        {r["tail"]}')

    passed = [r for r in results if r["state"] == "PASSED"]
    partial = [r for r in results if r["state"] == "PARTIAL"]
    skipped = [r for r in results if r["state"] == "SKIPPED"]
    bad = [r for r in results if r["state"] in ("FAILED", "TIMEOUT")]
    checks = sum(r["checks"] for r in results)

    print(f'\n{len(passed)} passed · {len(partial)} partial · '
          f'{len(skipped)} skipped · {len(bad)} failed   ({checks} checks)')

    if skipped:
        print("\nSKIPPED — these verified NOTHING in this run:")
        for r in skipped:
            print(f'  {r["name"]}')
        if not os.environ.get("OMEM_DATABASE_URL"):
            print("  Set OMEM_DATABASE_URL to a live PostgreSQL to run the PG suites.")
    if partial:
        print("\nPARTIAL — ran, but skipped an optional section:")
        for r in partial:
            print(f'  {r["name"]} ({r["checks"]} checks ran)')

    if bad:
        print("\nFAILED:")
        for r in bad:
            print(f'  {r["name"]}: {r["tail"]}')
        return 1
    if skipped and args.strict:
        print("\n--strict: a suite that verified nothing is a failure here.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
