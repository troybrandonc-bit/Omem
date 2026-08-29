"""The claims ledger cannot rot. Run: python3 tests_claims_ledger.py

CLAIMS.md maps every load-bearing claim to the executable statement that
would go red if the claim stopped being true. That mapping is itself a
claim, and this suite is what makes it falsifiable: every referenced file
must exist, every row must reference at least one, and the rows that anchor
the newest proofs must actually be present. Delete a proof, or a row's
file, and this goes red before the sentence it backed does.
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

PASS = FAIL = 0


def check(n, c, d=""):
    global PASS, FAIL
    if c:
        PASS += 1
        print("  ok  " + n)
    else:
        FAIL += 1
        print("  FAIL " + n + "  " + str(d)[:220])


LEDGER = os.path.join(ROOT, "CLAIMS.md")
check("CLAIMS.md exists at the repository root", os.path.exists(LEDGER))

with open(LEDGER, encoding="utf-8") as f:
    lines = f.read().splitlines()

rows = [ln for ln in lines
        if ln.startswith("|") and not ln.startswith("|---")
        and "The claim" not in ln]
check("the ledger holds a real number of claims", len(rows) >= 12, len(rows))

print("== every row names its executable statement ==")
all_refs = set()
for ln in rows:
    refs = [r for r in re.findall(r"`([^`]+)`", ln)
            if "/" in r or r.endswith((".py", ".txt", ".yml", ".json", ".md"))]
    claim = ln.split("|")[1].strip()[:60]
    check("'%s...' cites at least one file" % claim, bool(refs), ln[:120])
    all_refs.update(refs)

print("== every cited file exists ==")
for ref in sorted(all_refs):
    path = ref.split(" ")[0].strip("`")
    check(path, os.path.exists(os.path.join(ROOT, path)))

print("== the proofs the ledger leans on hardest are present ==")
for must in ("server/tests_airgap.py", "server/tests_upgrade_stability.py",
             "server/tests_witness_benchmark.py",
             "server/testdata/golden_log_v1.json"):
    check("ledger anchor %s is cited" % must,
          any(must in r for r in all_refs), sorted(all_refs))

print("\n%d passed, %d failed" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)
