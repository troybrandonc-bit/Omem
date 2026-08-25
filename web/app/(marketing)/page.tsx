import { MarketingShell } from "@/components/marketing/chrome";
import { Section, CodeBlock, ButtonLink, SpecList, HeroHeading } from "@/components/marketing/ui";
import { BeliefInspector } from "@/components/marketing/belief-inspector";

export const metadata = {
  title: "Memory for AI agents that refuses to decide what is true",
  description:
    "OMEM tracks what each agent believes, when it learned it, and why. Contradictions are surfaced rather than overwritten, and no repair runs that nobody authorised. Self-hosted, MIT, no dependencies.",
};

/* The landing page.
 *
 * CONTENT THESIS (unchanged, and still the right one): do not lead with memory.
 * Every framework ships a vector store, recall quality cannot be demonstrated in
 * a paragraph, and competing there is a race with no finish line. Lead with what
 * OMEM refuses to do, because that is the part a competitor cannot copy without
 * rebuilding their engine.
 *
 * LAYOUT: the brief was sleek, precise, modern, and the previous version was
 * none of those because of three habits, all of which are gone:
 *
 * - NO LABEL ABOVE ANYTHING. Every block opened with uppercase micro-type
 *   naming what you were about to read. That is chrome introducing content, and
 *   it was usually a restatement of the heading directly under it.
 *
 * - NO NUMBERED SECTIONS. `01 —— WHAT IT REFUSES TO DO` reads as a slide deck.
 *   A hairline does the same structural job without the furniture.
 *
 * - NOTHING BESIDE THE HEADLINE. Text-left/card-right is the most templated
 *   arrangement there is. The statement owns the first screen; the demo follows
 *   as a full-width figure, which is also the only way it is big enough to read.
 *
 * The measure is wider than a document's throughout — this is a landing page,
 * not an article, and 34em of lede under a 68px headline looked like a column
 * that had lost its other column.
 *
 * Nothing here is a claim the product cannot back. The belief inspector is the
 * real demo project the API serves. The refusal transcript is the real shape of
 * a denied plan. The last list is what OMEM does NOT do.
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
  ["Private by default",
   "Memory belongs to an agent unless you share it with a team or the project."],
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
];

/**
 * A section head.
 *
 * This used to be `01 —— WHAT IT REFUSES TO DO` above the heading: a monospace
 * ordinal, a rule, and an uppercase label, all before a single word of content.
 * Three pieces of chrome introducing one sentence. Numbered sections read as a
 * deck of generated slides, and the label was almost always a compressed
 * restatement of the heading directly beneath it — the reader parsed the idea
 * twice, in a harder setting first.
 *
 * What replaces it is a hairline the width of the column and the heading. The
 * rule still tells you a new argument started, which is the one job the number
 * was actually doing, and nothing is announced before it is said.
 *
 * `n` is kept in the signature and used as the anchor id, so the sections are
 * still individually linkable without the ordinal being visible furniture.
 */
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

export default function Home() {
  return (
    <MarketingShell>
      {/* ── hero ──────────────────────────────────────────────────────────
          Text left / card right is the single most templated arrangement on the
          web, and the uppercase micro-label above the headline is the second.
          Together they are the house style of a generated landing page, which is
          most of why this screen did not look designed.

          So: no label, and nothing beside the headline. The statement gets the
          first screen to itself at the full measure, and the demo follows below
          as a figure with its own caption — which is also the only way it gets
          enough width to actually be read rather than skimmed as a thumbnail. */}
      <Section className="hero-y">
        <div className="max-w-[68rem]">
          <HeroHeading>
            Your agent should be able to say <em>why</em> it believes something.
          </HeroHeading>
          {/* The lede is offset to a second column on wide screens rather than
              sitting directly under the headline. A left edge shared by every
              element down the page is what makes a layout read as a stack of
              blocks; breaking that alignment once, deliberately, is what makes
              it read as composed. */}
          <div className="mt-10 grid gap-x-16 gap-y-8 lg:grid-cols-[minmax(0,7fr)_minmax(0,5fr)]">
            <p className="lede !max-w-none">
              Most agent memory is a list of facts. When two of them conflict, one
              silently overwrites the other and the history is gone. OMEM keeps
              both, tracks which one is believed right now, and can reconstruct
              what was believed at any point in the past.
            </p>
            <div className="lg:pt-1">
              <div className="flex flex-wrap items-center gap-3">
                <ButtonLink href="/docs/quickstart">Start the quickstart</ButtonLink>
                <ButtonLink href="https://github.com/troybrandonc-bit/Omem" variant="secondary" external>
                  Read the source
                </ButtonLink>
              </div>
              <p className="mt-5 text-caption text-faint">
                Runs on your own machine, with no external services.
                <span className="mono mt-1 block">MIT · Python 3.9+ · no dependencies</span>
              </p>
            </div>
          </div>
        </div>
      </Section>

      {/* ── the demo, as a figure ─────────────────────────────────────────
          The real demo project, not a mockup: move the clock and the belief
          state actually changes. It is the subject of the opening screen, so it
          takes the one `lift-lg` on the site. */}
      <Section className="pb-24 sm:pb-32">
        {/* Capped at 62rem, not full measure.
            Stretched to the whole 1200px shell the two inner columns went
            mostly empty — Contradictions is four short lines and it was being
            given 600px to say them in. A demo that wide stops reading as an
            object you are being shown and starts reading as a table that failed
            to fill. Left-aligned rather than centred so it shares the headline's
            edge; the asymmetry is the composition. */}
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

      {/* ── 02 the refusal, shown ─────────────────────────────────────── */}
      <Section className="section-y">
        <div className="grid gap-10 lg:grid-cols-2 lg:gap-14">
          <div>
            <SectionHead n="02" title={<>A model proposed <span className="mono">exec_shell</span>. OMEM did not run it.</>}>
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

      {/* ── 03 what a vector store cannot do ──────────────────────────── */}
      <Section className="section-y">
        <SectionHead n="03" title="Two agents disagree. Both are kept, one is believed, and you can ask why." />
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

      {/* ── 04 the honesty section ────────────────────────────────────── */}
      <Section className="section-y">
        <div className="grid gap-10 lg:grid-cols-2 lg:gap-14">
          <div>
            <SectionHead n="04" title="This is early software, and the second list matters as much as the first.">
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
                <span className="led closed mt-[7px] shrink-0" aria-hidden="true" />
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
