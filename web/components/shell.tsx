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
import { getSession, setSession, ApiError, type AuthMode } from "@/lib/api";

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
  const [mode, setMode] = useState<AuthMode | null>(null);
  useEffect(() => {
    if (isMarketing || path?.startsWith("/onboarding")) return;
    // Which of the two modes the server is in decides what happens here, and the
    // server is the only one who knows. In local mode it is bound to loopback and
    // has no passwords, so provisioning a session silently is what makes the
    // quickstart a quickstart. In password mode it is reachable by other people,
    // so the only correct thing to show is a sign-in form. Auto-provisioning
    // there was the dashboard half of "an email address is the whole credential".
    let cancelled = false;
    (async () => {
      try {
        const h = await api.health();
        const m: AuthMode = h.auth === "password" ? "password" : "local";
        if (cancelled) return;
        setMode(m);
        if (getSession()) { setAuthed(true); return; }
        if (m === "password") { setAuthed(false); return; }
        const res = await api.signup({ email: "local@omem.dev", project: "My workspace" });
        setSession(res.token);
        if (!cancelled) setAuthed(true);
      } catch {
        // server not reachable yet — say so rather than bouncing to a page
        if (!cancelled) { setMode(null); setAuthed(false); }
      }
    })();
    return () => { cancelled = true; };
  }, [path, isMarketing]);
  if (isMarketing || path?.startsWith("/onboarding")) return <>{children}</>;
  if (authed === null) return null;
  if (!authed && mode === "password") return <SignIn onDone={() => setAuthed(true)} />;
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


/** Sign-in for password mode. Shown only when the server reports auth:"password",
 *  which is also the only mode in which a password exists to ask for. */
function SignIn({ onDone }: { onDone: () => void }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [needsCode, setNeedsCode] = useState(false);
  const [register, setRegister] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true); setErr(null);
    try {
      if (register) {
        const res = await api.signup({ email, password, code: code || undefined, project: "My workspace" });
        setSession(res.token);
      } else {
        const res = await api.login(email, password, code || undefined);
        setSession(res.token);
      }
      onDone();
    } catch (e2) {
      const ae = e2 as ApiError;
      // A second factor is a prompt, not a failure: ask for the code instead of
      // making the person guess why a correct password was rejected.
      if (ae.reason_code === "mfa_required" || /MFA/i.test(ae.message)) {
        setNeedsCode(true);
        setErr(code ? "That code was not accepted. Try the current one." : null);
      } else {
        setErr(ae.message);
      }
    }
    setBusy(false);
  }

  return (
    <div className="grid min-h-screen place-items-center px-6">
      <form onSubmit={submit} className="w-full max-w-sm">
        <div className="mb-8 flex items-center gap-2">
          <span className="grid h-6 w-6 place-items-center rounded-pill bg-accent text-white">
            <Share2 className="h-3 w-3" />
          </span>
          <span className="text-sm font-medium">OMEM</span>
        </div>
        <h1 className="text-lg font-medium">{register ? "Create an account" : "Sign in"}</h1>
        <p className="mt-1 text-sm text-muted">
          This server requires a password. OMEM is free while it is in beta.
        </p>
        <label className="mt-6 block text-sm">
          Email
          <input type="email" required value={email} onChange={e => setEmail(e.target.value)}
                 autoComplete="username"
                 className="mt-1 w-full rounded-md border bg-panel px-3 py-2 text-sm outline-none focus:border-accent" />
        </label>
        <label className="mt-4 block text-sm">
          Password
          <input type="password" required value={password} onChange={e => setPassword(e.target.value)}
                 autoComplete={register ? "new-password" : "current-password"}
                 minLength={register ? 10 : undefined}
                 className="mt-1 w-full rounded-md border bg-panel px-3 py-2 text-sm outline-none focus:border-accent" />
        </label>
        {register && (
          <p className="mt-1 text-xs text-muted">At least 10 characters.</p>
        )}
        {needsCode && (
          <label className="mt-4 block text-sm">
            Authentication code
            <input inputMode="numeric" autoComplete="one-time-code" value={code}
                   onChange={e => setCode(e.target.value)}
                   className="mt-1 w-full rounded-md border bg-panel px-3 py-2 text-sm outline-none focus:border-accent" />
          </label>
        )}
        {err && <div className="mt-4 rounded-md border border-conflict/40 bg-conflictBg px-3 py-2 text-2xs text-conflict">{err}</div>}
        <button type="submit" disabled={busy}
                className="mt-6 w-full rounded-md bg-accent px-3 py-2 text-sm text-white disabled:opacity-50">
          {busy ? "…" : register ? "Create account" : "Sign in"}
        </button>
        <button type="button" onClick={() => { setRegister(v => !v); setErr(null); }}
                className="mt-4 w-full text-center text-sm text-muted hover:underline">
          {register ? "I already have an account" : "Create an account"}
        </button>
      </form>
    </div>
  );
}
