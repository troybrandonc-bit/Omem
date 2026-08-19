"use client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createContext, useContext, useEffect, useState } from "react";
import { api, type Project } from "@/lib/api";

const qc = new QueryClient({ defaultOptions: { queries: { refetchOnWindowFocus: false, staleTime: 2000 } } });

// Global product state: current project, the as-of logical time (null = now), theme.
interface Ctx {
  project: string; setProject: (p: string) => void;
  asOf: number | null; setAsOf: (t: number | null) => void;  // null => now
  now: number; setNow: (n: number) => void;
  theme: "dark" | "light"; toggleTheme: () => void;
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

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const saved = localStorage.getItem("omem-project");
      let list: Project[] = [];
      try {
        list = (await api.projects()).data || [];
      } catch {
        // server not up yet — Shell shows the waiting state and this retries on
        // the next mount rather than pinning a project that may not exist.
        return;
      }
      if (cancelled || !list.length) return;
      // Keep the saved choice only if it still exists. A stale id in
      // localStorage is the other way this ends up querying a phantom project.
      if (saved && list.some(p => p.id === saved)) {
        setProjectState(saved);
        return;
      }
      // Otherwise the project that actually has memories in it. `/v1/projects`
      // already returns the counts, so this lands on the one the SDK has been
      // writing to rather than whichever happens to sort first.
      const real = list.filter(p => !p.is_demo);
      const pick = [...(real.length ? real : list)]
        .sort((a, b) => (b.assertions ?? 0) - (a.assertions ?? 0))[0];
      setProjectState(pick.id);
      localStorage.setItem("omem-project", pick.id);
    })();
    return () => { cancelled = true; };
  }, []);
  const [asOf, setAsOf] = useState<number | null>(null);
  const [now, setNow] = useState(0);
  const [theme, setTheme] = useState<"dark" | "light">("light");

  useEffect(() => {
    const saved = (localStorage.getItem("omem-theme") as "dark" | "light") || "light";
    setTheme(saved);
  }, []);
  useEffect(() => {
    document.documentElement.classList.toggle("dark", theme === "dark");
    localStorage.setItem("omem-theme", theme);
  }, [theme]);

  return (
    <QueryClientProvider client={qc}>
      <AppCtx.Provider value={{ project, setProject, asOf, setAsOf, now, setNow, theme, toggleTheme: () => setTheme(t => t === "dark" ? "light" : "dark") }}>
        {children}
      </AppCtx.Provider>
    </QueryClientProvider>
  );
}
