import Link from "next/link";
import { MarketingShell } from "@/components/marketing/chrome";
import { Section, Eyebrow, CodeBlock } from "@/components/marketing/ui";
import { BeliefInspector } from "@/components/marketing/belief-inspector";

export const metadata = {
  title: "OMEM / memory for AI agents that refuses to decide what is true",
  description:
    "OMEM tracks what each agent believes, when it learned it, and why. Contradictions are surfaced rather than overwritten, and no repair runs that nobody authorised. Self-hosted, MIT, no dependencies.",
};

/* The landing page.
 *
 * Content thesis: do not lead with memory. Every framework ships a vector store,
 * recall quality cannot be demonstrated in a paragraph, and competing there is a
 * race with no finish line. Lead with what OMEM refuses to do, because that is
 * the part a competitor cannot copy without rebuilding their engine.
 *
 * TYPE. Everything here is on the scale in tailwind.config.ts (11 · 13 · 16 · 20
 * · 25 · 31) rather than on arbitrary `text-[44px]` values. Two reasons, and the
 * second is the one that actually bites:
 *
 *   1. `.interface-design/system.md` defines that scale, and DESIGN-README says
 *      "headlines are strong, never huge". A 44px hero was neither on the scale
 *      nor in keeping with it.
 *   2. An arbitrary `text-[30px]` emits font-size and NOTHING else, so it
 *      silently discards the lineHeight and letterSpacing the config pairs with
 *      every step. The config carries a comment warning about exactly this. The
 *      marketing pages had drifted to eleven distinct arbitrary sizes, four of
 *      them within 3px of each other, which is not a hierarchy.
 *
 * Prose blocks add `leading-relaxed` on purpose: the paired leading is tuned for
 * dense dashboard rows, and 16/22 is too tight for a paragraph someone reads
 * rather than scans. Size stays on the scale so tracking still comes with it.
 *
 * Nothing on this page is a claim the product cannot back. The belief inspector
 * is the real demo project the API serves. The refusal transcript is the real
 * shape of a denied plan. The list near the end is what OMEM does NOT do.
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

/* The page's single primary action. It was an underlined text link competing
   with two others of identical weight, which left the layout with no answer to
   "what do I do here". 44px tall so it is a real target on a phone, not only a
   comfortable one on a desktop. */
function PrimaryLink({ href, children }: { href: string; children: React.ReactNode }) {
  return (
    <Link href={href}
      className="inline-flex h-11 items-center rounded-md bg-accent px-5 text-sm font-medium text-accentFg
                 transition-[opacity,transform] duration-150 ease-out hover:opacity-90 active:scale-[0.98]">
      {children}
    </Link>
  );
}

function SecondaryLink({ href, children, external }: { href: string; children: React.ReactNode; external?: boolean }) {
  const cls = "inline-flex h-11 items-center text-sm font-medium text-muted transition-colors hover:text-fg";
  return external
    ? <a href={href} className={cls}>{children}</a>
    : <Link href={href} className={cls}>{children}</Link>;
}

