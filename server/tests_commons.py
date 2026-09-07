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
con.executescript(commons.COMMONS_SCHEMA)

print("== validation at the door ==")
GOOD = {"instance": "a" * 16, "patterns": [
    {"antecedent": "prefers_morning_meetings", "consequent": "prefers_email_contact",
     "support": 5, "refute": 1, "subjects": 8, "consequent_base": 0.2}]}
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


print("== the lift test, which nobody but the contributor can measure ==")
# The bar a pattern has to clear is not "most P-holders hold Q". It is "more of
# them hold Q than hold Q anyway", and the base rate that answers that is
# measured over a population the collector deliberately never sees. Before
# `consequent_base` the door could not ask, so a hand-assembled contribution
# could clear every other test and still be the consequent's popularity wearing
# the antecedent as a hat. Measured on 19,719 respondents, the rate test alone
# recovered a known latent structure at 0.185 against a chance line of 0.184.
_P = GOOD["patterns"][0]
_wl = _h._wilson_lower(_P["support"], _P["support"] + _P["refute"])

clean, err = commons.validate(
    {**GOOD, "patterns": [{k: v for k, v in _P.items() if k != "consequent_base"}]})
check("a pattern that will not say what it beats is refused, not skipped",
      clean == [] and err is not None and "consequent_base" in err, (clean, err))

for name, base in (("a rate above one", 1.5), ("a negative rate", -0.1),
                   ("a rate that is not a number", "most")):
    clean, err = commons.validate(
        {**GOOD, "patterns": [{**_P, "consequent_base": base}]})
    check("%s is refused" % name,
          clean == [] and err is not None and "between 0 and 1" in err, err)

# The line itself, checked from both sides so a change to either constant moves
# the test rather than leaving it passing for the wrong reason.
_just_under = round(_wl - _h.PRIOR_MIN_LIFT - 0.01, 4)
_just_over = round(_wl - _h.PRIOR_MIN_LIFT + 0.01, 4)
clean, err = commons.validate(
    {**GOOD, "patterns": [{**_P, "consequent_base": _just_under}]})
check("a pattern that beats the consequent's base rate is kept",
      err is None and len(clean) == 1, (clean, err))
clean, err = commons.validate(
    {**GOOD, "patterns": [{**_P, "consequent_base": _just_over}]})
check("one that does not is skipped quietly, the way the floor is",
      err is None and clean == [], (clean, err))

# A consequent almost everybody holds cannot be predicted by anything: there is
# no headroom above its own popularity, whatever the antecedent is.
clean, err = commons.validate(
    {**GOOD, "patterns": [{**_P, "consequent_base": 0.95}]})
check("a near-universal consequent is predicted by nothing",
      err is None and clean == [], (clean, err))

# The rate floor was in hypotheses.py and never at the door either, so a
# contribution could carry a pattern its own author's install would refuse.
clean, err = commons.validate({**GOOD, "patterns": [
    {**_P, "support": 5, "refute": 5, "consequent_base": 0.0}]})
check("and the minimum rate is enforced at the door too",
      err is None and clean == [], (clean, err))

check("the surviving pattern carries the rate it was judged against",
      commons.validate(GOOD)[0][0].get("consequent_base") == 0.2,
      commons.validate(GOOD)[0])

# The three tests are one vocabulary shared by hypotheses.py, the door and the
# standalone contributor script. A copy that drifts is a door that enforces a
# different bar from the one the dataset card describes.
check("the door judges by the same constants the bank learns with",
      (commons.PRIOR_FLOOR_N, commons.PRIOR_MIN_RATE, commons.PRIOR_MIN_LIFT)
      == (_h.PRIOR_FLOOR_N, _h.PRIOR_MIN_RATE, _h.PRIOR_MIN_LIFT))

print("== the dataset says which of its checks a reader can settle ==")
_card = commons.dataset_card([], {"stances": 0, "contributors": 0})
check("the card separates what a reader can check from what it cannot",
      "cannot settle" in _card and "contributor's word" in _card, None)
check("and names the field that carries the unverifiable half",
      "consequent_base" in _card, None)


print("== a prior learned before the base rate was kept cannot be published ==")
# priors.base_q was added after the fact, so an install that has been running
# has rows with nothing in it. Those rows are still perfectly good LOCALLY:
# they were checked against the lift test when they were learned, and the
# column is missing because nobody wrote it down, not because the test was
# skipped. They cannot go into the commons, because a reader of the dataset
# has only what the file says and the file would have nothing to say.
_lg = sqlite3.connect(":memory:")
_lg.row_factory = sqlite3.Row
_h.ensure_schema(_lg)


def _prior(pid, proj, a, c, s, r, n, base):
    _lg.execute("INSERT INTO priors(id,project_id,antecedent,consequent,context,"
                "support,refute,subjects,updated,base_q) "
                "VALUES(?,?,?,?,'default',?,?,?,0,?)",
                (pid, proj, a, c, s, r, n, base))


_prior("p1", "projA", "prefers_async", "works_remotely", 9, 1, 10, 0.2)
_prior("p2", "projA", "likes_alpha", "likes_beta", 9, 1, 10, None)
_lg.commit()
_rows = {(b["antecedent"], b["consequent"]): b
         for b in _h.bank(_lg, ["projA"])}
check("a prior that recorded the base rate carries it into the bank",
      _rows[("prefers_async", "works_remotely")]["consequent_base"] == 0.2,
      _rows[("prefers_async", "works_remotely")])
check("one that predates the column carries None rather than a guess",
      _rows[("likes_alpha", "likes_beta")]["consequent_base"] is None,
      _rows[("likes_alpha", "likes_beta")])

# And the same pair from two projects. The merged row answers with ONE base
# rate, and it has to be the one that makes the pattern hardest to justify,
# because lift is measured against it: taking the mean or the lower would let a
# pattern that is pure popularity in one population be rescued by another where
# the consequent happened to be rare.
_prior("p3", "projB", "prefers_async", "works_remotely", 5, 0, 5, 0.45)
_lg.commit()
_merged = {(b["antecedent"], b["consequent"]): b
           for b in _h.bank(_lg, ["projA", "projB"])}
check("the merge of two populations keeps the least flattering base rate",
      _merged[("prefers_async", "works_remotely")]["consequent_base"] == 0.45,
      _merged[("prefers_async", "works_remotely")])

# One unknown poisons the merge. Dropping the None so the known rates could
# answer for it would launder exactly the rows whose lift was never recorded.
_prior("p4", "projB", "likes_alpha", "likes_beta", 5, 0, 5, 0.1)
_lg.commit()
_merged = {(b["antecedent"], b["consequent"]): b
           for b in _h.bank(_lg, ["projA", "projB"])}
check("a known rate cannot answer for an unknown one beside it",
      _merged[("likes_alpha", "likes_beta")]["consequent_base"] is None,
      _merged[("likes_alpha", "likes_beta")])

# Which is what the sender acts on: the row is dropped rather than sent to be
# refused, because a pattern that cannot state its base rate is refused at the
# door and would take the whole contribution down with it.
check("the door refuses what the bank could not describe",
      commons.validate({**GOOD, "patterns": [
          {k: v for k, v in _merged[("likes_alpha", "likes_beta")].items()
           if k in commons.PATTERN_FIELDS}]})[1] is not None)

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
