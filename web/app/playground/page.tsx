"use client";
import { useState } from "react";
import { api, getSession, type WhyResult } from "@/lib/api";
import { useApp } from "@/components/providers";
import { cn } from "@/lib/cn";
import { Play, Copy, Check, Terminal, RefreshCw, ArrowRight } from "lucide-react";

// Full developer loop, all live against the user's project:
// learn (text -> engine belief) -> recall -> why (state + provenance) -> code-gen.
// The engine decides state; this page only renders what it returns.
type Lang = "curl" | "python" | "typescript";

export default function Playground() {
  const { project } = useApp();
  const [text, setText] = useState("The customer told us they prefer annual billing.");
  const [about, setAbout] = useState("customer:acme");
  const [agent] = useState("support-agent");
  const [lang, setLang] = useState<Lang>("python");
  const [busy, setBusy] = useState(false);
  const [copied, setCopied] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [learned, setLearned] = useState<{ assertion: string; proposition: string; state: string }[] | null>(null);
  const [recalled, setRecalled] = useState<number | null>(null);
  const [why, setWhy] = useState<WhyResult | null>(null);

  const signed = typeof window !== "undefined" && !!getSession();

  async function run() {
    setBusy(true); setErr(null); setLearned(null); setWhy(null); setRecalled(null);
    try {
      const l = await api.learn(project, { agent, about, text, source: "playground" });
      setLearned(l.learned.map(x => ({ assertion: x.assertion, proposition: x.proposition, state: x.state })));
      const r = await api.recall(project, about);
      setRecalled(r.count);
      if (l.learned[0]) setWhy(await api.why(project, l.learned[0].assertion));
    } catch (e) {
      setErr((e as Error).message);
    }
    setBusy(false);
  }

  const snippet = CODE[lang](project, agent, about, text);

  return (
    <div className="space-y-5">
      <div className="flex items-baseline justify-between">
        <h1 className="display text-lg">Playground</h1>
        <span className="text-sm text-muted">Every call runs live against your project.</span>
      </div>

      <section className="panel overflow-hidden">
        <header className="border-b px-4 py-2.5"><h2 className="text-sm font-semibold">Teach your agent</h2></header>
        <div className="space-y-3 px-4 py-3">
          <div>
            <label className="text-2xs text-faint">Subject</label>
            <input value={about} onChange={e => setAbout(e.target.value)}
              className="mono mt-1 w-full rounded-md border bg-panel px-3 py-2 text-sm outline-none focus:border-accent" />
          </div>
          <div>
            <label className="text-2xs text-faint">What happened (free text)</label>
            <textarea value={text} onChange={e => setText(e.target.value)} rows={2}
              className="mt-1 w-full rounded-md border bg-panel px-3 py-2 text-sm outline-none focus:border-accent" />
          </div>
          {err && <div className="rounded-md border border-conflict/40 bg-conflictBg px-3 py-2 text-2xs text-conflict">{err}</div>}
          <button onClick={run} disabled={busy || !signed}
            className="inline-flex items-center gap-2 rounded-md bg-accent px-3 py-1.5 text-sm font-semibold text-accentFg shadow-[0_1px_1px_rgba(0,0,0,0.06)] transition-opacity hover:opacity-[0.88] disabled:opacity-40">
            {busy ? <RefreshCw className="h-3.5 w-3.5 animate-spin" /> : <Play className="h-3.5 w-3.5" />}
            {signed ? "Learn → recall → why" : "Sign in to run"}
          </button>
        </div>

        {learned && (
          <div className="border-t px-4 py-3">
            {learned.length === 0 ? (
              <div className="text-sm text-muted">No durable fact was found in that text. Try something like a preference, intent, or status.</div>
            ) : (
              <div className="space-y-4">
                <Step n={1} label="Learned">
                  {learned.map(l => (
                    <div key={l.assertion} className="flex items-center gap-2 text-sm">
                      <span className="mono">{l.proposition}</span>
                      <StatePill state={l.state} />
                    </div>
                  ))}
                </Step>
                {recalled !== null && (
                  <Step n={2} label="Recalled">
                    <span className="text-sm text-muted"><span className="num font-semibold text-fg">{recalled}</span> belief{recalled === 1 ? "" : "s"} about <span className="mono">{about}</span></span>
                  </Step>
                )}
                {why && (
                  <Step n={3} label="Why the agent believes it">
                    <div className="space-y-2">
                      <div className="flex items-center gap-2 text-sm">
                        <StatePill state={why.state} />
                        <span className="text-2xs text-faint">{why.grounded ? "grounded: reaches an event root" : "ungrounded"}</span>
                      </div>
                      <ProvChain why={why} />
                    </div>
                  </Step>
                )}
              </div>
            )}
          </div>
        )}
      </section>

      <section className="panel overflow-hidden">
        <header className="flex items-center justify-between border-b">
          <div className="flex">
            {(["curl", "python", "typescript"] as Lang[]).map(l => (
              <button key={l} onClick={() => setLang(l)}
                className={cn("px-4 py-2.5 text-sm transition-colors", lang === l ? "font-semibold text-fg" : "text-muted hover:text-fg")}>
                {l === "curl" ? "cURL" : l === "python" ? "Python" : "TypeScript"}
              </button>
            ))}
          </div>
          <button onClick={() => { navigator.clipboard.writeText(snippet); setCopied(true); setTimeout(() => setCopied(false), 1200); }}
            className="mr-3 p-1.5 text-muted hover:text-fg" aria-label="Copy">
            {copied ? <Check className="h-3.5 w-3.5 text-believed" /> : <Copy className="h-3.5 w-3.5" />}
          </button>
        </header>
        <pre className="mono overflow-x-auto p-4 text-xs leading-[1.7]">{snippet}</pre>
        <div className="flex items-center gap-2 border-t px-4 py-2.5 text-2xs text-muted">
          <Terminal className="h-3.5 w-3.5" /> The exact call the button runs, with your project id.
        </div>
      </section>
    </div>
  );
}

