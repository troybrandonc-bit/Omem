"use client";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { api } from "@/lib/api";
import { useApp } from "@/components/providers";
import { Table, Th, Td, Skeleton, EmptyState, ErrorState, Badge } from "@/components/ui/primitives";
import { Box } from "lucide-react";

export default function Entities() {
  const { project } = useApp();
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ["entities", project], queryFn: () => api.entities(project), enabled: !!project });
  return (
    <div className="mx-auto max-w-4xl">
      <h1 className="mb-1 display text-lg">Entities</h1>
      {isLoading ? <Skeleton className="h-40" /> :
        isError || !data ? <ErrorState title="Could not read entities" onRetry={() => refetch()} /> :
        data.data.length === 0 ? <EmptyState icon={Box} title="No entities yet" /> :
        <Table><thead><tr><Th>Entity</Th><Th>Type</Th><Th>ID</Th></tr></thead><tbody>
          {data.data.map(e => (
            <tr key={e.id} className="cursor-pointer hover:bg-[color:var(--border)]/20">
              <Td><Link href={`/entity?id=${encodeURIComponent(e.id)}`} className="font-medium hover:text-accent">{e.label || e.id}</Link></Td>
              <Td><Badge tone="accent">{e.type}</Badge></Td>
              <Td><span className="text-xs text-muted">{e.id}</span></Td>
            </tr>
          ))}
        </tbody></Table>}
    </div>
  );
}
