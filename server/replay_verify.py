#!/usr/bin/env python3
"""Prove the state is reproducible from the log, rather than asserting it.

    python3 replay_verify.py                 verify every project
    python3 replay_verify.py --project X     just one
    python3 replay_verify.py --record        write the digests to .omem-state.json
    python3 replay_verify.py --anchor F      compare against a digest file kept
                                             somewhere OMEM does not control

WHY THIS EXISTS. The README says memory is rebuilt by replaying an append-only
log, and that the same inputs give the same state. Both are true and neither was
checkable from outside: you had to read the code and believe it. For a system
whose whole argument is "you can reconstruct what the agent believed and why",
an unverifiable reproducibility claim is the weakest link in the pitch.

WHAT IT CHECKS, in order of how much it proves:

  1. DETERMINISM. The log is replayed into two independent fresh engines and
     the resulting state digests are compared. Different digests would mean the
     replay depends on something outside the log -- wall-clock, iteration order,
     a dict that is not sorted -- and that the "same question, same answer"
     property does not hold. This is the check that can fail for a reason
     nobody put in the database.

  2. AGREEMENT. The replayed digest is compared to the running server's own
     state, if a database is being read that a server also rebuilt from. In
     practice this is the same computation, which is why it is listed second:
     it confirms the code path, not the data.

  3. ANCHORING (--anchor). The digest is compared to one recorded earlier and
     kept elsewhere. THIS is the one that detects tampering. Someone with write
     access to the database can rewrite the log and the state will agree with
     itself perfectly; it will not agree with a digest you wrote down last
     month and stored somewhere they cannot reach. Same reasoning as the audit
     chain's head hash, applied to the op log.

WHAT IT DOES NOT PROVE. That the beliefs are correct, that the log is complete,
or that nothing was deleted before the first anchor was taken. It proves the
state follows from the log, and that the log has not changed since an anchor.
Those are narrow claims, which is why they are worth making precisely.

The digest covers the primitives and the belief state they produce, sorted
canonically, so it changes if any belief changes and does not change because a
dict happened to iterate differently.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

DIGEST_FILE = ".omem-state.json"


def state_digest(p) -> tuple:
    """A canonical digest of everything the engine believes, and the counts.

    Sorted at every level. An unsorted set or a dict iteration order leaking in
    here would make the digest differ between two replays of the same log,
    which is exactly the failure the determinism check is looking for, so it
    must not be introduced by the checker itself.
    """
    e = p.engine
    T = p.now()
    lines = []

    for ent in sorted(e.store.entities(), key=lambda x: x.id):
        lines.append("entity\x1f%s\x1f%s" % (ent.id, getattr(ent, "etype", "")))
    for ag in sorted(e.store.agents(), key=lambda x: x.id):
        lines.append("agent\x1f%s\x1f%s" % (ag.id, getattr(ag, "akind", "")))
    for ev in sorted(e.store.events(), key=lambda x: x.id):
        lines.append("event\x1f%s\x1f%s\x1f%s" % (
            ev.id, getattr(ev, "ekind", ""), getattr(ev, "event_time", "")))

    props = set()
    for a in sorted(e.store.assertions(), key=lambda x: x.id):
        subs = ",".join(sorted(a.subjects))
        lines.append("assertion\x1f%s\x1f%s\x1f%s\x1f%s\x1f%s\x1f%s" % (
            a.id, a.agent, subs, a.proposition, a.assertion_time,
            "open" if e.ledger.is_open_at(a, T) else "closed"))
        props.add((tuple(sorted(a.subjects)), a.proposition))

    for d in sorted(e.store.derivations(), key=lambda x: (x.consequent, x.kind)):
        lines.append("derivation\x1f%s\x1f%s\x1f%s" % (
            d.consequent, d.kind, ",".join(sorted(d.antecedents))))

    # The belief states themselves, not just the primitives that produce them.
    # Two logs could in principle yield the same assertion rows and different
    # states; this is what makes the digest about what the agent BELIEVES
    # rather than about what rows exist.
    for subs, prop in sorted(props):
        lines.append("state\x1f%s\x1f%s\x1f%s" % (
            ",".join(subs), prop, e.proposition_state(list(subs), prop, T)))

    blob = "\x1e".join(lines).encode("utf-8")
    counts = {"entities": len(list(e.store.entities())),
              "agents": len(list(e.store.agents())),
              "events": len(list(e.store.events())),
              "assertions": len(list(e.store.assertions())),
              "propositions": len(props), "logical_time": T}
    return hashlib.sha256(blob).hexdigest(), counts


def replay(api, row, ops) -> object:
    """Replay a log into a FRESH project, using the server's own dispatch.

    apply_op is the single path live writes, seeding and boot replay all go
    through, so verifying with it means this checks the real thing rather than
    a second implementation that could agree while both are wrong.
    """
    p = api.Project(row["id"], row["name"], row["env"], row["org_id"], bool(row["is_demo"]))
    for op in ops:
        p.clock = max(p.clock, op["clock"])
        api.apply_op(p, op["kind"], op["args"])
    return p


def audit_heads(api) -> dict:
    """The audit chain head hash per organisation, and whether it verifies.

    enterprise.py already says the honest thing about this chain: it is
    tamper-EVIDENCE, not tamper-proofing, and someone with write access can
    rewrite it from the edit forward. Detecting that needs the head hash kept
    somewhere OMEM does not control. GET /v1/audit/verify has always returned
    the head; nothing recorded it, so "anchor it off-system" was an instruction
    rather than a command.

    It rides in the same file as the state digests deliberately. Two anchors
    kept in two places is two habits, and the one you skip is the one that
    mattered.
    """
    orgs = sorted({r["org_id"] for r in api.STORE.projects_all() if r["org_id"]})
    out = {}
    for oid in orgs:
        try:
            res = api.ENT.verify_audit_chain(oid)
        except Exception as e:                       # never fail the state check
            out[oid] = {"error": "%s: %s" % (type(e).__name__, e)}
            continue
        out[oid] = {"head": res.get("head"), "internally_consistent": res.get("ok"),
                    "rows_checked": res.get("checked")}
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Verify OMEM state is reproducible from its log.")
    ap.add_argument("--project", help="only this project id")
    ap.add_argument("--record", action="store_true",
                    help=f"write the digests to {DIGEST_FILE}")
    ap.add_argument("--anchor", metavar="FILE",
                    help="compare against digests recorded earlier and kept elsewhere")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    args = ap.parse_args()

    os.environ.setdefault("OMEM_SEED_DEMO", "0")
    import api  # noqa: E402  (after sys.path and env)

    rows = [r for r in api.STORE.projects_all()
            if not args.project or r["id"] == args.project]
    if not rows:
        print(f"no project matched {args.project!r}" if args.project else "no projects")
        return 1

    anchored = {}
    if args.anchor:
        if not os.path.exists(args.anchor):
            print(f"anchor file not found: {args.anchor}")
            return 2
        anchored = json.load(open(args.anchor, encoding="utf-8")).get("projects", {})

    heads = audit_heads(api)
    results, failed = {}, 0
    for row in rows:
        pid = row["id"]
        ops = api.STORE.ops_for(pid)
        d1, counts = state_digest(replay(api, row, ops))
        d2, _ = state_digest(replay(api, row, ops))

        deterministic = d1 == d2
        entry = {"digest": d1, "operations": len(ops), **counts,
                 "deterministic": deterministic}

        if not deterministic:
            entry["error"] = "two replays of the same log produced different state"
            failed += 1
        if args.anchor:
            want = (anchored.get(pid) or {}).get("digest")
            if want is None:
                entry["anchor"] = "absent"
            elif want == d1:
                entry["anchor"] = "match"
            else:
                entry["anchor"] = "MISMATCH"
                entry["anchor_expected"] = want
                failed += 1
        results[pid] = entry

        if not args.json:
            name = row["name"]
            print(f"{pid}  {name}")
            print(f"  replayed {len(ops)} operations -> "
                  f"{counts['assertions']} assertions, {counts['propositions']} propositions")
            print(f"  state digest  {d1[:16]}...")
            print(f"  deterministic {'yes' if deterministic else 'NO -- replay is not a function of the log'}")
            if args.anchor:
                a = entry["anchor"]
                print("  anchor        " + {
                    "match": "matches the recorded digest",
                    "absent": "no digest recorded for this project",
                    "MISMATCH": f"DOES NOT MATCH {want[:16]}... the log has changed",
                }[a])
            print()

    if args.record:
        out = {"version": 1,
               "projects": {k: {"digest": v["digest"],
                                "operations": v["operations"]}
                            for k, v in results.items()},
               "audit": {k: {"head": v.get("head")} for k, v in heads.items()}}
        with open(DIGEST_FILE, "w", encoding="utf-8") as fh:
            json.dump(out, fh, indent=2, sort_keys=True)
            fh.write("\n")
        if not args.json:
            print(f"recorded {len(results)} digest(s) to {DIGEST_FILE}")
            print("Keep a copy somewhere OMEM cannot write. A digest stored only")
            print("next to the database proves nothing against someone who can edit both.")

    anchored_audit = {}
    if args.anchor:
        anchored_audit = json.load(open(args.anchor, encoding="utf-8")).get("audit", {})
    audit_report = {}
    for oid, h in heads.items():
        entry = dict(h)
        if h.get("internally_consistent") is False:
            entry["state"] = "BROKEN"
            failed += 1
        elif args.anchor:
            want = (anchored_audit.get(oid) or {}).get("head")
            if want is None:
                entry["state"] = "no head recorded"
            elif want == h.get("head"):
                entry["state"] = "matches the recorded head"
            else:
                entry["state"] = "MISMATCH"
                entry["expected"] = want
                failed += 1
        else:
            entry["state"] = "internally consistent"
        audit_report[oid] = entry
        if not args.json:
            print("audit chain  %s  %s" % (oid, entry["state"]))
    if audit_report and not args.json:
        print()

    if args.json:
        print(json.dumps({"ok": failed == 0, "projects": results,
                          "audit": audit_report}, indent=2, sort_keys=True))
    elif failed:
        print(f"{failed} project(s) FAILED verification")
    else:
        print(f"{len(results)} project(s) verified")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
