import { MarketingShell } from "@/components/marketing/chrome";
import { Section, Eyebrow, HeroHeading, ButtonLink, SpecList } from "@/components/marketing/ui";

export const metadata = {
  title: "Accountability for the AI agents you ship",
  description:
    "When your agent acts for a client and they ask why it did that, OMEM lets you answer: an audit trail of what it believed and when, a human approval gate before risky actions, and a record that cannot rewrite itself. Book a design-partner pilot.",
};

/* The buyer-facing product page. The homepage sells the engine to builders;
 * this page sells accountability to the team shipping agents to clients, the
 * one who gets asked "why did it do that" and "can a human approve first". It
 * leads with their problem, names the three things OMEM hands them, and ends on
 * the $1,500 design-partner pilot with a real contact path. Memory is the
 * mechanism here, never the headline. */

/* SoftwareApplication schema for AI-answer and rich-result extraction.
 * Facts only; nothing here the site does not already claim. */
const JSONLD = {
  "@context": "https://schema.org",
  "@type": "SoftwareApplication",
  name: "OMEM",
  applicationCategory: "DeveloperApplication",
  operatingSystem: "Windows, macOS, Linux (self-hosted)",
  license: "https://opensource.org/license/mit",
  url: "https://infrastructure.omem-cloud.com",
  offers: { "@type": "Offer", price: "0", priceCurrency: "USD" },
  description:
    "Open-source memory for AI agents built on belief revision: an audit trail of what the agent believed and when, contradictions kept with both sides on record, provenance for every belief, and a named human approval gate before risky actions run.",
};

const PILLARS = [
  {
    k: "Provenance you can hand to a client",
    d: `Ask why the agent believed something and get the chain: which source,
        when, on what basis, and what it contradicted. Export it. When a client's
        compliance person asks "why did it do that," you send a record, not a
        similarity score.`,
  },
  {
    k: "A human approves before it acts",
    d: `A risky action does not run on the model's say-so. It waits for a named
        approver, the approval is recorded under that name, and a plan the model
        proposes cannot name an action into existence. You decide what your agent
        is allowed to do to a client, in code, not in a prompt.`,
  },
  {
    k: "A record that cannot rewrite itself",
    d: `We call it the testimony ledger. Every belief is recorded under a named
        source with its evidence, the log is append-only, contradictions keep
        both sides, and the engine that reads it is frozen: it must replay the
        record byte-identically, verified on every commit, so not even an
        upgrade can change what was said. A court does not trust a witness who
        can edit their statement. Neither does a security reviewer.`,
  },
];

export default function Accountability() {
  return (
    <MarketingShell>
      <script type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(JSONLD) }} />
      <Section className="hero-y">
        <Eyebrow>For teams shipping agents to clients</Eyebrow>
        <HeroHeading className="mt-3">
          When your agent acts for a client, you have to answer for it.
        </HeroHeading>
        <div className="mt-10 grid gap-x-16 gap-y-8 lg:grid-cols-[minmax(0,7fr)_minmax(0,5fr)]">
          <p className="lede !max-w-none">
            The agent does something on a client&rsquo;s behalf, and the client
            asks the one question you have to be able to answer: <em>why did it do
            that?</em> Most memory can&rsquo;t tell you. It overwrote the evidence
            the moment the facts changed. OMEM is built so you can answer: prove
            why the agent believed and did what it did, and approve the risky
            moves before they run.
          </p>
          <div className="lg:pt-1">
            <div className="flex flex-wrap items-center gap-3">
              <ButtonLink href="/pilot">Book a design-partner pilot</ButtonLink>
              <ButtonLink href="/docs/quickstart" variant="secondary">See how it works</ButtonLink>
            </div>
            {/* The lowest-commitment way in. Someone who is not ready to talk
              * will still answer eleven questions about their own system, and
              * the gap list tells them whether they have a problem at all. */}
            <p className="mt-4 text-note">
              <a href="/agent-audit-check">
                Not sure whether you have a problem yet? Eleven questions, in
                your browser, nothing uploaded.
              </a>
            </p>
            <p className="mt-5 text-caption text-faint">
              Self-hosted, so nothing leaves your client&rsquo;s environment.
              <span className="mono mt-1 block">MIT core · your infrastructure</span>
            </p>
          </div>
        </div>
      </Section>

      <Section className="section-y">
        <div className="max-w-3xl">
          <span aria-hidden="true" className="block h-px w-full bg-[color:var(--border)]" />
          <h2 className="display mt-9 text-2xl">Three things a client&rsquo;s reviewer will ask for.</h2>
          <p className="lede mt-6">
            Accountability isn&rsquo;t a feature you bolt on at the security
            review. It&rsquo;s three properties the memory either has or does not,
            and OMEM was built around them.
          </p>
        </div>
        <div className="mt-10 max-w-3xl">
          <SpecList items={PILLARS.map(p => ({ k: p.k, d: p.d }))} />
        </div>
      </Section>

      <Section className="section-y">
        <div className="max-w-3xl">
          <span aria-hidden="true" className="block h-px w-full bg-[color:var(--border)]" />
          <h2 className="display mt-9 text-2xl">The belief-revision engine is how, not the pitch.</h2>
          <p className="lede mt-6">
            Under all of this is a memory that keeps contradictions, tracks what
            was believed at any past moment, and never decides on its own that two
            claims disagree. That&rsquo;s what makes the audit trail trustworthy,
            but you&rsquo;re buying the answer to your client&rsquo;s question, not
            a memory model. If the engine is what interests you, the{" "}
            <span className="mono">why()</span> chain and the whole design are on
            the homepage and in the docs.
          </p>
          <div className="mt-6 flex flex-wrap gap-3">
            <ButtonLink href="/" variant="quiet">How the engine works</ButtonLink>
            <ButtonLink href="/security" variant="quiet">What&rsquo;s built, and what isn&rsquo;t</ButtonLink>
          </div>
        </div>
      </Section>

      <Section className="section-y">
        <div className="rounded-lg border bg-panel p-7 sm:p-9">
          <Eyebrow>The design-partner pilot</Eyebrow>
          <h2 className="display mt-2 text-2xl">$1,500, and I wire it into your stack with you.</h2>
          <p className="lede mt-4 max-w-[54ch]">
            The software is free and MIT, so you are not paying for OMEM. You are
            paying for my time. A design-partner pilot is hands-on: over a couple
            of weeks I work with you to put the approval gate and the provenance
            trail into your agent, you walk away with a record you can show a
            client&rsquo;s compliance team, and I get your feedback and, if it
            earns it, a reference. It&rsquo;s small on purpose, and it carries
            its own guarantee: if the pilot does not produce a review-ready
            artifact, you do not pay.
          </p>
          <div className="mt-7 flex flex-wrap gap-3">
            <ButtonLink href="/pilot">Book a design-partner pilot</ButtonLink>
            <ButtonLink href="https://github.com/troybrandonc-bit/Omem" variant="secondary" external>
              Read the source first
            </ButtonLink>
          </div>
          <p className="mt-5 text-caption text-faint">
            Prefer to try it alone first? <span className="mono">pip install omem-infrastructure</span> and
            the whole thing runs on your laptop.
          </p>
        </div>
      </Section>
    </MarketingShell>
  );
}
