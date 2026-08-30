"use client";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { CommonsShell } from "@/components/marketing/commons-shell";
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
    <CommonsShell>
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

      <Section id="mission" className="mt-20">
        <Eyebrow>The mission</Eyebrow>
        <h2 className="display mt-2 max-w-[24ch] text-3xl sm:text-4xl">
          Teach AI what people are like, without teaching it who anyone is.
        </h2>
        <div className="mt-8 grid gap-y-6 gap-x-16 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
          <div className="space-y-6">
            <p className="lede !max-w-none">
              Almost everything an AI knows about people, it learned by reading
              them: messages, posts, documents, the exhaust of individual lives,
              scraped and memorised. That produces models that can recall a
              person. It does not produce models that understand people.
            </p>
            <p className="lede !max-w-none">
              The commons is the other way to learn. It holds no messages and no
              documents, no person and no profile: only how often, across
              everyone who consented, one kind of behaviour goes with another.
              <em className="text-fg not-italic">
                {" "}People who ask to meet in the morning tend to prefer email
                over a call
              </em>{" "}
              — as a rate, over a population, attached to nobody. A model can
              learn the shape of human behaviour from that and never hold a
              human.
            </p>
          </div>
          <div className="space-y-6">
            <p className="lede !max-w-none">
              These are priors, not rules. A rate across a population is a place
              to begin, not a verdict on the person in front of you. An agent
              that starts from a grounded prior — most people here lean this way
              — and revises it the instant the actual person says otherwise
              treats you as an individual, not a demographic. That behaviour is
              what we want AI to learn, and the clean, consented, anonymous
              corpus to learn it from did not exist. So we are building it.
            </p>
            <p className="lede !max-w-none">
              And it is a public good. The corpus is CC BY 4.0, so the
              understanding it builds belongs to everyone who trains on it, not
              to whoever gathered it. An AI&rsquo;s sense of human nature should
              be assembled from patterns people chose to share, in the open —
              not from surveillance, and not owned by one company.
            </p>
          </div>
        </div>
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

      <Section id="how" className="mt-16">
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

      <Section id="dataset" className="mt-16">
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
                <ButtonLink href="/docs" variant="secondary">What OMEM is</ButtonLink>
              </div>
            </>
          )}
        </div>
      </Section>

      <Section id="contribute" className="mb-24 mt-16">
        <h2 className="display text-2xl">We&rsquo;re looking for the people who&rsquo;ll build this.</h2>
        <p className="lede mt-4 max-w-[54ch]">
          The commons is new, and it grows one honest install at a time. Run
          OMEM as your agent&rsquo;s memory, and on first open it asks once
          whether to share anonymous patterns. Say no and nothing ever leaves
          your machine; say yes and only counts do — never a message, a name, or
          a fact about a person. Every install that opts in adds a little more of
          the picture, and teaches AI our nature from data people chose to give.
        </p>
        <div className="mt-7 flex flex-wrap gap-3">
          <ButtonLink href="https://github.com/troybrandonc-bit/Omem" external>Run OMEM and contribute</ButtonLink>
          <ButtonLink href="#dataset" variant="secondary">See what it produces</ButtonLink>
        </div>
      </Section>
    </CommonsShell>
  );
}
