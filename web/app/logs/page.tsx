"use client";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { useApp } from "@/components/providers";
import { Table, Th, Td, Skeleton, Badge, EmptyState } from "@/components/ui/primitives";
import { ScrollText } from "lucide-react";

export default function Logs() {
  const { project } = useApp();
  const { data, isLoading } = useQuery({ queryKey: ["logs", project], queryFn: () => api.logs(project), refetchInterval: 3000 });
  return (
    <div className="mx-auto max-w-5xl">
      <h1 className="mb-1 display text-[21px]">Logs</h1>
      {isLoading ? <Skeleton className="h-64" /> :
        !data || data.data.length === 0 ? <EmptyState icon={ScrollText} title="No requests yet" /> :
        <Table><thead><tr><Th>Method</Th><Th>Path</Th><Th>Summary</Th><Th>Status</Th></tr></thead><tbody>
          {data.data.map(l => (
            <tr key={l.id} className="hover:bg-[color:var(--border)]/20">
              <Td><span className="mono text-2xs">{l.method}</span></Td>
              <Td><span className="text-2xs text-faint">{l.path}</span></Td>
              <Td className="text-sm">{l.summary}</Td>
              <Td>{l.reason_code ? <Badge tone="conflict">{l.reason_code}</Badge> : <Badge tone={l.status < 300 ? "believed" : "conflict"}>{l.status}</Badge>}</Td>
            </tr>
          ))}
        </tbody></Table>}
    </div>
  );
}
