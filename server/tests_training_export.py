"""Training data with provenance, and the recall that makes it safe.
Run: python3 tests_training_export.py

The export is the easy half. The half that matters is `--check`: an export
whose supporting beliefs have since been retracted is not a corrupt file, it
is a correct record of what was true when it was written, and something has to
say so before an adapter is trained on it.

Driven against a fake client rather than a live server, because the property
under test is the bookkeeping, not the transport.
"""
import io
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "scripts"))

import export_training as ex  # noqa: E402

PASS = FAIL = 0


def check(n, c, d=""):
    global PASS, FAIL
    if c:
        PASS += 1
        print("  ok  " + n)
    else:
        FAIL += 1
        print("  FAIL " + n + "  " + str(d)[:220])


class Fake:
    """A server that answers /v1/memory/expectations and nothing else."""

    def __init__(self, supported, refuted):
        self.rows = {"supported": supported, "refuted": refuted}

    def get(self, path):
        for label in ("supported", "refuted"):
            if path.endswith("status=" + label):
                return {"data": self.rows[label]}
        return {"_error": 404, "_body": "no"}


def hyp(hid, subject, prop, generator, strength=0.35, decided=1_700_000_000):
    return {"id": hid, "subject": subject, "proposition": prop,
            "generator": generator, "strength": strength,
            "because": "because", "born_from": "a_" + hid, "decided": decided}


print("== the export ==")
c = Fake([hyp("h1", "alice", "prefers_email", "person:bob"),
          hyp("h2", "carol", "wants_pdf", "prior:p9")],
         [hyp("h3", "dave", "uses_mobile", "person:erin")])
rows = ex.collect(c)
check("every decided hypothesis becomes one example", len(rows) == 3, rows)
check("labels come from the verdict, not from the strength",
      sorted(r["label"] for r in rows) == ["refuted", "supported", "supported"], rows)
check("the forecast is exported as it was made, for calibrator training",
      all(r["strength"] == 0.35 for r in rows), rows)
check("every example names the belief it was born from",
      all(r["born_from"] for r in rows), rows)

print("== the generator never travels, only its class ==")
classes = {r["generator_class"] for r in rows}
check("a look-alike projection exports as a class",
      "neighbour" in classes and "prior" in classes, classes)
check("no subject id leaks through the generator field",
      not any("person:" in json.dumps(r) for r in rows), rows)

print("== recall: an export that has stopped being true ==")
tmp = os.path.join(tempfile.gettempdir(), "omem_train_export.jsonl")
with open(tmp, "w", encoding="utf-8") as f:
    for r in rows:
        f.write(json.dumps(r, sort_keys=True) + "\n")

# Nothing changed.
buf, sys.stdout = sys.stdout, io.StringIO()
rc = ex.check(c, tmp)
out, sys.stdout = sys.stdout.getvalue(), buf
check("an unchanged export passes", rc == 0, out[-200:])
check("and says every example still stands", "still rests" in out, out[-200:])

# h1's supporting belief was retracted: the hypothesis is no longer decided.
gone = Fake([hyp("h2", "carol", "wants_pdf", "prior:p9")],
            [hyp("h3", "dave", "uses_mobile", "person:erin")])
buf, sys.stdout = sys.stdout, io.StringIO()
rc = ex.check(gone, tmp)
out, sys.stdout = sys.stdout.getvalue(), buf
check("a retracted premise fails the check", rc == 1, out[-300:])
check("the contaminated example is named", "h1" in out, out[-400:])
check("the report explains that the file is not corrupt, it is stale",
      "correct" in out and "contaminated" in out, out[-400:])

# Reality changed its mind about h3.
flipped = Fake([hyp("h1", "alice", "prefers_email", "person:bob"),
                hyp("h2", "carol", "wants_pdf", "prior:p9"),
                hyp("h3", "dave", "uses_mobile", "person:erin")], [])
buf, sys.stdout = sys.stdout, io.StringIO()
rc = ex.check(flipped, tmp)
out, sys.stdout = sys.stdout.getvalue(), buf
check("a relabelled example fails the check too", rc == 1, out[-300:])
check("and the direction of the change is reported",
      "refuted -> supported" in out, out[-300:])

os.remove(tmp)
print("\n%d passed, %d failed" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)
