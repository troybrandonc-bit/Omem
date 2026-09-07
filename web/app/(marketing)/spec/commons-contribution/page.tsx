import { MarketingShell } from "@/components/marketing/chrome";
import { Section, CodeBlock } from "@/components/marketing/ui";

export const metadata = {
  title: "Contributing to the commons",
  description:
    "The format for contributing counts to the OMEM commons, written so that any system can contribute rather than only OMEM. A one file tool that builds a contribution from a CSV, what a contribution contains, what it deliberately cannot contain, the closed vocabulary, the terms, and a worked example in forty lines.",
};

/* WHY THIS IS A SPECIFICATION AND NOT A PAGE OF PRODUCT DOCUMENTATION.
 *
 * The commons had zero contributors, and the reason was structural rather than
 * anything to do with persuasion. Contributing ran through OMEM, so the bank
 * could only grow if OMEM was adopted, which put a public good on the one lever
 * that needs somebody else to say yes first.
 *
 * A contribution is a uuid, co-occurrence counts over a published closed
 * vocabulary, calibration figures, a consent record and a coarse frame. Almost
 * none of that is OMEM-shaped. Anyone who can map their own facts onto the
 * lexicon can contribute, and until this document existed there was no way for
 * them to know that.
 *
 * So it is written for somebody running something else entirely, and OMEM
 * appears at the bottom as one implementation they can ignore.
 *
 * No em dashes. */

const REPO = "https://github.com/troybrandonc-bit/Omem/blob/main/";

const TOOL = `$ cat observations.csv
subject,token
c1,prefers_email
c1,not:responds_phone
c2,prefers_email
...

$ python3 commons_contribute.py observations.csv \\
    --domain customer_support --region europe --send

640 observations, 88 people, 14 behaviours.
23 patterns cleared the bar.

The strongest, so you can see what you are about to send:
  prefers_email    -> not:responds_phone    41 of 47 people, 88 held the first
  ...

Terms, version 2026-09-03: Counts join the public commons and are
published there under CC BY 4.0 ...

accepted: {"stored": 23}

To withdraw everything sent under this id:
DELETE https://commons.omem-cloud.com/v1/commons/b1e5c8f2-...`;

const SHAPE = `{
  "instance": "b1e5c8f2-6a4d-4a7e-9c31-8f0d2e7a5c14",

  "patterns": [
    {"antecedent": "prefers_email", "consequent": "responds_slowly",
     "support": 41, "refute": 6, "subjects": 88,
     "consequent_base": 0.31}
  ],

  "calibration": [
    {"scope": "generator_class", "name": "association",
     "supported": 128, "refuted": 24}
  ],

  "terms": {"version": "2026-09-03", "granted": ["public_commons"]},

  "frame": {"domain": "customer_support", "region": "europe",
            "subjects": "200-999"}
}`;

const COUNTS = `-- what you need from your own store, whatever it is
--
-- One row per (antecedent, consequent) pair you can express in the
-- vocabulary. Nothing below identifies a subject: the ids are used to
-- count and then thrown away.

SELECT
  a.token                       AS antecedent,
  b.token                       AS consequent,
  COUNT(DISTINCT CASE WHEN b.holds THEN a.subject_id END)      AS support,
  COUNT(DISTINCT CASE WHEN NOT b.holds THEN a.subject_id END)  AS refute,
  COUNT(DISTINCT a.subject_id)                                 AS subjects,
  -- consequent_base: how often b held across EVERYONE, not just the people
  -- who held a. This is the comparison the pattern has to beat, so it is
  -- measured over the whole population and never over the matched group.
  (SELECT CAST(COUNT(DISTINCT CASE WHEN c.holds THEN c.subject_id END) AS REAL)
        / NULLIF(COUNT(DISTINCT c.subject_id), 0)
     FROM facts c WHERE c.token = b.token)                     AS consequent_base
FROM facts a
JOIN facts b USING (subject_id)
WHERE a.holds AND a.token <> b.token
GROUP BY a.token, b.token
HAVING COUNT(DISTINCT a.subject_id) >= 20;`;

