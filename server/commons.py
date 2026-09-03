"""The OMEM commons: anonymous behavioural regularities, pooled across
installations that chose to contribute, into one bank the project's creator
studies and writes from. The goal it serves: give AI a better understanding of
human nature and behaviour, without ever holding a fact about a person.

THE CONSENT MODEL, stated once and enforced in code, because "runs on your own
machine, with no external services" is a promise this feature must not bend:

  * A stock install never sends anything, and has no bank. Contribution
    happens only when the OPERATOR sets OMEM_COMMONS_URL themselves; unset
    means no network call, ever. What is sent is exactly the anonymous bank
    they can read on their own disk (intelligence-bank.json).
  * The collector role is configuration (OMEM_BANK_COLLECTOR=1), not a user
    feature: everywhere else the bank routes are 404 and the page is absent.
  * The collector RE-VALIDATES every contributed token with the same
    _identifying refusal used locally, so even a modified contributor cannot
    push a name, an id, or a value into the commons. Anonymity is checked at
    the door it enters, not only the door it leaves.
"""
from __future__ import annotations

import json
import time
import uuid

from hypotheses import _identifying, PRIOR_FLOOR_N

COMMONS_SCHEMA = """
CREATE TABLE IF NOT EXISTS commons_contributions(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  instance TEXT NOT NULL,
  received REAL NOT NULL,
  patterns TEXT NOT NULL,
  calibration TEXT,
  terms TEXT);
CREATE INDEX IF NOT EXISTS commons_inst ON commons_contributions(instance, received);
CREATE TABLE IF NOT EXISTS commons_meta(k TEXT PRIMARY KEY, v TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS commons_withdrawals(
  instance TEXT PRIMARY KEY,
  withdrawn REAL NOT NULL);
"""


POOLED_SCHEMA = """
CREATE TABLE IF NOT EXISTS commons_pooled(
  antecedent TEXT NOT NULL,
  consequent TEXT NOT NULL,
  support INTEGER NOT NULL,
  refute INTEGER NOT NULL,
  subjects INTEGER NOT NULL,
  sources INTEGER NOT NULL,
  frames INTEGER NOT NULL DEFAULT 0,
  rate_min REAL,
  rate_max REAL,
  received REAL NOT NULL,
  PRIMARY KEY(antecedent, consequent));
"""

# A pooled prior must have been seen by more than one install before it may
# influence anything. This is the commons-level echo check: one install's
# priors are one population, however many subjects stand behind them, and
# agreement ACROSS installs is the only independence signal available at this
# layer. It is the same argument scripts/independence_estimate.py makes inside
# a project -- agreement is cheap, independent agreement is not -- applied at
# the door where other people's knowledge enters this machine.
POOLED_MIN_SOURCES = 2

# Agreement across installs was the only independence signal at this layer, and
# it is a weak one: two installs that serve the same kind of people in the same
# place are close to one install, and they satisfy POOLED_MIN_SOURCES between
# them. A pattern can therefore replicate perfectly and still be a fact about a
# monoculture rather than about people.
#
# So a contribution may declare the SHAPE of the population its counts came
# from, and a pooled row records how many distinct shapes back it. The bar is
# separate from POOLED_MIN_SOURCES because they answer different questions:
# sources asks whether more than one machine saw it, frames asks whether more
# than one kind of population did.
POOLED_MIN_FRAMES = 2

# Coarse on purpose, in all three axes. A frame describes a deployment, not a
# person, but a precise one would still fingerprint a small operator -- an exact
# subject count plus a country plus a niche domain can identify a single
# company. Macro-region rather than country, a band rather than a count, and a
# closed list of domains, refused at both doors like the pattern vocabulary.
FRAME_DOMAINS = ("customer_support", "sales", "recruiting", "healthcare",
                 "education", "software", "operations", "personal", "other")
FRAME_REGIONS = ("africa", "americas", "asia", "europe", "oceania")
FRAME_BANDS = ("10-49", "50-199", "200-999", "1000+")

# ── the terms a contribution was made under ─────────────────────────────────
#
# A count is anonymous, so this is not a privacy record. It is a RIGHTS record,
# and it exists because the bank may one day be published in more than one
# form. Which uses an operator agreed to is a fact about the moment they
# agreed, and it cannot be reconstructed afterwards from anything else in the
# database -- so it is written down at the moment of contribution or it is lost.
#
# The rule that makes it worth having: the stored record carries the GRANTS
# THEMSELVES, not just a version pointer. A table keyed by version would mean
# editing this file could silently widen what a contribution made last year
# permitted, which is the failure this is here to prevent. The table below is
# used only to MINT a record; nothing ever reads a grant out of it for a
# contribution already stored.
TERMS_VERSION = "2026-09-03"

# Every use a contribution can grant. A grant absent from a record is a grant
# that was never given.
GRANTS = ("public_commons", "commercial")

TERMS = {
    "2026-09-03": {
        "granted": ["public_commons"],
        "summary": "Counts join the public commons and are published there "
                   "under CC BY 4.0, together with the coarse shape of the "
                   "population they came from: a working domain, a "
                   "macro-region and a size band, all declared by the operator "
                   "and none of them a fact about a person. They are not "
                   "licensed for any commercial dataset; that would need a "
                   "separate question, asked before it applies and never "
                   "backdated.",
    },
    "2026-09-02": {
        "granted": ["public_commons"],
        "summary": "Counts join the public commons and are published there "
                   "under CC BY 4.0. They are not licensed for any commercial "
                   "dataset; that would need a separate question, asked "
                   "before it applies and never backdated.",
    },
}


def mint_terms() -> dict:
    """The terms record to attach to a contribution made right now."""
    t = TERMS[TERMS_VERSION]
    return {"version": TERMS_VERSION, "granted": list(t["granted"]),
            "recorded": time.time()}


