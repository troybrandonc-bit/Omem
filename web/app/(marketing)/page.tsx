import { readFileSync } from "fs";
import { join } from "path";
import { MarketingShell } from "@/components/marketing/chrome";
import { Section, CodeBlock, ButtonLink, SpecList, HeroHeading } from "@/components/marketing/ui";
import { BeliefInspector } from "@/components/marketing/belief-inspector";
import { CircleDashed } from "lucide-react";

/* The reasoning replay is INLINED into the DOM rather than referenced as an
 * image. Chrome freezes animation clocks inside SVG-as-<img> (we shipped an
 * empty black terminal to the README before noticing), and an inline SVG's
 * SMIL runs everywhere a browser does. Read at build time from the same file
 * the README uses, so the two can never tell different stories. */
const REASONING_SVG = readFileSync(
  join(process.cwd(), "public", "demo-reasoning.svg"), "utf8");

export const metadata = {
  title: "Prove why your AI agent acted, and approve before it does",
  description:
    "OMEM keeps AI agents answerable: an audit trail of what the agent believed and when, and a human approval gate before a risky action runs. Built on a belief-revision engine that keeps contradictions and proves provenance. Self-hosted, MIT, no dependencies.",
};

/* The landing page.
 *
 * CONTENT THESIS (updated at 0.3.6): lead with ACCOUNTABILITY, not memory.
 * Belief-revision, contradiction-keeping and provenance are now shipped by the
 * funded incumbents (Mem0, Zep) and a near-clone, so "best memory engine" is a
 * losing race. What is still differentiated AND monetisable is the answer to
 * "why did the agent do that, and who approved it", sold to teams shipping
 * agents to clients (see /accountability). The hero leads there; the engine
 * sections below are the HOW that makes the answer trustworthy, not the pitch.
 * The refusals, take-back and intuition layer still carry the depth a builder
 * evaluates on.
 *
 * LAYOUT rules carried over from the redesign, still in force:
 * - No label above anything, no numbered furniture, nothing beside the
 *   headline. Sections open with a hairline and a heading.
 * - Figures are real: the belief inspector is the live demo project, the
 *   terminal replay is verbatim output of a CI-asserted test. Nothing here is
 *   a claim the product cannot back, and both figures say where they came
 *   from in their captions.
 */

const REFUSALS = [
  {
    k: "It will not decide what is true",
    d: `Two claims conflict only when a caller has declared the pair opposed.
        OMEM never reads two sentences and concludes they disagree, because that
        judgement is what would stop the same question having the same answer a
        year from now.`,
  },
  {
    k: "It will not let a hunch pass as a belief",
    d: `The intuition layer guesses eagerly and is never allowed to lie about
        it. expects() and believes() are different verbs: a hypothesis carries
        its case file, its strength stays below any evidenced confidence, and
        the engine's UNKNOWN stays UNKNOWN however good the hunch.`,
  },
  {
    k: "It will not run what nobody authorised",
    d: `A model may propose a repair. Only action types registered in code can
        execute, the risk class comes from OMEM's registry rather than from the
        plan that claims it, and a high-risk action needs a named approver on top
        of the permission.`,
  },
  {
    k: "It will not quietly overwrite",
    d: `A contradiction keeps both claims, records which is currently believed,
        and can reconstruct either side at any past point in time. Nothing is
        lost when something changes.`,
  },
];

