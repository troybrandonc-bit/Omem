"""One question, answered at the moment it matters, or honestly refused.
Run: python3 tests_ask.py

priors() hands over everything an installation has learned and leaves the
caller to search it. That is a filing cabinet. An agent deciding something
about a person needs one answer to one question, with what it rests on
attached, at the moment it is deciding -- which is a different object, and the
difference is most of what separates a dataset from something worth consulting.

Three properties are load-bearing here.

WHAT THIS INSTALL SAW ITSELF COMES FIRST. Knowledge about the people this
installation has actually met outranks knowledge borrowed from populations it
has not, which is the same order `leap` applies when choosing which prior may
speak, and it must survive the commons holding far more people.

IT ANSWERS FROM DISK. The pooled rows are the snapshot already on this
machine, so a question costs no network call and is answered identically with
the commons unreachable or never contacted. The commons is a gift in both
directions and never a dependency.

AND IT REFUSES WITH A REASON. `nothing matched` and `too few people for this to
be worth saying` are different answers. Returning an empty list for the second
tells a caller the first, which for a young installation is a lie in the most
damaging direction available.
"""
import os
import sqlite3
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import hypotheses as _h  # noqa: E402

PASS = FAIL = 0


def check(n, c, d=""):
    global PASS, FAIL
    if c:
        PASS += 1
        print("  ok  " + n)
    else:
        FAIL += 1
        print("  FAIL " + n + "  " + str(d)[:240])


def fresh():
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.executescript(_h.HYPOTHESES_SCHEMA)
    _h.ensure_schema(db)
    return db


def local(db, ant, con, support, refute, subjects, pid="proj"):
    db.execute("INSERT INTO priors VALUES(?,?,?,?,'default',?,?,?,0)",
               ("pr_%s_%s" % (ant, con), pid, ant, con, support, refute, subjects))
    db.commit()


def pooled(db, ant, con, support, refute, subjects, sources=4, frames=3):
    # commons_pooled belongs to the commons schema, not the hypotheses one: an
    # install that has never synced does not have the table at all, and ask()
    # has to survive that, which the last section of this file checks.
    db.executescript("""CREATE TABLE IF NOT EXISTS commons_pooled(
      antecedent TEXT NOT NULL, consequent TEXT NOT NULL,
      support INTEGER NOT NULL, refute INTEGER NOT NULL,
      subjects INTEGER NOT NULL, sources INTEGER NOT NULL,
      frames INTEGER NOT NULL DEFAULT 0, rate_min REAL, rate_max REAL,
      received REAL NOT NULL, PRIMARY KEY(antecedent, consequent));""")
    db.execute("INSERT INTO commons_pooled(antecedent, consequent, support, "
               "refute, subjects, sources, frames, rate_min, rate_max, received)"
               " VALUES(?,?,?,?,?,?,?,?,?,0)",
               (ant, con, support, refute, subjects, sources, frames, 0.6, 0.9))
    db.commit()


print("== a question with an answer ==")
db = fresh()
local(db, "prefers_async", "prefers_email", 40, 8, 60)
r = _h.ask(db, "proj", given="prefers_async")
check("it answers", r["answered"] is True, r)
a = r["answers"][0]
check("with the claim it predicts", a["expect"] == "prefers_email", a)
for f in ("people", "held_both", "held_first_denied_second", "rate",
          "confident_rate", "source"):
    check("carrying %s" % f, f in a, sorted(a))
check("the confident rate sits below the raw rate",
      a["confident_rate"] < a["rate"], (a["confident_rate"], a["rate"]))
check("the sentence matches the counts",
      "of 48 people" in a["says"] and "40 also hold" in a["says"], a["says"])
check("and a note that the person in front of you overrides all of it",
      "overrides" in r.get("how_to_read", ""), r.get("how_to_read", "")[:90])