def grants_of(terms) -> set:
    """What a stored record actually permits.

    A missing or unreadable record grants the public commons and nothing else.
    That is not a lenient default, it is the accurate one: a contribution that
    arrived before this existed was made by an operator who was shown the
    public-commons opt-in and no other question, so the public commons is
    exactly what they agreed to. Every other use has to be asked for. Silence
    is never a grant."""
    if isinstance(terms, str):
        try:
            terms = json.loads(terms)
        except (TypeError, ValueError):
            terms = None
    if not isinstance(terms, dict):
        return {"public_commons"}
    granted = terms.get("granted")
    if not isinstance(granted, list):
        return {"public_commons"}
    return {g for g in granted if g in GRANTS}


def validate_terms(payload) -> tuple[dict | None, str | None]:
    """The terms half of a contribution, checked at the door.

    A contributor may omit it -- an older client has no such field, and the
    commons must not break under a version skew -- and omission reads as the
    restrictive default above. What is refused is a MALFORMED one, and a grant
    this collector does not recognise, because a record nobody can interpret is
    worse than no record: it looks like consent and cannot be read as any."""
    if not isinstance(payload, dict):
        return None, "payload must be an object"
    t = payload.get("terms")
    if t is None:
        return None, None
    if not isinstance(t, dict):
        return None, "terms must be an object"
    ver = t.get("version")
    if not isinstance(ver, str) or not (1 <= len(ver) <= 32):
        return None, "terms.version must be a short string"
    granted = t.get("granted")
    if not isinstance(granted, list) or len(granted) > len(GRANTS):
        return None, "terms.granted must be a list of grant names"
    for g in granted:
        if g not in GRANTS:
            return None, f"unknown grant refused: {g!r}"
    return {"version": ver, "granted": sorted(set(granted)),
            "recorded": time.time()}, None


def ensure_schema(db):
    """The schema, plus the columns a collector predating calibration and the
    terms record will not have. A collector is a long-lived install, so the
    table is older than both features on every machine that already runs
    one."""
    db.executescript(COMMONS_SCHEMA)
    db.executescript(POOLED_SCHEMA)
    for col in ("calibration", "terms"):
        try:
            db.execute(f"ALTER TABLE commons_contributions ADD COLUMN {col} TEXT")
            db.commit()
        except Exception:
            pass  # already there


MAX_PATTERNS = 500          # one contribution's pattern cap
MAX_CALIBRATION = 200       # families are few; this is a bound, not a target
MAX_INSTANCE_LEN = 64

# The two halves of the bank answer different questions. A pattern says what
# people are like; a calibration row says how much a guess about a person is
# worth. `scope` names which kind of rate a row carries.
CALIBRATION_SCOPES = ("generator_class", "family")
GENERATOR_CLASSES = ("neighbour", "prior")

# ── the commons vocabulary ───────────────────────────────────────────────────
# The structural checks in _identifying stop rel_ tokens, colons, digits, and
# anything that is not lowercase-and-underscores. The one thing they cannot
# stop is a token ENGINEERED to look like a plain lowercase word:
# "johnsmith_of_acmecorp" carries an identity while passing every format
# check. Closing that hole needs a fixed vocabulary, and this is it: a
# commons-bound token must be built ONLY from the words below, joined by
# underscores. The list is behaviour-domain by construction; it deliberately
# contains no given names, no surnames (even the ones that double as common
# words), no company names, and no affiliation connectors ("at"), so no
# composition of allowed words can name an individual or an employer. A
# legitimate long-tail token that uses a word missing here is refused at the
# door with the word named; extending the lexicon is a code change and a
# review, exactly like registering an action type.
COMMONS_LEXICON = frozenset("""
prefers avoids responds replies holds pays renews churns opens ignores
chooses upgrades downgrades cancels reads writes attends skips schedules
delays completes abandons requests demands accepts declines negotiates
escalates complains praises recommends refers returns purchases buys
subscribes unsubscribes clicks browses searches compares waits switches
adopts rejects trusts doubts asks answers follows shares saves spends
invests books orders reserves confirms disputes appeals approves denies
delegates automates prefers wants needs uses avoids likes dislikes values
expects tolerates
is are has have was were be been being does did doing
to of for by via per non the a an and or with without over under
annual monthly weekly daily quarterly yearly hourly biweekly seasonal
recurring onetime morning afternoon evening night weekday weekend early
late often rarely never always sometimes frequently occasionally
email phone chat video call message text letter mail contact contacts notification
notifications reminder reminders newsletter forum portal dashboard app web
mobile desktop online offline async sync live remote inperson
billing invoice invoices payment payments discount discounts refund
refunds credit debit price pricing cost costs budget budgets contract
contracts plan plans tier tiers subscription subscriptions trial trials
demo demos quote quotes proposal proposals order orders shipping delivery
deliveries support ticket tickets feedback survey surveys review reviews
rating ratings renewal renewals upgrade upgrades downgrade downgrades
cancellation cancellations onboarding training documentation docs policy
policies terms privacy security compliance audit audits report reports
meeting meetings agenda agendas deadline deadlines milestone milestones
project projects task tasks workflow workflows process processes approval
approvals escalation escalations
formal informal verbose brief detailed concise technical simple visual
textual private public anonymous personal shared individual group team
solo bulk single multiple standard premium basic advanced custom default
automatic manual digital paper physical virtual local global domestic
international short long fast slow high low big small new old frequent
infrequent flexible strict loyal sensitive cautious aggressive
conservative risk averse quality focused brand conscious feature driven
value oriented deadline detail service touch enterprise startup smb
consumer business customer customers client clients vendor vendors partner
partners user users member members subscriber subscribers buyer buyers
decision maker makers stakeholder stakeholders
works remotely onsite hybrid parttime fulltime overtime
intends considering decided planning intending willing reluctant likely
unlikely ready hesitant eager
pdf spreadsheet slides document documents attachment attachments link
links file files format formats
alpha beta gamma pilot test production staging
upgrade cancel churn retain renew expand contract downgrade
""".split())


