"""The intuition layer: OMEM leaps to a conclusion, then doubts it hard.

Humans learn from almost nothing because they generalize from ONE example
and fill gaps with priors -- and that same reflex is what makes human memory
unreliable. Every other memory system resolves the tension by refusing to
leap, which is why an agent needs a hundred examples where a person needs
one. OMEM resolves it the other way: it leaps, because it is the one system
that can afford to. A store with retraction cascades, provenance, and
declared conflicts has landing gear; a guess here is cheap because taking it
back is clean.

The lifecycle, and the discipline that makes it safe:

  LEAP         a target entity resembles a known one (shared beliefs, shared
               relations -- deterministic, explainable similarity), so the
               known one's beliefs are projected onto the target as
               HYPOTHESES. One similar case is enough. A hypothesis is not
               an assertion: it never enters the engine, believes() never
               sees it, and expects() is the only mouth it speaks through.

  DOUBT        every hypothesis is born suspect, carrying a docket: what
               supports it (the single case it leapt from), what would kill
               it, and what is still unknown. Serving an expectation always
               serves its case file with it.

  INTERROGATE  a skeptic pass works each open case against everything OMEM
               already holds. Reality about the target settles it: the claim
               becoming believed is a verdict of SUPPORTED, a declared
               contradiction becoming believed is REFUTED. The source case
               dying (retracted, superseded) LAPSES it. Corroborating
               look-alikes strengthen it; counter-examples weaken it but
               never refute it -- only evidence about the target itself may
               do that. A case that will not resolve moves to ASKING, and
               says what it needs.

  LEARN        verdicts teach. Each entity that generates hypotheses has a
               record: confirmations raise the strength of its future
               projections, refutations lower it. A refuted hypothesis's
               fingerprint is spent -- OMEM never re-leaps the same way from
               the same evidence -- so every single outcome tunes the whole
               intuition base. That is where "learns quickly from very
               little" actually lives: one observation, felt everywhere.

What this is NOT: a hunch is never laundered into a belief. Strength is
capped below the confidence any evidenced assertion carries, hypotheses are
excluded from recall, conflicts, and every engine query, and the engine's
UNKNOWN stays UNKNOWN however good the hunch is. expects() and believes()
are different verbs on purpose; humans conflate them, and that is the one
human trait this layer refuses to inherit.
"""
from __future__ import annotations

import hashlib
import json
import time

MIN_SIMILARITY = 2.0     # shared evidence needed before anything counts as a look-alike
MAX_NEIGHBORS = 3        # project from the closest few, not the whole world
MAX_NEW_PER_RUN = 25     # bounded leaping, like every other learner here
ASK_AFTER_PASSES = 2     # unresolved this many interrogations -> start asking
BASE_STRENGTH = 0.35     # a newborn hunch; deliberately below any evidence
STRENGTH_CEILING = 0.6   # corroboration can raise a hunch only this far
STRENGTH_FLOOR = 0.05

HYPOTHESES_SCHEMA = """
CREATE TABLE IF NOT EXISTS hypotheses(
  id TEXT NOT NULL, project_id TEXT NOT NULL,
  subject TEXT NOT NULL, proposition TEXT NOT NULL,
  born_from TEXT NOT NULL, generator TEXT NOT NULL,
  because TEXT NOT NULL, strength REAL NOT NULL,
  status TEXT NOT NULL, docket TEXT NOT NULL, passes INTEGER NOT NULL,
  fp TEXT NOT NULL, created REAL NOT NULL, decided REAL,
  PRIMARY KEY(project_id, id));
CREATE TABLE IF NOT EXISTS leap_generators(
  project_id TEXT NOT NULL, generator TEXT NOT NULL,
  wins INTEGER NOT NULL, losses INTEGER NOT NULL,
  PRIMARY KEY(project_id, generator));
"""


