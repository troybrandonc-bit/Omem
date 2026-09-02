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
  calibration TEXT);
CREATE INDEX IF NOT EXISTS commons_inst ON commons_contributions(instance, received);
CREATE TABLE IF NOT EXISTS commons_meta(k TEXT PRIMARY KEY, v TEXT NOT NULL);
"""


def ensure_schema(db):
    """The schema, plus the one column a collector predating calibration will
    not have. A collector is a long-lived install, so the table is older than
    this feature on every machine that already runs one."""
    db.executescript(COMMONS_SCHEMA)
    try:
        db.execute("ALTER TABLE commons_contributions ADD COLUMN calibration TEXT")
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
    """Record the decision. Either answer is durable; both are revocable from
    Settings, because consent that cannot be withdrawn is not consent."""
    db.execute("INSERT OR REPLACE INTO commons_meta(k,v) VALUES('contribute',?)",
               ("yes" if contribute else "no",))
    db.commit()


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


def store(db, instance: str, patterns: list, calibration: list | None = None):
    db.execute("INSERT INTO commons_contributions(instance, received, patterns, "
               "calibration) VALUES(?,?,?,?)",
               (instance, time.time(), json.dumps(patterns),
                json.dumps(calibration or [])))
    db.commit()


def latest_per_instance(db) -> dict:
    """{instance: (received, patterns)} using each instance's newest snapshot,
    so a contributor that reports weekly is counted once, not cumulatively."""
    out: dict = {}
    for r in db.execute("SELECT instance, received, patterns FROM commons_contributions "
                        "ORDER BY received"):
        out[r["instance"]] = (r["received"], json.loads(r["patterns"]))
    return out


def latest_calibration_per_instance(db) -> dict:
    """{instance: rows} from each instance's newest snapshot. A contribution
    that predates calibration stores NULL, which reads as no rows rather than
    as an error, so an old collector keeps working while clients catch up."""
    out: dict = {}
    for r in db.execute("SELECT instance, calibration FROM commons_contributions "
                        "ORDER BY received"):
        try:
            out[r["instance"]] = json.loads(r["calibration"]) if r["calibration"] else []
        except (TypeError, ValueError):
            out[r["instance"]] = []
    return out


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
        "silent. Truly anonymous counts of this kind are not personal data.",
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
    for r in db.execute("SELECT received FROM commons_contributions ORDER BY received"):
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