def _foreign_word(token: str) -> str | None:
    """First word of a token that is outside the commons lexicon, or None."""
    for w in token.split("_"):
        if w and w not in COMMONS_LEXICON:
            return w
    return None


def lexicon_ok(token: str) -> bool:
    """A commons-publishable token: structurally clean AND built only from
    lexicon words."""
    if not isinstance(token, str) or not token or len(token) > 64:
        return False
    if _identifying(token):
        return False
    return _foreign_word(token) is None

# Where contributions go when an operator says yes: the commons the OMEM
# project runs, on the project's own domain. Overridable with OMEM_COMMONS_URL
# (a lab pooling its own installs would point at its own collector); an
# override also counts as consent, since setting it IS the operator's
# explicit act.
DEFAULT_COMMONS_URL = "https://commons.omem-cloud.com"


def get_choice(db) -> str | None:
    """The operator's recorded decision: 'yes', 'no', or None (never asked)."""
    r = db.execute("SELECT v FROM commons_meta WHERE k='contribute'").fetchone()
    return r["v"] if r else None


def set_choice(db, contribute: bool):
    """Record the decision, and the terms it was made under.

    Either answer is durable; both are revocable from Settings, because consent
    that cannot be withdrawn is not consent. Saying yes also stamps the terms
    in force at that moment, so a later version of them cannot claim to cover a
    decision taken before it existed. Saying no clears the stamp: there is no
    agreement to describe."""
    db.execute("INSERT OR REPLACE INTO commons_meta(k,v) VALUES('contribute',?)",
               ("yes" if contribute else "no",))
    if contribute:
        db.execute("INSERT OR REPLACE INTO commons_meta(k,v) VALUES('terms',?)",
                   (json.dumps(mint_terms()),))
    else:
        db.execute("DELETE FROM commons_meta WHERE k='terms'")
    db.commit()


def set_frame_declaration(db, domain: str = "", region: str = ""):
    """Record the operator's declaration of what kind of population this
    install serves. Free text is not stored: a value outside the closed list
    clears the declaration rather than being kept and refused later, so what
    is on disk is always something that can actually travel."""
    d = (domain or "").strip().lower()
    r = (region or "").strip().lower()
    if d in FRAME_DOMAINS and r in FRAME_REGIONS:
        db.execute("INSERT OR REPLACE INTO commons_meta(k,v) VALUES('frame',?)",
                   (json.dumps({"domain": d, "region": r}),))
    else:
        db.execute("DELETE FROM commons_meta WHERE k='frame'")
    db.commit()


def frame_declaration(db) -> dict:
    """What the operator declared, without the size band, which is measured
    rather than declared."""
    r = db.execute("SELECT v FROM commons_meta WHERE k='frame'").fetchone()
    if not r:
        return {}
    try:
        v = json.loads(r["v"])
    except (TypeError, ValueError):
        return {}
    return v if isinstance(v, dict) else {}


def declared_frame(db, subjects: int) -> dict | None:
    """The frame to send with a contribution: the operator's declared domain
    and region, plus the band this install's actual population falls in.

    The size is not taken on trust because it does not have to be -- the
    counts being contributed already say how many subjects there were, and a
    declared size that disagreed with them would be the one part of the frame
    an operator could get wrong without noticing."""
    d = frame_declaration(db)
    return frame_of(subjects, d.get("domain", ""), d.get("region", ""))


def current_terms(db) -> dict:
    """The terms this install contributes under, to travel with the payload.

    An install that consented before the record existed has no stamp, so it
    contributes under the restrictive default -- the same reading the collector
    applies, arrived at from the same argument, rather than two halves of the
    system disagreeing about what an operator agreed to."""
    r = db.execute("SELECT v FROM commons_meta WHERE k='terms'").fetchone()
    if r:
        try:
            t = json.loads(r["v"])
            if isinstance(t, dict):
                return t
        except (TypeError, ValueError):
            pass
    return {"version": "pre-record", "granted": ["public_commons"]}


def instance_id(db) -> str:
    """This install's stable pseudonym for contributions: a random uuid minted
    once, carrying nothing about the machine or its owner."""
    r = db.execute("SELECT v FROM commons_meta WHERE k='instance'").fetchone()
    if r:
        return r["v"]
    v = uuid.uuid4().hex
    db.execute("INSERT OR REPLACE INTO commons_meta(k,v) VALUES('instance',?)", (v,))
    db.commit()
    return v


# ── what may leave this machine, and the argument for each field ────────────
#
# The doors validate what ARRIVES. Nothing pinned what departs, and that is the
# gap the calibration work walked into: `leap_generators.generator` holds
# subject ids, the design proposed contributing the table, and both existing
# doors would have passed it because they inspect proposition tokens rather
# than that column. The lesson written down then was that the anonymity
# argument has to be made per column. This is that lesson as code.
#
# A field absent from these maps is not sent. Not trimmed at the far end, not
# dropped quietly on arrival: never transmitted. Adding one means adding the
# sentence that says why it is safe, which is the point.
CONTRIBUTION_FIELDS = {
    "instance": "a uuid4 minted on this machine, carrying nothing about it or "
                "its owner",
    "patterns": "counts over populations, tokens built from the closed commons "
                "vocabulary and refused at both doors",
    "calibration": "how much a guess about a person was worth, by generator "
                   "CLASS and by lexicon-bound family",
    "terms": "which uses this operator granted, recorded when they granted them",
    "frame": "the coarse shape of the population these counts came from, so "
             "that agreement can be required across DIFFERENT populations "
             "rather than across installs that happen to be alike. Declared by "
             "the operator, optional, and holding no fact about any person",
}

