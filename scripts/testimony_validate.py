#!/usr/bin/env python3
"""Validate a Testimony Record and report the conformance level it reaches.

    python3 scripts/testimony_validate.py record.jsonl
    python3 scripts/testimony_validate.py record.jsonl --require TR-3
    python3 scripts/testimony_validate.py record.jsonl --json

The specification: https://infrastructure.omem-cloud.com/spec/testimony-record/

This is the reference validator, and it is deliberately boring: standard
library only, one file, no network. Copy it into your own repository and run it
in your own CI if that is easier than depending on ours. A conformance claim
that cannot be checked by the person hearing it is just an adjective.

What it checks is what a JSON Schema cannot: the relationships between entries.
A schema can say a belief has an evidence field. Only a validator can say the
evidence it cites exists, that both sides of a contradiction are still in the
record, that the risk class did not come from the model proposing the action,
and that the approver was a person the auth layer named.

Copyright 2026 Michael Brandon Clifford. MIT licensed.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import re
import sys

SPEC = "testimony-record/0.2"
SPECS = ("testimony-record/0.1", "testimony-record/0.2")
LEVELS = ["TR-1", "TR-2", "TR-3", "TR-4"]
TYPES = {"belief", "evidence", "conflict", "decision", "approval", "integrity",
         "scope"}

# `scope` exists because this validator was refusing a level to systems that
# had earned it. TR-3 required at least one decision entry, on the reasoning
# that a record with no decisions cannot demonstrate a gate. True, and it meant
# a system which takes no actions at all could never pass TR-3, and since the
# ladder is cumulative its integrity at TR-4 stayed invisible however good it
# was. A record-only system with a real hash chain reported TR-2.
#
# Reported by Phill Clapham on 4 September 2026, who is that case: a chained
# audit, no actuation gate, and no need for one. The check it failed appears
# nowhere in the specification text, which says only that every consequential
# action produces a decision entry, and a system with no consequential actions
# satisfies that by having none.
#
# The check is still worth having, because without it a system that does act
# passes TR-3 by omitting its decisions. So the record declares whether the
# system acts, and the validator believes it. That declaration is visible in
# the reported level for the same reason the census reports what a subject
# claims: "TR-4, record only" is a different sentence from "TR-4".
#
# 0.1 records have no scope entry and are validated exactly as before.
RFC3339 = re.compile(
    r"^\d{4}-\d{2}-\d{2}[Tt]\d{2}:\d{2}:\d{2}(\.\d+)?([Zz]|[+-]\d{2}:\d{2})$")

# Identity that the proposing model could have written is not identity.
#
# These were a denylist until 5 September 2026, which meant any word not on it
# passed. `identity_source: "the-model-said-so"` reached TR-4, and so did
# "vibes". A denylist over a string the emitter chooses is not a check, it is a
# spelling test, and this one could be passed by a system announcing in the
# field itself that the model supplied the name.
#
# They are allowlists now. A source outside the list is not refused outright,
# because a real deployment may authenticate in a way nobody here thought of,
# but it must be declared as an extension with an `x-` prefix so that it is
# visible as one rather than indistinguishable from a standard source.
#
# What this cannot become is proof. Every value is still the emitter's word,
# which is why both checks report as attested however the field is spelled.
UNTRUSTED_SOURCES = {"model", "plan", "request", "request-body", "prompt", "agent"}

RISK_SOURCES = {"registry", "policy", "catalogue", "catalog", "configuration",
                "config", "regulation", "operator", "human"}
IDENTITY_SOURCES = {"auth-session", "session", "api-key", "jwt", "oidc",
                    "oauth", "saml", "mtls", "webauthn", "passkey",
                    "signed-token", "directory", "sso", "ldap", "kerberos"}


# ── how a digest is computed ────────────────────────────────────────────────
#
# This was undefined until 5 September 2026. The draft said only that the
# digest was "the value under which alteration would be detected", which names
# no algorithm, no serialisation and no ordering, so two conforming
# implementations would compute different digests for the same record and no
# reader could recompute either. A verifiable level whose arithmetic is a
# secret of one implementation is not verifiable.
#
# The rule, in full, so that it can be implemented from this comment alone:
#
#   1. Take the entries the integrity entry `covers`, in the order it lists
#      them.
#   2. Serialise each as JSON with no insignificant whitespace, with members
#      ordered by name, compared as sequences of Unicode code points, and with
#      members whose names begin with U+005F LOW LINE omitted, those being
#      reader annotations rather than record content.
#   3. Join them with a single U+000A LINE FEED, with none at the end.
#   4. Encode as UTF-8 and take the SHA-256. The digest is "sha256:" followed
#      by the lowercase hex.
#
# Member names defined by this specification are ASCII, so ordering by code
# point and ordering by UTF-16 code unit as RFC 8785 does cannot differ for
# them. An extension using non-ASCII member names should expect that they can.
SEP = "\n"


# Numbers are the one place two languages can serialise the same value into
# different bytes. Python writes 1.0 where ECMAScript writes 1, and 1e-05 where
# ECMAScript writes 0.00001. The digest would differ, and only when somebody
# finally checked, which is the failure this whole change is about.
#
# Whole numbers are written without a fraction, as ECMAScript does. Outside the
# range where the two agree exactly, the value is refused rather than hashed
# into a digest the other language cannot reproduce. No plausible field in this
# format lives out there, and a refusal is recoverable where a silent
# disagreement is not.
# Below 1e-4 Python writes an exponent and ECMAScript writes the digits out;
# at or above 1e21 both write an exponent but reach it by different routes, and
# beyond 2**53 an integer does not survive a round trip through ECMAScript at
# all. Between those bounds the two agree character for character, which is
# checked against node rather than assumed.
NUM_MIN, NUM_MAX = 1e-4, 1e21
SAFE_INT = 2 ** 53


def _number(v):
    if isinstance(v, bool):
        return v
    if isinstance(v, int):
        if abs(v) > SAFE_INT:
            raise ValueError("%d does not survive a round trip through "
                             "ECMAScript, so no digest over it is portable" % v)
        return v
    f = float(v)
    if f != f or f in (float("inf"), float("-inf")):
        raise ValueError("a digest cannot cover %r" % f)
    if f.is_integer() and abs(f) < NUM_MAX:
        return int(f)
    if not (NUM_MIN <= abs(f) < NUM_MAX):
        raise ValueError("%r is outside the range where Python and ECMAScript "
                         "write a number the same way" % f)
    return f


def _plain(v):
    if isinstance(v, dict):
        return {k: _plain(x) for k, x in v.items() if not k.startswith("_")}
    if isinstance(v, list):
        return [_plain(x) for x in v]
    if isinstance(v, (int, float)):
        return _number(v)
    return v


def canonical(entry: dict) -> str:
    return json.dumps(_plain(entry), sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False)


def digest_of(entries: list) -> str:
    return hashlib.sha256(
        SEP.join(canonical(e) for e in entries).encode("utf-8")).hexdigest()


# The DER of an AlgorithmIdentifier's SHA-256 OID, which in an RFC 3161 token
# is followed by the hashed message it was taken over. Parsing this much of a
# timestamp does not need a certificate library, and refusing to check it at
# all was how a token over somebody else's record used to pass.
_SHA256_OID = bytes.fromhex("0609608648016503040201")


def _imprints(token: bytes) -> list:
    """Every SHA-256 message imprint in a TimeStampResp."""
    out, i = [], 0
    while True:
        i = token.find(_SHA256_OID, i)
        if i < 0:
            return out
        j = i + len(_SHA256_OID)
        if token[j:j + 2] == b"\x05\x00":      # absent parameters, as NULL
            j += 2
        if token[j:j + 2] == b"\x04\x20":      # OCTET STRING, 32 bytes
            out.append(token[j + 2:j + 34])
        i = j


def _declared(value: object, allowed: set) -> str:
    """Empty, an extension, a known source, or none of these.

    Returns "" when the value is acceptable, and the reason when it is not.
    """
    v = str(value or "").strip().lower()
    if not v:
        return "not stated"
    if v in UNTRUSTED_SOURCES:
        return "%r is the proposing side of the same system" % v
    if v.startswith("x-"):
        return "" if len(v) > 2 else "'x-' names no extension"
    if v not in allowed:
        return ("%r is not a known source; an unlisted one is written as "
                "'x-%s'" % (v, v))
    return ""


class Report:
    def __init__(self):
        self.checks: list[dict] = []
        self.level: str | None = None
        self.spec: str = SPEC
        self.scope: str = "acts"

    def add(self, level: str, name: str, ok: bool, detail: str = "", *,
            basis: str):
        """Record a check and, as importantly, what kind of check it was.

        `verified` means a reader can confirm it from the record alone:
        structure, references between entries, or arithmetic over the bytes.
        `attested` means the record asserts it and no reader can check it here,
        as with a field naming where a risk class came from.

        There is no default. A validator that quietly treats a new attestation
        as proof is the failure this format exists to report in other systems,
        and it would be reported here as a level rather than as a caveat.
        """
        if basis not in ("verified", "attested"):
            raise ValueError("basis must be 'verified' or 'attested'")
        self.checks.append({"level": level, "check": name, "ok": ok,
                            "detail": detail, "basis": basis})

    def failures(self, level: str) -> list[dict]:
        return [c for c in self.checks if c["level"] == level and not c["ok"]]

    def as_dict(self) -> dict:
        return {"spec": self.spec, "level": self.level, "scope": self.scope,
                "levels_met": {lvl: not self.failures(lvl) for lvl in LEVELS},
                "basis": {lvl: self.basis(lvl) for lvl in LEVELS},
                "checks": self.checks}

    def basis(self, level: str) -> dict:
        """How much of a level was confirmed, and how much was taken on trust.

        A level reported without this is a number standing on an unknown
        mixture of the two.
        """
        at = [c for c in self.checks if c["level"] == level]
        return {"verified": sum(1 for c in at if c["basis"] == "verified"),
                "attested": sum(1 for c in at if c["basis"] == "attested")}


def _parse(text: str) -> tuple[list[dict], list[str]]:
    """Lines to entries, with the parse errors kept rather than raised."""
    entries, errors = [], []
    for i, line in enumerate(text.splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as e:
            errors.append(f"line {i}: not valid JSON ({e.msg})")
            continue
        if not isinstance(obj, dict):
            errors.append(f"line {i}: not a JSON object")
            continue
        obj["_line"] = i
        entries.append(obj)
    return entries, errors


REQUIRED = {
    "scope": ("acts",),
    "belief": ("subject", "proposition", "polarity", "state", "asserted_by"),
    "evidence": ("kind", "source"),
    "conflict": ("subject", "proposition", "sides"),
    "decision": ("action_type", "risk_class", "proposed_by", "verdict", "executed"),
    "approval": ("decision", "approver"),
    "integrity": ("scheme", "digest"),
}
ENUMS = {
    ("belief", "polarity"): {"affirm", "deny"},
    ("belief", "state"): {"believed_true", "believed_false", "contradicted", "unknown"},
    ("evidence", "kind"): {"document", "message", "event", "api", "human", "derived"},
    ("decision", "risk_class"): {"low", "medium", "high"},
    ("decision", "verdict"): {"permitted", "refused"},
    ("integrity", "scheme"): {"replay", "hash-chain", "signature", "external-anchor"},
}


def validate(text: str) -> Report:
    r = Report()
    entries, parse_errors = _parse(text)

    # ── TR-1: the record exists, is well formed, and is append-only ──────────
    r.add("TR-1", "every line parses as a JSON object", not parse_errors,
          "; ".join(parse_errors[:3]),
          basis="verified")
    r.add("TR-1", "the record is not empty", bool(entries),
          basis="verified")

    named = {e.get("spec") for e in entries}
    known = named & set(SPECS)
    bad_spec = [e for e in entries if e.get("spec") not in SPECS]
    r.add("TR-1", "every entry names a known specification version",
          bool(entries) and not bad_spec,
          f"{len(bad_spec)} entr(ies) with an unknown or missing spec field",
          basis="verified")
    r.add("TR-1", "the record names one specification version, not several",
          len(named) <= 1,
          f"mixed versions in one record: {sorted(x for x in named if x)}",
          basis="verified")
    if len(known) == 1:
        r.spec = known.pop()

    bad_type = [e for e in entries if e.get("type") not in TYPES]
    r.add("TR-1", "every entry has a known type", not bad_type,
          f"{len(bad_type)} unknown type(s)",
          basis="verified")

    missing = []
    for e in entries:
        for f in REQUIRED.get(e.get("type"), ()):
            if f not in e:
                missing.append(f"line {e['_line']}: {e.get('type')} missing '{f}'")
    r.add("TR-1", "required fields are present for each type", not missing,
          "; ".join(missing[:3]),
          basis="verified")

    bad_enum = []
    for e in entries:
        for (t, f), allowed in ENUMS.items():
            if e.get("type") == t and f in e and e[f] not in allowed:
                bad_enum.append(f"line {e['_line']}: {f}={e[f]!r}")
    r.add("TR-1", "enumerated fields use allowed values", not bad_enum,
          "; ".join(bad_enum[:3]),
          basis="verified")

    ids = [e.get("id") for e in entries if "id" in e]
    dupes = {i for i in ids if ids.count(i) > 1}
    r.add("TR-1", "entry ids are unique and never reused", not dupes,
          f"reused: {sorted(dupes)[:3]}",
          basis="verified")

    bad_time = [e for e in entries
                if not isinstance(e.get("at"), str) or not RFC3339.match(e.get("at", ""))]
    r.add("TR-1", "every entry has an RFC 3339 write time", not bad_time,
          f"{len(bad_time)} entr(ies) with a missing or malformed 'at'",
          basis="verified")

    times = [e["at"] for e in entries if isinstance(e.get("at"), str)]
    ordered = all(a <= b for a, b in zip(times, times[1:]))
    r.add("TR-1", "entries are in non-decreasing time order (append-only)", ordered,
          "an entry is written before the one above it, which an append-only "
          "record cannot do",
          basis="verified")

    by_type = {t: [e for e in entries if e.get("type") == t] for t in TYPES}
    by_id = {e["id"]: e for e in entries if "id" in e}

    # ── TR-2: beliefs resolve to evidence, disagreements survive ─────────────
    beliefs = by_type["belief"]
    no_field = [e for e in beliefs if "evidence" not in e]
    r.add("TR-2", "every belief states its evidence, even when there is none",
          not no_field,
          f"{len(no_field)} belief(s) omit the field; an ungrounded belief must "
          "say so explicitly with an empty list",
          basis="verified")

    dangling = []
    for e in beliefs:
        for ev in e.get("evidence", []) or []:
            if by_id.get(ev, {}).get("type") != "evidence":
                dangling.append(f"line {e['_line']}: cites {ev!r}")
    r.add("TR-2", "cited evidence exists in the record", not dangling,
          "; ".join(dangling[:3]),
          basis="verified")

    conflicts = by_type["conflict"]
    thin = [c for c in conflicts if len(c.get("sides") or []) < 2]
    r.add("TR-2", "each conflict names at least two sides", not thin,
          f"{len(thin)} conflict(s) with fewer than two sides",
          basis="verified")

    lost = []
    for c in conflicts:
        for s in c.get("sides") or []:
            if by_id.get(s, {}).get("type") != "belief":
                lost.append(f"line {c['_line']}: side {s!r} is not a belief in this record")
    r.add("TR-2", "both sides of every conflict are retained", not lost,
          "; ".join(lost[:3]),
          basis="verified")

    contradicted = {(e["subject"], e["proposition"]) for e in beliefs
                    if e.get("state") == "contradicted"}
    declared = {(c["subject"], c["proposition"]) for c in conflicts
                if "subject" in c and "proposition" in c}
    undeclared = contradicted - declared
    r.add("TR-2", "a contradicted belief has a conflict entry naming it",
          not undeclared, f"undeclared: {sorted(undeclared)[:3]}",
          basis="verified")

    bad_res = []
    for c in conflicts:
        res = c.get("resolution")
        if res in (None, {}):
            continue
        for f in ("method", "by", "at", "kept"):
            if f not in res:
                bad_res.append(f"line {c['_line']}: resolution missing '{f}'")
        if "kept" in res and res["kept"] not in (c.get("sides") or []):
            bad_res.append(f"line {c['_line']}: kept side is not one of the sides")
    r.add("TR-2", "a resolved conflict records who resolved it and what was kept",
          not bad_res, "; ".join(bad_res[:3]),
          basis="verified")

    # ── TR-3: actions carry a verdict, approvals carry a name ────────────────
    decisions = by_type["decision"]
    approvals = by_type["approval"]

    # What the emitting system says it does. Absent, the answer is "it acts",
    # which is what every 0.1 record means and keeps them validating unchanged.
    scopes = by_type["scope"]
    r.add("TR-1", "at most one scope entry", len(scopes) <= 1,
          f"{len(scopes)} scope entries; a record describes one system",
          basis="verified")
    declared = scopes[0] if scopes else None
    if declared is not None and declared.get("spec") == "testimony-record/0.1":
        r.add("TR-1", "scope is not used in a 0.1 record", False,
              "the scope entry was introduced in testimony-record/0.2; a 0.1 "
              "record carrying one is claiming a version it does not name",
          basis="verified")
    acts = True if declared is None else bool(declared.get("acts"))
    r.scope = "acts" if acts else "record only"

    # A system that says it does not act, and then records actions, is not
    # describing itself. Catching that is what makes the declaration safe to
    # believe at all.
    r.add("TR-1", "a record that declares no actions contains none",
          acts or not decisions,
          f"scope says acts=false but the record carries {len(decisions)} "
          f"decision entr(ies)",
          basis="verified")

    if acts:
        r.add("TR-3", "the record contains at least one decision", bool(decisions),
              "a record from a system that acts, with no decisions in it, "
              "cannot demonstrate a gate. If this system does not act, say so "
              "with a scope entry rather than leaving it to be inferred.",
          basis="verified")
    else:
        r.add("TR-3", "no decisions required: the system declares it does not act",
              True, "",
          basis="attested")

    self_declared = []
    for d in decisions:
        why = _declared(d.get("risk_source"), RISK_SOURCES)
        if why:
            self_declared.append(f"line {d['_line']}: {why}")
    r.add("TR-3", "the risk class is declared to come from outside the "
                  "proposing model", not self_declared,
          "; ".join(self_declared[:3]),
          basis="attested")

    ran_anyway = [d for d in decisions
                  if d.get("verdict") == "refused" and d.get("executed") is True]
    r.add("TR-3", "a refused action did not execute", not ran_anyway,
          f"{len(ran_anyway)} refused decision(s) recorded as executed",
          basis="verified")

    no_reason = [d for d in decisions
                 if d.get("verdict") == "refused" and not d.get("reason")]
    r.add("TR-3", "every refusal records its reason", not no_reason,
          f"{len(no_reason)} refusal(s) without a reason",
          basis="verified")

    unapproved = []
    for d in decisions:
        if d.get("risk_class") == "high" and d.get("executed") is True:
            a = by_id.get(d.get("approval") or "", {})
            if a.get("type") != "approval" or a.get("decision") != d.get("id"):
                unapproved.append(f"line {d['_line']}: {d.get('action_type')}")
    r.add("TR-3", "an executed high-risk action has an approval entry",
          not unapproved, "; ".join(unapproved[:3]),
          basis="verified")

    # These were one check until 5 September 2026, which reported a bundle of
    # things a reader can confirm together with one thing nobody can. Whether an
    # approver is named, is a person, and is somebody other than the proposer is
    # all decidable from the record. Where the name came from is not, and
    # reporting them jointly meant a level appeared to rest on evidence for a
    # part of itself that rests on a declaration.
    bad_approver = []
    for a in approvals:
        who = a.get("approver") or {}
        if who.get("kind") != "human":
            bad_approver.append(f"line {a['_line']}: approver kind {who.get('kind')!r}")
        if not str(who.get("id") or "").strip():
            bad_approver.append(f"line {a['_line']}: approver names nobody")
        approved = by_id.get(a.get("decision") or "", {})
        if approved.get("type") != "decision":
            bad_approver.append(f"line {a['_line']}: approves a decision not in the record")
        else:
            # An approver who is also the proposer satisfies every other
            # requirement here and is worth nothing. A system that lets the
            # acting agent's own credential sign off its action does not meet
            # this level, however the name in the entry is spelled.
            proposer = (approved.get("proposed_by") or {}).get("id")
            if proposer and proposer == who.get("id"):
                bad_approver.append(
                    f"line {a['_line']}: approver is the proposer {proposer!r}")
    r.add("TR-3", "an approval names a person, other than the proposer, for a "
                  "decision in the record", not bad_approver,
          "; ".join(bad_approver[:3]),
          basis="verified")

    unsourced = []
    for a in approvals:
        why = _declared(a.get("identity_source"), IDENTITY_SOURCES)
        if why:
            unsourced.append(f"line {a['_line']}: {why}")
    r.add("TR-3", "the approver's name is declared to come from authentication",
          not unsourced, "; ".join(unsourced[:3]),
          basis="attested")

    # ── TR-4: the record can be shown not to have changed ────────────────────
    integrity = by_type["integrity"]
    r.add("TR-4", "the record publishes an integrity scheme", bool(integrity),
          "no integrity entry, so nothing states how alteration would be detected",
          basis="verified")

    weak = [g for g in integrity if not g.get("digest")]
    r.add("TR-4", "every integrity entry carries a digest", not weak,
          f"{len(weak)} integrity entr(ies) without one",
          basis="verified")

    unnamed = [g for g in integrity
               if g.get("scheme") == "replay" and not (g.get("engine")
                                                       and g.get("engine_version"))]
    r.add("TR-4", "a replay scheme names the engine and its version", not unnamed,
          f"{len(unnamed)} replay entr(ies) that cannot be reproduced by a third party",
          basis="attested")

    # An external anchor is the one scheme whose evidence somebody else holds,
    # which is the whole reason it is worth more than a digest the producer
    # computed. Saying "external-anchor" without naming who anchored it, or
    # without the token they returned, is the claim without the thing.
    hollow = []
    for g in integrity:
        if g.get("scheme") != "external-anchor":
            continue
        a = g.get("anchor")
        if not isinstance(a, dict):
            hollow.append(f"line {g['_line']}: no anchor object")
            continue
        for f in ("kind", "authority", "token"):
            if not a.get(f):
                hollow.append(f"line {g['_line']}: anchor missing {f!r}")
    r.add("TR-4", "an external anchor names its authority and carries its token",
          not hollow, "; ".join(hollow[:3]),
          basis="verified")

    stale = []
    for g in integrity:
        for cid in g.get("covers") or []:
            if cid not in by_id:
                stale.append(f"line {g['_line']}: covers {cid!r}, not in the record")
    r.add("TR-4", "integrity entries cover entries that exist", not stale,
          "; ".join(stale[:3]),
          basis="verified")

    # Until 5 September 2026 nothing here recomputed anything. The level called
    # Verifiable was reached by a digest of sixty-four zeros, because the checks
    # asked whether a digest was present and never whether it was the digest of
    # this record. An anchored record could carry a real, correctly signed token
    # over some entirely different record and pass.
    #
    # Both are arithmetic over bytes already in the file, so both are verified
    # in the strict sense: a reader disagreeing with this validator can settle
    # it without asking anyone.
    # `covers` is optional in the format, because a record may carry an
    # integrity entry for its own purposes. It is required to reach this level,
    # because a digest that does not say what it is over cannot be recomputed by
    # anybody, and leaving it optional here would have made every check below it
    # skippable by deleting one field.
    silent = [f"line {g['_line']}" for g in integrity if not g.get("covers")]
    r.add("TR-4", "an integrity entry says which entries its digest is over",
          not silent, "; ".join(silent[:3]),
          basis="verified")

    wrong = []
    for g in integrity:
        if not g.get("covers"):
            continue
        try:
            covered = [by_id[cid] for cid in g["covers"]]
        except KeyError:
            continue                        # already reported as stale, above
        want = str(g.get("digest") or "")
        try:
            got = "sha256:" + digest_of(covered)
        except ValueError as e:
            # A value no two implementations would serialise alike. Saying so
            # is more use than a digest mismatch nobody can account for.
            wrong.append(f"line {g['_line']}: {e}")
            continue
        if want != got:
            wrong.append(f"line {g['_line']}: says {want[:22]}.., covers {got[:22]}..")
    r.add("TR-4", "a digest is the digest of the entries it covers", not wrong,
          "; ".join(wrong[:3]),
          basis="verified")

    adrift = []
    for g in integrity:
        if g.get("scheme") != "external-anchor":
            continue
        a = g.get("anchor") if isinstance(g.get("anchor"), dict) else {}
        tok, want = a.get("token"), str(g.get("digest") or "")
        if not tok or not want.startswith("sha256:"):
            continue                        # already reported as hollow, above
        try:
            raw = base64.b64decode(tok, validate=True)
        except Exception:                                       # noqa: BLE001
            adrift.append(f"line {g['_line']}: the token is not base64")
            continue
        found = _imprints(raw)
        if not found:
            adrift.append(f"line {g['_line']}: no SHA-256 imprint in the token")
        elif bytes.fromhex(want[7:]) not in found:
            adrift.append(f"line {g['_line']}: the authority signed a different "
                          f"digest ({found[0].hex()[:16]}..)")
    r.add("TR-4", "the anchor's authority signed this record's digest",
          not adrift, "; ".join(adrift[:3]),
          basis="verified")

    # ── the level reached is the highest with nothing failing below it ───────
    reached = None
    for lvl in LEVELS:
        if r.failures(lvl):
            break
        reached = lvl
    r.level = reached
    return r


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Validate a Testimony Record and report its conformance level.")
    ap.add_argument("record", help="path to a .jsonl record, or - for stdin")
    ap.add_argument("--require", choices=LEVELS, default=None,
                    help="exit non-zero unless the record reaches this level")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    a = ap.parse_args()

    text = sys.stdin.read() if a.record == "-" else open(
        a.record, encoding="utf-8").read()
    r = validate(text)

    if a.json:
        print(json.dumps(r.as_dict(), indent=1))
    else:
        # Grouped by level rather than printed in the order the checks were
        # added. The scope checks belong to TR-1 and are computed alongside the
        # decisions at TR-3, so insertion order printed a second TR-1 heading
        # halfway down the report.
        for lvl in LEVELS:
            here = [c for c in r.checks if c["level"] == lvl]
            if not here:
                continue
            print(f"\n{lvl}")
            for c in here:
                mark = "ok  " if c["ok"] else "FAIL"
                print(f"  {mark} {c['check']}")
                if not c["ok"] and c["detail"]:
                    print(f"       {c['detail']}")
        scope = "" if r.scope == "acts" else f", {r.scope}"
        print("\nConformance: " + (r.level or "none, TR-1 not met") + scope)

        # Every level's own result, always. The ladder is cumulative, so a
        # level can be satisfied and not reached, and the old output threw
        # that away: a record-only system with a real hash chain was told
        # TR-2 and never told its integrity had passed. Printing what was
        # already computed costs nothing, and not printing it cost somebody
        # three weeks of thinking their chain was invisible.
        met = {lvl: not r.failures(lvl) for lvl in LEVELS}
        print("Per level:   " + "   ".join(
            f"{lvl} {'met' if met[lvl] else 'not met'}" for lvl in LEVELS))

        if r.level:
            higher = [lvl for lvl in LEVELS
                      if met[lvl] and LEVELS.index(lvl) > LEVELS.index(r.level)]
            if higher:
                print("\n" + ", ".join(higher) + " "
                      + ("is" if len(higher) == 1 else "are")
                      + " satisfied but not reached, because the levels are "
                        "cumulative and a\nlevel below is not met. The checks "
                        "are listed above either way.")

        if r.level and r.level != "TR-4":
            nxt = LEVELS[LEVELS.index(r.level) + 1]
            print(f"\nTo reach {nxt}, fix:")
            for c in r.failures(nxt):
                print(f"  - {c['check']}")

    if a.require:
        ok = r.level is not None and LEVELS.index(r.level) >= LEVELS.index(a.require)
        return 0 if ok else 1
    return 0 if r.level else 1


if __name__ == "__main__":
    sys.exit(main())
