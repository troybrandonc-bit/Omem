"use client";
import Image from "next/image";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { cn } from "@/lib/cn";
import { useApp } from "@/components/providers";
import { useScrolled } from "@/lib/use-scrolled";
import { Sun, Moon, Menu, X } from "lucide-react";

/* The marketing chrome.
 *
 * Two things were broken here, both of the kind that never show up on a desktop
 * screenshot:
 *
 * 1. THE NAVIGATION DID NOT EXIST ON A PHONE. The whole <nav> was
 *    `hidden md:flex`, with no drawer and no fallback, so below 768px the site
 *    had a logo and a button and no way to reach docs, pricing, security or the
 *    changelog. That is most of the traffic a launch post sends.
 *
 * 2. THE MENUS WERE HOVER-ONLY. Three dropdowns opened on `group-hover` with no
 *    click handler, no `aria-expanded`, and no focus behaviour, so they were
 *    unreachable by keyboard AND unreachable by touch: hover is not an
 *    interaction a finger has.
 *
 * The fix for (2) is not a better dropdown, it is fewer of them. The dropdowns
 * held two kinds of link: four marketing pages, and four DASHBOARD routes
 * (memory explorer, playground, timeline, conflicts) that need a running local
 * server. Sending a first-time reader from a public page into an app that
 * answers "Waiting for the OMEM server…" is worse than not linking it. So the
 * nav is flat and is exactly the public surface, with one labelled door to the
 * dashboard for people who already have it running.
 */

function Wordmark({ className }: { className?: string }) {
  return (
    <Link href="/" className={cn("flex items-center gap-2.5 rounded", className)}>
      {/* The actual OMEM mark, not a drawn stand-in. Served at 256px so it
          stays sharp on retina at this 24px display size. */}
      <Image src="/omem-mark.png" alt="" width={24} height={24} unoptimized
             className="h-6 w-6 shrink-0" />
      <span className="text-lg font-semibold tracking-[-0.02em]">OMEM</span>
      <span className="sr-only">home</span>
    </Link>
  );
}

const NAV = [
  { label: "Accountability", href: "/accountability" },
  { label: "Objective", href: "/objectives" },
  { label: "Docs", href: "/docs" },
  { label: "Guides", href: "/guides" },
  { label: "Compare", href: "/compare" },
  { label: "Pricing", href: "/pricing" },
  { label: "Security", href: "/security" },
  { label: "Changelog", href: "/changelog" },
];

function isActive(path: string | null, href: string) {
  if (!path) return false;
  return href === "/" ? path === "/" : path === href || path.startsWith(href + "/");
}

function ThemeToggle({ className }: { className?: string }) {
  const { theme, toggleTheme } = useApp();
  const [mounted, setMounted] = useState(false);
  // The label has to name the state the control moves TO, and that is not known
  // on the server. Swapping the icon only after mount keeps the markup from
  // claiming "switch to dark" on a page that is already dark.
  useEffect(() => setMounted(true), []);
  const dark = mounted && theme === "dark";
  return (
    <button onClick={toggleTheme}
      aria-pressed={mounted ? theme === "dark" : undefined}
      aria-label={dark ? "Switch to light theme" : "Switch to dark theme"}
      className={cn("tap grid h-10 w-10 place-items-center rounded-md text-muted",
        "transition-colors duration-1 ease-out hover:bg-raised hover:text-fg", className)}>
      {dark ? <Sun className="h-[18px] w-[18px]" /> : <Moon className="h-[18px] w-[18px]" />}
    </button>
  );
}