const SEND = `import json, urllib.request, uuid

payload = {
    "instance": str(uuid.uuid4()),          # minted once, stored, reused
    "patterns": rows,                       # the query above
    "calibration": [],                      # optional, see below
    "terms": {"version": "2026-09-03", "granted": ["public_commons"]},
    "frame": {"domain": "customer_support", # or omit the frame entirely
              "region": "europe", "subjects": "200-999"},
}

req = urllib.request.Request(
    "https://commons.omem-cloud.com/v1/commons",
    data=json.dumps(payload).encode(),
    headers={"Content-Type": "application/json"},
)
print(urllib.request.urlopen(req, timeout=30).read().decode())

# No account, no key, no signup. A contribution is anonymous by
# construction, so there is nothing to authenticate.`;

type Row = [string, string];

const FIELDS: Row[] = [
  ["instance", "A uuid4 you mint once and reuse. It carries nothing about you or your machine, and exists only so a later withdrawal can find the counts it should remove."],
  ["patterns", "The counts. One entry per pair of behaviour tokens, both drawn from the closed vocabulary and refused at both ends if not."],
  ["calibration", "Optional. How often a guess of a given kind turned out to be supported or refuted, so the bank can say what a guess is worth rather than only what is common."],
  ["terms", "Which uses you granted, and when. A grant absent from the record is a grant that was never given."],
  ["frame", "Optional. The coarse shape of the population these counts came from."],
];

const PATTERN: Row[] = [
  ["antecedent", "A behaviour token from the vocabulary. The thing held."],
  ["consequent", "A behaviour token from the vocabulary. The thing that may follow."],
  ["support", "How many subjects held both."],
  ["refute", "How many held the first and opposed the second. Counting this is not optional: without it, a bank records what is common rather than what is associated."],
  ["subjects", "How many held the first at all, which is what makes the other two a rate rather than a tally."],
  ["consequent_base", "How often the consequent held across your WHOLE population, as a rate between 0 and 1 and never a count. Required. It is the number the lift test is measured against, and it is the only field here that nobody but you can compute."],
];

