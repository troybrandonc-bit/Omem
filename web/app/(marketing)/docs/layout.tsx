"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { MarketingNav, MarketingFooter } from "@/components/marketing/chrome";
import { cn } from "@/lib/cn";

const DOCS_NAV: { group: string; items: { href: string; label: string }[] }[] = [
  { group: "Getting started", items: [
    { href: "/docs", label: "Introduction" },
    { href: "/docs/quickstart", label: "Quickstart" },
  ]},
  { group: "Building", items: [
    { href: "/docs/sdk", label: "SDK overview" },
    { href: "/developers", label: "API reference" },
    { href: "/playground", label: "Playground" },
  ]},
];

export default function DocsLayout({ children }: { children: React.ReactNode }) {
  const path = usePathname();
  return (
    <div className="min-h-screen">
      <MarketingNav />
      <div className="mx-auto flex max-w-6xl gap-10 px-6 py-12">
        <aside className="hidden w-52 shrink-0 md:block">
          <div className="sticky top-24 space-y-6">
            {DOCS_NAV.map(g => (
              <div key={g.group}>
                <div className="mb-2 text-2xs font-semibold uppercase tracking-[0.08em] text-muted">{g.group}</div>
                <ul className="space-y-0.5">
                  {g.items.map(it => (
                    <li key={it.href}>
                      <Link href={it.href}
                        className={cn("block rounded-md px-2 py-1.5 text-sm transition",
                          path === it.href ? "bg-panel font-medium text-fg" : "text-muted hover:text-fg")}>
                        {it.label}
                      </Link>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </aside>
        <main className="min-w-0 flex-1">{children}</main>
      </div>
      <MarketingFooter />
    </div>
  );
}
