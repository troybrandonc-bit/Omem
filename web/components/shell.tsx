"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { useApp } from "./providers";
import { api } from "@/lib/api";
import { cn } from "@/lib/cn";
import {
  Home, Brain, Bot, Box, Clock, AlertTriangle, Network, FlaskConical, Braces,
  ScrollText, Gauge, Settings, Share2, ChevronDown, Search, Sun, Moon, User, Activity, Users, ShieldCheck, HeartPulse, Stethoscope,
} from "lucide-react";
import { useEffect, useState } from "react";
import { getSession, setSession } from "@/lib/api";

const NAV = [
  { group: null, items: [
    { href: "/overview", label: "Home", icon: Home },
    { href: "/memory", label: "Memory", icon: Brain },
    { href: "/intelligence", label: "Intelligence", icon: Activity },
    { href: "/memory-health", label: "Memory health", icon: HeartPulse },
    { href: "/agents", label: "Agents", icon: Bot },
    { href: "/entities", label: "Entities", icon: Box },
    { href: "/timeline", label: "Timeline", icon: Clock },
    { href: "/conflicts", label: "Conflicts", icon: AlertTriangle },
    { href: "/graph", label: "Graph", icon: Network },
  ]},
  { group: "Developers", items: [
    { href: "/playground", label: "Playground", icon: FlaskConical },
    { href: "/developers", label: "API", icon: Braces },
    { href: "/logs", label: "Logs", icon: ScrollText },
    { href: "/diagnostics", label: "Diagnostics", icon: Stethoscope },
  ]},
  { group: "Organization", items: [
    { href: "/usage", label: "Usage", icon: Gauge },
    { href: "/team", label: "Team", icon: Users },
    { href: "/audit", label: "Audit", icon: ShieldCheck },
    { href: "/settings", label: "Settings", icon: Settings },
  ]},
];

export function Shell({ children }: { children: React.ReactNode }) {
  const path = usePathname();
  const MARKETING = ["/docs", "/pricing", "/security", "/changelog"];
  const isMarketing = path === "/" || MARKETING.some(r => path?.startsWith(r));
  const [palette, setPalette] = useState(false);
  useEffect(() => {
    const h = (e: KeyboardEvent) => { if ((e.metaKey || e.ctrlKey) && e.key === "k") { e.preventDefault(); setPalette(v => !v); } };
    window.addEventListener("keydown", h); return () => window.removeEventListener("keydown", h);
  }, []);
  const [authed, setAuthed] = useState<boolean | null>(null);
  useEffect(() => {
    if (isMarketing || path?.startsWith("/onboarding")) return;
    // No login screen: if there's no session yet, silently provision a local one
    // against the running server so the dashboard opens straight onto the agent's
    // memory. (The server still requires auth for every call; we just create the
    // session automatically instead of showing a signup form.)
    let cancelled = false;
    (async () => {
      if (getSession()) { if (!cancelled) setAuthed(true); return; }
      try {
        const res = await api.signup({ email: "local@omem.dev", project: "My workspace" });
        setSession(res.token);
        if (!cancelled) setAuthed(true);
      } catch {
        // server not reachable yet — retry shortly rather than bouncing to a page
        if (!cancelled) setAuthed(false);
      }
    })();
    return () => { cancelled = true; };
  }, [path, isMarketing]);
  if (isMarketing || path?.startsWith("/onboarding")) return <>{children}</>;
  if (authed === null) return null;
  if (!authed) return (
    <div style={{ padding: "3rem", fontFamily: "system-ui", color: "#64748b" }}>
      Waiting for the OMEM server… make sure it&apos;s running, then refresh.
    </div>
  );

  return (
    <div className="flex min-h-screen">
      <Sidebar path={path ?? ""} />
      <div className="min-w-0 flex-1">
        <TopBar onSearch={() => setPalette(true)} />
        <main className="mx-auto max-w-[1200px] px-6 pb-16 pt-2">{children}</main>
      </div>
      {palette && <CommandPalette onClose={() => setPalette(false)} />}
    </div>
  );
}

