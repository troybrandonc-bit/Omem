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

  LEARN        verdicts teach, and they do not all teach the same amount.
               Each entity that generates hypotheses has a record:
               confirmations raise the strength of its future projections,
               refutations lower it, each by how far the verdict fell from
               the strength the hunch was carrying. Being confident and
               wrong is the most informative thing that can happen to a
               guesser; being unsure and wrong is barely news, and a flat
               win-or-loss tally cannot tell those apart. A refuted
               hypothesis's fingerprint is spent -- OMEM never re-leaps the
               same way from the same evidence -- so every single outcome
               tunes the whole intuition base. That is where "learns quickly
               from very little" actually lives: one observation, felt
               everywhere, in proportion to how much it overturned.

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
import re
import time

MIN_SIMILARITY = 2.0     # shared evidence needed before anything counts as a look-alike
MAX_NEIGHBORS = 3        # project from the closest few, not the whole world
MAX_NEW_PER_RUN = 25     # bounded leaping, like every other learner here
ASK_AFTER_PASSES = 2     # unresolved this many interrogations -> start asking
BASE_STRENGTH = 0.35     # a newborn hunch; deliberately below any evidence
# A hunch may not be born as certain as evidence. That separation is real, and
# it is enforced structurally rather than by this number: expects() and
# believes() are different verbs over different tables, and the engine's UNKNOWN
# stays UNKNOWN for everything the intuition layer holds, whatever strength it
# carries. Nothing in the codebase compares a hunch's strength against an
# evidenced confidence.
#
# This was 0.6, which sits below the rate hunches actually achieve: 68% measured
# against 19,668 real respondents. A cap under the observed rate is not caution,
# it is a fixed error that no amount of evidence can correct, and it is the same
# fault already found in the borrowed-hunch cap, which held borrowed hunches at
# 0.45 while they landed 65% of the time. Clipping the statement does not make
# the guess safer; it makes the statement false.
#
# Raised to sit above what hunches achieve rather than beneath it. 0.85 and 1.0
# score within 0.0005 of each other, so this is not a tuned constant: the
# finding is that the cap must not bind below the observed rate.
STRENGTH_CEILING = 0.85
STRENGTH_FLOOR = 0.05

# The priors tier: regularities that hold ACROSS people, not facts about one.
# A prior is "entities that hold P tend to hold Q", learned by co-occurrence
# and applied to a new person's SILENCE (never over what they are known to
# be). Two numbers gate it, both honest: it may not fire from fewer than
# PRIOR_FLOOR_N supporting subjects (no law of humanity from two examples),
# and not below PRIOR_MIN_RATE (a pattern that barely holds is not a prior).
PRIOR_FLOOR_N = 3
PRIOR_MIN_RATE = 0.6
# ...and it must beat the CONSEQUENT'S OWN BASE RATE by this much, which is a
# different question and the one that matters. "Sixty percent of the people who
# hold P also hold Q" is satisfied by Q being popular: if seventy six percent of
# everyone holds Q, the rule has learned nothing about P. Measured over 19,719
# real respondents in a dataset with a known latent structure, the rate test
# alone recovered that structure at 0.185 against a chance line of 0.184, which
# is to say not at all, while the consequents it selected had a mean base rate
# of 0.76 against an item mean of 0.57. See benchmarks/external.
#
# 0.15 is deliberately below the margin that scored best in that sweep. The
# sweep was run on the same data it was evaluated on, and a threshold tuned to
# its own evaluation set is a number, not evidence.
PRIOR_MIN_LIFT = 0.10
PRIOR_LIFT_Z = 1.96      # the 95% one-sided bound, so "three of three" is not
                         # mistaken for "three hundred of three hundred"
# How much evidence it takes to move a hunch off the house rate, and how much
# it takes before the house rate is believed at all. Both are pseudo-counts:
# BIRTH_K is the weight of the prior on one generator's record, ANCHOR_K the
# weight of BASE_STRENGTH on the install's overall record.
# Below this a generator's record is reported with a note rather than as a
# rate, because a rate on two verdicts is not a rate about anything.
MIN_VERDICTS_FOR_RATE = 5

BIRTH_K = 8.0            # one verdict nudges a generator, thirty move it a
                         # long way. A smaller number scored better on Brier
                         # here, but only because birth strength is capped
                         # below the rate these hunches actually achieve, so
                         # that measurement rewards whatever reaches the cap
                         # fastest. Choosing on a confounded number would be
                         # choosing on nothing.
ANCHOR_K = 20.0          # an install needs a couple of dozen verdicts before
                         # its own hit rate is worth more than the default. At
                         # four verdicts the learned rate still sits within a
                         # few points of BASE_STRENGTH, which is the intent:
                         # an install that has been right twice does not yet
                         # know that it is good at this.
# A prior borrowed from the commons is about other people's populations, so it
# has to earn its confidence here before it gets it. This is the ratio by which
# borrowing RAISES the evidence bar: a borrowed prior is shrunk toward the
# house rate by BIRTH_K / POOLED_DISCOUNT pseudo-counts rather than BIRTH_K, so
# it needs a third again as much of its own record to say the same thing.
#
# It used to multiply the finished strength instead, which stacked on the
# ceiling and capped a borrowed hunch at 0.45 forever, while borrowed hunches
# were measured landing 65% of the time. Caution about other people's
# populations is right; a permanent twenty point error is not.
POOLED_DISCOUNT = 0.75

# A pooled pair that replicated across installs but only inside ONE kind of
# population is a weaker claim than one that held in several, and the two are
# indistinguishable in the counts: both say "many people, and they agreed".
# The collector reports how many distinct population frames back a row, and a
# row backed by one raises the bar again, on the same principle as borrowing
# itself -- more of its own record on THIS install's people before it moves off
# the house rate. It is not refused, because a regularity found in one kind of
# workplace may well hold in another; it is just not yet evidence that it does.
MONOCULTURE_DISCOUNT = 0.6
POOLED_MIN_FRAMES = 2
PRIOR_MAX = 500          # a bound on how many priors one mining pass may hold

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
  w_wins REAL, w_losses REAL,
  base_sum REAL, verdicts INTEGER,
  PRIMARY KEY(project_id, generator));
CREATE TABLE IF NOT EXISTS priors(
  id TEXT NOT NULL, project_id TEXT NOT NULL,
  antecedent TEXT NOT NULL, consequent TEXT NOT NULL, context TEXT NOT NULL,
  support INTEGER NOT NULL, refute INTEGER NOT NULL, subjects INTEGER NOT NULL,
  updated REAL NOT NULL,
  PRIMARY KEY(project_id, id));