export default function Home() {
  return (
    <MarketingShell>
      {/* ── hero ──────────────────────────────────────────────────────── */}
      <Section className="pb-16 pt-20">
        <div className="grid items-start gap-12 lg:grid-cols-[minmax(0,1fr)_minmax(0,500px)]">
          <div>
            <Eyebrow>Memory for AI agents</Eyebrow>
            {/* xl on a phone, 2xl from sm up: the top of the scale, not past it. */}
            <h1 className="display max-w-xl text-xl sm:text-2xl">
              Your agent should be able to say <em>why</em> it believes something.
            </h1>
            <p className="mt-5 max-w-lg text-md leading-relaxed text-muted">
              Most agent memory is a list of facts. When two of them conflict, one
              silently overwrites the other and the history is gone. OMEM keeps
              both, tracks which one is believed right now, and can reconstruct
              what was believed at any point in the past.
            </p>
            <p className="mt-3.5 max-w-lg text-md leading-relaxed text-muted">
              It runs on your own machine, with no external services and nothing
              to install alongside it.
            </p>

            <div className="mt-7 max-w-md">
              <CodeBlock filename="one minute" single={`pip install omem-infrastructure\nomem-server`} />
            </div>

            <div className="mt-6 flex flex-wrap items-center gap-x-5 gap-y-1">
              <PrimaryLink href="/docs/quickstart">Start the quickstart</PrimaryLink>
              <SecondaryLink href="https://github.com/troybrandonc-bit/Omem" external>
                Read the source
              </SecondaryLink>
            </div>
            <p className="mono mt-1 text-2xs text-faint">MIT &middot; Python 3.9+ &middot; no dependencies</p>
          </div>

          {/* The real demo project, not a mockup: move the selector and the
              belief state actually changes. */}
          <div>
            <BeliefInspector />
            <p className="mt-3 text-2xs text-faint">
              A real assertion from the demo project. Change &ldquo;as of&rdquo; and
              watch the belief state move.
            </p>
          </div>
        </div>
      </Section>

      {/* ── the refusals ──────────────────────────────────────────────── */}
      <Section className="border-t py-16">
        <Eyebrow>What it refuses to do</Eyebrow>
        <h2 className="display max-w-2xl text-lg sm:text-xl">
          The useful part of a memory layer is the part that says no.
        </h2>
        <p className="mt-4 max-w-xl text-md leading-relaxed text-muted">
          Anything can store a fact. What decides whether your agent is
          trustworthy is what it declines to do with one.
        </p>
        <div className="mt-9 border-t">
          {REFUSALS.map(r => (
            <div key={r.k} className="spec-row border-b py-6">
              <div className="text-sm font-medium">{r.k}</div>
              <p className="max-w-xl text-sm leading-relaxed text-muted">{r.d}</p>
            </div>
          ))}
        </div>
      </Section>

      {/* ── the refusal, shown ────────────────────────────────────────── */}
      <Section className="border-t py-16">
        <div className="grid gap-10 lg:grid-cols-2">
          <div>
            <Eyebrow>Self-healing, under policy</Eyebrow>
            <h2 className="display max-w-lg text-lg sm:text-xl">
              A model proposed <span className="mono">exec_shell</span>. OMEM did not run it.
            </h2>
            <p className="mt-4 max-w-lg text-md leading-relaxed text-muted">
              OMEM records what breaks and repairs it under policy. The model is a
              reasoning component that may <em className="not-italic font-medium text-fg">propose</em> a
              plan; OMEM decides what is permitted, what executes, and whether it
              actually worked.
            </p>
            <p className="mt-3.5 max-w-lg text-md leading-relaxed text-muted">
              Error text and model output are data here. Neither can name an
              action into existence, and the refusal is written down with the
              reason for every action rather than disappearing.
            </p>
            <SecondaryLink href="/docs">How the healing loop works</SecondaryLink>
          </div>
          <CodeBlock
            filename="a denied plan"
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

      {/* ── what a vector store cannot do ─────────────────────────────── */}
      <Section className="border-t py-16">
        <Eyebrow>The part a vector store cannot do</Eyebrow>
        <h2 className="display max-w-2xl text-lg sm:text-xl">
          Two agents disagree. Both are kept, one is believed, and you can ask why.
        </h2>
        <div className="mt-9 grid gap-10 lg:grid-cols-[minmax(0,540px)_minmax(0,1fr)]">
          <CodeBlock
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
                code: `import { Memory } from "@omem/sdk";

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
          <div className="flex flex-col gap-5">
            {FEATURES.map(([k, d]) => (
              <div key={k}>
                <div className="text-sm font-medium">{k}</div>
                <p className="mt-1 max-w-md text-sm leading-relaxed text-muted">{d}</p>
              </div>
            ))}
          </div>
        </div>
      </Section>

      {/* ── the honesty section ───────────────────────────────────────── */}
      <Section className="border-t py-16">
        <div className="grid gap-10 lg:grid-cols-2">
          <div>
            <Eyebrow>What it does not do</Eyebrow>
            <h2 className="display max-w-lg text-lg sm:text-xl">
              This is early software, and the second list matters as much as the first.
            </h2>
            <p className="mt-4 max-w-lg text-md leading-relaxed text-muted">
              OMEM is free while it is in beta, and it is missing things you would
              need before putting it somewhere serious. They are written down
              rather than discovered during a security review.
            </p>
            <SecondaryLink href="/security">Read the full security page</SecondaryLink>
          </div>
          <ul className="border-t">
            {NOT_YET.map(n => (
              <li key={n} className="flex items-start gap-3 border-b py-3">
                <span className="led closed mt-1 shrink-0" aria-hidden="true" />
                <span className="text-sm leading-relaxed text-muted">{n}</span>
              </li>
            ))}
          </ul>
        </div>
      </Section>

      {/* ── close ─────────────────────────────────────────────────────── */}
      <Section className="border-t py-20">
        <h2 className="display max-w-xl text-lg sm:text-xl">
          The whole thing runs on your laptop in about a minute.
        </h2>
        <p className="mt-4 max-w-lg text-md leading-relaxed text-muted">
          No signup, no card, no quota, and no service to depend on. If it breaks
          or feels wrong, that is exactly the feedback worth having right now.
        </p>
        <div className="mt-7 max-w-md">
          <CodeBlock filename="start here" single={`pip install omem-infrastructure\nomem-server`} />
        </div>
        <div className="mt-6 flex flex-wrap items-center gap-x-5 gap-y-1">
          <PrimaryLink href="/docs/quickstart">Start the quickstart</PrimaryLink>
          <SecondaryLink href="/docs">Documentation</SecondaryLink>
          <SecondaryLink href="https://github.com/troybrandonc-bit/Omem/issues" external>
            Report something broken
          </SecondaryLink>
        </div>
      </Section>
    </MarketingShell>
  );
}
