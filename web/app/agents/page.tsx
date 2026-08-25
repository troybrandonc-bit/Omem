"use client";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { api } from "@/lib/api";
import { useApp } from "@/components/providers";
import { Table, Th, Td, Skeleton, EmptyState, ErrorState, Badge } from "@/components/ui/primitives";
import { Bot } from "lucide-react";

export default function Agents() {
  const { project } = useApp();
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ["agents", project], queryFn: () => api.agents(project), enabled: !!project });
  return (
    <div className="mx-auto max-w-4xl">
      <h1 className="mb-1 display text-lg">Agents</h1>
      {isLoading ? <Skeleton className="h-40" /> :
        isError || !data ? <ErrorState title="Could not read agents" onRetry={() => refetch()} /> :
        data.data.length === 0 ? <EmptyState icon={Bot} title="No agents yet" /> :
        <Table><thead><tr><Th>Agent</Th><Th>Kind</Th><Th>ID</Th></tr></thead><tbody>
          {data.data.map(a => (
            <tr key={a.id} className="cursor-pointer hover:bg-[color:var(--border)]/20">
              <Td><Link href={`/agent?id=${encodeURIComponent(a.id)}`} className="font-medium hover:text-accent">{a.label || a.id}</Link></Td>
              <Td><Badge tone="accent">{a.kind}</Badge></Td>
              <Td><span className="text-xs text-muted">{a.id}</span></Td>
            </tr>
          ))}
        </tbody></Table>}
    </div>
  );
}