"""


def ensure_schema(db):
    """The schema, plus the two columns an install predating prediction-error
    weighting will not have. CREATE TABLE IF NOT EXISTS does not add columns to
    a table that already exists, and every install that has ever scored a
    generator already has this one."""
    db.executescript(HYPOTHESES_SCHEMA)
    for col in ("w_wins", "w_losses", "base_sum", "verdicts"):
        try:
            db.execute("ALTER TABLE leap_generators ADD COLUMN %s REAL" % col)
        except Exception:
            pass  # already there
    db.commit()


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


_CLUSTER_CACHE: dict = {}
_CLUSTER_CACHE_MAX = 8


def _prop_clusters(props: list) -> dict:
    """prop -> cluster representative, via the same embeddings semantic
    recall uses. "wants_yearly_invoicing" and "prefers_annual_billing" are
    one experience to a person; with a real embedder configured they become
    one feature here too. The dependency-free hashing embedding clusters
    only near-identical spellings, which is the honest offline floor.
    Deterministic: sorted greedy assignment, first-seen token is the rep.

    Three things make it affordable at a large vocabulary, none of which
    change which clusters come out.

    It is cached on the vocabulary, because a consolidation pass asks for the
    same clustering twice, once from leap and once from learn_priors, and asks
    again on the next pass with a vocabulary that has usually not moved.

    A candidate is only compared with representatives that share a non-zero
    dimension with it. The embedding is 256 numbers of which about twenty are
    non-zero, so most pairs share nothing, and a pair sharing nothing has a
    cosine of exactly zero, which can never beat a best-so-far that starts at
    zero.

    And each representative's norm is computed once when it is created rather
    than recomputed on every comparison against it."""
    key = tuple(sorted(props))
    hit = _CLUSTER_CACHE.get(key)
    if hit is not None:
        return dict(hit)

    import math
    import semantic_recall as _sr
    ordered = list(key)
    vecs = _sr.embed([x.replace("_", " ") for x in ordered])
    reps: list = []                 # (prop, {dim: value}, norm)
    dim_index: dict = {}            # dim -> positions in reps
    mapping: dict = {}
    for prop, vec in zip(ordered, vecs):
        sparse = {i: v for i, v in enumerate(vec) if v}
        norm = math.sqrt(sum(v * v for v in sparse.values())) or 1.0
        seen = set()
        for i in sparse:
            seen.update(dim_index.get(i, ()))
        best, best_sim = None, 0.0
        for j in sorted(seen):
            rep_prop, rep_sparse, rep_norm = reps[j]
            if len(rep_sparse) < len(sparse):
                dot = sum(v * sparse[i] for i, v in rep_sparse.items() if i in sparse)
            else:
                dot = sum(v * rep_sparse[i] for i, v in sparse.items() if i in rep_sparse)
            sim = dot / (norm * rep_norm)
            if sim > best_sim:
                best, best_sim = rep_prop, sim
        if best is not None and best_sim >= 0.75:
            mapping[prop] = best
        else:
            for i in sparse:
                dim_index.setdefault(i, []).append(len(reps))
            reps.append((prop, sparse, norm))
            mapping[prop] = prop

    if len(_CLUSTER_CACHE) >= _CLUSTER_CACHE_MAX:
        _CLUSTER_CACHE.pop(next(iter(_CLUSTER_CACHE)))
    _CLUSTER_CACHE[key] = dict(mapping)
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


def _reps_map(props, rep_of: dict) -> dict:
    """Cluster representative -> the spelling this entity used for it.

    Built once per entity rather than twice per comparison. `setdefault` keeps
    the first spelling seen, exactly as the inline version did, so the evidence
    line reads the same."""
    out: dict = {}
    for x in props:
        out.setdefault(rep_of.get(x, x), x)
    return out


def _sim_score(a_reps: dict, a_rels, b_reps: dict, b_rels, weights: dict) -> float:
    """The score alone, for the comparison every entity gets.

    Scoring is a sum, so it needs no sorting, and it needs no prose. The
    explanation is built afterwards for the few neighbours that survive, which
    is the difference between formatting a string for three comparisons and
    formatting one for every pair of entities in the project."""
    score = 0.0
    for rep in a_reps.keys() & b_reps.keys():
        score += weights.get(("p", rep), 1.0)
    for rel_cp in a_rels & b_rels:
        score += weights.get(("r", rel_cp), 1.0)
    return score


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


def surprise(strength: float, won: bool) -> float:
    """How much this verdict should teach: the prediction error.

    A flat win-or-loss says every outcome is equally informative, which is not
    how anything learns. Being confident and wrong is the most informative
    thing that can happen to a guesser; being unsure and wrong is barely news.
    The error between what was forecast and what occurred is exactly that
    quantity, and both numbers were already here -- the strength the hypothesis
    carried when reality answered, and the verdict it returned.

    Supported at 0.05 is a shock and moves the record a long way. Refuted at
    0.05 was half expected and moves it barely. Same arithmetic as the Brier
    residual the calibration benchmark scores, over the same column, which is
    deliberate: the thing that decides how much to learn is the thing that
    measures how wrong we were."""
    s = max(0.0, min(1.0, float(strength)))
    return (1.0 - s) if won else s


def _weighted(row) -> tuple[float, float]:
    """A generator's weighted record, read off one row.

    A row written before weighting existed has no weights, so it falls back to
    its counts: an upgrade must not silently reset what a generator had earned.
    The fallback is also the honest reading of such a row -- an unweighted
    record is one where every verdict was taken to teach the same amount,
    which is exactly 1.0 each."""
    w, l = row["w_wins"], row["w_losses"]
    if w is None and l is None:
        return (float(row["wins"]), float(row["losses"]))
    return (float(w or 0.0), float(l or 0.0))


def _gen_record(db, project_id: str, generator: str) -> tuple[float, float]:
    """The WEIGHTED record, which is what boldness is computed from.

    The integer counts stay in the same row untouched, because a count is what
    the commons contributes and what a person reads in a report. "Nine wins" is
    a fact about the world; 6.2 is a fact about how much those nine taught."""
    r = db.execute("SELECT wins, losses, w_wins, w_losses FROM leap_generators "
                   "WHERE project_id=? AND generator=?",
                   (project_id, generator)).fetchone()
    return _weighted(r) if r else (0.0, 0.0)


def _gen_records(db, project_id: str) -> dict:
    """Every generator's weighted record in one read, for a leap run that
    needs all of them. Same fallback, same arithmetic, one query."""
    return {r["generator"]: _weighted(r) for r in db.execute(
        "SELECT generator, wins, losses, w_wins, w_losses FROM leap_generators "
        "WHERE project_id=?", (project_id,))}


def _gen_counts(db, project_id: str, generator: str) -> tuple[int, int]:
    """The plain counts, for the commons and for anything a human reads."""
    r = db.execute("SELECT wins, losses FROM leap_generators WHERE project_id=? "
                   "AND generator=?", (project_id, generator)).fetchone()
    return (r["wins"], r["losses"]) if r else (0, 0)


def _score_generator(db, project_id: str, generator: str, won: bool,
                     strength: float, base: float | None = None):
    """Record a verdict, and what chance would have been on the same claim.

    A win rate on its own is the defect the mining rule was repaired for, one
    level up. `rate = wins / (wins + losses)` says nothing about whether the
    guesses were worth making: a generator that only ever predicts claims most
    people hold accumulates an excellent record and carries no information, in
    exactly the way a prior selected on popularity did. PRIOR_MIN_LIFT stopped
    that happening in the miner; nothing stopped it here, and this number feeds
    birth strength, so the confounded quantity propagated into every forecast.

    `base` is the claim's own rate in the population at the moment the verdict
    landed. Accumulated, it makes the record's lift readable: how much better
    than chance this generator has been, rather than merely how often it was
    right about things that were usually true anyway. It is recorded rather
    than acted on: correcting birth strength by it is a change that should be
    measured before it is made, not assumed."""
    wins, losses = _gen_counts(db, project_id, generator)
    w_wins, w_losses = _gen_record(db, project_id, generator)
    bs, vd = _gen_base(db, project_id, generator)
    s = surprise(strength, won)
    db.execute("INSERT OR REPLACE INTO leap_generators(project_id, generator, "
               "wins, losses, w_wins, w_losses, base_sum, verdicts) "
               "VALUES(?,?,?,?,?,?,?,?)",
               (project_id, generator, wins + (1 if won else 0),
                losses + (0 if won else 1),
                w_wins + (s if won else 0.0), w_losses + (0.0 if won else s),
                bs + (base if base is not None else 0.0),
                vd + (1 if base is not None else 0)))
    db.commit()


def _gen_base(db, project_id: str, generator: str) -> tuple:
    """The accumulated chance level behind one generator's verdicts."""
    try:
        r = db.execute("SELECT base_sum, verdicts FROM leap_generators "
                       "WHERE project_id=? AND generator=?",
                       (project_id, generator)).fetchone()
    except Exception:
        return (0.0, 0)          # database predating these columns
    if not r:
        return (0.0, 0)
    return (r["base_sum"] or 0.0, int(r["verdicts"] or 0))


