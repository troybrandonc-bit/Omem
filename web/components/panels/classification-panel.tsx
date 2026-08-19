"use client";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api, type MessageClassification } from "@/lib/api";
import { useApp } from "@/components/providers";
import { cn } from "@/lib/cn";

// What the relevance classifier decided, and why. Every number is a real count
// from message_classifications; nothing here is estimated.
const TABS = [
  { key: "BUSINESS_RELEVANT", label: "Business" },
  { key: "POSSIBLY_BUSINESS", label: "Possible" },
  { key: "AUTOMATED_NOISE", label: "Automated" },
  { key: "NON_BUSINESS", label: "Non-business" },
];

const TONE: Record<string, string> = {
  BUSINESS_RELEVANT: "text-believed",
  POSSIBLY_BUSINESS: "text-unknown",
  AUTOMATED_NOISE: "text-muted",
  NON_BUSINESS: "text-muted",
};

export function ClassificationPanel() {
  const { project } = useApp();
  const [tab, setTab] = useState("BUSINESS_RELEVANT");
  const { data: summary } = useQuery({
    queryKey: ["cls-summary", project],
    queryFn: () => api.classificationSummary(project),
    refetchInterval: 8000,
  });
  const { data: list } = useQuery({
    queryKey: ["cls-list", project, tab],
    queryFn: () => api.classifications(project, tab),
  });

  if (!summary || summary.messages_scanned === 0) return null;
  const by = summary.by_classification;

  return (
    <section className="panel overflow-hidden">
      <header className="flex flex-wrap items-center justify-between gap-2 border-b px-4 py-2.5">
        <h2 className="text-[14px] font-semibold">Business relevance</h2>
        <span className="text-2xs text-faint">
          <span className="num text-fg">{summary.messages_scanned}</span> scanned ·{" "}
          <span className="num text-fg">{summary.threads}</span> threads ·{" "}
          <span className="num text-fg">{summary.facts_extracted}</span> facts
        </span>
      </header>

      <div className="grid grid-cols-2 divide-x divide-y sm:grid-cols-4 sm:divide-y-0">
        {TABS.map(t => (
          <button key={t.key} onClick={() => setTab(t.key)}
            className={cn("px-4 py-3 text-left transition-colors hover:bg-raised",
              tab === t.key && "bg-raised")}>
            <div className="text-2xs text-faint">{t.label}</div>
            <div className={cn("num mt-1 text-[20px] leading-none", TONE[t.key])}>{by[t.key] ?? 0}</div>
          </button>
        ))}
      </div>

      <div className="divide-y border-t">
        {!list ? null : list.data.length === 0 ? (
          <div className="px-4 py-3 text-2xs text-faint">Nothing in this category.</div>
        ) : (
          list.data.slice(0, 12).map((m, i) => <Row key={i} m={m} />)
        )}
      </div>
    </section>
  );
}

function Row({ m }: { m: MessageClassification }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="px-4 py-2">
      <button onClick={() => setOpen(!open)} className="flex w-full items-center gap-3 text-left">
        <span className="min-w-0 flex-1 truncate text-[13px]">{m.subject || "(no subject)"}</span>
        {m.business_type && (
          <span className="shrink-0 rounded-sm border border-line-strong px-1.5 py-px text-2xs text-muted">
            {m.business_type}
          </span>
        )}
        <span className="num shrink-0 text-2xs text-faint">{m.confidence.toFixed(2)}</span>
        <span className="num shrink-0 text-2xs text-faint">
          {m.facts_extracted} {m.facts_extracted === 1 ? "fact" : "facts"}
        </span>
      </button>
      {open && (
        <div className="mt-1.5 space-y-1.5 border-l-2 border-border pl-3">
          <div className="text-2xs text-muted">{m.sender}</div>
          {m.reasons.map((r, i) => (
            <div key={i} className="text-2xs text-muted">{r}</div>
          ))}
          {m.signals.length > 0 && (
            <div className="flex flex-wrap gap-1">
              {m.signals.map((s, i) => <span key={i} className="chip">{s}</span>)}
            </div>
          )}
          <div className="text-2xs text-faint">
            {m.entered_pipeline ? "Entered the memory pipeline" : "Excluded from memory"} · judged by {m.method}
          </div>
        </div>
      )}
    </div>
  );
}
