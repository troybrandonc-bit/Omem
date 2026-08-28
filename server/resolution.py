"""Identity resolution: OMEM notices two entities are one person.

The frozen engine has carried full coreference machinery from the start --
merge (corefer), split, a referent partition every query reduces subject sets
through -- and nothing above it ever proposed a merge. Two entities became one
referent only when a caller worked out the duplication and called
/v1/coreference by hand, which in practice meant never. So a project
accumulated person:sarah (named in a body: "managed by Sarah") next to
person:sarah_chen@acme (who wrote the mail), each holding half the beliefs
about one human, unable to corroborate or contradict each other.

This module is the missing proposer. It scans a project's person entities for
pairs that are plausibly one referent and does one of two things:

  MERGE     only when the evidence is decisive: the same full name inside the
            same organisation. This is not a new judgment -- formation already
            makes it. infer_employment mints person:sarah_chen@acme for every
            mail Sarah Chen sends from acme.com, so the same full name at the
            same organisation ALREADY collapses to one id whenever one path
            forms it. Two ids with one full name and one organisation exist
            only because two formation paths minted them separately; merging
            them applies formation's own identity rule across paths, it does
            not invent a looser one. Recorded through the ordinary op path as
            a coreference assertion by agent:omem-resolution, with a
            derivation to the assertions anchoring both entities to the
            organisation, so /why answers for the merge like any other
            conclusion. Wrong is recoverable: a merge is a belief with an
            interval, and a split closes it without editing history.

  PROPOSE   when the evidence is suggestive: a bare given name matching one
            full name in the same organisation ("Sarah" against "Sarah Chen"
            at acme, and nobody else there is a Sarah). The pair goes into
            merge_proposals and NOTHING reaches the engine until a caller
            approves it, attributed to the approving agent.

Everything else is a refusal, and the refusals are the design:

  never across organisations     a shared name is not a shared identity
  never without an organisation  nothing anchors "Sarah" to "Sarah"
  never on conflicting names     Sarah Chen is not Sarah Miller
  never on role vocabulary       "Billing" and "Support" are not people
  never when ambiguous           two Sarahs at acme means propose neither
  never against a split          a closed coreference is a person saying
                                 "these are different"; the machine does not
                                 relitigate that, not even through approve()
  never twice                    a rejected proposal stays rejected; a pair
                                 already in one referent class is skipped

Formation-time resolution (connectors.EntityResolver) maps a raw signal to an
entity id BEFORE anything is stored. This module reconciles ids AFTER
formation, when two paths minted two ids for one human. Different job,
deliberately separate.

The engine stays the sole authority. Everything here goes through record()
as ordinary corefer/derive ops, so replay reconstructs every merge, as_of
shows the partition before and after, and omem_engine/ is untouched.
"""
from __future__ import annotations

import hashlib
import itertools
import json
import time

from extraction import ROLE_WORDS

RESOLUTION_AGENT = "agent:omem-resolution"

# Proposals are records of machine suggestions awaiting human judgment. They
# live beside the engine, never inside it: an unapproved proposal changes no
# answer to any query.
MERGE_SCHEMA = """
CREATE TABLE IF NOT EXISTS merge_proposals(
  id TEXT NOT NULL, project_id TEXT NOT NULL,
  entity_a TEXT NOT NULL, entity_b TEXT NOT NULL,
  confidence REAL NOT NULL, evidence TEXT NOT NULL, support TEXT NOT NULL,
  status TEXT NOT NULL, created REAL NOT NULL,
  decided REAL, decided_by TEXT, coreference_id TEXT,
  PRIMARY KEY(project_id, id));
"""

# The auto tier merges on formation's own rule (see module docstring); the
# given tier is a suggestion. Both numbers sit below spoken-statement
# confidence (0.75+) on purpose: identity inferred from records is never
# stronger evidence than a person saying who they are.
CONF_FULL = 0.7
CONF_GIVEN = 0.5


def _pair_id(project_id: str, a: str, b: str) -> str:
    return "mp_" + hashlib.sha256(f"{project_id}|{a}|{b}".encode()).hexdigest()[:12]