const FEATURES = [
  ["Belief state over time",
   "Every claim carries an interval. Ask what was believed last Tuesday and get last Tuesday's answer, not today's."],
  ["Provenance you can follow",
   "Ask why something is believed and get the chain of assertions and evidence that led there."],
  ["What changed while you were gone",
   "changes(since) returns the delta an agent wants at session start: what appeared, what closed and how, which conflicts opened, who merged."],
  ["A judgment queue, not a guessing engine",
   "When two records look like one person, or a declared rule is violated, the question waits for a human. Approvals are recorded under the approver's name, and a dismissed question is never asked twice."],
  ["Private by default",
   "Memory belongs to an agent unless you share it with a team or the project."],
  ["Everyday habits are memory",
   "“Mornings work best for me” attaches to the person who wrote it, grounded in their own sentence, extracted offline with no LLM. The priors tier then learns what people are like in general, as counts that name nobody."],
  ["The right to be forgotten, executed",
   "One request rewrites the record for real: the person's data, the cascade behind it, and their sentences quoted under surviving beliefs. Replay-verified before anything is touched; what remains is a hash, counts, and a date."],
  ["A bank that teaches AI what people are like",
   "The priors OMEM learns collect in an intelligence bank on your own machine, anonymous counts about how people behave, exportable as a training set. The rule that fills it has been tested against 19,668 real respondents rather than a world we invented. Our objective is to give AI a real understanding of our nature while holding no fact about anyone."],
  ["The dashboard is included",
   "One pip install serves the API and the UI on the same port. No Node at runtime, no second process."],
];

const NOT_YET = [
  "No SSO or SCIM",
  "No SOC 2, ISO 27001 or HIPAA BAA",
  "No key rotation tooling",
  "No region pinning",
  "An audit chain that detects tampering, not one that prevents it",
  "One writer per database, so no high availability",
  "The intuition layer is reachable from the SDK and the HTTP API, not yet from the MCP tools",
  "The commons can be downloaded whole, but not yet queried a question at a time",
];

function SectionHead({ n, title, children }: {
  n: string; title: React.ReactNode; children?: React.ReactNode;
}) {
  return (
    <div className="max-w-3xl">
      <span aria-hidden="true" className="block h-px w-full bg-[color:var(--border)]" />
      <h2 id={`s-${n}`} className="display mt-9 text-2xl">{title}</h2>
      {children && <p className="lede mt-6">{children}</p>}
    </div>
  );
}

// Structured data for rich results and AI answer extraction. Only claims the
// page itself makes; no invented ratings or reviews.
const JSONLD = {
  "@context": "https://schema.org",
  "@graph": [
    {
      "@type": "Organization",
      name: "OMEM",
      url: "https://infrastructure.omem-cloud.com",
      logo: "https://infrastructure.omem-cloud.com/omem-mark.png",
      sameAs: ["https://github.com/troybrandonc-bit/Omem", "https://x.com/Omem_ai"],
    },
    {
      "@type": "SoftwareApplication",
      name: "OMEM",
      applicationCategory: "DeveloperApplication",
      operatingSystem: "Windows, macOS, Linux",
      description:
        "The open-source system of record for what an AI agent believed and did: keeps both sides of a contradiction, tracks belief over time, answers why with a provenance chain, and gates risky actions behind a human approval step. Self-hosted, MIT.",
      offers: { "@type": "Offer", price: "0", priceCurrency: "USD" },
      license: "https://opensource.org/licenses/MIT",
      url: "https://infrastructure.omem-cloud.com",
      downloadUrl: "https://pypi.org/project/omem-infrastructure/",
    },
  ],
};

