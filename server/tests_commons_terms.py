"""A contribution records the deal it was made under.
Run: python3 tests_commons_terms.py

The counts are anonymous, so this is not a privacy record, it is a rights
record. It exists because the bank may one day be published in more than one
form, and which uses an operator agreed to is a fact about the moment they
agreed. Nothing else in the database can reconstruct it afterwards, so it is
written at the moment of contribution or it is lost.

Four properties, each a way this could quietly become decoration:

  a grant is read from the STORED record, never from the table in this file.
  A table keyed by version would mean editing the source could widen what a
  contribution made last year permitted, which is the whole failure this
  guards against;

  silence is never a grant. A contribution that predates the record, or one
  whose record cannot be read, grants the public commons and nothing else --
  the exact question its operator was actually shown;

  the filter lives in ONE place, so every artifact inherits it by
  construction rather than by remembering. A row that granted no publication
  cannot reach the dataset, the public endpoint, or the operator's own view;

  withdrawal reaches the bank. set_choice has always said consent that cannot
  be withdrawn is not consent, and until now that was true only of the next
  contribution.
"""
import json
import os
import sqlite3
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

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


def fresh():
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    commons.ensure_schema(db)
    return db


PATS = [{"antecedent": "prefers_async", "consequent": "works_remotely",
         "support": 5, "refute": 1, "subjects": 6}]
CAL = [{"scope": "generator_class", "name": "prior", "supported": 4, "refuted": 1}]


print("== what contributing grants today ==")
t = commons.mint_terms()
check("the minted record names the version in force",
      t["version"] == commons.TERMS_VERSION, t)
check("it grants the public commons",
      commons.grants_of(t) == {"public_commons"}, t)
check("and grants nothing commercial, because nobody has been asked",
      "commercial" not in commons.grants_of(t), t)
check("commercial is a known grant, so the question can be asked later",
      "commercial" in commons.GRANTS, commons.GRANTS)

print("== silence is never a grant ==")
check("no record at all reads as the public commons only",
      commons.grants_of(None) == {"public_commons"})
check("an unreadable record reads the same way, rather than raising",
      commons.grants_of("{not json") == {"public_commons"})
check("a record with no granted list reads the same way",
      commons.grants_of({"version": "x"}) == {"public_commons"})
check("a grant this build does not recognise is dropped, not honoured",
      commons.grants_of({"version": "x", "granted": ["public_commons", "resale"]})
      == {"public_commons"})

print("== a stored grant cannot be widened by editing this file ==")
# The property that makes the record worth keeping. A contribution is stored
# under today's terms; the terms table is then rewritten to claim that same
# version always allowed commercial use. The stored record must not move.
stored = {"version": commons.TERMS_VERSION, "granted": ["public_commons"]}
_saved = commons.TERMS[commons.TERMS_VERSION]
commons.TERMS[commons.TERMS_VERSION] = {
    "granted": ["public_commons", "commercial"], "summary": "rewritten"}
try:
    check("rewriting the table does not widen a contribution already stored",
          commons.grants_of(stored) == {"public_commons"}, commons.grants_of(stored))
    check("but a NEW contribution is minted under the rewritten table",
          commons.grants_of(commons.mint_terms())
          == {"public_commons", "commercial"})
finally:
    commons.TERMS[commons.TERMS_VERSION] = _saved
check("the table is restored for the rest of the suite",
      commons.grants_of(commons.mint_terms()) == {"public_commons"})

print("== the door ==")
ok, err = commons.validate_terms({"instance": "a" * 12})
check("a client that sends no terms is accepted, and reads as the default",
      ok is None and err is None, (ok, err))
_, err = commons.validate_terms({"terms": "public_commons"})
check("a terms field that is not an object is refused", err is not None, err)
_, err = commons.validate_terms({"terms": {"version": "x", "granted": "all"}})
check("granted must be a list", err is not None, err)
_, err = commons.validate_terms({"terms": {"version": "x",
                                           "granted": ["everything"]}})
check("an unknown grant is refused BY NAME rather than trimmed silently",
      err is not None and "everything" in err, err)
ok, err = commons.validate_terms({"terms": {"version": "2026-09-02",
                                            "granted": ["public_commons"]}})
check("a well-formed record is accepted and stamped with arrival",
      err is None and ok["granted"] == ["public_commons"] and "recorded" in ok, ok)

print("== the filter every artifact inherits ==")
db = fresh()
commons.store(db, "inst-public", PATS, CAL,
              {"version": "2026-09-02", "granted": ["public_commons"]})
commons.store(db, "inst-both", PATS, CAL,
              {"version": "2026-09-02", "granted": ["public_commons", "commercial"]})