def _name_words(p, eid: str) -> tuple:
    """The words of an entity's human name, lowercased.

    The label is what a person actually presented ("Sarah Chen"); the id local
    part is the fallback for entities formed without one (person:sarah ->
    "sarah"). Punctuation-only or empty names come back as ()."""
    meta = p.labels.get(eid)
    label = meta.get("label") if isinstance(meta, dict) else None
    if not label:
        label = eid.split(":", 1)[-1].split("@", 1)[0].replace("_", " ").replace("-", " ")
    words = tuple(w.lower().rstrip(".") for w in str(label).replace(",", " ").split())
    return tuple(w for w in words if w)


def _plausible_person(words: tuple) -> bool:
    """One to four words, none of them role vocabulary. Reuses the same
    ROLE_WORDS the employment inference refuses on, so an entity that slipped
    past formation's person test still cannot merge as one."""
    if not 1 <= len(words) <= 4:
        return False
    return not any(w in ROLE_WORDS for w in words)


def _name_tier(wa: tuple, wb: tuple):
    """'full' when both are the same multi-word name; 'given' when a bare
    given name matches a full name's first word (or two bare names agree);
    None otherwise. Two multi-word names that differ are None outright:
    conflicting surnames are a refusal, not a weaker match."""
    if len(wa) >= 2 and len(wb) >= 2:
        return "full" if wa == wb else None
    if len(wa) == 1 and len(wb) >= 2:
        return "given" if wa[0] == wb[0] else None
    if len(wb) == 1 and len(wa) >= 2:
        return "given" if wb[0] == wa[0] else None
    return "given" if wa and wa == wb else None


def _org_anchors(db, p, eid: str, T) -> tuple[set, list]:
    """The organisations this person is anchored to, with the assertion ids
    that anchor them. Two sources: any LIVE graph edge between the person and
    a company entity (relation-agnostic: works_at, managed_by and involves all
    place a person in an organisation's orbit), and the @org suffix formation
    puts in the id. The suffix carries no assertion, so it anchors context but
    supports no derivation."""
    orgs, support = set(), []
    for r in db.execute(
            "SELECT assertion_id, src, dst FROM memory_edges WHERE project_id=? "
            "AND (src=? OR dst=?) ORDER BY assertion_id", (p.id, eid, eid)):
        other = r["dst"] if r["src"] == eid else r["src"]
        if not other.startswith("company:"):
            continue
        a = p.engine.store.assertion(r["assertion_id"])
        if a is None:
            continue
        try:
            if not p.engine.ledger.is_open_at(a, T):
                continue
        except Exception:
            continue
        orgs.add(other)
        support.append((other, r["assertion_id"]))
    local = eid.split(":", 1)[-1]
    if "@" in local:
        orgs.add("company:" + local.rsplit("@", 1)[1])
    return orgs, support


def _coref_index(p, T) -> dict:
    """frozenset({a,b}) -> {"open": n, "closed": n} over every coreference
    assertion ever recorded for the pair. Closed and none open means a split:
    recorded human experience this module must never override."""
    idx: dict = {}
    for a in p.engine.store.assertions():
        if not (a.proposition or "").startswith("COREF("):
            continue
        pair = frozenset(a.subjects)
        if len(pair) != 2:
            continue
        slot = idx.setdefault(pair, {"open": 0, "closed": 0})
        try:
            slot["open" if p.engine.ledger.is_open_at(a, T) else "closed"] += 1
        except Exception:
            slot["closed"] += 1
    return idx


def _same_class(p, T, a: str, b: str) -> bool:
    for c in p.engine.referent_partition(T):
        if a in c:
            return b in c
    return False


def _ensure_agent(p, record):
    if RESOLUTION_AGENT not in p.labels:
        record(p, "agent", {"id": RESOLUTION_AGENT, "kind": "system",
                            "label": "OMEM identity resolution"})


