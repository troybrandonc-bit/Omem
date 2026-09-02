#!/usr/bin/env python3
"""Export OMEM's own verdicts as training data, with provenance and recall.

    python3 scripts/export_training.py --url http://127.0.0.1:8787 \
        --key omem_sk_... --project proj_... > train.jsonl

    python3 scripts/export_training.py --url ... --key ... --project ... \
        --check train.jsonl

THIS IS YOUR DATA, NOT THE COMMONS. Every line names a subject and a claim
about them, because that is what makes it useful for training. It is exported
from your machine for your own use and it must not be published. The commons
is the other thing entirely: counts, no people, and it leaves through
`commons.py` under an explicit opt-in. Do not confuse the two files.

WHY THIS EXISTS

A deployed model cannot learn. The practical answer is periodic fine-tuning,
usually an adapter, on data collected from use -- and the bottleneck there is
never the fitting, it is having labelled outcomes and knowing which ones are
still true.

OMEM produces exactly those: it commits to a claim about a person, records how
bold it was and why, and reality later labels the guess `supported` or
`refuted`. That is a training example with a verdict attached, generated as a
by-product of ordinary use, and every other system in this category throws it
away.

RECALL, WHICH IS THE PART NOBODY BUILDS

Learning from deployment without provenance is how a model silently absorbs a
mistake. If the belief that produced a training example is retracted later --
the source was wrong, the customer corrected it, the premise was withdrawn --
nothing in an ordinary pipeline can tell you which examples are now poisoned,
so the adapter keeps the error permanently and invisibly.

Every line here carries the assertion it was born from. `--check` re-reads the
live project and reports what has changed since the export:

    valid        the supporting belief still stands
    RETRACTED    it does not: these examples are contaminated
    RELABELLED   reality changed its mind; the old label is wrong

A contaminated export is not a corrupt file -- it is a correct record of what
was true when it was written. The check is what makes it safe to train on.

Stdlib only, MIT.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import sys
import urllib.error
import urllib.request

FORMAT = "omem-training/0.1"
LABELS = ("supported", "refuted")


def _rfc3339(epoch: float) -> str:
    return _dt.datetime.fromtimestamp(
        float(epoch), _dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class Client:
    def __init__(self, url: str, key: str, project: str):
        self.url, self.key, self.project = url.rstrip("/"), key, project

    def get(self, path: str):
        sep = "&" if "?" in path else "?"
        req = urllib.request.Request(
            f"{self.url}{path}{sep}project={self.project}",
            headers={"Authorization": "Bearer " + self.key})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read().decode() or "{}")
        except urllib.error.HTTPError as e:
            return {"_error": e.code, "_body": e.read().decode()[:200]}


def _generator_class(generator: str) -> str:
    """Which KIND of leap produced this, never which one. The raw generator is
    a subject id for a look-alike projection, so it does not travel into a
    file that may be handed to a training pipeline."""
    return "prior" if str(generator).startswith("prior:") else "neighbour"


def collect(c: Client) -> list[dict]:
    """One row per hypothesis reality has already decided."""
    rows = []
    for label in LABELS:
        got = c.get(f"/v1/memory/expectations?status={label}")
        if got.get("_error"):
            raise SystemExit("server refused %s: %s" % (label, got.get("_body")))
        for h in got.get("data") or []:
            rows.append({
                "format": FORMAT,
                "id": h.get("id"),
                "subject": h.get("subject"),
                "proposition": h.get("proposition"),
                "label": label,
                # The forecast, as it was made. Not rewritten on resolution,
                # which is what lets this train a calibrator and not just a
                # classifier.
                "strength": h.get("strength"),
                "generator_class": _generator_class(h.get("generator") or ""),
                "because": h.get("because"),
                # The belief this was leapt from. The whole recall mechanism
                # hangs off this one field.
                "born_from": h.get("born_from"),
                "decided_at": _rfc3339(h["decided"]) if h.get("decided") else None,
            })
    rows.sort(key=lambda r: (r["label"], r["id"] or ""))
    return rows


def check(c: Client, path: str) -> int:
    with open(path, encoding="utf-8") as f:
        old = [json.loads(ln) for ln in f if ln.strip()]
    if not old:
        print("%s holds no examples" % path)
        return 1

    live = {r["id"]: r for r in collect(c)}
    valid, retracted, relabelled = [], [], []
    for row in old:
        now = live.get(row.get("id"))
        if now is None:
            # The hypothesis is no longer a decided one: its supporting belief
            # lapsed, was retracted, or the subject was erased. Either way the
            # example no longer rests on anything standing.
            retracted.append(row)
        elif now.get("label") != row.get("label"):
            relabelled.append((row, now))
        else:
            valid.append(row)

    print("checked %d examples from %s\n" % (len(old), path))
    print("  valid       %d" % len(valid))
    print("  RETRACTED   %d" % len(retracted))
    print("  RELABELLED  %d" % len(relabelled))

    for row in retracted[:20]:
        print("\n  retracted   %s" % row.get("id"))
        print("              %s / %s" % (row.get("subject"), row.get("proposition")))
        print("              born from %s" % row.get("born_from"))
    for row, now in relabelled[:20]:
        print("\n  relabelled  %s  %s -> %s"
              % (row.get("id"), row.get("label"), now.get("label")))

    if retracted or relabelled:
        print("\nThis export is contaminated. It is not a corrupt file: it is a "
              "correct\nrecord of what was true when it was written, and %d of its "
              "examples have\nsince stopped being true. Anything trained on it "
              "carries those.\n" % (len(retracted) + len(relabelled)))
        return 1
    print("\nEvery example still rests on a belief that stands.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8787")
    ap.add_argument("--key", required=True)
    ap.add_argument("--project", required=True)
    ap.add_argument("--check", default=None, metavar="FILE")
    args = ap.parse_args()

    c = Client(args.url, args.key, args.project)
    if args.check:
        return check(c, args.check)

    rows = collect(c)
    if not rows:
        print("no resolved hypotheses in this project yet; nothing to export",
              file=sys.stderr)
        return 1
    for r in rows:
        print(json.dumps(r, sort_keys=True))
    print("exported %d examples (%d supported, %d refuted)"
          % (len(rows), sum(1 for r in rows if r["label"] == "supported"),
             sum(1 for r in rows if r["label"] == "refuted")), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
