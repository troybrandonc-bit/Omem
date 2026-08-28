"""Declared relation constraints, and the tensions they detect.

The engine's conflict machinery is exactly as strong as its rule: two beliefs
conflict only when a declared-contradictory pair holds over the SAME reduced
subject set. That is what keeps belief state reproducible, and it also means
"Sarah works at Acme" and "Sarah works at Beta" can never be an engine
contradiction -- {sarah, acme} and {sarah, beta} are different subject sets,
so both sit open forever, each looking like uncontested fact.

Whether that is fine is domain knowledge the machine must not invent.
supplies is naturally many-to-many; works_at usually is not. So the shape a
relation may take is DECLARED, like a contradiction and like an inference
rule:

    {"relation": "works_at", "kind": "one_dst_per_src"}
    "a person has one employer at a time"

and a violation among live edges becomes a TENSION: a recorded observation
that the declared shape is broken, sitting in the same queue merge proposals
wait in. Nothing else happens. OMEM does not pick the newer employer, does
not supersede, does not retract -- it asks. A person resolves the tension by
naming the COUNTERPARTY that survives (beliefs toward the others are
retracted through the ordinary op path, under the resolver's name, and
anything the rules engine concluded from a retracted premise falls with it
in the same request), or dismisses it, which is permanent for that exact set
of counterparties: the machine never nags about evidence a person already
judged. A NEW counterparty is new evidence and may raise a new tension; a
dismissal is never widened past what was dismissed.

Refusals, as ever:

  never outside the vocabulary   graph.RELATIONS gates the relation, and the
                                 kind must be a shape this module defines
  never an auto-resolution       detection and judgment are different jobs,
                                 and only the second belongs to a person
  never the same nag twice       a tension's identity is its holder set;
                                 dismissed stays dismissed for that set
  never engine involvement       tensions live beside the engine; an open
                                 tension changes no answer to any query

Every retraction a resolution performs is an op in the log: replay
reconstructs who kept what, and as_of shows both employments before the
judgment and one after.
"""
from __future__ import annotations

import hashlib
import json
import time

import graph as _graph

KINDS = ("one_dst_per_src", "one_src_per_dst")

CONSTRAINTS_SCHEMA = """
CREATE TABLE IF NOT EXISTS relation_constraints(
  id TEXT NOT NULL, project_id TEXT NOT NULL,
  relation TEXT NOT NULL, kind TEXT NOT NULL,
  active INTEGER NOT NULL DEFAULT 1,
  created REAL NOT NULL, created_by TEXT,
  PRIMARY KEY(project_id, id));
CREATE TABLE IF NOT EXISTS constraint_tensions(
  id TEXT NOT NULL, project_id TEXT NOT NULL,
  constraint_id TEXT NOT NULL, relation TEXT NOT NULL,
  entity TEXT NOT NULL, holders TEXT NOT NULL, fp TEXT NOT NULL,
  status TEXT NOT NULL, created REAL NOT NULL,
  decided REAL, decided_by TEXT, kept TEXT,
  PRIMARY KEY(project_id, id));
"""


def constraint_id(relation: str, kind: str) -> str:
    return "rc_" + hashlib.sha256(f"{relation}|{kind}".encode()).hexdigest()[:12]


def declare(db, project_id: str, relation: str, kind: str,
            created_by: str | None = None) -> dict:
    """Validate and store one constraint. Redeclaring reactivates."""
    if relation not in _graph.RELATIONS:
        raise ValueError(f"unknown relation {relation!r}; the vocabulary is "
                         f"{', '.join(_graph.RELATIONS)}")
    if kind not in KINDS:
        raise ValueError(f"kind must be one of {', '.join(KINDS)}, not {kind!r}")
    cid = constraint_id(relation, kind)
    db.execute("INSERT OR IGNORE INTO relation_constraints(id,project_id,relation,"
               "kind,active,created,created_by) VALUES(?,?,?,?,1,?,?)",
               (cid, project_id, relation, kind, time.time(), created_by))
    db.execute("UPDATE relation_constraints SET active=1 WHERE project_id=? AND id=?",
               (project_id, cid))
    db.commit()
    return {"id": cid, "relation": relation, "kind": kind, "active": True}


def deactivate(db, project_id: str, cid: str) -> bool:
    cur = db.execute("UPDATE relation_constraints SET active=0 "
                     "WHERE project_id=? AND id=?", (project_id, cid))
    db.commit()
    return getattr(cur, "rowcount", 1) > 0