def base_rate_of(profs: dict, prop: str) -> float | None:
    """How often a claim is held in this population, counting only those who
    took a position. A negated claim's rate is the rate of denying it.

    This is the yardstick a verdict has to beat to have meant anything, and it
    is the number the record was missing."""
    bare = prop[4:] if prop.startswith("not:") else prop
    yes = no = 0
    for pa in profs.values():
        held = pa[0]
        if bare in held:
            yes += 1
        elif ("not:" + bare) in held:
            no += 1
    if not (yes + no):
        return None
    return (no / (yes + no)) if prop.startswith("not:") else yes / (yes + no)


def _wilson_lower(k: int, n: int, z: float = PRIOR_LIFT_Z) -> float:
    """The lower end of a Wilson interval on k successes in n trials.

    A raw rate treats three of three as certainty and three hundred of three
    hundred as the same certainty. The lower bound does not: it is what the
    rate could be if this sample happened to flatter it, so a pair supported by
    a handful of people has to be much cleaner than one supported by hundreds
    to clear the same line. That is the whole reason the floor on support can
    stay small without the bank filling with coincidences.

    Measured on 19,719 real respondents against a known latent structure,
    swapping the raw rate for this bound took structure recovery from 0.534 to
    0.803 and lift from +0.083 to +0.125, while examining MORE claims rather
    than fewer. See benchmarks/external."""
    if n <= 0:
        return 0.0
    p = k / n
    d = 1 + z * z / n
    centre = p + z * z / (2 * n)
    margin = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5)
    return (centre - margin) / d


def _family(prop: str) -> str:
    """The KIND of claim, for calibration: prefers_*, wants_*, uses_*.
    Crude on purpose -- the first token names the speech family well enough
    to notice that guesses about preferences keep landing while guesses
    about tooling keep missing, and crude-but-stated beats clever-but-
    unexplainable in a number that adjusts behaviour."""
    return (prop[4:] if prop.startswith("not:") else prop).split("_", 1)[0]


def _family_records(db, project_id: str, weighted: bool = False) -> dict:
    """Per claim-family, how the verdicts went.

    Counts by default, because a count is what the commons contributes and
    what a person reads in a report. Weighted when boldness is being computed,
    by the same prediction error surprise() returns -- a family that keeps
    being wrong in ways it half expected has learned less from all of it than
    one that was confident and wrong once."""
    out: dict = {}
    for r in db.execute("SELECT proposition, status, strength FROM hypotheses "
                        "WHERE project_id=? AND status IN ('supported','refuted')",
                        (project_id,)):
        fam = _family(r["proposition"])
        won = r["status"] == "supported"
        amount = surprise(r["strength"], won) if weighted else 1
        w, l = out.get(fam, (0, 0))
        out[fam] = (w + (amount if won else 0), l + (0 if won else amount))
    return out


def _house_rate(records) -> float:
    """How often this install's hunches turn out right, at all.

    BASE_STRENGTH is a guess about a population nobody had seen. Measured
    against 19,719 real respondents, hunches landed 68% of the time while
    birth strength was anchored at 35%, and that single gap accounted for most
    of the miscalibration: moving the anchor to the observed rate took Brier
    skill from -0.49 to -0.10, while changing the estimator's shape barely
    moved it at all.

    So the anchor is learned. It is itself shrunk toward BASE_STRENGTH by
    ANCHOR_K pseudo-counts, because an install with four verdicts does not know
    its own hit rate either, and the number would swing wildly if it were
    trusted immediately."""
    wins = sum(w for w, _l in records)
    losses = sum(l for _w, l in records)
    return ((wins + BASE_STRENGTH * ANCHOR_K)
            / (wins + losses + ANCHOR_K))


# How hard the house rate pulls a prior's own measured rate back toward this
# install's general experience. A pair seen in three hundred people nearly
# speaks for itself; one seen in twelve barely moves off the house rate.
PRIOR_ANCHOR_K = 60.0


def _prior_anchor(support: int, refute: int, house: float) -> float:
    """What to expect of a hunch this prior produces, before its own record.

    Birth strength anchored every hunch on the house rate: how often this
    install's guesses land in general. That is the right anchor for a leap from
    a look-alike, where there is nothing else to go on. It is the wrong one for
    a prior, which arrives carrying a direct measurement of how often Q follows
    P across a population, and which was then thrown away.

    The lower bound rather than the rate, for the same reason the mining rule
    uses it: three of three is not certainty. Shrunk toward the house rate by
    support, so a measurement has to be worth something before it displaces the
    install's own experience.

    Measured against 19,668 real respondents this moved Brier skill from -0.09
    to -0.02 on its own, and to +0.08 once the ceiling stopped clipping it.
    Neither change reaches positive skill alone: this produces a correct
    estimate that the old cap then truncated, and raising the cap without this
    only un-clips a wrong one (-0.08)."""
    n = support + refute
    if n <= 0:
        return house
    rate = _wilson_lower(support, n)
    return (rate * n + house * PRIOR_ANCHOR_K) / (n + PRIOR_ANCHOR_K)


def _birth_strength(gen_rec: tuple, fam_rec: tuple,
                    house: float = BASE_STRENGTH, k: float = None) -> float:
    """How bold a hunch is born: the posterior mean of this generator's hit
    rate, shrunk toward what this install's hunches do in general.

    It used to be BASE_STRENGTH plus and minus fixed steps per verdict, which
    is not a probability of anything, and the calibration benchmark was then
    scoring it as though it were. A generator with one confirmed leap came out
    at 0.40 and one with ten at the ceiling, with no notion that one
    observation is thin.

    Now: one win moves a generator a little off the house rate, thirty move it
    a long way, and the FAMILY record counts for half, because what OMEM
    guesses badly in general is weaker evidence about this generator than its
    own record is.

    `k` is how much evidence it takes to move off the house rate, and it is
    raised for borrowed knowledge rather than the answer being cut down
    afterwards. See the pooled branch in leap for why.

    The clamp survives untouched. A hunch may never be born stronger than
    STRENGTH_CEILING however good its record, because a hunch that can dress
    as evidence is the failure this whole layer exists to avoid."""
    gw, gl = gen_rec
    fw, fl = fam_rec
    wins = gw + 0.5 * fw
    losses = gl + 0.5 * fl
    k = BIRTH_K if k is None else k
    a = house * k
    b = (1.0 - house) * k
    p = (wins + a) / (wins + losses + a + b)
    return round(max(STRENGTH_FLOOR, min(STRENGTH_CEILING, p)), 2)


# What a query has to clear before it is answered rather than refused. A
# published bank states what it holds; answering a QUESTION is a different act,
# because the caller is about to do something to a person with the answer.
ASK_MIN_SUBJECTS = 12


