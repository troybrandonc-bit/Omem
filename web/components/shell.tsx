"use client";
import Image from "next/image";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { useApp } from "./providers";
import { api } from "@/lib/api";
import { cn } from "@/lib/cn";
import { useScrolled } from "@/lib/use-scrolled";
import { isMarketingRoute } from "@/lib/routes";
import {
  Home, Brain, Bot, Box, Clock, AlertTriangle, Network, FlaskConical, Braces,
  ScrollText, Gauge, Settings, Search, Sun, Moon, User, Activity, Users, ShieldCheck,
  HeartPulse, ShieldPlus, Stethoscope, Menu, X, ChevronDown, History, GitMerge,
} from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
// getSession and AuthMode moved with the bootstrap into providers.tsx; setSession
// stays because SignIn below still establishes a session on submit.
import { setSession, ApiError } from "@/lib/api";

/* The dashboard chrome.
 *
 * The navigation is grouped by the question you arrived with, not by feature
 * name. Somebody opens this because an agent said something wrong. They are
 * asking "what does it believe / what disagrees / where did that come from",
 * and the nav answers in those terms.
 *
 * What the redesign fixed:
 *
 * - THE DASHBOARD HAD NO NAVIGATION ON A PHONE. The sidebar was
 *   `hidden w-[232px] … md:flex` and nothing replaced it, so below 768px there
 *   were twenty destinations and no way to reach nineteen of them. It is a
 *   drawer now, opened from the top bar, closing on route change and on Escape.
 *
 * - THE "AS OF" CLOCK WAS DESKTOP-ONLY TOO (`hidden sm:flex`), which meant the
 *   product's headline capability was unavailable on the device most people
 *   would first try it on. It moves into a compact control that survives to
 *   360px, and the range input carries the ARIA a slider needs.
 *
 * - THE SERVER-DOWN SCREEN WAS AN UNSTYLED PARAGRAPH with an inline hex colour
 *   and system-ui, i.e. the one screen a new user is most likely to hit was the
 *   one screen outside the design system, and it offered no way forward. It is
 *   a real empty state with the command to run and a retry.
 *
 * - THE COMMAND PALETTE WAS A DIV. No dialog role, no Escape, no focus return,
 *   no keyboard traversal of its own results — a modal that a keyboard user
 *   could open and then not leave.
 */

const NAV = [
  { group: "What is believed", items: [
    { href: "/overview", label: "Overview", icon: Home },
    { href: "/memory", label: "Memory", icon: Brain },
    { href: "/timeline", label: "Timeline", icon: Clock },
    { href: "/graph", label: "Belief graph", icon: Network },
  ]},
  { group: "What disagrees", items: [
    { href: "/conflicts", label: "Conflicts", icon: AlertTriangle },
    { href: "/proposals", label: "Proposals", icon: GitMerge },
    { href: "/memory-health", label: "Memory health", icon: HeartPulse },
    { href: "/intelligence", label: "Intelligence", icon: Activity },
  ]},
  { group: "Where it came from", items: [
    { href: "/agents", label: "Agents", icon: Bot },
    { href: "/entities", label: "Entities", icon: Box },
    { href: "/audit", label: "Audit trail", icon: ShieldCheck },
    { href: "/logs", label: "Request log", icon: ScrollText },
  ]},
  { group: "Build", items: [
    { href: "/playground", label: "Playground", icon: FlaskConical },
    { href: "/developers", label: "API", icon: Braces },
  ]},
  /* Nobody opens these while building; they open them because something broke.
     "Is it running" is the question they arrived with, and it was the one
     question the four original groups did not ask. */
  { group: "Is it running", items: [
    { href: "/healing", label: "Self-healing", icon: ShieldPlus },
    { href: "/diagnostics", label: "Diagnostics", icon: Stethoscope },
  ]},
  { group: "Account", items: [
    { href: "/usage", label: "Usage", icon: Gauge },
    { href: "/team", label: "Team", icon: Users },
    { href: "/settings", label: "Settings", icon: Settings },
  ]},
];

const ALL_ROUTES = NAV.flatMap(g => g.items);

