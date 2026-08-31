import Link from "next/link";
import { MarketingShell } from "@/components/marketing/chrome";
import { Section, PageHeader, SpecList, ButtonLink } from "@/components/marketing/ui";
import { COMPARISONS, SHARED_DIFFERS } from "./comparisons";

export const metadata = {
  title: "OMEM vs other agent memory",
  description:
    "How OMEM differs from memory layers like Mem0, Zep and Letta: belief state instead of stored strings, declared conflicts, evidence chains, and a replayable record.",
};

/* The hub. Each alternative gets its own page because that is how people
 * search, but the argument they share lives here once. Same fairness rule
 * as comparisons.ts: praise first, category-level claims only, and nothing
 * about OMEM that the repository's CI does not assert. */

export default function Compare() {
  return (
    <MarketingShell>
      <Section className="page-y">
        <PageHeader
          eyebrow="Comparisons"
          title="Most agent memory answers what was said. OMEM answers what is believed.">
          The tools below are good at what they do, and honest comparison
          beats a fair fight lost. The difference is the question being
          answered: retrieval layers find relevant text, OMEM keeps an
          auditable record of belief, with evidence, conflicts, and history
          you can replay.
        </PageHeader>
      </Section>

      <Section className="pb-16 sm:pb-20">
        <h2 className="display text-xl">The comparisons</h2>
        <dl className="mt-6 border-t">
          <div className="spec-row border-b py-9">
            <dt className="text-note font-semibold text-fg">
              <Link href="/compare/omem-vs-mem0-vs-zep" className="hover:text-accent">
                OMEM vs Mem0 vs Zep, side by side
              </Link>
            </dt>
            <dd className="max-w-read text-body text-muted">
              The three-way table for anyone weighing the two incumbents
              against each other: what each optimizes, what happens on a
              conflict, and where each one honestly wins.
            </dd>
          </div>
          {COMPARISONS.map(c => (
            <div key={c.slug} className="spec-row border-b py-9">
              <dt className="text-note font-semibold text-fg">
                <Link href={`/compare/${c.slug}`} className="hover:text-accent">
                  OMEM vs {c.name}
                </Link>
              </dt>
              <dd className="max-w-read text-body text-muted">{c.lede}</dd>
            </div>
          ))}
        </dl>
      </Section>

      <Section className="pb-20 sm:pb-28">
        <h2 className="display text-xl">What is different, whoever the alternative is</h2>
        <div className="mt-6">
          <SpecList items={SHARED_DIFFERS} />
        </div>
        <div className="mt-10 flex flex-wrap items-center gap-4">
          <ButtonLink href="https://github.com/troybrandonc-bit/Omem" external>
            Read the source
          </ButtonLink>
          <ButtonLink href="/docs/quickstart" variant="secondary">
            Try it in five minutes
          </ButtonLink>
        </div>
      </Section>
    </MarketingShell>
  );
}
