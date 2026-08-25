import { CodeBlock, ButtonLink } from "@/components/marketing/ui";
import { ArrowRight } from "lucide-react";

export const metadata = {
  title: "Quickstart",
  description: "Store a belief, query it, and see why it is believed. Five minutes.",
};

/* Every sample below is the real API, copied from a working call. This page
 * used to document a product that does not exist: `pip install omem` (the
 * package is omem-infrastructure), `omem.Client()` and `Client(embedded=True)`
 * (neither exists — the SDK is Memory(), and it talks to a server over HTTP),
 * and mem.entity()/mem.event() constructors that were never written. Someone
 * following it got an ImportError on line one. CONTRIBUTING.md rule 4 says
 * nothing displayed may be fabricated; that applies to the docs, not just to
 * the dashboard's numbers.
 */
const STEPS = [
  { title: "Install and start the server", body: "One package, no dependencies. Or run it straight from a clone — same server, same port, same first-run key. From source the dashboard needs building once (cd web && OMEM_STATIC=1 npm run build); in the wheel it is already bundled.",
    code: [
      { label: "From PyPI", code: `pip install omem-infrastructure\nomem-server            # or: omem-server 9000` },
      { label: "From source", code: `cd server\npython api.py          # or: python api.py 9000` },
    ] },
  { title: "Create a client", body: "The first run prints a project id and an API key. There is no signup call and nothing to configure — paste them straight in.",
    code: [{ label: "Python", code: `from omem import Memory\n\nmem = Memory(api_key="omem_sk_...",\n             base_url="http://127.0.0.1:8787",\n             project="proj_...")` }] },
  { title: "Remember a belief", body: "`about` is any entity id you choose. `claim` is a token, not a sentence — OMEM normalises spelling, so three spellings of one claim stay one claim.",
    code: [{ label: "Python", code: `mem.remember(agent="support-bot",\n             about="customer:alice",\n             claim="prefers_annual_billing")` }] },
  { title: "Query what it believes", body: "Returns a four-valued state: BELIEVED_TRUE, BELIEVED_FALSE, CONTRADICTED, or UNKNOWN.",
    code: [{ label: "Python", code: `mem.believes(about="customer:alice",\n             claim="prefers_annual_billing")\n# -> 'BELIEVED_TRUE'` }] },
  { title: "Contradict yourself", body: "The part a vector store cannot do. Tell OMEM two claims disagree, then assert the second one. Nothing is overwritten and nothing is lost.",
    code: [{ label: "Python", code: `mem.contradict("prefers_annual_billing",\n               "prefers_monthly_billing")\n\nmem.remember(agent="sales", about="customer:alice",\n             claim="prefers_monthly_billing")\n\nmem.believes(about="customer:alice",\n             claim="prefers_annual_billing")\n# -> 'CONTRADICTED'` }] },
  { title: "Ask why", body: "Both claims are still on record. Pass an assertion id to get the chain that led there — which agent said it, when, and on what basis.",
    code: [{ label: "Python", code: `beliefs = mem.about("customer:alice")\n\nmem.why(beliefs[0]["id"])\n# -> {'state': ..., 'provenance': [...]}` }] },
];

/* The step list was `<li className="relative border-l pl-8">` with an absolutely
 * positioned number sitting on the rule. Two problems it had: the number was
 * `-left-[13px]` on a 1px border, so at any browser zoom other than 100% the
 * circle drifted off the line; and on a phone the 32px of left padding came
 * straight out of an already narrow measure. It is a grid now — the rule and the
 * number are laid out rather than nudged, and the whole rail collapses on small
 * screens instead of eating the text column.
 */

export default function Quickstart() {
  return (
    <article className="max-w-read">
      <div className="tech-label mb-3">Quickstart</div>
      <h1 className="display text-2xl">Your first memory in five minutes</h1>
      <p className="lede mt-4">
        Store a belief, query it, and see why it&rsquo;s believed. Every snippet
        below is real and runs against the same API the dashboard uses.
      </p>

      <ol className="mt-12 space-y-12">
        {STEPS.map((s, i) => (
          <li key={i} className="grid gap-x-5 gap-y-3 sm:grid-cols-[28px_minmax(0,1fr)]">
            <div className="flex items-center gap-3 sm:block">
              <span aria-hidden="true"
                className="mono grid h-7 w-7 shrink-0 place-items-center rounded-full border text-2xs font-semibold">
                {i + 1}
              </span>
              <h2 className="text-lede font-semibold sm:hidden">{s.title}</h2>
            </div>
            <div className="min-w-0">
              <h2 className="hidden text-lede font-semibold sm:block">
                <span className="sr-only">Step {i + 1}: </span>{s.title}
              </h2>
              <p className="mt-2 max-w-read text-note text-muted">{s.body}</p>
              <div className="mt-4"><CodeBlock tabs={s.code} label={s.title} /></div>
            </div>
          </li>
        ))}
      </ol>

      <div className="mt-16 border-t pt-8">
        <h2 className="text-lede font-semibold">See it in the dashboard</h2>
        <p className="mt-2 max-w-read text-note text-muted">
          Your belief appears live in the memory explorer. Open the &ldquo;why&rdquo;
          view to trace its provenance and scrub through time. Both need
          <span className="mono"> omem-server</span> running locally.
        </p>
        <div className="mt-5 flex flex-wrap gap-3">
          <ButtonLink href="/overview">
            Open dashboard <ArrowRight className="h-4 w-4" aria-hidden="true" />
          </ButtonLink>
          <ButtonLink href="/playground" variant="secondary">Playground</ButtonLink>
        </div>
      </div>
    </article>
  );
}
