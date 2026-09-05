"""The other door into the commons, and the two ways it could poison it.
Run: python3 tests_commons_contribute.py

scripts/commons_contribute.py exists so that somebody who has behavioural data
and no interest in OMEM can still contribute to the bank. It is meant to be
downloaded on its own, so it restates the vocabulary, the identity refusal and
the acceptance bar rather than importing them. That is only defensible if the
copy and the original agree, and the way to know is to run both, not to read
both.

Two failure modes are worth more than the rest.

  A TOOL THAT SENDS WHAT AN OMEM INSTALL WOULD NOT. The bank's value is that
  every count in it cleared the same bar. A contributor tool with a lower bar
  is not a wider door, it is a way to fill the commons with popular
  consequents wearing an antecedent as a hat, contributed in good faith by
  somebody who never saw the rule they were below. So the floor, the rate and
  the lift test are checked against the server's constants and against a
  population built to pass two of the three.

  A TOOL THAT LEAKS THE THING THE BANK PROMISES NOT TO HOLD. Contributors
  label their own subjects, and a label is the one field in this tool that
  comes from a person's real records. It is used to count people and then
  discarded, and this asserts that by feeding it labels that are email
  addresses and names and searching the payload for them.

The third thing checked is the identity file, which looks like a convenience
and is not. The collector requires a pooled pattern to have been seen by more
than one source, and a contributor who sends under a fresh id every run
satisfies that alone.

Copyright 2026 Michael Brandon Clifford. MIT licensed.
"""
import io
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, ".."))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import commons                    # noqa: E402
import hypotheses                 # noqa: E402
import commons_contribute as cc   # noqa: E402

TOOL = os.path.join(ROOT, "scripts", "commons_contribute.py")
# The tool keeps a contributor id beside itself by default, which is right for a
# contributor and wrong for a test run: the first version of this file left one
# in server/, and it would have been committed.
IDENT = os.path.join(tempfile.mkdtemp(prefix="commons-test-"), ".id")
PASS = FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  ok  " + name)
    else:
        FAIL += 1
        print("  FAIL " + name + "  " + str(detail)[:300])


def refuses(name, fn):
    try:
        fn()
        check(name, False, "it was accepted")
        return ""
    except cc.Refused as e:
        check(name, True)
        return str(e)
    except Exception as e:                                    # noqa: BLE001
        check(name, False, "raised %s instead of Refused: %s"
              % (type(e).__name__, e))
        return ""


print("the copy has not drifted from what it copied")
# Every value the tool restates, against the module it restated it from. A
# contributor holding an older copy is a version skew the collector survives;
# a contributor holding a copy that disagrees with the collector is a stream of
# refusals nobody here would see.
for attr, mod in (("PRIOR_FLOOR_N", hypotheses), ("PRIOR_MIN_RATE", hypotheses),
                  ("PRIOR_MIN_LIFT", hypotheses), ("PRIOR_LIFT_Z", hypotheses),
                  ("MAX_PATTERNS", commons), ("TERMS_VERSION", commons),
                  ("FRAME_DOMAINS", commons), ("FRAME_REGIONS", commons),
                  ("DEFAULT_COMMONS_URL", commons),
                  ("COMMONS_LEXICON", commons)):
    check("%s agrees with %s" % (attr, mod.__name__),
          getattr(cc, attr) == getattr(mod, attr),
          "%r vs %r" % (getattr(cc, attr), getattr(mod, attr)))

check("the terms it prints are the terms it sends under",
      cc.TERMS_SUMMARY.split(".")[0].strip()
      in commons.TERMS[commons.TERMS_VERSION]["summary"],
      cc.TERMS_SUMMARY[:80])

print("\nthe three copied functions answer as the originals do")
TOKENS = ["prefers_email", "not:prefers_email", "rel_works_at_acme",
          "person:sam", "pays_late_2024", "John_Smith", "john@acme.com",
          "not:person:sam", "", "a" * 70, "prefers_pdf_documents",
          "johnsmith_of_acmecorp", "prefers_smoke_signals", "not:renews",
          "acme.com", "PREFERS_EMAIL", "prefers__email", "not:not:renews"]
