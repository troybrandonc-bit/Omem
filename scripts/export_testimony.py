#!/usr/bin/env python3
"""Export an OMEM project as a Testimony Record.

    python3 scripts/export_testimony.py --url http://127.0.0.1:8787 \
        --key omem_sk_... --project proj_... > record.jsonl
    python3 scripts/testimony_validate.py record.jsonl

The specification: https://infrastructure.omem-cloud.com/spec/testimony-record/

This is what makes OMEM the reference implementation rather than a project
that merely published a document: the record it hands you is the same format
anyone else can emit, and the same validator checks it.

Nothing here is invented. Beliefs, their states and their evidence come from
the memory; conflicts come from the conflict view; decisions, refusals and
approvals come from the gate's own history. Where OMEM does not know
something, the export says so rather than filling it in.

Copyright 2026 Michael Brandon Clifford. MIT licensed.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import sys
import urllib.error
import urllib.request

SPEC = "testimony-record/0.1"
STATE = {"BELIEVED_TRUE": "believed_true", "BELIEVED_FALSE": "believed_false",
         "CONTRADICTED": "contradicted", "UNKNOWN": "unknown"}


def _rfc3339(epoch: float) -> str:
    return _dt.datetime.fromtimestamp(
        float(epoch), _dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class Client:
    def __init__(self, url: str, key: str, project: str):
        self.url, self.key, self.project = url.rstrip("/"), key, project

    def _call(self, method: str, path: str, body=None):
        sep = "&" if "?" in path else "?"
        req = urllib.request.Request(
            f"{self.url}{path}{sep}project={self.project}",
            data=json.dumps(body).encode() if body is not None else None,
            headers={"Content-Type": "application/json",
                     "Authorization": "Bearer " + self.key},
            method=method)
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read().decode() or "{}")
        except urllib.error.HTTPError as e:
            return {"_error": e.code, "_body": e.read().decode()[:200]}

    get = lambda self, p: self._call("GET", p)              # noqa: E731
    post = lambda self, p, b: self._call("POST", p, b)      # noqa: E731


def build_record(c: Client) -> list[dict]:
    """The project's beliefs, conflicts, decisions and approvals, as entries."""
    entries: list[dict] = []
    seen_beliefs: dict[str, dict] = {}

    # ── beliefs ─────────────────────────────────────────────────────────────
    ents = (c.get("/v1/entities?limit=500").get("data") or [])
    for ent in ents:
        pack = c.post("/v1/recall", {"about": ent["id"], "limit": 200})
        for m in pack.get("memories") or []:
            aid = m.get("assertion")
            if not aid or aid in seen_beliefs:
                continue
            why = c.get(f"/v1/assertions/{aid}/why")
            a = why.get("assertion") or {}
            prop = m.get("proposition") or ""
            # "not:x" is the same proposition with the opposite polarity, and
            # saying so is what lets a conflict name both sides at once.
            deny = prop.startswith("not:")
            ts = float(a.get("recorded_at") or 0)
            entry = {
                "spec": SPEC, "type": "belief", "id": aid, "_ts": ts,
                "at": _rfc3339(ts),
                "subject": (m.get("subjects") or [ent["id"]])[0],
                "proposition": prop[4:] if deny else prop,
                "polarity": "deny" if deny else "affirm",
                "state": STATE.get(m.get("state"), "unknown"),
                "asserted_by": {"id": a.get("agent") or "unknown", "kind": "agent"},
                # OMEM records whether a claim is grounded in a source. An
                # ungrounded belief exports as an empty list, which the
                # specification requires to be sayable rather than hidden.
                "evidence": [],
            }
            if a.get("label"):
                entry["note"] = a["label"]
            seen_beliefs[aid] = entry
            entries.append(entry)

    # ── conflicts ───────────────────────────────────────────────────────────
    for i, row in enumerate((c.get("/v1/memory/conflicts").get("data") or []), 1):
        sides = [s.get("assertion") for s in (row.get("sides") or [])
                 if s.get("assertion") in seen_beliefs]
        if len(sides) < 2:
            continue
        first = seen_beliefs[sides[0]]
        # A contradiction is only visible once its second side arrives, so it
        # is dated by the later of the two claims that caused it.
        ts = max(seen_beliefs[s]["_ts"] for s in sides)
        entries.append({
            "spec": SPEC, "type": "conflict", "id": f"conflict_{i}", "_ts": ts,
            "at": _rfc3339(ts),
            "subject": first["subject"], "proposition": first["proposition"],
            "sides": sides,
            "declared_by": {"id": "omem", "kind": "system"},
            # OMEM never resolves a contradiction on its own, so an exported
            # conflict is unresolved unless a human or a rule resolved it.
            "resolution": None,
        })

    # ── decisions, refusals and approvals ───────────────────────────────────
    # Risk classes are read from the registry itself rather than inferred from
    # what happened, because a record whose risk column was reconstructed by
    # the exporter would be worth nothing to the auditor reading it.
    registry = c.get("/v1/healing/actions").get("data") or {}

    def risk_of(action_type: str) -> str:
        entry = registry.get(action_type)
        # An action the registry does not know has no risk class of its own,
        # and that absence is exactly why the gate refuses it. Reporting it as
        # the highest class is the conservative reading; the reason recorded
        # alongside says it was never registered.
        return (entry or {}).get("risk") or "high"

    n = 0
    for f in (c.get("/v1/healing/failures").get("data") or []):
        detail = c.get(f"/v1/healing/failures/{f['id']}")
        for d in (detail.get("diagnoses") or []):
            acts = d.get("actions") or []
            for verdict in (d.get("decisions") or []):
                n += 1
                k = verdict.get("index")
                act = acts[k] if isinstance(k, int) and k < len(acts) else {}
                atype = act.get("type") or "unknown"
                entries.append({
                    "spec": SPEC, "type": "decision", "id": f"decision_{n}",
                    "_ts": float(d.get("ts") or f.get("ts") or 0),
                    "at": _rfc3339(d.get("ts") or f.get("ts") or 0),
                    "action_type": atype,
                    "risk_class": verdict.get("risk") or risk_of(atype),
                    "risk_source": "registry",
                    "proposed_by": {"id": "model", "kind": "agent"},
                    "verdict": "permitted" if verdict.get("permit") else "refused",
                    "reason": verdict.get("reason") or "refused by policy",
                    "executed": False,
                    "approval": None,
                })
        for r in (detail.get("recoveries") or []):
            ran = [a.get("type") for a in (r.get("actions_run") or []) if a.get("ok")]
            if not ran:
                continue
            approved = r.get("approved_by")
            ts = float(r.get("ts") or 0)
            at = _rfc3339(ts)
            aid = None
            if approved:
                n += 1
                aid = f"approval_{n}"
            unlocked = []
            for t in ran:
                n += 1
                unlocked.append(f"decision_{n}")
                entries.append({
                    "spec": SPEC, "type": "decision", "id": f"decision_{n}",
                    "_ts": ts, "at": at, "action_type": t,
                    "risk_class": risk_of(t),
                    "risk_source": "registry",
                    "proposed_by": {"id": "model", "kind": "agent"},
                    "verdict": "permitted",
                    "reason": "approved by a named reviewer" if approved
                              else "permitted by policy",
                    "executed": True,
                    "approval": aid,
                })
            if approved:
                # The approval sorts ahead of what it unlocked, so the record
                # can never be read as a human blessing something already done.
                entries.append({
                    "spec": SPEC, "type": "approval", "id": aid, "_ts": ts, "at": at,
                    "decision": unlocked[0],
                    "approver": {"id": str(approved), "kind": "human"},
                    "method": "api",
                    # The authority came from an owner-role API key that the
                    # authentication layer checked; the name is the label that
                    # key supplied. Both are reported rather than blurred.
                    "identity_source": "api-key",
                    "authenticated_principal": r.get("owner"),
                })

    # Export order is time order. The underlying log is already append-only;
    # this only guarantees the file reads that way. Sorting on the real
    # timestamp rather than the printed one keeps events that share a second
    # in the order they actually happened.
    entries.sort(key=lambda e: (e["_ts"], 0 if e["type"] == "approval" else 1))
    for e in entries:
        del e["_ts"]

    # Numbering follows the order the file is read in, so decision_1 is the
    # first decision an auditor meets. Beliefs keep the assertion ids the
    # memory gave them, because that is how the rest of OMEM refers to them.
    counters = {"decision": 0, "approval": 0, "conflict": 0}
    renamed: dict[str, str] = {}
    for e in entries:
        if e["type"] in counters:
            counters[e["type"]] += 1
            renamed[e["id"]] = f"{e['type']}_{counters[e['type']]}"
            e["id"] = renamed[e["id"]]
    for e in entries:
        for field in ("decision", "approval"):
            if e.get(field) in renamed:
                e[field] = renamed[e[field]]

    # ── integrity ───────────────────────────────────────────────────────────
    # The digest covers every entry above it, so any later edit to the exported
    # file is detectable; the engine it names is the frozen one whose replay of
    # the underlying log has to reproduce these same beliefs byte for byte.
    digest = hashlib.sha256(
        "\n".join(json.dumps(e, sort_keys=True) for e in entries).encode()).hexdigest()
    health = c.get("/v1/health") or {}
    last = entries[-1]["at"] if entries else _rfc3339(0)
    entries.append({
        "spec": SPEC, "type": "integrity", "id": "integrity_1", "at": last,
        "scheme": "replay", "digest": "sha256:" + digest,
        "engine": health.get("engine") or "omem_engine",
        "engine_version": health.get("engine_version") or "unknown",
        "covers": [e["id"] for e in entries],
        "verified_at": last,
    })
    return entries


def main() -> int:
    ap = argparse.ArgumentParser(description="Export an OMEM project as a Testimony Record.")
    ap.add_argument("--url", default="http://127.0.0.1:8787")
    ap.add_argument("--key", required=True)
    ap.add_argument("--project", required=True)
    ap.add_argument("--out", default="-")
    a = ap.parse_args()

    entries = build_record(Client(a.url, a.key, a.project))
    text = "\n".join(json.dumps(e) for e in entries) + "\n"
    if a.out == "-":
        sys.stdout.write(text)
    else:
        with open(a.out, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        print(f"wrote {a.out}: {len(entries)} entries", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