# Which of those may be absent. Written down rather than inferred from whether
# a payload happens to contain them, so that "this one is optional" stays a
# decision somebody made and the guard can still require exact agreement in
# both cases instead of falling back to a subset check, which would let a new
# field travel unnoticed -- the precise failure that map exists to prevent.
OPTIONAL_CONTRIBUTION_FIELDS = {"frame"}

PATTERN_FIELDS = {
    "antecedent": "a behaviour token from the closed vocabulary",
    "consequent": "a behaviour token from the closed vocabulary",
    "support": "how many subjects held both",
    "refute": "how many held the first and opposed the second",
    "subjects": "how many held the first at all",
}

FRAME_FIELDS = {
    "domain": "one of a closed list of coarse working domains, declared by the "
              "operator and never inferred from their data",
    "region": "a macro-region, never a country and never a city",
    "subjects": "a band, never a count: an exact population size is one of the "
                "three things that together would identify an operator",
}

CALIBRATION_FIELDS = {
    "scope": "generator_class or family, which kind of rate this row carries",
    "name": "one of two literals, or a lexicon-bound family token",
    "supported": "how many guesses of this kind reality confirmed",
    "refuted": "how many of those same guesses reality refuted",
}

# Fields the local bank carries for the operator to read, derived entirely from
# the counts above and deliberately NOT transmitted. Listed so a new field is a
# decision rather than a default: the suite fails on any key in neither map,
# which is what turns "we should think about that" into CI.
# `projects` is the one this guard caught on its first run: it counts how
# many of the operator's OWN projects a pattern appeared in, and it was
# travelling because the client sent bank() rows as they sat. It says
# nothing about a person, but it does describe the contributor's
# deployment, and the bank has no use for it. Local.
DERIVED_LOCAL_ONLY = {"pattern", "rate", "fires", "sources", "projects"}


def band_of(subjects: int) -> str | None:
    """The band a population size falls in, or None below the smallest one.

    Under ten subjects there is no band rather than a band called `small`,
    because a frame that narrow describes the operator more than it describes a
    population, and a contribution that thin has nothing to say anyway."""
    try:
        n = int(subjects)
    except (TypeError, ValueError):
        return None
    if n < 10:
        return None
    if n < 50:
        return "10-49"
    if n < 200:
        return "50-199"
    if n < 1000:
        return "200-999"
    return "1000+"


def frame_of(subjects: int, domain: str = "", region: str = "") -> dict | None:
    """The frame to attach to a contribution, or None if the operator declared
    nothing usable. An undeclared frame is not an error: the counts still
    contribute, they simply cannot help satisfy POOLED_MIN_FRAMES, which is the
    honest consequence of declining to say where they came from."""
    d = (domain or "").strip().lower()
    r = (region or "").strip().lower()
    band = band_of(subjects)
    if d not in FRAME_DOMAINS or r not in FRAME_REGIONS or band is None:
        return None
    return {"domain": d, "region": r, "subjects": band}


def validate_frame(frame) -> tuple[dict | None, str | None]:
    """A frame at the door. Absent is fine; present and wrong is not, because a
    value outside the closed list is either a bug or an attempt to smuggle a
    free-text field into a payload that has none."""
    if frame is None:
        return None, None
    if not isinstance(frame, dict):
        return None, "frame must be an object"
    unknown = sorted(set(frame) - set(FRAME_FIELDS))
    if unknown:
        return None, "frame field with no stated argument refused: %s" % unknown
    d, r, b = frame.get("domain"), frame.get("region"), frame.get("subjects")
    if d not in FRAME_DOMAINS:
        return None, "frame domain outside the closed list: %r" % (d,)
    if r not in FRAME_REGIONS:
        return None, "frame region outside the closed list: %r" % (r,)
    if b not in FRAME_BANDS:
        return None, "frame subjects must be a band, not a count: %r" % (b,)
    return {"domain": d, "region": r, "subjects": b}, None


def frame_key(frame) -> str:
    """How a collector counts distinct populations. Undeclared frames all
    collapse to one key rather than counting as one each, so a thousand silent
    installs cannot manufacture the appearance of a thousand populations."""
    if not isinstance(frame, dict):
        return ""
    d, r, b = frame.get("domain"), frame.get("region"), frame.get("subjects")
    if d not in FRAME_DOMAINS or r not in FRAME_REGIONS or b not in FRAME_BANDS:
        return ""       # a partial frame is an undeclared one, not a new kind
    return "%s/%s/%s" % (d, r, b)


def _project(row: dict, fields: dict) -> dict:
    return {k: row[k] for k in fields if k in row}


def contribution_payload(instance: str, patterns: list, calibration: list,
                         terms: dict, frame: dict | None = None) -> dict:
    """The only place a contribution is assembled.

    Rows are projected onto the approved fields rather than sent as they sit in
    the local bank, so a column added upstream cannot travel by accident. The
    projection is the runtime guarantee; the suite pinning these maps against
    what the bank actually produces is what makes anyone notice."""
    body = {
        "instance": instance,
        "patterns": [_project(p, PATTERN_FIELDS) for p in patterns],
        "calibration": [_project(c, CALIBRATION_FIELDS) for c in calibration],
        "terms": terms,
    }
    if frame:
        body["frame"] = _project(frame, FRAME_FIELDS)
    unknown = sorted(set(body) - set(CONTRIBUTION_FIELDS))
    if unknown:
        raise ValueError("field with no stated argument refused: %s" % unknown)
    return body


NOTICE_KEY = "notice_shown"