export function Shell({ children }: { children: React.ReactNode }) {
  const path = usePathname();
  // The list moved to lib/routes.ts so Providers can share it; it had this
  // knowledge and Providers did not, which is how the public site ended up
  // opening a doomed request to the dashboard API on every visit.
  const isMarketing = isMarketingRoute(path);

  const [palette, setPalette] = useState(false);
  const [drawer, setDrawer] = useState(false);

  useEffect(() => {
    const h = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") { e.preventDefault(); setPalette(v => !v); }
    };
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, []);

  useEffect(() => { setDrawer(false); }, [path]);

  /* Startup lives in `Providers` now, not here. Both used to do half of it —
   * Shell provisioned the session, Providers listed projects — with nothing
   * ordering the two, and Providers runs ABOVE this component so it could not
   * wait for a session Shell had not created yet. That race left a new user
   * looking at an app whose every panel said "nothing here" while the server
   * held their data. One bootstrap, one order: see providers.tsx.
   */
  const { boot, mode, retryBoot } = useApp();

  if (isMarketing || path?.startsWith("/onboarding")) return <>{children}</>;
  if (boot === "connecting") return <BootSkeleton />;
  if (boot === "signin") return <SignIn onDone={retryBoot} />;
  if (boot === "unreachable") return <ServerDown onRetry={retryBoot} />;

  return (
    <div className="flex min-h-screen">
      <Sidebar path={path ?? ""} className="hidden md:flex" />

      {/* the drawer: same component, same order, no reduced version of the app */}
      {drawer && (
        <div className="fixed inset-0 z-50 md:hidden">
          <div className="anim-fade absolute inset-0 bg-black/40" onClick={() => setDrawer(false)} aria-hidden="true" />
          <div role="dialog" aria-modal="true" aria-label="Navigation"
            className="anim-fade absolute inset-y-0 left-0 w-[86%] max-w-[300px] overflow-y-auto border-r bg-bg">
            <div className="flex h-14 items-center justify-between pl-3 pr-2">
              <span className="tech-label">Navigation</span>
              <button onClick={() => setDrawer(false)} autoFocus
                className="tap grid h-10 w-10 place-items-center rounded-md text-muted hover:bg-raised hover:text-fg">
                <X className="h-5 w-5" /><span className="sr-only">Close navigation</span>
              </button>
            </div>
            <Sidebar path={path ?? ""} className="flex w-full border-r-0 pt-0" dense={false} />
          </div>
        </div>
      )}

      <div className="flex min-w-0 flex-1 flex-col">
        <TopBar onSearch={() => setPalette(true)} onMenu={() => setDrawer(true)} />
        <main id="main" tabIndex={-1}
          className="gutter-app mx-auto w-full max-w-shell flex-1 pb-20 pt-5"
          style={{ paddingBottom: "calc(5rem + env(safe-area-inset-bottom))" }}>
          {children}
        </main>
      </div>

      {palette && <CommandPalette onClose={() => setPalette(false)} />}
    </div>
  );
}

/** The first paint before auth resolves. `return null` meant a blank white
 *  document for as long as /health takes, which reads as a broken page rather
 *  than a loading one. */
function BootSkeleton() {
  return (
    <div className="flex min-h-screen items-center justify-center px-6" role="status" aria-live="polite">
      <div className="flex items-center gap-3 text-sm text-muted">
        <span className="led unknown animate-pulse" aria-hidden="true" />
        Connecting to the OMEM server…
      </div>
    </div>
  );
}