print("== what this install saw itself outranks what it borrowed ==")
db = fresh()
local(db, "prefers_async", "prefers_email", 20, 4, 30)
pooled(db, "prefers_async", "prefers_phone", 9000, 500, 12000)
r = _h.ask(db, "proj", given="prefers_async")
check("both are returned", len(r["answers"]) == 2, r["answers"])
check("this install's own answer comes first, despite the commons holding "
      "four hundred times the people",
      r["answers"][0]["source"] == "this install", [x["source"] for x in r["answers"]])
check("and each says which it came from",
      {x["source"] for x in r["answers"]} == {"this install", "the commons"},
      [x["source"] for x in r["answers"]])
check("the borrowed one reports how many populations back it",
      r["answers"][1]["populations"] == 3, r["answers"][1])

print("== the same pair is not answered twice ==")
db = fresh()
local(db, "prefers_async", "prefers_email", 20, 4, 30)
pooled(db, "prefers_async", "prefers_email", 800, 90, 1200)
r = _h.ask(db, "proj", given="prefers_async")
check("one answer, not two, when both tiers hold the same pair",
      len(r["answers"]) == 1, r["answers"])
check("and it is this install's", r["answers"][0]["source"] == "this install",
      r["answers"][0])

print("== it refuses, and says which refusal it is ==")
db = fresh()
local(db, "prefers_async", "prefers_email", 40, 8, 60)
r = _h.ask(db, "proj", given="likes_dogs")
check("nothing matched: refused, not an empty answer list",
      r["answered"] is False and r["answers"] == [] and r.get("refused"), r)
check("and it says absence of evidence is not evidence of absence",
      "not a finding" in r["refused"], r["refused"])

db = fresh()
local(db, "prefers_async", "prefers_email", 4, 1, 6)
r = _h.ask(db, "proj", given="prefers_async")
check("too few people: a DIFFERENT refusal", r["answered"] is False, r)
check("which says how thin, so the caller can judge for themselves",
      str(_h.ASK_MIN_SUBJECTS) in r["refused"], r["refused"])
check("and the two refusals do not read alike",
      "not a finding" not in r["refused"], r["refused"])

r = _h.ask(db, "proj")
check("a question with no question in it is refused too",
      r["answered"] is False and "ask what" in r["refused"], r)

print("== asked the other way round ==")
db = fresh()
local(db, "prefers_async", "prefers_email", 40, 8, 60)
local(db, "works_remotely", "prefers_email", 30, 5, 44)
r = _h.ask(db, "proj", expect="prefers_email")
check("asking what predicts a claim returns every antecedent",
      r["answered"] and sorted(x["given"] for x in r["answers"])
      == ["prefers_async", "works_remotely"], r["answers"])
r = _h.ask(db, "proj", given="prefers_async", expect="prefers_email")
check("both together narrow to one", len(r["answers"]) == 1, r["answers"])

print("== the record of what happened when it was used ==")
db = fresh()
local(db, "prefers_async", "prefers_email", 40, 8, 60)
_h._score_generator(db, "proj", "prior:pr_prefers_async_prefers_email",
                    True, 0.6, base=0.5)
r = _h.ask(db, "proj", given="prefers_async")
check("an answer carries what happened when this prior was actually applied, "
      "which is a different question from how often it held in a population",
      r["answers"][0]["when_applied"] == {"supported": 1, "refuted": 0},
      r["answers"][0]["when_applied"])

print("== it answers with the commons unreachable, because it never calls it ==")
db = fresh()
pooled(db, "prefers_async", "prefers_email", 800, 90, 1200)
src = open(os.path.join(HERE, "hypotheses.py"), encoding="utf-8").read()
body = src[src.index("def ask(db, project_id"):src.index("def calibration(db")]
check("no network call anywhere in the answer path",
      not any(t in body for t in ("urllib", "requests", "http", "socket")), body[:0])
r = _h.ask(db, "proj", given="prefers_async")
check("and the borrowed snapshot on disk still answers",
      r["answered"] and r["answers"][0]["source"] == "the commons", r)

