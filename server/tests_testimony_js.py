"""The browser validator agrees with the reference one, or it does not ship.
Run: python3 tests_testimony_js.py

Two validators that disagree are worse than one, because a conformance claim
then depends on which the reader happened to run, and the whole argument for
this format is that a claim can be checked by the person hearing it.

So this runs both over the same records and fails on any difference: the level
reached, the scope, whether each level was met, and every individual check by
name and outcome. Not a spot check on the happy path. The records below include
the ones designed to fail, because agreeing about a valid record is easy and
agreeing about why an invalid one is invalid is the part that matters.

SKIPS if Node is missing or too old for type stripping. run_tests.py counts a
skip separately and never as a pass, which is the point: a run without Node
verifies nothing here and says so.
"""
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import testimony_validate as tv  # noqa: E402

RUNNER = os.path.join(ROOT, "scripts", "testimony_validate_js.mts")
EXAMPLE = os.path.join(ROOT, "web", "public", "testimony-record-example.jsonl")
PASS = FAIL = 0


def check(n, c, d=""):
    global PASS, FAIL
    if c:
        PASS += 1
        print("  ok  " + n)
    else:
        FAIL += 1
        print("  FAIL " + n + "  " + str(d)[:300])


def node_report(text):
    """What the browser validator says, via the command line runner."""
    fd, path = tempfile.mkstemp(suffix=".jsonl")
    with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    try:
        out = subprocess.run(
            ["node", "--experimental-strip-types", "--no-warnings", RUNNER, path],
            capture_output=True, text=True, timeout=60)
        if out.returncode != 0:
            return None, (out.stderr or out.stdout)[:300]
        return json.loads(out.stdout), ""
    finally:
        os.remove(path)


def usable_node():
    try:
        v = subprocess.run(["node", "--version"], capture_output=True,
                           text=True, timeout=30)
    except Exception:
        return False
    if v.returncode != 0:
        return False
    ok, _ = node_report('{"spec":"testimony-record/0.2","type":"scope",'
                        '"id":"s","at":"2026-01-01T00:00:00Z","acts":false}')
    return ok is not None


if not usable_node():
    print("SKIP: no Node with --experimental-strip-types available.")
    print("      The browser validator was NOT compared against the reference "
          "one in this run.")
    sys.exit(0)


S1, S2 = "testimony-record/0.1", "testimony-record/0.2"


def line(**kw):
    return json.dumps(kw)


def records():
    """Every record both validators are held to, valid and otherwise."""
    out = {}

    with open(EXAMPLE, encoding="utf-8") as f:
        out["the published example"] = f.read()

    out["empty"] = ""
    out["noise"] = "not json at all\n{{{\n[1,2,3]\n"
    out["one line of rubbish among good ones"] = "\n".join([
        line(spec=S2, type="scope", id="s", at="2026-01-01T00:00:00Z", acts=False),
        "{ not json",
    ])

    base = [
        line(spec=S2, type="scope", id="s", at="2026-01-01T00:00:00Z",
             acts=False, system="x"),
        line(spec=S2, type="evidence", id="e1", at="2026-01-01T00:00:01Z",
             kind="document", source="doc:1", digest="sha256:aa", redacted=True),
        line(spec=S2, type="belief", id="b1", at="2026-01-01T00:00:02Z",
             subject="s", proposition="p", polarity="affirm",
             state="believed_true",
             asserted_by={"id": "x", "kind": "system"}, evidence=["e1"]),
        line(spec=S2, type="integrity", id="i1", at="2026-01-01T00:00:03Z",
             scheme="hash-chain", digest="sha256:bb",
             covers=["s", "e1", "b1"]),
    ]
    out["a record-only system at TR-4"] = "\n".join(base)

    out["the same record claiming to act"] = "\n".join(
        [line(spec=S2, type="scope", id="s", at="2026-01-01T00:00:00Z",
              acts=True, system="x")] + base[1:])

    out["declares no actions, then acts"] = "\n".join(base[:3] + [
        line(spec=S2, type="decision", id="d1", at="2026-01-01T00:00:03Z",
             action_type="wire", risk_class="high", risk_source="registry",
             proposed_by={"id": "a", "kind": "agent"}, verdict="permitted",
             executed=True, approval=None)])

    out["a 0.1 record carrying a scope entry"] = "\n".join(base).replace(S2, S1)

    out["mixed specification versions"] = "\n".join(
        [base[0]] + [b.replace(S2, S1) for b in base[1:]])

    out["a belief citing evidence that is not there"] = "\n".join([
        base[0], base[2], base[3]])

    out["entries out of time order"] = "\n".join([base[0], base[2], base[1], base[3]])

    out["a contradiction with no conflict entry"] = "\n".join([
        base[0], base[1],
        line(spec=S2, type="belief", id="b1", at="2026-01-01T00:00:02Z",
             subject="s", proposition="p", polarity="affirm",
             state="contradicted",
             asserted_by={"id": "x", "kind": "system"}, evidence=["e1"]),
    ])

    out["an agent approving its own high-risk action"] = "\n".join([
        line(spec=S2, type="decision", id="d1", at="2026-01-01T00:00:00Z",
             action_type="refund", risk_class="high", risk_source="registry",
             proposed_by={"id": "agent:1", "kind": "agent"},
             verdict="permitted", executed=True, approval="a1"),
        line(spec=S2, type="approval", id="a1", at="2026-01-01T00:00:01Z",
             decision="d1", approver={"id": "agent:1", "kind": "human"},
             identity_source="api-key"),
    ])

    out["a refused action recorded as executed"] = "\n".join([
        line(spec=S2, type="decision", id="d1", at="2026-01-01T00:00:00Z",
             action_type="refund", risk_class="low", risk_source="registry",
             proposed_by={"id": "a", "kind": "agent"}, verdict="refused",
             executed=True),
    ])

    out["an enumerated field with an invented value"] = "\n".join([
        base[0],
        line(spec=S2, type="evidence", id="e1", at="2026-01-01T00:00:01Z",
             kind="email", source="doc:1", digest="sha256:aa"),
    ])
    return out


print("== the two validators agree, record by record ==")
for name, text in records().items():
    py = tv.validate(text)
    js, err = node_report(text)
    if js is None:
        check(name, False, "the browser validator errored: " + err)
        continue

    py_checks = [[c["level"], c["check"], c["ok"]] for c in py.checks]
    js_checks = [list(c) for c in js["checks"]]
    py_levels = {lvl: not py.failures(lvl) for lvl in tv.LEVELS}

    same = (py.level == js["level"] and py.scope == js["scope"]
            and py.spec == js["spec"] and py_levels == js["levels_met"]
            and sorted(map(str, py_checks)) == sorted(map(str, js_checks)))
    detail = ""
    if not same:
        only_py = [c for c in py_checks if c not in js_checks]
        only_js = [c for c in js_checks if c not in py_checks]
        detail = (f"python level={py.level} scope={py.scope} | "
                  f"node level={js['level']} scope={js['scope']} | "
                  f"python only={only_py[:2]} node only={only_js[:2]}")
    check(name, same, detail)

print("\n%d passed, %d failed" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)
