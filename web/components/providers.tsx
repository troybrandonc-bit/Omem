"use client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createContext, useContext, useEffect, useState } from "react";
import { usePathname } from "next/navigation";
import { api, getSession, setSession, type Project, type AuthMode } from "@/lib/api";
import { isMarketingRoute } from "@/lib/routes";

const qc = new QueryClient({ defaultOptions: { queries: { refetchOnWindowFocus: false, staleTime: 2000 } } });

/* How far the app has got in starting up. `ready` is the only state in which a
   product page may mount, and it means BOTH a session and a project have been
   resolved — see the bootstrap effect for why that pairing is the whole point. */
export type Boot = "connecting" | "ready" | "signin" | "unreachable";

// Global product state: current project, the as-of logical time (null = now), theme.
interface Ctx {
  project: string; setProject: (p: string) => void;
  asOf: number | null; setAsOf: (t: number | null) => void;  // null => now
  now: number; setNow: (n: number) => void;
  theme: "dark" | "light"; toggleTheme: () => void;
  boot: Boot; mode: AuthMode | null; retryBoot: () => void;
}
const AppCtx = createContext<Ctx>(null as any);
export const useApp = () => useContext(AppCtx);

export function Providers({ children }: { children: React.ReactNode }) {
  // "" until a real project id is known, NOT "demo".
  //
  // It used to default to the literal string "demo", and the demo project only
  // exists when OMEM_SEED_DEMO=1, which it is not by default. So a fresh install
  // pointed every query at a project that did not exist: the dashboard came up
  // empty and stayed empty no matter how many memories the SDK had written. The
  // data was there the whole time; the dashboard was asking about a phantom.
  const [project, setProjectState] = useState("");
  const setProject = (p: string) => { setProjectState(p); if (typeof window !== "undefined") localStorage.setItem("omem-project", p); };

  /* The public site does not have a project, and must not ask for one.
     `Shell` already returns its children untouched on these routes, so nothing
     below this provider consumes `project` there — but this effect sits ABOVE
     Shell and ran anyway, opening a request to the dashboard API on every
     landing-page and docs visit. For the people those pages are written for,
     that request cannot succeed: they do not have a server yet. See
     lib/routes.ts. */
  const path = usePathname();
  const isMarketing = isMarketingRoute(path);

  const [boot, setBoot] = useState<Boot>("connecting");
  const [mode, setMode] = useState<AuthMode | null>(null);
  const [attempt, setAttempt] = useState(0);
  const retryBoot = () => { setBoot("connecting"); setAttempt(a => a + 1); };

  /* ONE bootstrap, in order: health -> session -> project.
   *
   * These three used to run in two places that could not see each other.
   * `Shell` provisioned the session; this provider, which sits ABOVE Shell,
   * listed projects. Nothing sequenced them, so on a browser with no stored
   * session they raced: this effect called /v1/projects first, got a 401
   * because Shell had not signed up yet, hit the `catch` below and returned.
   * Its dependency list did not include anything that changes when Shell
   * finishes, so it never ran again. `project` stayed "" for the life of the
   * page, every query went out as `?project=` and 404ed, and every screen
   * rendered its empty state — on a server with data in it.
   *
   * That is the first thing a new user sees, and it reported "No conflicts"
   * over the top of a real contradiction. Sequencing is the fix: a session is a
   * precondition for listing projects, so it is awaited rather than hoped for.
   */
  useEffect(() => {
    if (isMarketing) return;
    let cancelled = false;
    (async () => {
      // 1. Which mode is the server in? Only the server knows, and the answer
      //    decides whether a missing session is provisioned or asked for.
      let m: AuthMode;
      try {
        const h = await api.health();
        m = h.auth === "password" ? "password" : "local";
      } catch {
        if (!cancelled) { setMode(null); setBoot("unreachable"); }
        return;
      }
      if (cancelled) return;
      setMode(m);

      // 2. A session, before anything that needs one. Local mode provisions
      //    silently (no passwords, loopback only) which is what makes the
      //    quickstart a minute; password mode must ask.
      if (!getSession()) {
        if (m === "password") { if (!cancelled) setBoot("signin"); return; }
        try {
          const res = await api.signup({ email: "local@omem.dev", project: "My workspace" });
          if (cancelled) return;
          setSession(res.token);
        } catch {
          if (!cancelled) setBoot("unreachable");
          return;
        }
      }

      // 3. Now, and only now, the project. A 401 here is no longer possible by
      //    construction, so a failure is a real one and is reported as such
      //    rather than silently leaving `project` empty.
      const saved = localStorage.getItem("omem-project");
      let list: Project[] = [];
      try {
        list = (await api.projects()).data || [];
      } catch {
        if (!cancelled) setBoot("unreachable");
        return;
      }
      if (cancelled) return;

      if (list.length) {
        // Keep the saved choice only if it still exists. A stale id in
        // localStorage is the other way this ends up querying a phantom project.
        if (saved && list.some(p => p.id === saved)) {
          setProjectState(saved);
        } else {
          // Otherwise the project that actually has memories in it.
          // `/v1/projects` already returns the counts, so this lands on the one
          // the SDK has been writing to rather than whichever sorts first.
          const real = list.filter(p => !p.is_demo);
          const pick = [...(real.length ? real : list)]
            .sort((a, b) => (b.assertions ?? 0) - (a.assertions ?? 0))[0];
          setProjectState(pick.id);
          localStorage.setItem("omem-project", pick.id);
        }
      }
      // `ready` even when the list is empty: that is a real state (a server with
      // no projects) and the panels say so honestly. Staying in `connecting`
      // would hang the whole app on a spinner that never resolves.
      if (!cancelled) setBoot("ready");
    })();
    return () => { cancelled = true; };
    /* `isMarketing`, not `[]`. With an empty array the early return above would
       be permanent for the session: somebody landing on the marketing site and
       then clicking through to the dashboard would carry an empty project id
       into it forever, and every panel would sit empty with no indication why.
       Keyed on the flag rather than on `path` so it re-runs when the surface
       changes, not on every navigation inside the app. */
  }, [isMarketing, attempt]);
  const [asOf, setAsOf] = useState<number | null>(null);
  const [now, setNow] = useState(0);

  /* The inline script in app/layout.tsx has already put the right class on
     <html> before first paint. This reads that back rather than assuming
     "light" and correcting itself a frame later, which is what produced the
     white flash on every navigation for dark-mode users. The lazy initialiser
     runs once, on the client only; on the server it returns the light default
     and the class on <html> is what the browser actually paints. */
  const [theme, setTheme] = useState<"dark" | "light">(() => {
    if (typeof document === "undefined") return "light";
    return document.documentElement.classList.contains("dark") ? "dark" : "light";
  });

  /* Reflect state onto the document. This deliberately does NOT persist:
     persisting here would write a value on mount, and the OS-following effect
     below would then find a "stated preference" that nobody ever stated. Only
     toggleTheme writes. */
  useEffect(() => {
    document.documentElement.classList.toggle("dark", theme === "dark");
    document.documentElement.style.colorScheme = theme;
  }, [theme]);

  /* Follow the OS while the person has not stated a preference of their own.
     Choosing a theme in the product is a stated preference and wins; until
     then, the system switching to dark at sunset should switch this too. */
  useEffect(() => {
    if (localStorage.getItem("omem-theme")) return;
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const sync = (e: MediaQueryListEvent) => setTheme(e.matches ? "dark" : "light");
    mq.addEventListener("change", sync);
    return () => mq.removeEventListener("change", sync);
  }, []);

  const toggleTheme = () => setTheme(t => {
    const next = t === "dark" ? "light" : "dark";
    try { localStorage.setItem("omem-theme", next); } catch { /* private mode */ }
    return next;
  });

  return (
    <QueryClientProvider client={qc}>
      <AppCtx.Provider value={{ project, setProject, asOf, setAsOf, now, setNow, theme, toggleTheme,
                                boot, mode, retryBoot }}>
        {children}
      </AppCtx.Provider>
    </QueryClientProvider>
  );
}
