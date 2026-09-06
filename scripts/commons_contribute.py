#!/usr/bin/env python3
"""Contribute to the OMEM commons without running OMEM.

The commons is a bank of anonymous behavioural regularities: counts of the
form "people who do P tend to do Q", pooled across installations that chose to
send them, holding no fact about any person. Until now the only way to put
something in it was to run OMEM, let it mine your data, and switch
contribution on. That is a large ask of somebody who has the data and no
interest in the product, and it made the commons a by-product of adoption
rather than a thing anyone could join.

This is the other door. One file, no dependencies, no install. You give it
observations -- a subject and what is known about them -- and it derives the
counts, refuses anything that could name somebody, and writes the exact
payload the collector accepts.

WHAT IT WILL NOT DO, which is most of what it is for:

  * It will not let a token outside the closed commons vocabulary through, and
    when it refuses one it names the word that is not in the lexicon rather
    than the token, because the word is the thing you have to change.
  * It will not mine a pattern that an OMEM install would not have sent. The
    floor on support, the minimum rate, and the lift test are the same three
    the miner applies, for the same reason: without the lift test a bank fills
    with popular consequents wearing an antecedent as a hat.
  * It will not mint a new identity every run. A contributor who sends ten
    times under ten fresh ids looks to the collector like ten installations
    agreeing, and agreement across installations is the only independence
    signal the commons has. So the id lives in a file, and if that file cannot
    be written this refuses to contribute at all.
  * It will not infer your frame from your data. The domain and the region are
    declared by you or they are absent, exactly as in OMEM.

TWO HONEST DIFFERENCES FROM WHAT AN OMEM INSTALL SENDS, both narrowing:

  * OMEM merges synonymous propositions into clusters before counting. This
    does not, because clustering needs the extraction pipeline that is the
    product. If you record both `prefers_email` and `likes_email` your counts
    split between them and both may fall under the floor. Pick one word per
    behaviour.
  * OMEM knows which claims a project declared contradictory. This knows only
    the `not:` marker, so opposition has to be written as `not:x`.

Neither can inflate a count. Both can lose one, which is the right direction
for a tool that strangers run over data nobody here has seen.

USE

    python3 commons_contribute.py observations.csv \\
        --domain customer_support --region europe

    python3 commons_contribute.py observations.csv \\
        --domain customer_support --region europe \\
        --send https://commons.omem-cloud.com

    python3 commons_contribute.py --words email     # search the vocabulary

The CSV is two columns, one observation per line, no header needed:

    subject,token
    c1,prefers_email
    c1,not:responds_phone
    c2,prefers_email

The subject column never leaves this machine. It is used to count people and
then discarded; nothing derived from it appears in the payload.

Copyright 2026 Michael Brandon Clifford. MIT licensed.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
import uuid


class Refused(Exception):
    """A contribution that would have been wrong, refused where it was made.

    The collector refuses the same things, but it refuses them after the file
    is written and the run is over, and it reports one error for the whole
    payload. Refusing here can say which observation and which word."""


# ── the bar a pattern has to clear, copied from server/hypotheses.py ─────────
# Not imported: this file is meant to be downloaded on its own by somebody who
# does not have the repository. tests_commons_contribute.py pins every value
# below against the server, so the copy cannot drift in silence.
PRIOR_FLOOR_N = 3
PRIOR_MIN_RATE = 0.6
PRIOR_MIN_LIFT = 0.10
PRIOR_LIFT_Z = 1.96
MAX_PATTERNS = 500
MAX_TOKEN_LEN = 64

TERMS_VERSION = "2026-09-03"
TERMS_SUMMARY = (
    "Counts join the public commons and are published there under CC BY 4.0, "
    "together with the coarse shape of the population they came from: a "
    "working domain, a macro-region and a size band, all declared by you and "
    "none of them a fact about a person. They are not licensed for any "
    "commercial dataset; that would need a separate question, asked before it "
    "applies and never backdated.")

FRAME_DOMAINS = ("customer_support", "sales", "recruiting", "healthcare",
                 "education", "software", "operations", "personal", "other")
FRAME_REGIONS = ("africa", "americas", "asia", "europe", "oceania")

DEFAULT_COMMONS_URL = "https://commons.omem-cloud.com"

# The closed vocabulary. A commons token is built only from these words, joined
# by underscores. The structural checks below stop colons, digits and the rel_
# prefix; what they cannot stop is a token engineered to look like a plain
# lowercase word, and "johnsmith_of_acmecorp" carries an identity while passing
# every format check. The list is behaviour-domain by construction: no given
# names, no surnames, no company names, and no affiliation connectors, so no
# composition of allowed words can name a person or an employer.
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


def _identifying(token: str) -> bool:
    """A token that could name someone or something.

    A single leading `not:` is the negation marker and is stripped first. What
    follows is checked exactly as a positive token would be, so `not:pays_late`
    passes and `not:person:sam` does not, because the second colon survives."""
    if token.startswith("not:"):
        token = token[4:]
    if token.startswith("rel_") or ":" in token or bool(re.search(r"\d", token)):
        return True
    return re.fullmatch(r"[a-z_]+", token) is None


def foreign_word(token: str) -> str | None:
    """The first word of a token that is outside the lexicon, or None."""
    if token.startswith("not:"):
        token = token[4:]
    for w in token.split("_"):
        if w and w not in COMMONS_LEXICON:
            return w
    return None


def check_token(token: str, where: str = "") -> str:
    """A token, or a refusal that says what to change. Returns it unchanged."""
    at = (" at " + where) if where else ""
    if not isinstance(token, str) or not token:
        raise Refused("empty token" + at)
    if len(token) > MAX_TOKEN_LEN:
        raise Refused("token longer than %d characters%s: %r"
                      % (MAX_TOKEN_LEN, at, token[:80]))
    if _identifying(token):
        raise Refused(
            "token could name somebody or carry a value%s: %r. A commons token "
            "is lowercase letters and underscores, optionally after one "
            "`not:`. Digits, colons, capitals, @ and the rel_ prefix are all "
            "refused, because the whole point of the bank is that it holds no "
            "fact about a person." % (at, token))
    fw = foreign_word(token)
    if fw:
        raise Refused(
            "the word %r is not in the commons vocabulary%s (in %r). The "
            "vocabulary is closed on purpose: it is the only defence against "
            "a token that looks like a plain word and is really a name. Run "
            "with --words %s to see what is near it, and if the behaviour "
            "genuinely has no word, the lexicon is extended by a pull request "
            "rather than by a contributor." % (fw, at, token, fw))
    return token


def wilson_lower(k: int, n: int, z: float = PRIOR_LIFT_Z) -> float:
    """The lower end of a Wilson interval on k successes in n trials.

    A raw rate treats three of three as certainty and three hundred of three
    hundred as the same certainty. This does not, which is why the floor on
    support can stay at three without the bank filling with coincidences."""
    if n <= 0:
        return 0.0
    p = k / n
    d = 1 + z * z / n
    centre = p + z * z / (2 * n)
    margin = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5)
    return (centre - margin) / d


def band_of(subjects: int) -> str | None:
    """The band a population size falls in, or None below the smallest.

    Under ten people there is no band rather than a band called `small`: a
    frame that narrow describes the contributor more than the population."""
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


def instance_id(path: str) -> str:
    """A stable opaque id for this contributor, created once and reused.

    This is the one piece of state the tool keeps, and keeping it is not a
    convenience. The collector requires a pooled pattern to have been seen by
    more than one source before it may influence anything, and a contributor
    who sends under a fresh id every run satisfies that requirement alone. So a
    file that cannot be written is a refusal rather than a fallback to a
    throwaway id: contributing wrongly is worse than not contributing."""
    try:
        if os.path.exists(path):
            got = open(path, encoding="utf-8").read().strip()
            if 8 <= len(got) <= 64 and got.replace("-", "").isalnum():
                return got
        made = str(uuid.uuid4())
        with open(path, "w", encoding="utf-8") as f:
            f.write(made + "\n")
        return made
    except OSError as e:
        raise Refused(
            "could not keep a stable contributor id at %s (%s). Without one, "
            "every run of this tool looks to the commons like a different "
            "installation, and agreement across installations is the only "
            "independence signal the bank has. Point --identity somewhere "
            "writable rather than contributing under a new id each time."
            % (path, e))


class Contribution:
    """Observations in, counts out.

    A subject is any stable label for one person: a customer id, a row number,
    a hash. It is used to count people and is then discarded. Nothing derived
    from it reaches the payload, so it does not need to be anonymised first,
    though there is no reason to make it a name either."""

    def __init__(self, domain: str = "", region: str = "",
                 identity: str = ".commons-instance"):
        self.domain = (domain or "").strip().lower()
        self.region = (region or "").strip().lower()
        if self.domain and self.domain not in FRAME_DOMAINS:
            raise Refused("domain outside the closed list: %r. One of: %s"
                          % (self.domain, ", ".join(FRAME_DOMAINS)))
        if self.region and self.region not in FRAME_REGIONS:
            raise Refused("region outside the closed list: %r. One of: %s. A "
                          "macro-region, never a country: a country plus a "
                          "domain plus a size can identify one company."
                          % (self.region, ", ".join(FRAME_REGIONS)))
        self.identity_path = identity
        self.held: dict[str, set] = {}       # token -> subjects holding it
        self.subjects: set = set()
        self.dropped_words: dict = {}        # foreign word -> one example

    # ── in ──────────────────────────────────────────────────────────────────
    def observe(self, subject, *tokens, where: str = "") -> None:
        """Record that one person holds these behaviours.

        `not:x` says they oppose x, which is what a refutation is made of.
        Silence is not opposition: a subject with no stated position on x is
        neither support nor refute, and is precisely the gap a prior fills."""
        s = str(subject)
        if not s:
            raise Refused("a subject needs a label%s"
                          % ((" at " + where) if where else ""))
        for t in tokens:
            t = check_token(str(t).strip(), where)
            opp = t[4:] if t.startswith("not:") else "not:" + t
            if s in self.held.get(opp, ()):
                raise Refused(
                    "subject holds both %r and %r%s. One person cannot both do "
                    "a thing and not do it, and counting them twice corrupts "
                    "the support and the refutation of every pattern the "
                    "token appears in." % (t, opp, (" at " + where) if where
                                           else ""))
            self.held.setdefault(t, set()).add(s)
            self.subjects.add(s)

    def read_record(self, path: str) -> tuple:
        """Read observations out of a Testimony Record. Returns (kept, dropped).

        A record already holds what this needs: a belief entry names a subject
        and a proposition, and says whether the system held it or denied it. So
        anything emitting Testimony Records can contribute without also keeping
        a separate CSV, which is the point: the format and the bank stop being
        two unrelated pieces of work.

        Three rules, and the second is the one that matters:

          `believed_true` is the token, `believed_false` is `not:` the token.
          A belief with polarity `deny` flips it the same way.

          `contradicted` and `unknown` are SKIPPED. A system that holds two
          irreconcilable positions on a proposition, or none, has no stated
          position, and a bank that resolved that silently would be inventing
          an opinion the record deliberately declined to have. This is the
          same reason the miner does not count absence.

          A proposition outside the commons vocabulary is dropped and counted,
          not translated. Guessing a mapping is how a shared resource gets
          quietly polluted by somebody acting in good faith.
        """
        kept = dropped = 0
        seen_bad: dict = {}
        with open(path, encoding="utf-8") as f:
            for i, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    e = json.loads(line)
                except ValueError:
                    raise Refused("line %d of %s is not JSON. A Testimony "
                                  "Record is one JSON object per line."
                                  % (i, path))
                if not isinstance(e, dict) or e.get("type") != "belief":
                    continue
                state = e.get("state")
                if state not in ("believed_true", "believed_false"):
                    continue          # no stated position; see the docstring
                prop = str(e.get("proposition", "")).strip()
                subject = str(e.get("subject", "")).strip()
                if not prop or not subject:
                    continue
                negative = (state == "believed_false") ^ (e.get("polarity") == "deny")
                token = ("not:" + prop) if negative else prop
                fw = foreign_word(token)
                if fw or _identifying(token):
                    dropped += 1
                    seen_bad.setdefault(fw or "not a plain token", prop)
                    continue
                self.observe(subject, token, where="line %d" % i)
                kept += 1
        self.dropped_words = seen_bad
        return kept, dropped

    def read_csv(self, path: str) -> int:
        """subject,token per line. Returns the number of observations read."""
        n = 0
        with open(path, newline="", encoding="utf-8") as f:
            for i, row in enumerate(csv.reader(f), 1):
                row = [c.strip() for c in row if c.strip()]
                if not row or row[0].startswith("#"):
                    continue
                if len(row) < 2:
                    raise Refused("line %d of %s has one column; it needs "
                                  "subject,token" % (i, path))
                if i == 1 and row[1].lower() == "token":
                    continue                       # a header, not an entry
                self.observe(row[0], *row[1:], where="line %d" % i)
                n += len(row) - 1
        return n

    # ── out ─────────────────────────────────────────────────────────────────
    def patterns(self) -> list[dict]:
        """The regularities that clear the same bar an OMEM install applies.

        For every ordered pair, support counts the people who hold both,
        refute counts the people who hold the first and oppose the second, and
        subjects counts everyone who holds the first at all. Absence is never
        counted against a pattern.

        Three tests, and the third is the one that makes this a regularity
        rather than a popularity contest. Without the lift test the rule asks
        only whether most P-holders hold Q, which any common Q passes on its
        own, and the bank fills with things most people do rather than things
        that follow from anything."""
        bare = sorted({t[4:] if t.startswith("not:") else t for t in self.held})
        base = {}
        for q in bare:
            yes = len(self.held.get(q, ()))
            no = len(self.held.get("not:" + q, ()))
            base[q] = (yes / (yes + no)) if (yes + no) else None

        space = []
        for q in bare:
            space.append((q, self.held.get(q, set()),
                          self.held.get("not:" + q, set()), base[q]))
            b = base[q]
            space.append(("not:" + q, self.held.get("not:" + q, set()),
                          self.held.get(q, set()),
                          None if b is None else 1.0 - b))

        out = []
        for p, holders, _, _ in space:
            if len(holders) < PRIOR_FLOOR_N:
                continue
            bp = p[4:] if p.startswith("not:") else p
            for q, q_yes, q_no, base_q in space:
                bq = q[4:] if q.startswith("not:") else q
                if bq == bp:
                    continue          # a claim never predicts itself or its own
                support = len(holders & q_yes)
                if support < PRIOR_FLOOR_N:
                    continue
                refute = len(holders & q_no)
                total = support + refute
                if total == 0 or support / total < PRIOR_MIN_RATE:
                    continue
                if base_q is not None and \
                        wilson_lower(support, total) < base_q + PRIOR_MIN_LIFT:
                    continue
                out.append({"antecedent": p, "consequent": q,
                            "support": support, "refute": refute,
                            "subjects": len(holders)})
        # Strongest first, then capped. The collector takes at most MAX_PATTERNS
        # and a truncation in arrival order would silently drop the best ones.
        out.sort(key=lambda r: (-r["support"], r["antecedent"], r["consequent"]))
        return out[:MAX_PATTERNS]

    def frame(self) -> dict | None:
        """The coarse shape of this population, or None if it was not declared.

        An undeclared frame is not an error. The counts still contribute; they
        simply cannot help satisfy the bank's requirement that a pattern hold
        in more than one KIND of population, which is the honest consequence of
        declining to say where they came from."""
        b = band_of(len(self.subjects))
        if self.domain not in FRAME_DOMAINS or self.region not in FRAME_REGIONS \
                or b is None:
            return None
        return {"domain": self.domain, "region": self.region, "subjects": b}

    def payload(self) -> dict:
        """Exactly what the collector accepts, and nothing else.

        `calibration` is empty and stays empty. It records how much a guess
        about a person turned out to be worth, which is a track record of
        predictions this tool has never made. An empty list is the true
        answer; a fabricated one would be the worst thing in the payload."""
        pats = self.patterns()
        if not pats:
            raise Refused(
                "nothing here clears the bar: no pair had %d people holding "
                "both, at a rate of %.0f%% or better, beating the consequent's "
                "own base rate by %.0f points. That is the tool working. A "
                "commons of weak patterns is worse than a small one, and %d "
                "subjects over %d behaviours is usually simply not enough yet."
                % (PRIOR_FLOOR_N, PRIOR_MIN_RATE * 100, PRIOR_MIN_LIFT * 100,
                   len(self.subjects), len(self.held)))
        body = {
            "instance": instance_id(self.identity_path),
            "patterns": pats,
            "calibration": [],
            "terms": {"version": TERMS_VERSION,
                      "granted": ["public_commons"],
                      "recorded": time.time()},
        }
        fr = self.frame()
        if fr:
            body["frame"] = fr
        return body

    def send(self, url: str) -> tuple[bool, str]:
        """POST it. Returns (accepted, what the collector said)."""
        data = json.dumps(self.payload()).encode()
        req = urllib.request.Request(
            url.rstrip("/") + "/v1/commons", data=data,
            headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=15) as r:
                return True, r.read().decode("utf-8", "replace")[:400]
        except urllib.error.HTTPError as e:
            return False, "%d %s" % (e.code,
                                     e.read().decode("utf-8", "replace")[:400])
        except OSError as e:
            return False, str(e)


# ── the command line ────────────────────────────────────────────────────────
def _words(term: str) -> int:
    hits = sorted(w for w in COMMONS_LEXICON if term in w) if term \
        else sorted(COMMONS_LEXICON)
    if not hits:
        print("no word in the commons vocabulary contains %r." % term)
        print("A behaviour with no word is a pull request against "
              "COMMONS_LEXICON, not something a contributor can add locally: "
              "the vocabulary is closed because it is what stops a token from "
              "carrying a name.")
        return 1
    print("%d of %d words%s:\n" % (len(hits), len(COMMONS_LEXICON),
                                   (" containing %r" % term) if term else ""))
    for i in range(0, len(hits), 6):
        print("  " + "  ".join(w.ljust(15) for w in hits[i:i + 6]).rstrip())
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Build a contribution to the OMEM commons from your own "
                    "data, without running OMEM.",
        epilog="The CSV is subject,token per line. The subject column never "
               "leaves this machine.")
    ap.add_argument("observations", nargs="?",
                    help="CSV of subject,token observations")
    ap.add_argument("--from-record", metavar="FILE", default="",
                    help="read the observations out of a Testimony Record "
                         "instead of a CSV")
    ap.add_argument("--domain", default="", help="one of: " +
                    ", ".join(FRAME_DOMAINS))
    ap.add_argument("--region", default="", help="one of: " +
                    ", ".join(FRAME_REGIONS))
    ap.add_argument("--identity", default=".commons-instance",
                    help="where the stable contributor id is kept")
    ap.add_argument("--out", default="", help="write the payload here")
    ap.add_argument("--send", metavar="URL", nargs="?", const=DEFAULT_COMMONS_URL,
                    help="POST it to a collector (default: %s)"
                         % DEFAULT_COMMONS_URL)
    ap.add_argument("--words", nargs="?", const="", metavar="TERM",
                    help="print the commons vocabulary, or search it")
    a = ap.parse_args(argv)

    if a.words is not None:
        return _words(a.words.strip().lower())
    if not a.observations and not a.from_record:
        ap.print_help()
        return 2

    try:
        c = Contribution(a.domain, a.region, a.identity)
        if a.from_record:
            n, dropped = c.read_record(a.from_record)
            if dropped:
                print("%d belief%s dropped: the proposition is not in the "
                      "commons vocabulary." % (dropped, "" if dropped == 1 else "s"))
                for word, example in sorted(c.dropped_words.items())[:6]:
                    print("  %-18s e.g. %r" % (word, example[:40]))
                print("  Nothing was translated or guessed. Run --words to see "
                      "what is near a word, and if a behaviour genuinely has "
                      "none, the lexicon is extended by a pull request.")
        else:
            n = c.read_csv(a.observations)
        body = c.payload()
    except Refused as e:
        print("refused: %s" % e, file=sys.stderr)
        return 1

    pats = body["patterns"]
    print("%d observations, %d people, %d behaviours."
          % (n, len(c.subjects), len(c.held)))
    print("%d patterns cleared the bar." % len(pats))
    if not body.get("frame"):
        print("No frame: %s. The counts still contribute, but they cannot help "
              "the bank require that a pattern hold in more than one kind of "
              "population."
              % ("declare --domain and --region" if len(c.subjects) >= 10
                 else "under ten people there is no size band, because a frame "
                      "that narrow describes you rather than a population"))
    print("\nThe strongest, so you can see what you are about to send:")
    for r in pats[:8]:
        total = r["support"] + r["refute"]
        print("  %-28s -> %-28s %d of %d people, %d held the first"
              % (r["antecedent"][:28], r["consequent"][:28],
                 r["support"], total, r["subjects"]))

    if a.out:
        with open(a.out, "w", encoding="utf-8") as f:
            json.dump(body, f, indent=2, sort_keys=True)
        print("\nwritten to %s" % a.out)

    if a.send:
        print("\nTerms, version %s: %s" % (TERMS_VERSION, TERMS_SUMMARY))
        print("\nSending to %s as %s" % (a.send, body["instance"]))
        ok, said = c.send(a.send)
        print(("accepted: " if ok else "refused: ") + said)
        if ok:
            print("\nTo withdraw everything sent under this id: "
                  "DELETE %s/v1/commons/%s"
                  % (a.send.rstrip("/"), body["instance"]))
        return 0 if ok else 1
    if not a.out:
        print("\nNothing was sent. Add --out FILE to write the payload, or "
              "--send to contribute it.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