commons.store(db, "inst-old", PATS, CAL, None)   # a client predating the record
pub = commons.latest_per_instance(db)
com = commons.latest_per_instance(db, grant="commercial")
check("the public dataset sees every install that granted publication",
      set(pub) == {"inst-public", "inst-both", "inst-old"}, sorted(pub))
check("a commercial artifact sees only the one that granted it",
      set(com) == {"inst-both"}, sorted(com))
check("the pre-record contribution is published, because that IS what it "
      "agreed to", "inst-old" in pub)
check("and is not commercial, because that question was never put to it",
      "inst-old" not in com)
check("calibration is filtered by the same rule, from the same record",
      set(commons.latest_calibration_per_instance(db)) == set(pub)
      and set(commons.latest_calibration_per_instance(db, grant="commercial"))
      == {"inst-both"})
rows = commons.merged([], com)
check("so an artifact built from the filtered view carries only granted counts",
      len(rows) == 1 and rows[0]["sources"] == 1, rows)

print("== withdrawal reaches the bank, not just the next send ==")
n = commons.withdraw(db, "inst-both")
check("withdrawing reports how many contributions it covered", n == 1, n)
check("the withdrawn install leaves the public view",
      "inst-both" not in commons.latest_per_instance(db))
check("and leaves the commercial view, which is now empty",
      commons.latest_per_instance(db, grant="commercial") == {})
check("and leaves the calibration view",
      "inst-both" not in commons.latest_calibration_per_instance(db))
check("the other contributors are untouched",
      set(commons.latest_per_instance(db)) == {"inst-public", "inst-old"})
kept = db.execute("SELECT COUNT(*) AS n FROM commons_contributions "
                  "WHERE instance='inst-both'").fetchone()["n"]
check("the row is kept rather than deleted, so the ledger stays append-only "
      "and the withdrawal is itself auditable", kept == 1, kept)
check("withdrawing twice is not an error", commons.withdraw(db, "inst-both") == 1)
check("withdrawing an instance that never contributed is not an error",
      commons.withdraw(db, "inst-never") == 0)

print("== the published stats do not count what was taken back ==")
stats = commons.analytics(commons.merged([], commons.latest_per_instance(db)),
                          commons.latest_per_instance(db), db)
check("contributors counts the two that remain", stats["contributors"] == 2, stats)
check("and the timeline counts their contributions only",
      sum(w["contributions"] for w in stats["timeline"]) == 2, stats["timeline"])

print("== the operator's own record of what they agreed to ==")
db2 = fresh()
check("an install that never answered contributes under the restrictive "
      "default", commons.grants_of(commons.current_terms(db2)) == {"public_commons"})
check("and says so plainly rather than inventing a version",
      commons.current_terms(db2)["version"] == "pre-record")
commons.set_choice(db2, True)
check("saying yes stamps the terms in force at that moment",
      commons.current_terms(db2)["version"] == commons.TERMS_VERSION,
      commons.current_terms(db2))
check("the choice itself is recorded as before", commons.get_choice(db2) == "yes")
commons.set_choice(db2, False)
check("saying no clears the stamp: there is no agreement to describe",
      commons.current_terms(db2)["version"] == "pre-record")
check("and the choice is recorded as no", commons.get_choice(db2) == "no")

print("== the card tells the reader which deal produced the file ==")
card = commons.dataset_card(rows, {"stances": 6, "contributors": 2})
check("the terms version travels with the dataset",
      commons.TERMS_VERSION in card, card[-400:])
check("the card states that contributing grants no other use",
      "requires its own question" in card)
check("and that withdrawn contributions are not in it", "withdrawn" in card)
check("the licence line is unchanged", commons.DATASET_LICENSE in card)

print("== an upgrade adds the column without losing a contribution ==")
db3 = sqlite3.connect(":memory:")
db3.row_factory = sqlite3.Row
db3.execute("CREATE TABLE commons_contributions(id INTEGER PRIMARY KEY "
            "AUTOINCREMENT, instance TEXT NOT NULL, received REAL NOT NULL, "
            "patterns TEXT NOT NULL, calibration TEXT)")
db3.execute("INSERT INTO commons_contributions(instance, received, patterns, "
            "calibration) VALUES('inst-legacy',1.0,?,'[]')", (json.dumps(PATS),))
db3.commit()
commons.ensure_schema(db3)
cols = {r["name"] for r in db3.execute("PRAGMA table_info(commons_contributions)")}
check("ensure_schema adds terms to a collector that predates it",
      "terms" in cols, cols)
check("and the contribution already in it still publishes",
      set(commons.latest_per_instance(db3)) == {"inst-legacy"})
check("but grants nothing beyond the commons",
      commons.latest_per_instance(db3, grant="commercial") == {})

print("\n%d passed, %d failed" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)