def _open_beliefs(p, T) -> list:
    from omem_engine.canon import RETRACTED
    out = []
    for a in p.engine.store.assertions():
        prop = a.proposition or ""
        if prop.startswith("COREF(") or prop.startswith("pattern_") or prop == RETRACTED:
            continue
        try:
            if p.engine.ledger.is_open_at(a, T):
                out.append(a)
        except Exception:
            continue
    return out


def _profiles(db, p, T) -> dict:
    """entity -> (props set, (relation, counterparty) set). The raw material
    of resemblance, and every element of it is quotable evidence."""
    from omem_engine.canon import RETRACTED
    profs: dict = {}
    for a in _open_beliefs(p, T):
        if a.proposition == RETRACTED or a.proposition.startswith("rel_"):
            continue
        if len(a.subjects) != 1:
            continue
        s = list(a.subjects)[0]
        profs.setdefault(s, [set(), set()])[0].add(a.proposition)
    for r in db.execute("SELECT assertion_id, src, relation, dst FROM memory_edges "
                        "WHERE project_id=? ORDER BY assertion_id", (p.id,)):
        a = p.engine.store.assertion(r["assertion_id"])
        if a is None:
            continue
        try:
            if not p.engine.ledger.is_open_at(a, T):
                continue
        except Exception:
            continue
        profs.setdefault(r["src"], [set(), set()])[1].add((r["relation"], r["dst"]))
        profs.setdefault(r["dst"], [set(), set()])[1].add((r["relation"] + "~of", r["src"]))
    return profs


def _similarity(pa, pb) -> tuple[float, list]:
    """Score plus the EVIDENCE of resemblance, because a leap that cannot say
    why it leapt is exactly the unreliability this layer refuses to keep."""
    shared_props = pa[0] & pb[0]
    shared_rels = pa[1] & pb[1]
    score = len(shared_props) * 1.0 + len(shared_rels) * 1.5
    because = sorted(f"both: {x}" for x in shared_props)
    because += sorted(f"both: {rel} {cp}" for rel, cp in shared_rels)
    return score, because


def _kind(eid: str) -> str:
    return eid.split(":", 1)[0]


def _fp(project_id: str, subject: str, prop: str, src_assertion: str) -> str:
    return hashlib.sha256(
        f"{project_id}|{subject}|{prop}|{src_assertion}".encode()).hexdigest()[:24]


def _gen_record(db, project_id: str, generator: str) -> tuple[int, int]:
    r = db.execute("SELECT wins, losses FROM leap_generators WHERE project_id=? "
                   "AND generator=?", (project_id, generator)).fetchone()
    return (r["wins"], r["losses"]) if r else (0, 0)


def _score_generator(db, project_id: str, generator: str, won: bool):
    wins, losses = _gen_record(db, project_id, generator)
    db.execute("INSERT OR REPLACE INTO leap_generators VALUES(?,?,?,?)",
               (project_id, generator, wins + (1 if won else 0),
                losses + (0 if won else 1)))
    db.commit()


def _birth_strength(db, project_id: str, generator: str) -> float:
    """The learning loop's other half: a generator whose projections keep
    getting refuted produces weaker hunches, one that keeps being confirmed
    produces stronger ones. One verdict moves every future leap."""
    wins, losses = _gen_record(db, project_id, generator)
    s = BASE_STRENGTH + 0.05 * wins - 0.08 * losses
    return round(max(STRENGTH_FLOOR, min(STRENGTH_CEILING, s)), 2)