def notice(db, patterns: int, bank_path: str, dashboard: str) -> str | None:
    """The one time a terminal-only install is told the commons exists.

    The opt-in prompt lives in the dashboard, and `pip install
    omem-infrastructure && omem-server` is the documented way in. A developer
    who used the SDK and never opened a browser was therefore never asked, and
    an install that is never asked can never contribute. That is not a shy
    consent model, it is a consent model the largest group of users cannot
    reach, and the commons cannot fill from a population it never speaks to.

    Three rules, because a notice like this is one step from being a nag:

    It is printed only when there is something real to contribute. Asking on
    first boot means asking about an empty bank, which is a question with no
    content and an answer worth nothing.

    It is printed once, ever. An install that read it and did nothing has
    answered, and asking again would be pretending otherwise.

    It changes nothing on its own. Saying yes still happens in the dashboard,
    under the session-only rule that keeps an API key from deciding an
    instance-wide question, and until then nothing is sent."""
    if patterns <= 0 or get_choice(db) is not None:
        return None
    if db.execute("SELECT v FROM commons_meta WHERE k=?",
                  (NOTICE_KEY,)).fetchone():
        return None
    db.execute("INSERT OR REPLACE INTO commons_meta(k,v) VALUES(?,?)",
               (NOTICE_KEY, str(time.time())))
    db.commit()
    return chr(10).join([
        "",
        "  The commons",
        "    This install has learned %d pattern%s about how people behave,"
        % (patterns, "" if patterns == 1 else "s"),
        "    like \"people who prefer async usually prefer email\". They can",
        "    join a shared bank that studies human behaviour in general, so AI",
        "    can understand people better.",
        "",
        "    Counts only. Never a name, a company, a message, or a number from",
        "    your data. The exact file is already on your disk:",
        "      %s" % bank_path,
        "",
        "    It goes both ways: contributing also pulls the published bank",
        "    back, ranked beneath everything this install learned itself. A",
        "    pattern needs two separate installations before it returns to",
        "    anyone, so early on there is little to receive.",
        "",
        "    Nothing has been sent and nothing will be unless you say so:",
        "      %s" % dashboard,
        "",
        "    Printed once. Ignoring it is an answer.",
        "",
    ])


def should_contribute(db, env_url, is_collector: bool) -> bool:
    """Whether this install may send anything at all.

    Named and testable rather than an inline condition, because it is the
    sentence the whole consent model rests on: a stock install never sends, and
    only an explicit act by the operator changes that. Setting
    OMEM_COMMONS_URL is such an act; so is answering the prompt. Silence is
    not, and a collector never contributes to itself."""
    if is_collector:
        return False
    if env_url:
        return True
    try:
        return get_choice(db) == "yes"
    except Exception:
        return False


def validate(payload) -> tuple[list, str | None]:
    """A contribution, checked at the door. Returns (clean_patterns, error).
    Only counts survive: identifying tokens, absurd sizes, and non-integer
    counts are refused rather than trimmed silently where it matters."""
    if not isinstance(payload, dict):
        return [], "payload must be an object"
    inst = payload.get("instance")
    if not isinstance(inst, str) or not (8 <= len(inst) <= MAX_INSTANCE_LEN) \
            or not inst.replace("-", "").isalnum():
        return [], "instance must be an opaque id (8..64 alphanumeric chars)"
    _frame, ferr = validate_frame(payload.get("frame"))
    if ferr:
        return [], ferr
    pats = payload.get("patterns")
    if not isinstance(pats, list) or len(pats) > MAX_PATTERNS:
        return [], f"patterns must be a list of at most {MAX_PATTERNS}"
    clean = []
    for p in pats:
        if not isinstance(p, dict):
            return [], "every pattern must be an object"
        a, c = p.get("antecedent"), p.get("consequent")
        if not isinstance(a, str) or not isinstance(c, str) \
                or not a or not c or len(a) > 64 or len(c) > 64:
            return [], "antecedent/consequent must be short strings"
        if _identifying(a) or _identifying(c):
            return [], f"identifying token refused: {a if _identifying(a) else c!r}"
        fw = _foreign_word(a) or _foreign_word(c)
        if fw:
            bad = a if _foreign_word(a) else c
            return [], (f"token outside the commons vocabulary refused: {bad!r} "
                        f"(word {fw!r} is not in the lexicon)")
        try:
            s, r, n = int(p.get("support")), int(p.get("refute")), int(p.get("subjects"))
        except (TypeError, ValueError):
            return [], "support/refute/subjects must be integers"
        if s < 0 or r < 0 or n < 0 or s + r > 10_000_000:
            return [], "counts out of range"
        if s < PRIOR_FLOOR_N:
            continue  # below the floor it is not a pattern, skip quietly
        clean.append({"antecedent": a, "consequent": c,
                      "support": s, "refute": r, "subjects": n})
    return clean, None


def validate_calibration(payload) -> tuple[list, str | None]:
    """The calibration half of a contribution, checked at the same door.

    Stricter than the pattern check in one place that matters: `name` under
    `generator_class` must be one of two literals. The local column this is
    derived from holds SUBJECT IDS for look-alike projections (see
    hypotheses._generator_class), so a contributor that sent the raw column
    would be sending people. An enum cannot carry one, and a contributor that
    tries is refused rather than trimmed."""
    if not isinstance(payload, dict):
        return [], "payload must be an object"
    rows = payload.get("calibration")
    if rows is None:
        return [], None                      # optional: an older client sends none
    if not isinstance(rows, list) or len(rows) > MAX_CALIBRATION:
        return [], f"calibration must be a list of at most {MAX_CALIBRATION}"
    clean = []
    for r in rows:
        if not isinstance(r, dict):
            return [], "every calibration row must be an object"
        scope, name = r.get("scope"), r.get("name")
        if scope not in CALIBRATION_SCOPES:
            return [], f"calibration scope must be one of {CALIBRATION_SCOPES}"
        if not isinstance(name, str) or not name or len(name) > 64:
            return [], "calibration name must be a short string"
        if scope == "generator_class":
            if name not in GENERATOR_CLASSES:
                return [], (f"generator class must be one of {GENERATOR_CLASSES}, "
                            f"refused: {name!r}")
        else:
            if _identifying(name):
                return [], f"identifying token refused: {name!r}"
            fw = _foreign_word(name)
            if fw:
                return [], (f"token outside the commons vocabulary refused: {name!r} "
                            f"(word {fw!r} is not in the lexicon)")
        try:
            s, f = int(r.get("supported")), int(r.get("refuted"))
        except (TypeError, ValueError):
            return [], "supported/refuted must be integers"
        if s < 0 or f < 0 or s + f > 10_000_000:
            return [], "counts out of range"
        if s + f < PRIOR_FLOOR_N:
            continue  # too few verdicts to be a rate about anything
        clean.append({"scope": scope, "name": name, "supported": s, "refuted": f})
    return clean, None


