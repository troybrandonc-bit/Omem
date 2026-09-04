import { MarketingShell } from "@/components/marketing/chrome";
import { Section, CodeBlock } from "@/components/marketing/ui";

export const metadata = {
  title: "Contributing to the commons",
  description:
    "The format for contributing counts to the OMEM commons, written so that any system can contribute rather than only OMEM. What a contribution contains, what it deliberately cannot contain, the closed vocabulary, the terms, and a worked example in forty lines.",
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

const SHAPE = `{
  "instance": "b1e5c8f2-6a4d-4a7e-9c31-8f0d2e7a5c14",

  "patterns": [
    {"antecedent": "prefers_email", "consequent": "responds_slowly",
     "support": 41, "refute": 6, "subjects": 88}
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
  COUNT(DISTINCT a.subject_id)                                 AS subjects
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

          <h2>Producing the counts</h2>
          <p>
            The shape below is the general case. Substitute your own store; the
            only requirements are that you can group by subject and that you can
            express the behaviour in the vocabulary.
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
            Then you have most of this already. A belief carries a subject and a
            proposition, and a pattern is a count over pairs of propositions
            across subjects. The mapping worth doing carefully is your
            propositions onto the vocabulary, and the same advice applies:
            conservative, and drop what you are unsure of.
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
