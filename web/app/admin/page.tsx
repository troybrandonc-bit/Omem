"use client";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { useQueryClient } from "@tanstack/react-query";
import { Skeleton } from "@/components/ui/primitives";

// INTERNAL operator console (not customer-facing). Access requires the signed-in
// email to be listed in OMEM_ADMIN_EMAILS on the server; everyone else gets 403.
// Every number is a real database count; MRR is honestly labeled an estimate.
const STATUSES = ["pilot", "trial", "paid", "cancelled"];

export default function Admin() {
  const qc = useQueryClient();
  async function setStatus(orgId: string, status: string) {
    await api.setCustomerStatus(orgId, { status });
    qc.invalidateQueries({ queryKey: ["admin-orgs"] });
  }
  const { data, error } = useQuery({ queryKey: ["admin-metrics"], queryFn: api.adminMetrics, retry: false, refetchInterval: 5000 });
  const { data: orgs } = useQuery({ queryKey: ["admin-orgs"], queryFn: api.adminOrgs, retry: false, refetchInterval: 10000 });

  if (error) return <div className="panel m-1 p-6 text-sm text-muted">Operator access only. Your account is not listed in OMEM_ADMIN_EMAILS.</div>;
  if (!data) return <Skeleton className="h-64" />;

  const CELLS: [string, number | string][] = [
    ["Organizations", data.organizations], ["Users", data.users], ["Projects", data.projects],
    ["API requests", data.api_requests], ["Assertions", data.assertions_created], ["Recalls", data.recalls],
    ["Learn calls", data.learn_calls], ["Sources", data.connected_sources], ["Source records", data.source_records],
    ["Audit events", data.audit_events], ["DB size", fmtBytes(data.db_bytes)], ["Est. MRR", `$${data.estimated_mrr}`],
  ];

  return (
    <div className="space-y-5">
      <div className="flex items-baseline justify-between">
        <h1 className="display text-lg">Operator console</h1>
        <span className="text-sm text-muted">Internal. All counts live from the database.</span>
      </div>

      <section className="panel overflow-hidden">
        <div className="grid grid-cols-2 divide-x divide-y sm:grid-cols-4 lg:grid-cols-6">
          {CELLS.map(([l, v]) => (
            <div key={l} className="px-4 py-3">
              <div className="text-2xs text-faint">{l}</div>
              <div className="num mt-1 text-lg leading-none">{v}</div>
            </div>
          ))}
        </div>
        <div className="border-t px-4 py-2 text-2xs text-muted">{data.revenue_note}</div>
      </section>

      <section className="panel overflow-hidden">
        <header className="border-b px-4 py-2.5"><h2 className="text-sm font-semibold">Job queue (all tenants)</h2></header>
        <div className="grid grid-cols-3 divide-x divide-y sm:grid-cols-6 sm:divide-y-0">
          {Object.entries(data.jobs).map(([st, n]) => (
            <div key={st} className="px-4 py-2.5.5">
              <div className="text-2xs text-faint">{st.replace("_", " ")}</div>
              <div className="num mt-1 text-md leading-none">{n}</div>
            </div>
          ))}
        </div>
      </section>

      <BackupPanel />

      <section className="panel overflow-hidden">
        <header className="border-b px-4 py-2.5"><h2 className="text-sm font-semibold">Customers</h2></header>
        {!orgs ? <div className="p-5"><Skeleton className="h-24" /></div> : orgs.data.length === 0 ? (
          <div className="empty m-5">No organizations yet.</div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b text-left text-2xs text-muted">
                <th className="px-4 py-2 font-medium">Organization</th>
                <th className="px-3 py-2.5 font-medium">Plan</th>
                <th className="px-3 py-2.5 font-medium">Status</th>
                <th className="px-3 py-2.5 text-right font-medium">Projects</th>
                <th className="px-3 py-2.5 text-right font-medium">Members</th>
                <th className="px-3 py-2.5 text-right font-medium">Usage events</th>
                <th className="px-4 py-2 text-right font-medium">Last activity</th>
              </tr>
            </thead>
            <tbody className="divide-y">
              {orgs.data.map(o => (
                <tr key={o.id}>
                  <td className="px-4 py-2 font-medium">{o.name || o.id}</td>
                  <td className="px-3 py-2.5"><span className="rounded-sm border border-line-strong px-2 py-px text-2xs font-semibold uppercase text-muted">{o.plan}</span></td>
                  <td className="px-3 py-2.5">
                    <select value={o.customer.status} onChange={e => setStatus(o.id, e.target.value)}
                      className="rounded-md border bg-panel px-1.5 py-0.5 text-2xs font-semibold uppercase">
                      {STATUSES.map(s_ => <option key={s_} value={s_}>{s_}</option>)}
                    </select>
                  </td>
                  <td className="num px-3 py-2.5 text-right">{o.projects}</td>
                  <td className="num px-3 py-2.5 text-right">{o.members}</td>
                  <td className="num px-3 py-2.5 text-right">{o.usage_total}</td>
                  <td className="num px-4 py-2 text-right text-2xs text-faint">{o.last_activity ? new Date(o.last_activity * 1000).toLocaleString() : "-"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </div>
  );
}

function fmtBytes(b: number) {
  if (b > 1048576) return `${(b / 1048576).toFixed(1)} MB`;
  if (b > 1024) return `${(b / 1024).toFixed(0)} KB`;
  return `${b} B`;
}


function BackupPanel() {
  const qc = useQueryClient();
  const { data } = useQuery({ queryKey: ["backups"], queryFn: api.backupStatus, retry: false, refetchInterval: 15000 });
  if (!data) return null;
  return (
    <section className="panel overflow-hidden">
      <header className="flex items-center justify-between border-b px-4 py-2.5">
        <h2 className="text-sm font-semibold">Backups</h2>
        <button onClick={async () => { await api.runBackup(); qc.invalidateQueries({ queryKey: ["backups"] }); }}
          className="rounded-md border px-3 py-1.5 text-2xs font-semibold text-muted hover:border-line-strong">Run now</button>
      </header>
      <div className="grid grid-cols-2 divide-x sm:grid-cols-4">
        <div className="px-4 py-3">
          <div className="text-2xs text-faint">State</div>
          <div className={data.failing ? "mt-0.5 text-sm font-semibold text-conflict" : "mt-0.5 text-sm font-semibold text-believed"}>
            {data.failing ? "FAILING" : "Healthy"}
          </div>
          {data.failing && data.last_run?.error && <div className="mt-1 text-2xs text-conflict">{data.last_run.error}</div>}
        </div>
        <div className="px-4 py-3">
          <div className="text-2xs text-faint">Last successful</div>
          <div className="num mt-0.5 text-sm">{data.last_successful ? new Date(data.last_successful.started * 1000).toLocaleString() : "never"}</div>
        </div>
        <div className="px-4 py-3">
          <div className="text-2xs text-faint">Completed</div>
          <div className="num mt-1 text-lg leading-none">{data.completed_count}</div>
        </div>
        <div className="px-4 py-3">
          <div className="text-2xs text-faint">Retention</div>
          <div className="num mt-1 text-lg leading-none">{data.retain}</div>
        </div>
      </div>
    </section>
  );
}