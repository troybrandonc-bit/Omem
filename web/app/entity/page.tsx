"use client";
/* Query-param route, not /assertions/[id].
 *
 * `output: "export"` emits a file per route at build time, and a route whose id
 * only exists at runtime has no file to emit. Next needs generateStaticParams,
 * which cannot enumerate ids that have not been created yet. So the id moves
 * into the query string, which is a client-side concern and needs no file.
 *
 * The singular path (/assertion, not /assertions) keeps it from colliding with
 * the list page that already lives at the plural one.
 *
 * useSearchParams() suspends during prerender, so the body sits inside a
 * Suspense boundary. Without it the export fails with "useSearchParams() should
 * be wrapped in a suspense boundary", a build error, not a runtime one.
 */
import { Suspense } from "react";
import { useQuery } from "@tanstack/react-query";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import { api, isGrounded } from "@/lib/api";
import { useApp } from "@/components/providers";
import { Card, Skeleton, Badge, ErrorState } from "@/components/ui/primitives";
import { ArrowLeft, Box } from "lucide-react";

function EntityDetailInner() {
  const id = useSearchParams().get("id") || "";
  const { project, asOf } = useApp();
  const { data: ent } = useQuery({ queryKey: ["entity", project, id], queryFn: () => api.entity(project, id) });
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ["beliefs", project, id, asOf],
    queryFn: () => api.beliefsAbout(project, id, asOf ?? "now"), enabled: !!project });
  return (
    <div className="mx-auto max-w-3xl">
      <Link href="/entities" className="mb-4 inline-flex items-center gap-1.5 text-sm text-muted hover:text-fg"><ArrowLeft className="h-4 w-4" /> Entities</Link>
      <div className="mb-5 flex items-center gap-3">
        <div className="grid h-10 w-10 place-items-center rounded-lg border bg-panel"><Box className="h-5 w-5 text-muted" /></div>
        <div><h1 className="display text-2xl">{ent?.label || id}</h1><div className="text-xs text-muted">{id}{ent?.type ? ` / ${ent.type}` : ""}</div></div>
      </div>
      <div className="mb-2 tech-label">
        What your AI believes about this entity{asOf !== null ? ` (as-of t=${asOf})` : ""}
      </div>
      {isLoading ? <Skeleton className="h-40" /> :
        isError || !data ?
          <ErrorState title="Could not read beliefs about this entity"
            body="The request failed, so this is not a statement that nothing is believed."
            onRetry={() => refetch()} /> :
        <div className="space-y-2">
          {(data?.data || []).map(b => (
            <Link key={b.id} href={`/assertion?id=${encodeURIComponent(b.id)}`}>
              <Card className="p-3 hover:border-[color:var(--accent)]/40">
                <div className="flex items-center justify-between">
                  <div className="text-sm font-medium">{b.label || b.proposition}</div>
                  {isGrounded(b.grounded) ? <Badge tone="believed">grounded</Badge> : <Badge tone="unknown">ungrounded</Badge>}
                </div>
                <div className="mt-0.5 text-2xs text-muted">by {b.agent} / t={b.assertion_time}</div>
              </Card>
            </Link>
          ))}
          {data.data.length === 0 && <div className="text-sm text-muted">No current beliefs about this entity.</div>}
        </div>}
    </div>
  );
}


export default function EntityDetail() {
  return (
    <Suspense fallback={null}>
      <EntityDetailInner />
    </Suspense>
  );
}
