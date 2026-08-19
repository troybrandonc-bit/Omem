"use client";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, setSession } from "@/lib/api";
import { useApp } from "@/components/providers";
import { Skeleton } from "@/components/ui/primitives";

export default function Settings() {
  const { project, theme, toggleTheme } = useApp();
  const { data, isLoading } = useQuery({ queryKey: ["projects"], queryFn: api.projects });
  const { data: me } = useQuery({ queryKey: ["me"], queryFn: api.me });
  const p = data?.data.find(x => x.id === project);

  return (
    <div className="mx-auto max-w-3xl">
      <section className="panel mb-6 overflow-hidden">
        <header className="flex items-center justify-between border-b px-4 py-2.5">
          <h2 className="text-[14px] font-semibold">Account</h2>
          <button onClick={() => { setSession(null); location.href = "/onboarding"; }}
            className="text-[13px] font-medium text-conflict hover:underline">Sign out</button>
        </header>
        <div className="grid grid-cols-2 gap-4 px-4 py-3 text-[13px]">
          <div><div className="text-2xs text-faint">Email</div><div className="mt-0.5 font-medium">{me?.email ?? "…"}</div></div>
          <div><div className="text-2xs text-faint">Organization</div><div className="mt-0.5 font-medium">{me?.org?.name ?? "…"}</div></div>
        </div>
      </section>

      <h1 className="mb-1 display text-[21px]">Settings</h1>
      <p className="mb-6 text-[13px] text-muted">Workspace configuration.</p>

      <div className="tech-label mb-3">Project</div>
      {isLoading || !p ? <Skeleton className="mb-8 h-28" /> : (
        <dl className="mb-8 overflow-hidden rounded-lg border">
          {[["Name", p.name], ["ID", p.id], ["Environment", p.env],
            ["Logical clock", `t=${p.now}`],
            ["Store", `${p.entities} entities / ${p.agents} agents / ${p.events} events / ${p.assertions} assertions`],
          ].map(([k, v], i, arr) => (
            <div key={k} className={`flex items-baseline justify-between gap-6 px-4 py-2.5 text-[13px] ${i < arr.length - 1 ? "border-b" : ""}`}>
              <dt className="text-muted">{k}</dt><dd className="mono text-right">{v}</dd>
            </div>
          ))}
        </dl>
      )}

      <div className="tech-label mb-3">Appearance</div>
      <div className="mb-8 flex items-center justify-between rounded-lg border px-4 py-3">
        <div>
          <div className="text-[14px]">Theme</div>
          <div className="text-2xs text-faint">Applies to the dashboard and site.</div>
        </div>
        <button onClick={toggleTheme}
          className="rounded-md border px-3 py-1.5 text-[13px] font-medium capitalize transition-colors hover:bg-panel">
          {theme} / switch
        </button>
      </div>

      <div className="tech-label mb-3">Organization</div>
      <div className="overflow-hidden rounded-lg border">
        <p className="px-4 py-3 text-[13px] leading-relaxed text-muted">
          Team members, roles, SSO, and API key management are part of the hosted product and
          are not wired in this build. The development key is visible on the
          {" "}<a href="/developers" className="text-accent hover:underline">API page</a>.
        </p>
      </div>
    
      <section className="panel overflow-hidden">
        <header className="border-b px-4 py-2.5"><h2 className="text-[14px] font-semibold">Extraction</h2></header>
        <ExtractionSettings />
      </section>

      <section className="panel mt-6 overflow-hidden">
        <header className="border-b px-4 py-2.5"><h2 className="text-[14px] font-semibold">Organization identity</h2></header>
        <IdentitySettings />
      </section>
    </div>
  );
}


