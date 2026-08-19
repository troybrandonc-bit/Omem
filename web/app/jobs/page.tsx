"use client";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { useApp } from "@/components/providers";
import { Skeleton } from "@/components/ui/primitives";
import { cn } from "@/lib/cn";

// Real job records from the durable ingest_jobs table. States and counts are live.
const STATE_TONE: Record<string, string> = {
  pending: "text-muted", running: "text-accent", completed: "text-believed",
  retrying: "text-unknown", dead_lettered: "text-conflict", cancelled: "text-faint",
};

export default function Jobs() {
  const { project } = useApp();
  const qc = useQueryClient();
  const { data: stats } = useQuery({ queryKey: ["ingest-stats", project], queryFn: () => api.ingestStats(project), refetchInterval: 4000 });
  const { data: jobs } = useQuery({ queryKey: ["jobs", project], queryFn: () => api.jobs(project), refetchInterval: 4000 });

  async function cancel(id: number) {
    await api.cancelJob(project, id);
    qc.invalidateQueries({ queryKey: ["jobs", project] });
    qc.invalidateQueries({ queryKey: ["ingest-stats", project] });
  }

  return (
    <div className="space-y-5">
      <h1 className="display text-[24px]">Jobs</h1>

      <section className="panel overflow-hidden">
        <header className="border-b px-4 py-2.5"><h2 className="text-[14px] font-semibold">Queue</h2></header>
        {!stats ? <div className="p-5"><Skeleton className="h-12" /></div> : (
          <div className="grid grid-cols-3 divide-x divide-y sm:grid-cols-6 sm:divide-y-0">
            {[["Pending", stats.pending], ["Running", stats.running], ["Completed", stats.completed],
              ["Retrying", stats.retrying], ["Dead-letter", stats.dead], ["Cancelled", stats.cancelled]].map(([l, v]) => (
              <div key={l as string} className="px-4 py-3">
                <div className="text-2xs text-faint">{l}</div>
                <div className="num mt-1 text-[20px] leading-none">{v as number}</div>
              </div>
            ))}
          </div>
        )}
      </section>

      <section className="panel overflow-hidden">
        <header className="border-b px-4 py-2.5"><h2 className="text-[14px] font-semibold">Recent jobs</h2></header>
        {!jobs ? <div className="p-5"><Skeleton className="h-32" /></div> : jobs.data.length === 0 ? (
          <div className="empty m-5">No jobs yet. Connect a source and sync to enqueue work.</div>
        ) : (
          <div className="divide-y">
            {jobs.data.map(j => (
              <div key={j.id} className="flex items-center gap-4 px-4 py-2.5">
                <span className="num w-10 text-2xs text-faint">#{j.id}</span>
                <span className={cn("w-24 text-2xs font-semibold uppercase tracking-[0.04em]", STATE_TONE[j.state] ?? "text-muted")}>
                  {j.state.replace("_", " ")}
                </span>
                <span className="flex-1 truncate text-2xs text-muted">
                  {j.last_error ? j.last_error : j.connector_id}
                </span>
                <span className="num text-2xs text-faint">{j.attempts} attempt{j.attempts === 1 ? "" : "s"}</span>
                {["pending", "retrying"].includes(j.state) && (
                  <button onClick={() => cancel(j.id)} className="text-2xs font-medium text-conflict hover:underline">Cancel</button>
                )}
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
