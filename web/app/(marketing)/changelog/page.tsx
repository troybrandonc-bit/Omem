import { MarketingShell } from "@/components/marketing/chrome";
import { Section } from "@/components/marketing/ui";

export const metadata = { title: "Changelog / OMEM Cloud" };

const ENTRIES = [
  { date: "2026-08", version: "v1.0", tag: "GA",
    title: "OMEM Cloud is generally available",
    items: [
      "The full memory model, hosted and multi-tenant, with as-of time travel on every query.",
      "Dashboard: memory explorer, provenance viewer, timeline, conflict viewer, memory graph, live inspector.",
      "Python and TypeScript SDKs, CTS-gated with the embedded engine.",
      "Playground with real API calls and multi-language code generation.",
    ]},
  { date: "2026-07", version: "v0.9", tag: "Beta",
    title: "Contradiction detection and the \"why\" view",
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
      <Section className="pt-20 pb-14">
        <div className="tech-label mb-4">Changelog</div>
        <h1 className="display max-w-xl text-[40px]">What&apos;s new in OMEM Cloud</h1>
        <p className="mt-5 max-w-lg text-[15px] leading-relaxed text-muted">
          Product updates, shipped. The underlying OMEM standard stays frozen and is versioned separately.
        </p>
      </Section>

      <Section className="pb-8">
        <div className="border-t">
          {ENTRIES.map(e => (
            <div key={e.version} className="spec-row border-b py-8">
              <div>
                <div className="num text-xs">{e.date}</div>
                <div className="num mt-1 text-2xs text-muted">{e.version} / {e.tag}</div>
              </div>
              <div>
                <h2 className="text-[17px] font-medium tracking-tight">{e.title}</h2>
                <ul className="mt-3 space-y-2">
                  {e.items.map((it, j) => (
                    <li key={j} className="flex gap-2.5 text-[14px] leading-relaxed text-muted">
                      <span className="mt-0.5 text-border">·</span> {it}
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          ))}
        </div>
      </Section>
    </MarketingShell>
  );
}