def _apply_merge(p, db, scopes, record, mint, a: str, b: str,
                 agent: str, evidence: str, support: list) -> str:
    """One merge through the ordinary op path: corefer, then a derivation to
    the anchoring assertions when there are any (a derivation needs >=1
    antecedent, and an id-suffix anchor has none). Org scope, like every other
    machine conclusion, so the merge is as visible as what it merged."""
    cid = mint("cor")
    record(p, "corefer", {"id": cid, "entity_a": a, "entity_b": b,
                          "agent": agent, "assertion_time": p.tick()})
    if support:
        record(p, "derive", {"id": mint("d"), "consequent": cid,
                             "antecedents": sorted(set(support))[:8],
                             "dkind": "inference"})
    try:
        scopes.set(p.id, cid, "org", granted_by=agent)
    except Exception:
        pass
    return cid


def scan(p, db, scopes, record, mint, apply: bool = True) -> dict:
    """One deterministic, idempotent resolution pass. Real counts only.

    apply=False is a dry run: the report says what WOULD merge or be proposed
    and nothing is recorded anywhere, same contract as the memory scanner."""
    T = p.now()
    persons = {}
    for eid in sorted(p.labels):
        meta = p.labels.get(eid)
        if not (isinstance(meta, dict) and meta.get("kind") == "entity"):
            continue
        if not eid.startswith("person:"):
            continue
        words = _name_words(p, eid)
        if not _plausible_person(words):
            continue
        orgs, support = _org_anchors(db, p, eid, T)
        persons[eid] = (words, orgs, support)

    result = {"examined": len(persons), "merged": [], "proposed": [],
              "already_merged": 0, "refused": [], "dry_run": not apply}
    corefs = _coref_index(p, T)

    # First pass: every name-similar pair, classified. Ambiguity needs the
    # whole field of matches before any single one can be trusted, so nothing
    # is applied until the field is known.
    candidates = []
    given_partners: dict[str, set] = {}
    for a, b in itertools.combinations(sorted(persons), 2):
        wa, oa, sa = persons[a]
        wb, ob, sb = persons[b]
        tier = _name_tier(wa, wb)
        if tier is None:
            continue
        shared = oa & ob
        if not shared:
            reason = ("different organisations" if oa and ob
                      else "no organisation anchors the identity")
            result["refused"].append({"pair": [a, b], "reason": reason})
            continue
        hist = corefs.get(frozenset((a, b)), {"open": 0, "closed": 0})
        if hist["closed"] and not hist["open"]:
            result["refused"].append(
                {"pair": [a, b],
                 "reason": "a split recorded these as different people"})
            continue
        if hist["open"] or _same_class(p, T, a, b):
            result["already_merged"] += 1
            continue
        row = db.execute(
            "SELECT status FROM merge_proposals WHERE project_id=? AND id=?",
            (p.id, _pair_id(p.id, a, b))).fetchone()
        if row is not None and row["status"] == "rejected":
            result["refused"].append(
                {"pair": [a, b], "reason": "previously rejected by a caller"})
            continue
        if row is not None and row["status"] == "open" and tier == "given":
            result["proposed"].append({"proposal": _pair_id(p.id, a, b),
                                       "pair": [a, b], "existing": True})
            continue
        support = sorted({aid for org, aid in sa + sb if org in shared})
        candidates.append((a, b, tier, sorted(shared), support))
        if tier == "given":
            for short in ([a] if len(wa) == 1 else []) + ([b] if len(wb) == 1 else []):
                given_partners.setdefault(short, set()).add((a, b))

    for a, b, tier, shared, support in candidates:
        wa, wb = persons[a][0], persons[b][0]
        if tier == "given":
            ambiguous = any(len(given_partners.get(e, ())) > 1
                            for e in (a, b) if len(persons[e][0]) == 1)
            if ambiguous:
                result["refused"].append(
                    {"pair": [a, b],
                     "reason": "ambiguous: the name matches more than one person there"})
                continue
            evidence = (f'"{ " ".join(wa) }" matches the given name of '
                        f'"{ " ".join(wb) }" at {", ".join(shared)}, '
                        f"and nobody else there does")
            pid_ = _pair_id(p.id, a, b)
            if apply:
                db.execute(
                    "INSERT OR IGNORE INTO merge_proposals(id,project_id,entity_a,"
                    "entity_b,confidence,evidence,support,status,created) "
                    "VALUES(?,?,?,?,?,?,?,?,?)",
                    (pid_, p.id, a, b, CONF_GIVEN, evidence,
                     json.dumps(support), "open", time.time()))
                db.commit()
            result["proposed"].append({"proposal": pid_, "pair": [a, b],
                                       "evidence": evidence})
            continue
        evidence = f'same full name "{" ".join(wa)}" at {", ".join(shared)}'
        entry = {"pair": [a, b], "evidence": evidence}
        if apply:
            _ensure_agent(p, record)
            entry["coreference"] = _apply_merge(
                p, db, scopes, record, mint, a, b, RESOLUTION_AGENT,
                evidence, support)
        result["merged"].append(entry)
    return result