def ask(db, project_id: str, given: str = "", expect: str = "",
        limit: int = 20) -> dict:
    """What is known about someone who holds `given`, asked at the moment it
    matters rather than downloaded in advance.

    Answers from this installation's own priors FIRST and the commons snapshot
    second, each labelled, because knowledge about the people this install has
    actually seen outranks knowledge borrowed from populations it has not --
    the same order `leap` applies when it chooses which prior may speak.

    Answered entirely from disk. The pooled rows are the snapshot this machine
    already holds, so asking costs no network call and works with the commons
    unreachable or never contacted at all. The commons is a gift in both
    directions and never a dependency.

    Refuses with a reason rather than returning an empty list. An empty answer
    reads as `no such regularity exists`, when the truth is nearly always `too
    few people here for this to be worth saying`, and a caller acts differently
    on each.
    """
    g = (given or "").strip().lower()
    e = (expect or "").strip().lower()
    if not g and not e:
        return {"answered": False, "answers": [],
                "refused": "ask what? give `given`, a claim the person holds, "
                           "or `expect`, a claim you want anticipated"}

    def matches(a, c):
        return (not g or a == g) and (not e or c == e)

    seen, out, thin = set(), [], 0
    tiers = [("this install", [dict(r) for r in db.execute(
        "SELECT * FROM priors WHERE project_id=?", (project_id,))]),
        ("the commons", _pooled_rows(db))]
    for label, rows in tiers:
        for r in rows:
            a, c = r["antecedent"], r["consequent"]
            if not matches(a, c) or (a, c) in seen:
                continue
            total = r["support"] + r["refute"]
            if total <= 0:
                continue
            if r["subjects"] < ASK_MIN_SUBJECTS:
                thin += 1
                continue
            seen.add((a, c))
            gen = db.execute(
                "SELECT wins, losses FROM leap_generators WHERE project_id=? "
                "AND generator=?", (project_id, "prior:" + r["id"])).fetchone()                 if r.get("id") else None
            out.append({
                "given": a, "expect": c, "source": label,
                "rate": round(r["support"] / total, 3),
                "confident_rate": round(_wilson_lower(r["support"], total), 3),
                "people": r["subjects"],
                "held_both": r["support"],
                "held_first_denied_second": r["refute"],
                "populations": r.get("frames") or None,
                "installations": r.get("sources") or None,
                # What happened when this was actually used here, which is a
                # different question from how often it held in a population.
                "when_applied": ({"supported": gen["wins"],
                                  "refuted": gen["losses"]} if gen else None),
                "says": "of %d people who hold %s, %d also hold %s"
                        % (total, a, r["support"], c),
            })
    if not out:
        if thin:
            return {"answered": False, "answers": [],
                    "refused": "%d regularity(ies) touch this and none rests on "
                               "at least %d people. Too thin to answer with."
                               % (thin, ASK_MIN_SUBJECTS)}
        return {"answered": False, "answers": [],
                "refused": "nothing here connects %s. That is not a finding "
                           "that no connection exists: this install has not "
                           "seen enough people, and the commons has not been "
                           "contributed to enough, for it to be sayable."
                           % (("holding " + g) if g else ("anything to " + e))}
    out.sort(key=lambda x: (x["source"] != "this install", -x["people"]))
    return {"answered": True, "answers": out[:limit],
            "how_to_read": "Rates are over people who took a position, never "
                           "over everyone. `confident_rate` is the lower bound "
                           "of the rate, which is what a small sample is "
                           "actually worth. None of this is a fact about the "
                           "person in front of you, and anything they have "
                           "actually said overrides all of it."}


def weigh(db, project_id: str, claim: str, holds=None, limit: int = 20) -> dict:
    """Weigh a belief against the population, without ruling on it.

    `ask` answers what to expect. This answers a different question, and it is
    the one the record needs: an agent believed something about a person; was
    that belief defensible on what was known at the time? The Testimony Record
    says what was believed and on what evidence. This says what the population
    evidence says about it, which is the other half of being able to check a
    claim made by a machine.

    It does NOT rule on the claim. Nothing here concludes that a person holds
    or does not hold anything: the bank holds counts over populations, and a
    regularity is not a fact about anybody. What it returns is the evidence
    pointing each way, with the counts behind each piece, so a person can
    judge. A system that answered `true` or `false` here would be deciding what
    is true about someone from statistics about other people, which is the one
    thing this project exists to refuse.

    `holds` is what is known about the person -- the same claims an agent would
    have had in front of it. Each is looked up as an antecedent: a prior
    pointing at the claim supports the belief, one pointing at its negation
    undermines it.
    """
    c = (claim or "").strip().lower()
    if not c:
        return {"checked": False, "refused": "no claim to check"}
    bare_c = c[4:] if c.startswith("not:") else c
    neg_c = bare_c if c.startswith("not:") else ("not:" + bare_c)
    known = [str(x).strip().lower() for x in (holds or []) if str(x).strip()]
    if not known:
        return {"checked": False, "claim": c,
                "refused": "nothing known about this person to weigh the claim "
                           "against. Give `holds`: what the agent had in front "
                           "of it when it formed the belief."}

    supports, undermines = [], []
    for k in known:
        for direction, target, bucket in (("for", c, supports),
                                          ("against", neg_c, undermines)):
            r = ask(db, project_id, given=k, expect=target, limit=limit)
            for a in r.get("answers", []):
                bucket.append({**a, "because_they_hold": k})

    n_for = len(supports)
    n_against = len(undermines)
    if not n_for and not n_against:
        verdict = ("The bank says nothing either way. That is not evidence the "
                   "belief is wrong: no contributed population has shown a "
                   "regularity connecting what is known about this person to "
                   "this claim.")
    elif n_for and not n_against:
        verdict = ("The population evidence leans toward the belief. It remains "
                   "a regularity about other people, not a fact about this one.")
    elif n_against and not n_for:
        verdict = ("The population evidence leans against the belief. That is a "
                   "reason to look again at what it rested on, not a finding "
                   "that it is false.")
    else:
        verdict = ("The evidence is divided, and both sides are below. A "
                   "regularity pointing each way is exactly the case where a "
                   "population should not settle anything about a person.")

    return {
        "checked": True, "claim": c, "given_that_they_hold": known,
        "supported_by": sorted(supports, key=lambda x: -x["people"])[:limit],
        "undermined_by": sorted(undermines, key=lambda x: -x["people"])[:limit],
        "verdict": verdict,
        "how_to_read": "This weighs a belief against counts over other people. "
                       "It does not decide whether the belief is true, and "
                       "nothing here outranks what the person has actually "
                       "said. Where the two disagree, the person wins.",
    }


def calibration(db, project_id: str) -> dict:
    """What OMEM knows about its own guessing: per claim-family and per
    generator, how the verdicts have gone. Read-only self-knowledge; the
    same numbers already feed birth strength."""
    fams = {fam: {"supported": w, "refuted": l,
                  "rate": round(w / (w + l), 2) if (w + l) else None}
            for fam, (w, l) in sorted(_family_records(db, project_id).items())}
    gens = {}
    try:
        rows = list(db.execute(
            "SELECT generator, wins, losses, base_sum, verdicts FROM "
            "leap_generators WHERE project_id=? ORDER BY generator",
            (project_id,)))
    except Exception:      # database predating the base-rate columns
        rows = [dict(r, base_sum=None, verdicts=None) for r in db.execute(
            "SELECT generator, wins, losses FROM leap_generators "
            "WHERE project_id=? ORDER BY generator", (project_id,))]
    for r in rows:
        t = r["wins"] + r["losses"]
        rate = round(r["wins"] / t, 2) if t else None
        e = {"supported": r["wins"], "refuted": r["losses"], "rate": rate,
             "n": t}
        vd = int(r["verdicts"] or 0) if r["verdicts"] is not None else 0
        if vd and rate is not None:
            exp = (r["base_sum"] or 0.0) / vd
            e["expected"] = round(exp, 3)
            e["lift"] = round(rate - exp, 3)
        # The condition travels with the number. A rate whose lift is unknown,
        # or which rests on too few verdicts to be a rate about anything, says
        # so here rather than leaving the reader to assume otherwise -- the one
        # place this was already done, the calibration scorer's note about the
        # strength cap, is what identified the largest defect this layer had.
        if t < MIN_VERDICTS_FOR_RATE:
            e["note"] = ("%d verdict(s): too few to be a rate about anything"
                         % t)
        elif "lift" not in e:
            e["note"] = ("rate only, no lift: these verdicts predate the "
                         "base rate being recorded, so how much better than "
                         "chance this was is unknown")
        elif e["lift"] <= 0:
            e["note"] = ("no better than the claim's own base rate: this "
                         "generator has been right about things that were "
                         "usually true anyway")
        gens[r["generator"]] = e
    return {"families": fams, "generators": gens,
            "priors": priors(db, project_id)}


