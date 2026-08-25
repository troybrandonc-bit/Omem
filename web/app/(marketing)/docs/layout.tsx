"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { MarketingNav, MarketingFooter } from "@/components/marketing/chrome";
import { useScrolled } from "@/lib/use-scrolled";
import { cn } from "@/lib/cn";

/* The docs shell.
 *
 * The sidebar was `hidden md:block` with nothing in its place, so on a phone the
 * documentation had no table of contents and no way to move between pages
 * except the browser's back button. Below md it becomes a horizontally
 * scrollable rail pinned under the header — the pattern a docs site uses when
 * there is no room for a column, and one that keeps every destination one tap
 * away instead of behind a disclosure nobody opens.
 *
 * Also fixed: the active row was marked with `bg-panel`, which on the light
 * theme is #ffffff on a #faf9f6 ground — a 2% difference that is invisible in
 * most lighting, and the only indication of where you were. Active is now the
 * same 2px ink rule the dashboard sidebar and the primary nav use.
 */

const DOCS_NAV: { group: string; items: { href: string; label: string; note?: string }[] }[] = [
  { group: "Getting started", items: [
    { href: "/docs", label: "Introduction" },
    { href: "/docs/quickstart", label: "Quickstart" },
  ]},
  { group: "Building", items: [
    { href: "/docs/sdk", label: "SDK overview" },
    { href: "/developers", label: "API reference", note: "dashboard" },
    { href: "/playground", label: "Playground", note: "dashboard" },
  ]},
];

const FLAT = DOCS_NAV.flatMap(g => g.items);

export default function DocsLayout({ children }: { children: React.ReactNode }) {
  const path = usePathname();
  const lifted = useScrolled();

  return (
    <div className="reading flex min-h-screen flex-col">
      <MarketingNav />

      {/* mobile: a scrollable rail, because a column does not fit and no nav at
          all is not an option */}
      <nav aria-label="Documentation" className={cn("chrome-bar sticky top-16 z-30 md:hidden", lifted && "is-lifted")}>
        <ul className="gutter flex gap-1 overflow-x-auto py-2">
          {FLAT.map(it => (
            <li key={it.href}>
              <Link href={it.href} aria-current={path === it.href ? "page" : undefined}
                className={cn("flex h-10 items-center whitespace-nowrap rounded-md px-3 text-note",
                  path === it.href ? "bg-chip font-medium text-fg" : "text-muted")}>
                {it.label}
              </Link>
            </li>
          ))}
        </ul>
      </nav>

      <div className="gutter mx-auto flex w-full max-w-page flex-1 gap-12 py-10 lg:gap-16 lg:py-16">
        <nav aria-label="Documentation" className="hidden w-56 shrink-0 md:block">
          <div className="sticky top-24 space-y-7">
            {DOCS_NAV.map(g => (
              <div key={g.group}>
                <h2 className="tech-label mb-2 px-3">{g.group}</h2>
                <ul>
                  {g.items.map(it => {
                    const active = path === it.href;
                    return (
                      <li key={it.href}>
                        <Link href={it.href} aria-current={active ? "page" : undefined}
                          className={cn("relative flex h-10 items-center rounded-md px-3 text-note",
                            "transition-colors duration-1 ease-out",
                            active ? "font-medium text-fg" : "text-muted hover:bg-raised hover:text-fg")}>
                          {active && <span aria-hidden="true"
                            className="absolute left-0 top-1.5 bottom-1.5 w-[2px] rounded-r bg-accent" />}
                          <span className="min-w-0 truncate">{it.label}</span>
                          {/* These two leave the docs for the app, which needs a
                              running server. Say so before the click, not after. */}
                          {it.note && <span className="ml-auto shrink-0 text-caption text-faint">{it.note}</span>}
                        </Link>
                      </li>
                    );
                  })}
                </ul>
              </div>
            ))}
          </div>
        </nav>

        <main id="main" tabIndex={-1} className="min-w-0 flex-1">{children}</main>
      </div>

      <MarketingFooter />
    </div>
  );
}