export default function CommonsContribution() {
  return (
    <MarketingShell>
      <Section className="page-y">
        <article className="prose-omem max-w-3xl">
          <div className="tech-label mb-3">Commons</div>
          <h1 className="display text-3xl">Contributing counts</h1>

          <p className="lede">
            You do not need OMEM. A contribution is a handful of counts over a
            published vocabulary, and anything that stores facts about people
            can produce one.
          </p>

          <p>
            The commons is a bank of regularities about people in general:
            what somebody who does one thing tends, and tends not, to do next.
            It exists so that a system meeting a person for the first time has
            something better than nothing, and so that the something is
            checkable rather than a model&rsquo;s recollection of the internet.
          </p>

          <h2>What is honestly in it today</h2>
          <p>
            Very little. The bank is new and this document exists because until
            now the only way to contribute was to run one particular piece of
            software, which put a public good behind a private adoption
            problem. You should know what you would be joining before you join
            it, so: the published bank, its size, and what it is worth are
            all on the <a href="/commons">commons page</a>, and if the answer
            there is thin, it is thin.
          </p>
          <p>
            The reason to contribute early is not that the bank is useful yet.
            It is that a bank assembled from one kind of installation is worth
            less than one assembled from many, and the population frame below
            is the mechanism that makes the difference measurable rather than
            asserted.
          </p>

          <h2>What a contribution cannot contain</h2>
          <p>
            No names, no identifiers, no text, no free-form fields at all. Both
            ends of every pattern must be a word from a closed list of 392, and
            a token outside it is refused at the door rather than stored and
            filtered later. There is no field a sentence could travel in.
          </p>
          <p>
            The population size is a band and never a count, because an exact
            population size is one of the three facts that together would
            identify an operator. The region is a macro-region and never a
            country. The domain is one of nine coarse categories and is
            declared by you rather than inferred from your data.
          </p>
          <p>
            This is a design constraint rather than a promise. A payload
            carrying a field that is not in the map below is refused, and the
            test suite fails on any key in neither map, which is what turns
            &ldquo;we should think about that&rdquo; into something a build can
            check.
          </p>

          <h2>The shape</h2>

          <CodeBlock single={SHAPE} filename="contribution.json"
            label="Everything a contribution may contain" />

          <table>
            <thead><tr><th>Field</th><th></th></tr></thead>
            <tbody>
              {FIELDS.map(([f, d]) => (
                <tr key={f}>
                  <td className="mono">{f}</td>
                  <td className="text-note text-muted">{d}</td>
                </tr>
              ))}
            </tbody>
          </table>

          <h3 className="sub">Inside a pattern</h3>
          <table>
            <thead><tr><th>Field</th><th></th></tr></thead>
            <tbody>
              {PATTERN.map(([f, d]) => (
                <tr key={f}>
                  <td className="mono">{f}</td>
                  <td className="text-note text-muted">{d}</td>
                </tr>
              ))}
            </tbody>
          </table>

          <p className="tnote">
            A pattern whose <span className="mono">subjects</span> count is very
            small is discarded rather than trusted. Twenty is a reasonable floor
            to apply on your own side before sending, and the bank applies its
            own regardless.
          </p>

          <h2>The vocabulary</h2>
          <p>
            392 behaviour words, closed, published in{" "}
            <span className="mono">server/commons.py</span> as{" "}
            <span className="mono">COMMONS_LEXICON</span>. A token may be a
            single word from it, or a word prefixed with{" "}
            <span className="mono">not:</span> to record the negative, which is
            how a bank learns that people who do one thing reliably do not do
            another.
          </p>
          <p>
            Mapping your own facts onto it is the only real work in this
            document, and it is worth doing conservatively. A token you are not
            sure about is better dropped than guessed: a wrong mapping does not
            fail, it quietly pollutes a shared resource.
          </p>

          <h2>The frame, and why it is worth declaring</h2>
          <p>
            Three fields, all optional, all closed lists. Domain is one of{" "}
            <span className="mono">customer_support, sales, recruiting,
            healthcare, education, software, operations, personal, other</span>.
            Region is one of{" "}
            <span className="mono">africa, americas, asia, europe, oceania
            </span>. Subjects is one of{" "}
            <span className="mono">10-49, 50-199, 200-999, 1000+</span>.
          </p>
          <p>
            The frame exists so the bank can require agreement across{" "}
            <i>different</i> populations rather than across installations that
            happen to be alike. Ten contributors in one sector agreeing with
            each other is not evidence about people; it is evidence about that
            sector. Declaring a frame is what lets a regularity be marked as
            holding broadly rather than locally, and a contribution without one
            still counts but cannot help establish that distinction.
          </p>

          <h2>Terms</h2>
          <p>
            The current version is <span className="mono">2026-09-03</span> and
            grants <span className="mono">public_commons</span>: counts join the
            public commons and are published there under CC BY 4.0, together
            with the coarse population shape. They are not licensed for any
            commercial dataset. That would need a separate question, asked
            before it applies and never applied backwards.
          </p>
          <p>
            The version is recorded with your counts because which uses you
            agreed to is a fact about the moment you agreed, and it cannot be
            reconstructed afterwards from anything else. When what leaves your
            machine changes, the version changes and you are asked again.
          </p>

          <h2>Withdrawal</h2>
          <p>
            Send your instance id to withdraw. Your counts leave the live bank
            and every release published afterwards, and the withdrawal itself is
            recorded with its date so the removal is auditable. Releases already
            downloaded are not un-published, because nobody can un-publish a
            downloaded file, and a promise that says otherwise is a lie told to
            make a form easier to sign.
          </p>

          <h2>The short way</h2>
          <p>
            There is a tool that does everything below.{" "}
            <a href={`${REPO}scripts/commons_contribute.py`}>
              <span className="mono">commons_contribute.py</span></a> is one
            file, standard library only, MIT, and needs nothing from OMEM. You
            give it a two column CSV of subject and behaviour, it derives the
            counts, refuses anything that could name somebody, and writes or
            sends the payload.
          </p>

          <CodeBlock single={TOOL} filename="terminal"
            label="A contribution in one command" />

          <p>
            It refuses where the mistake is rather than after the file is
            written. A word outside the vocabulary is named as a word, not as a
            token, because the word is the thing you have to change. A subject
            recorded as both doing and not doing something is refused rather
            than counted twice.
          </p>

          <h3 className="sub">The one number the bank has to take on trust</h3>
          <p>
            The collector rejects identifying tokens, foreign words and
            malformed counts, and it applies all three of the tests an OMEM
            installation applies before it sends: at least three subjects
            holding both, a rate of 60 per cent or better against the
            refutations, and a lower confidence bound that clears the
            consequent&rsquo;s own base rate by ten points. A pattern that
            fails any of them is dropped whether you applied the tests or not,
            so a hand built payload does not get an easier ride than an
            installation.
          </p>
          <p>
            The third test is why{" "}
            <span className="mono">consequent_base</span> is required. A
            pattern earns its place by beating what your population already
            says about the consequent on its own, and the collector never sees
            your population, so it cannot derive that number and will not
            assume one. If almost everyone in your data renews then every
            antecedent appears to predict renewal, and a bank filled with that
            records what is popular rather than what follows from anything.
          </p>
          <p>
            What the collector still cannot do is confirm the number you send.
            It re-runs the test against your figure and refuses what fails; a
            figure that is simply wrong will pass. That is a real limit and the
            dataset card states it, next to the counts, which any reader can
            check for themselves. It is worth asking for anyway, because a
            contributor who states a base rate can be contradicted by anyone
            who knows the population, and a contributor who states nothing
            cannot be contradicted at all.
          </p>

          <h2>Producing the counts by hand</h2>
          <p>
            The shape below is the general case. Substitute your own store; the
            only requirements are that you can group by subject and that you can
            express the behaviour in the vocabulary. It gives you support,
            refutations, subjects and the consequent&rsquo;s base rate, which is
            everything the collector needs to apply all three tests itself.
          </p>

          <CodeBlock single={COUNTS} filename="counts.sql"
            label="Deriving patterns from an ordinary store" />

          <p>
            Note the <span className="mono">refute</span> column. Counting only
            co-occurrence produces a bank that records what is common, which is
            not the same as what is associated, and a system built on the first
            will confidently tell you that most people do the most popular
            thing. That defect was measured and published: recovery of a known
            structure at 0.185 against a chance rate of 0.184, before the rule
            was changed.
          </p>

          <h2>Sending it</h2>

          <CodeBlock single={SEND} filename="contribute.py"
            label="One POST, no account" />

          <p>
            A malformed payload is refused with a reason rather than partially
            accepted. Contributions are rate limited by address, and there is no
            key to obtain because a contribution is anonymous by construction
            and there is nothing to authenticate.
          </p>

          <h2>If you already emit a Testimony Record</h2>
          <p>
            Then you are done, and the tool will read it directly:
          </p>

          <CodeBlock single={`python3 commons_contribute.py \\
    --from-record record.jsonl \\
    --domain customer_support --region europe

40 beliefs dropped: the proposition is not in the commons vocabulary.
  smoke              e.g. 'prefers_smoke_signals'
  Nothing was translated or guessed.

120 observations, 40 people, 5 behaviours.
4 patterns cleared the bar.`} filename="terminal"
            label="A record is already a contribution" />

          <p>
            A belief carries a subject and a proposition and says whether the
            system held it or denied it, which is exactly what a count needs.
            Three rules, and the middle one is the one that matters:{" "}
            <span className="mono">believed_true</span> is the token,{" "}
            <span className="mono">believed_false</span> is{" "}
            <span className="mono">not:</span> the token, and a belief marked{" "}
            <span className="mono">contradicted</span> or{" "}
            <span className="mono">unknown</span> is <i>skipped</i>. A system
            holding two irreconcilable positions has no stated position, and a
            bank that resolved that quietly would be inventing an opinion the
            record deliberately declined to have.
          </p>
          <p>
            A proposition outside the vocabulary is dropped and counted, never
            translated. Guessing a mapping is how a shared resource gets
            polluted by somebody acting in good faith.
          </p>
          <p>
            The two are separate things and neither requires the other. A record
            is about one system&rsquo;s account of itself. A contribution is
            about a population, names nobody, and is one direction only.
          </p>

          <p className="text-note text-muted">
            OMEM is one implementation of this and contributes through the same
            endpoint with the same payload. Its client is readable if you want a
            second example. You do not need it, and nothing on this page assumes
            it.
          </p>
        </article>
      </Section>
    </MarketingShell>
  );
}
