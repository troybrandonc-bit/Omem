"""Declared inference rules, with truth maintenance.

The engine decides contradiction only from explicitly declared token pairs
(ContradictionRegistry) and never from parsing text. This module gives
inference the same treatment: a rule is DECLARED DATA, never a judgment the
machine invents, and the engine remains the sole authority over what is
believed. What was missing is composition -- the graph knew

    person:sarah --works_at--> company:beta
    company:acme --owns------> company:beta

and concluded nothing, because nothing above the engine was allowed to. A
caller who declares

    works_at(fwd) . owns(rev)  =>  involves(rev)

is saying: whenever someone works at a company another company owns, the
owner's orbit involves that person. One rule, applied deterministically,
produces ordinary assertions:

  * asserted by agent:omem-rules, with the rule's conclusion as an ordinary
    two-subject relational proposition, so it projects to a graph edge and
    recall can traverse it;
  * derived (dkind="inference") from the exact premise assertions it used, so
    /why walks from the conclusion to the evidence;
  * defeasible like anything else -- supersession, contradiction and scope
    apply unchanged.

TRUTH MAINTENANCE is the half that matters. A concluded belief is only as
alive as its premises: when a premise is superseded or retracted, every
conclusion resting on it is retracted through the ordinary op path, and
conclusions resting on THOSE fall in turn. Acme sells Beta, and OMEM
withdraws -- attributably, replayably -- everything it had concluded from the
ownership. Two mechanisms, one authority:

  immediate   record() nudges maintain_after_close() when a supersede or
              retract lands, so dependents fall in the same request. Best
              effort, an optimisation only.
  sweep       run() re-checks every recorded conclusion against the engine
              before deriving anything new. This is the authoritative pass,
              same contract as projection rebuilds: the nudge can be missed,
              the sweep cannot.

Refusals, in the spirit of the rest of this codebase:

  never a rule outside the relation vocabulary   graph.RELATIONS gates both
                                                 premises and conclusion
  never the same conclusion twice                a fingerprint of (rule,
                                                 premises); new premises make
                                                 a new fingerprint
  never relitigating a human's supersession      a conclusion someone closed
                                                 stays closed unless the
                                                 EVIDENCE changed, because the
                                                 fingerprint is already spent
  never unbounded                                pass and per-run caps; a
                                                 deactivated rule's
                                                 conclusions are withdrawn on
                                                 the next pass

The engine is untouched. Every conclusion and every withdrawal is an op in
the log, so replay reconstructs the reasoning and as_of shows belief before a
premise died and after.
"""
from __future__ import annotations

import hashlib
import time

import graph as _graph

RULES_AGENT = "agent:omem-rules"

MAX_PASSES = 3          # chained rules reach fixpoint or stop here
MAX_NEW_PER_RUN = 50    # bounded work per pass, like consolidation

RULES_SCHEMA = """
CREATE TABLE IF NOT EXISTS inference_rules(
  id TEXT NOT NULL, project_id TEXT NOT NULL,
  when_a TEXT NOT NULL, dir_a TEXT NOT NULL,
  when_b TEXT NOT NULL, dir_b TEXT NOT NULL,
  then_rel TEXT NOT NULL, then_dir TEXT NOT NULL,
  active INTEGER NOT NULL DEFAULT 1,
  created REAL NOT NULL, created_by TEXT,
  PRIMARY KEY(project_id, id));
CREATE TABLE IF NOT EXISTS rule_conclusions(
  project_id TEXT NOT NULL, fp TEXT NOT NULL,
  rule_id TEXT NOT NULL, assertion_id TEXT NOT NULL,
  premise_a TEXT NOT NULL, premise_b TEXT NOT NULL,
  created REAL NOT NULL,
  PRIMARY KEY(project_id, fp));
"""

_DIRS = ("fwd", "rev")


def rule_id(when_a, dir_a, when_b, dir_b, then_rel, then_dir) -> str:
    """Deterministic from the rule's shape, so declaring twice is declaring
    once and a replayed declaration lands on the same row."""
    key = "|".join((when_a, dir_a, when_b, dir_b, then_rel, then_dir))
    return "rule_" + hashlib.sha256(key.encode()).hexdigest()[:12]


