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


def _prop_clusters(props: list) -> dict:
    """prop -> cluster representative, via the same embeddings semantic
    recall uses. "wants_yearly_invoicing" and "prefers_annual_billing" are
    one experience to a person; with a real embedder configured they become
    one feature here too. The dependency-free hashing embedding clusters
    only near-identical spellings, which is the honest offline floor.
    Deterministic: sorted greedy assignment, first-seen token is the rep."""
    import semantic_recall as _sr
    reps: list = []
    mapping: dict = {}
    ordered = sorted(props)
    vecs = _sr.embed([x.replace("_", " ") for x in ordered])
    for prop, vec in zip(ordered, vecs):
        best, best_sim = None, 0.0
        for rep_prop, rep_vec in reps:
            sim = _sr._cosine(vec, rep_vec)
            if sim > best_sim:
                best, best_sim = rep_prop, sim
        if best is not None and best_sim >= 0.75:
            mapping[prop] = best
        else:
            reps.append((prop, vec))
            mapping[prop] = prop
    return mapping


def _feature_weights(profs: dict, rep_of: dict) -> dict:
    """Inverse-frequency weight per feature: w = 1 + ln(N / df). A trait
    everyone shares still counts (floor of 1), a rare one binds hard --
    sharing "runs_on_mainframes" says far more about two entities than
    sharing "prefers_email", which is exactly how human analogy weighs
    coincidence."""
    import math
    n = max(1, len(profs))
    df: dict = {}
    for pa in profs.values():
        for f in {rep_of.get(x, x) for x in pa[0]}:
            df[("p", f)] = df.get(("p", f), 0) + 1
        for f in pa[1]:
            df[("r", f)] = df.get(("r", f), 0) + 1
    return {k: 1.0 + math.log(n / v) for k, v in df.items()}


def _similarity(pa, pb, rep_of: dict, weights: dict) -> tuple[float, list]:
    """Score plus the EVIDENCE of resemblance, because a leap that cannot say
    why it leapt is exactly the unreliability this layer refuses to keep.
    Props compare by cluster representative (meaning, not spelling); every
    shared feature contributes its rarity weight."""
    a_reps = {}
    for x in pa[0]:
        a_reps.setdefault(rep_of.get(x, x), x)
    b_reps = {}
    for x in pb[0]:
        b_reps.setdefault(rep_of.get(x, x), x)
    score = 0.0
    because = []
    for rep in sorted(set(a_reps) & set(b_reps)):
        w = weights.get(("p", rep), 1.0)
        score += w
        if a_reps[rep] == b_reps[rep]:
            note = f"both: {a_reps[rep]}"
        else:
            note = f"both: {a_reps[rep]} ~ {b_reps[rep]}"
        because.append(note + (f" (rare, x{w:.1f})" if w >= 2.0 else ""))
    for rel, cp in sorted(pa[1] & pb[1]):
        w = weights.get(("r", (rel, cp)), 1.0)
        # Shared CONTEXT weighs less than shared EXPERIENCE: both using the
        # same tool is circumstance, both preferring the same terms is
        # character. At weight 1.0 a single common relation can never cross
        # MIN_SIMILARITY on its own, and that is the intended refusal.
        score += 1.0 * w
        because.append(f"both: {rel} {cp}")
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


def _family(prop: str) -> str:
    """The KIND of claim, for calibration: prefers_*, wants_*, uses_*.
    Crude on purpose -- the first token names the speech family well enough
    to notice that guesses about preferences keep landing while guesses
    about tooling keep missing, and crude-but-stated beats clever-but-
    unexplainable in a number that adjusts behaviour."""
    return (prop[4:] if prop.startswith("not:") else prop).split("_", 1)[0]


def _family_records(db, project_id: str) -> dict:
    out: dict = {}
    for r in db.execute("SELECT proposition, status FROM hypotheses WHERE "
                        "project_id=? AND status IN ('supported','refuted')",
                        (project_id,)):
        fam = _family(r["proposition"])
        w, l = out.get(fam, (0, 0))
        out[fam] = (w + (1 if r["status"] == "supported" else 0),
                    l + (1 if r["status"] == "refuted" else 0))
    return out


