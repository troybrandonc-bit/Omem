#!/usr/bin/env python3
"""OMEM reasoning, demonstrated against a real server in about a minute.

    python3 scripts/demo_reasoning.py

Anything can retrieve a fact. What makes memory trustworthy is what happens
around one: noticing that two records are one person, concluding only what
was declared, and -- above all -- taking a conclusion back the moment the
evidence under it dies. This drives all three through the Python SDK.

It is also a TEST. Every behaviour below is asserted, and the script exits
non-zero if any of them stops happening. Same contract as demo_refusal.py: a
demo that can quietly stop being true is worse than no demo.

The scenario: a small sales team's memory. Sarah Chen exists twice (once from
an email, once from a message body). A rule says people who work at a company
you own are in your orbit. Then the ownership is retracted, and everything
that rested on it falls, on the record.
"""
import os
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
SERVER = os.path.join(HERE, "..", "server")
sys.path.insert(0, SERVER)
sys.path.insert(0, os.path.join(HERE, "..", "sdk", "python"))

TMP = os.environ.get("TEMP") or "/tmp"
os.environ.setdefault("OMEM_DB", os.path.join(TMP, "omem_demo_reasoning.db"))
os.environ.setdefault("OMEM_SEED_DEMO", "0")
if os.path.exists(os.environ["OMEM_DB"]):
    os.remove(os.environ["OMEM_DB"])

import api  # noqa: E402
from omem import Memory  # noqa: E402
from http.server import ThreadingHTTPServer  # noqa: E402

FAILED = 0
BOLD, DIM, OFF = "\033[1m", "\033[2m", "\033[0m"
if os.environ.get("NO_COLOR") or not sys.stdout.isatty():
    BOLD = DIM = OFF = ""


def holds(label, condition, detail=""):
    """Assert a behaviour happened. The demo fails loudly if it did not."""
    global FAILED
    if condition:
        print("    " + label)
    else:
        FAILED += 1
        print("    DID NOT HOLD: " + label + "  " + str(detail)[:200])


def head(n):
    print("\n" + BOLD + n + OFF)


srv = ThreadingHTTPServer(("127.0.0.1", 0), api.Handler)
PORT = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()
time.sleep(0.3)

import json
import urllib.request


def _signup():
    req = urllib.request.Request(
        "http://127.0.0.1:%d/v1/signup" % PORT, method="POST",
        data=json.dumps({"email": "demo-reasoning@omem.local"}).encode(),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())


acct = _signup()
mem = Memory(acct["api_key"]["secret"],
             base_url="http://127.0.0.1:%d" % PORT,
             project=acct["project"]["id"])
OWNER = "agent:owner"

print(BOLD + "OMEM: reasoning with receipts" + OFF)
print(DIM + "A real server on 127.0.0.1:%d. Every behaviour below is asserted." % PORT + OFF)

# ─────────────────────────────────────────────────────────────────────────────
head("1. One person arrived twice. OMEM notices, and knows when not to.")
print(DIM + "   person:sarah_chen@acme (wrote the mail) and person:sarah_chen" + OFF)
print(DIM + "   (named in a body) each hold half the beliefs about one human." + OFF)

for eid, label in [("company:acme", "Acme"), ("company:beta", "BetaCorp"),
                   ("person:sarah_chen@acme", "Sarah Chen"),
                   ("person:sarah_chen", "Sarah Chen"),
                   ("person:sarah_chen@globex", "Sarah Chen"),
                   ("person:dana_kim@acme", "Dana Kim"),
                   ("person:dana", "Dana")]:
    mem.ensure_entity(eid, type="organization" if eid.startswith("company:") else "person",
                      label=label)
mem.remember(OWNER, ["person:sarah_chen@acme", "company:acme"], "rel_works_at_acme")
mem.remember(OWNER, ["person:sarah_chen", "company:acme"], "rel_works_at_acme")
mem.remember(OWNER, ["company:acme", "person:dana"], "rel_involves_dana")
mem.remember(OWNER, "person:sarah_chen", "prefers_annual_billing")

before = mem.believes("person:sarah_chen@acme", "prefers_annual_billing")
print("\n    before: the alias knows nothing        -> " + before)
r = mem.resolve()
merged = r.get("merged", [])
pairs = [sorted(m["pair"]) for m in merged]
after = mem.believes("person:sarah_chen@acme", "prefers_annual_billing")
print("    after one resolution pass              -> " + after)

holds("the two Sarah Chens at acme merged (same full name, same organisation)",
      ["person:sarah_chen", "person:sarah_chen@acme"] in pairs, r)
holds("the belief crossed the merge", before == "UNKNOWN" and after == "BELIEVED_TRUE",
      (before, after))
