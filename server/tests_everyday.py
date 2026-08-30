"""Everyday-habit extraction and the intelligence bank's anonymity.
Run: python3 tests_everyday.py

Habits ("mornings work best for me") are the writer's own, so a first-person
sentence must attach to the PERSON who wrote it -- the same node inference
gives their employment -- while "we prefer ..." stays a fact about the company.
And the bank, which merges priors across projects for publication, must refuse
any token that could embed a name, an id, or a value.
"""
import os
import sqlite3
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
TMP = os.environ.get("TEMP") or "/tmp"
DB = os.path.join(TMP, "omem_everyday.db")
if os.path.exists(DB):
    os.remove(DB)
os.environ["OMEM_DB"] = DB

from extraction import ContextualBusinessExtractor  # noqa: E402
import hypotheses  # noqa: E402

PASS = FAIL = 0


def check(n, c, d=""):
    global PASS, FAIL
    if c:
        PASS += 1
        print("  ok  " + n)
    else:
        FAIL += 1
        print("  FAIL " + n + "  " + str(d)[:220])


IDENT = {"emails": ["owner@yourteam.dev"], "domains": ["yourteam.dev"],
         "company_name": "Your Team"}
EXT = ContextualBusinessExtractor(IDENT)


def facts_for(body, sender="Alice Chen <alice.chen@acme.com>"):
    return EXT.extract({"subject": "scheduling", "body": body, "from": sender,
                        "to": "owner@yourteam.dev", "at": "now",
                        "message_id": "m1", "headers": {}})


def habit(body, prop, sender="Alice Chen <alice.chen@acme.com>"):
    return next((f for f in facts_for(body, sender)
                 if f["proposition"] == prop), None)


print("== first-person habits attach to the person who wrote them ==")
CASES = [
    ("Mornings work best for me.", "prefers_morning_meetings"),
    ("Afternoons suit me better for calls.", "prefers_afternoon_meetings"),
    ("Email is the best way to reach me.", "prefers_email_contact"),
    ("Just call me anytime, phone works best for me.", "prefers_phone_contact"),
    ("I prefer keeping things async, no need for a call.", "prefers_async"),
    ("I don't work Fridays.", "unavailable_fridays"),
    ("I usually work from home.", "works_remotely"),
]
for body, prop in CASES:
    f = habit(body, prop)
    check(f"{prop} extracted", f is not None, body)
    if f:
        check(f"{prop} is the WRITER's habit", f["subject"]["id"] == "person:alice_chen@acme",
              f["subject"]["id"])
        check(f"{prop} carries the sentence as evidence",
              body[:30] in (f.get("evidence") or ""), f.get("evidence"))

print("== plural statements stay facts about the company ==")
f = habit("We prefer afternoon meetings on our side.", "prefers_afternoon_meetings")
check("'we prefer ...' attaches to the company",
      f is not None and f["subject"]["id"] == "company:acme",
      f and f["subject"]["id"])

print("== a writer with no person identity falls back, never misattributes ==")
f = habit("Mornings work best for me.", "prefers_morning_meetings",
          sender="support@acme.com")
check("role address: habit does not mint a fake person",
      f is None or not f["subject"]["id"].startswith("person:"),
      f and f["subject"]["id"])

print("== the bank refuses identifying tokens ==")
check("relation props are identifying", hypotheses._identifying("rel_works_at_acme"))
check("raw ids are identifying", hypotheses._identifying("company:acme"))
check("value-bearing props are identifying", hypotheses._identifying("payment_terms_net30"))
check("plain habit props are not", not hypotheses._identifying("prefers_morning_meetings"))

con = sqlite3.connect(DB)
con.row_factory = sqlite3.Row
con.executescript(hypotheses.PRIORS_SCHEMA if hasattr(hypotheses, "PRIORS_SCHEMA") else
                  """CREATE TABLE IF NOT EXISTS priors(
  id TEXT PRIMARY KEY, project_id TEXT NOT NULL,
  antecedent TEXT NOT NULL, consequent TEXT NOT NULL, context TEXT NOT NULL,
  support INTEGER NOT NULL, refute INTEGER NOT NULL, subjects INTEGER NOT NULL,
  updated REAL NOT NULL);""")
rows = [
    ("p1", "projA", "prefers_morning_meetings", "prefers_email_contact", "default", 5, 2, 9, 0.0),
    ("p2", "projB", "prefers_morning_meetings", "prefers_email_contact", "default", 4, 0, 6, 0.0),
    ("p3", "projA", "rel_works_at_acme", "prefers_email_contact", "default", 6, 0, 6, 0.0),
    ("p4", "projA", "payment_terms_net30", "prefers_email_contact", "default", 6, 0, 6, 0.0),
    ("p5", "projB", "prefers_async", "prefers_email_contact", "default", 2, 0, 2, 0.0),
]
con.executemany("INSERT INTO priors VALUES(?,?,?,?,?,?,?,?,?)", rows)
con.commit()
bank = hypotheses.bank(con, ["projA", "projB"])
pats = {(b["antecedent"], b["consequent"]): b for b in bank}
check("bank merges the same pattern across projects",
      pats.get(("prefers_morning_meetings", "prefers_email_contact"), {}).get("support") == 9, bank)
check("merged pattern counts both projects",
      pats.get(("prefers_morning_meetings", "prefers_email_contact"), {}).get("projects") == 2)
check("bank drops the relation prop (it names a company)",
      ("rel_works_at_acme", "prefers_email_contact") not in pats)
check("bank drops the value prop (it carries a number)",
      ("payment_terms_net30", "prefers_email_contact") not in pats)
check("bank keeps the support floor (2 < PRIOR_FLOOR_N)",
      ("prefers_async", "prefers_email_contact") not in pats)
check("no bank row carries a colon, a digit, or rel_",
      all(not hypotheses._identifying(b["antecedent"])
          and not hypotheses._identifying(b["consequent"]) for b in bank))

print("\n%d passed, %d failed" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)
