#!/usr/bin/env python3
"""Generate a CycloneDX SBOM for the published package.

    python3 scripts/gen_sbom.py            > sbom.json
    python3 scripts/gen_sbom.py --check    verify the declared deps are still none

Every software questionnaire asks for one, and for most projects producing it is
a chore. Here it is close to an argument: the server and the Python SDK have NO
runtime dependencies, so the bill of materials is one component and the
transitive attack surface is the standard library.

That is the whole point of the constraint in CONTRIBUTING.md rule 3, and it is
worth being able to hand someone a machine-readable file that says so rather
than asking them to take it on trust.

The optional extras ARE listed, marked optional, because "no dependencies"
would otherwise be a half-truth: [postgres] pulls psycopg2-binary and
[encryption] pulls cryptography. Both are opt-in and neither is needed to run
the server, but a reader deciding what enters their environment should see them.

--check exits non-zero if a runtime dependency has appeared, so the claim
cannot quietly stop being true.
"""
import argparse
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PYPROJECT = os.path.join(HERE, "..", "sdk", "python", "pyproject.toml")


def parse_pyproject(path):
    """Read name, version, licence and dependencies without a TOML parser.

    tomllib is 3.11+ and this package supports 3.9, and adding a dependency to
    a script whose purpose is to prove there are no dependencies would be its
    own kind of joke.
    """
    text = open(path, encoding="utf-8").read()

    def scalar(key):
        m = re.search(r'^%s\s*=\s*"([^"]*)"' % key, text, re.M)
        return m.group(1) if m else None

    # dependencies = [...] in [project]; empty list means none.
    m = re.search(r'^dependencies\s*=\s*\[(.*?)\]', text, re.M | re.S)
    runtime = [d.strip().strip('"\'') for d in (m.group(1) if m else "").split(",")
               if d.strip().strip('"\'')]

    extras = {}
    m = re.search(r'\[project\.optional-dependencies\](.*?)(?=^\[|\Z)', text, re.M | re.S)
    if m:
        for line in m.group(1).splitlines():
            em = re.match(r'\s*([A-Za-z0-9_-]+)\s*=\s*\[(.*)\]', line)
            if em:
                extras[em.group(1)] = [d.strip().strip('"\'')
                                       for d in em.group(2).split(",") if d.strip()]
    return {"name": scalar("name"), "version": scalar("version"),
            "description": scalar("description"), "runtime": runtime, "extras": extras}


def build(meta, source_date=None):
    ref = "pkg:pypi/%s@%s" % (meta["name"], meta["version"])
    components = []
    for extra, deps in sorted(meta["extras"].items()):
        for d in deps:
            nm = re.split(r"[<>=!~\[]", d)[0].strip()
            components.append({
                "type": "library", "name": nm, "bom-ref": "pkg:pypi/%s" % nm,
                "purl": "pkg:pypi/%s" % nm, "scope": "optional",
                "description": "Only installed with the [%s] extra; not needed to run OMEM."
                               % extra,
            })
    doc = {
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "version": 1,
        "metadata": {
            "component": {
                "type": "application", "bom-ref": ref, "purl": ref,
                "name": meta["name"], "version": meta["version"],
                "description": meta["description"],
                "licenses": [{"license": {"id": "MIT"}}],
            },
            "properties": [
                {"name": "omem:runtime_dependencies", "value": str(len(meta["runtime"]))},
                {"name": "omem:note",
                 "value": "The server and SDK run on the Python standard library "
                          "alone. Components listed below are optional extras."},
            ],
        },
        "components": components,
    }
    if source_date:
        doc["metadata"]["timestamp"] = source_date
    return doc


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true",
                    help="fail if a runtime dependency has appeared")
    ap.add_argument("-o", "--out", help="write here instead of stdout")
    args = ap.parse_args()

    meta = parse_pyproject(PYPROJECT)
    if args.check:
        if meta["runtime"]:
            print("SBOM check FAILED: %s now declares runtime dependencies: %s"
                  % (meta["name"], ", ".join(meta["runtime"])), file=sys.stderr)
            print("If that is deliberate, update this check and CONTRIBUTING.md "
                  "rule 3 in the same change.", file=sys.stderr)
            return 1
        print("%s %s: 0 runtime dependencies, %d optional extra(s)"
              % (meta["name"], meta["version"], len(meta["extras"])))
        return 0

    # SOURCE_DATE_EPOCH keeps the output byte-identical across runs, so the SBOM
    # can be diffed and committed without churn.
    ts = os.environ.get("SOURCE_DATE_EPOCH")
    stamp = None
    if ts:
        import datetime
        stamp = datetime.datetime.utcfromtimestamp(int(ts)).strftime("%Y-%m-%dT%H:%M:%SZ")
    doc = build(meta, stamp)
    text = json.dumps(doc, indent=2, sort_keys=True) + "\n"
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(text)
        print("wrote %s" % args.out)
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