function Step({ n, label, children }: { n: number; label: string; children: React.ReactNode }) {
  return (
    <div className="flex gap-3">
      <span className="mt-0.5 grid h-5 w-5 shrink-0 place-items-center rounded-sm bg-accentBg text-2xs font-semibold text-accent">{n}</span>
      <div className="min-w-0 flex-1">
        <div className="mb-1 text-2xs font-semibold capitalize text-muted">{label}</div>
        {children}
      </div>
    </div>
  );
}

function StatePill({ state }: { state: string }) {
  const tone = state === "BELIEVED_TRUE" ? "believed" : state === "CONTRADICTED" ? "conflict" : state === "BELIEVED_FALSE" ? "conflict" : "closed";
  return (
    <span className={cn("inline-flex items-center gap-1.5 rounded-sm border px-2 py-px text-2xs font-semibold lowercase",
      tone === "believed" ? "text-believed" : tone === "conflict" ? "text-conflict" : "text-muted")}
      style={{ borderColor: "currentColor" }}>
      <span className={cn("led", tone)} style={{ width: 6, height: 6 }} />{state.replace("_", " ")}
    </span>
  );
}

function ProvChain({ why }: { why: WhyResult }) {
  // render the assertion -> ... -> event chain from provenance edges
  const nodes = why.provenance.nodes;
  const chain = [
    { id: why.assertion.id, label: why.assertion.proposition, kind: "assertion" },
    ...nodes.map(n => ({ id: n.id, label: n.label || n.id, kind: n.kind })),
  ];
  return (
    <div className="flex flex-wrap items-center gap-2 rounded-md bg-raised px-3 py-2.5">
      {chain.map((c, i) => (
        <span key={c.id} className="flex items-center gap-2">
          <span className="inline-flex items-center gap-1.5">
            <span className={cn("led", c.kind === "event" ? "believed" : c.kind === "assertion" ? "accent" : "closed")} style={{ width: 7, height: 7 }} />
            <span className="mono text-2xs">{c.label}</span>
            <span className="text-2xs text-faint">({c.kind})</span>
          </span>
          {i < chain.length - 1 && <ArrowRight className="h-3 w-3 text-faint" />}
        </span>
      ))}
    </div>
  );
}

const CODE: Record<Lang, (p: string, agent: string, about: string, text: string) => string> = {
  // api.omem.dev does not resolve and there is no hosted OMEM. The server you
  // are reading this page from is the one to curl, so these are copy-pasteable
  // rather than aspirational.
  curl: (p, agent, about, text) =>
`# 1. learn from text
curl http://127.0.0.1:8787/v1/learn?project=${p} \\
  -H "Authorization: Bearer $OMEM_API_KEY" -H "Content-Type: application/json" \\
  -d '${JSON.stringify({ agent, about, text })}'

# 2. recall what the agent knows
curl http://127.0.0.1:8787/v1/recall?project=${p} \\
  -H "Authorization: Bearer $OMEM_API_KEY" -H "Content-Type: application/json" \\
  -d '${JSON.stringify({ about })}'

# 3. ask why (state + provenance)
curl "http://127.0.0.1:8787/v1/assertions/<id>/why?project=${p}" \\
  -H "Authorization: Bearer $OMEM_API_KEY"`,
  python: (p, agent, about, text) =>
`from omem import Memory

mem = Memory(api_key="omem_sk_...", project="${p}")
agent = mem.agent("${agent}")

# teach from free text; the frozen engine decides the resulting state
result = agent.learn(text=${JSON.stringify(text)}, about="${about}")
aid = result["learned"][0]["assertion"]

print(agent.recall("${about}"))   # what does the agent know?
print(agent.why(aid))              # why does it believe it? (state + provenance)`,
  typescript: (p, agent, about, text) =>
`// Not on npm yet: the TypeScript SDK is used from sdk/typescript/ in the repo.
import { Memory } from "./sdk/typescript/src/index";

const mem = new Memory({ apiKey: "omem_sk_...", project: "${p}" });
const agent = mem.agent("${agent}");

// teach from free text; the frozen engine decides the resulting state
const result = await agent.learn({ text: ${JSON.stringify(text)}, about: "${about}" });
const aid = result.learned[0].assertion;

console.log(await agent.recall("${about}"));  // what does the agent know?
console.log(await agent.why(aid));             // why? (state + provenance)`,
};
