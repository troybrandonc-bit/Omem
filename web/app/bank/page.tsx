"use client";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { useApp } from "@/components/providers";
import { Skeleton } from "@/components/ui/primitives";
import { Landmark, Download, FileText, ShieldCheck, HardDriveDownload, Users, Layers, Activity, BrainCircuit } from "lucide-react";

/* The commons bank: the creator's instrument, not a product page.
 *
 * A stock OMEM install has no bank. This page exists only on the collector
 * instance (OMEM_BANK_COLLECTOR=1), reads only for its owner, and pools the
 * anonymous regularities contributed by installs whose operators chose to
 * send them (OMEM_COMMONS_URL, off by default, forever).
 *
 * The point of the pool: give AI a better understanding of human nature and
 * behaviour without holding a single fact about a person. Counts over
 * populations, refused at both doors if a token could carry a name, an id,
 * or a value. That is why the exports publish as-is. */

function humanize(p: string): string {
  return p.replace(/^not:/, "not ").replace(/_/g, " ");
}
function download(name: string, text: string, type: string) {
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([text], { type }));
  a.download = name;
  a.click();
  URL.revokeObjectURL(a.href);
}

export default function Bank() {
  const { collector } = useApp();
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["bank"], queryFn: () => api.bank(), retry: false, enabled: collector });

  if (!collector) {
    return (
      <div className="mx-auto max-w-2xl">
        <h1 className="display text-2xl">Intelligence bank</h1>
        <p className="mt-3 text-sm leading-relaxed text-muted">
          This install is not the commons collector, so there is no bank here.
          The bank lives on the one instance the OMEM project runs; installs
          that want to contribute their anonymous patterns do so only when
          their operator sets <span className="mono text-2xs text-fg">OMEM_COMMONS_URL</span> themselves.
          Nothing is ever sent otherwise.
        </p>
      </div>
    );
  }
  if (isLoading) return <div className="space-y-5"><Skeleton className="h-40" /><Skeleton className="h-64" /></div>;
  if (isError || !data) {
    return (
      <div className="mx-auto max-w-2xl">
        <h1 className="display text-2xl">Intelligence bank</h1>
        <p className="mt-3 text-sm text-muted">
          {error instanceof Error && /owner|permission|403/i.test(error.message)
            ? "The bank reads only for this instance's owner, from a signed-in session."
            : "Could not read the bank."}
        </p>
      </div>
    );
  }
  const pct = (n: number) => `${Math.round(n * 100)}%`;
  const a = data.analytics;
  const last = data.failsafe.last_backup?.last_successful?.finished;
  const maxWeek = Math.max(1, ...a.timeline.map(t => t.contributions));

  return (
    <div className="mx-auto max-w-4xl space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="display text-2xl">Intelligence bank</h1>
          <p className="mt-1 max-w-2xl text-sm text-muted">
            What OMEM has learned about human behaviour in general, pooled from
            your projects and from every install that chose to contribute. Only
            you can read this page, and nothing on it can name a person, a
            company, or a price, which is what makes the exports publishable
            as they are.
          </p>
        </div>
        <div className="flex shrink-0 gap-2">
          <button onClick={() => download("intelligence-bank.md", data.markdown, "text/markdown")}
            className="tap inline-flex h-8 items-center gap-1.5 rounded border border-[color:var(--line-strong)] bg-panel px-3 text-xs font-medium hover:bg-raised">
            <FileText className="h-3.5 w-3.5" /> Markdown
          </button>
          <button onClick={() => download("intelligence-bank.json",
              JSON.stringify({ patterns: data.patterns, note: data.note }, null, 1), "application/json")}
            className="tap inline-flex h-8 items-center gap-1.5 rounded border border-[color:var(--line-strong)] bg-panel px-3 text-xs font-medium hover:bg-raised">
            <Download className="h-3.5 w-3.5" /> JSON
          </button>
        </div>
      </div>

      {/* Analytics: how much human regularity the commons holds, from where. */}
      <section className="grid grid-cols-2 gap-2 lg:grid-cols-4">
        {[[Users, "Contributing installs", String(a.contributors + 1), "yours included"],
          [Layers, "Patterns held", String(a.patterns), `${a.strong} at 80% or stronger`],
          [Activity, "Stances counted", String(a.stances), "one per subject per pattern"],
          [Landmark, "Behaviour areas", String(Object.keys(a.categories).length),
            Object.entries(a.categories).slice(0, 2).map(([k, v]) => `${k} ${v}`).join(" · ") || "none yet"],
        ].map(([Icon, label, value, sub]: any) => (
          <div key={label} className="panel px-4 py-3">
            <div className="flex items-center gap-1.5 text-2xs text-faint"><Icon className="h-3 w-3" />{label}</div>
            <div className="num mt-1 text-xl leading-none">{value}</div>
            <div className="mt-1 text-2xs text-faint">{sub}</div>
          </div>
        ))}
      </section>

      {a.timeline.length > 0 && (
        <section className="panel overflow-hidden">
          <header className="border-b px-4 py-2.5"><h2 className="text-sm font-semibold">Contributions over time</h2></header>
          <div className="flex items-end gap-1.5 px-4 py-4" style={{ height: 96 }}>
            {a.timeline.map(t => (
              <div key={t.week} className="flex flex-col items-center gap-1" title={`${t.week}: ${t.contributions}`}>
                <div className="w-6 rounded-sm"
                  style={{ height: Math.max(4, (t.contributions / maxWeek) * 56),
                           background: "var(--accent)", opacity: 0.75 }} />
                <span className="text-[9px] text-faint">{t.week.slice(5)}</span>
              </div>
            ))}
          </div>
        </section>
      )}

      <section className="panel overflow-hidden">
        <header className="flex items-center gap-2 border-b px-4 py-2.5">
          <Landmark className="h-3.5 w-3.5 text-amber-500" />
          <h2 className="text-sm font-semibold">Learned patterns</h2>
          <span className="text-2xs text-faint">{data.patterns.length} on record, largest populations first</span>
        </header>
        <div className="divide-y">
          {data.patterns.length === 0 &&
            <div className="empty m-5">Nothing banked yet. Patterns arrive when a regularity repeats across enough subjects, here or in a contributing install.</div>}
          {data.patterns.map(p => {
            const denom = p.support + p.refute;
            return (
              <div key={p.pattern} className="flex items-center justify-between gap-4 px-4 py-3">
                <div className="text-sm">
                  <span className="font-medium">{humanize(p.antecedent)}</span>
                  <span className="text-faint"> → usually </span>
                  <span className="font-medium">{humanize(p.consequent)}</span>
                </div>
                <div className="flex shrink-0 items-center gap-2.5">
                  <div className="h-1.5 w-16 rounded-sm bg-chip">
                    <div className="h-1.5 rounded-sm bg-amber-500" style={{ width: pct(p.rate) }} />
                  </div>
                  <span className="num w-32 text-right text-2xs text-muted">
                    {pct(p.rate)} of {denom}{p.sources > 1 && ` · ${p.sources} installs`}
                  </span>
                </div>
              </div>
            );
          })}
        </div>
      </section>

      <TrainingDataset />

      <section className="panel overflow-hidden">
        <header className="flex items-center gap-2 border-b px-4 py-2.5">
          <HardDriveDownload className="h-3.5 w-3.5 text-believed" />
          <h2 className="text-sm font-semibold">Failsafe</h2>
          <span className="text-2xs text-faint">what happens if this machine is lost</span>
        </header>
        <div className="space-y-2.5 px-4 py-3.5 text-sm text-muted">
          <p className="flex items-start gap-2">
            <ShieldCheck className="mt-0.5 h-3.5 w-3.5 shrink-0 text-believed" />
            <span>
              A copy of this bank ({data.failsafe.bank_file_written ? "already written" : "written on the next backup run"})
              rides every database backup, in{" "}
              <span className="mono text-2xs text-fg">{data.failsafe.backup_dir}</span>
              {last ? <> — last backup {new Date(last * 1000).toLocaleString()}.</> : <> — no backup has completed yet.</>}
            </span>
          </p>
          <p>
            Point that directory at a synced or mounted volume (OneDrive, Dropbox,
            a NAS: set <span className="mono text-2xs text-fg">OMEM_BACKUP_DIR</span>) and losing this
            laptop loses neither your data nor this bank. The downloads above are
            the manual version of the same failsafe — the file is anonymous, so a
            copy anywhere leaks nothing.
          </p>
        </div>
      </section>
    </div>
  );
}

