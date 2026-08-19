"use client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createContext, useContext, useEffect, useState } from "react";

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
  const [project, setProjectState] = useState("demo");
  const setProject = (p: string) => { setProjectState(p); if (typeof window !== "undefined") localStorage.setItem("omem-project", p); };
  useEffect(() => { const saved = localStorage.getItem("omem-project"); if (saved) setProjectState(saved); }, []);
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