def leap(p, db, about: str | None = None) -> dict:
    """One bounded leap pass. For each target entity, find its closest
    look-alikes and project their beliefs onto it as hypotheses.

    Refusals, before anything is created: never a claim the target already
    has a state on (believed needs no hunch; contradicted needs no third
    opinion); never a claim whose declared opposite the target holds; never
    a relation (a projected employment is a merge of two guesses, and this
    layer takes one liberty at a time); never the same leap twice, however
    it ended -- the fingerprint is spent forever."""
    T = p.now()
    profs = _profiles(db, p, T)
    result = {"examined": 0, "leapt": [], "skipped_spent": 0, "refused": []}
    spent = {r["fp"] for r in db.execute(
        "SELECT fp FROM hypotheses WHERE project_id=?", (p.id,))}
    # ONE hypothesis per claim: a second look-alike holding the same belief
    # is corroboration for the existing case file (interrogation collects
    # it), not grounds for a rival file about the same claim. Only a LAPSE
    # reopens the question -- the old source died, a new one may leap.
    claimed = {(r["subject"], r["proposition"]) for r in db.execute(
        "SELECT subject, proposition, status FROM hypotheses WHERE project_id=?",
        (p.id,)) if r["status"] != "lapsed"}
    # what each entity believes, for the birth refusals
    targets = sorted(profs) if about is None else [about]
    for tgt in targets:
        if tgt not in profs:
            continue
        result["examined"] += 1
        neighbors = []
        for other in sorted(profs):
            if other == tgt or _kind(other) != _kind(tgt):
                continue
            score, why = _similarity(profs[tgt], profs[other])
            if score >= MIN_SIMILARITY:
                neighbors.append((-score, other, why))
        neighbors.sort()
        for negscore, nb, why in neighbors[:MAX_NEIGHBORS]:
            for a in _open_beliefs(p, T):
                if len(result["leapt"]) >= MAX_NEW_PER_RUN:
                    return result
                if list(a.subjects) != [nb]:
                    continue
                prop = a.proposition
                if prop.startswith("rel_") or prop in profs[tgt][0]:
                    continue
                if (tgt, prop) in claimed:
                    continue  # the claim already has its case file
                state = p.engine.proposition_state([tgt], prop, T)
                if state != "UNKNOWN":
                    continue  # reality already speaks; no hunch needed
                fp = _fp(p.id, tgt, prop, a.id)
                if fp in spent:
                    result["skipped_spent"] += 1
                    continue
                generator = nb
                strength = _birth_strength(db, p.id, generator)
                because = (f"{nb} holds {prop}; {tgt} resembles {nb} "
                           f"({'; '.join(why[:4])})")
                docket = {"supports": [{"kind": "leapt_from", "assertion": a.id,
                                        "entity": nb}],
                          "undermines": [],
                          "gaps": [f"no direct evidence about {tgt} yet"]}
                hid = "hy_" + fp[:12]
                db.execute("INSERT OR IGNORE INTO hypotheses(id,project_id,subject,"
                           "proposition,born_from,generator,because,strength,status,"
                           "docket,passes,fp,created) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                           (hid, p.id, tgt, prop, a.id, generator, because,
                            strength, "open", json.dumps(docket), 0, fp, time.time()))
                spent.add(fp)
                claimed.add((tgt, prop))
                result["leapt"].append({"hypothesis": hid, "subject": tgt,
                                        "proposition": prop, "strength": strength,
                                        "because": because})
    db.commit()
    return result


def _declared_opposites(p, prop: str) -> set:
    out = set()
    try:
        for pair in p.engine.contra._pairs:  # registry of declared pairs
            a, b = tuple(pair)
            if a == prop:
                out.add(b)
            if b == prop:
                out.add(a)
    except Exception:
        pass
    if prop.startswith("not:"):
        out.add(prop[4:])
    else:
        out.add("not:" + prop)
    return out


