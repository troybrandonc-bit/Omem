"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/cn";
import { useApp } from "@/components/providers";
import { Sun, Moon, ChevronDown, Share2 } from "lucide-react";

function Wordmark() {
  return (
    <Link href="/" className="flex items-center gap-2">
      <span className="grid h-6 w-6 place-items-center rounded-pill bg-accent text-white">
        <Share2 className="h-3 w-3" />
      </span>
      <span className="text-[16px] font-bold tracking-tight">OMEM</span>
    </Link>
  );
}

const MENUS: { label: string; items: { label: string; href: string }[] }[] = [
  { label: "Product", items: [
    { label: "Memory explorer", href: "/memory" }, { label: "Playground", href: "/playground" },
    { label: "Time travel", href: "/timeline" }, { label: "Conflicts", href: "/conflicts" },
  ]},
  { label: "Developers", items: [
    { label: "Documentation", href: "/docs" }, { label: "Quickstart", href: "/docs/quickstart" },
    { label: "SDK", href: "/docs/sdk" }, { label: "API reference", href: "/developers" },
  ]},
  { label: "Enterprise", items: [
    { label: "Security", href: "/security" }, { label: "Deployment", href: "/security" },
  ]},
];
const FLAT = [
  { label: "Pricing", href: "/pricing" },
  { label: "Docs", href: "/docs" },
  { label: "Changelog", href: "/changelog" },
];

export function MarketingNav() {
  const path = usePathname();
  const { theme, toggleTheme } = useApp();
  return (
    <header className="sticky top-0 z-40 border-b bg-panel">
      <div className="mx-auto flex h-[60px] max-w-[1200px] items-center justify-between px-6">
        <Wordmark />
        <nav className="hidden items-center gap-1 md:flex">
          {MENUS.map(m => (
            <div key={m.label} className="group relative">
              <button className="flex items-center gap-1 rounded-md px-3 py-2 text-[14px] font-medium text-fg/85 transition-colors hover:text-fg">
                {m.label} <ChevronDown className="h-3.5 w-3.5 text-faint transition-transform group-hover:rotate-180" />
              </button>
              <div className="invisible absolute left-0 top-full pt-1 opacity-0 transition-all group-hover:visible group-hover:opacity-100">
                <div className="panel min-w-44 p-1.5">
                  {m.items.map(it => (
                    <Link key={it.label} href={it.href}
                      className="block rounded-md px-3 py-2 text-[13px] text-muted transition-colors hover:bg-raised hover:text-fg">
                      {it.label}
                    </Link>
                  ))}
                </div>
              </div>
            </div>
          ))}
          {FLAT.map(n => (
            <Link key={n.label} href={n.href}
              className={cn("rounded-md px-3 py-2 text-[14px] font-medium transition-colors",
                path?.startsWith(n.href) ? "text-fg" : "text-fg/85 hover:text-fg")}>
              {n.label}
            </Link>
          ))}
        </nav>
        <div className="flex items-center gap-2">
          <button onClick={toggleTheme} aria-label="Toggle theme"
            className="rounded-md p-2 text-muted transition-colors hover:text-fg">
            {theme === "dark" ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
          </button>
          <Link href="/overview" className="hidden rounded-md px-3 py-2 text-[14px] font-medium text-fg/85 transition-colors hover:text-fg sm:block">
            Sign in
          </Link>
          <Link href="/onboarding"
            className="rounded-md bg-accent px-4 py-2 text-[14px] font-semibold text-white transition-opacity duration-[120ms] hover:opacity-[0.88]">
            Start building
          </Link>
        </div>
      </div>
    </header>
  );
}

export function MarketingFooter() {
  const links = [
    { label: "Docs", href: "/docs" }, { label: "Quickstart", href: "/docs/quickstart" },
    { label: "SDK", href: "/docs/sdk" }, { label: "Pricing", href: "/pricing" },
    { label: "Security", href: "/security" }, { label: "Changelog", href: "/changelog" },
    { label: "Dashboard", href: "/overview" },
  ];
  return (
    <footer className="mt-32 border-t bg-panel">
      <div className="mx-auto flex max-w-[1200px] flex-col gap-4 px-6 py-8 md:flex-row md:items-center md:justify-between">
        <div className="flex flex-wrap items-center gap-x-5 gap-y-2">
          <Wordmark />
          {links.map(l => (
            <Link key={l.label} href={l.href} className="text-[13px] text-muted transition-colors hover:text-fg">{l.label}</Link>
          ))}
        </div>
        <div className="num text-2xs text-faint">© {new Date().getFullYear()} OMEM / Protocol 1.0 / CTS 29-29</div>
      </div>
    </footer>
  );
}

export function MarketingShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen">
      <MarketingNav />
      {children}
      <MarketingFooter />
    </div>
  );
}
