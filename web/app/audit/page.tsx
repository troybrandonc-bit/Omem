"use client";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { Skeleton } from "@/components/ui/primitives";

// Immutable audit trail from the backend. Admin+ only (403 otherwise).
export default function Audit() {
  const { data, error } = useQuery({ queryKey: ["audit"], queryFn: api.auditLog, retry: false });
  if (error) return <div className="panel m-1 p-6 text-sm text-muted">Audit log requires an admin or owner role.</div>;
  if (!data) return <Skeleton className="h-64" />;

  return (
    <div className="space-y-5">
      <h1 className="display text-lg">Audit log</h1>
      <section className="panel overflow-hidden">
        <header className="border-b px-4 py-2.5"><h2 className="text-sm font-semibold">Security events</h2></header>
        {data.data.length === 0 ? <div className="empty m-5">No audit events yet.</div> : (
          <div className="divide-y">
            {data.data.map(e => (
              <div key={e.id} className="grid grid-cols-[1fr_auto] gap-2 px-4 py-2.5">
                <div>
                  <span className="text-sm font-semibold">{e.action}</span>
                  {e.resource && <span className="ml-2 text-2xs text-muted">{e.resource}</span>}
                  <div className="text-2xs text-faint">{e.actor ?? "system"}</div>
                </div>
                <div className="num text-right text-2xs text-faint">{new Date(e.ts * 1000).toLocaleString()}</div>
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
