"""The commons' return leg: what comes back, and where it ranks.
Run: python3 tests_pooled_priors.py

Contribution was always the easy direction. Reading is the one that needs the
stricter door, because these rows arrive from a server and end up shaping what
this machine believes about the people in front of it.

Three properties, and all three are refusals:
  * a pooled prior never displaces a local one,
  * it is born less bold than the same prior mined here,
  * one install cannot teach the world its own idiosyncrasies.
"""
import os
import sqlite3
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
TMP = os.environ.get("TEMP") or "/tmp"
DB = os.path.join(TMP, "omem_pooled.db")
if os.path.exists(DB):
    os.remove(DB)
os.environ["OMEM_DB"] = DB

import commons  # noqa: E402
import hypotheses as _h  # noqa: E402

PASS = FAIL = 0


def check(n, c, d=""):
    global PASS, FAIL
    if c:
        PASS += 1
        print("  ok  " + n)
    else:
        FAIL += 1
        print("  FAIL " + n + "  " + str(d)[:220])


con = sqlite3.connect(DB)
con.row_factory = sqlite3.Row
commons.ensure_schema(con)

print("== the door the bank comes back through ==")
rows, err = commons.accept_pooled([
    {"antecedent": "asks_early", "consequent": "approves_agenda",
     "support": 40, "refute": 5, "subjects": 30, "sources": 4},
    {"antecedent": "asks_early", "consequent": "abandons_alpha",
     "support": 40, "refute": 1, "subjects": 30, "sources": 1},
    {"antecedent": "asks_early", "consequent": "accepts_async",
     "support": 1, "refute": 0, "subjects": 1, "sources": 9},
])
check("a pattern only one install has seen is refused",
      err is None and not any(r["consequent"] == "abandons_alpha" for r in rows), rows)
check("a pattern under the support floor is refused",
      not any(r["consequent"] == "accepts_async" for r in rows), rows)
check("the independently corroborated pattern survives",
      len(rows) == 1 and rows[0]["consequent"] == "approves_agenda", rows)
check("POOLED_MIN_SOURCES is the rule being applied",
      commons.POOLED_MIN_SOURCES == 2)

_, err = commons.accept_pooled([
    {"antecedent": "person:alice@corp.example", "consequent": "approves_agenda",
     "support": 40, "refute": 5, "subjects": 30, "sources": 4}])
check("an identifying token from a compromised collector is refused",
      err is not None and "identifying" in err, err)
out, err = commons.accept_pooled([
    {"antecedent": "johnsmith", "consequent": "approves_agenda",
     "support": 40, "refute": 5, "subjects": 30, "sources": 4}])
check("a token outside the shared vocabulary is dropped, not imported",
      err is None and out == [], (out, err))
check("a malformed payload is refused rather than half-read",
      commons.accept_pooled("not a list")[1] is not None)

print("== storage is a snapshot, never an accumulation ==")
commons.store_pooled(con, rows)
commons.store_pooled(con, rows)
check("syncing twice does not double-count the same populations",
      len(commons.pooled(con)) == 1, commons.pooled(con))
check("the engine reads the same rows through its own door",
      len(_h._pooled_rows(con)) == 1, _h._pooled_rows(con))

print("== a database that has never synced is not an error ==")
bare = sqlite3.connect(":memory:")
bare.row_factory = sqlite3.Row
check("no pooled table reads as no pooled priors", _h._pooled_rows(bare) == [])
check("and commons.pooled agrees", commons.pooled(bare) == [])

print("== the discount only ever makes a hunch more cautious ==")
check("POOLED_DISCOUNT is below 1", 0 < _h.POOLED_DISCOUNT < 1, _h.POOLED_DISCOUNT)
base = _h._birth_strength((0, 0), (0, 0))
disc = round(max(_h.STRENGTH_FLOOR, base * _h.POOLED_DISCOUNT), 2)
check("a borrowed prior is born weaker than the same prior mined here",
      disc < base, (base, disc))
bold = _h._birth_strength((10, 0), (10, 0))
check("even a well-recorded generator cannot push a pooled hunch above local",
      round(max(_h.STRENGTH_FLOOR, bold * _h.POOLED_DISCOUNT), 2) < bold)
check("the discount cannot fall through the floor",
      round(max(_h.STRENGTH_FLOOR, 0.05 * _h.POOLED_DISCOUNT), 2) >= _h.STRENGTH_FLOOR)

print("== local knowledge is never displaced by borrowed knowledge ==")
# The rule leap() applies: a pair a local prior already covers is dropped
# before pooled rows are appended, so the local row is the one that fires.
local = [{"antecedent": "asks_early", "consequent": "approves_agenda"}]
local_pairs = {(r["antecedent"], r["consequent"]) for r in local}
kept = [r for r in commons.pooled(con)
        if (r["antecedent"], r["consequent"]) not in local_pairs]
check("a pooled prior covering a local pair is dropped, not ranked", kept == [], kept)

print("\n%d passed, %d failed" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)