def _positive_clusters(profs: dict) -> dict:
    """Cluster POSITIVE propositions only. Negations are handled by name, not
    by embedding: the offline char-hash embedder scores "not:wants_pdf" and
    "wants_pdf" as near-identical, so clustering them together would file a
    subject's refutation as if it were support. Both the priors miner and the
    priors leap read reps through here, so their vocabularies always agree."""
    pos = sorted({x for pa in profs.values() for x in pa[0]
                  if not x.startswith("not:")})
    return _prop_clusters(pos) if pos else {}


def learn_priors(p, db) -> dict:
    """Mine the instance tier for regularities that transfer across people.

    For every pair of positive property-clusters (P, Q), count the subjects
    who hold P and also hold Q (support) versus those who hold P and OPPOSE Q
    (refute -- they hold not:Q, or a positive claim declared contradictory to
    Q). A pair that clears PRIOR_FLOOR_N support, PRIOR_MIN_RATE, and
    PRIOR_MIN_LIFT over the consequent's own base rate becomes a prior P -> Q.
    The prior stores COUNTS, never a subject or a sentence: it is knowledge
    about people in general, not a record of any person, which is what makes it
    inspectable and portable without leaking anyone.

    THE LIFT TEST IS THE ONE THAT MAKES THIS A REGULARITY. Without it the rule
    asks only whether most P-holders hold Q, which any popular Q satisfies on
    its own, and the result is a bank full of things most people think rather
    than things that follow from anything. Q's base rate here is measured over
    the same population the pair was mined from, so a prior has to say more
    about P-holders than the room already says about everyone.

    It is the LOWER BOUND of the rate that must clear that line, not the rate
    itself, so a pair resting on three people has to be far cleaner than one
    resting on three hundred to earn the same standing.

    Absence is not counted against a prior. A subject who holds P but has no
    stated position on Q is neither support nor refute -- they are precisely
    the silence a prior later fills. The rate is honest about only what is
    known.
    """
    T = p.now()
    profs = _profiles(db, p, T)
    rep_of = _positive_clusters(profs)
    pos_holders: dict = {}                  # positive cluster rep -> subjects
    neg_bare: dict = {}                     # bare prop -> subjects holding not:it
    for s, pa in profs.items():
        for x in pa[0]:
            if x.startswith("not:"):
                neg_bare.setdefault(x[4:], set()).add(s)
            else:
                pos_holders.setdefault(rep_of.get(x, x), set()).add(s)

    def opposers(q_rep: str) -> set:
        out = set()
        for bare, subs in neg_bare.items():     # holders of not:<in cluster q>
            if rep_of.get(bare, bare) == q_rep:
                out |= subs
        for opp in _declared_opposites(p, q_rep):   # positive declared opposites
            if not opp.startswith("not:"):
                out |= pos_holders.get(rep_of.get(opp, opp), set())
        return out

    context = "default"                     # per-context rates are phase 3
    reps = sorted(pos_holders)
    # Who opposes each consequent, computed once. This used to be called from
    # inside the pair loop, twice per surviving pair after the lift test
    # arrived, and each call walked every negated proposition and asked the
    # engine for declared opposites. That made a loop which is quadratic in
    # vocabulary by design into one that is cubic, and the cost per pair grew
    # with the population, which is the shape of that mistake. One pass here,
    # constant lookups below.
    opp_of = {q: opposers(q) for q in reps}

    # Subject sets become bitmasks before the loop. Intersecting two Python
    # sets is linear in the population and this loop does it twice per pair, so
    # the cost per pair grew with the number of people even after the
    # vocabulary walk was hoisted out. A bitmask intersection is one machine
    # word per sixty four subjects: measured thirty times faster at a thousand
    # people, ninety at fifty thousand, and the gap widens as the population
    # does, which is the direction that matters.
    _bit = {s: i for i, s in enumerate(profs)}

    def _mask(subs) -> int:
        m = 0
        for s in subs:
            m |= 1 << _bit[s]
        return m

    _popcount = ((lambda x: x.bit_count()) if hasattr(int, "bit_count")
                 else (lambda x: bin(x).count("1")))   # bit_count is 3.10+

    pos_mask = {q: _mask(pos_holders[q]) for q in reps}
    opp_mask = {q: _mask(opp_of[q]) for q in reps}
    q_base = {}
    for q in reps:
        yes, no = _popcount(pos_mask[q]), _popcount(opp_mask[q])
        q_base[q] = (yes / (yes + no)) if (yes + no) else None
    # Both spaces admit negation. Until now `reps` was positive-only and both
    # loops walked it, so two whole classes of regularity could never be
    # learned: what people who DENY P tend to hold, and what people who hold P
    # tend to DENY. The second is the expensive omission -- a system that can
    # only ever guess "holds" is structurally unable to be right about a denial,
    # and it either stays silent or is wrong.
    #
    # Measured over 19,668 real respondents on three independent seed groups,
    # admitting both takes coverage from 762/721/740 hunches to 1249/1194/1226
    # and marginal lift from +0.128/+0.104/+0.130 to +0.197/+0.180/+0.183:
    # roughly two and a half times the correct answers above chance. Negated
    # ANTECEDENTS alone are worse than positive-only in all three groups, and
    # better than positive-only in all three once negated consequents exist
    # alongside them, because `not:P -> not:Q` is then expressible and "people
    # who deny P tend to deny Q" is the strongest pattern this data holds.
    # The interaction is why both ship together or neither does.
    #
    # Brier skill is NOT the measure here and falls while this improves, for a
    # reason worth stating: admitting denials raises the observed rate, which
    # grows the base-rate reference the score divides by. Coverage and lift are
    # the comparable pair. See benchmarks/external/README.md.
    ant_space = [(q, pos_mask[q], pos_holders[q]) for q in reps]
    ant_space += [("not:" + q, opp_mask[q], opp_of[q])
                  for q in reps if opp_of[q]]
    cons_space = []
    for q in reps:
        cons_space.append((q, pos_mask[q], opp_mask[q], q_base[q]))
        _b = q_base[q]
        cons_space.append(("not:" + q, opp_mask[q], pos_mask[q],
                           None if _b is None else 1.0 - _b))

    result = {"examined_pairs": 0, "learned": 0, "kept": 0}
    kept = 0
    for P, base_mask, base in ant_space:
        if len(base) < PRIOR_FLOOR_N:
            continue
        bare_p = P[4:] if P.startswith("not:") else P
        for Q, q_yes, q_no, base_q in cons_space:
            bare_q = Q[4:] if Q.startswith("not:") else Q
            if bare_q == bare_p:
                continue        # a claim never predicts itself or its negation
            result["examined_pairs"] += 1
            support = _popcount(base_mask & q_yes)
            if support < PRIOR_FLOOR_N:
                continue
            refute = _popcount(base_mask & q_no)
            total = support + refute
            if total == 0 or support / total < PRIOR_MIN_RATE:
                continue
            # ...and it has to beat what the whole population already says
            # about Q, or it is Q's popularity wearing P as a hat.
            if base_q is not None and                     _wilson_lower(support, total) < base_q + PRIOR_MIN_LIFT:
                continue
            if kept >= PRIOR_MAX:
                break
            pid_ = "pr_" + hashlib.sha256(
                f"{p.id}|{context}|{P}|{Q}".encode()).hexdigest()[:12]
            db.execute(
                "INSERT OR REPLACE INTO priors(id,project_id,antecedent,"
                "consequent,context,support,refute,subjects,updated) "
                "VALUES(?,?,?,?,?,?,?,?,?)",
                (pid_, p.id, P, Q, context, support, refute, len(base),
                 time.time()))
            kept += 1
            result["learned"] += 1
    result["kept"] = kept
    db.commit()
    return result


