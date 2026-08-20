"use client";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { api } from "@/lib/api";
import { useApp } from "@/components/providers";
import { Table, Th, Td, Skeleton, EmptyState, Badge } from "@/components/ui/primitives";
import { Box } from "lucide-react";

export default function Entities() {
  const { project } = useApp();
  const { data, isLoading } = useQuery({ queryKey: ["entities", project], queryFn: () => api.entities(project) });
  return (
    <div className="mx-auto max-w-4xl">
      <h1 className="mb-1 display text-[21px]">Entities</h1>
      {isLoading ? <Skeleton className="h-40" /> :
        !data || data.data.length === 0 ? <EmptyState icon={Box} title="No entities yet" /> :
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
