#!/usr/bin/env python3
"""Run the Witness benchmark against one memory system.

    python3 run.py omem      needs OMEM_BASE_URL, OMEM_API_KEY, OMEM_PROJECT
    python3 run.py mem0      needs OPENAI_API_KEY, pip install mem0ai
    python3 run.py graphiti  needs OPENAI_API_KEY, NEO4J_URI, graphiti-core

Writes results-<system>.json next to this file and prints the human report.
A system whose requirements are missing exits with the reason instead of a
degraded run: numbers from a half-configured system are worse than none.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import harness  # noqa: E402
from adapters import AdapterUnavailable  # noqa: E402


def build(name):
    if name == "omem":
        sys.path.insert(0, os.path.join(HERE, "..", "..", "sdk", "python"))
        import omem
        from adapters.omem_adapter import OmemAdapter
        base = os.environ.get("OMEM_BASE_URL", "http://127.0.0.1:8787")
        key, proj = os.environ.get("OMEM_API_KEY"), os.environ.get("OMEM_PROJECT")
        if not key or not proj:
            raise AdapterUnavailable("set OMEM_API_KEY and OMEM_PROJECT "
                                     "(and OMEM_BASE_URL for a remote server)")
        return OmemAdapter(omem.Memory(key, base_url=base, project=proj))
    if name == "mem0":
        from adapters.mem0_adapter import Mem0Adapter
        return Mem0Adapter()
    if name == "graphiti":
        from adapters.graphiti_adapter import GraphitiAdapter
        return GraphitiAdapter()
    raise SystemExit("unknown system %r; choose omem, mem0 or graphiti" % name)


def main():
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    name = sys.argv[1]
    try:
        adapter = build(name)
    except AdapterUnavailable as e:
        raise SystemExit("cannot run %s here: %s" % (name, e))
    report = harness.run_all(adapter)
    out = os.path.join(HERE, "results-%s.json" % name)
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"system": name, "report": report,
                   "summary": harness.summarize(report)}, f, indent=2)
    print(harness.render(name, report))
    print("\nwritten: " + out)


if __name__ == "__main__":
    main()
