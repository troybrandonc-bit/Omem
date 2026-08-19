"""Self-healing on Postgres: proves the subsystem is correct on the production
backend, especially the DB-enforced single-active-claim under CONCURRENT SEPARATE
connections (true multi-instance). Skips cleanly if OMEM_DATABASE_URL is unset."""
import os, sys, threading

URL = os.environ.get("OMEM_DATABASE_URL")
if not URL or not URL.startswith(("postgres://", "postgresql://")):
    print("SKIP: set OMEM_DATABASE_URL to a Postgres URL to run these tests")
    sys.exit(0)

from store import Store
import healing as H

passed = failed = 0
def check(n, c, d=""):
    global passed, failed
    passed += bool(c); failed += (not c)
    print(("  ok   " if c else "  FAIL ") + n + ("" if c else f"  <<< {d}"))

ORG, PROJ = "org_pg", "proj_pg"
st = Store(URL)
hs = H.HealingStore(st.db)

print("== PG: full recovery lifecycle ==")
reg = H.default_action_registry(); comps = H.ComponentRegistry()
state = {"ok": False}
comps.register("comp", rebuild_index=lambda a=None: state.update(ok=True),
               health=lambda: ("healthy" if state["ok"] else "failed", "s"))
healer = H.Healer(hs, reg, comps, H.Policy(reg, lambda p: True))
res = healer.handle(ORG, PROJ, {"component": "comp", "error_type": "E", "message": "m"},
                    owner="a", diagnose_fn=lambda f, m: {"actions": [{"type": "rebuild_index"}], "confidence": 0.9})
check("recovers on PG", res["status"] == "recovered", res)

print("== PG: DB-enforced single claim under concurrent SEPARATE connections ==")
f = hs.record_failure(ORG, PROJ, {"fingerprint": "cc", "component": "cc", "error_type": "E"})
results = []; lock = threading.Lock()
def claim(i):
    s = Store(URL); h = H.HealingStore(s.db)
    r = h.claim_recovery(ORG, PROJ, f["id"], "cc", f"o{i}", "fp")
    with lock: results.append(r)
tp = [threading.Thread(target=claim, args=(i,)) for i in range(10)]
[t.start() for t in tp]; [t.join() for t in tp]
winners = [r for r in results if r]
check("exactly one winner across 10 concurrent connections", len(winners) == 1, len(winners))
hs.release_recovery(ORG, PROJ, "cc", winners[0])
check("re-claim succeeds after release", hs.claim_recovery(ORG, PROJ, f["id"], "cc", "o", "fp2") is not None)

print("== PG: tenant isolation ==")
fa = hs.record_failure("orgA", "projA", {"fingerprint": "x", "component": "c", "error_type": "E"})
check("cross-tenant read blocked", hs.failure("orgB", "projB", fa["id"]) is None)

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
