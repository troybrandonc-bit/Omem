import Link from "next/link";
import { notFound } from "next/navigation";
import { MarketingShell } from "@/components/marketing/chrome";
import { Section, PageHeader, SpecList, ButtonLink, CodeBlock } from "@/components/marketing/ui";
import { COMPARISONS, SHARED_DIFFERS, getComparison } from "../comparisons";

export function generateStaticParams() {
  return COMPARISONS.map(c => ({ slug: c.slug }));
}

export function generateMetadata({ params }: { params: { slug: string } }) {
  const c = getComparison(params.slug);
  if (!c) return {};
  return {
    title: `OMEM vs ${c.name}`,
    description: c.lede,
  };
}

const SAMPLE = `mem.remember(agent="sales", about="customer:acme", claim="prefers_annual_billing")
mem.remember(agent="support", about="customer:acme", claim="not:prefers_annual_billing")

mem.believes(about="customer:acme", claim="prefers_annual_billing")
# -> CONTRADICTED   (both sides on the record, neither silently wins)

mem.why(assertion_id)
# -> the evidence chain: who said it, the quoted source, what conflicts`;

export default function ComparePage({ params }: { params: { slug: string } }) {
  const c = getComparison(params.slug);
  if (!c) notFound();

  return (
    <MarketingShell>
      <Section className="page-y">
        <PageHeader eyebrow={c.eyebrow} title={c.title}>
          {c.lede}
        </PageHeader>
      </Section>

      <Section className="pb-16 sm:pb-20">
        <h2 className="display text-xl">What {c.name} is genuinely good at</h2>
        <p className="mt-3 max-w-read text-body text-muted">
          A comparison that cannot say this is an advertisement. These are
          real strengths, and if they match your problem, use {c.name}.
        </p>
        <div className="mt-6">
          <SpecList items={c.goodAt} />
        </div>
      </Section>

      <Section className="pb-16 sm:pb-20">
        <h2 className="display text-xl">What OMEM does differently</h2>
        <p className="mt-3 max-w-read text-body text-muted">
          Every claim below is asserted by the repository&apos;s CI, so none
          of it can quietly stop being true.
        </p>
        <div className="mt-6">
          <SpecList items={SHARED_DIFFERS} tone="accent" />
        </div>
        <div className="mt-10">
          <CodeBlock single={SAMPLE} filename="the_difference.py" label="Belief state example" />
        </div>
      </Section>

      <Section className="pb-20 sm:pb-28">
        <h2 className="display text-xl">The honest decision guide</h2>
        <div className="mt-6 grid gap-10 sm:grid-cols-2">
          <div>
            <h3 className="text-note font-semibold text-fg">Choose {c.name} when</h3>
            <ul className="mt-4 space-y-3">
              {c.chooseThem.map(x => (
                <li key={x} className="max-w-read text-body text-muted">{x}</li>
              ))}
            </ul>
          </div>
          <div>
            <h3 className="text-note font-semibold text-accent">Choose OMEM when</h3>
            <ul className="mt-4 space-y-3">
              {c.chooseOmem.map(x => (
                <li key={x} className="max-w-read text-body text-muted">{x}</li>
              ))}
            </ul>
          </div>
        </div>
        <div className="mt-12 flex flex-wrap items-center gap-4">
          <ButtonLink href="https://github.com/troybrandonc-bit/Omem" external>
            Read the source
          </ButtonLink>
          <ButtonLink href="/docs/quickstart" variant="secondary">
            Try it in five minutes
          </ButtonLink>
          <Link href="/compare" className="text-note text-muted underline decoration-[color:var(--line-strong)] underline-offset-[6px] hover:text-fg">
            All comparisons
          </Link>
        </div>
      </Section>
    </MarketingShell>
  );
}
