import { MarketingShell } from "@/components/marketing/chrome";
import { Section } from "@/components/marketing/ui";
import { RecordViewer } from "@/components/marketing/record-viewer";

export const metadata = {
  title: "Read a Testimony Record",
  description:
    "Drop a Testimony Record in and read what the agent believed, where each belief came from, where it disagreed with itself, and what it was allowed to do. Checked against the specification in your browser. Nothing is uploaded.",
};

/* The thing that was missing. Everything else built around this format serves
 * CHECKING a record: a validator, a CI action, a conformance mark, a register.
 * Nothing made a record worth having to the person who produced it, so the only
 * reason to emit one was to claim a level, and nobody wants a badge.
 *
 * A record is a decent account of what an agent believed, what disagreed with
 * what, and what got approved. That is hard to get out of ordinary logs and
 * useful while debugging. If reading one costs a drag and drop, the conformance
 * level becomes a side effect of something somebody already wanted. That is how
 * formats spread; the specification was never going to do it on its own.
 *
 * No em dashes. */

export default function View() {
  return (
    <MarketingShell>
      <Section className="page-y">
        <article className="prose-omem max-w-3xl">
          <div className="tech-label mb-3">Testimony Record</div>
          <h1 className="display text-3xl">Read a record</h1>

          <p className="lede">
            What the agent believed, where each belief came from, where it
            disagreed with itself, and what it was allowed to do. Checked
            against the specification as it loads.
          </p>

          <p>
            Everything happens in this tab. The file is read, parsed, validated
            and drawn here, and there is no endpoint to send it to. Records
            carry real material about real people, and a viewer that posted
            them somewhere would be asking you to hand over the thing the
            format exists to look after.
          </p>
        </article>

        <div className="mt-10 max-w-3xl">
          <RecordViewer />
        </div>

        <article className="prose-omem mt-16 max-w-3xl">
          <h2>What you are looking at</h2>
          <p>
            The verdict at the top reports every level separately, not only the
            highest reached. The levels are cumulative, so a level can be
            satisfied and still not count because something below it is not met,
            and hiding that was a real defect in this validator until September
            2026: a system with a genuine hash chain and no actuation gate was
            told it had reached TR-2 and never told its integrity had passed.
          </p>
          <p>
            Below the verdict, the record itself. Beliefs resolve to the
            evidence under them, so you can see what each one rests on rather
            than taking it on trust. A belief supported by nothing says so
            rather than being quietly dropped, because a system that cannot
            express &ldquo;believed, and nothing supports it&rdquo; will
            eventually invent support.
          </p>
          <p>
            Disagreements are drawn as pairs. Both sides of a contradiction are
            retained in a conforming record, and putting them side by side is
            the part an ordinary log cannot do for you: two rows that disagree
            look like two rows unless something says they are about the same
            claim.
          </p>

          <h2>If you do not have a record</h2>
          <p>
            The{" "}
            <a href="/spec/testimony-record/emitting">emitting guide</a> works
            through producing one from an ordinary two-table store in about
            forty lines, with no dependency on anything. The{" "}
            <a href="/testimony-record-example.jsonl">published example</a> is a
            conforming record you can drop straight in to see what the viewer
            does with it.
          </p>

          <h2>The same checks, elsewhere</h2>
          <p>
            This runs a TypeScript port of the reference validator. The two are
            held to agreement by a test that runs both over the same records,
            valid and invalid, and fails on any difference in the level, the
            scope, or any individual check. Two validators that disagree are
            worse than one, because a conformance claim then depends on which
            one you happened to run.
          </p>
          <p>
            If you would rather not trust a page, the reference validator is one
            standard library file with no network calls. Copy it into your own
            repository and run it there, which is the point of it being that
            small.
          </p>
        </article>
      </Section>
    </MarketingShell>
  );
}
