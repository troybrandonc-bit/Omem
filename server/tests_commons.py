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
    # Regression: these carry no digit, colon, or rel_ prefix, so the original
    # door check let them through and they landed in the public dataset.
    ("email token refused",
     {**GOOD, "patterns": [{**GOOD["patterns"][0], "antecedent": "email_john@acme.com"}]}),
    ("domain token refused",
     {**GOOD, "patterns": [{**GOOD["patterns"][0], "consequent": "works_at_acme.com"}]}),
    ("capitalised name token refused",
     {**GOOD, "patterns": [{**GOOD["patterns"][0], "antecedent": "John_Smith"}]}),
    ("non-integer counts refused",
     {**GOOD, "patterns": [{**GOOD["patterns"][0], "support": "many"}]}),
    ("bad instance id refused", {**GOOD, "instance": "x"}),
    ("non-list patterns refused", {**GOOD, "patterns": "nope"}),
]:
    _, err = commons.validate(bad)
    check(name, err is not None)
_, err = commons.validate({**GOOD, "patterns": GOOD["patterns"] * (commons.MAX_PATTERNS + 1)})
check("oversized contribution refused", err is not None)

print("== the vocabulary: engineered-lowercase tokens can no longer pass ==")
# Regression for the residual hole the format checks could not close: a token
# built to LOOK like a plain behaviour word while smuggling identity.
for name, tok in [
    ("smuggled name+employer token refused", "johnsmith_of_acmecorp"),
    ("affiliation connector 'at' is outside the lexicon", "works_at_acme"),
    ("random word outside the lexicon refused", "prefers_zorblax_billing"),
]:
    _, err = commons.validate(
        {**GOOD, "patterns": [{**GOOD["patterns"][0], "antecedent": tok}]})
    check(name, err is not None and "vocabulary" in (err or ""), err)
clean, err = commons.validate(GOOD)
check("canonical tokens still pass the lexicon", err is None and len(clean) == 1, err)
for tok in ("prefers_annual_billing", "works_remotely", "is_enterprise_customer",
            "intends_to_upgrade", "considering_cancel", "wants_pdf_invoices"):
    check("lexicon covers canonical token " + tok, commons.lexicon_ok(tok))
check("lexicon_ok refuses structural violations too",
      not commons.lexicon_ok("rel_works_at_acme") and not commons.lexicon_ok("a:b"))

print("== merged() re-checks stored rows against the vocabulary ==")
_pre_vocab = {"legacy": (1.0, [
    {"antecedent": "johnsmith_of_acmecorp", "consequent": "likes_beta",
     "support": 9, "refute": 0, "subjects": 9},
    {"antecedent": "likes_alpha", "consequent": "likes_beta",
     "support": 9, "refute": 0, "subjects": 9}])}
_m = commons.merged([], _pre_vocab)
_toks = {r["antecedent"] for r in _m}
check("a pre-vocabulary stored row is dropped from the dataset",
      "johnsmith_of_acmecorp" not in _toks, _toks)
check("while the clean row from the same snapshot survives",
      "likes_alpha" in _toks, _toks)
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

print("== calibration: the half that says what a guess is worth ==")
import hypotheses as _h  # noqa: E402

# The leak this feature nearly shipped. `leap()` sets generator = the
# NEIGHBOUR'S SUBJECT ID, so the raw column is people. Only the class travels.
check("a subject id is classed, never published",
      _h._generator_class("person:alice@corp.example") == "neighbour")
check("a prior-driven leap is classed as prior",
      _h._generator_class("prior:p-1731") == "prior")

cal_db = sqlite3.connect(":memory:")
cal_db.row_factory = sqlite3.Row
cal_db.executescript(_h.HYPOTHESES_SCHEMA)
for gen, w, l in (("person:alice@corp.example", 4, 1), ("person:bob@corp.example", 2, 2),
                  ("prior:p-1", 5, 0)):
    cal_db.execute("INSERT INTO leap_generators(project_id, generator, wins, losses) "
                   "VALUES('proj',?,?,?)", (gen, w, l))
for i, (prop, st) in enumerate((("prefers_email", "supported"), ("prefers_email", "supported"),
                                ("prefers_email", "refuted"), ("wants_pdf", "supported"))):
    cal_db.execute("INSERT INTO hypotheses VALUES(?,'proj','s','%s','b','g','c',0.4,?,'d',0,"
                   "'fp',0,0)" % prop, (f"h{i}", st))
cal_db.commit()

rows = _h.calibration_bank(cal_db, ["proj"])
names = {r["name"] for r in rows}
check("no subject id reaches the bank",
      not any("@" in n or "person:" in n for n in names), names)
check("the two generator classes are pooled, not the six generators",
      names >= {"neighbour", "prior"} and len(names & {"neighbour", "prior"}) == 2, names)
neigh = [r for r in rows if r["name"] == "neighbour"][0]
check("neighbour verdicts are summed across the subjects they came from",
      (neigh["supported"], neigh["refuted"]) == (6, 3), neigh)
check("a family below the floor does not travel",
      "wants" not in names, names)

print("== calibration is refused at the door too ==")
_, e = commons.validate_calibration({"calibration": [
    {"scope": "generator_class", "name": "person:alice@corp.example",
     "supported": 9, "refuted": 1}]})
check("a raw generator is refused even when it is spelled like a class",
      e is not None and "generator class" in e, e)
_, e = commons.validate_calibration({"calibration": [
    {"scope": "family", "name": "johnsmith", "supported": 9, "refuted": 1}]})
check("a family outside the lexicon is refused with the word named",
      e is not None and "lexicon" in e, e)
_, e = commons.validate_calibration({"calibration": [
    {"scope": "audience", "name": "prior", "supported": 9, "refuted": 1}]})
check("an unknown scope is refused", e is not None, e)
ok, e = commons.validate_calibration({"calibration": [
    {"scope": "generator_class", "name": "prior", "supported": 1, "refuted": 0},
    {"scope": "generator_class", "name": "neighbour", "supported": 6, "refuted": 3}]})
check("the floor drops the thin row and keeps the real one",
      e is None and len(ok) == 1 and ok[0]["name"] == "neighbour", (ok, e))
check("an absent calibration key is not an error (older clients)",
      commons.validate_calibration({"patterns": []}) == ([], None))

print("== calibration storage and merge ==")
commons.ensure_schema(con)
commons.store(con, "inst-cal", [], [{"scope": "generator_class", "name": "neighbour",
                                     "supported": 6, "refuted": 3}])
con.execute("INSERT INTO commons_contributions(instance, received, patterns, calibration) "
            "VALUES('inst-old',?,'[]',NULL)", (time.time(),))
con.commit()
latest = commons.latest_calibration_per_instance(con)
check("a contribution predating calibration reads as no rows, not an error",
      latest.get("inst-old") == [], latest.get("inst-old"))
merged = commons.merged_calibration(
    [{"scope": "generator_class", "name": "neighbour", "supported": 4, "refuted": 0}],
    latest)
n = [r for r in merged if r["name"] == "neighbour"][0]
check("own and contributed verdicts merge into one rate",
      (n["supported"], n["refuted"], n["sources"]) == (10, 3, 2), n)
check("the rate is computed from what survived", n["rate"] == round(10 / 13, 3), n)

print("\n%d passed, %d failed" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)
