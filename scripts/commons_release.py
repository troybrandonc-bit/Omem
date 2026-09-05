#!/usr/bin/env python3
"""Cut a commons release, or check one somebody handed you.

    python3 scripts/commons_release.py build releases/2026-09-05
    python3 scripts/commons_release.py verify releases/2026-09-05

WHY THIS EXISTS.

The dataset endpoint answers from the live bank. That is fine for looking and
useless for citing: the file somebody downloaded last month cannot be
reproduced today, so nothing distinguishes a genuine aggregate from one edited
afterwards. A corpus that asks to be trained on has to be better than that, and
this project's answer to every other system is that a claim nobody can check is
an adjective.

A release is a directory:

    manifest.json        what went in, what aggregated it, what came out
    dataset.jsonl        the corpus
    contributions.jsonl  the counts each install contributed
    DATASET_CARD.md      what the corpus is and what it can never contain
    VERIFY.md            how to check all of this without any of our software

`verify` recomputes the corpus from the contributions and compares digests.
Anyone can, which is the point: it needs this file, a Python interpreter, and
nothing else of ours.

WHAT REPUBLISHING THE CONTRIBUTIONS DOES NOT COST.

A contribution is counts over a population and holds no fact about any person,
so publishing one for verification publishes nobody. That is what makes
recomputability affordable here. A corpus of records about people could not do
this, and the reason is worth stating rather than leaving as a convenience.

WITHDRAWAL.

Forward acting, and this does not weaken it. A contributor's counts leave the
bank and every release built after their withdrawal, and the withdrawal is
recorded with its date. Releases already published are not withdrawn, because
nobody can unpublish a file somebody else has downloaded, and the terms say
that rather than promising an erasure no one can perform.

Copyright 2026 Michael Brandon Clifford. MIT licensed.
"""
from __future__ import annotations

import argparse
import io
import json
import os
import sqlite3
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "server"))

import commons as _c        # noqa: E402


VERIFY_MD = """# Checking this release

Nothing here needs our software beyond `commons_release.py`, which is one file
and MIT licensed. If you would rather not run that either, the last section
says what it does in enough detail to reimplement in an afternoon.

    python3 commons_release.py verify .

## What is being checked

1. Every contribution in `contributions.jsonl` hashes to the digest
   `manifest.json` records for it. An edited contribution is caught here and
   named.
2. The corpus is rebuilt from those contributions and hashed. If it does not
   match `dataset_digest`, the corpus you were handed is not the corpus the
   manifest describes.
3. The aggregation version is compared. If it differs, a rebuilt corpus
   legitimately differs too, and you are told that rather than being told the
   file was tampered with.

## What it does not establish

That the contributions are true. An install contributes counts it learned from
its own memory, and no arithmetic here can check that those counts reflect
anything that happened. Verification establishes that this corpus is the
aggregate of these contributions and that neither has changed since. Whether a
population's behaviour is what an install says it is remains a question about
the install.

## Doing it by hand

A contribution's digest is the SHA-256 of its patterns, each written as JSON
with members ordered by name and no insignificant whitespace, joined by single
line feeds with none at the end, encoded as UTF-8. That is the digest rule the
Testimony Record specification publishes, used here rather than restated:
https://datatracker.ietf.org/doc/draft-clifford-testimony-record/

The corpus digest is the SHA-256 of `dataset.jsonl` as bytes.
"""


def build(db_path: str, out: str, at: str = "") -> int:
    if not os.path.exists(db_path):
        print("no database at %s" % db_path, file=sys.stderr)
        return 1
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    rel = _c.release(con, at=at)
    m = rel["manifest"]

    os.makedirs(out, exist_ok=True)
    w = lambda name, text: io.open(os.path.join(out, name), "w",       # noqa: E731
                                   encoding="utf-8", newline="\n").write(text)
    w("manifest.json", json.dumps(m, indent=1, sort_keys=True) + "\n")
    w("dataset.jsonl", rel["jsonl"])
    w("contributions.jsonl", "".join(
        json.dumps(c, sort_keys=True) + "\n" for c in rel["contributions"]))
    stats = _c.analytics(rel["rows"],
                         {c["instance"]: (c["received"], c["patterns"])
                          for c in rel["contributions"]}, con)
    w("DATASET_CARD.md", _c.dataset_card(rel["rows"], stats) + "\n")
    w("VERIFY.md", VERIFY_MD)

    print("release %s" % m["built_at"])
    print("  contributors  %d" % m["contributors"])
    print("  rows          %d" % m["rows"])
    print("  aggregation   %s" % m["aggregation"])
    print("  digest        %s" % m["dataset_digest"])
    print("  written to    %s" % out)
    if m["rows"] == 0:
        print("\nthe corpus is empty. That is a true statement about the bank "
              "and not a failure here; a release of nothing is still "
              "checkable, and publishing one says so honestly.")
    return 0


def verify(path: str) -> int:
    try:
        manifest = json.load(io.open(os.path.join(path, "manifest.json"),
                                     encoding="utf-8"))
        jsonl = io.open(os.path.join(path, "dataset.jsonl"),
                        encoding="utf-8").read()
        contributions = [json.loads(l) for l in io.open(
            os.path.join(path, "contributions.jsonl"), encoding="utf-8")
            if l.strip()]
    except FileNotFoundError as e:
        print("not a release directory: %s" % e, file=sys.stderr)
        return 2

    ok, problems = _c.verify_release(manifest, contributions, jsonl)
    print("release %s, %d contributors, %d rows"
          % (manifest.get("built_at"), manifest.get("contributors"),
             manifest.get("rows")))
    if ok:
        print("\nverified: the corpus is the aggregate of these contributions, "
              "and neither has changed.")
        print("digest %s" % manifest.get("dataset_digest"))
        return 0
    print("\nnot verified:")
    for p in problems:
        print("  - %s" % p)
    return 1


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Cut a commons release, or check one.")
    ap.add_argument("action", choices=("build", "verify"))
    ap.add_argument("path", help="the release directory")
    ap.add_argument("--db", default=os.environ.get("OMEM_DB", "omem.db"),
                    help="the collector's database, for build")
    ap.add_argument("--at", default="", help="override the build time, for "
                                             "reproducing an existing release")
    a = ap.parse_args()
    return build(a.db, a.path, a.at) if a.action == "build" else verify(a.path)


if __name__ == "__main__":
    sys.exit(main())