print("== an install that has never synced answers from its own priors ==")
db = fresh()
local(db, "prefers_async", "prefers_email", 40, 8, 60)
check("no commons table at all, and it still answers",
      _h.ask(db, "proj", given="prefers_async")["answered"] is True)
check("and refuses normally for what it does not know",
      _h.ask(db, "proj", given="likes_dogs")["answered"] is False)

print("== a belief weighed against the population, without being ruled on ==")
# `ask` answers what to expect. `check` answers whether a belief already formed
# was defensible on what was known, which is the question a record of what an
# agent believed actually raises. The line it must not cross is deciding: a
# regularity over other people is not a fact about this one, and a system that
# answered true or false here would be doing exactly what the whole project
# refuses.
db = fresh()
local(db, "prefers_async", "prefers_email", 40, 6, 55)
r = _h.weigh(db, "proj", "prefers_email", holds=["prefers_async"])
check("a belief with evidence behind it is checked",
      r["checked"] is True and r["supported_by"], r)
check("and the evidence names why it applies to this person",
      r["supported_by"][0]["because_they_hold"] == "prefers_async",
      r["supported_by"][0])
check("carrying the people behind it, not just a direction",
      r["supported_by"][0]["people"] == 55, r["supported_by"][0])
check("the verdict leans toward, and says it is still about other people",
      "leans toward" in r["verdict"] and "not a fact about this one" in r["verdict"],
      r["verdict"])

print("== evidence pointing the other way is found too ==")
db = fresh()
local(db, "works_remotely", "not:prefers_email", 30, 4, 42)
r = _h.weigh(db, "proj", "prefers_email", holds=["works_remotely"])
check("a prior predicting the negation undermines the belief",
      r["undermined_by"] and not r["supported_by"], r)
check("and the verdict says look again rather than declaring it false",
      "leans against" in r["verdict"] and "not a finding that it is false" in r["verdict"],
      r["verdict"])

print("== and when both point at once, it settles nothing ==")
db = fresh()
local(db, "prefers_async", "prefers_email", 40, 6, 55)
local(db, "works_remotely", "not:prefers_email", 30, 4, 42)
r = _h.weigh(db, "proj", "prefers_email",
             holds=["prefers_async", "works_remotely"])
check("both sides are returned", r["supported_by"] and r["undermined_by"], r)
check("and the verdict declines to pick one",
      "divided" in r["verdict"] and "should not settle anything" in r["verdict"],
      r["verdict"])

print("== silence is reported as silence, not as refutation ==")
db = fresh()
local(db, "prefers_async", "prefers_email", 40, 6, 55)
r = _h.weigh(db, "proj", "likes_dogs", holds=["prefers_async"])
check("nothing either way is stated as nothing either way",
      r["checked"] and not r["supported_by"] and not r["undermined_by"], r)
check("and explicitly is not evidence the belief is wrong",
      "not evidence the belief is wrong" in r["verdict"], r["verdict"])

print("== it refuses rather than guessing at the question ==")
check("no claim: refused", _h.weigh(db, "proj", "")["checked"] is False)
r = _h.weigh(db, "proj", "prefers_email")
check("no context about the person: refused, and it says what to supply",
      r["checked"] is False and "holds" in r["refused"], r.get("refused"))

print("== it never rules on the claim ==")
db = fresh()
local(db, "prefers_async", "prefers_email", 900, 2, 1200)
r = _h.weigh(db, "proj", "prefers_email", holds=["prefers_async"])
blob = repr(r).lower()
check("even on overwhelming evidence there is no true, no false, no verdict "
      "of holds", not any(k in blob for k in ('"true"', '"false"', "believed_true")),
      blob[:120])
check("the answer is evidence, not a decision",
      set(r) >= {"supported_by", "undermined_by", "verdict"}, sorted(r))
check("and it says the person outranks all of it",
      "the person wins" in r["how_to_read"], r["how_to_read"][-60:])

print("\n%d passed, %d failed" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)