def _birth_strength(gen_rec: tuple, fam_rec: tuple) -> float:
    """The learning loop's other half, now with self-knowledge: a generator
    whose projections keep getting refuted produces weaker hunches, and so
    does a FAMILY of claim OMEM has learned it guesses badly. Metacognition
    as arithmetic: the system knows what it is good at guessing, and its
    boldness follows its record."""
    gw, gl = gen_rec
    fw, fl = fam_rec
    s = BASE_STRENGTH + 0.05 * gw - 0.08 * gl + 0.03 * fw - 0.05 * fl
    return round(max(STRENGTH_FLOOR, min(STRENGTH_CEILING, s)), 2)


def calibration(db, project_id: str) -> dict:
    """What OMEM knows about its own guessing: per claim-family and per
    generator, how the verdicts have gone. Read-only self-knowledge; the
    same numbers already feed birth strength."""
    fams = {fam: {"supported": w, "refuted": l,
                  "rate": round(w / (w + l), 2) if (w + l) else None}
            for fam, (w, l) in sorted(_family_records(db, project_id).items())}
    gens = {}
    for r in db.execute("SELECT generator, wins, losses FROM leap_generators "
                        "WHERE project_id=? ORDER BY generator", (project_id,)):
        t = r["wins"] + r["losses"]
        gens[r["generator"]] = {"supported": r["wins"], "refuted": r["losses"],
                                "rate": round(r["wins"] / t, 2) if t else None}
    return {"families": fams, "generators": gens}


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
    all_props = sorted({x for pa in profs.values() for x in pa[0]})
    rep_of = _prop_clusters(all_props)
    weights = _feature_weights(profs, rep_of)
    fam_recs = _family_records(db, p.id)
    gen_recs = {r["generator"]: (r["wins"], r["losses"]) for r in db.execute(
        "SELECT generator, wins, losses FROM leap_generators WHERE project_id=?",
        (p.id,))}
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
        tgt_reps = {rep_of.get(x, x) for x in profs[tgt][0]}
        neighbors = []
        for other in sorted(profs):
            if other == tgt or _kind(other) != _kind(tgt):
                continue
            score, why = _similarity(profs[tgt], profs[other], rep_of, weights)
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
                if rep_of.get(prop, prop) in tgt_reps:
                    continue  # the target holds a sibling of this claim
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
                strength = _birth_strength(gen_recs.get(generator, (0, 0)),
                                           fam_recs.get(_family(prop), (0, 0)))
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


def answer(p, db, record, mint, hypothesis_id: str, response: str,
           agent: str) -> dict:
    """A person (or another agent) answers an open question, and the answer
    is EVIDENCE, not a status flip: yes records the claim as an ordinary
    assertion under the answerer's name, no records its negation, and then
    interrogation reaches the verdict the normal way -- through reality. The
    asking loop closes without ever giving anyone a lever that marks a hunch
    true by decree."""
    row = db.execute("SELECT * FROM hypotheses WHERE project_id=? AND id=?",
                     (p.id, hypothesis_id)).fetchone()
    if row is None:
        return {"error": "not_found"}
    if row["status"] not in ("open", "asking"):
        return {"error": "already_decided", "status": row["status"]}
    if response not in ("yes", "no"):
        return {"error": "refused",
                "reason": "answer must be 'yes' or 'no'; an answer is "
                          "evidence, and evidence takes a side"}
    prop = row["proposition"]
    if response == "no":
        prop = prop[4:] if prop.startswith("not:") else "not:" + prop
    aid = mint("a")
    record(p, "assert", {"id": aid, "agent": agent,
                         "subjects": [row["subject"]], "proposition": prop,
                         "assertion_time": p.tick(),
                         "label": f"answer to OMEM's question about "
                                  f"{row['subject']}"})
    verdicts = interrogate(p, db)
    after = db.execute("SELECT status FROM hypotheses WHERE project_id=? AND "
                       "id=?", (p.id, hypothesis_id)).fetchone()
    return {"hypothesis": hypothesis_id, "answered": response,
            "recorded": aid, "verdict": after["status"],
            "note": "the answer became an ordinary assertion under the "
                    "answerer's name; the verdict came from interrogation, "
                    "not decree"}


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