def declare(db, project_id: str, when: list, then: dict,
            created_by: str | None = None) -> dict:
    """Validate and store one rule. Everything is checked against
    graph.RELATIONS: a rule cannot smuggle a relation the vocabulary does not
    have, for the same reason record_edge refuses one. Redeclaring an existing
    rule reactivates it."""
    if not (isinstance(when, list) and len(when) == 2 and isinstance(then, dict)):
        raise ValueError("a rule is two premises and one conclusion")
    parts = []
    for spec in list(when) + [then]:
        rel = (spec or {}).get("rel")
        d = (spec or {}).get("dir", "fwd")
        if rel not in _graph.RELATIONS:
            raise ValueError(f"unknown relation {rel!r}; the vocabulary is "
                             f"{', '.join(_graph.RELATIONS)}")
        if d not in _DIRS:
            raise ValueError(f"dir must be 'fwd' or 'rev', not {d!r}")
        parts.extend((rel, d))
    rid = rule_id(*parts)
    db.execute("INSERT OR IGNORE INTO inference_rules(id,project_id,when_a,dir_a,"
               "when_b,dir_b,then_rel,then_dir,active,created,created_by) "
               "VALUES(?,?,?,?,?,?,?,?,1,?,?)",
               (rid, project_id, *parts, time.time(), created_by))
    db.execute("UPDATE inference_rules SET active=1 WHERE project_id=? AND id=?",
               (project_id, rid))
    db.commit()
    return {"id": rid, "when": when, "then": then, "active": True}


def deactivate(db, project_id: str, rid: str) -> bool:
    cur = db.execute("UPDATE inference_rules SET active=0 "
                     "WHERE project_id=? AND id=?", (project_id, rid))
    db.commit()
    return getattr(cur, "rowcount", 1) > 0


def list_rules(db, project_id: str) -> list[dict]:
    out = []
    for r in db.execute("SELECT * FROM inference_rules WHERE project_id=? "
                        "ORDER BY created, id", (project_id,)):
        d = dict(r)
        d["active"] = bool(d["active"])
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


def _edges(db, p, relation: str, T) -> list[dict]:
    """Live edges of one relation, deterministic order."""
    out = []
    for r in db.execute("SELECT assertion_id, src, dst FROM memory_edges "
                        "WHERE project_id=? AND relation=? ORDER BY src, dst, "
                        "assertion_id", (p.id, relation)):
        if _live(p, r["assertion_id"], T):
            out.append(dict(r))
    return out


def _walk(edge: dict, direction: str) -> tuple[str, str]:
    """(from, to) as the RULE reads the edge: fwd walks with it, rev against."""
    if direction == "fwd":
        return edge["src"], edge["dst"]
    return edge["dst"], edge["src"]


def _conclusion_token(then_rel: str, dst: str) -> str:
    # Same shape formation uses (extract_relations, infer_employment), so a
    # concluded relation and an observed one about the same pair are ONE
    # proposition that can corroborate, supersede or contradict.
    return f"rel_{then_rel}_{dst.split(':', 1)[-1]}"


def _label(p, eid: str) -> str:
    meta = p.labels.get(eid)
    return ((meta.get("label") if isinstance(meta, dict) else None)
            or eid.split(":", 1)[-1])


def _ensure_agent(p, record):
    if RULES_AGENT not in p.labels:
        record(p, "agent", {"id": RULES_AGENT, "kind": "system",
                            "label": "OMEM inference rules"})


def _retract(p, record, mint, a) -> str:
    nid = mint("a")
    record(p, "retract", {"id": nid, "agent": RULES_AGENT,
                          "subjects": list(a.subjects),
                          "assertion_time": p.tick(), "old": a.id,
                          "did": mint("d")})
    return nid


def _is_conclusion(db, project_id: str, aid: str) -> bool:
    """Only what the rules engine RECORDED as a conclusion is the rules
    engine's to withdraw. The agent check alone is not enough: the retraction
    assertions RULES_AGENT writes are its own too, and treating one as a
    conclusion would retract the retraction, forever."""
    return db.execute("SELECT 1 FROM rule_conclusions WHERE project_id=? AND "
                      "assertion_id=?", (project_id, aid)).fetchone() is not None


def maintain_after_close(p, db, record, mint, closed_ids: list) -> list:
    """Withdraw open conclusions that rested on assertions which just closed,
    and cascade: a withdrawn conclusion is itself a closed premise. Walks the
    engine's own derivation graph, so it cannot disagree with /why about what
    rested on what. Never touches anything it did not conclude -- a person's
    belief is theirs to close."""
    retracted, seen = [], set()
    work = list(closed_ids)
    while work:
        aid = work.pop(0)
        if aid in seen:
            continue
        seen.add(aid)
        for d in p.engine.store.derivations_referencing(aid):
            if aid not in d.antecedents:
                continue
            c = p.engine.store.assertion(d.consequent)
            if c is None or c.agent != RULES_AGENT:
                continue
            if not _is_conclusion(db, p.id, c.id):
                continue
            if not _live(p, c.id, p.now()):
                continue
            _retract(p, record, mint, c)
            retracted.append({"assertion": c.id, "proposition": c.proposition,
                              "because_premise_closed": aid})
            work.append(c.id)
    return retracted


