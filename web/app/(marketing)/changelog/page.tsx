import { MarketingShell } from "@/components/marketing/chrome";
import { Section, PageHeader } from "@/components/marketing/ui";
import { CircleCheck, Circle } from "lucide-react";

export const metadata = {
  title: "Changelog",
  description: "Product updates, shipped. The OMEM standard is versioned separately.",
};

/* A changelog is a record, so it is set like one: a dated left rail, a rule per
 * entry, and the version as a machine value in mono. The previous version put
 * the date and the version in the label column and the entries in the body,
 * which was right — what it did not do was mark WHICH entry is current, and it
 * set its own heading two steps larger than every other page on the site. */

const ENTRIES = [
  { date: "2026-08", version: "v1.0", tag: "Stable", current: true,
    title: "The OMEM standard reaches 1.0",
    items: [
      "The engine is frozen at 1.0 and replays byte-identically, so an upgrade never rewrites your past.",
      "The full memory model, self-hosted and multi-tenant, with as-of time travel on every query.",
      "Dashboard: memory explorer, provenance viewer, timeline, conflict viewer, memory graph, live inspector.",
      "Python and TypeScript SDKs against the embedded engine.",
      "Playground with real API calls and multi-language code generation.",
    ]},
  { date: "2026-07", version: "v0.9", tag: "Beta",
    title: "Contradiction detection and the “why” view",
    items: [
      "Conflicting claims now resolve to a first-class CONTRADICTED state instead of overwriting.",
      "The belief-inspection view ties state, provenance, contradictions, and revisions together.",
      "Reason codes surface verbatim in API errors, each with a documentation link.",
    ]},
  { date: "2026-06", version: "v0.8", tag: "Preview",
    title: "Time-travel debugging",
    items: [
      "A replay control re-renders every view as memory stood at time T.",
      "Deterministic replay backed by the append-only log.",
      "Revision chains with canonical ordering.",
    ]},
];

export default function Changelog() {
  return (
    <MarketingShell>
      <Section className="page-y">
        <PageHeader eyebrow="Changelog" title="What&rsquo;s new in OMEM">
          Product updates, shipped. The underlying OMEM standard stays frozen and
          is versioned separately.
        </PageHeader>
      </Section>

      <Section className="pb-24 sm:pb-32">
        <ol className="border-t">
          {ENTRIES.map(e => (
            <li key={e.version} className="spec-row border-b py-8">
              <div className="flex flex-row items-center gap-3 sm:flex-col sm:items-start sm:gap-1">
                <time className="mono text-note font-medium text-fg" dateTime={e.date}>{e.date}</time>
                <div className="flex items-center gap-2">
                  <span className="mono text-caption text-muted">{e.version}</span>
                  {/* The tag is state, so it gets a mark and not only a word.
                      "Current" is the one thing a reader scans this page for. */}
                  <span className={`chip ${e.current ? "text-fg" : ""}`}>
                    {e.current
                      ? <CircleCheck className="h-3.5 w-3.5 shrink-0 text-believed" aria-hidden="true" />
                      : <Circle className="h-3.5 w-3.5 shrink-0 text-faint" aria-hidden="true" />}
                    {e.tag}
                  </span>
                </div>
              </div>
              <div>
                <h2 className="display text-lg">{e.title}</h2>
                <ul className="mt-4 space-y-2.5">
                  {e.items.map((it, j) => (
                    <li key={j} className="flex gap-3 text-note text-muted">
                      <span aria-hidden="true" className="mt-[11px] h-px w-3 shrink-0" style={{ background: "var(--line-strong)" }} />
                      <span className="min-w-0">{it}</span>
                    </li>
                  ))}
                </ul>
              </div>
            </li>
          ))}
        </ol>
      </Section>
    </MarketingShell>
  );
}