export function MarketingNav() {
  const path = usePathname();
  const lifted = useScrolled();
  const [open, setOpen] = useState(false);
  const toggleRef = useRef<HTMLButtonElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);

  // Close on route change: a drawer that survives navigation covers the page
  // the reader just asked for.
  useEffect(() => { setOpen(false); }, [path]);

  // Escape closes and returns focus to the control that opened it, and the page
  // behind stops scrolling while the sheet is up.
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") { setOpen(false); toggleRef.current?.focus(); }
    };
    document.addEventListener("keydown", onKey);
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    panelRef.current?.querySelector<HTMLElement>("a,button")?.focus();
    return () => { document.removeEventListener("keydown", onKey); document.body.style.overflow = prev; };
  }, [open]);

  return (
    /* The scroll edge. The hairline and the blur arrive when content starts
       passing underneath, rather than being painted permanently across the top
       of a page nobody has scrolled yet. While the drawer is open the bar is
       lifted regardless: it is over the sheet at that point whatever the scroll
       position says. */
    <header className={cn("chrome-bar sticky top-0 z-40", (lifted || open) && "is-lifted")}>
      <div className="gutter mx-auto flex h-16 max-w-shell items-center justify-between gap-4">
        <Wordmark />

        <nav aria-label="Primary" className="hidden items-center gap-0.5 md:flex">
          {NAV.map(n => {
            const active = isActive(path, n.href);
            return (
              <Link key={n.href} href={n.href} aria-current={active ? "page" : undefined}
                className={cn("relative flex h-10 items-center rounded-md px-3 text-note font-medium",
                  "transition-colors duration-1 ease-out",
                  active ? "text-fg" : "text-muted hover:text-fg")}>
                {n.label}
                {/* Active is marked with a rule, not only a colour shift, so it
                    reads in greyscale and to anyone who cannot separate the two
                    ink levels. */}
                {active && <span aria-hidden="true" className="absolute inset-x-3 bottom-1 h-[2px] rounded-full bg-accent" />}
              </Link>
            );
          })}
        </nav>

        <div className="flex items-center gap-1">
          <ThemeToggle />
          <Link href="/overview"
            className="hidden h-10 shrink-0 items-center justify-center whitespace-nowrap rounded-md px-3 text-sm font-medium leading-none text-muted transition-colors duration-1 ease-out hover:bg-raised hover:text-fg sm:flex">
            Dashboard
          </Link>
          <Link href="/docs/quickstart"
            className="on-accent hidden h-10 shrink-0 items-center justify-center whitespace-nowrap rounded-md bg-accent px-5 text-sm font-medium leading-none text-accentFg transition-[background-color,transform] duration-1 ease-out hover:bg-accentHover active:scale-[0.98] sm:flex">
            Get started
          </Link>

          <button ref={toggleRef} onClick={() => setOpen(v => !v)}
            aria-expanded={open} aria-controls="mobile-nav"
            className="tap grid h-10 w-10 place-items-center rounded-md text-fg transition-colors duration-1 ease-out hover:bg-raised md:hidden">
            {open ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
            <span className="sr-only">{open ? "Close menu" : "Open menu"}</span>
          </button>
        </div>
      </div>

      {/* The drawer. Rows are 48px because this is the touch surface, and it
          carries the same two actions the desktop bar does rather than a
          reduced version of them. */}
      {open && (
        <div id="mobile-nav" ref={panelRef}
          className="anim-fade border-t bg-bg md:hidden"
          style={{ paddingBottom: "env(safe-area-inset-bottom)" }}>
          <nav aria-label="Primary" className="gutter mx-auto max-w-shell py-2">
            {NAV.map(n => {
              const active = isActive(path, n.href);
              return (
                <Link key={n.href} href={n.href} aria-current={active ? "page" : undefined}
                  className={cn("flex h-12 items-center rounded-md px-3 text-body font-medium",
                    active ? "bg-chip text-fg" : "text-muted")}>
                  {n.label}
                </Link>
              );
            })}
            <div className="mt-2 flex flex-col gap-2 border-t pt-3">
              <Link href="/docs/quickstart"
                className="on-accent flex h-12 items-center justify-center rounded-md bg-accent text-note font-medium text-accentFg">
                Get started
              </Link>
              <Link href="/overview"
                className="flex h-12 items-center justify-center rounded-md border border-[color:var(--line-strong)] text-note font-medium">
                Open the dashboard
              </Link>
            </div>
          </nav>
        </div>
      )}
    </header>
  );
}