def _sweep(p, db, record, mint) -> list:
    """The authoritative maintenance pass: every recorded conclusion is
    re-checked against the engine. Retracts a conclusion whose premises are no
    longer all open, or whose rule is gone or deactivated. Loops until stable
    because a first-level withdrawal closes a second level's premise."""
    active = {r["id"] for r in db.execute(
        "SELECT id FROM inference_rules WHERE project_id=? AND active=1", (p.id,))}
    retracted = []
    while True:
        changed = False
        T = p.now()
        for row in db.execute("SELECT * FROM rule_conclusions WHERE project_id=? "
                              "ORDER BY fp", (p.id,)):
            a = p.engine.store.assertion(row["assertion_id"])
            if a is None or not _live(p, a.id, T):
                continue
            reason = None
            if row["rule_id"] not in active:
                reason = "rule deactivated"
            elif not (_live(p, row["premise_a"], T) and _live(p, row["premise_b"], T)):
                reason = "premise no longer believed"
            if reason:
                _retract(p, record, mint, a)
                retracted.append({"assertion": a.id, "proposition": a.proposition,
                                  "reason": reason})
                changed = True
        if not changed:
            return retracted


def run(p, db, scopes, record, mint) -> dict:
    """One deterministic pass: maintain first (withdrawals precede new
    conclusions, so nothing is derived from a premise this same pass is about
    to bury), then derive to a bounded fixpoint. Idempotent: a second run over
    unchanged state does nothing."""
    result = {"rules": 0, "derived": [], "retracted": [],
              "skipped_existing": 0, "skipped_spent": 0}
    result["retracted"] = _sweep(p, db, record, mint)

    rules = [r for r in list_rules(db, p.id) if r["active"]]
    result["rules"] = len(rules)
    if not rules:
        return result

    spent = {r["fp"] for r in db.execute(
        "SELECT fp FROM rule_conclusions WHERE project_id=?", (p.id,))}

    for _pass in range(MAX_PASSES):
        T = p.now()
        open_claims = set()
        for a in p.engine.store.assertions():
            try:
                if p.engine.ledger.is_open_at(a, T):
                    open_claims.add((frozenset(a.subjects), a.proposition))
            except Exception:
                continue
        new = 0
        for rule in rules:
            by_from: dict[str, list] = {}
            for e2 in _edges(db, p, rule["when_b"], T):
                b, c = _walk(e2, rule["dir_b"])
                by_from.setdefault(b, []).append((c, e2))
            for e1 in _edges(db, p, rule["when_a"], T):
                a_ent, b = _walk(e1, rule["dir_a"])
                for c_ent, e2 in by_from.get(b, []):
                    if c_ent == a_ent:
                        continue
                    src, dst = ((a_ent, c_ent) if rule["then_dir"] == "fwd"
                                else (c_ent, a_ent))
                    fp = hashlib.sha256("|".join(
                        (rule["id"], e1["assertion_id"], e2["assertion_id"])
                    ).encode()).hexdigest()[:24]
                    if fp in spent:
                        result["skipped_spent"] += 1
                        continue
                    prop = _conclusion_token(rule["then_rel"], dst)
                    if (frozenset((src, dst)), prop) in open_claims:
                        result["skipped_existing"] += 1
                        continue
                    pa = p.engine.store.assertion(e1["assertion_id"])
                    pb = p.engine.store.assertion(e2["assertion_id"])
                    confs = [x.confidence for x in (pa, pb)
                             if x is not None and x.confidence is not None]
                    _ensure_agent(p, record)
                    aid = mint("a")
                    record(p, "assert", {
                        "id": aid, "agent": RULES_AGENT, "subjects": [src, dst],
                        "proposition": prop, "assertion_time": p.tick(),
                        "confidence": min(confs) if confs else None,
                        "label": f"{_label(p, src)} "
                                 f"{rule['then_rel'].replace('_', ' ')} "
                                 f"{_label(p, dst)} (concluded)"})
                    record(p, "derive", {"id": mint("d"), "consequent": aid,
                                         "antecedents": [e1["assertion_id"],
                                                         e2["assertion_id"]],
                                         "dkind": "inference"})
                    # record() projected the edge with sorted-order direction;
                    # the rule KNOWS the direction, so restate it, same as the
                    # observe path does after its own record().
                    try:
                        _graph.record_edge(db, p.id, aid, src,
                                           rule["then_rel"], dst)
                    except Exception:
                        pass
                    try:
                        scopes.set(p.id, aid, "org", granted_by=RULES_AGENT)
                    except Exception:
                        pass
                    db.execute("INSERT OR IGNORE INTO rule_conclusions(project_id,"
                               "fp,rule_id,assertion_id,premise_a,premise_b,created)"
                               " VALUES(?,?,?,?,?,?,?)",
                               (p.id, fp, rule["id"], aid, e1["assertion_id"],
                                e2["assertion_id"], time.time()))
                    db.commit()
                    spent.add(fp)
                    open_claims.add((frozenset((src, dst)), prop))
                    result["derived"].append({"assertion": aid, "rule": rule["id"],
                                              "proposition": prop,
                                              "pair": [src, dst]})
                    new += 1
                    if len(result["derived"]) >= MAX_NEW_PER_RUN:
                        return result
        if not new:
            break
    return result