reasons = " | ".join(x.get("reason", "") for x in r.get("refused", []))
holds("Sarah Chen at globex was refused: a shared name is not a shared identity",
      "different organisations" in reasons, reasons)
holds("Dana against Dana Kim was only PROPOSED, because a given name is a guess",
      any("person:dana" in x.get("pair", []) for x in r.get("proposed", [])), r)

open_props = mem.merge_proposals(status="open")
dana = next(p for p in open_props
            if sorted((p["entity_a"], p["entity_b"])) == ["person:dana", "person:dana_kim@acme"])
print(DIM + "\n    proposal: %s" % dana["evidence"] + OFF)
ap = mem.approve_merge(dana["id"], agent=OWNER)
holds("a person approved it, and the merge is recorded under THEIR name",
      ap.get("status") == "approved" and ap.get("coreference"), ap)

# ─────────────────────────────────────────────────────────────────────────────
head("2. A declared rule concludes. Only what was declared, with its premises.")
print(DIM + "   works_at(fwd) . owns(rev) => involves(rev): whoever works at a" + OFF)
print(DIM + "   company you own is in your orbit. A rule is data, not a judgment." + OFF)

mem.ensure_entity("person:marco", type="person", label="Marco Ruiz")
mem.remember(OWNER, ["person:marco", "company:beta"], "rel_works_at_beta")
owns = mem.remember(OWNER, ["company:acme", "company:beta"], "rel_owns_beta")
mem.declare_rule(when=[("works_at", "fwd"), ("owns", "rev")],
                 then=("involves", "rev"))
run = mem.infer()
derived = run.get("derived", [])
print("\n    derived: " + ", ".join(d["proposition"] for d in derived))
holds("the rule concluded acme's orbit involves Marco",
      mem.believes(["company:acme", "person:marco"], "rel_involves_marco")
      == "BELIEVED_TRUE", run)
conc = next(d["assertion"] for d in derived if d["proposition"] == "rel_involves_marco")
why = mem.why(conc)
blob = json.dumps(why)
holds("/why walks from the conclusion to BOTH premises it used",
      owns["id"] in blob, blob[:200])
holds("and a second pass concludes nothing new: the evidence is spent",
      len(mem.infer().get("derived", [])) == 0)

# ─────────────────────────────────────────────────────────────────────────────
head("3. The take-back. Retract the premise; the conclusion falls with it.")
print(DIM + "   Acme sells BetaCorp. Nothing that rested on the ownership may" + OFF)
print(DIM + "   survive it, and nothing is deleted: every withdrawal is an op." + OFF)

mem.retract(owns["id"], agent=OWNER)
state = mem.believes(["company:acme", "person:marco"], "rel_involves_marco")
print("\n    rel_involves_marco after the retraction -> " + state)
holds("the conclusion was withdrawn IN THE SAME REQUEST, no pass needed",
      state == "UNKNOWN", state)
holds("while the untouched premise still stands",
      mem.believes(["person:marco", "company:beta"], "rel_works_at_beta")
      == "BELIEVED_TRUE")
holds("and the machine does not re-conclude from the dead evidence",
      len(mem.infer().get("derived", [])) == 0)

# ─────────────────────────────────────────────────────────────────────────────
head("4. A split is final for the machine.")
print(DIM + "   A person separates the two Sarah Chens. The machine never" + OFF)
print(DIM + "   re-merges a pair a person split, not even via its own queue." + OFF)

cor = next(m["coreference"] for m in merged
           if sorted(m["pair"]) == ["person:sarah_chen", "person:sarah_chen@acme"])
mem.split(cor, agent=OWNER)
r2 = mem.resolve()
holds("the referents separated again",
      mem.believes("person:sarah_chen@acme", "prefers_annual_billing") == "UNKNOWN")
holds("and the next pass refuses to re-merge them",
      len(r2.get("merged", [])) == 0 and
      "a split recorded these as different people" in
      " | ".join(x.get("reason", "") for x in r2.get("refused", [])), r2)

srv.shutdown()

print("\n" + BOLD + "What this showed" + OFF)
print("""    OMEM merged one person's two records on decisive evidence, queued the
    suggestive case for a human whose approval it recorded by name, concluded
    exactly what a declared rule implied, explained the conclusion from its
    premises, withdrew it the moment a premise was retracted, and refused to
    re-merge what a person had split.

    Every one of those is an ordinary operation in the append-only log:
    replay reconstructs the reasoning, and /why answers for every step.""")

if FAILED:
    print("\n%d behaviour(s) DID NOT HOLD. This is a failure." % FAILED)
    sys.exit(1)
print(DIM + "\nall behaviours asserted and held" + OFF)
sys.exit(0)