const FOOTER = [
  { group: "Start", items: [
    { label: "Quickstart", href: "/docs/quickstart" },
    { label: "Documentation", href: "/docs" },
    { label: "SDK reference", href: "/docs/sdk" },
  ]},
  { group: "Product", items: [
    { label: "Accountability", href: "/accountability" },
    { label: "Pricing", href: "/pricing" },
    { label: "Security", href: "/security" },
    { label: "Guides", href: "/guides" },
    { label: "Compare", href: "/compare" },
    { label: "Changelog", href: "/changelog" },
    { label: "Objectives", href: "/objectives" },
    { label: "The commons", href: "/commons" },
    { label: "Claims ledger", href: "/claims" },
  ]},
  { group: "Run it", items: [
    { label: "Dashboard", href: "/overview" },
    { label: "Source on GitHub", href: "https://github.com/troybrandonc-bit/Omem", external: true },
    { label: "Report an issue", href: "https://github.com/troybrandonc-bit/Omem/issues", external: true },
    { label: "Privacy", href: "/privacy" },
    { label: "Terms", href: "/terms" },
  ]},
];

export function MarketingFooter() {
  return (
    <footer className="mt-24 border-t">
      <div className="gutter mx-auto max-w-shell py-14">
        <div className="grid gap-10 sm:grid-cols-2 lg:grid-cols-[1.4fr_repeat(3,minmax(0,1fr))]">
          <div>
            <Wordmark />
            <p className="mt-4 max-w-[32ch] text-note text-muted">
              Keeps AI agents answerable: prove why it acted, approve before it
              does. Built on a memory that keeps both sides of a contradiction.
            </p>
          </div>
          {FOOTER.map(col => (
            <nav key={col.group} aria-label={col.group}>
              <h2 className="tech-label mb-3">{col.group}</h2>
              <ul className="space-y-0.5">
                {col.items.map(l => (
                  <li key={l.label}>
                    {l.external
                      ? <a href={l.href} rel="noreferrer"
                          className="-mx-2 flex h-10 items-center rounded px-2 text-note text-muted transition-colors duration-1 ease-out hover:text-fg">
                          {l.label}
                        </a>
                      : <Link href={l.href}
                          className="-mx-2 flex h-10 items-center rounded px-2 text-note text-muted transition-colors duration-1 ease-out hover:text-fg">
                          {l.label}
                        </Link>}
                  </li>
                ))}
              </ul>
            </nav>
          ))}
        </div>

        <div className="mt-12 flex flex-col gap-2 border-t pt-6 text-caption text-faint sm:flex-row sm:items-center sm:justify-between">
          {/* No `new Date()` here. It ran on the server at build time and again
              on the client, and across a New Year those disagree, a hydration
              mismatch in the footer of every page. The wheel is versioned; the
              year was not load-bearing. */}
          <span>MIT licensed. Free while in beta.</span>
          {/* "CTS 29/29" sat in the footer of every page. ENGINE_VALIDATION.md
              says the suite behind that figure is not in this repository and it
              "should not be read as independent validation", so the strongest
              claim on the site was the one thing the project cannot show. The
              engine's frozen version is checkable; the conformance score is not. */}
          <span className="mono">OMEM Protocol 1.0 · engine 1.0.0 (frozen)</span>
        </div>
      </div>
    </footer>
  );
}

/**
 * The wrapper every marketing and docs page uses.
 *
 * `.reading` is applied here, once: this is where the 13px instrument base
 * becomes a 16-17px document base. `#main` is the skip-link target and the
 * page's only <main>, which is the landmark a screen reader jumps to.
 */
export function MarketingShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="reading flex min-h-screen flex-col">
      <MarketingNav />
      {/* `wash-host` carries the background gradient behind the top of every
          public page. It lives here rather than on each page's first section
          because <main> is the only element that is already the full width of
          the document. See the note on `.wash-host` in globals.css for why the
          usual 100vw full-bleed trick is not safe. */}
      <main id="main" tabIndex={-1} className="wash-host flex-1">{children}</main>
      <MarketingFooter />
    </div>
  );
}
