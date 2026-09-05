"""A release is a corpus somebody else can recompute, or it is a download.
Run: python3 tests_commons_release.py

The dataset endpoint answers from the live bank, so the file a consumer pulled
last month could not be reproduced or checked today. For a corpus that asks to
be trained on, that is the whole problem: nothing distinguishes a genuine
aggregate from one edited afterwards, and this project's answer to everybody
else is that a claim nobody can check is an adjective.

These tests hold the release to the property that makes it worth publishing:
given the manifest and the contributions it names, an independent party
rebuilds the same bytes, and every way of getting different bytes is reported
as the specific thing that differs rather than as a mismatch.
"""
import copy
import json
import os
import sqlite3
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
TMP = os.environ.get("TEMP") or "/tmp"
DB = os.path.join(TMP, "omem_commons_release.db")
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


def pat(a, c, s, r, n):
    return {"antecedent": a, "consequent": c, "support": s, "refute": r,
            "subjects": n}


# Two installs that have seen overlapping behaviour, so the merge has something
# to do and the floor has something to exclude.
A = [pat("prefers_morning_meetings", "prefers_email_contact", 9, 1, 12),
     pat("prefers_async_docs", "prefers_email_contact", 7, 2, 10),
     pat("prefers_short_meetings", "avoids_long_reviews", 2, 0, 3)]
B = [pat("prefers_morning_meetings", "prefers_email_contact", 6, 3, 11),
     pat("prefers_async_docs", "avoids_long_reviews", 8, 1, 9)]

for inst, pats in (("a" * 16, A), ("b" * 16, B)):
    clean, err = commons.validate({"instance": inst, "patterns": pats})
    assert err is None, err
    commons.store(con, inst, clean)
con.commit()

print("== a release describes itself ==")
rel = commons.release(con, at="2026-09-05T00:00:00Z")
m = rel["manifest"]
check("it names the specification it follows", m["spec"] == "commons-release/1")
check("it is dated", m["built_at"] == "2026-09-05T00:00:00Z")
check("it counts its contributors", m["contributors"] == 2, m["contributors"])
check("it carries a digest of the corpus",
      m["dataset_digest"].startswith("sha256:") and len(m["dataset_digest"]) == 71,
      m["dataset_digest"])
check("it names every contribution with its own digest",
      len(m["contributions"]) == 2
      and all(c["digest"].startswith("sha256:") for c in m["contributions"]))
check("it pins the code that aggregated it",
      m["aggregation"] == commons.aggregation_version())
check("it pins the floor and the vocabulary",
      m["floor"] == commons.PRIOR_FLOOR_N
      and m["lexicon_words"] == len(commons.COMMONS_LEXICON))
check("the corpus is not empty", m["rows"] > 0, m["rows"])

print("\n== an independent party rebuilds the same bytes ==")
ok, why = commons.verify_release(m, rel["contributions"], rel["jsonl"])
check("the release verifies against its own contributions", ok, why)

again = commons.release(con, at="2026-09-05T00:00:00Z")
check("building it twice produces the same manifest",
      again["manifest"] == m)
check("and the same corpus, byte for byte", again["jsonl"] == rel["jsonl"])

# The order a database happens to return rows in must not reach the file.
shuffled = list(reversed(rel["contributions"]))
ok, why = commons.verify_release(m, shuffled, rel["jsonl"])
check("the order the contributions arrive in does not change the result",
      ok, why)

print("\n== every way of differing is reported as what differs ==")
tampered = rel["jsonl"].replace("prefers_email_contact", "prefers_phone_contact", 1)
ok, why = commons.verify_release(m, rel["contributions"], tampered)
check("an edited corpus is caught",
      not ok and any("not the corpus the manifest describes" in p for p in why),
      why)

bad = copy.deepcopy(rel["contributions"])
bad[0]["patterns"][0]["support"] += 1
ok, why = commons.verify_release(m, bad, rel["jsonl"])
check("an edited contribution is caught, and named",
      not ok and any("does not match its digest" in p for p in why), why)

ok, why = commons.verify_release(m, rel["contributions"][:1], rel["jsonl"])
check("a contribution the manifest names and nobody supplied is caught",
      not ok and any("which is not here" in p for p in why), why)

extra = rel["contributions"] + [{"instance": "c" * 16, "received": 0,
                                 "patterns": [], "digest": "sha256:" + "0" * 64}]
ok, why = commons.verify_release(m, extra, rel["jsonl"])
check("a contribution supplied that the manifest does not name is caught",
      not ok and any("not in the manifest" in p for p in why), why)

wrong_spec = dict(m, spec="something-else/9")
ok, why = commons.verify_release(wrong_spec, rel["contributions"], rel["jsonl"])
check("a manifest of some other kind is refused rather than guessed at",
      not ok and any("not commons-release/1" in p for p in why), why)

print("\n== a changed build says so, instead of crying tamper ==")
# The most dangerous failure here is a true difference reported as fraud. If
# the aggregation changes, a rebuilt corpus legitimately differs, and a reader
# has to be told which of the two it is looking at.
old = dict(m, aggregation="0123456789abcdef")
ok, why = commons.verify_release(old, rel["contributions"], rel["jsonl"])
check("a different aggregation version is reported as a different build",
      not ok and any("aggregates differently" in p
                     and "not evidence of tampering" in p for p in why), why)

floor = commons.PRIOR_FLOOR_N
try:
    commons.PRIOR_FLOOR_N = floor + 100
    check("moving the floor changes the aggregation version",
          commons.aggregation_version() != m["aggregation"])
finally:
    commons.PRIOR_FLOOR_N = floor
check("and restoring it restores the version",
      commons.aggregation_version() == m["aggregation"])

print("\n== withdrawal is forward acting, and visible ==")
commons.withdraw(con, "b" * 16)
con.commit()
after = commons.release(con, at="2026-09-06T00:00:00Z")
check("a withdrawn contributor is absent from the next release",
      [c["instance"] for c in after["manifest"]["contributions"]] == ["a" * 16],
      after["manifest"]["contributions"])
check("and the corpus is rebuilt without them",
      after["manifest"]["dataset_digest"] != m["dataset_digest"])
ok, why = commons.verify_release(after["manifest"], after["contributions"],
                                 after["jsonl"])
check("the later release verifies on its own terms", ok, why)
check("the earlier release still verifies, because it was published",
      commons.verify_release(m, rel["contributions"], rel["jsonl"])[0])

print("\n== nothing identifying rides along ==")
# The reason contributions can be republished for verification at all is that
# they hold counts and no facts about people. That has to stay true of the
# manifest too, which is the new file leaving the machine.
blob = json.dumps(after["manifest"]) + json.dumps(after["contributions"])
words = set()
for c in after["contributions"]:
    for p in c["patterns"]:
        words.update(p["antecedent"].split("_"))
        words.update(p["consequent"].split("_"))
check("every word in every published token is in the fixed vocabulary",
      all(w in commons.COMMONS_LEXICON for w in words),
      sorted(w for w in words if w not in commons.COMMONS_LEXICON))
check("a contribution carries counts and tokens and nothing else",
      all(set(p) == {"antecedent", "consequent", "support", "refute", "subjects"}
          for c in after["contributions"] for p in c["patterns"]))
check("the manifest publishes digests rather than the contributions",
      all(set(c) == {"instance", "patterns", "digest"}
          for c in after["manifest"]["contributions"]))

print("\n%d passed, %d failed" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)
