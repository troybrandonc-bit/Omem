"use client";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { Skeleton } from "@/components/ui/primitives";
import { Landmark, Download, FileText, ShieldCheck, HardDriveDownload } from "lucide-react";

/* The joint intelligence bank.
 *
 * Everything OMEM has learned about subjects IN GENERAL, merged across every
 * project the signed-in owner has -- and nothing else. Owner-only on the
 * server (bank.read), session-only (an API key is project-scoped and cannot
 * read across projects). The content is anonymous by construction: a pattern
 * is counts over a population, and any token that could embed a name, id, or
 * value is refused before it ever reaches this page. That is what makes the
 * export publishable without a redaction pass.
 *
 * The failsafe: the same export is written beside the database backups on
 * every backup run. Point the backup directory at a synced or mounted volume
 * and losing this machine loses neither the data nor the bank. */

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
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["bank"], queryFn: () => api.bank(), retry: false });

  if (isLoading) return <div className="space-y-5"><Skeleton className="h-40" /><Skeleton className="h-64" /></div>;
  if (isError || !data) {
    return (
      <div className="mx-auto max-w-2xl">
        <h1 className="display text-2xl">Intelligence bank</h1>
        <p className="mt-3 text-sm text-muted">
          {error instanceof Error && /owner|permission|403/i.test(error.message)
            ? "The bank is only readable by the org owner, from a signed-in session. You are signed in as a member without the owner role."
            : "Could not read the bank."}
        </p>
      </div>
    );
  }
  const pct = (n: number) => `${Math.round(n * 100)}%`;
  const last = data.failsafe.last_backup?.last_successful?.finished;

  return (
    <div className="mx-auto max-w-4xl space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="display text-2xl">Intelligence bank</h1>
          <p className="mt-1 max-w-2xl text-sm text-muted">
            Everything OMEM has learned about subjects in general, pooled from
            your {data.projects === 1 ? "project" : `${data.projects} projects`}. Only you can read this
            page. Every row is a count over a population — nothing here can name
            a person, a company, or a price — so the export publishes as-is.
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

      <section className="panel overflow-hidden">
        <header className="flex items-center gap-2 border-b px-4 py-2.5">
          <Landmark className="h-3.5 w-3.5 text-amber-500" />
          <h2 className="text-sm font-semibold">Learned patterns</h2>
          <span className="text-2xs text-faint">{data.patterns.length} on record</span>
        </header>
        <div className="divide-y">
          {data.patterns.length === 0 &&
            <div className="empty m-5">Nothing banked yet. Patterns arrive once a regularity repeats across enough subjects in any of your projects.</div>}
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
                  <span className="num w-28 text-right text-2xs text-muted">
                    {pct(p.rate)} of {denom}{data.projects > 1 && ` · ${p.projects} proj`}
                  </span>
                </div>
              </div>
            );
          })}
        </div>
      </section>

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