def list_constraints(db, project_id: str) -> list[dict]:
    out = []
    for r in db.execute("SELECT * FROM relation_constraints WHERE project_id=? "
                        "ORDER BY created, id", (project_id,)):
        d = dict(r)
        d["active"] = bool(d["active"])
        out.append(d)
    return out


def list_tensions(db, project_id: str, status: str | None = None) -> list[dict]:
    q = "SELECT * FROM constraint_tensions WHERE project_id=?"
    args = [project_id]
    if status:
        q += " AND status=?"
        args.append(status)
    out = []
    for r in db.execute(q + " ORDER BY created, id", args):
        d = dict(r)
        d["holders"] = json.loads(d.get("holders") or "[]")
        out.append(d)
    return out


def _live(p, aid: str, T) -> bool:
    a = p.engine.store.assertion(aid)
    if a is None:
        return False
    try:
        return bool(p.engine.ledger.is_open_at(a, T))
    except Exception:
        return False


def _sides(kind: str) -> tuple[str, str]:
    group_by = "src" if kind == "one_dst_per_src" else "dst"
    return group_by, ("dst" if group_by == "src" else "src")


def _violations(db, p, constraint: dict, T) -> list[tuple]:
    """(shared entity, sorted counterparties, {counterparty: [live assertion
    ids]}) for every entity whose live edges break the declared shape.

    A tension's identity is the COUNTERPARTY SET, never the assertion ids:
    "Sarah at Acme and Beta" is the situation a person judges, and a second
    assertion of the same employment is corroboration of one side of it, not
    new evidence of the clash. Keying on assertion ids made every
    corroboration lapse and re-raise the same question, which is nagging."""
    group_by, other_of = _sides(constraint["kind"])
    groups: dict[str, dict] = {}
    for r in db.execute("SELECT assertion_id, src, dst FROM memory_edges "
                        "WHERE project_id=? AND relation=? ORDER BY assertion_id",
                        (p.id, constraint["relation"])):
        if not _live(p, r["assertion_id"], T):
            continue
        groups.setdefault(r[group_by], {}) \
              .setdefault(r[other_of], []).append(r["assertion_id"])
    out = []
    for entity in sorted(groups):
        if len(groups[entity]) >= 2:
            out.append((entity, sorted(groups[entity]),
                        {k: sorted(v) for k, v in groups[entity].items()}))
    return out


def _fp(cid: str, entity: str, counterparties: list) -> str:
    return hashlib.sha256(
        "|".join([cid, entity] + list(counterparties)).encode()).hexdigest()[:24]


def check(p, db) -> dict:
    """One deterministic detection pass. Lapse first (a tension whose
    evidence changed or whose constraint is gone stops being anyone's
    homework), then raise what the live edges currently violate. Detection
    only: nothing here touches the engine."""
    T = p.now()
    constraints = {c["id"]: c for c in list_constraints(db, p.id) if c["active"]}
    report = {"constraints": len(constraints), "raised": [], "lapsed": [],
              "unchanged": 0, "spent": 0}

    current: dict[str, tuple] = {}
    for cid in sorted(constraints):
        for entity, others, holders in _violations(db, p, constraints[cid], T):
            fp = _fp(cid, entity, others)
            current[fp] = (cid, constraints[cid]["relation"], entity, others, holders)

    for row in db.execute("SELECT * FROM constraint_tensions WHERE project_id=? "
                          "AND status='open' ORDER BY id", (p.id,)):
        if row["fp"] not in current or row["constraint_id"] not in constraints:
            db.execute("UPDATE constraint_tensions SET status='lapsed', decided=? "
                       "WHERE project_id=? AND id=?", (time.time(), p.id, row["id"]))
            report["lapsed"].append({"tension": row["id"],
                                     "reason": ("constraint deactivated"
                                                if row["constraint_id"] not in constraints
                                                else "the evidence changed")})
    db.commit()

    seen = {r["fp"]: r["status"] for r in db.execute(
        "SELECT fp, status FROM constraint_tensions WHERE project_id=?", (p.id,))}
    for fp in sorted(current):
        cid, relation, entity, others, holders = current[fp]
        status = seen.get(fp)
        if status == "open":
            # same question, though the supporting assertions may have grown;
            # keep the stored evidence current for whoever reads the queue.
            db.execute("UPDATE constraint_tensions SET holders=? "
                       "WHERE project_id=? AND fp=?",
                       (json.dumps(holders), p.id, fp))
            report["unchanged"] += 1
            continue
        if status in ("dismissed", "resolved"):
            # A person already judged exactly this evidence. Dismissed means
            # "both are fine"; resolved means they chose and the loser is
            # closed (so the violation is normally gone -- reaching here means
            # something reopened, which a NEW holder set would express as a
            # new fp anyway). Either way: never the same nag twice.
            report["spent"] += 1
            continue
        tid = "tn_" + fp[:12]
        if status == "lapsed":
            # The violation is back, undecided (a lapse is circumstance, not
            # judgment -- the constraint was off, or the evidence flickered).
            # The row's id derives from the fp, so it must reopen rather than
            # be re-inserted.
            db.execute("UPDATE constraint_tensions SET status='open', holders=?, "
                       "decided=NULL, decided_by=NULL WHERE project_id=? AND id=?",
                       (json.dumps(holders), p.id, tid))
        else:
            db.execute("INSERT OR IGNORE INTO constraint_tensions(id,project_id,"
                       "constraint_id,relation,entity,holders,fp,status,created) "
                       "VALUES(?,?,?,?,?,?,?,?,?)",
                       (tid, p.id, cid, relation, entity, json.dumps(holders), fp,
                        "open", time.time()))
        report["raised"].append({"tension": tid, "relation": relation,
                                 "entity": entity, "between": others})
    db.commit()
    return report


