import { MarketingShell } from "@/components/marketing/chrome";
import { Section, Eyebrow, HeroHeading, ButtonLink } from "@/components/marketing/ui";

export const metadata = {
  title: "Our objective: teach AI what people are like, holding a fact about no one",
  description:
    "OMEM is the system of record for what an AI agent believed and did, but the reason it exists runs deeper: to give AI a real understanding of human nature and behaviour, learned as anonymous patterns that name no one. Consenting installs pool their counts into a shared bank, offered to train AI while holding a fact about nobody.",
};

/* The objective / identity page. OMEM's mission, stated plainly. Consenting
 * installs contribute anonymous counts to a shared bank, which is offered to
 * train AI while holding a fact about no one. Human copy, no em dashes. */

const POINTS = [
  {
    k: "Learn people, without holding a person",
    d: `Most of what AI knows about people it learned by reading them: their
        messages, their documents, the record of individual lives. OMEM learns
        the other way. From what it sees across many people it forms priors,
        regularities of the form "people who do X tend to do Y", and keeps them
        as counts, never as a fact about anyone.`,
  },
  {
    k: "A shared bank, contributed on purpose",
    d: `Installs that choose to can pool their counts into one shared bank. Every
        line is two behaviour tokens and the number of people who held both. No
        name, no message, and no number about a person can appear, because it is
        refused at the door it enters and the door it leaves.`,
  },
  {
    k: "A corpus AIs can train on",
    d: `The shared bank is offered as a training set: counts plus a plain
        rendering, under a permissive license. A model can learn the shape of how
        people behave from it and never hold a person. That is the objective:
        teach AI our nature from patterns people chose to share, not from
        surveillance.`,
  },
  {
    k: "Contributing grants one use, and it is written down",
    d: `Every contribution records the terms it was made under, at the moment it
        was made. Today those terms grant one thing: publication in the public
        commons under CC BY. Any other use, commercial ones included, needs its
        own question, asked before it applies and never applied backwards. And
        turning contribution off now asks the commons to withdraw what was
        already sent, so the counts stop being published and stop reaching
        anyone.`,
  },
  {
    k: "A prior yields to the person",
    d: `A rate across a population is a place to start, not a verdict on the one
        in front of you. A prior fires only into a silence, and the instant that
        person's own evidence disagrees it steps aside. A general pattern never
        overrides an individual.`,
  },
];

export default function Objectives() {
  return (
    <MarketingShell>
      <Section className="hero-y">
        <Eyebrow>Our objective</Eyebrow>
        <HeroHeading className="mt-3">
          Teach AI what people are like, holding a fact about no one.
        </HeroHeading>
        <div className="mt-10 max-w-[52rem]">
          <p className="lede">
            OMEM is the record of what an AI agent believed and did, but the
            reason it exists runs deeper.
            We want to give AI a real understanding of human nature and
            behaviour, learned as anonymous patterns that name no one. Installs
            that opt in contribute their counts to a shared bank, and that bank is
            offered to train AI, holding counts about behaviour rather than facts
            about people.
          </p>
        </div>
      </Section>

      <Section className="section-y">
        <ul className="grid gap-x-14 gap-y-10 sm:grid-cols-2">
          {POINTS.map(p => (
            <li key={p.k}>
              <h2 className="text-note font-semibold">{p.k}</h2>
              <p className="mt-2 text-note leading-relaxed text-muted">{p.d}</p>
            </li>
          ))}
        </ul>
      </Section>

      <Section className="rule section-y">
        <h2 className="display max-w-[26ch] text-2xl">
          Contribute, and keep everything else yours.
        </h2>
        <p className="lede mt-5 max-w-[52ch]">
          Run OMEM as your agent&rsquo;s memory, and on first open it asks once
          whether to share anonymous counts. Say no and nothing ever leaves your
          machine. Say yes and only counts do, never a message, a name, or a fact
          about a person. That is how the shared bank grows, and how AI comes to
          understand our nature from what people chose to give.
        </p>
        <div className="mt-8 flex flex-wrap items-center gap-3">
          <ButtonLink href="/docs/quickstart">Run OMEM</ButtonLink>
          <ButtonLink href="/docs" variant="secondary">How the priors work</ButtonLink>
        </div>
      </Section>
    </MarketingShell>
  );
}
