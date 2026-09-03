"""The Witness harness: run scenarios against one adapter, score honestly.

Every probe lands in exactly one of three outcomes:

    PASS         the checks held
    VIOLATION    a check failed, with the offending evidence quoted
    UNSUPPORTED  the probe needs a capability the system's design lacks

UNSUPPORTED is never folded into either other bucket. A system that cannot
declare rules has not "failed" the cascade derivation, and it certainly has
not passed it; the honest report says it cannot express the question. The
same runner logic that keeps skipped test suites out of the pass count in
this repository's CI applies here, for the same reason.

Scoring is deterministic substring matching against what the system itself
returned. No LLM judges: a judged benchmark inherits the judge's own
confabulation rate, which is the quantity under measurement.
"""
from __future__ import annotations

import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
SCENARIOS = os.path.join(HERE, "scenarios")

# speculation / deference / coherence were added after the intuition layer
# grew: a system that INFERS has duties a system that only records does not.
# Each is judged purely from holdings(), which every adapter here supports, so
# no system is marked UNSUPPORTED on them and none is scored on a capability
# only one of them has. Adding axes a competitor cannot express is how a
# vendor benchmark lies, and the constraint is stated here so it can be
# checked rather than trusted.
AXES = ("fabrication", "retention", "retraction", "staleness", "history",
        "contradiction", "identity", "rules", "cascade", "provenance",
        "speculation", "deference", "coherence")

# What each probe field demands of the adapter.
_NEEDS = {
    "forbid": "holdings", "expect": "holdings", "expect_state": "state",
    "want_conflict": "conflicts", "want_sources": "provenance",
}
_HISTORY_AXES = {"history"}
_NEEDS["forbid_both"] = "holdings"


def load_scenarios(only=None):
    out = []
    for fn in sorted(os.listdir(SCENARIOS)):
        if not fn.endswith(".json"):
            continue
        with open(os.path.join(SCENARIOS, fn), encoding="utf-8") as f:
            sc = json.load(f)
        if only and sc["name"] not in only:
            continue
        out.append(sc)
    return out


def _needs(probe):
    need = {_NEEDS[k] for k in probe if k in _NEEDS}
    if probe["axis"] in _HISTORY_AXES:
        need.discard("holdings")
        need.add("history")
    if probe["axis"] == "rules" or probe["axis"] == "cascade":
        need.add("rules")
    return need


def _texts(rows):
    return [r["text"].lower() for r in rows]


def run_probe(adapter, probe):
    missing = _needs(probe) - adapter.capabilities
    if missing:
        return {"probe": probe["id"], "axis": probe["axis"],
                "outcome": "UNSUPPORTED", "missing": sorted(missing)}

    about = probe["about"]
    problems = []

    if "expect_state" in probe:
        got = adapter.state(about, probe["claim"])
        if got != probe["expect_state"]:
            problems.append("state is %s, wanted %s" % (got, probe["expect_state"]))

    if "forbid" in probe or "expect" in probe or "want_sources" in probe:
        rows = (adapter.history(about) if probe["axis"] in _HISTORY_AXES
                else adapter.holdings(about))
        texts = _texts(rows)
        for tok in probe.get("forbid", []):
            hits = [t for t in texts if tok.lower() in t]
            if hits:
                problems.append("asserts %r via %r" % (tok, hits[0][:80]))
        for tok in probe.get("expect", []):
            if not any(tok.lower() in t for t in texts):
                problems.append("lost %r" % tok)
        for pair in probe.get("forbid_both", []):
            a, b = pair[0].lower(), pair[1].lower()
            if any(a in t for t in texts) and any(b in t for t in texts):
                problems.append("asserts BOTH %r and %r about the same "
                                "subject" % (pair[0], pair[1]))
        if probe.get("want_sources"):
            for r in rows:
                if not r.get("sources"):
                    problems.append("no source for %r" % r["text"][:60])

    if probe.get("want_conflict"):
        if not adapter.conflict_visible(about):
            problems.append("no conflict visible about %s" % about)

    return {"probe": probe["id"], "axis": probe["axis"],
            "outcome": "VIOLATION" if problems else "PASS",
            "problems": problems}


def run_scenario(adapter, sc):
    """Play a scenario's events at one system, then probe what it holds.

    A scenario may ask every system to do its inference step before being
    probed, with the `consolidate` op. Systems that infer at write time
    implement it as a no-op; OMEM mines and leaps on a pass, so without it the
    intuition layer never runs during a benchmark and any probe asking whether
    an inference was kept out of testimony passes because no inference was
    ever made. That is a test which cannot fail, which is worse than no test.
    """
    results = []
    for ev in sc["events"]:
        op = ev["op"]
        if op == "probe_checkpoint":
            for p in sc.get("checkpoint_probes", []):
                results.append(run_probe(adapter, p))
            continue
        if op == "rule" and "rules" not in adapter.capabilities:
            continue    # the probes that depend on it report UNSUPPORTED
        if op == "consolidate" and not hasattr(adapter, "consolidate"):
            continue    # a system with no separate inference step just skips
        getattr(adapter, op)(ev)
    for p in sc["probes"]:
        results.append(run_probe(adapter, p))
    return {"scenario": sc["name"], "title": sc["title"], "results": results}


def run_all(adapter, only=None):
    return [run_scenario(adapter, sc) for sc in load_scenarios(only)]


def summarize(report):
    """Per-axis tallies: {axis: {"pass": n, "violation": n, "unsupported": n}}."""
    tally = {a: {"pass": 0, "violation": 0, "unsupported": 0} for a in AXES}
    for sc in report:
        for r in sc["results"]:
            tally[r["axis"]][r["outcome"].lower()
                             if r["outcome"] != "PASS" else "pass"] += 1
    return {a: t for a, t in tally.items() if sum(t.values())}


def render(name, report):
    lines = ["witness: %s\n" % name]
    for sc in report:
        lines.append("  %s (%s)" % (sc["title"], sc["scenario"]))
        for r in sc["results"]:
            mark = {"PASS": "ok  ", "VIOLATION": "FAIL",
                    "UNSUPPORTED": "n/a "}[r["outcome"]]
            detail = "; ".join(r.get("problems", [])) or \
                     ("needs " + ", ".join(r.get("missing", [])))
            lines.append("    %s %-13s %s%s" % (
                mark, r["axis"], r["probe"],
                ("  " + detail) if r["outcome"] != "PASS" else ""))
    lines.append("")
    lines.append("  axis          pass  violation  unsupported")
    for axis, t in summarize(report).items():
        lines.append("  %-13s %4d  %9d  %11d"
                     % (axis, t["pass"], t["violation"], t["unsupported"]))
    return "\n".join(lines)
