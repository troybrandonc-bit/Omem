"use client";
import { useRef, useState } from "react";
import Link from "next/link";
import { cn } from "@/lib/cn";
import { Copy, Check } from "lucide-react";

/* The marketing / docs kit.
 *
 * These pages are documents, not instruments, so everything here sits on the
 * reading base (`.reading`, set once by MarketingShell) rather than the 13px
 * dashboard base. The rest of the system — ink levels, state colour, hairline
 * rules, 6px radius — is identical, because it is one product. */

function esc(s: string) {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}
const KW = /\b(from|import|await|const|new|def|return|if|let|func|use|fn|package|async|export)\b/g;
function highlight(line: string) {
  let h = esc(line);
  h = h.replace(/(&quot;|")([^"]*?)(&quot;|")/g, '<span class="code-str">"$2"</span>');
  h = h.replace(KW, '<span class="code-kw">$1</span>');
  h = h.replace(/(#.*$|\/\/.*$)/g, '<span class="code-cm">$1</span>');
  return h;
}

/**
 * A code block, optionally tabbed.
 *
 * The tabs are a real tab set now: role/aria-selected/aria-controls, one tab
 * stop for the whole group, and left/right arrows to move between panels. They
 * were bare <button>s before, which meant a screen reader announced four
 * unlabelled buttons with no indication that they switched one region, and a
 * keyboard user tabbed through every language to get past the block.
 *
 * Tab height is 44px, the platform minimum for a finger, rather than the 34px
 * it was: these are the only controls on a marketing page and they sit on a
 * phone. The code itself is a reading step too — at 12px it was the smallest
 * text on the site, and it is the text a developer came here to read.
 */
export function CodeBlock({ tabs, single, filename, label }:
  { tabs?: { label: string; code: string }[]; single?: string; filename?: string; label?: string }) {
  const items = tabs ?? [{ label: filename ?? "", code: single ?? "" }];
  const tabbed = items.length > 1;
  const [active, setActive] = useState(0);
  const [copied, setCopied] = useState(false);
  const refs = useRef<(HTMLButtonElement | null)[]>([]);
  const id = useRef(`cb-${Math.random().toString(36).slice(2, 8)}`).current;
  const code = items[active].code;
  const lines = code.split("\n");

  function onKey(e: React.KeyboardEvent) {
    const d = e.key === "ArrowRight" ? 1 : e.key === "ArrowLeft" ? -1 : e.key === "Home" ? -active
      : e.key === "End" ? items.length - 1 - active : 0;
    if (!d) return;
    e.preventDefault();
    const next = (active + d + items.length) % items.length;
    setActive(next);
    refs.current[next]?.focus();
  }

  async function copy() {
    try {
      await navigator.clipboard.writeText(code);
      setCopied(true);
      setTimeout(() => setCopied(false), 1600);
    } catch { /* clipboard blocked; the code is selectable either way */ }
  }

  return (
    <figure className="panel lift overflow-hidden">
      <div className="flex items-center justify-between gap-2 border-b">
        <div
          role={tabbed ? "tablist" : undefined}
          aria-label={tabbed ? "Choose a language" : undefined}
          onKeyDown={tabbed ? onKey : undefined}
          className="flex min-w-0 items-center overflow-x-auto">
          {items.map((t, i) => (
            <button key={t.label + i}
              ref={el => { refs.current[i] = el; }}
              role={tabbed ? "tab" : undefined}
              id={tabbed ? `${id}-tab-${i}` : undefined}
              aria-selected={tabbed ? i === active : undefined}
              aria-controls={tabbed ? `${id}-panel` : undefined}
              tabIndex={tabbed ? (i === active ? 0 : -1) : -1}
              onClick={() => setActive(i)}
              className={cn(
                "relative flex h-11 shrink-0 items-center whitespace-nowrap px-4 text-note",
                "transition-colors duration-1 ease-out",
                !tabbed && "mono pointer-events-none text-faint",
                tabbed && (i === active ? "font-medium text-fg" : "text-muted hover:text-fg"))}>
              {t.label}
              {/* the marked line: a 2px ink rule, the same mark the sidebar
                  uses for an active row. Colour alone would not survive a
                  greyscale screenshot. */}
              {tabbed && i === active && (
                <span aria-hidden="true" className="absolute inset-x-2 -bottom-px h-[2px] rounded-t bg-accent" />
              )}
            </button>
          ))}
        </div>
        <button onClick={copy}
          className="tap mr-1 grid h-9 w-9 shrink-0 place-items-center rounded text-muted transition-colors duration-1 ease-out hover:bg-raised hover:text-fg">
          {copied ? <Check className="h-4 w-4 text-believed" /> : <Copy className="h-4 w-4" />}
          <span className="sr-only">{copied ? "Copied" : "Copy code"}</span>
        </button>
        {/* Announced without stealing focus. A silent icon swap tells a sighted
            reader it worked and tells a screen-reader user nothing. */}
        <span role="status" aria-live="polite" className="sr-only">{copied ? "Copied to clipboard" : ""}</span>
      </div>
      <div
        id={tabbed ? `${id}-panel` : undefined}
        role={tabbed ? "tabpanel" : undefined}
        aria-labelledby={tabbed ? `${id}-tab-${active}` : undefined}
        // Focusable because it scrolls: a region a mouse can pan must also be
        // reachable by keyboard, or its overflow is unreadable without one.
        tabIndex={0}
        aria-label={label ?? filename ?? "Code sample"}
        className="mono overflow-x-auto p-4 text-caption leading-[1.7]">
        {lines.map((l, i) => (
          /* `w-max min-w-full`, and `whitespace-pre` on the code.
             The wrapper has always said `overflow-x-auto` and the panel is
             focusable *because it scrolls* — but nothing in here actually
             scrolled. The rows were plain flex items at the container's width
             and the code inherited `overflow-wrap: break-word` from body, so
             every long line wrapped instead, mid-token, under a line number
             that then no longer matched the line. A wrapped code sample with
             line numbers is worse than either one alone: the numbers stop being
             true. Sizing the row to its content is what lets the overflow the
             component already declared actually happen. */
          <div key={i} className="flex w-max min-w-full">
            {/* w-10, not w-7. At 28px with 12px of padding the number had 16px,
                and two digits of Plex Mono at the reading size need ~16 — so
                every block longer than nine lines stacked "1" above "0". Three
                digits fit now, which covers every sample on the site. */}
            <span aria-hidden="true"
              className="w-10 shrink-0 select-none whitespace-nowrap pr-3 text-right text-faint">{i + 1}</span>
            <span className="whitespace-pre" dangerouslySetInnerHTML={{ __html: highlight(l) || "&nbsp;" }} />
          </div>
        ))}
      </div>
    </figure>
  );
}

/** The marketing measure. `.gutter` is the horizontal margin: it steps with the
 *  viewport AND takes the display cutout into account, so a notched phone held
 *  in landscape does not run the first character of every line under its own
 *  sensor housing. See globals.css. */
export function Section({ children, className, id }:
  { children: React.ReactNode; className?: string; id?: string }) {
  return (
    <section id={id} className={cn("gutter mx-auto max-w-shell", className)}>
      {children}
    </section>
  );
}

export function Eyebrow({ children, className }: { children: React.ReactNode; className?: string }) {
  return <div className={cn("tech-label mb-3", className)}>{children}</div>;
}

/**
 * The page header every marketing and docs page shares.
 *
 * Each page used to hand-roll this with its own arbitrary size, so the landing
 * page led at 31px, pricing and security at 40px and the docs at 36px — four
 * different answers to "how big is a page title" inside one site. It is one
 * answer now, and it is on the scale.
 *
 * That answer is `3xl` (31→44px fluid) rather than `2xl`. There is exactly one
 * of these per page and it is the first thing on it, but at `2xl` it was the
 * same size as the section heading three screens further down, so nothing on
 * the first screen was visibly the most important thing on it. Raising the top
 * step is what buys the rest of the scale room to mean something.
 */
export function PageHeader({ eyebrow, title, children }:
  { eyebrow: string; title: React.ReactNode; children?: React.ReactNode }) {
  return (
    <header>
      <Eyebrow>{eyebrow}</Eyebrow>
      <h1 className="display max-w-[18ch] text-3xl sm:max-w-[22ch]">{title}</h1>
      {/* mt-7, not mt-6. The lede is the only thing between a 44px headline and
          the body of the page, and at the old step it sat close enough to the
          heading to read as a second line of it. */}
      {children && <div className="lede mt-7">{children}</div>}
    </header>
  );
}

/**
 * The opening statement of the whole site.
 *
 * Distinct from PageHeader on purpose. A sub-page headline answers "where am
 * I"; this one has to land an argument to somebody who has never heard of the
 * product, and it is the only element on the site that gets the 4xl step.
 *
 * The measure is 19ch, not 15. 15 was correct when this shared a row with a
 * 500px panel and had roughly half the page to work in; now that it owns the
 * whole first screen the same cap would set a 68px headline in a 480px column
 * inside a 1088px container — a narrow ribbon of type floating in empty space,
 * which reads as timid rather than confident. 19ch gives two or three full
 * lines that use the width they have been given.
 */
export function HeroHeading({ children, className }:
  { children: React.ReactNode; className?: string }) {
  return (
    <h1 className={cn("display max-w-[19ch] text-4xl", className)}>{children}</h1>
  );
}

/**
 * The page's primary action.
 *
 * 44px tall, which is the platform default control size for a finger rather
 * than the 34px these were. There is at most one per view: the landing page
 * previously offered three text links of identical weight, which is the same as
 * offering none.
 *
 * The label is `text-note`, a READING step — so it is ~16px inside `.reading`
 * rather than the 13px instrument size. A 13px label centred in a 44px button
 * looks like a control that was resized without being redrawn.
 */
export function ButtonLink({ href, children, variant = "primary", external, className }: {
  href: string; children: React.ReactNode;
  variant?: "primary" | "secondary" | "quiet"; external?: boolean; className?: string;
}) {
  const base = cn(
    "inline-flex h-control-lg items-center justify-center gap-2 rounded-md px-5 text-note font-medium",
    "transition-[background-color,color,border-color,transform] duration-1 ease-out active:scale-[0.98]",
    className);
  const v = {
    primary: "on-accent bg-accent text-accentFg hover:bg-accentHover",
    secondary: "border border-[color:var(--line-strong)] bg-panel text-fg hover:bg-raised",
    quiet: "px-0 text-muted underline decoration-[color:var(--line-strong)] underline-offset-[6px] hover:text-fg hover:decoration-[color:var(--accent)]",
  }[variant];
  const cls = cn(base, v);
  return external
    ? <a href={href} className={cls} rel="noreferrer">{children}</a>
    : <Link href={href} className={cls}>{children}</Link>;
}

/**
 * A ruled list of label / definition pairs — the shape a record is set in, and
 * the main structural device on these pages. Flat, left-aligned, no boxes.
 *
 * Both columns are on the READING scale. They were `text-sm`, which is 13px —
 * the dashboard's instrument size — so the densest body copy on the public site
 * was also the copy people were most expected to actually read.
 */
export function SpecList({ items, tone = "fg" }: {
  items: { k: string; d: React.ReactNode }[];
  tone?: "fg" | "accent" | "conflict";
}) {
  const kcls = { fg: "text-fg", accent: "text-accent", conflict: "text-conflict" }[tone];
  return (
    <dl className="border-t">
      {items.map(it => (
        <div key={it.k} className="spec-row border-b py-9">
          <dt className={cn("text-note font-semibold", kcls)}>{it.k}</dt>
          <dd className="max-w-read text-body text-muted">{it.d}</dd>
        </div>
      ))}
    </dl>
  );
}
