"""A pattern can replicate perfectly and still be about a monoculture.
Run: python3 tests_population_frame.py

POOLED_MIN_SOURCES asks whether more than one machine saw a regularity. It is
the only independence signal the commons had, and it is weak: two installs
serving the same kind of people in the same place are close to one install, and
between them they satisfy it. A bank filled that way would hold facts about
whoever happened to adopt first, published as facts about people.

So a contribution may declare the SHAPE of the population its counts came from
-- a working domain, a macro-region, a size band -- and a pooled row records how
many distinct shapes back it. This suite pins the three things that have to be
true for that to mean anything:

  * the frame describes a deployment and never a person, and is too coarse to
    identify the operator: bands not counts, macro-regions not countries, a
    closed list of domains and nothing else able to travel;
  * declaring nothing is allowed and cannot be gamed, because every undeclared
    frame collapses to the same key rather than counting as a population each;
  * a row backed by one population raises the evidence bar rather than being
    silently treated like a row backed by five.
"""
import os
import sqlite3
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import commons as _c  # noqa: E402
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


print("== a frame is coarse enough not to identify the operator ==")
check("an exact subject count never travels, only a band",
      _c.frame_of(340, "customer_support", "europe")["subjects"] == "200-999",
      _c.frame_of(340, "customer_support", "europe"))
check("band boundaries are where they say they are",
      [_c.band_of(n) for n in (9, 10, 49, 50, 199, 200, 999, 1000)]
      == [None, "10-49", "10-49", "50-199", "50-199", "200-999", "200-999", "1000+"],
      [_c.band_of(n) for n in (9, 10, 49, 50, 199, 200, 999, 1000)])
check("under ten subjects there is no frame at all, rather than a narrow one",
      _c.frame_of(4, "sales", "europe") is None)
check("a domain outside the closed list is not a frame",
      _c.frame_of(340, "acme logistics ltd", "europe") is None)
check("a region outside the closed list is not a frame",
      _c.frame_of(340, "sales", "united kingdom") is None,
      "country granularity must be refused, macro-region only")

print("== nothing but the three stated fields can travel ==")
_, err = _c.validate_frame({"domain": "sales", "region": "europe",
                            "subjects": "50-199", "company": "acme"})
check("an extra key is refused rather than dropped quietly", bool(err), err)
_, err = _c.validate_frame({"domain": "sales", "region": "europe", "subjects": 340})
check("a raw count where a band belongs is refused", bool(err), err)
_, err = _c.validate_frame({"domain": "b2b saas for dentists",
                            "region": "europe", "subjects": "50-199"})
check("free text in the domain is refused", bool(err), err)
check("an absent frame is not an error", _c.validate_frame(None) == (None, None))

body = _c.contribution_payload(
    "i" * 12, [], [], _c.mint_terms(),
    frame={"domain": "sales", "region": "europe", "subjects": "50-199",
           "headcount": 41, "customer": "acme"})
check("the payload projects the frame onto the stated fields, so a key added "
      "upstream cannot travel by accident",
      set(body["frame"]) == {"domain", "region", "subjects"}, body["frame"])
check("and frame is itself a declared contribution field",
      "frame" in _c.CONTRIBUTION_FIELDS)
check("a contribution with no frame carries no frame key at all",
      "frame" not in _c.contribution_payload("i" * 12, [], [], _c.mint_terms()))

print("== declaring nothing is allowed, and cannot be gamed ==")
check("an undeclared frame and an empty one collapse to the same key",
      _c.frame_key(None) == _c.frame_key({}) == "")
check("so does a half-declared one, which is not a new kind of population",
      _c.frame_key({"domain": "sales"}) == "")
check("two different declared frames are two keys",
      _c.frame_key({"domain": "sales", "region": "europe", "subjects": "50-199"})
      != _c.frame_key({"domain": "sales", "region": "asia", "subjects": "50-199"}))

print("== the terms cover what now leaves the machine ==")
check("the version moved when the payload gained a field",
      _c.TERMS_VERSION == "2026-09-03", _c.TERMS_VERSION)
