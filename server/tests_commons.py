"""The commons: consent, validation at the door, honest merging.
Run: python3 tests_commons.py

The bank is the creator's, not a user feature, and contributions from other
installs are gifts that must be checked at the door: identifying tokens
refused, counts sane, one snapshot per instance (never cumulative), and the
analytics computed from what survived.
"""
import json
import os
import sqlite3
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
TMP = os.environ.get("TEMP") or "/tmp"
DB = os.path.join(TMP, "omem_commons.db")
if os.path.exists(DB):
    os.remove(DB)
os.environ["OMEM_DB"] = DB

import commons  # noqa: E402

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
con.executescript(commons.COMMONS_SCHEMA)

print("== validation at the door ==")
GOOD = {"instance": "a" * 16, "patterns": [
    {"antecedent": "prefers_morning_meetings", "consequent": "prefers_email_contact",
     "support": 5, "refute": 1, "subjects": 8}]}
clean, err = commons.validate(GOOD)
check("a clean contribution passes", err is None and len(clean) == 1, err)
for name, bad in [
    ("identifying antecedent refused",
     {**GOOD, "patterns": [{**GOOD["patterns"][0], "antecedent": "rel_works_at_acme"}]}),
    ("identifying consequent refused",
     {**GOOD, "patterns": [{**GOOD["patterns"][0], "consequent": "company:acme"}]}),
    ("value-bearing token refused",
     {**GOOD, "patterns": [{**GOOD["patterns"][0], "antecedent": "payment_terms_net30"}]}),
    ("non-integer counts refused",
     {**GOOD, "patterns": [{**GOOD["patterns"][0], "support": "many"}]}),
    ("bad instance id refused", {**GOOD, "instance": "x"}),
    ("non-list patterns refused", {**GOOD, "patterns": "nope"}),
]:
    _, err = commons.validate(bad)
    check(name, err is not None)
_, err = commons.validate({**GOOD, "patterns": GOOD["patterns"] * (commons.MAX_PATTERNS + 1)})
check("oversized contribution refused", err is not None)
clean, err = commons.validate({**GOOD, "patterns": [
    {**GOOD["patterns"][0], "support": 2}]})
check("below-floor pattern skipped quietly, not an error",
      err is None and clean == [])

print("== one snapshot per instance, never cumulative ==")
commons.store(con, "instA", [{"antecedent": "likes_alpha", "consequent": "likes_beta",
                              "support": 5, "refute": 0, "subjects": 5}])
time.sleep(0.01)
commons.store(con, "instA", [{"antecedent": "likes_alpha", "consequent": "likes_beta",
                              "support": 9, "refute": 1, "subjects": 10}])
commons.store(con, "instB", [{"antecedent": "likes_alpha", "consequent": "likes_beta",
                              "support": 4, "refute": 0, "subjects": 4}])
latest = commons.latest_per_instance(con)
check("two instances, latest snapshot each", len(latest) == 2)
check("instA counted at its newest report", latest["instA"][1][0]["support"] == 9)

print("== merging own priors with contributions ==")
own = [{"antecedent": "likes_alpha", "consequent": "likes_beta", "support": 6, "refute": 2, "subjects": 8}]
rows = commons.merged(own, latest)
r = next(x for x in rows if (x["antecedent"], x["consequent"]) == ("likes_alpha", "likes_beta"))
check("support sums across own + both instances", r["support"] == 6 + 9 + 4, r)
check("sources counts every install, own included", r["sources"] == 3)
check("rate recomputed over the pool", abs(r["rate"] - (19 / 22)) < 0.01, r["rate"])

print("== analytics ==")
a = commons.analytics(rows, latest, con)
check("contributors counted", a["contributors"] == 2)
check("patterns counted", a["patterns"] == len(rows))
check("stances = support + refute over the pool",
      a["stances"] == sum(x["support"] + x["refute"] for x in rows))
check("timeline has at least one week", len(a["timeline"]) >= 1)
check("communication category recognised",
      commons.category_of("prefers_email_contact") == "communication")
check("scheduling covers unavailable days",
      commons.category_of("unavailable_fridays") == "scheduling")
check("commercial category recognised",
      commons.category_of("prefers_annual_billing") == "commercial")

print("== the training corpus ==")
jl = commons.dataset_jsonl(rows)
jlines = [json.loads(x) for x in jl.strip().splitlines()]
check("one JSON line per pattern", len(jlines) == len(rows))
check("every line carries text, counts and a category",
      all(l.get("text") and "support" in l and l.get("category") for l in jlines))
check("no line carries an identifying token",
      all(not commons._identifying(l["antecedent"])
          and not commons._identifying(l["consequent"]) for l in jlines))
card = commons.dataset_card(rows, a)
check("the card names the license", commons.DATASET_LICENSE in card)
check("the card explains the consent story", "opt-in" in card)
check("the card treats patterns as priors, not rules",
      "never rules about individuals" in card)

print("== the operator's decision: durable, revocable, never presumed ==")
check("never asked reads as None (no send happens on None)",
      commons.get_choice(con) is None)
commons.set_choice(con, True)
check("yes is recorded", commons.get_choice(con) == "yes")
commons.set_choice(con, False)
check("consent is revocable", commons.get_choice(con) == "no")

print("\n%d passed, %d failed" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)