function Sidebar({ path, className, dense = true }: { path: string; className?: string; dense?: boolean }) {
  const { project, setProject } = useApp();
  const { data } = useQuery({ queryKey: ["projects"], queryFn: api.projects });
  const projects = data?.data || [];
  return (
    <aside className={cn("w-[232px] shrink-0 flex-col border-r px-3 pb-6 pt-4", className)}>
      {dense && (
        <div className="mb-6 flex items-center gap-2.5 px-2">
          <Link href="/" aria-label="OMEM home" className="shrink-0">
            <Image src="/omem-mark.png" alt="" width={24} height={24}
                   unoptimized className="h-6 w-6" />
          </Link>
          <div className="relative min-w-0 flex-1">
            <label htmlFor="project-select" className="sr-only">Current project</label>
            <select id="project-select" value={project} onChange={e => setProject(e.target.value)}
              className="w-full cursor-pointer appearance-none rounded bg-transparent py-1 pr-5 text-xs font-semibold outline-none hover:bg-raised">
              {(projects.length ? projects : [{ id: "demo", name: "OMEM" } as any]).map(p => (
                <option key={p.id} value={p.id}>{p.is_demo ? "Demo (shared)" : p.name}</option>
              ))}
            </select>
            <ChevronDown aria-hidden="true" className="pointer-events-none absolute right-0 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-faint" />
          </div>
        </div>
      )}

      <nav aria-label="Dashboard" className="flex-1 space-y-5">
        {NAV.map((g, gi) => (
          <div key={gi}>
            <h2 className="tech-label mb-2 px-2">{g.group}</h2>
            <ul className="space-y-0.5">
              {g.items.map(it => {
                const active = path.startsWith(it.href);
                const Icon = it.icon;
                return (
                  <li key={it.href}>
                    <Link href={it.href} aria-current={active ? "page" : undefined}
                      className={cn(
                        "tap relative flex items-center gap-2.5 rounded px-2 text-xs",
                        // 36px rows here, not 26px: this list is scanned and
                        // clicked constantly, and it is the touch surface in the
                        // drawer. Density elsewhere does not require a 26px link.
                        dense ? "h-9" : "h-11 text-sm",
                        "transition-colors duration-1 ease-out",
                        active ? "bg-chip font-medium text-fg" : "text-muted hover:bg-raised hover:text-fg")}>
                      {/* the marked line: a 2px ink rule, not a coloured pill */}
                      {active && <span aria-hidden="true"
                        className="absolute -left-3 top-1 bottom-1 w-[2px] rounded-r bg-accent" />}
                      <Icon aria-hidden="true"
                        className={cn("shrink-0", dense ? "h-[15px] w-[15px]" : "h-[17px] w-[17px]",
                          active ? "text-fg" : "text-faint")} strokeWidth={1.75} />
                      {it.label}
                    </Link>
                  </li>
                );
              })}
            </ul>
          </div>
        ))}
      </nav>
    </aside>
  );
}

function TopBar({ onSearch, onMenu }: { onSearch: () => void; onMenu: () => void }) {
  const lifted = useScrolled();
  const { project, asOf, setAsOf, now, setNow, theme, toggleTheme } = useApp();
  const { data } = useQuery({ queryKey: ["overview", project], queryFn: () => api.overview(project) });
  useEffect(() => { if (data?.now !== undefined) setNow(data.now); }, [data?.now, setNow]);
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);
  const T = asOf ?? now;

  return (
    /* The scroll edge again: at the top of a page this bar is the same paper as
       the canvas under it, and it separates itself only once rows are running
       beneath. `.gutter-app` keeps the leading control clear of a display
       cutout in landscape. */
    <div className={cn("chrome-bar sticky top-0 z-30", lifted && "is-lifted")}>
      <div className="gutter-app mx-auto flex h-14 max-w-shell items-center gap-2">
        <button onClick={onMenu} aria-label="Open navigation"
          className="tap grid h-10 w-10 shrink-0 place-items-center rounded-md text-fg hover:bg-raised md:hidden">
          <Menu className="h-5 w-5" />
        </button>

        {/* The brand in the header. On a phone the sidebar (which also carries
            the mark) is hidden, so this is the only logo on screen; on wider
            screens the wordmark joins it. */}
        <Link href="/" aria-label="OMEM home"
          className="mr-1 flex shrink-0 items-center gap-2 rounded">
          <Image src="/omem-mark.png" alt="" width={24} height={24}
                 unoptimized className="h-6 w-6" />
          <span className="hidden text-sm font-semibold tracking-[-0.02em] sm:inline">OMEM</span>
        </Link>

        <button onClick={onSearch}
          className="panel panel-link flex h-9 min-w-0 flex-1 items-center gap-2 px-3 text-left text-xs text-faint sm:max-w-md">
          <Search className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
          <span className="truncate">Search beliefs…</span>
          <kbd className="mono ml-auto hidden shrink-0 rounded-sm border bg-raised px-1.5 text-2xs text-faint sm:block">⌘K</kbd>
        </button>

        <div className="ml-auto flex shrink-0 items-center gap-1.5">
          <AsOfControl asOf={asOf} setAsOf={setAsOf} now={now} T={T} />
          <HealthIndicator />
          <button onClick={toggleTheme}
            aria-pressed={mounted ? theme === "dark" : undefined}
            aria-label={mounted && theme === "dark" ? "Switch to light theme" : "Switch to dark theme"}
            className="tap grid h-9 w-9 place-items-center rounded-md text-muted transition-colors duration-1 ease-out hover:bg-raised hover:text-fg">
            {mounted && theme === "dark" ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
          </button>
          <Link href="/settings" aria-label="Account settings"
            className="tap hidden h-9 w-9 place-items-center rounded-md border bg-panel text-faint transition-colors duration-1 ease-out hover:text-fg sm:grid">
            <User className="h-4 w-4" />
          </Link>
        </div>
      </div>
    </div>
  );
}

