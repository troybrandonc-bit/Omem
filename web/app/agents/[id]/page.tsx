"use client";
import { useQuery } from "@tanstack/react-query";
import { useParams } from "next/navigation";
import Link from "next/link";
import { api } from "@/lib/api";
import { useApp } from "@/components/providers";
import { Card, Skeleton, Badge } from "@/components/ui/primitives";
import { ArrowLeft, Bot } from "lucide-react";

export default function AgentDetail() {
  const id = decodeURIComponent(useParams().id as string);
  const { project, asOf } = useApp();
  const { data, isLoading } = useQuery({ queryKey: ["agent", project, id, asOf], queryFn: () => api.agent(project, id, asOf ?? "now") });
  if (isLoading || !data) return <Skeleton className="h-64" />;
  return (
    <div className="mx-auto max-w-3xl">
      <Link href="/agents" className="mb-4 inline-flex items-center gap-1.5 text-sm text-muted hover:text-fg"><ArrowLeft className="h-4 w-4" /> Agents</Link>
      <div className="mb-5 flex items-center gap-3">
        <div className="grid h-10 w-10 place-items-center rounded-lg border bg-panel"><Bot className="h-5 w-5 text-muted" /></div>
        <div><h1 className="display text-[24px]">{data.label || data.id}</h1><div className="text-xs text-muted">{data.id} / {data.kind}</div></div>
      </div>
      <div className="mb-2 tech-label">Claims asserted by this agent</div>
      <div className="space-y-2">
        {(data.claims || []).map(c => (
          <Link key={c.id} href={`/assertions/${encodeURIComponent(c.id)}`}>
            <Card className="p-3 hover:border-[color:var(--accent)]/40">
              <div className="flex items-center justify-between">
                <div className="text-sm font-medium">{c.label || c.proposition}</div>
                <Badge tone={c.open ? "believed" : "closed"}>{c.open ? "open" : "closed"}</Badge>
              </div>
              <div className="mt-0.5 text-2xs text-muted">t={c.assertion_time}</div>
            </Card>
          </Link>
        ))}
        {(!data.claims || data.claims.length === 0) && <div className="text-sm text-muted">No claims.</div>}
      </div>
    </div>
  );
}
