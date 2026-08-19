"use client";
import { useState } from "react";
import { cn } from "@/lib/cn";
import { Copy, Check } from "lucide-react";

function esc(s: string) {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}
const KW = /\b(from|import|await|const|new|def|return|if|let|func|use|fn|package)\b/g;
function highlight(line: string) {
  let h = esc(line);
  h = h.replace(/(&quot;|")([^"]*?)(&quot;|")/g, '<span class="code-str">"$2"</span>');
  h = h.replace(KW, '<span class="code-kw">$1</span>');
  h = h.replace(/(#.*$|\/\/.*$)/g, '<span class="code-cm">$1</span>');
  return h;
}

export function CodeBlock({ tabs, single, filename }:
  { tabs?: { label: string; code: string }[]; single?: string; filename?: string }) {
  const items = tabs ?? [{ label: filename ?? "", code: single ?? "" }];
  const [active, setActive] = useState(0);
  const [copied, setCopied] = useState(false);
  const code = items[active].code;
  const lines = code.split("\n");
  return (
    <div className="panel overflow-hidden">
      <div className="flex items-center justify-between border-b">
        <div className="flex items-center">
          {items.map((t, i) => (
            <button key={i} onClick={() => setActive(i)}
              className={cn("px-3.5 py-2 text-[13px] transition-colors",
                items.length === 1 ? "mono pointer-events-none text-muted" :
                i === active ? "font-semibold text-fg" : "text-muted hover:text-fg")}>
              {t.label}
            </button>
          ))}
        </div>
        <button onClick={() => { navigator.clipboard.writeText(code); setCopied(true); setTimeout(() => setCopied(false), 1200); }}
          className="mr-2 p-1.5 text-muted transition-colors hover:text-fg" aria-label="Copy">
          {copied ? <Check className="h-3.5 w-3.5 text-believed" /> : <Copy className="h-3.5 w-3.5" />}
        </button>
      </div>
      <div className="mono overflow-x-auto p-4 text-[12.5px] leading-[1.7]">
        {lines.map((l, i) => (
          <div key={i} className="flex">
            <span className="w-7 shrink-0 select-none text-right pr-3 text-faint">{i + 1}</span>
            <span dangerouslySetInnerHTML={{ __html: highlight(l) || "&nbsp;" }} />
          </div>
        ))}
      </div>
    </div>
  );
}

export function Section({ children, className }: { children: React.ReactNode; className?: string }) {
  return <section className={cn("mx-auto max-w-[1200px] px-6", className)}>{children}</section>;
}
export function Eyebrow({ children }: { children: React.ReactNode }) {
  return <div className="tech-label mb-4">{children}</div>;
}