/**
 * The replay clock: permanent chrome, because time travel is an instrument
 * rather than a feature page.
 *
 * It was `hidden sm:flex`, so the capability the landing page leads with did not
 * exist on a phone. Below sm it collapses to the state readout plus a reset,
 * which keeps the one thing that must never be ambiguous — whether you are
 * looking at now or at the past — visible at every width.
 */
function AsOfControl({ asOf, setAsOf, now, T }: {
  asOf: number | null; setAsOf: (t: number | null) => void; now: number; T: number;
}) {
  const past = asOf !== null;
  return (
    <div className={cn("panel flex h-9 items-center gap-2 px-2.5 transition-colors duration-1 ease-out",
      past && "border-[color:var(--accent)] bg-accentBg")}>
      <History className={cn("h-3.5 w-3.5 shrink-0", past ? "text-accent" : "text-faint")} aria-hidden="true" />
      <label htmlFor="as-of" className="tech-label hidden sm:block">as of</label>
      <input id="as-of" type="range" min={0} max={Math.max(now, 1)} value={T}
        aria-label="View memory as of an earlier logical time"
        aria-valuetext={past ? `logical time ${asOf}` : `now, logical time ${now}`}
        onChange={e => { const v = Number(e.target.value); setAsOf(v >= now ? null : v); }}
        className="hidden h-1.5 w-20 cursor-pointer accent-[color:var(--accent)] sm:block lg:w-28" />
      <span className={cn("mono shrink-0 text-2xs tabular-nums", past ? "font-medium text-accent" : "text-muted")}>
        {past ? `t${asOf}` : `now`}
      </span>
      {past && (
        <button onClick={() => setAsOf(null)}
          className="tap shrink-0 rounded px-1 text-2xs font-medium text-accent hover:underline">
          reset
        </button>
      )}
    </div>
  );
}

/**
 * A real modal: role, label, Escape, focus capture on open and restoration on
 * close, and arrow-key traversal of the results. It was a plain <div> with a
 * click-outside handler, which a keyboard user could open and not escape.
 */
