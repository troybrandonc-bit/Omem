"use client";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { useApp } from "@/components/providers";
import { Skeleton } from "@/components/ui/primitives";
import { useState } from "react";

const ROLES = ["owner", "admin", "developer", "viewer"];

export default function Team() {
  const { project } = useApp();
  const qc = useQueryClient();
  const { data, error } = useQuery({ queryKey: ["members", project], queryFn: () => api.members(project), retry: false });
  const [email, setEmail] = useState("");
  const [role, setRole] = useState("developer");

  if (error) return <div className="panel m-1 p-6 text-[13px] text-muted">Managing members requires an admin or owner role.</div>;

  async function invite() {
    if (!email.includes("@")) return;
    await api.setRole(email, role);
    setEmail("");
    qc.invalidateQueries({ queryKey: ["members", project] });
  }

  return (
    <div className="space-y-5">
      <h1 className="display text-[24px]">Team</h1>
      <section className="panel overflow-hidden">
        <header className="border-b px-4 py-2.5"><h2 className="text-[14px] font-semibold">Members</h2></header>
        {!data ? <div className="p-5"><Skeleton className="h-12" /></div> : (
          <div className="divide-y">
            {data.data.map(m => (
              <div key={m.user_id} className="flex items-center justify-between px-4 py-2.5">
                <span className="text-[13px] font-medium">{m.email}</span>
                <span className="rounded-pill border border-line-strong px-2 py-px text-2xs font-semibold uppercase text-muted">{m.role}</span>
              </div>
            ))}
          </div>
        )}
        <div className="flex flex-wrap items-center gap-2 border-t px-4 py-2.5.5">
          <input value={email} onChange={e => setEmail(e.target.value)} placeholder="teammate@company.com"
            className="flex-1 rounded-md border bg-panel px-3 py-1.5 text-[13px] outline-none focus:border-accent" />
          <select value={role} onChange={e => setRole(e.target.value)} className="rounded-md border bg-panel px-2 py-1.5 text-[13px]">
            {ROLES.map(r => <option key={r} value={r}>{r}</option>)}
          </select>
          <button onClick={invite} className="rounded-md bg-accent px-3.5 py-1.5 text-[13px] font-semibold text-white hover:opacity-[0.88]">Set role</button>
        </div>
      </section>
    </div>
  );
}