def list_proposals(db, project_id: str, status: str | None = None) -> list[dict]:
    q = "SELECT * FROM merge_proposals WHERE project_id=?"
    args = [project_id]
    if status:
        q += " AND status=?"
        args.append(status)
    out = []
    for r in db.execute(q + " ORDER BY created, id", args):
        d = dict(r)
        d["support"] = json.loads(d.get("support") or "[]")
        out.append(d)
    return out


def approve(p, db, scopes, record, mint, proposal_id: str, agent: str) -> dict:
    """Turn one open proposal into a real merge, attributed to the APPROVING
    agent -- the judgment is theirs, not the machine's. Refuses when a split
    has closed the pair since the proposal was made: approval flows through
    the machine's queue, and the machine does not relitigate splits. A person
    who really means it can call /v1/coreference directly, which is their own
    op under their own name."""
    row = db.execute("SELECT * FROM merge_proposals WHERE project_id=? AND id=?",
                     (p.id, proposal_id)).fetchone()
    if row is None:
        return {"error": "not_found"}
    if row["status"] != "open":
        return {"error": "already_decided", "status": row["status"]}
    a, b = row["entity_a"], row["entity_b"]
    T = p.now()
    hist = _coref_index(p, T).get(frozenset((a, b)), {"open": 0, "closed": 0})
    if hist["closed"] and not hist["open"]:
        return {"error": "refused",
                "reason": "a split recorded these as different people; "
                          "use POST /v1/coreference to overrule it explicitly"}
    if hist["open"] or _same_class(p, T, a, b):
        db.execute("UPDATE merge_proposals SET status='approved', decided=?, "
                   "decided_by=? WHERE project_id=? AND id=?",
                   (time.time(), agent, p.id, proposal_id))
        db.commit()
        return {"proposal": proposal_id, "status": "approved",
                "note": "already coreferent; nothing recorded"}
    cid = _apply_merge(p, db, scopes, record, mint, a, b, agent,
                       row["evidence"], json.loads(row["support"] or "[]"))
    db.execute("UPDATE merge_proposals SET status='approved', decided=?, "
               "decided_by=?, coreference_id=? WHERE project_id=? AND id=?",
               (time.time(), agent, cid, p.id, proposal_id))
    db.commit()
    return {"proposal": proposal_id, "status": "approved", "coreference": cid,
            "pair": [a, b]}


def reject(db, project_id: str, proposal_id: str, agent: str) -> dict:
    """A rejection is permanent for the machine: the scan never re-proposes a
    rejected pair. Recorded with who decided, because a refusal that cannot be
    audited is indistinguishable from a bug."""
    row = db.execute("SELECT * FROM merge_proposals WHERE project_id=? AND id=?",
                     (project_id, proposal_id)).fetchone()
    if row is None:
        return {"error": "not_found"}
    if row["status"] != "open":
        return {"error": "already_decided", "status": row["status"]}
    db.execute("UPDATE merge_proposals SET status='rejected', decided=?, "
               "decided_by=? WHERE project_id=? AND id=?",
               (time.time(), agent, project_id, proposal_id))
    db.commit()
    return {"proposal": proposal_id, "status": "rejected"}