export default function Home() {
  return (
    <MarketingShell>
      <script type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(JSONLD) }} />
      {/* ── hero ────────────────────────────────────────────────────────── */}
      <Section className="hero-y">
        <div className="max-w-[68rem]">
          <HeroHeading>
            Prove <em>why</em> your agent did that, and approve before it acts.
          </HeroHeading>
          <div className="mt-10 grid gap-x-16 gap-y-8 lg:grid-cols-[minmax(0,7fr)_minmax(0,5fr)]">
            <p className="lede !max-w-none">
              When an agent acts for someone and they ask why, most memory
              can&rsquo;t say. It overwrote the evidence the moment the facts
              changed. OMEM keeps both sides of every contradiction, tracks what
              was believed and when, and puts a human approval step before a
              risky action runs. An agent&rsquo;s decisions stay answerable: you
              can show why it believed something, and stop what nobody signed
              off on.
            </p>
            <div className="lg:pt-1">
              <div className="flex flex-wrap items-center gap-3">
                <ButtonLink href="/docs/quickstart">Start the quickstart</ButtonLink>
                <ButtonLink href="https://github.com/troybrandonc-bit/Omem" variant="secondary" external>
                  Read the source
                </ButtonLink>
              </div>
              <p className="mt-4">
                <ButtonLink href="/accountability" variant="quiet">
                  Shipping agents to clients? Book a design-partner pilot &rarr;
                </ButtonLink>
              </p>
              <p className="mt-5 text-caption text-faint">
                Runs on your own machine, with no external services.
                <span className="mono mt-1 block">MIT · Python 3.9+ · no dependencies</span>
              </p>
            </div>
          </div>
        </div>
      </Section>

      {/* ── the demo, as a figure ───────────────────────────────────────── */}
      <Section className="pb-24 sm:pb-32">
        <figure className="m-0 max-w-[62rem]">
          <div className="lift-lg rounded-lg">
            <BeliefInspector />
          </div>
          <figcaption className="mt-5 flex flex-wrap items-baseline gap-x-3 text-caption text-faint">
            <span aria-hidden="true" className="h-px w-8 shrink-0 bg-[color:var(--line-strong)]" />
            A real assertion from the demo project. Change &ldquo;as of&rdquo; and watch
            the belief state move.
          </figcaption>
        </figure>
      </Section>

      {/* ── 01 the refusals ───────────────────────────────────────────── */}
      <Section className="section-y">
        <SectionHead n="01" title="The useful part of a memory layer is the part that says no.">
          Anything can store a fact. What decides whether your agent is
          trustworthy is what it declines to do with one.
        </SectionHead>
        <div className="mt-10">
          <SpecList items={REFUSALS.map(r => ({ k: r.k, d: r.d }))} />
        </div>
      </Section>

      {/* ── 02 the take-back ──────────────────────────────────────────────
          The reasoning story, told by its own output. The figure is the same
          asserted replay the README carries: every line is verbatim from
          scripts/demo_reasoning.py, which runs in CI, so this screen cannot
          quietly drift from the product. */}
      <Section className="section-y">
        <SectionHead n="02" title="It concludes things. And it can take them back.">
          Declare a rule, and OMEM composes what it knows into conclusions that
          carry their premises. The reason to want that is what happens on the
          way down: retract one fact and every conclusion resting on it is
          withdrawn in the same request, cascade included, with the whole chain
          answerable to <span className="mono">why()</span>.
        </SectionHead>
        <figure className="m-0 mt-10 max-w-[45rem]">
          <div
            className="lift-lg overflow-hidden rounded-lg [&_svg]:block [&_svg]:h-auto [&_svg]:w-full"
            dangerouslySetInnerHTML={{ __html: REASONING_SVG }}
          />
          <figcaption className="mt-5 flex flex-wrap items-baseline gap-x-3 text-caption text-faint">
            <span aria-hidden="true" className="h-px w-8 shrink-0 bg-[color:var(--line-strong)]" />
            Verbatim output of scripts/demo_reasoning.py. Every line is an
            asserted test that runs in CI.
          </figcaption>
        </figure>
      </Section>

      {/* ── 03 the intuition layer ────────────────────────────────────── */}
      <Section className="section-y">
        <div className="grid gap-10 lg:grid-cols-2 lg:gap-14">
          <div>
            <SectionHead n="03" title="It learns from one example, then doubts itself harder than you would.">
              Humans learn fast by leaping to conclusions, and confabulate for
              the same reason. OMEM keeps the speed and drops the confabulation:
              one similar case is enough to form an expectation, and every
              expectation is born suspect, wearing a case file.
            </SectionHead>
            <p className="mt-5 max-w-read text-body text-muted">
              A skeptic pass works each case against everything OMEM holds. Only
              evidence about the target itself can support or refute; rival
              hypotheses compete and reality picks the winner. A case that will
              not resolve asks a question, the answer is recorded as evidence
              under the answerer&apos;s name, and a calibration record keeps the
              boldness of new leaps honest about the record of old ones.
            </p>
            <p className="mt-5 max-w-read text-body text-muted">
              And it generalizes. From what it has seen across many people OMEM
              learns priors, regularities of the form &ldquo;people who hold P
              tend to hold Q&rdquo; &mdash; but only where holding P actually
              moves the odds. A pattern that holds because Q is common
              everywhere is discarded, and the test is applied to the lower
              bound of the rate rather than the rate itself, so a regularity
              resting on a handful of people must be far cleaner than one
              resting on hundreds. Against 19,668 real respondents that rule
              recovers known structure at 4.8 times chance; the rule it replaced
              recovered it at chance exactly.
            </p>
            <p className="mt-5 max-w-read text-body text-muted">
              A prior fires only into a silence and yields the instant
              that person&apos;s own evidence disagrees, so a general pattern
              never overrides an individual. Each prior stores counts, never a
              person, so the learned model of people carries no fact about
              anyone.
            </p>
            <ButtonLink href="/docs" variant="quiet" className="mt-5">
              How the intuition layer works
            </ButtonLink>
          </div>
          <CodeBlock filename="hunches with case files" label="The intuition layer"
            single={`mem.leap()      # one similar case is enough

mem.expects(about="customer:gamma")
# wants_pdf_invoices   strength 0.35
#   because: beta holds it; gamma resembles beta
#   supports: 1   undermines: 0
#   gaps: no direct evidence about gamma yet

mem.interrogate()    # the skeptic works every open case
# verdicts come from reality, never from the model

mem.believes(about="customer:gamma",
             claim="wants_pdf_invoices")
# "UNKNOWN"  - a hunch is never a belief

mem.priors()         # what it learned about people in general
# holds P -> holds Q
#   in_population: 41 of 52     Q on its own: 0.29
#   kept because the lower bound of that rate clears
#   0.29, not because Q happens to be common
#   when_applied: 3-0
#   fires only into a silence, yields to the person`}
          />
        </div>
      </Section>

      {/* ── the objective ──────────────────────────────────────────────────
          The identity, stated plainly. The priors above are not just a feature;
          they are in service of this. */}
      <Section className="section-y" id="objective">
        <SectionHead n="objective" title="Why we are building this: AI that understands people, and holds a fact about no one.">
          OMEM is memory for agents, but the reason it exists runs deeper. From
          what it sees across many people it learns priors, regularities of the
          form &ldquo;people who do X tend to do Y&rdquo;, kept as counts that
          name nobody. Installs that choose to can pool those counts into a
          shared, anonymous bank, and that bank is offered to teach AI our nature
          without ever holding a person. That is the objective: connect humans
          and AI by giving AI a real understanding of who we are, learned from
          patterns people chose to share, held by no one.
        </SectionHead>
        <p className="mt-5 max-w-read text-body text-muted">
          Today a model reasons about people by recalling studies. A study hands
          it a finding stripped of the person in front of it, and says nothing
          about when the finding should not be applied &mdash; which is where
          confabulation comes from. Every entry OMEM holds has the opposite
          shape: it is already an application, carrying the evidence it rests on
          and, uniquely, the record of when it refused. The counts are worth
          little without the discipline that decides when to use them, so the
          intention is that both travel together.
        </p>
        <div className="mt-5 flex flex-wrap items-center gap-3">
          <ButtonLink href="/objectives" variant="quiet">
            Read the objective
          </ButtonLink>
          <ButtonLink href="https://machinetestimony.org/papers/wp1/" variant="quiet" external>
            The rule, audited against 19,668 people &rarr;
          </ButtonLink>
        </div>
      </Section>

      {/* ── 04 the refusal, shown ─────────────────────────────────────── */}
      <Section className="section-y">
        <div className="grid gap-10 lg:grid-cols-2 lg:gap-14">
          <div>
            <SectionHead n="04" title={<>A model proposed <span className="mono">exec_shell</span>. OMEM did not run it.</>}>
              OMEM records what breaks and repairs it under policy. The model is a
              reasoning component that may{" "}
              <em className="not-italic font-medium text-fg">propose</em> a plan;
              OMEM decides what is permitted, what executes, and whether it
              actually worked.
            </SectionHead>
            <p className="mt-5 max-w-read text-body text-muted">
              Error text and model output are data here. Neither can name an
              action into existence, and the refusal is written down with the
              reason for every action rather than disappearing.
            </p>
            <ButtonLink href="/docs" variant="quiet" className="mt-5">
              How the healing loop works
            </ButtonLink>
          </div>
          <CodeBlock filename="a denied plan" label="A repair plan that OMEM refused"
            single={`result = mem.healing.handle(
    error={"component": "billing-sync", "error_type": "AuthError"},
    plan={"diagnosis": "credentials rotated upstream",
          "actions": [{"type": "reload_config"},
                      {"type": "exec_shell"}]},
)

result["status"]
# "denied"  - nothing executed

result["decisions"]
# reload_config  permitted      (low risk)
# exec_shell     unknown action type (not registered)`}
          />
        </div>
      </Section>

      {/* ── 05 what a vector store cannot do ──────────────────────────── */}
      <Section className="section-y">
        <SectionHead n="05" title="Two agents disagree. Both are kept, one is believed, and you can ask why." />
        <div className="mt-10 grid gap-10 lg:grid-cols-[minmax(0,1fr)_minmax(0,320px)] lg:gap-14">
          <CodeBlock label="Recording a contradiction"
            tabs={[
              {
                label: "Python",
                code: `from omem import Memory

mem = Memory(api_key="omem_sk_...", project="proj_...")

mem.remember(agent="support", about="customer:alice",
             claim="prefers_annual_billing")

# Nothing infers that these two disagree. You say so, once.
mem.contradict("prefers_annual_billing", "prefers_monthly_billing")

mem.remember(agent="sales", about="customer:alice",
             claim="prefers_monthly_billing")

mem.believes(about="customer:alice", claim="prefers_annual_billing")
# "CONTRADICTED"  - not deleted, not overwritten

mem.why(assertion_id)   # the chain that led there`,
              },
              {
                label: "TypeScript",
                code: `// Not on npm yet: used from sdk/typescript/ in the repo.
import { Memory } from "./sdk/typescript/src/index";

const mem = new Memory({ apiKey: "omem_sk_...", project: "proj_..." });

await mem.remember({ agent: "support", about: "customer:alice",
                     claim: "prefers_annual_billing" });

await mem.contradict("prefers_annual_billing", "prefers_monthly_billing");

await mem.believes({ about: "customer:alice",
                     claim: "prefers_annual_billing" });
// "CONTRADICTED"`,
              },
              {
                label: "MCP",
                code: `// claude_desktop_config.json
{
  "mcpServers": {
    "omem": {
      "command": "omem-mcp",
      "env": {
        "OMEM_API_KEY": "omem_sk_...",
        "OMEM_BASE_URL": "http://127.0.0.1:8787",
        "OMEM_PROJECT": "proj_...",
        "OMEM_AGENT": "claude"
      }
    }
  }
}`,
              },
            ]}
          />
          <ul className="flex flex-col gap-6">
            {FEATURES.map(([k, d]) => (
              <li key={k}>
                <h3 className="text-note font-semibold">{k}</h3>
                <p className="mt-1.5 text-note text-muted">{d}</p>
              </li>
            ))}
          </ul>
        </div>
      </Section>

      {/* ── 06 the proofs ─────────────────────────────────────────────────
          Nothing in this section is a feature. Each item is a sentence the
          project says about itself that has been made executable, with the
          file that would go red named on the page. The ledger guards the
          rest, and tests_claims_ledger.py guards the ledger. */}
      <Section className="section-y">
        <SectionHead n="06" title="Marketing that cannot fail is indistinguishable from marketing that is false.">
          So the load-bearing sentences here are executable. Each one names
          the test that goes red the moment it stops being true, and those
          tests run on every commit.
        </SectionHead>
        <ul className="mt-10 grid gap-x-14 gap-y-9 sm:grid-cols-2">
          {([
            ["The Witness benchmark",
             "Memory benchmarks measure recall. Witness measures testimony: no asserting what nobody said, retraction honoured, disagreement kept visible, two people with one name kept apart, conclusions dying with their premises. OMEM's card is asserted in CI. Adapters for Mem0 and Graphiti are included and run with your keys, because this repo publishes no numbers it did not run.",
             "benchmarks/witness/README.md"],
            ["It phones home to nobody",
             "A guard installed under the socket layer, then a full working session: identity, contradiction, a rule cascade, recall, hunches. One outbound connection or DNS lookup that is not loopback fails the build with the address in hand.",
             "server/tests_airgap.py"],
            ["Upgrades never rewrite your past",
             "An ops log frozen on 2026-08-29 replays on every commit and must produce a byte-identical state digest. The suite also tampers with one op and requires the digest to move, so the check is proven able to fail.",
             "server/tests_upgrade_stability.py"],
            ["Tested against people we did not invent",
             "The mining rule was run over 19,668 Big Five respondents, whose correlation structure nobody here chose and where the neutral answer is a genuine silence a prior can fire into. It recovered the dataset's known five-factor structure at chance exactly, which is how the defect was found; the repaired rule recovers it at 4.8 times chance, on 94% fewer priors that cover more claims. The harness downloads the data at run time and this repository redistributes nobody's survey answers.",
             "benchmarks/external/README.md"],
            ["The claims ledger",
             "Sixteen load-bearing sentences mapped to the test behind each. The ledger is itself guarded: a row whose file goes missing fails CI. A claim with no row is opinion.",
             "CLAIMS.md"],
          ] as const).map(([k, d, path]) => (
            <li key={k}>
              <h3 className="text-note font-semibold">{k}</h3>
              <p className="mt-1.5 text-note text-muted">{d}</p>
              <a className="mono mt-2 inline-block text-caption text-faint underline decoration-[color:var(--line-strong)] underline-offset-4 hover:text-[color:var(--fg)]"
                 href={`https://github.com/troybrandonc-bit/Omem/blob/main/${path}`}
                 target="_blank" rel="noreferrer">
                {path}
              </a>
            </li>
          ))}
        </ul>
      </Section>

      {/* ── 07 the honesty section ────────────────────────────────────── */}
      <Section className="section-y">
        <div className="grid gap-10 lg:grid-cols-2 lg:gap-14">
          <div>
            <SectionHead n="07" title="This is early software, and the second list matters as much as the first.">
              OMEM is free while it is in beta, and it is missing things you would
              need before putting it somewhere serious. They are written down
              rather than discovered during a security review.
            </SectionHead>
            <ButtonLink href="/security" variant="quiet" className="mt-5">
              Read the full security page
            </ButtonLink>
          </div>
          <ul className="border-t">
            {NOT_YET.map(n => (
              <li key={n} className="flex items-start gap-3 border-b py-4">
                <CircleDashed className="mt-0.5 h-4 w-4 shrink-0 text-faint" aria-hidden="true" />
                <span className="text-note text-muted">{n}</span>
              </li>
            ))}
          </ul>
        </div>
      </Section>

      {/* ── close ─────────────────────────────────────────────────────── */}
      <Section className="rule section-y">
        <h2 className="display max-w-[22ch] text-2xl">
          The whole thing runs on your laptop in about a minute.
        </h2>
        <p className="lede mt-5">
          No signup, no card, no quota, and no service to depend on. If it breaks
          or feels wrong, that is exactly the feedback worth having right now.
        </p>
        <div className="mt-8 max-w-md">
          <CodeBlock filename="start here" label="Install and run OMEM"
            single={`pip install omem-infrastructure\nomem-server`} />
        </div>
        <div className="mt-6 flex flex-wrap items-center gap-3">
          <ButtonLink href="/docs/quickstart">Start the quickstart</ButtonLink>
          <ButtonLink href="/docs" variant="secondary">Documentation</ButtonLink>
          <ButtonLink href="https://github.com/troybrandonc-bit/Omem/issues" variant="quiet" external>
            Report something broken
          </ButtonLink>
        </div>
      </Section>
    </MarketingShell>
  );
}