/* The commons offered as a training corpus. Same anonymous rows, shaped for
 * machines: JSONL with a natural-language rendering per line, and a dataset
 * card carrying provenance, consent, and license, so a lab can use it
 * responsibly without a single email back and forth. The public endpoint is
 * off until the creator flips OMEM_COMMONS_DATASET_PUBLIC=1. */
function TrainingDataset() {
  const { data } = useQuery({ queryKey: ["commons-dataset"], queryFn: api.commonsDataset, retry: false });
  if (!data) return null;
  return (
    <section className="panel overflow-hidden">
      <header className="flex items-center gap-2 border-b px-4 py-2.5">
        <BrainCircuit className="h-3.5 w-3.5 text-violet-500" />
        <h2 className="text-sm font-semibold">For AI training</h2>
        <span className="text-2xs text-faint">{data.patterns} patterns · {data.license}</span>
      </header>
      <div className="space-y-3 px-4 py-3.5 text-sm text-muted">
        <p>
          The same corpus, shaped for models: one JSON line per pattern with the
          counts and a plain-English rendering, plus a dataset card that carries
          the provenance, the consent story, and the license, so a lab can train
          on human behavioural priors responsibly. Publish it anywhere, or flip{" "}
          <span className="mono text-2xs text-fg">OMEM_COMMONS_DATASET_PUBLIC=1</span> to
          serve it live at <span className="mono text-2xs text-fg">/v1/commons/dataset</span>
          {data.public ? " (currently on)" : " (currently off)"}.
        </p>
        <div className="flex gap-2">
          <button onClick={() => download("omem-commons.jsonl", data.jsonl, "application/x-ndjson")}
            className="tap inline-flex h-8 items-center gap-1.5 rounded border border-[color:var(--line-strong)] bg-panel px-3 text-xs font-medium hover:bg-raised">
            <Download className="h-3.5 w-3.5" /> Training JSONL
          </button>
          <button onClick={() => download("omem-commons-dataset-card.md", data.card, "text/markdown")}
            className="tap inline-flex h-8 items-center gap-1.5 rounded border border-[color:var(--line-strong)] bg-panel px-3 text-xs font-medium hover:bg-raised">
            <FileText className="h-3.5 w-3.5" /> Dataset card
          </button>
        </div>
      </div>
    </section>
  );
}
