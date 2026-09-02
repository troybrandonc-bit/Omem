"""Two promises the mission rests on, made checkable.
Run: python3 tests_commons_guards.py

The site says OMEM teaches AI what people are like while holding a fact about
no one, and that only installs which opt in contribute anything. Both were
architecture arguments. An argument is not a proof, and this project's own
rule is that a claim with no test is opinion.

WHAT MAY LEAVE. The existing doors validate what ARRIVES, and nothing pinned
what departs. That is precisely the gap the calibration work walked into:
`leap_generators.generator` holds subject ids, the design proposed
contributing that table, and both doors would have passed it because they
inspect proposition tokens rather than that column. So a field now travels
only if it appears in a map with a sentence saying why it is safe, rows are
projected onto those fields before sending, and this suite fails if the local
bank grows a key that is in neither the sent map nor the deliberately-local
one. A new column becomes a decision instead of a default.

WHEN IT MAY LEAVE. "No answer, or no: no network call exists" was a comment
above an inline condition. It is now a named rule with a truth table, and the
suite drives the real export path with a recording stub in place of the
network to prove that an install which never answered contacts nobody.
"""
import io
import json
import os
import sqlite3
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

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


print("== every field that travels has a written argument ==")
for name, fields in (("contribution", commons.CONTRIBUTION_FIELDS),
                     ("pattern", commons.PATTERN_FIELDS),
                     ("calibration", commons.CALIBRATION_FIELDS)):
    check(f"every {name} field carries a reason, not just a name",
          all(isinstance(v, str) and len(v) > 20 for v in fields.values()),
          {k: v for k, v in fields.items() if not (isinstance(v, str) and len(v) > 20)})

TERMS = {"version": commons.TERMS_VERSION, "granted": ["public_commons"]}
body = commons.contribution_payload("i" * 16, [], [], TERMS)
check("the payload has exactly the approved top-level fields",
      set(body) == set(commons.CONTRIBUTION_FIELDS), sorted(body))

print("== a column added upstream cannot travel by accident ==")
# The shape of the leak that nearly shipped: a field appears on a local row
# and rides along because nothing was looking at the outgoing side.
leaky = [{"antecedent": "prefers_async", "consequent": "works_remotely",
          "support": 5, "refute": 1, "subjects": 6,
          "generator": "person:alice@corp.example"}]
sent = commons.contribution_payload("i" * 16, leaky, [], TERMS)
check("the subject id is not in what would be sent",
      "generator" not in sent["patterns"][0], sent["patterns"][0])
check("and nothing outside the approved pattern fields is either",
      set(sent["patterns"][0]) <= set(commons.PATTERN_FIELDS), sent["patterns"][0])
check("the counts that were argued for do survive",
      sent["patterns"][0]["support"] == 5 and sent["patterns"][0]["subjects"] == 6)
leaky_cal = [{"scope": "generator_class", "name": "prior", "supported": 4,
              "refuted": 1, "generator": "person:bob@corp.example"}]
sent2 = commons.contribution_payload("i" * 16, [], leaky_cal, TERMS)
check("the same holds for a calibration row",
      set(sent2["calibration"][0]) <= set(commons.CALIBRATION_FIELDS),
      sent2["calibration"][0])
check("a whole serialised contribution contains no such value anywhere",
      "corp.example" not in json.dumps(
          commons.contribution_payload("i" * 16, leaky, leaky_cal, TERMS)))

print("== the local bank cannot grow a field nobody argued about ==")
# The CI half. Projection stops a new column travelling; this is what makes
# someone notice it exists, which is the part that failed last time.
db = sqlite3.connect(":memory:")
db.row_factory = sqlite3.Row
db.executescript(_h.HYPOTHESES_SCHEMA)
for i, (a, c) in enumerate((("prefers_async", "works_remotely"),
                            ("works_remotely", "wants_pdf_invoices"))):
    db.execute("INSERT INTO priors VALUES(?,'proj',?,?,'ctx',9,1,10,0)",
               ("pr_%d" % i, a, c))
db.execute("INSERT INTO leap_generators(project_id, generator, wins, losses) "
           "VALUES('proj','prior:pr_0',4,1)")
for hid, prop, st in (("h1", "wants_pdf", "supported"), ("h2", "wants_pdf", "refuted"),
                      ("h3", "wants_pdf", "supported")):
    db.execute("INSERT INTO hypotheses VALUES(?,'proj','s',?,'b','g','c',0.4,?,"
               "'{}',0,?,0,0)", (hid, prop, st, hid))
db.commit()

known_pattern = set(commons.PATTERN_FIELDS) | commons.DERIVED_LOCAL_ONLY
for row in _h.bank(db, ["proj"]):
    extra = set(row) - known_pattern
    check("bank() emits no field that is neither sent nor documented as local",
          not extra, extra)
    break
known_cal = set(commons.CALIBRATION_FIELDS) | commons.DERIVED_LOCAL_ONLY
for row in _h.calibration_bank(db, ["proj"]):
    extra = set(row) - known_cal
    check("calibration_bank() emits no such field either", not extra, extra)
    break
