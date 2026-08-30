"use client";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { MarketingShell } from "@/components/marketing/chrome";
import { Section, Eyebrow, HeroHeading, ButtonLink } from "@/components/marketing/ui";

/* The public face of the commons -- what commons.omem-cloud.com shows a
 * visitor, distinct from the product landing. It reads /v1/commons/public,
 * which exists only on the collector, so on any other install this page
 * describes the commons and points at the live one instead. Headline counts
 * are always shown (anonymous aggregate); the patterns and a download appear
 * only once the operator has published the dataset. */

function humanize(t: string): string {
  return t.replace(/^not:/, "not ").replace(/_/g, " ");
}
const CATEGORY_WORD: Record<string, string> = {
  communication: "how people prefer to be reached",
  scheduling: "when they like to meet",
  "work style": "how they like to work",
  commercial: "what they intend commercially",
  other: "other",
};

export default function Commons() {
  const { data, isError } = useQuery({
    queryKey: ["commons-public"], queryFn: () => api.commonsPublic(), retry: false });

  // isError (404) => not a collector: this is a describe-the-commons page.
  const live = data && data.collector && !isError;
  const s = data?.stats;

  return (
    <MarketingShell>
      <Section className="pt-16 sm:pt-24">
        <Eyebrow>The OMEM commons</Eyebrow>
        <HeroHeading>What people are like, learned as counts, held by no one.</HeroHeading>
        <p className="lede mt-7 max-w-[44ch]">
          A shared, anonymous record of how people actually work, contributed on
          purpose by OMEM installations. Its one objective:{" "}
          {data?.mission
            ? data.mission + "."
            : "connect humans and AI by giving AI a better understanding of our nature and behaviour, without holding a single fact about a person."}
        </p>
      </Section>

      {live && s && (
        <Section className="mt-14">
          <div className="grid grid-cols-1 gap-px overflow-hidden rounded-lg border bg-[color:var(--line)] sm:grid-cols-3">
            {[["Contributing installations", s.contributors + 1],
              ["Patterns learned", s.patterns],
              ["Stances counted", s.stances]].map(([label, value]) => (
              <div key={label} className="bg-bg px-6 py-7">
                <div className="num display text-4xl">{Number(value).toLocaleString()}</div>
                <div className="mt-2 text-note text-muted">{label}</div>
              </div>
            ))}
          </div>
          {Object.keys(s.categories).length > 0 && (
            <p className="mt-5 text-note text-muted">
              What it covers so far:{" "}
              {Object.keys(s.categories).map(c => CATEGORY_WORD[c] || c).join(", ")}.
            </p>
          )}
        </Section>
      )}

      <Section className="mt-16">
        <div className="grid gap-8 sm:grid-cols-3">
          {[["Anonymous by construction",
             "A line is two behaviour tokens and the counts of people who held both. No name, no company, no message, no number can appear. It is refused at the door it enters and the door it leaves."],
            ["Contributed, not scraped",
             "Every line was learned by an install from its own memory and sent only because its operator opted in. What leaves a machine is exactly the file that sits on its own disk to read."],
            ["A prior, never a rule",
             "A rate is a tendency across a population. Any one person can and will contradict it, and a system that respects people treats every pattern as a prior that yields to the individual."]].map(([h, b]) => (
            <div key={h}>
              <h3 className="text-note font-semibold">{h}</h3>
              <p className="mt-2 text-note leading-relaxed text-muted">{b}</p>
            </div>
          ))}
        </div>
      </Section>

      <Section className="mt-16">
        <div className="rounded-lg border bg-panel p-7 sm:p-9">
          <Eyebrow>For AI training</Eyebrow>
          {live && data?.dataset_public && data.patterns && data.patterns.length > 0 ? (
            <>
              <h2 className="display mt-2 text-2xl">The dataset is open.</h2>
              <p className="lede mt-4 max-w-[52ch]">
                One JSON line per pattern, counts plus a plain-English rendering,
                with a dataset card. {data.license}, attribution to the OMEM commons.
              </p>
              <div className="mono mt-6 space-y-1 rounded-md border bg-bg p-4 text-note">
                {data.patterns.slice(0, 6).map(p => (
                  <div key={p.pattern} className="text-muted">
                    <span className="text-fg">{humanize(p.antecedent)}</span> → usually{" "}
                    <span className="text-fg">{humanize(p.consequent)}</span>{" "}
                    <span className="text-faint">({Math.round(p.rate * 100)}% of {p.support + p.refute})</span>
                  </div>
                ))}
              </div>
              <div className="mt-7 flex flex-wrap gap-3">
                <ButtonLink href="/v1/commons/dataset" external>Fetch the dataset (JSON)</ButtonLink>
                <ButtonLink href="https://github.com/troybrandonc-bit/Omem" variant="secondary" external>How it is built</ButtonLink>
              </div>
            </>
          ) : (
            <>
              <h2 className="display mt-2 text-2xl">The dataset opens here.</h2>
              <p className="lede mt-4 max-w-[52ch]">
                {live
                  ? "The commons is collecting. Once there is enough to be worth training on, the full corpus is published from this page, as JSONL with a dataset card, under a permissive license."
                  : "This installation is not the commons collector. The live commons runs at commons.omem-cloud.com, and this is what it will offer: an anonymous behavioural corpus for training and evaluating AI."}
              </p>
              <div className="mt-7 flex flex-wrap gap-3">
                {!live && <ButtonLink href="https://commons.omem-cloud.com/commons" external>Visit the commons</ButtonLink>}
                <ButtonLink href="/" variant="secondary">What OMEM is</ButtonLink>
              </div>
            </>
          )}
        </div>
      </Section>

      <Section className="mb-24 mt-16">
        <h2 className="display text-2xl">Feed it, and keep everything else on your own machine.</h2>
        <p className="lede mt-4 max-w-[52ch]">
          The commons grows from OMEM installations that choose to contribute.
          Run OMEM, and on first open it asks once whether to share anonymous
          patterns. Say no and nothing ever leaves; say yes and only counts do.
        </p>
        <div className="mt-7">
          <ButtonLink href="https://github.com/troybrandonc-bit/Omem" external>Run OMEM</ButtonLink>
        </div>
      </Section>
    </MarketingShell>
  );
}
