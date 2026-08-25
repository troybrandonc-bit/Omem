import Link from "next/link";
import { MarketingShell } from "@/components/marketing/chrome";
import { Section, PageHeader, ButtonLink } from "@/components/marketing/ui";
import { Check } from "lucide-react";

export const metadata = {
  title: "Pricing",
  description: "OMEM is free while it is in beta. No paid plan, no card, no quota.",
};

/* OMEM is free while it is in beta. This page used to advertise $25 and $299
 * tiers with SSO, US/EU residency, a 99.9% uptime SLA, SOC 2, HIPAA and BYOK.
 * None of which exist, and none of which could be bought anyway: the checkout
 * endpoint never created a Stripe Checkout Session, so there was no way to pay.
 * Rather than price a product that cannot take payment, this says what is true.
 *
 * The redesign kept every word of that and fixed the form it was in: a 40px
 * headline that matched nothing else on the site, a three-column grid that
 * stacked into an unreadable order on a phone, and a $0 "tier" laid out like
 * one row of a pricing table that has no other rows. There is one plan, so this
 * is one panel, and the list of what is included is the point of the page. */

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
      <Section className="page-y">
        <PageHeader eyebrow="Pricing" title="Free while it is in beta.">
          There is no paid plan, no card, and no quota. OMEM is early software and
          what it needs right now is people using it and telling us where it
          breaks, which is worth more than the revenue a product at this stage
          would make.
        </PageHeader>
      </Section>

      <Section className="pb-20 sm:pb-28">
        <div className="panel overflow-hidden">
          <div className="grid gap-x-12 gap-y-8 p-6 sm:p-8 lg:grid-cols-[minmax(0,300px)_minmax(0,1fr)]">
            <div>
              <h2 className="text-note font-semibold">Everything</h2>
              <div className="mt-2 flex items-baseline gap-2">
                <span className="display text-3xl">$0</span>
                <span className="text-note text-muted">while in beta</span>
              </div>
              <p className="mt-4 max-w-[32ch] text-note text-muted">
                Self-hosted. Runs on your machine with no account anywhere and
                nothing to sign up for.
              </p>
              <ButtonLink href="/docs/quickstart" className="mt-6 w-full sm:w-auto">
                Get started
              </ButtonLink>
            </div>

            <div>
              <h3 className="tech-label mb-3">What that includes</h3>
              <ul className="grid gap-x-8 sm:grid-cols-2">
                {INCLUDED.map(f => (
                  <li key={f} className="flex items-start gap-2.5 border-b border-dotted py-3 text-note last:border-b-0 sm:[&:nth-last-child(2)]:border-b-0">
                    {/* A tick, not a bullet: these are things you get, and the
                        mark should say so without depending on colour. */}
                    <Check className="mt-[5px] h-4 w-4 shrink-0 text-believed" aria-hidden="true" />
                    {f}
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </div>
      </Section>

      <Section className="pb-24 sm:pb-32">
        <div className="spec-row border-t pt-10">
          <h2 className="tech-label pt-1">When that changes</h2>
          <div className="max-w-read space-y-4 text-body text-muted">
            <p>
              The reference engine and the SDKs stay free and self-hostable
              regardless. You should never pay to define what a memory means. If a
              hosted service is ever charged for, it will be for running it at
              scale, and it will be announced before it is billed, not after.
            </p>
            <p>
              What OMEM does not have yet is on the{" "}
              <Link href="/security" className="link-underline text-fg">security page</Link>,
              and it is worth reading before you plan around it.
            </p>
          </div>
        </div>
      </Section>
    </MarketingShell>
  );
}
