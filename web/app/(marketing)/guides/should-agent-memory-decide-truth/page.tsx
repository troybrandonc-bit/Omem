import { MarketingShell } from "@/components/marketing/chrome";
import { Section, ButtonLink } from "@/components/marketing/ui";

export const metadata = {
  title: "Should an AI agent's memory decide what is true?",
  description:
    "Most agent memory silently overwrites contradictions and loses the history. The case for memory that keeps both sides, tracks belief over time, and proves why, instead of deciding truth on its own.",
};

/* The cornerstone essay, published on the owned domain so every post and
 * thread has a link target that ranks here rather than on someone else's
 * platform. No em dashes. */

export default function Essay() {
  return (
    <MarketingShell>
      <Section className="page-y">
        <article className="prose-omem max-w-3xl">
          <div className="tech-label mb-3">Essay</div>
          <h1 className="display text-3xl">Should an agent&rsquo;s memory decide what is true?</h1>

          <h2>The bug you cannot see until it bites</h2>
          <p>
            You give your agent a fact on Monday: the customer is on the Pro
            plan. On Thursday a webhook says the customer downgraded to Free.
            Your memory layer does the sensible-looking thing. It updates the
            record. Pro becomes Free, and Monday is gone.
          </p>
          <p>
            Now ask the agent a question it should be able to answer: when did
            they downgrade, and what did we believe before that? It cannot. Not
            because the data was hard to find, but because your memory threw it
            away the moment it decided the new fact won. The history that would
            let you audit the agent, reconstruct a past decision, or notice that
            the two facts came from sources you trust differently: none of it
            exists anymore.
          </p>
          <p>
            This is the default in almost every agent memory system on the
            market. Store a fact. Retrieve the nearest one. When two conflict,
            the last write wins and the loser is deleted. It looks like memory.
            It behaves like a whiteboard.
          </p>

          <h2>The quiet assumption underneath</h2>
          <p>
            Overwriting on conflict encodes a belief most teams never chose on
            purpose: that the memory layer is the right place to decide what is
            true.
          </p>
          <p>
            It is not. Deciding truth is a judgment about which source is more
            reliable, whether two claims actually contradict or just look
            similar, whether the old fact still holds in some context the new
            one does not cover. That judgment belongs to your application, your
            policy, or a human. A key-value store is not equipped to make it,
            and when it makes it silently, you inherit three problems:
          </p>
          <ul>
            <li>
              <strong>You cannot audit what you cannot reconstruct.</strong> If
              a client asks why your agent told them they were on the Free
              plan, &ldquo;the database only keeps the current value&rdquo; is
              not an answer they will accept.
            </li>
            <li>
              <strong>You get confabulation, not memory.</strong> A system that
              resolves every conflict into one confident current value states
              that value with the same confidence whether it is well supported
              or a coin flip between two sources.
            </li>
            <li>
              <strong>The judgment is invisible and unversioned.</strong> The
              most consequential thing your memory does, picking a winner,
              leaves no trace. You cannot tune it, test it, or explain it,
              because it was never written down.
            </li>
          </ul>

          <h2>The alternative: memory that refuses</h2>
          <p>
            There is a different design, and it comes from an old idea in AI
            called belief revision: keep the claims, track which one you
            currently believe, and never throw away the losing side. Memory
            that refuses to decide truth does four things a vector store does
            not:
          </p>
          <ul>
            <li>
              <strong>It keeps both sides of a contradiction.</strong> Pro and
              Free both stay on record. One is marked believed right now; the
              other is contradicted, not deleted.
            </li>
            <li>
              <strong>It tracks belief over time.</strong> You can ask what the
              agent believed last Tuesday and get last Tuesday&rsquo;s answer,
              not today&rsquo;s.
            </li>
            <li>
              <strong>It can tell you why.</strong> Ask why it believes the
              customer is on Free and you get the chain of evidence: which
              source, when, on what basis. Not a similarity score.
            </li>
            <li>
              <strong>It will not invent a disagreement.</strong> Declaring two
              claims opposed is a judgment, and the caller makes it explicitly.
              The memory never reads two sentences and decides they conflict,
              which is what keeps the same question returning the same answer a
              year from now.
            </li>
          </ul>
          <p>
            The shift is small to describe and large in consequence. The memory
            stops being an oracle that hands you one confident answer and
            becomes a ledger you can question.
          </p>

          <h2>Is that not just more complexity?</h2>
          <p>Fair objection. Three honest answers.</p>
          <p>
            <strong>You already have this complexity; it is just hidden.</strong>{" "}
            The conflict-resolution logic exists in every system. The overwrite
            version simply runs it silently and discards the evidence. Making
            it explicit is not adding complexity, it is surfacing complexity
            you already shipped.
          </p>
          <p>
            <strong>You still get one current answer.</strong> Keeping both
            sides does not mean your agent has to reason about both. It asks
            what is believed now and gets a single value, same as before. The
            history is there when you need it (an audit, a rollback, a what
            changed since last session) and invisible when you do not.
          </p>
          <p>
            <strong>Sometimes you do want a decision, and that is fine.</strong>{" "}
            The point is not that truth is never resolved. It is that the
            resolution should happen where the context lives, in your policy,
            your rules, or a human in the loop, and should leave a record.
            Memory&rsquo;s job is to hold the claims and the provenance
            faithfully, so the decision, wherever it is made, can be made well
            and explained later.
          </p>

          <h2>Why this is becoming non-optional</h2>
          <p>
            For a weekend project, last-write-wins is fine. The stakes change
            the moment an agent acts on behalf of someone else. When you ship
            an agent to a client, &ldquo;why did it do that&rdquo; stops being
            a debugging convenience and becomes an accountability requirement,
            sometimes a contractual or regulatory one. You cannot answer it
            with a memory that overwrote the evidence.
          </p>
          <p>
            The teams that will trust agents with real decisions are going to
            demand what we demand of any system that acts with authority: show
            your work, keep the record, let a human check it before it acts.
            Memory that refuses to decide truth is the substrate that makes
            that possible.
          </p>

          <h2>Where this is built</h2>
          <p>
            This is what OMEM exists to do. Open source (MIT), self-hosted, no
            dependencies, one pip install. The belief-revision engine keeps
            contradictions, tracks belief over time, and answers why. It runs
            on your machine and phones home to nobody. If you have ever watched
            your agent state something with total confidence that you knew was
            a coin flip between two sources, that is the problem it exists to
            fix.
          </p>

          <div className="mt-10 flex flex-wrap gap-3">
            <ButtonLink href="/docs/quickstart">Run OMEM locally</ButtonLink>
            <ButtonLink href="/guides/ai-agent-audit-trail" variant="secondary">
              The audit-trail guide
            </ButtonLink>
          </div>
        </article>
      </Section>
    </MarketingShell>
  );
}