function CommandPalette({ onClose }: { onClose: () => void }) {
  const { project } = useApp();
  const [q, setQ] = useState("");
  const [i, setI] = useState(0);
  const opener = useRef<Element | null>(null);
  const listRef = useRef<HTMLDivElement>(null);

  const { data } = useQuery({ queryKey: ["assertions", project, "palette"], queryFn: () => api.assertions(project) });

  const beliefs = (data?.data || [])
    .filter(a => (a.label || a.proposition).toLowerCase().includes(q.toLowerCase()))
    .slice(0, 6)
    .map(a => ({ kind: "belief" as const, id: a.id, label: a.label || a.proposition, hint: a.id,
                 href: `/assertion?id=${encodeURIComponent(a.id)}` }));

  // Routes are searchable too. Twenty destinations behind a ⌘K that only found
  // assertions meant the fastest way to a page was still the mouse.
  const routes = ALL_ROUTES
    .filter(r => q.trim() && r.label.toLowerCase().includes(q.toLowerCase()))
    .slice(0, 4)
    .map(r => ({ kind: "route" as const, id: r.href, label: r.label, hint: "Go to page", href: r.href }));

  const results = [...routes, ...beliefs];

  useEffect(() => { opener.current = document.activeElement; return () => (opener.current as HTMLElement | null)?.focus?.(); }, []);
  useEffect(() => { setI(0); }, [q]);

  const onKey = useCallback((e: React.KeyboardEvent) => {
    if (e.key === "Escape") { e.preventDefault(); onClose(); return; }
    if (e.key === "ArrowDown") { e.preventDefault(); setI(v => Math.min(v + 1, results.length - 1)); }
    if (e.key === "ArrowUp") { e.preventDefault(); setI(v => Math.max(v - 1, 0)); }
    if (e.key === "Enter" && results[i]) {
      e.preventDefault();
      listRef.current?.querySelectorAll<HTMLAnchorElement>("a")[i]?.click();
    }
  }, [results, i, onClose]);

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center px-4 pt-[12vh]"
      onClick={onClose}>
      <div className="absolute inset-0 bg-black/35" aria-hidden="true" />
      <div role="dialog" aria-modal="true" aria-label="Search"
        onClick={e => e.stopPropagation()} onKeyDown={onKey}
        className="anim-rise panel relative w-full max-w-lg overflow-hidden">
        <div className="flex items-center gap-2 border-b px-3">
          <Search className="h-4 w-4 shrink-0 text-faint" aria-hidden="true" />
          <input autoFocus value={q} onChange={e => setQ(e.target.value)}
            placeholder="Search beliefs and pages…"
            aria-label="Search beliefs and pages"
            role="combobox" aria-expanded aria-controls="palette-results"
            aria-activedescendant={results[i] ? `palette-${i}` : undefined}
            className="h-12 w-full bg-transparent text-sm outline-none placeholder:text-faint" />
          <kbd className="mono hidden shrink-0 rounded-sm border bg-raised px-1.5 text-2xs text-faint sm:block">esc</kbd>
        </div>
        <div id="palette-results" ref={listRef} role="listbox" aria-label="Results"
          className="max-h-[min(60vh,22rem)] overflow-y-auto p-1.5">
          {results.length === 0 && (
            <p className="px-3 py-8 text-center text-sm text-muted">
              {q ? "No matches" : "Type to search beliefs and pages"}
            </p>
          )}
          {results.map((r, n) => (
            <Link key={r.kind + r.id} id={`palette-${n}`} role="option" aria-selected={n === i}
              href={r.href} onClick={onClose} onMouseEnter={() => setI(n)}
              className={cn("flex h-11 items-center justify-between gap-3 rounded px-3 text-sm",
                n === i ? "bg-chip text-fg" : "text-muted")}>
              <span className="truncate">{r.label}</span>
              <span className="mono shrink-0 text-2xs text-faint">{r.hint}</span>
            </Link>
          ))}
        </div>
      </div>
    </div>
  );
}

/** Server health, on every screen.
 *
 *  Self-healing is worth nothing if you only find out it happened by visiting a
 *  page you had no reason to visit. This sits in the top bar so a degraded or
 *  failed component is visible wherever you are, and stays deliberately quiet
 *  when everything is healthy. A permanent green badge is noise, and noise is
 *  what people learn to stop seeing. */
function HealthIndicator() {
  const { project } = useApp();
  const { data, isError, isPending } = useQuery({
    queryKey: ["healing", project],
    queryFn: () => api.healing(project),
    refetchInterval: 15000,
    enabled: !!project,
    retry: false,
  });
  if (isPending || (!data && !isError)) return null;

  // An unreadable health endpoint gets its own mark rather than disappearing.
  // Returning null on error meant a 403 or an unreachable server rendered
  // exactly like a healthy one: the failure mode looked like the success.
  const state = isError || !data ? "unreadable" : data.overall;
  const tone = state === "unreadable" ? "closed"
    : state === "healthy" ? "believed"
    : state === "failed" ? "conflict"
    : state === "unknown" ? "closed" : "unknown";
  const bad = state !== "healthy" && state !== "unknown" && state !== "unreadable";
  const broken = data ? data.components.filter(c => c.status !== "healthy").length : 0;
  const label = state === "unreadable" ? "Health unreadable" : `System health: ${state}`;

  return (
    <Link href="/healing" title={label}
      className={cn("panel panel-link tap flex h-9 items-center gap-2 px-2.5", bad && "border-[color:var(--conflict)]")}>
      <span className={cn("led", tone)} aria-hidden="true" />
      {/* Only the interesting states get words. Healthy is just the mark. */}
      {bad && (
        <span className="hidden text-2xs font-medium text-conflict sm:block">
          {broken > 1 ? `${broken} components` : state}
        </span>
      )}
      <span className="sr-only">{label}</span>
    </Link>
  );
}

/**
 * The server is not answering.
 *
 * This is the single most likely first screen for someone following the
 * quickstart, and it was an unstyled paragraph with a hard-coded `#64748b`,
 * `fontFamily: system-ui`, and the instruction to "refresh" — a dead end in a
 * typeface the product does not use. It now says what is wrong, gives the exact
 * command, and retries in place.
 */
