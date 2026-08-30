import { MarketingShell } from "@/components/marketing/chrome";
import { Section, Eyebrow, HeroHeading, ButtonLink } from "@/components/marketing/ui";

export const metadata = {
  title: "Our objective: teach AI what people are like, holding no fact about anyone",
  description:
    "OMEM is memory for AI agents, but the reason it exists goes further: to give AI a real understanding of human nature and behaviour, learned as anonymous patterns that name no one. Those patterns live in your own intelligence bank, a file on your machine, and can be exported to train AI without holding a person.",
};

/* The objective / mission page, folded onto the product site from what used to
 * be the standalone commons. There is no public pool and no separate commons
 * website anymore: the bank is a local file on the operator's own machine, and
 * this page states why it exists. Human copy, no em dashes. */

const POINTS = [
  {
    k: "Learn people, without holding a person",
    d: `Most of what AI knows about people it learned by reading them: their
        messages, their documents, the record of individual lives. OMEM learns
        the other way. From what it sees across many people it forms priors,
        regularities of the form "people who do X tend to do Y", and it stores
        them as counts, never as a fact about anyone.`,
  },
  {
    k: "The bank is yours, on your machine",
    d: `Those priors collect in your intelligence bank, a file on your own
        computer. It holds counts over behaviour, not people. No name, no
        message, and no number about anyone can appear in it, because the door
        it enters refuses anything that could.`,
  },
  {
    k: "A corpus you can train on",
    d: `The bank exports as a training set: one line per pattern, plain counts,
        under a permissive license. A model can learn the shape of how people
        behave from it and never hold a person. That is the objective: teach AI
        our nature from patterns people can stand behind, not from surveillance.`,
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
          Teach AI what people are like, without holding a fact about anyone.
        </HeroHeading>
        <div className="mt-10 max-w-[52rem]">
          <p className="lede">
            OMEM is memory for AI agents, but the reason it exists goes further.
            We want to give AI a real understanding of human nature and
            behaviour, learned as anonymous patterns that name no one. Those
            patterns live in your own intelligence bank, a file on your machine,
            and hold counts about behaviour rather than facts about people.
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
          The bank grows as you use OMEM, and it stays on your own machine.
        </h2>
        <p className="lede mt-5 max-w-[52ch]">
          Run OMEM as your agent&rsquo;s memory and it learns what people are
          like as it goes. Your data never leaves your computer unless you export
          it on purpose. Read the intelligence bank in the dashboard, and take
          the training set whenever you want it.
        </p>
        <div className="mt-8 flex flex-wrap items-center gap-3">
          <ButtonLink href="/docs/quickstart">Run OMEM</ButtonLink>
          <ButtonLink href="/docs" variant="secondary">How the priors work</ButtonLink>
        </div>
      </Section>
    </MarketingShell>
  );
}