check("and the two maps do not overlap, so a field is sent or local, never both",
      not (set(commons.PATTERN_FIELDS) & commons.DERIVED_LOCAL_ONLY))

print("== silence is not consent ==")
db2 = sqlite3.connect(":memory:")
db2.row_factory = sqlite3.Row
commons.ensure_schema(db2)
check("an install that has never been asked sends nothing",
      commons.should_contribute(db2, None, False) is False)
commons.set_choice(db2, False)
check("an install that said no sends nothing",
      commons.should_contribute(db2, None, False) is False)
commons.set_choice(db2, True)
check("an install that said yes may send",
      commons.should_contribute(db2, None, False) is True)
check("a collector never contributes to itself, whatever it answered",
      commons.should_contribute(db2, None, True) is False)
db3 = sqlite3.connect(":memory:")
db3.row_factory = sqlite3.Row
commons.ensure_schema(db3)
check("setting the URL is itself the explicit act, so it may send unasked",
      commons.should_contribute(db3, "https://commons.example", False) is True)
check("but not if this instance is the collector",
      commons.should_contribute(db3, "https://commons.example", True) is False)
broken = sqlite3.connect(":memory:")   # no schema at all
check("an unreadable decision is read as no, never as yes",
      commons.should_contribute(broken, None, False) is False)

print("== and the export path really does contact nobody ==")
# Not the rule in isolation: the actual function that writes the bank and
# contributes, with a recorder where the network should be.
os.environ.setdefault("OMEM_TENANT_RL_BURST", "10000")
os.environ.setdefault("OMEM_TENANT_RL_RPS", "10000")
TMP = os.environ.get("TEMP") or "/tmp"
DB = os.path.join(TMP, "omem_guards.db")
if os.path.exists(DB):
    os.remove(DB)
os.environ["OMEM_DB"] = DB
os.environ.pop("OMEM_COMMONS_URL", None)

import urllib.request  # noqa: E402
import api  # noqa: E402

CALLS = []


def _recording_open(req, *a, **k):
    CALLS.append(getattr(req, "full_url", str(req)))

    class _R:
        def read(self):
            return b"{}"

        def __enter__(self):
            return self

        def __exit__(self, *x):
            return False
    return _R()


api.urllib.request.urlopen = _recording_open
dest = tempfile.mkdtemp(prefix="omem_bank_")

api._commons.set_choice(api.STORE.db, False)
CALLS.clear()
api._write_bank_export(dest)
check("an install that said no makes no request at all", CALLS == [], CALLS)
check("and it still wrote the operator's own bank to disk",
      os.path.exists(os.path.join(dest, "intelligence-bank.json")))

api.STORE.db.execute("DELETE FROM commons_meta WHERE k='contribute'")
api.STORE.db.commit()
CALLS.clear()
api._write_bank_export(dest)
check("an install that was never asked makes no request either", CALLS == [], CALLS)

print("== the words match the machine, and cannot go stale ==")
# Numbers in outward-facing copy drift silently, and a stale number in a
# consent dialog or a dataset card is the same defect as a wrong one.
card = commons.dataset_card([], {"stances": 0, "contributors": 0})
check("the card states the real size of the vocabulary",
      str(len(commons.COMMONS_LEXICON)) in card, len(commons.COMMONS_LEXICON))
check("and the real floor a published line clears",
      str(commons.PRIOR_FLOOR_N) in card, commons.PRIOR_FLOOR_N)
check("it does not conclude the law for the reader",
      "not personal data" not in card)
check("it says what the file contains instead",
      "cannot appear at all" in card and "supporting subjects" in card)

# The consent dialog. The commons goes both ways, so an operator told only
# what leaves has not been told what they are agreeing to.
DIALOG = os.path.join(os.path.dirname(HERE), "web", "components", "shell.tsx")
ui = io.open(DIALOG, encoding="utf-8").read() if os.path.exists(DIALOG) else ""
_MARK = chr(10) + "function "
ask = ui.split("function CommonsAsk")[1].split(_MARK)[0] if "function CommonsAsk" in ui else ""
check("the consent dialog is where we think it is", bool(ask), DIALOG)
check("it still says what leaves", "leaves this machine" in ask)
check("it also says what arrives, because the commons goes both ways",
      "pulls the published bank back" in ask)
check("it says borrowed patterns rank beneath local knowledge",
      "rank" in ask and "beneath" in ask)
check("and that one only ever fires into a silence", "silence" in ask)
NUMBER_WORD = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five"}
check("it discloses the threshold before anything comes back, and the number "
      "it names is the one the code enforces",
      NUMBER_WORD[commons.POOLED_MIN_SOURCES] + " separate install" in ask,
      commons.POOLED_MIN_SOURCES)
check("and it does not promise a benefit the benchmark calls conditional",
      "helps most when" in ask and "least when" in ask)

print("\n%d passed, %d failed" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)