def resolve(p, db, record, mint, tension_id: str, keep: str, agent: str) -> dict:
    """A person names the COUNTERPARTY that survives ("Acme is her
    employer"). Every live assertion of the relation between the entity and
    the tension's other counterparties is retracted through the ordinary op
    path under the resolver's name -- withdrawn, not negated -- and anything
    the rules engine concluded from a retracted premise falls with it in the
    same request (record()'s truth-maintenance nudge).

    Live edges are re-read at judgment time, so a corroboration recorded
    since the tension was raised is retracted with its sibling rather than
    surviving on a stale snapshot. A counterparty the tension never named is
    never touched: new evidence gets its own tension, not a wider sweep."""
    row = db.execute("SELECT * FROM constraint_tensions WHERE project_id=? AND id=?",
                     (p.id, tension_id)).fetchone()
    if row is None:
        return {"error": "not_found"}
    if row["status"] != "open":
        return {"error": "already_decided", "status": row["status"]}
    constraint = db.execute(
        "SELECT * FROM relation_constraints WHERE project_id=? AND id=?",
        (p.id, row["constraint_id"])).fetchone()
    if constraint is None:
        return {"error": "not_found"}
    counterparties = sorted(json.loads(row["holders"] or "{}"))
    if keep not in counterparties:
        return {"error": "refused",
                "reason": "keep must name one of the tension's counterparties"}
    group_by, other_of = _sides(constraint["kind"])
    retracted = []
    for r in db.execute("SELECT assertion_id, src, dst FROM memory_edges "
                        "WHERE project_id=? AND relation=? ORDER BY assertion_id",
                        (p.id, row["relation"])):
        if r[group_by] != row["entity"]:
            continue
        cp = r[other_of]
        if cp == keep or cp not in counterparties:
            continue
        if not _live(p, r["assertion_id"], p.now()):
            continue
        a = p.engine.store.assertion(r["assertion_id"])
        record(p, "retract", {"id": mint("a"), "agent": agent,
                              "subjects": list(a.subjects),
                              "assertion_time": p.tick(),
                              "old": r["assertion_id"], "did": mint("d")})
        retracted.append(r["assertion_id"])
    db.execute("UPDATE constraint_tensions SET status='resolved', decided=?, "
               "decided_by=?, kept=? WHERE project_id=? AND id=?",
               (time.time(), agent, keep, p.id, tension_id))
    db.commit()
    return {"tension": tension_id, "status": "resolved", "kept": keep,
            "retracted": retracted}


def dismiss(db, project_id: str, tension_id: str, agent: str) -> dict:
    """Both beliefs are fine; the declared shape does not apply here. Recorded
    with who decided, and permanent for exactly this holder set: a new holder
    is new evidence and may raise a new tension, but a dismissal is never
    widened past what was actually dismissed."""
    row = db.execute("SELECT * FROM constraint_tensions WHERE project_id=? AND id=?",
                     (project_id, tension_id)).fetchone()
    if row is None:
        return {"error": "not_found"}
    if row["status"] != "open":
        return {"error": "already_decided", "status": row["status"]}
    db.execute("UPDATE constraint_tensions SET status='dismissed', decided=?, "
               "decided_by=? WHERE project_id=? AND id=?",
               (time.time(), agent, project_id, tension_id))
    db.commit()
    return {"tension": tension_id, "status": "dismissed"}
