import Link from "next/link";
import { MarketingShell } from "@/components/marketing/chrome";
import { Section } from "@/components/marketing/ui";

export const metadata = { title: "Pricing / OMEM" };

// OMEM is free while it is in beta. This page used to advertise $25 and $299
// tiers with SSO, US/EU residency, a 99.9% uptime SLA, SOC 2, HIPAA and BYOK.
// None of which exist, and none of which could be bought anyway: the checkout
// endpoint never created a Stripe Checkout Session, so there was no way to pay.
// Rather than price a product that cannot take payment, this says what is true.

const INCLUDED = [
  "The full memory model: belief state, contradiction, provenance, recall",
  "Unlimited memories and sources",
  "Python and TypeScript SDKs, and an MCP server",
  "The dashboard: memory, conflicts, graph, timeline, audit",
  "Self-host it anywhere, on SQLite or PostgreSQL",
  "MIT licensed: fork it, keep it, no take-backs",
];

export default function Pricing() {
  return (
    <MarketingShell>
      <Section className="pt-20 pb-14">
        <div className="tech-label mb-4">Pricing</div>
        <h1 className="display max-w-xl text-[40px]">Free while it is in beta.</h1>
        <p className="mt-5 max-w-lg text-[15px] leading-relaxed text-muted">
          There is no paid plan, no card, and no quota. OMEM is early software and what it
          needs right now is people using it and telling us where it breaks, which is worth
          more than the revenue a product at this stage would make.
        </p>
      </Section>

      <Section className="pb-8">
        <div className="border-t">
          <div className="grid gap-x-10 gap-y-5 border-b py-8 md:grid-cols-[200px_1fr_auto]">
            <div>
              <span className="text-[17px] font-medium tracking-tight">Everything</span>
              <div className="mt-1.5 flex items-baseline gap-1">
                <span className="display text-[28px]">$0</span>
                <span className="text-xs text-muted">while in beta</span>
              </div>
              <p className="mt-2 max-w-[180px] text-[13px] leading-relaxed text-muted">
                Self-hosted. Runs on your machine with no account anywhere.
              </p>
            </div>
            <ul className="grid grid-cols-1 gap-2 sm:grid-cols-2">
              {INCLUDED.map(f => (
                <li key={f} className="border-b border-dotted py-1.5 text-[13px] last:border-b-0">{f}</li>
              ))}
            </ul>
            <div className="flex items-start">
              <Link href="/docs/quickstart"
                className="whitespace-nowrap rounded-md border border-fg bg-fg px-4 py-2 text-[13px] font-medium text-bg transition-colors hover:bg-transparent hover:text-fg">
                Get started
              </Link>
            </div>
          </div>
        </div>

        <div className="mt-10 max-w-xl text-[13px] leading-relaxed text-muted">
          <p className="font-medium text-fg">When that changes</p>
          <p className="mt-2">
            The reference engine and the SDKs stay free and self-hostable regardless. You should
            never pay to define what a memory means. If a hosted service is ever charged for, it
            will be for running it at scale, and it will be announced before it is billed, not
            after.
          </p>
          <p className="mt-4">
            What OMEM does not have yet is on the{" "}
            <Link href="/security" className="link-underline">security page</Link>, and it is worth
            reading before you plan around it.
          </p>
        </div>
      </Section>
    </MarketingShell>
  );
}
