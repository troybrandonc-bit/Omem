import Link from "next/link";
import { MarketingShell } from "@/components/marketing/chrome";
import { Section } from "@/components/marketing/ui";

export const metadata = { title: "Pricing / OMEM Cloud" };

const TIERS = [
  { name: "Free", price: "$0", note: "forever", cta: "Start free", href: "/onboarding", accent: false,
    line: "Full memory model, one development environment.",
    features: ["100k stored primitives", "1 development environment", "Embedded SDK, offline", "Community support"] },
  { name: "Pro", price: "$25", note: "/mo + usage", cta: "Start building", href: "/onboarding", accent: true,
    line: "Production keys, staging, and higher limits.",
    features: ["5M stored primitives", "Staging + production", "gRPC, webhooks, live inspector", "Email support"] },
  { name: "Business", price: "$299", note: "/mo + usage", cta: "Start building", href: "/onboarding", accent: false,
    line: "Teams, SSO, residency, and an SLA.",
    features: ["100M stored primitives", "Full RBAC, SSO add-on", "US / EU residency", "99.9% uptime SLA"] },
  { name: "Enterprise", price: "Custom", note: "", cta: "Talk to us", href: "/security", accent: false,
    line: "Self-hosted, compliance, and dedicated support.",
    features: ["VPC / self-hosted / air-gapped", "SOC 2, HIPAA, BYOK", "Residency anywhere", "Dedicated support + SLA"] },
];

export default function Pricing() {
  return (
    <MarketingShell>
      <Section className="pt-20 pb-14">
        <div className="tech-label mb-4">Pricing</div>
        <h1 className="display max-w-xl text-[40px]">Start free. Pay for scale, not for the standard.</h1>
        <p className="mt-5 max-w-lg text-[15px] leading-relaxed text-muted">
          Usage-based and developer-friendly. The embedded SDK and reference engine are free and
          self-hostable forever. You pay to run memory at scale, never to define what a memory means.
        </p>
      </Section>

      <Section className="pb-8">
        <div className="border-t">
          {TIERS.map((t, i) => (
            <div key={t.name} className="grid gap-x-10 gap-y-5 border-b py-8 md:grid-cols-[200px_1fr_auto]">
              <div>
                <div className="flex items-baseline gap-2">
                  <span className="text-[17px] font-medium tracking-tight">{t.name}</span>
                  {t.accent && <span className="text-2xs font-medium text-accent">popular</span>}
                </div>
                <div className="mt-1.5 flex items-baseline gap-1">
                  <span className="display text-[28px]">{t.price}</span>
                  <span className="text-xs text-muted">{t.note}</span>
                </div>
                <p className="mt-2 max-w-[180px] text-[13px] leading-relaxed text-muted">{t.line}</p>
              </div>
              <ul className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                {t.features.map(f => (
                  <li key={f} className="border-b border-dotted py-1.5 text-[13px] last:border-b-0">{f}</li>
                ))}
              </ul>
              <div className="flex items-start">
                <Link href={t.href}
                  className={`whitespace-nowrap rounded-md border px-4 py-2 text-[13px] font-medium transition-colors ${
                    t.accent ? "border-fg bg-fg text-bg hover:bg-transparent hover:text-fg" : "hover:bg-panel"}`}>
                  {t.cta}
                </Link>
              </div>
            </div>
          ))}
        </div>
        <p className="mt-6 text-2xs text-muted">
          Metered on writes, weighted query units, and stored primitives. Hard spend caps and alerts on every plan.
        </p>
      </Section>
    </MarketingShell>
  );
}