def priors(db, project_id: str) -> list[dict]:
    """The learned regularities, each with TWO honest rates: how the pattern
    held in the population it was mined from, and how it has fared when
    actually projected onto someone's silence (its verdict record, the same
    ledger every generator keeps). A prior that has never been applied has no
    track record yet, and says so."""
    gens = {r["generator"]: (r["wins"], r["losses"]) for r in db.execute(
        "SELECT generator, wins, losses FROM leap_generators WHERE project_id=?",
        (project_id,))}
    out = []
    for r in db.execute("SELECT * FROM priors WHERE project_id=? ORDER BY "
                        "support DESC, id", (project_id,)):
        total = r["support"] + r["refute"]
        gw, gl = gens.get("prior:" + r["id"], (0, 0))
        vt = gw + gl
        out.append({
            "id": r["id"],
            "pattern": f'holds {r["antecedent"]} -> holds {r["consequent"]}',
            "antecedent": r["antecedent"], "consequent": r["consequent"],
            "context": r["context"],
            "in_population": {"support": r["support"], "refute": r["refute"],
                             "subjects": r["subjects"],
                             "rate": round(r["support"] / total, 2) if total else None},
            "when_applied": {"supported": gw, "refuted": gl,
                             "rate": round(gw / vt, 2) if vt else None},
            "fires": (r["support"] >= PRIOR_FLOOR_N and total > 0
                      and r["support"] / total >= PRIOR_MIN_RATE),
        })
    return out


def _pooled_k(pr) -> float:
    """Pseudo-counts a borrowed prior must overcome before its own record
    speaks. Larger means a higher bar, never a lower answer."""
    k = BIRTH_K / POOLED_DISCOUNT
    frames = pr.get("frames")
    if isinstance(frames, int) and 0 < frames < POOLED_MIN_FRAMES:
        k /= MONOCULTURE_DISCOUNT
    return k