same = [t for t in TOKENS
        if cc._identifying(t) == hypotheses._identifying(t)]
check("_identifying agrees on every token tried", len(same) == len(TOKENS),
      [t for t in TOKENS if t not in same])
same = [t for t in TOKENS if cc.foreign_word(t) == commons._foreign_word(t)]
check("foreign_word agrees on every token tried", len(same) == len(TOKENS),
      [t for t in TOKENS if t not in same])
check("lexicon_ok would agree too",
      all(commons.lexicon_ok(t)
          == (not cc._identifying(t) and cc.foreign_word(t) is None
              and bool(t) and len(t) <= 64)
          for t in TOKENS))
check("wilson_lower agrees to the last decimal place",
      all(abs(cc.wilson_lower(k, n) - hypotheses._wilson_lower(k, n)) < 1e-12
          for n in range(1, 60) for k in range(n + 1)))
check("band_of agrees at every boundary",
      all(cc.band_of(n) == commons.band_of(n)
          for n in (0, 1, 9, 10, 11, 49, 50, 199, 200, 999, 1000, 100000)))
check("and the bands it can produce are the bands the collector accepts",
      {cc.band_of(n) for n in (10, 50, 200, 1000)} == set(commons.FRAME_BANDS))

print("\nit refuses at the observation, not at the payload")
c = cc.Contribution("customer_support", "europe")
msg = refuses("a word outside the vocabulary",
              lambda: c.observe("s1", "prefers_smoke_signals"))
check("and the refusal names the WORD, which is the thing to change",
      "'smoke'" in msg, msg[:160])
check("and says where to look for a replacement", "--words" in msg, msg[:200])
refuses("a token carrying an entity id", lambda: c.observe("s1", "person:sam"))
refuses("a token carrying a value", lambda: c.observe("s1", "pays_late_2024"))
refuses("a relation token", lambda: c.observe("s1", "rel_works_at_acme"))
refuses("an email dressed as a behaviour",
        lambda: c.observe("s1", "john@acme.com"))
refuses("a subject with no label", lambda: c.observe("", "renews"))
refuses("a domain outside the closed list",
        lambda: cc.Contribution("insurance", "europe"))
refuses("a country where a macro-region belongs",
        lambda: cc.Contribution("sales", "ireland"))

c2 = cc.Contribution()
c2.observe("s1", "renews")
msg = refuses("one person holding a thing and its negation",
              lambda: c2.observe("s1", "not:renews"))
check("and the refusal says why that corrupts the counts rather than one row",
      "support" in msg and "refut" in msg, msg[:160])

print("\nit will not send what an OMEM install would not have sent")
# A population where `renews` is held by almost everybody. Any antecedent
# therefore "predicts" it at a high rate, and without the lift test the bank
# would fill with that. `prefers_email` genuinely predicts `pays_monthly`.
pop = cc.Contribution("software", "europe", IDENT)
for i in range(40):
    s = "p%d" % i
    pop.observe(s, "renews")                      # 40 of 40: pure popularity
    if i < 20:
        pop.observe(s, "prefers_email", "pays_monthly")
    else:
        pop.observe(s, "not:prefers_email")
        pop.observe(s, "pays_monthly" if i < 24 else "not:pays_monthly")
pats = pop.patterns()
by = {(r["antecedent"], r["consequent"]): r for r in pats}
check("a real regularity is kept",
      ("prefers_email", "pays_monthly") in by, sorted(by)[:6])
check("a consequent that is merely popular is not",
      not any(c == "renews" for _, c in by),
      [k for k in by if k[1] == "renews"])
check("the counts are the ones a hand count gives",
      by[("prefers_email", "pays_monthly")]["support"] == 20
      and by[("prefers_email", "pays_monthly")]["refute"] == 0
      and by[("prefers_email", "pays_monthly")]["subjects"] == 20,
      by.get(("prefers_email", "pays_monthly")))
check("nothing predicts itself or its own negation",
      not any(a.replace("not:", "") == q.replace("not:", "")
              for a, q in by))