check("and the summary says what the frame is",
      "macro-region" in _c.TERMS[_c.TERMS_VERSION]["summary"])
check("the previous terms are still readable, because a record made under them "
      "was made under them", "2026-09-02" in _c.TERMS)
check("the older grant still resolves and grants no more than it did",
      _c.grants_of({"version": "2026-09-02", "granted": ["public_commons"]})
      == {"public_commons"})

print("== a row that replicated inside one population does not enter the bank ==")
row = {"antecedent": "prefers_async", "consequent": "prefers_email",
       "support": 80, "refute": 4, "subjects": 120, "sources": 6}
ok, err = _c.accept_pooled([dict(row, frames=4)])
check("four populations: accepted", len(ok) == 1 and not err, (ok, err))
ok, err = _c.accept_pooled([dict(row, frames=1)])
check("one population: refused, however many installs agreed",
      ok == [] and not err, (ok, err))
ok, err = _c.accept_pooled([dict(row)])
check("frames not reported at all: accepted, because an older collector is not "
      "a dishonest one", len(ok) == 1, (ok, err))
check("and the accepted row carries the count forward",
      _c.accept_pooled([dict(row, frames=4)])[0][0]["frames"] == 4)

print("== the spread travels, because an average hides the case that matters ==")
ok, _ = _c.accept_pooled([dict(row, frames=4, rate_min=0.21, rate_max=0.94)])
check("min and max rate survive the door",
      (ok[0]["rate_min"], ok[0]["rate_max"]) == (0.21, 0.94), ok[0])
ok, _ = _c.accept_pooled([dict(row, frames=4, rate_min="soon", rate_max=3.5)])
check("a rate that is not a rate becomes absent rather than a number",
      (ok[0]["rate_min"], ok[0]["rate_max"]) == (None, None), ok[0])

print("== an existing database gains the columns rather than breaking ==")
db = sqlite3.connect(":memory:")
db.row_factory = sqlite3.Row
db.executescript("""CREATE TABLE commons_pooled(
  antecedent TEXT NOT NULL, consequent TEXT NOT NULL, support INTEGER NOT NULL,
  refute INTEGER NOT NULL, subjects INTEGER NOT NULL, sources INTEGER NOT NULL,
  received REAL NOT NULL, PRIMARY KEY(antecedent, consequent));""")
_c.ensure_pooled_columns(db)
_c.ensure_pooled_columns(db)          # twice: the migration must be idempotent
cols = {r["name"] for r in db.execute("PRAGMA table_info(commons_pooled)")}
check("frames, rate_min and rate_max are added to a table that predates them",
      {"frames", "rate_min", "rate_max"} <= cols, sorted(cols))
_c.store_pooled(db, [dict(row, frames=3, rate_min=0.4, rate_max=0.8)])
got = _c.pooled(db)
check("and a stored row reads back with all of it",
      len(got) == 1 and got[0]["frames"] == 3 and got[0]["rate_max"] == 0.8, got)
check("the engine reads the frame count through its own SQL",
      _h._pooled_rows(db)[0]["frames"] == 3, _h._pooled_rows(db))

print("== one population raises the bar rather than lowering the answer ==")
k_local = _h.BIRTH_K
k_many = _h._pooled_k({"pooled": True, "frames": 4})
k_one = _h._pooled_k({"pooled": True, "frames": 1})
k_none = _h._pooled_k({"pooled": True})
check("borrowed knowledge already needs more of its own record than local",
      k_many > k_local, (k_local, k_many))
check("and borrowed from one kind of population needs more still",
      k_one > k_many, (k_many, k_one))
check("an undeclared frame is treated as borrowed, not as monoculture, because "
      "not saying is not the same as saying one", k_none == k_many, (k_none, k_many))
check("every one of these is a larger pseudo-count, never a smaller strength: "
      "the bar moves, the ceiling does not",
      all(k >= k_local for k in (k_many, k_one, k_none)))

print("\n%d passed, %d failed" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)