def store(db, instance: str, patterns: list, calibration: list | None = None,
          terms: dict | None = None):
    """One contribution, with the deal it was made under stored beside it.

    `terms` is None for a client that predates the record; grants_of reads that
    as the public commons and nothing more, which is what that operator was
    asked."""
    db.execute("INSERT INTO commons_contributions(instance, received, patterns, "
               "calibration, terms) VALUES(?,?,?,?,?)",
               (instance, time.time(), json.dumps(patterns),
                json.dumps(calibration or []),
                json.dumps(terms) if terms else None))
    db.commit()


def withdraw(db, instance: str) -> int:
    """An install takes its contributions back.

    set_choice's own docstring says consent that cannot be withdrawn is not
    consent, and until now that was true only of FUTURE sends: revoking stopped
    the next contribution and left every earlier one in the bank. A withdrawal
    is registered here and excluded from every artifact built afterwards, so
    the counts stop being published and stop influencing any install that pulls
    the bank.

    The instance id is the credential, as it is for any pseudonymous
    contribution: it is a uuid4 nobody but that install holds, and requiring an
    account would mean knowing who contributed, which is the one thing this
    design refuses to know. Rows are kept rather than deleted so the ledger
    stays append-only and a withdrawal is itself auditable; nothing reads
    them again."""
    db.execute("INSERT OR REPLACE INTO commons_withdrawals(instance, withdrawn) "
               "VALUES(?,?)", (instance, time.time()))
    db.commit()
    r = db.execute("SELECT COUNT(*) AS n FROM commons_contributions WHERE "
                   "instance=?", (instance,)).fetchone()
    return int(r["n"]) if r else 0


def withdrawn(db) -> set:
    """Instances that have taken their contributions back."""
    return {r["instance"] for r in
            db.execute("SELECT instance FROM commons_withdrawals")}


def latest_per_instance(db, grant: str = "public_commons") -> dict:
    """{instance: (received, patterns)} using each instance's newest snapshot,
    so a contributor that reports weekly is counted once, not cumulatively.

    `grant` is the use the artifact being built is for, and it is the single
    place the rights record is enforced. A contribution that did not grant this
    use is not returned, so it cannot reach a dataset, a public endpoint, or
    the pooled view, and a withdrawn instance is not returned at all. Putting
    the check here rather than in each caller is deliberate: a future artifact
    gets the filter by construction rather than by remembering."""
    gone = withdrawn(db)
    out: dict = {}
    for r in db.execute("SELECT instance, received, patterns, terms FROM "
                        "commons_contributions ORDER BY received"):
        if r["instance"] in gone:
            continue
        if grant not in grants_of(r["terms"]):
            continue
        out[r["instance"]] = (r["received"], json.loads(r["patterns"]))
    return out


def latest_calibration_per_instance(db, grant: str = "public_commons") -> dict:
    """{instance: rows} from each instance's newest snapshot. A contribution
    that predates calibration stores NULL, which reads as no rows rather than
    as an error, so an old collector keeps working while clients catch up."""
    gone = withdrawn(db)
    out: dict = {}
    for r in db.execute("SELECT instance, calibration, terms FROM "
                        "commons_contributions ORDER BY received"):
        if r["instance"] in gone or grant not in grants_of(r["terms"]):
            continue
        try:
            out[r["instance"]] = json.loads(r["calibration"]) if r["calibration"] else []
        except (TypeError, ValueError):
            out[r["instance"]] = []
    return out


def accept_pooled(rows) -> tuple[list, str | None]:
    """The bank coming BACK, checked as hard as the bank going out.

    Until now the commons was one-way: an install contributed and received
    nothing, so nothing it ran was ever affected by anyone else's data. Reading
    is the direction that needs the stricter door, because these rows come from
    a server and end up shaping what this machine believes about the people in
    front of it.

    Three refusals, in order of how much they matter:
      * the same identifying and vocabulary checks a contribution passes, so a
        compromised collector cannot push a name in through the back door;
      * POOLED_MIN_SOURCES, so a single install cannot teach the world its own
        idiosyncrasies through a bank that merely echoes it back;
      * the same floor and count sanity as everything else here."""
    if not isinstance(rows, list):
        return [], "pooled patterns must be a list"
    clean = []
    for r in rows:
        if not isinstance(r, dict):
            return [], "every pooled pattern must be an object"
        a, c = r.get("antecedent"), r.get("consequent")
        if not isinstance(a, str) or not isinstance(c, str) or not a or not c:
            return [], "antecedent/consequent must be strings"
        if _identifying(a) or _identifying(c):
            return [], f"identifying token refused: {a if _identifying(a) else c!r}"
        if _foreign_word(a) or _foreign_word(c):
            continue        # outside the shared vocabulary: not ours to learn from
        try:
            s, f = int(r.get("support", 0)), int(r.get("refute", 0))
            n = int(r.get("subjects", 0))
            src = int(r.get("sources", 0))
            frm = int(r.get("frames", 0))
        except (TypeError, ValueError):
            return [], "counts must be integers"
        if s < 0 or f < 0 or s + f > 10_000_000:
            return [], "counts out of range"
        if s < PRIOR_FLOOR_N or src < POOLED_MIN_SOURCES:
            continue        # too thin, or one install talking to itself
        if frm and frm < POOLED_MIN_FRAMES:
            continue        # replicated, but only inside one kind of population
        lo, hi = _rate_bounds(r)
        clean.append({"antecedent": a, "consequent": c, "support": s,
                      "refute": f, "subjects": n, "sources": src,
                      "frames": frm, "rate_min": lo, "rate_max": hi})
    return clean, None


