"use client";
import Image from "next/image";
import Link from "next/link";
import { useEffect, useState } from "react";
import { cn } from "@/lib/cn";
import { useApp } from "@/components/providers";
import { useScrolled } from "@/lib/use-scrolled";
import { Sun, Moon } from "lucide-react";

/* The commons wears its OWN chrome, not the product's.
 *
 * On the collector the whole domain is the commons, so it should read as its
 * own site: a wordmark that says "commons", links that are about the commons
 * (the dataset, how it works, contributing), and a footer that credits the
 * engine underneath rather than a full product nav for docs, pricing and
 * compare. Same design tokens, different site. */

const GITHUB = "https://github.com/troybrandonc-bit/Omem";

const LINKS = [
  { label: "How it works", href: "#how" },
  { label: "The dataset", href: "#dataset" },
  { label: "Contribute", href: "#contribute" },
];

function ThemeToggle() {
  const { theme, toggleTheme } = useApp();
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);
  const dark = mounted && theme === "dark";
  return (
    <button onClick={toggleTheme}
      aria-label={dark ? "Switch to light theme" : "Switch to dark theme"}
      className="tap grid h-10 w-10 place-items-center rounded-md text-muted transition-colors duration-1 ease-out hover:bg-raised hover:text-fg">
      {dark ? <Sun className="h-[18px] w-[18px]" /> : <Moon className="h-[18px] w-[18px]" />}
    </button>
  );
}

export function CommonsShell({ children }: { children: React.ReactNode }) {
  const lifted = useScrolled();
  return (
    <div className="reading flex min-h-screen flex-col">
      <header className={cn("chrome-bar sticky top-0 z-40", lifted && "is-lifted")}>
        <div className="gutter mx-auto flex h-16 max-w-shell items-center gap-6">
          <Link href="/commons" className="flex items-center gap-2.5 rounded">
            <Image src="/omem-mark.png" alt="" width={24} height={24} unoptimized className="h-6 w-6 shrink-0" />
            <span className="text-lg font-semibold tracking-[-0.02em]">OMEM</span>
            <span className="rounded-sm border px-1.5 py-0.5 text-2xs font-medium uppercase tracking-wide text-muted">commons</span>
          </Link>
          <nav aria-label="Commons" className="ml-auto hidden items-center gap-1 sm:flex">
            {LINKS.map(l => (
              <a key={l.href} href={l.href}
                className="rounded px-3 py-2 text-note text-muted transition-colors duration-1 ease-out hover:text-fg">
                {l.label}
              </a>
            ))}
          </nav>
          <div className="flex items-center gap-1 sm:ml-0 ml-auto">
            <a href={GITHUB} rel="noreferrer"
              className="rounded px-3 py-2 text-note text-muted transition-colors duration-1 ease-out hover:text-fg">
              GitHub
            </a>
            <ThemeToggle />
          </div>
        </div>
      </header>

      <main id="main" tabIndex={-1} className="wash-host flex-1">{children}</main>

      <footer className="mt-24 border-t">
        <div className="gutter mx-auto flex max-w-shell flex-wrap items-center justify-between gap-4 py-10">
          <div className="flex items-center gap-2.5">
            <Image src="/omem-mark.png" alt="" width={20} height={20} unoptimized className="h-5 w-5" />
            <span className="text-note text-muted">
              The OMEM commons. Anonymous behavioural counts, CC BY 4.0.
            </span>
          </div>
          <div className="flex items-center gap-5 text-note text-muted">
            <a href={GITHUB} rel="noreferrer" className="hover:text-fg">Built on OMEM</a>
            <Link href="/docs" className="hover:text-fg">What OMEM is</Link>
          </div>
        </div>
      </footer>
    </div>
  );
}