function ExtractionSettings() {
  const { project } = useApp();
  const qc = useQueryClient();
  const { data } = useQuery({ queryKey: ["settings", project], queryFn: () => api.getSettings(project) });
  async function toggle() {
    await api.setSettings(project, { llm_enabled: data?.llm_enabled === "1" ? "0" : "1" });
    qc.invalidateQueries({ queryKey: ["settings", project] });
  }
  async function setModel(m: string) {
    await api.setSettings(project, { llm_model: m });
    qc.invalidateQueries({ queryKey: ["settings", project] });
  }
  const enabled = data?.llm_enabled === "1";
  return (
    <div className="space-y-3 px-4 py-3 text-[13px]">
      <div className="flex items-center justify-between">
        <div>
          <div className="font-medium">LLM extraction</div>
          <div className="text-2xs text-faint">Off = deterministic rules. On = configured model proposes facts; the engine still decides truth.</div>
        </div>
        <button onClick={toggle}
          className={enabled ? "rounded-md bg-accent px-3 py-1.5 text-2xs font-semibold text-white" : "rounded-md border px-3 py-1.5 text-2xs font-semibold text-muted"}>
          {enabled ? "Enabled" : "Disabled"}
        </button>
      </div>
      {enabled && (
        <div>
          <label className="text-2xs text-faint">Model</label>
          <input defaultValue={data?.llm_model ?? ""} placeholder="gpt-4o-mini"
            onBlur={e => setModel(e.target.value)}
            className="mono mt-1 w-full max-w-sm rounded-md border bg-panel px-3 py-1.5 text-[13px] outline-none focus:border-accent" />
          <p className="mt-1 text-2xs text-faint">Requires OMEM_LLM_API_KEY on the server; otherwise a deterministic fallback runs and is logged as such.</p>
        </div>
      )}
    </div>
  );
}
// "Who is us." The anchor for every direction/role decision in Gmail
// extraction: mail from these addresses/domains is SELF, and the company name
// becomes the subject of our own commercial intents. Connected mailbox
// addresses are always included automatically.
function IdentitySettings() {
  const { project } = useApp();
  const qc = useQueryClient();
  const { data } = useQuery({ queryKey: ["identity", project], queryFn: () => api.identity(project) });
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [form, setForm] = useState<{ company_name: string; domains: string; emails: string } | null>(null);

  const current = form ?? {
    company_name: data?.company_name ?? "",
    domains: (data?.domains ?? []).join(", "),
    emails: (data?.emails ?? []).join(", "),
  };

  async function save() {
    setSaving(true); setSaved(false);
    try {
      await api.setIdentity(project, {
        company_name: current.company_name || null,
        domains: current.domains.split(",").map(s => s.trim()).filter(Boolean),
        emails: current.emails.split(",").map(s => s.trim()).filter(Boolean),
      });
      setSaved(true);
      qc.invalidateQueries({ queryKey: ["identity", project] });
    } finally { setSaving(false); }
  }

  return (
    <div className="space-y-3 px-4 py-3">
      <p className="text-[13px] text-muted">
        Tells OMEM who &ldquo;we&rdquo; are. Mail from these addresses or domains is treated as
        sent by your organization — so your own &ldquo;I&rsquo;d like to upgrade our subscription&rdquo;
        becomes a memory about <em>your company</em>, never about a customer.
      </p>
      <div>
        <div className="text-2xs uppercase tracking-wide text-faint">Company name</div>
        <input value={current.company_name}
          onChange={e => setForm({ ...current, company_name: e.target.value })}
          placeholder="Acme Ltd"
          className="mt-1 w-full max-w-sm rounded-md border bg-panel px-3 py-1.5 text-[13px] outline-none focus:border-accent" />
      </div>
      <div>
        <div className="text-2xs uppercase tracking-wide text-faint">Domains (comma-separated)</div>
        <input value={current.domains}
          onChange={e => setForm({ ...current, domains: e.target.value })}
          placeholder="acme.com, acme.io"
          className="mono mt-1 w-full max-w-sm rounded-md border bg-panel px-3 py-1.5 text-[13px] outline-none focus:border-accent" />
      </div>
      <div>
        <div className="text-2xs uppercase tracking-wide text-faint">Extra addresses (comma-separated)</div>
        <input value={current.emails}
          onChange={e => setForm({ ...current, emails: e.target.value })}
          placeholder="info@acme.com, sales@acme.com"
          className="mono mt-1 w-full max-w-sm rounded-md border bg-panel px-3 py-1.5 text-[13px] outline-none focus:border-accent" />
        <p className="mt-1 text-2xs text-faint">Connected Gmail accounts are always included automatically.</p>
      </div>
      <div className="flex items-center gap-3">
        <button onClick={save} disabled={saving}
          className="rounded-md bg-accent px-3 py-1.5 text-[13px] font-semibold text-white disabled:opacity-50">
          {saving ? "Saving…" : "Save identity"}
        </button>
        {saved && <span className="text-2xs text-believed">Saved.</span>}
      </div>
    </div>
  );
}
