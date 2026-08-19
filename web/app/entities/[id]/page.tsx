"use client";
import { useQuery } from "@tanstack/react-query";
import { useParams } from "next/navigation";
import Link from "next/link";
import { api, isGrounded } from "@/lib/api";
import { useApp } from "@/components/providers";
import { Card, Skeleton, Badge } from "@/components/ui/primitives";
import { ArrowLeft, Box } from "lucide-react";

export default function EntityDetail() {
  const id = decodeURIComponent(useParams().id as string);
  const { project, asOf } = useApp();
  const { data: ent } = useQuery({ queryKey: ["entity", project, id], queryFn: () => api.entity(project, id) });
  const { data, isLoading } = useQuery({ queryKey: ["beliefs", project, id, asOf], queryFn: () => api.beliefsAbout(project, id, asOf ?? "now") });
  return (
    <div className="mx-auto max-w-3xl">
      <Link href="/entities" className="mb-4 inline-flex items-center gap-1.5 text-sm text-muted hover:text-fg"><ArrowLeft className="h-4 w-4" /> Entities</Link>
      <div className="mb-5 flex items-center gap-3">
        <div className="grid h-10 w-10 place-items-center rounded-lg border bg-panel"><Box className="h-5 w-5 text-muted" /></div>
        <div><h1 className="display text-[24px]">{ent?.label || id}</h1><div className="text-xs text-muted">{id}{ent?.type ? ` / ${ent.type}` : ""}</div></div>
      </div>
      <div className="mb-2 tech-label">
        What your AI believes about this entity{asOf !== null ? ` (as-of t=${asOf})` : ""}
      </div>
      {isLoading ? <Skeleton className="h-40" /> :
        <div className="space-y-2">
          {(data?.data || []).map(b => (
            <Link key={b.id} href={`/assertions/${encodeURIComponent(b.id)}`}>
              <Card className="p-3 hover:border-[color:var(--accent)]/40">
                <div className="flex items-center justify-between">
                  <div className="text-sm font-medium">{b.label || b.proposition}</div>
                  {isGrounded(b.grounded) ? <Badge tone="believed">grounded</Badge> : <Badge tone="unknown">ungrounded</Badge>}
                </div>
                <div className="mt-0.5 text-2xs text-muted">by {b.agent} / t={b.assertion_time}</div>
              </Card>
            </Link>
          ))}
          {(!data || data.data.length === 0) && <div className="text-sm text-muted">No current beliefs about this entity.</div>}
        </div>}
    </div>
  );
}