function ServerDown({ onRetry }: { onRetry: () => void }) {
  return (
    <div className="grid min-h-screen place-items-center px-5">
      <div className="w-full max-w-md">
        <div className="flex items-center gap-2.5">
          <span className="led unknown" aria-hidden="true" />
          <h1 className="text-md font-semibold">The OMEM server isn&rsquo;t answering</h1>
        </div>
        <p className="mt-3 text-sm leading-relaxed text-muted">
          The dashboard talks to a local server and cannot reach one. Start it in
          a terminal, then retry.
        </p>
        <pre className="mono mt-4 overflow-x-auto rounded-md border bg-panel px-4 py-3 text-xs">omem-server</pre>
        <div className="mt-5 flex flex-wrap gap-3">
          <button onClick={onRetry}
            className="on-accent inline-flex h-control-lg items-center rounded-md bg-accent px-5 text-sm font-medium text-accentFg transition-[background-color,transform] duration-1 ease-out hover:bg-accentHover active:scale-[0.98]">
            Retry
          </button>
          <Link href="/docs/quickstart"
            className="inline-flex h-control-lg items-center rounded-md border border-[color:var(--line-strong)] px-5 text-sm font-medium transition-colors duration-1 ease-out hover:bg-raised">
            Read the quickstart
          </Link>
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
    <div className="grid min-h-screen place-items-center px-5 py-10">
      <form onSubmit={submit} className="w-full max-w-sm">
        <div className="mb-8 flex items-center gap-2.5">
          <Image src="/omem-mark.png" alt="" width={24} height={24}
                 unoptimized className="h-6 w-6" />
          <span className="text-md font-semibold">OMEM</span>
        </div>

        <h1 className="display text-lg">{register ? "Create an account" : "Sign in"}</h1>
        <p className="mt-1.5 text-sm text-muted">
          This server requires a password. OMEM is free while it is in beta.
        </p>

        <div className="mt-7 space-y-4">
          <div>
            <label htmlFor="email" className="mb-1.5 block text-sm font-medium">Email</label>
            <input id="email" type="email" required value={email} onChange={e => setEmail(e.target.value)}
              autoComplete="username" className="field" />
          </div>
          <div>
            <label htmlFor="password" className="mb-1.5 block text-sm font-medium">Password</label>
            <input id="password" type="password" required value={password} onChange={e => setPassword(e.target.value)}
              autoComplete={register ? "new-password" : "current-password"}
              minLength={register ? 10 : undefined}
              aria-describedby={register ? "pw-hint" : undefined}
              className="field" />
            {register && <p id="pw-hint" className="mt-1.5 text-2xs text-muted">At least 10 characters.</p>}
          </div>
          {needsCode && (
            <div>
              <label htmlFor="code" className="mb-1.5 block text-sm font-medium">Authentication code</label>
              <input id="code" inputMode="numeric" autoComplete="one-time-code" value={code}
                onChange={e => setCode(e.target.value)} className="field mono" />
            </div>
          )}
        </div>

        {/* Announced, not just drawn. An error that only appears visually is an
            error a screen-reader user submits into twice. */}
        <div role="alert" aria-live="assertive">
          {err && (
            <p className="mt-4 flex items-start gap-2 rounded border border-[color:var(--conflict)]/40 bg-conflictBg px-3 py-2.5 text-xs leading-relaxed text-conflict">
              <span className="led conflict mt-[3px] shrink-0" aria-hidden="true" />
              {err}
            </p>
          )}
        </div>

        <button type="submit" disabled={busy}
          className="on-accent mt-6 inline-flex h-control-lg w-full items-center justify-center rounded-md bg-accent text-sm font-medium text-accentFg transition-[background-color,transform] duration-1 ease-out hover:bg-accentHover active:scale-[0.99] disabled:opacity-50 disabled:active:scale-100">
          {busy ? "Working…" : register ? "Create account" : "Sign in"}
        </button>
        <button type="button" onClick={() => { setRegister(v => !v); setErr(null); }}
          className="mt-3 h-11 w-full text-center text-sm text-muted hover:text-fg hover:underline">
          {register ? "I already have an account" : "Create an account"}
        </button>
      </form>
    </div>
  );
}
