"use client";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { useApp } from "@/components/providers";
import { Card, Skeleton, EmptyState } from "@/components/ui/primitives";
import { Clock } from "lucide-react";

export default function Timeline() {
  const { project, asOf } = useApp();
  const { data, isLoading } = useQuery({ queryKey: ["timeline", project, asOf], queryFn: () => api.timeline(project, asOf ?? "now") });
  return (
    <div className="mx-auto max-w-4xl">
      <h1 className="mb-1 display text-[21px]">Timeline</h1>
      {isLoading ? <Skeleton className="h-40" /> :
        !data || data.events.length === 0 ? <EmptyState icon={Clock} title="No events yet" /> :
        <div className="relative pl-6">
          <div className="absolute left-2 top-2 bottom-2 w-px bg-border" />
          {data.events.map(e => (
            <div key={e.id} className="relative mb-4">
              <span className="led accent absolute -left-[15px] top-2" />
              <Card className="p-3">
                <div className="flex items-center justify-between"><div className="text-sm font-medium">{e.label || e.id}</div><span className="text-2xs text-faint">t={e.event_time}</span></div>
                <div className="mt-0.5 text-2xs text-muted">{e.kind}</div>
              </Card>
            </div>
          ))}
        </div>}
    </div>
  );
}