check("every emitted pattern clears the floor",
      all(r["support"] >= hypotheses.PRIOR_FLOOR_N for r in pats))
check("every emitted pattern clears the rate",
      all(r["support"] / (r["support"] + r["refute"])
          >= hypotheses.PRIOR_MIN_RATE for r in pats))
check("support and refutation never exceed the people who held the antecedent",
      all(r["support"] + r["refute"] <= r["subjects"] for r in pats))
check("silence was not counted as either",
      by[("prefers_email", "pays_monthly")]["subjects"] == 20)

thin = cc.Contribution()
for i in range(2):
    thin.observe("t%d" % i, "renews", "pays_monthly")
msg = refuses("a population too thin to say anything", thin.payload)
check("and it says that is the tool working rather than an error",
      "worse than a small one" in msg, msg[:200])

print("\nthe collector accepts what it produces, unchanged")
body = pop.payload()
clean, err = commons.validate(body)
check("validate raises nothing", err is None, err)
check("and drops nothing", len(clean) == len(body["patterns"]),
      "%d of %d survived" % (len(clean), len(body["patterns"])))
check("the patterns are byte-identical after the door",
      clean == body["patterns"])
cal, cerr = commons.validate_calibration(body)
check("the empty calibration is accepted", cerr is None and cal == [], cerr)
terms, terr = commons.validate_terms(body)
check("the terms are accepted", terr is None and terms, terr)
check("and grant the public commons and nothing else",
      commons.grants_of(body["terms"]) == {"public_commons"},
      commons.grants_of(body["terms"]))
frame, ferr = commons.validate_frame(body.get("frame"))
check("the frame is accepted", ferr is None and frame, ferr)
check("and counts as a real population shape rather than an undeclared one",
      commons.frame_key(body["frame"]) != "", body.get("frame"))

check("the payload carries exactly the fields the collector states",
      set(body) == set(commons.CONTRIBUTION_FIELDS),
      sorted(set(body) ^ set(commons.CONTRIBUTION_FIELDS)))
check("every pattern carries exactly the stated pattern fields",
      all(set(p) == set(commons.PATTERN_FIELDS) for p in body["patterns"]))
check("the frame carries exactly the stated frame fields",
      set(body["frame"]) == set(commons.FRAME_FIELDS))
check("and none of the fields the local bank keeps to itself travelled",
      not any(k in p for p in body["patterns"]
              for k in commons.DERIVED_LOCAL_ONLY))

print("\nthe subject labels do not leave the machine")
# The one field in this tool that comes from somebody's real records. It is
# used to count people and then discarded, and asserting that is worth more
# than saying it in a docstring.
leaky = cc.Contribution("healthcare", "americas", IDENT)
SECRETS = ["sam.okonkwo@stmartins.example", "Ruth Alvarez", "NHS-8842-Q",
           "patient/00119", "acme corp ltd"]
for i in range(30):
    s = SECRETS[i % len(SECRETS)] + "#%d" % i
    if i < 15:
        leaky.observe(s, "attends_weekly", "prefers_reminder_message")
    else:
        leaky.observe(s, "not:attends_weekly")
        leaky.observe(s, "prefers_reminder_message" if i < 18
                      else "not:prefers_reminder_message")
blob = json.dumps(leaky.payload())
check("no subject label survives into the payload",
      not any(x.lower() in blob.lower() for x in SECRETS),
      [x for x in SECRETS if x.lower() in blob.lower()])
check("nor does any count reveal how many labels there were",
      "#" not in blob and "@" not in blob)
check("the payload is counts and vocabulary only",
      commons.validate(leaky.payload())[1] is None)