function Sidebar({ path }: { path: string }) {
  const { project, setProject } = useApp();
  const { data } = useQuery({ queryKey: ["projects"], queryFn: api.projects });
  const projects = data?.data || [];
  return (
    <aside className="hidden w-[216px] shrink-0 flex-col border-r px-3 pb-6 pt-4 md:flex">
      <div className="mb-5 flex items-center gap-2.5 px-2">
        <span className="grid h-7 w-7 place-items-center rounded-pill bg-accent text-white">
          <Share2 className="h-3.5 w-3.5" />
        </span>
        <div className="relative min-w-0 flex-1">
          <select value={project} onChange={e => setProject(e.target.value)}
            className="w-full appearance-none bg-transparent pr-5 text-[14px] font-semibold outline-none">
            {(projects.length ? projects : [{ id: "demo", name: "OMEM" } as any]).map(p => (
              <option key={p.id} value={p.id}>{p.is_demo ? "Demo (shared)" : p.name}</option>
            ))}
          </select>
          <ChevronDown className="pointer-events-none absolute right-0 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-faint" />
        </div>
      </div>
      <nav className="flex-1 space-y-4">
        {NAV.map((g, gi) => (
          <div key={gi}>
            {g.group && <div className="tech-label mb-1.5 px-2">{g.group}</div>}
            <div className="space-y-0.5">
              {g.items.map(it => {
                const active = path.startsWith(it.href);
                const Icon = it.icon;
                return (
                  <Link key={it.href} href={it.href} aria-current={active ? "page" : undefined}
                    className={cn("flex items-center gap-2.5 rounded-md px-2 py-[5px] text-[13px] transition-colors",
                      active
                        ? "bg-accentBg font-semibold text-accent"
                        : "text-muted hover:bg-raised hover:text-fg")}>
                    <Icon className={cn("h-[15px] w-[15px]", active ? "text-accent" : "text-faint")} strokeWidth={1.8} />
                    {it.label}
                  </Link>
                );
              })}
            </div>
          </div>
        ))}
      </nav>
    </aside>
  );
}

function TopBar({ onSearch }: { onSearch: () => void }) {
  const { project, asOf, setAsOf, now, setNow, theme, toggleTheme } = useApp();
  const { data } = useQuery({ queryKey: ["overview", project], queryFn: () => api.overview(project) });
  useEffect(() => { if (data?.now !== undefined) setNow(data.now); }, [data?.now, setNow]);
  const T = asOf ?? now;
  return (
    <div className="sticky top-0 z-30 bg-bg/95 backdrop-blur-sm">
      <div className="mx-auto flex max-w-[1200px] items-center gap-4 px-6 py-4">
        <button onClick={onSearch}
          className="panel flex h-10 w-full max-w-xl items-center gap-2.5 px-3.5 text-left text-[14px] text-faint">
          <Search className="h-4 w-4" /> Search…
          <kbd className="ml-auto rounded border bg-raised px-1.5 text-2xs text-faint">⌘K</kbd>
        </button>
        <div className="ml-auto flex items-center gap-2.5">
          <div className="panel hidden h-10 items-center gap-2.5 px-3 sm:flex">
            <span className="text-2xs text-faint">as of</span>
            <input type="range" min={0} max={Math.max(now, 1)} value={T}
              onChange={e => { const v = Number(e.target.value); setAsOf(v >= now ? null : v); }}
              className="h-1 w-28 cursor-pointer accent-[color:var(--accent)]" />
            <span className="num w-14 text-right text-2xs text-muted">
              {asOf === null ? `now t=${now}` : `t=${asOf}`}
            </span>
          </div>
          <button onClick={toggleTheme} aria-label="Toggle theme"
            className="panel grid h-10 w-10 place-items-center text-muted transition-colors hover:text-fg">
            {theme === "dark" ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
          </button>
          <span className="grid h-10 w-10 place-items-center rounded-pill border bg-panel text-faint">
            <User className="h-4.5 w-4.5" style={{ width: 17, height: 17 }} />
          </span>
        </div>
      </div>
    </div>
  );
}

function CommandPalette({ onClose }: { onClose: () => void }) {
  const { project } = useApp();
  const [q, setQ] = useState("");
  const { data } = useQuery({ queryKey: ["assertions", project, "palette"], queryFn: () => api.assertions(project) });
  const results = (data?.data || []).filter(a =>
    (a.label || a.proposition).toLowerCase().includes(q.toLowerCase())).slice(0, 8);
  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center bg-black/30 pt-32" onClick={onClose}>
      <div className="panel w-full max-w-lg overflow-hidden" onClick={e => e.stopPropagation()}>
        <input autoFocus value={q} onChange={e => setQ(e.target.value)} placeholder="Search beliefs…"
          className="w-full border-b bg-transparent px-4 py-3 text-sm outline-none" />
        <div className="max-h-72 overflow-y-auto p-1.5">
          {results.length === 0 && <div className="px-3 py-6 text-center text-sm text-muted">No matches</div>}
          {results.map(a => (
            <Link key={a.id} href={`/assertions/${encodeURIComponent(a.id)}`} onClick={onClose}
              className="flex items-center justify-between rounded-md px-3 py-2 text-sm hover:bg-raised">
              <span>{a.label || a.proposition}</span>
              <span className="text-2xs text-faint">{a.id}</span>
            </Link>
          ))}
        </div>
      </div>
    </div>
  );
}