def _rate_bounds(r):
    """The lowest and highest rate this pair reached in any one population.

    Pooling averages, and an average hides the case that matters: a pair
    holding at 0.9 in three populations and 0.2 in a fourth arrives identical
    to one holding at 0.72 everywhere. The spread is the reader's only warning
    that a regularity is not general, so it travels with the row rather than
    being reconstructable from it, which it is not."""
    out = []
    for k in ("rate_min", "rate_max"):
        v = r.get(k)
        try:
            v = float(v)
        except (TypeError, ValueError):
            out.append(None)
            continue
        out.append(v if 0.0 <= v <= 1.0 else None)
    return out[0], out[1]


def ensure_pooled_columns(db):
    """Idempotent, because commons_pooled predates the frame columns and a
    CREATE TABLE IF NOT EXISTS will not add them to a database that already
    has the table."""
    for col, decl in (("frames", "INTEGER NOT NULL DEFAULT 0"),
                      ("rate_min", "REAL"), ("rate_max", "REAL")):
        try:
            db.execute("ALTER TABLE commons_pooled ADD COLUMN %s %s" % (col, decl))
        except Exception:
            pass        # already there
    db.commit()


def store_pooled(db, rows: list):
    """Replace, never accumulate. The bank is a snapshot of what the commons
    currently holds; merging successive snapshots would double-count the same
    populations every time a machine syncs."""
    ensure_pooled_columns(db)
    db.execute("DELETE FROM commons_pooled")
    now = time.time()
    db.executemany(
        "INSERT INTO commons_pooled(antecedent, consequent, support, refute, "
        "subjects, sources, frames, rate_min, rate_max, received) "
        "VALUES(?,?,?,?,?,?,?,?,?,?)",
        [(r["antecedent"], r["consequent"], r["support"], r["refute"],
          r["subjects"], r["sources"], r.get("frames", 0),
          r.get("rate_min"), r.get("rate_max"), now) for r in rows])
    db.commit()


def pooled(db) -> list[dict]:
    try:
        return [dict(r) for r in db.execute(
            "SELECT antecedent, consequent, support, refute, subjects, sources, "
            "frames, rate_min, rate_max FROM commons_pooled")]
    except Exception:
        return []           # a database predating the pooled table has none


def merged_calibration(own_rows: list, contribs: dict) -> list:
    """Own calibration plus every contributor's latest, one population view of
    how well thin-evidence guesses about people actually land."""
    agg: dict = {}
    for rows in [own_rows] + list(contribs.values()):
        for r in rows:
            k = (r["scope"], r["name"])
            e = agg.setdefault(k, {"scope": r["scope"], "name": r["name"],
                                   "supported": 0, "refuted": 0, "sources": 0})
            e["supported"] += int(r.get("supported", 0))
            e["refuted"] += int(r.get("refuted", 0))
            e["sources"] += 1
    out = []
    for e in agg.values():
        total = e["supported"] + e["refuted"]
        if total < PRIOR_FLOOR_N:
            continue
        out.append({**e, "rate": round(e["supported"] / total, 3)})
    out.sort(key=lambda x: (x["scope"], -x["supported"], x["name"]))
    return out


def merged(own_rows: list, contribs: dict) -> list:
    """Own priors + every contributor's latest snapshot, one population view.
    Same shape as hypotheses.bank rows, plus `sources` (how many installs,
    own included, the pattern was seen in)."""
    agg: dict = {}

    def add(a, c, s, r, n):
        e = agg.setdefault((a, c), {"antecedent": a, "consequent": c,
                                    "support": 0, "refute": 0, "subjects": 0,
                                    "sources": 0})
        e["support"] += s
        e["refute"] += r
        e["subjects"] += n
        e["sources"] += 1

    # Belt and braces: the door validates on ingest, but rows stored before
    # the vocabulary existed, and the collector's own bank rows, are re-checked
    # here so nothing outside the lexicon can reach the published dataset.
    for row in own_rows:
        if not (lexicon_ok(row["antecedent"]) and lexicon_ok(row["consequent"])):
            continue
        add(row["antecedent"], row["consequent"],
            row["support"], row["refute"], row["subjects"])
    for _inst, (_ts, pats) in contribs.items():
        seen_here = set()
        for p in pats:
            k = (p["antecedent"], p["consequent"])
            if k in seen_here:
                continue
            if not (lexicon_ok(p["antecedent"]) and lexicon_ok(p["consequent"])):
                continue
            seen_here.add(k)
            add(p["antecedent"], p["consequent"],
                p["support"], p["refute"], p["subjects"])
    out = []
    for e in agg.values():
        total = e["support"] + e["refute"]
        if total == 0 or e["support"] < PRIOR_FLOOR_N:
            continue
        rate = e["support"] / total
        out.append({**e, "rate": round(rate, 3),
                    "pattern": f'holds {e["antecedent"]} -> holds {e["consequent"]}'})
    out.sort(key=lambda x: (-x["subjects"], -x["rate"], x["pattern"]))
    return out


# What a token is ABOUT, for the analytics breakdown. A pattern is filed under
# its consequent: the thing the regularity lets you anticipate.
_CATEGORIES = (
    ("communication", ("prefers_email_contact", "prefers_phone_contact", "prefers_async")),
    ("scheduling", ("prefers_morning_meetings", "prefers_afternoon_meetings",
                    "prefers_short_meetings")),
    ("work style", ("works_remotely", "wants_pdf_invoices")),
    ("commercial", ("prefers_annual_billing", "prefers_monthly_billing",
                    "is_enterprise_customer", "intends_to_upgrade",
                    "considering_cancel", "decided_to_cancel")),
)