print("\nthe contributor id is stable, and refuses to be otherwise")
with tempfile.TemporaryDirectory() as d:
    p = os.path.join(d, ".commons-instance")
    a = cc.instance_id(p)
    b = cc.instance_id(p)
    check("a second run reuses the first run's id", a == b, (a, b))
    check("and it is opaque, carrying nothing about the machine",
          len(a) == 36 and a.replace("-", "").isalnum(), a)
    check("the collector accepts it as an instance",
          commons.validate({"instance": a, "patterns": []})[1] is None)
    io.open(p, "w", encoding="utf-8").write("nope!\n")
    check("a corrupted id file is replaced rather than sent",
          cc.instance_id(p) != "nope!")
    msg = refuses("an unwritable identity path, rather than a throwaway id",
                  lambda: cc.instance_id(os.path.join(p, "no", "such", "dir")))
    check("and the refusal explains why a fresh id per run is the harm",
          "independence" in msg, msg[:200])
    check("which is the same requirement the collector enforces",
          commons.POOLED_MIN_SOURCES >= 2, commons.POOLED_MIN_SOURCES)

print("\nit runs as a program, for somebody who will not read the module")
with tempfile.TemporaryDirectory() as d:
    csvp = os.path.join(d, "obs.csv")
    with io.open(csvp, "w", encoding="utf-8") as f:
        f.write("subject,token\n")
        for i in range(40):
            f.write("c%d,renews\n" % i)
            if i < 20:
                f.write("c%d,prefers_email\nc%d,pays_monthly\n" % (i, i))
            else:
                f.write("c%d,not:prefers_email\n" % i)
                f.write("c%d,%s\n" % (i, "pays_monthly" if i < 24
                                      else "not:pays_monthly"))
    out = os.path.join(d, "payload.json")
    r = subprocess.run(
        [sys.executable, TOOL, csvp, "--domain", "software",
         "--region", "europe", "--identity", os.path.join(d, ".id"),
         "--out", out], capture_output=True, text=True)
    check("it exits cleanly", r.returncode == 0, (r.stderr or r.stdout)[-300:])
    check("it says how many people it read", "40 people" in r.stdout, r.stdout)
    check("it shows what is about to be sent before sending anything",
          "prefers_email" in r.stdout and "-> " in r.stdout, r.stdout[-300:])
    check("it does not send unless asked",
          "Nothing was sent" in r.stdout or "written to" in r.stdout)
    wrote = json.load(io.open(out, encoding="utf-8"))
    check("what it wrote is what the collector takes",
          commons.validate(wrote)[1] is None, commons.validate(wrote)[1])
    check("and matches what the module produces from the same file",
          [(p["antecedent"], p["consequent"], p["support"])
           for p in wrote["patterns"]]
          == [(p["antecedent"], p["consequent"], p["support"])
              for p in pop.patterns()])

    bad = os.path.join(d, "bad.csv")
    io.open(bad, "w", encoding="utf-8").write("c1,prefers_smoke_signals\n")
    r = subprocess.run([sys.executable, TOOL, bad, "--identity",
                        os.path.join(d, ".id")], capture_output=True, text=True)
    check("a bad token fails the program rather than shipping a partial one",
          r.returncode == 1 and "smoke" in r.stderr, (r.stderr or r.stdout)[:200])
    check("and the line number is in the message", "line 1" in r.stderr,
          r.stderr[:200])

r = subprocess.run([sys.executable, TOOL, "--words", "email"],
                   capture_output=True, text=True)
check("the vocabulary can be searched, since it is the first thing anyone hits",
      r.returncode == 0 and "email" in r.stdout, r.stdout[:200])
r = subprocess.run([sys.executable, TOOL, "--words", "telepathy"],
                   capture_output=True, text=True)
check("and a miss says a contributor cannot extend it locally",
      "pull request" in r.stdout, r.stdout[:200])

check("and a run leaves no contributor id beside the code",
      not os.path.exists(os.path.join(HERE, ".commons-instance"))
      and not os.path.exists(os.path.join(ROOT, ".commons-instance")),
      "a test run wrote a contributor id into the repository")

print("\nit needs nothing from this repository")
src = io.open(TOOL, encoding="utf-8").read()
check("no import reaches back into the server",
      not any(("import " + m) in src
              for m in ("commons", "hypotheses", "api", "omem")), TOOL)
check("and none of it is third-party",
      not any(("import " + m) in src for m in ("requests", "numpy", "pandas")))

print("\n%d passed, %d failed" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)
