"use client";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { api, isGrounded } from "@/lib/api";
import { useApp } from "@/components/providers";
import { Skeleton, EmptyState } from "@/components/ui/primitives";
import { ShieldCheck } from "lucide-react";

// Two incompatible beliefs, side by side. The layout is the argument:
// claim A versus claim B, each carrying its own agent, time, and evidence.
export default function Conflicts() {
  const { project, asOf } = useApp();
  const { data, isLoading } = useQuery({ queryKey: ["conflicts", project, asOf], queryFn: () => api.conflicts(project, asOf ?? "now") });

  return (
    <div className="mx-auto max-w-4xl">
      <h1 className="mb-1 display text-[21px]">Conflicts</h1>
      <p className="mb-6 max-w-lg text-[13px] text-muted">
        Your AI holds incompatible beliefs about the same thing. OMEM records both sides and
        marks the proposition CONTRADICTED. It never silently picks a winner.
      </p>
      {isLoading ? <Skeleton className="h-40" /> :
        !data || data.conflicts.length === 0 ?
          <EmptyState icon={ShieldCheck} title="No conflicts" body="Every proposition has a consistent belief state at this point in time." /> :
          <div className="space-y-5">
            {data.conflicts.map((c, i) => (
              <div key={i} className="overflow-hidden rounded-lg border">
                <div className="flex items-center justify-between border-b bg-[color:var(--conflict)]/[0.05] px-4 py-2">
                  <span className="text-xs font-medium text-conflict">CONTRADICTED</span>
                  <span className="text-2xs text-faint">referent-level conflict</span>
                </div>
                <div className="relative grid md:grid-cols-2">
                  {c.pair.map((a, j) => (
                    <Link key={a.id} href={`/assertion?id=${encodeURIComponent(a.id)}`}
                      className={`group p-5 transition-colors hover:bg-panel ${j === 0 ? "border-b md:border-b-0 md:border-r" : ""}`}>
                      <div className="text-[15px] leading-snug group-hover:text-accent">{a.label || a.proposition}</div>
                      <div className="mt-1 text-2xs text-muted">{a.proposition}</div>
                      <dl className="mt-4 space-y-1 text-2xs text-muted">
                        <div className="flex gap-2"><dt className="w-14">agent</dt><dd className="mono text-fg/80">{a.agent}</dd></div>
                        <div className="flex gap-2"><dt className="w-14">asserted</dt><dd className="mono text-fg/80">t={a.assertion_time}</dd></div>
                        <div className="flex gap-2"><dt className="w-14">evidence</dt>
                          <dd className={isGrounded(a.grounded) ? "font-medium text-believed" : "text-unknown"}>
                            {isGrounded(a.grounded) ? "grounded" : "ungrounded"}</dd></div>
                      </dl>
                    </Link>
                  ))}
                  <span aria-hidden
                    className="absolute left-1/2 top-1/2 hidden -translate-x-1/2 -translate-y-1/2 rounded-full border bg-bg px-2 py-0.5 text-2xs font-medium text-muted md:block">
                    vs
                  </span>
                </div>
              </div>
            ))}
          </div>}
    </div>
  );
}