def interrogate(p, db) -> dict:
    """The skeptic pass: work every open case against everything OMEM holds.

    Verdicts only reality can give: the claim believed about the TARGET is
    SUPPORTED (the leap was right); a declared opposite believed about the
    target is REFUTED (it was wrong, and its generator pays); the source
    case dying is LAPSED (the leap has nothing left under it). Look-alike
    corroboration and counter-examples move strength, never verdicts --
    other people's behaviour is a reason to suspect, not a verdict about
    you. A case still open after ASK_AFTER_PASSES passes starts ASKING,
    with the question it needs answered in its docket."""
    T = p.now()
    result = {"supported": [], "refuted": [], "lapsed": [], "asking": [],
              "updated": 0}
    profs = _profiles(db, p, T)
    for row in db.execute("SELECT * FROM hypotheses WHERE project_id=? AND "
                          "status IN ('open','asking') ORDER BY id", (p.id,)):
        docket = json.loads(row["docket"])
        subject, prop = row["subject"], row["proposition"]
        state = p.engine.proposition_state([subject], prop, T)
        verdict = None
        if state == "BELIEVED_TRUE":
            verdict = "supported"
        elif state in ("BELIEVED_FALSE", "CONTRADICTED"):
            verdict = "refuted"
            docket["undermines"].append(
                {"kind": "reality", "detail": f"{subject}: {prop} is {state}"})
        else:
            for opp in sorted(_declared_opposites(p, prop)):
                if p.engine.proposition_state([subject], opp, T) == "BELIEVED_TRUE":
                    verdict = "refuted"
                    docket["undermines"].append(
                        {"kind": "reality", "detail": f"{subject} holds {opp}, "
                                                      f"declared opposite of {prop}"})
                    break
        if verdict is None:
            src = p.engine.store.assertion(row["born_from"])
            src_open = False
            try:
                src_open = src is not None and p.engine.ledger.is_open_at(src, T)
            except Exception:
                pass
            if not src_open:
                verdict = "lapsed"
                docket["undermines"].append(
                    {"kind": "source_died",
                     "detail": f"the case this leapt from ({row['born_from']}) "
                               "is no longer believed"})
        strength = row["strength"]
        if verdict is None:
            # circumstantial: other look-alikes holding, or opposing, the claim
            for other in sorted(profs):
                if other in (subject, row["generator"]) or _kind(other) != _kind(subject):
                    continue
                if prop in profs[other][0] and not any(
                        s.get("entity") == other for s in docket["supports"]):
                    docket["supports"].append({"kind": "corroborating_case",
                                               "entity": other})
                    strength = min(STRENGTH_CEILING, strength + 0.05)
                for opp in _declared_opposites(p, prop):
                    if opp in profs[other][0] and not any(
                            u.get("entity") == other for u in docket["undermines"]):
                        docket["undermines"].append({"kind": "counter_case",
                                                     "entity": other,
                                                     "detail": opp})
                        strength = max(STRENGTH_FLOOR, strength - 0.07)
            passes = row["passes"] + 1
            status = row["status"]
            if passes >= ASK_AFTER_PASSES and status == "open":
                status = "asking"
                question = (f"is it true that {subject}: "
                            f"{prop.replace('_', ' ')}? OMEM suspects it "
                            f"because {row['because']}")
                docket["gaps"] = [question]
                result["asking"].append({"hypothesis": row["id"],
                                         "question": question})
            db.execute("UPDATE hypotheses SET strength=?, docket=?, passes=?, "
                       "status=? WHERE project_id=? AND id=?",
                       (round(strength, 2), json.dumps(docket), passes, status,
                        p.id, row["id"]))
            result["updated"] += 1
            continue
        db.execute("UPDATE hypotheses SET status=?, docket=?, decided=? "
                   "WHERE project_id=? AND id=?",
                   (verdict, json.dumps(docket), time.time(), p.id, row["id"]))
        if verdict in ("supported", "refuted"):
            _score_generator(db, p.id, row["generator"], verdict == "supported")
        result[verdict].append({"hypothesis": row["id"], "subject": subject,
                                "proposition": prop})
    db.commit()
    return result


def expects(p, db, about: str | None = None, status: str | None = None) -> list[dict]:
    """The hunches, each wearing its case file. Never anything believes()
    would say: a hypothesis whose claim reality settled is a verdict row,
    not an expectation, and nothing here carries engine authority."""
    q = "SELECT * FROM hypotheses WHERE project_id=?"
    args: list = [p.id]
    if about:
        q += " AND subject=?"
        args.append(about)
    if status:
        q += " AND status=?"
        args.append(status)
    else:
        q += " AND status IN ('open','asking')"
    out = []
    for r in db.execute(q + " ORDER BY strength DESC, id", args):
        d = dict(r)
        d["docket"] = json.loads(d["docket"])
        out.append(d)
    return out