def _pooled_rows(db) -> list[dict]:
    """The commons bank as prior-shaped rows.

    Read with SQL rather than through commons.py, which imports this module;
    the table is the contract between them. A database that has never synced,
    or predates the table, contributes nothing and raises nothing -- the
    commons is a gift in both directions and never a dependency."""
    try:
        return [dict(r) for r in db.execute(
            "SELECT antecedent, consequent, support, refute, subjects, sources, "
            "frames FROM commons_pooled")]
    except Exception:
        pass            # older table, no frame columns: fall back, do not go dark
    try:
        return [dict(r) for r in db.execute(
            "SELECT antecedent, consequent, support, refute, subjects, sources "
            "FROM commons_pooled")]
    except Exception:
        return []


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
    # The open beliefs, read ONCE and indexed by the subject they are about.
    # Both loops below want the beliefs about one person, and both used to get
    # them by walking every assertion in the store and discarding the rest,
    # from inside a loop over entities and again from inside a loop over
    # priors. In steady state, when reality already speaks and nothing is
    # leapable, four hundred entities did twelve hundred full store scans and
    # two point eight million assertion reads, taking five seconds to produce
    # nothing. None of those scans depended on the loop they sat inside.
    _open = _open_beliefs(p, T)
    by_subject: dict = {}
    for _a in _open:
        if len(_a.subjects) == 1:
            by_subject.setdefault(list(_a.subjects)[0], []).append(_a)
    all_props = sorted({x for pa in profs.values() for x in pa[0]})
    rep_of = _prop_clusters(all_props)
    weights = _feature_weights(profs, rep_of)
    # One representative map per entity, not two per comparison. The scan is
    # quadratic in entities by nature, so anything rebuilt inside it is paid
    # for a quadratic number of times.
    ent_reps = {e: _reps_map(pa[0], rep_of) for e, pa in profs.items()}
    # Who holds each feature, so a target is only compared with entities it
    # could possibly resemble. An entity sharing no proposition and no relation
    # with the target scores exactly zero, and MIN_SIMILARITY is 2.0, so
    # skipping it changes no result: the neighbours list is identical, it is
    # just built without asking four thousand strangers whether they have
    # anything in common when the answer is written down already.
    feature_owners: dict = {}
    for _e, _reps in ent_reps.items():
        for _rep in _reps:
            feature_owners.setdefault(("p", _rep), []).append(_e)
    for _e, _pa in profs.items():
        for _rc in _pa[1]:
            feature_owners.setdefault(("r", _rc), []).append(_e)
    # WEIGHTED records here rather than counts: how bold to be about the next
    # guess is a function of how much each past verdict actually taught.
    fam_recs = _family_records(db, p.id, weighted=True)
    gen_recs = _gen_records(db, p.id)
    # What this install's hunches do in general, learned rather than assumed.
    # Every new generator starts here instead of at a constant nobody measured.
    house = _house_rate(gen_recs.values())
    result = {"examined": 0, "leapt": [], "skipped_spent": 0, "refused": []}
    # The system could not see its own selection. It answers only where a
    # prior fires, and that is not a random subset: measured against an
    # external reference it turned out to answer the claims whose base rate
    # already supplies most of the answer, and to decline the balanced ones
    # where a forecast is worth most. That was invisible from in here.
    #
    # So a pass now reports the mean base rate of the claims it spoke about
    # beside the mean over every claim in the population. If the first is much
    # the higher, the pass was picking the easy questions, and it says so.
    _base_cache: dict = {}

    def _base_of(prop):
        if prop not in _base_cache:
            _base_cache[prop] = base_rate_of(profs, prop)
        return _base_cache[prop]

    _spoken: list = []
    _all_props = {x for pa in profs.values() for x in pa[0]}
    _pop_bases = [b for b in (_base_of(x) for x in sorted(_all_props))
                  if b is not None]
    if _pop_bases:
        result["population_base_mean"] = round(
            sum(_pop_bases) / len(_pop_bases), 3)

    def _note_spoken(prop):
        """Recorded as it happens, not totalled at the end. leap returns from
        inside its loops when MAX_NEW_PER_RUN fills, so anything computed at
        the bottom is missing precisely on the pass where the cap fired -- and
        that is the state a mature installation is in every time."""
        b = _base_of(prop)
        if b is None:
            return
        _spoken.append(b)
        result["spoken_base_mean"] = round(sum(_spoken) / len(_spoken), 3)
        if _pop_bases:
            result["selection_bias"] = round(
                result["spoken_base_mean"]
                - result["population_base_mean"], 3)
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
        candidates = set()
        for _rep in ent_reps[tgt]:
            candidates.update(feature_owners.get(("p", _rep), ()))
        for _rc in profs[tgt][1]:
            candidates.update(feature_owners.get(("r", _rc), ()))
        candidates.discard(tgt)
        for other in sorted(candidates):
            if _kind(other) != _kind(tgt):
                continue
            score = _sim_score(ent_reps[tgt], profs[tgt][1],
                               ent_reps[other], profs[other][1], weights)
            if score >= MIN_SIMILARITY:
                neighbors.append((-score, other))
        neighbors.sort()
        # The evidence is built only for the neighbours actually used. It was
        # being written for every entity in the project and thrown away.
        for negscore, nb in neighbors[:MAX_NEIGHBORS]:
            why = _similarity(profs[tgt], profs[nb], rep_of, weights)[1]
            for a in by_subject.get(nb, ()):
                if len(result["leapt"]) >= MAX_NEW_PER_RUN:
                    return result
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
                                           fam_recs.get(_family(prop), (0, 0)),
                                           house)
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
                _note_spoken(prop)
                result["leapt"].append({"hypothesis": hid, "subject": tgt,
                                        "proposition": prop, "strength": strength,
                                        "because": because})

    # Priors: the same leap, but the generator is a learned regularity rather
    # than a look-alike person. A prior fires ONLY into a silence (the target
    # has no state on the consequent), so a general pattern can never overrule
    # what this person is actually known to be. It fills a gap, and the next
    # interrogate pass settles it against reality like any other hunch; the
    # prior's own record (as generator "prior:<id>") takes the win or the loss.
    prior_rows = [dict(r) for r in db.execute(
        "SELECT * FROM priors WHERE project_id=?", (p.id,))]
    # What the rest of the commons has learned, ranked strictly beneath what
    # this install learned itself. Three rules keep the order honest:
    #   * a pooled prior is appended AFTER the local ones, and a pair a local
    #     prior already covers is dropped, so borrowed knowledge never displaces
    #     knowledge about this population;
    #   * its hunches are born weaker (POOLED_DISCOUNT), because a rate across
    #     other people's populations is weaker evidence about this one;
    #   * it is still defeasible in exactly the same way, firing only into a
    #     silence and yielding the instant this person's own evidence speaks.
    # An install that contributes nothing can still read: the published bank is
    # CC BY and the loop is not a payment scheme.
    local_pairs = {(r["antecedent"], r["consequent"]) for r in prior_rows}
    for r in _pooled_rows(db):
        if (r["antecedent"], r["consequent"]) in local_pairs:
            continue
        prior_rows.append({**r, "pooled": True,
                           "id": "pooled:%s>%s" % (r["antecedent"], r["consequent"])})
    # Which prior speaks when several fire into the same silence. Only one may
    # -- `claimed` keeps a single hunch per claim -- and it used to be whichever
    # came first out of the tables, which is arbitrary among priors of equal
    # standing. Best-evidenced first instead.
    #
    # Sorted WITHIN tier, so local still outranks pooled however thin it is.
    # Measured on 19,668 respondents this is worth Brier 0.2006 -> 0.1950 on
    # identical cases, and it turned out to cost nothing: the harness produces
    # no local priors at six subjects, so every one of those reorderings was
    # among pooled rows and no local prior was ever displaced. Sorting globally
    # scored the same. The tier is kept in the key anyway, because a real
    # installation does have local priors and the guarantee should not depend on
    # them being absent.
    prior_rows.sort(key=lambda r: (
        bool(r.get("pooled")),
        -_prior_anchor(r["support"], r["refute"], house)))
    # Positives-only reps, the same vocabulary the miner used, so a stored
    # antecedent/consequent lines up with what a target actually holds.
    prep = _positive_clusters(profs) if prior_rows else {}
    for tgt in targets:
        if tgt not in profs or not prior_rows:
            continue
        held_reps = {prep.get(x, x) for x in profs[tgt][0]
                     if not x.startswith("not:")}
        # What this person has DENIED, by cluster rep. A prior may now carry a
        # negated antecedent, and "does not hold P" is a fact about them in
        # exactly the way "holds P" is: it is in their profile because they
        # said it.
        denied_reps = {prep.get(x[4:], x[4:]) for x in profs[tgt][0]
                       if x.startswith("not:")}
        for pr in prior_rows:
            if len(result["leapt"]) >= MAX_NEW_PER_RUN:
                break
            total = pr["support"] + pr["refute"]
            if pr["support"] < PRIOR_FLOOR_N or total == 0 \
                    or pr["support"] / total < PRIOR_MIN_RATE:
                continue
            ant, cons = pr["antecedent"], pr["consequent"]
            ant_neg = ant.startswith("not:")
            bare_ant = ant[4:] if ant_neg else ant
            cons_neg = cons.startswith("not:")
            bare_cons = cons[4:] if cons_neg else cons
            if bare_ant not in (denied_reps if ant_neg else held_reps):
                continue                      # target doesn't hold the antecedent
            _cons_rep = prep.get(bare_cons, bare_cons)
            if _cons_rep in held_reps or _cons_rep in denied_reps:
                continue                      # already spoken, either way
            # Keyed on the BARE claim, so the engine can never hand one person
            # both "holds Q" and "does not hold Q" about the same silence. A
            # record whose purpose is to keep contradictions visible must not
            # manufacture them, and with negation in the space it otherwise
            # could. The best-evidenced prior now decides the DIRECTION of the
            # guess, not merely which of two ways to say the same thing.
            if (tgt, bare_cons) in claimed:
                continue
            if p.engine.proposition_state([tgt], cons, T) != "UNKNOWN":
                continue                      # DEFEASIBLE: only ever fill a silence
            born = None
            for a in by_subject.get(tgt, ()):
                a_neg = a.proposition.startswith("not:")
                a_bare = a.proposition[4:] if a_neg else a.proposition
                if a_neg == ant_neg and prep.get(a_bare, a_bare) == bare_ant:
                    born = a
                    break
            if born is None:
                continue
            fp = _fp(p.id, tgt, cons, "prior:" + pr["id"])
            if fp in spent:
                result["skipped_spent"] += 1
                continue
            generator = "prior:" + pr["id"]
            # Borrowed knowledge raises the BAR rather than capping the
            # answer. It used to multiply the finished strength by
            # POOLED_DISCOUNT, which stacked on the ceiling: a borrowed hunch
            # could never be born above 0.45 however well it did, while
            # borrowed hunches were measured landing 65% of the time. That is
            # not caution, it is a fixed error. Needing more of its own record
            # before it moves off the house rate says the same thing honestly,
            # and once a borrowed prior has proved itself on THIS install's
            # people it is not really borrowed any more.
            strength = _birth_strength(
                gen_recs.get(generator, (0, 0)),
                fam_recs.get(_family(cons), (0, 0)),
                _prior_anchor(pr["support"], pr["refute"], house),
                _pooled_k(pr) if pr.get("pooled") else BIRTH_K)
            rate = pr["support"] / total
            if pr.get("pooled"):
                frames = pr.get("frames") or 0
                where = (f"across {pr.get('sources', 0)} other installs"
                         + (f" in {frames} kinds of population" if frames else ""))
                because = (f"{where}, people who hold {ant} tend to hold {cons} "
                           f"(held in {pr['support']} of {total}); {tgt} holds {ant}")
            else:
                because = (f"people who hold {ant} tend to hold {cons} "
                           f"(held in {pr['support']} of {total}); {tgt} holds {ant}")
            docket = {"supports": [{"kind": "prior", "prior": pr["id"],
                                    "pooled": bool(pr.get("pooled")),
                                    "detail": f"{ant} -> {cons}, rate {rate:.2f}"}],
                      "undermines": [],
                      "gaps": [f"no direct evidence about {tgt} yet"]}
            hid = "hy_" + fp[:12]
            db.execute("INSERT OR IGNORE INTO hypotheses(id,project_id,subject,"
                       "proposition,born_from,generator,because,strength,status,"
                       "docket,passes,fp,created) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                       (hid, p.id, tgt, cons, born.id, generator, because,
                        strength, "open", json.dumps(docket), 0, fp, time.time()))
            spent.add(fp)
            claimed.add((tgt, bare_cons))
            _note_spoken(cons)
            result["leapt"].append({"hypothesis": hid, "subject": tgt,
                                    "proposition": cons, "strength": strength,
                                    "because": because, "from_prior": pr["id"]})
    # What this pass chose to speak about, against what was available to speak
    # about. Reported rather than acted on: a pass that answers only the easy
    # claims is not necessarily wrong, but it should not be able to look the
    # same as one that answers the hard ones.
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
    # Who holds each proposition, and what each proposition's declared
    # opposites are, both built once for the pass. The corroboration scan below
    # used to walk every entity for every open hypothesis and ask the engine
    # for declared opposites inside that walk, which is one engine query per
    # hypothesis per entity. Neither depends on the entity being examined.
    holders_of: dict = {}
    for _e, _pa in profs.items():
        for _x in _pa[0]:
            holders_of.setdefault(_x, set()).add(_e)
    _opp_cache: dict = {}

    def _opposites(prop_: str) -> set:
        if prop_ not in _opp_cache:
            _opp_cache[prop_] = set(_declared_opposites(p, prop_))
        return _opp_cache[prop_]

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
            for opp in sorted(_opposites(prop)):
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
            # circumstantial: other look-alikes holding, or opposing, the claim.
            # Only entities holding the claim or one of its declared opposites
            # can do anything in this loop, so the rest are skipped. Sorted, so
            # the docket reads in the same order it always did.
            opps = _opposites(prop)
            relevant = set(holders_of.get(prop, ()))
            for _o in opps:
                relevant |= holders_of.get(_o, set())
            for other in sorted(relevant):
                if other in (subject, row["generator"]) or _kind(other) != _kind(subject):
                    continue
                if prop in profs[other][0] and not any(
                        s.get("entity") == other for s in docket["supports"]):
                    docket["supports"].append({"kind": "corroborating_case",
                                               "entity": other})
                    strength = min(STRENGTH_CEILING, strength + 0.05)
                for opp in opps:
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
            # What chance was on this claim, in this population, right now.
            # Without it the record cannot say whether the guess was worth
            # making -- only whether it happened to be right.
            _score_generator(db, p.id, row["generator"],
                             verdict == "supported", row["strength"],
                             base_rate_of(profs, prop))
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


