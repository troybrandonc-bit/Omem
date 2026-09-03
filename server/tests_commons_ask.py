"""The commons can be asked a question, and can decline to answer one.
Run: python3 tests_commons_ask.py

The bank had four doors and all of them were bulk: an agent wanting one
regularity had to fetch the whole corpus. That is the difference between a
dataset, which you download and hold, and a bureau, which you consult at the
moment you are deciding about someone.

Two properties make the difference worth anything, and both are tested here.

EVERY ANSWER CARRIES WHAT IT RESTS ON. How many people, how many separate
installations, the rate, the lower bound of the rate, and what the counts
actually were. An answer without its evidence is a number a caller has to take
on trust, and nothing in this project asks anyone to do that.

AND IT REFUSES. A question the bank cannot support gets a stated refusal with
the reason, never an empty list. An empty list reads as "there is no such
regularity" when the truth is almost always "not enough people have
contributed for this to be worth saying", and a caller acts differently on
each. Getting that wrong would make a young bank look like evidence of
absence, which is the most damaging thing it could do.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import commons as _c  # noqa: E402

PASS = FAIL = 0


def check(n, c, d=""):
    global PASS, FAIL
    if c:
        PASS += 1
        print("  ok  " + n)
    else:
        FAIL += 1
        print("  FAIL " + n + "  " + str(d)[:240])


def row(a, c, support, refute, subjects, sources):
    total = support + refute
    return {"antecedent": a, "consequent": c, "support": support,
            "refute": refute, "subjects": subjects, "sources": sources,
            "rate": round(support / total, 3) if total else 0.0,
            "pattern": "holds %s -> holds %s" % (a, c)}


STRONG = row("prefers_async", "prefers_email_contact", 340, 60, 520, 6)
THIN_PEOPLE = row("prefers_async", "prefers_pdf_invoices", 5, 1, 9, 4)
THIN_SOURCES = row("prefers_async", "prefers_morning_meetings", 90, 20, 140, 1)
OTHER = row("works_remotely", "prefers_email_contact", 200, 30, 300, 5)
ROWS = [STRONG, THIN_PEOPLE, THIN_SOURCES, OTHER]

print("== a question with an answer ==")
r = _c.ask(ROWS, given="prefers_async")
check("it answers", r["answered"] is True, r)
check("and only with the pattern that clears both bars",
      [a["expect"] for a in r["answers"]] == ["prefers_email_contact"],
      [a["expect"] for a in r["answers"]])

a = r["answers"][0]
print("== the answer carries what it rests on ==")
for field in ("people", "held_both", "held_first_denied_second",
              "installations", "rate", "confident_rate"):
    check("it reports %s" % field, field in a, sorted(a))
check("the confident rate is BELOW the raw rate, because a sample can flatter",
      a["confident_rate"] < a["rate"], (a["confident_rate"], a["rate"]))
check("the counts add up to what the sentence claims",
      "of 400 people" in a["says"] and "340 also hold" in a["says"], a["says"])
check("and the licence and terms version travel with it",
      r.get("license") and r.get("terms_version"), sorted(r))
check("with a note that a general pattern yields to the person in front of you",
      "yield" in r.get("how_to_read", ""), r.get("how_to_read", "")[:80])

print("== a question it cannot support is refused, not answered empty ==")
r2 = _c.ask(ROWS, given="likes_dogs")
check("nothing known: refused rather than an empty answer list",
      r2["answered"] is False and r2["answers"] == [] and r2.get("refused"), r2)
check("and the refusal says absence of evidence is not evidence of absence",
      "not a finding that no connection exists" in r2["refused"], r2["refused"])

r3 = _c.ask([THIN_PEOPLE], given="prefers_async")
check("too few people: refused", r3["answered"] is False and r3.get("refused"), r3)
check("and the refusal says how thin, so the caller can judge",
      str(_c.ASK_MIN_SUBJECTS) in r3["refused"], r3["refused"])

r4 = _c.ask([THIN_SOURCES], given="prefers_async")
check("seen in only one installation: refused however many people",
      r4["answered"] is False, r4)
check("because one installation agreeing with itself is not agreement",
      str(_c.ASK_MIN_SOURCES) in r4["refused"], r4["refused"])

r5 = _c.ask(ROWS)
check("a question with no question in it is refused too",
      r5["answered"] is False and "ask what" in r5["refused"], r5)

print("== it can be asked the other way round ==")
r6 = _c.ask(ROWS, expect="prefers_email_contact")
check("asking what predicts a claim returns every strong antecedent",
      r6["answered"] and sorted(x["given"] for x in r6["answers"])
      == ["prefers_async", "works_remotely"],
      [x["given"] for x in r6["answers"]])
r7 = _c.ask(ROWS, given="prefers_async", expect="prefers_email_contact")
check("and both together narrow to the one pair",
      r7["answered"] and len(r7["answers"]) == 1, r7["answers"])

print("== the ordering and the limit ==")
many = [row("a_%d" % i, "prefers_email_contact", 100 + i, 10, 200 + i * 10, 3)
        for i in range(30)]
r8 = _c.ask(many, expect="prefers_email_contact", limit=5)
check("a limit is honoured", len(r8["answers"]) == 5, len(r8["answers"]))
check("and the best-evidenced come first",
      r8["answers"][0]["people"] >= r8["answers"][-1]["people"],
      [x["people"] for x in r8["answers"]])

print("== nothing that names a person can be asked about, or answered with ==")
check("an identifying token is not in the lexicon and so never in the bank",
      not _c.lexicon_ok("person:sam") and not _c.lexicon_ok("rel_works_at_acme"))
check("and a negated behaviour still is, so the bank can answer about what "
      "people tend not to do", _c.lexicon_ok("not:prefers_email_contact"))

print("\n%d passed, %d failed" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)
