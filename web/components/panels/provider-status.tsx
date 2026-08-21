"use client";
import { useQuery } from "@tanstack/react-query";
import { api, type DnsResult } from "@/lib/api";
import { RefreshCw } from "lucide-react";

// Live provider connectivity. Every external host the app contacts is resolved
// and reported, so a failing sync points at the host responsible instead of
// leaving an anonymous URLError on a connector card.
export function ProviderStatus() {
  const { data, isFetching, refetch } = useQuery({
    queryKey: ["providers-check"],
    queryFn: api.providersCheck,
    retry: false,
    refetchOnWindowFocus: false,
  });

  if (!data) return null;

  type Row = { label: string; configured: boolean; dns?: DnsResult; note?: string; state: "ok" | "fail" | "unset" };
  const llmState: Row["state"] = !data.llm.configured
    ? "unset"
    : data.llm.reachable === true
      ? "ok"
      : data.llm.reachable === false
        ? "fail"           // resolved, but the provider refused or errored
        : data.llm.dns?.ok ? "ok" : "fail";
  const rows: Row[] = [
    {
      label: data.llm.model ? `LLM (${data.llm.model})` : "LLM extraction",
      configured: data.llm.configured,
      dns: data.llm.dns,
      state: llmState,
      note: !data.llm.configured
        ? "not configured, deterministic extraction in use"
        : data.llm.reachable === false
          ? data.llm.error
          : data.llm.reachable
            ? `responding${data.llm.sample ? ` (${data.llm.sample})` : ""}`
            : undefined,
    },
    ...Object.entries(data.google.hosts).map(([host, dns]) => ({
      label: host,
      configured: data.google.configured,
      dns,
      state: (!data.google.configured ? "unset" : dns.ok ? "ok" : "fail") as Row["state"],
      note: data.google.configured ? undefined : "Google not configured",
    })),
  ];

  // the panel is only healthy when every configured provider actually works,
  // not merely when its hostname resolves
  const healthy = rows.every(r => r.state !== "fail");
  const summary = healthy
    ? "all configured providers working"
    : rows.filter(r => r.state === "fail").map(r => r.label).join(", ") + " not working";

  return (
    <section className="panel overflow-hidden">
      <header className="flex items-center justify-between border-b px-4 py-2.5">
        <div className="flex items-center gap-2.5">
          <h2 className="text-[15px] font-semibold">Provider connectivity</h2>
          <span className={healthy ? "text-2xs text-believed" : "text-2xs text-conflict"}>
            {summary}
          </span>
        </div>
        <button onClick={() => refetch()} disabled={isFetching}
          className="inline-flex items-center gap-1.5 rounded-md border px-2.5 py-1 text-2xs font-semibold text-muted hover:border-line-strong disabled:opacity-40">
          {isFetching ? <RefreshCw className="h-3 w-3 animate-spin" /> : <RefreshCw className="h-3 w-3" />} Re-check
        </button>
      </header>
      <div className="divide-y">
        {rows.map(r => {
          const ok = r.state === "ok";
          return (
            <div key={r.label} className="flex items-start justify-between gap-4 px-4 py-2">
              <div className="min-w-0">
                <div className="mono text-[13px]">{r.label}</div>
                {(r.dns?.error || r.note) && (
                  <div className={"mt-0.5 text-2xs " + (r.dns?.error ? "text-conflict" : "text-muted")}>
                    {r.dns?.error ?? r.note}
                  </div>
                )}
                {ok && r.dns?.addresses && (
                  <div className="mono mt-0.5 text-2xs text-faint">{r.dns.addresses.slice(0, 2).join(", ")}</div>
                )}
              </div>
              <span className={"shrink-0 rounded-sm border px-2 py-px text-2xs font-semibold uppercase " +
                (r.state === "unset" ? "text-muted" : ok ? "text-believed" : "text-conflict")}
                style={{ borderColor: "currentColor" }}>
                {r.state === "unset" ? "not set" : ok ? "working" : r.dns?.ok === false ? "unreachable" : "rejected"}
              </span>
            </div>
          );
        })}
      </div>
    </section>
  );
}