def category_of(token: str) -> str:
    for name, members in _CATEGORIES:
        if token in members:
            return name
    if token.startswith("unavailable_"):
        return "scheduling"
    return "other"


# ── the commons as a training corpus ─────────────────────────────────────────
# The same anonymous regularities, shaped for machine consumption: JSONL with
# both the structured counts and a natural-language rendering per line, plus a
# dataset card that explains provenance, consent, and limits, so a lab can use
# it responsibly without a single email back and forth.

DATASET_LICENSE = "CC BY 4.0"


def _sentence(p: dict) -> str:
    a = p["antecedent"].replace("_", " ")
    c = p["consequent"].replace("_", " ")
    total = p["support"] + p["refute"]
    pct = round(p["rate"] * 100)
    src = (f", observed across {p['sources']} independent installations"
           if p.get("sources", 0) > 1 else "")
    return (f"Subjects who hold '{a}' usually also hold '{c}': this held for "
            f"{p['support']} of the {total} with a stance ({pct}%){src}.")


def dataset_jsonl(rows: list) -> str:
    lines = []
    for p in rows:
        lines.append(json.dumps({
            "antecedent": p["antecedent"], "consequent": p["consequent"],
            "support": p["support"], "refute": p["refute"],
            "subjects": p["subjects"], "rate": p["rate"],
            "sources": p.get("sources", 1), "category": category_of(p["consequent"]),
            "text": _sentence(p)}, ensure_ascii=False))
    return "\n".join(lines) + ("\n" if lines else "")


def dataset_card(rows: list, stats: dict) -> str:
    """The dataset card, written to travel with the file. Outward-facing text,
    so it explains consent and limits in plain sentences."""
    return "\n".join([
        "# The OMEM commons dataset",
        "",
        "Regularities in human working behaviour, expressed as counts over",
        "populations. Built to give AI systems a better understanding of what",
        "people are like in general, without holding a single fact about any",
        "person.",
        "",
        "## How it was collected",
        "",
        "Each line was learned by an OMEM installation from its own memory and",
        "contributed by that installation's operator, who answered an explicit",
        "opt-in question. Contributions carry a random pseudonym and are",
        "re-validated on arrival: any token that could embed a name, an",
        "identifier, or an extracted value is refused at the door, and every",
        "token must be built solely from a fixed behaviour-domain vocabulary,",
        "so even a token engineered to look like a plain word cannot smuggle",
        "an identity in.",
        "",
        "## What a line can never contain",
        "",
        "No names, no organisations, no message text, no prices or terms, no",
        "identifiers of any kind. A line is two behaviour tokens and the counts",
        "of subjects who held both, held one and opposed the other, or were",
        "silent. Every word in both tokens has to appear in a fixed vocabulary",
        f"of {len(COMMONS_LEXICON)} behaviour words, so a word that is not in it,",
        "a name or a company among them, cannot appear at all. No line is",
        f"published on fewer than {PRIOR_FLOOR_N} supporting subjects.",
        "",
        "That is what the file contains, stated so a reader can check it. It is",
        "deliberately not followed by the sentence that this therefore is not",
        "personal data under any particular law. That is a conclusion for the",
        "reader and their own counsel to reach, and this project does not make",
        "claims it cannot hand you a way to test.",
        "",
        "## Schema",
        "",
        "One JSON object per line: antecedent, consequent, support, refute,",
        "subjects, rate, sources (independent installations), category, and",
        "text (a natural-language rendering of the same numbers).",
        "",
        "## Scale",
        "",
        f"{len(rows)} patterns, {stats.get('stances', 0)} stances, "
        f"{stats.get('contributors', 0) + 1} contributing installations.",
        "",
        "## Consent and rights",
        "",
        "Every line in this file comes from a contribution whose operator",
        "granted publication in the public commons, recorded at the moment",
        "they contributed rather than assumed afterwards. A contribution that",
        "granted no such use, and one whose install has since withdrawn, is",
        "not in this file and was never in an earlier one. No other use is",
        "granted by the act of contributing: a commercial dataset, if one is",
        "ever offered, requires its own question, asked before it applies and",
        "never applied backwards.",
        "",
        f"Terms in force at export: {TERMS_VERSION}.",
        "",
        "## License and intended use",
        "",
        f"{DATASET_LICENSE}, attribution to \"the OMEM commons\". Intended for",
        "training and evaluating AI systems on human behavioural priors.",
        "Rates are population tendencies, never rules about individuals; a",
        "model trained on them should treat every pattern as a prior a real",
        "person can and will contradict.",
        "",
        f"Exported from OMEM on {time.strftime('%Y-%m-%d')}.",
        ""])


def analytics(rows: list, contribs: dict, db) -> dict:
    """What the creator wants to know at a glance: how much human regularity
    the commons holds, where it comes from, and what kind it is."""
    weeks: dict = {}
    gone = withdrawn(db)
    for r in db.execute("SELECT instance, received FROM commons_contributions "
                        "ORDER BY received"):
        if r["instance"] in gone:
            continue  # withdrawn: it is not in the rows, so it is not in the count
        wk = time.strftime("%Y-%m-%d", time.gmtime(r["received"] - (r["received"] % 604800)))
        weeks[wk] = weeks.get(wk, 0) + 1
    cats: dict = {}
    for row in rows:
        cats[category_of(row["consequent"])] = cats.get(category_of(row["consequent"]), 0) + 1
    return {
        "contributors": len(contribs),
        "patterns": len(rows),
        "stances": sum(r["support"] + r["refute"] for r in rows),
        "strong": sum(1 for r in rows if r["rate"] >= 0.8),
        "categories": dict(sorted(cats.items(), key=lambda kv: -kv[1])),
        "timeline": [{"week": w, "contributions": n} for w, n in sorted(weeks.items())],
    }
