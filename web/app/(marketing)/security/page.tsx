import Link from "next/link";
import { MarketingShell } from "@/components/marketing/chrome";
import { Section } from "@/components/marketing/ui";

export const metadata = { title: "Security / OMEM Cloud" };

const CONTROLS = [
  { k: "ENCRYPTION", d: "TLS 1.3 in transit; per-tenant envelope encryption at rest via KMS. Customer-managed keys (BYOK) on Enterprise." },
  { k: "AUDIT", d: "An append-only, hash-chained audit stream records every write and sensitive read. Exportable to your SIEM." },
  { k: "RESIDENCY", d: "Pin each project to a region. Data and projections stay in-region; residency is immutable after provisioning." },
  { k: "DEPLOYMENT", d: "Hosted multi-tenant, single-tenant VPC, or fully self-hosted and air-gapped. All pass the identical conformance suite." },
  { k: "IDENTITY", d: "OIDC and SAML SSO, SCIM 2.0 provisioning, enforced 2FA, and scoped, rotatable API keys with least-privilege roles." },
  { k: "COMPLIANCE", d: "SOC 2 Type II and ISO 27001; GDPR/CCPA data-subject export and erase; HIPAA BAA available on Enterprise." },
];

export default function Security() {
  return (
    <MarketingShell>
      <Section className="pt-20 pb-14">
        <div className="tech-label mb-4">Security & Trust</div>
        <h1 className="display max-w-xl text-[40px]">Memory you can put in production.</h1>
        <p className="mt-5 max-w-lg text-[15px] leading-relaxed text-muted">
          The moment an agent acts on a belief, someone is accountable for it. OMEM Cloud is
          built so you can reconstruct and prove agent state at decision time, with
          the controls a regulated deployment requires.
        </p>
      </Section>

      <Section className="pb-16">
        <div className="border-t">
          {CONTROLS.map(c => (
            <div key={c.k} className="spec-row border-b py-6">
              <div className="text-xs font-medium text-accent">{c.k}</div>
              <p className="max-w-xl text-[14px] leading-relaxed text-muted">{c.d}</p>
            </div>
          ))}
        </div>
      </Section>

      <Section className="pb-8">
        <div className="spec-row border-t pt-12">
          <div className="tech-label pt-1">No lock-in</div>
          <div>
            <h2 className="display max-w-lg text-[28px]">An open standard you can verify, and leave with.</h2>
            <p className="mt-5 max-w-lg text-[15px] leading-relaxed text-muted">
              OMEM is a standard first, with a public conformance suite. &quot;Correct&quot; is decidable:
              every deployment (hosted, VPC, or air-gapped) passes the identical 29-vector CTS.
              An agent built against the cloud behaves the same self-hosted. Your memory&apos;s meaning
              never leaves with a vendor.
            </p>
            <dl className="mt-8 max-w-md overflow-hidden rounded-lg border bg-panel text-[13px] shadow-sm">
              {[["Protocol", "OMEM 1.0"], ["Conformance", "CTS 29/29 / deterministic"],
                ["Reference engine", "open source, self-hostable"], ["Audit stream", "hash-chained, append-only"],
                ["Uptime SLA", "up to 99.95% (Enterprise)"]].map(([k, v]) => (
                <div key={k} className="flex items-center justify-between border-b px-4 py-2.5 last:border-b-0">
                  <dt className="text-muted">{k}</dt><dd className="num text-[13px]">{v}</dd>
                </div>
              ))}
            </dl>
            <Link href="/onboarding" className="link-underline mt-8 inline-block text-[13px]">
              Talk to us about enterprise
            </Link>
          </div>
        </div>
      </Section>
    </MarketingShell>
  );
}
