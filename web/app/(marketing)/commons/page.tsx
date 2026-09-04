import { MarketingShell } from "@/components/marketing/chrome";
import { Section, Eyebrow, HeroHeading, ButtonLink } from "@/components/marketing/ui";
import { CommonsState } from "@/components/marketing/commons-state";
import { CommonsLive } from "./live";

export const metadata = {
  title: "The commons: what people are like, holding a fact about no one",
  description:
    "Installations that opt in pool anonymous counts into one shared bank, published under CC BY so AI can be trained on how people behave without holding a fact about any person. Live figures, the rules that govern it, and what contributing does and does not buy you.",
};

/* The public face of the commons. Live counts from the collector, the rules
 * that govern what may enter and leave, and an honest account of what
 * contributing buys the contributor, which the benchmark says is conditional.
 * Human copy, no em dashes. */

const RULES: [string, string][] = [
  ["A line is counts, never a person",
   `Two behaviour tokens and how many subjects held both. Every word in both
    tokens has to appear in a fixed vocabulary of 383 behaviour words, so a
    name or a company cannot appear at all, and nothing is published on fewer
    than three supporting subjects.`],
  ["Nothing moves without an answer",
   `A stock installation has no bank and makes no request. Contribution happens
    only after the operator says yes, either answer is durable, and saying no
    later asks the collector to withdraw what was already sent.`],
  ["Every contribution records its own terms",
   `What an operator agreed to is written down when they agree to it, with the
    permissions stored beside the counts rather than looked up later. Today
    that grants one thing: publication here under CC BY. Anything else needs
    its own question, asked before it applies.`],
  ["It goes both ways, beneath your own knowledge",
   `Contributing also pulls the published bank back. Borrowed patterns rank
    below anything an installation learned itself, are born more cautious, and
    still only ever fire into a silence, so one steps aside the moment the
    person in front of it says otherwise.`],
  ["One installation cannot teach the world",
   `A pattern has to have been seen by two separate installations before it
    returns to anyone. Agreement is cheap; agreement across separate
    populations is not.`],
];

export default function Commons() {
  return (
    <MarketingShell>
      <Section className="hero-y">
        <Eyebrow>The commons</Eyebrow>
        <HeroHeading className="mt-3">
          What people are like, holding a fact about no one.
        </HeroHeading>
        <div className="mt-10 max-w-[52rem]">
          <p className="lede">
            Installations that choose to pool their counts into one shared bank,
            published under CC BY so an AI can be trained on how people behave
            without anyone handing over a fact about a person. These are the
            live figures, straight from the collector.
          </p>
        </div>
        <CommonsLive />
      </Section>

      <Section className="section-y">
        <h2 className="text-title font-semibold">What is in it</h2>
        <CommonsState />
      </Section>

      <Section className="section-y">
        <h2 className="text-title font-semibold">Contributing without OMEM</h2>
        <p className="mt-4 max-w-2xl text-note leading-relaxed text-muted">
          A contribution is a handful of counts over a published vocabulary of
          392 words, a coarse population shape and a record of which uses you
          granted. Almost none of that is specific to any one piece of
          software, and until recently there was no way for anyone running
          something else to know that. The format is now written down so that
          anything storing facts about people can contribute:{" "}
          <a href="/spec/commons-contribution" className="underline hover:text-fg">
            the contribution format
          </a>
          , with a worked example and one POST that needs no account.
        </p>
      </Section>

      <Section className="section-y">
        <h2 className="text-title font-semibold">The rules it runs under</h2>
        <ul className="mt-8 grid gap-x-14 gap-y-9 sm:grid-cols-2">
          {RULES.map(([k, d]) => (
            <li key={k}>
              <h3 className="text-note font-semibold">{k}</h3>
              <p className="mt-2 text-note leading-relaxed text-muted">{d}</p>
            </li>
          ))}
        </ul>
      </Section>

      <Section className="section-y">
        <h2 className="text-title font-semibold">
          What contributing buys you, and where it stops
        </h2>
        <div className="mt-6 max-w-read space-y-5 text-body text-muted">
          <p>
            We measured this rather than asserting it. A simulated installation
            that had seen six people could mine almost nothing on its own, and
            with the bank it formed an opinion about 111 claims it could not
            otherwise reach, beating the base rate of those same claims by
            twelve points.
          </p>
          <p>
            It stops paying in two places, and both are in the published
            result. When the contributing populations have nothing in common
            the lift falls to zero and then below, which is the control that
            makes the first number worth reading. And when a behaviour is so
            common that almost everyone already holds it, there is nothing left
            for a pattern to add.
          </p>
          <p>
            So the honest version is not that contributing makes your
            installation better. It is that it does when the people you work
            with resemble other contributors&rsquo;, and that early on, before
            two installations have seen the same pattern, there is little to
            receive at all.
          </p>
        </div>
        <div className="mt-8 flex flex-wrap gap-3">
          <ButtonLink href="/objectives">Why this exists</ButtonLink>
          <ButtonLink href="/docs/quickstart" variant="secondary">
            Run an installation
          </ButtonLink>
        </div>
      </Section>
    </MarketingShell>
  );
}