# ── the joint intelligence bank ──────────────────────────────────────────────

def _identifying(token: str) -> bool:
    """A proposition token that could name someone or something. Relation
    props embed the target's slug (rel_works_at_acme names a company), colons
    carry raw entity ids, digits carry extracted values (a contract price, a
    payment term). The bank refuses them all, so what it exports can be
    published without a redaction pass.

    Blacklisting those formats is enough for the LOCAL bank, whose tokens come
    from OMEM's own extraction. It is NOT enough for the commons collector,
    which re-validates tokens contributed by untrusted clients: a crafted token
    could smuggle an email (john@acme.com), a domain, or a capitalised name past
    the three checks above, none of which carry a digit, a colon, or the rel_
    prefix. So a legitimate behaviour token is also required to be exactly what
    one is: lowercase letters and underscores, nothing else. An @, a dot, an
    uppercase letter, or any other character is refused at the door. (A token
    engineered to look like a plain lowercase word is the one thing this cannot
    tell from a real one; closing that needs a fixed vocabulary, tracked
    separately.)

    A single leading `not:` is the negation marker and is stripped before any
    of that. It is not an entity id: what follows it is checked exactly as a
    positive token would be, so `not:prefers_pdf` passes and `not:person:sam`
    still does not, because the second colon survives the strip."""
    if token.startswith("not:"):
        token = token[4:]
    if token.startswith("rel_") or ":" in token or bool(re.search(r"\d", token)):
        return True
    return re.fullmatch(r"[a-z_]+", token) is None


def bank(db, project_ids: list[str]) -> list[dict]:
    """Priors from every given project, merged into one population-level view.

    Anonymity is structural, not procedural. A prior already stores counts and
    proposition tokens -- never a subject, a sentence, or a name -- and the
    bank additionally drops any token that could embed an identity or a value
    (see _identifying). What remains is knowledge about people in general:
    "holds P -> usually holds Q, at this rate, over this many subjects",
    publishable as-is because there is nothing in it to leak."""
    agg: dict = {}
    for pid in project_ids:
        for r in db.execute(
                "SELECT antecedent, consequent, support, refute, subjects "
                "FROM priors WHERE project_id=?", (pid,)):
            a, c = r["antecedent"], r["consequent"]
            if _identifying(a) or _identifying(c):
                continue
            e = agg.setdefault((a, c), {
                "antecedent": a, "consequent": c,
                "support": 0, "refute": 0, "subjects": 0, "projects": 0})
            e["support"] += r["support"]
            e["refute"] += r["refute"]
            e["subjects"] += r["subjects"]
            e["projects"] += 1
    out = []
    for e in agg.values():
        total = e["support"] + e["refute"]
        if total == 0 or e["support"] < PRIOR_FLOOR_N:
            continue
        rate = e["support"] / total
        out.append({**e,
                    "pattern": f'holds {e["antecedent"]} -> holds {e["consequent"]}',
                    "rate": round(rate, 3),
                    "fires": rate >= PRIOR_MIN_RATE})
    out.sort(key=lambda x: (-x["rate"], -x["support"], x["pattern"]))
    return out


GENERATOR_CLASSES = ("neighbour", "prior")


def _generator_class(generator: str) -> str:
    """WHICH KIND of leap produced a hypothesis, without saying which one.

    `generator` is not a code identifier and must never be published. For a
    look-alike projection `leap()` sets it to the NEIGHBOUR'S SUBJECT ID, so the
    column holds real people; `_identifying` never sees it, because that
    refusal inspects proposition tokens. The class can be published: it is the
    distinction the calibration question actually turns on -- does projecting
    from a similar person beat projecting from a population rate -- and it
    names nobody."""
    return "prior" if generator.startswith("prior:") else "neighbour"


def calibration_bank(db, project_ids: list[str]) -> list[dict]:
    """How the guessing went, per generator CLASS and per claim family, pooled
    across projects. Counts only, floored like priors.

    This is the half of the bank that says how much a thin-evidence claim about
    a person is worth, rather than what people are like. One install learns it
    slowly and only about its own population; pooled, it is the question no
    single install can answer.

    Family tokens are refused here if they could carry an identity, and the
    caller filters again against the commons vocabulary before anything is
    sent -- the same two doors a prior passes through."""
    gens: dict = {}
    fams: dict = {}
    for pid in project_ids:
        for r in db.execute("SELECT generator, wins, losses FROM leap_generators "
                            "WHERE project_id=?", (pid,)):
            k = _generator_class(r["generator"])
            w, l = gens.get(k, (0, 0))
            gens[k] = (w + r["wins"], l + r["losses"])
        for fam, (w, l) in _family_records(db, pid).items():
            if _identifying(fam):
                continue
            pw, pl = fams.get(fam, (0, 0))
            fams[fam] = (pw + w, pl + l)

    out = []
    for scope, table in (("generator_class", gens), ("family", fams)):
        for name, (w, l) in sorted(table.items()):
            if w + l < PRIOR_FLOOR_N:
                continue  # too few verdicts to be a rate about anything
            out.append({"scope": scope, "name": name,
                        "supported": w, "refuted": l,
                        "rate": round(w / (w + l), 3)})
    return out
