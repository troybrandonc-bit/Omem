import Link from "next/link";
import { MarketingShell } from "@/components/marketing/chrome";
import { Section, CodeBlock, ButtonLink } from "@/components/marketing/ui";

export const metadata = {
  title: "A memory MCP server for Claude",
  description:
    "Give Claude Desktop persistent memory with remember, recall and why tools through MCP. One pip install, one JSON block, runs entirely on your machine.",
};

export default function Guide() {
  return (
    <MarketingShell>
      <Section className="page-y">
        <article className="prose-omem max-w-3xl">
          <div className="tech-label mb-3">Guide</div>
          <h1 className="display text-3xl">A memory MCP server for Claude</h1>

          <p className="lede">
            MCP is how Claude Desktop and other clients talk to outside tools.
            This guide gives Claude memory that persists between conversations,
            runs entirely on your machine, and can answer{" "}
            <em>why</em> it believes what it believes, not just what.
          </p>

          <h2>Start the server</h2>
          <CodeBlock label="Install and run" single={`pip install omem-infrastructure\nomem-server`} />
          <p className="mt-3 text-note text-muted">
            First run prints a project id and an API key, and serves a dashboard
            on the same port where you can watch memories arrive.
          </p>

          <h2>Wire it into Claude Desktop</h2>
          <p>
            Add this to <code className="mono text-fg">claude_desktop_config.json</code>{" "}
            (macOS: <code className="mono text-fg">~/Library/Application Support/Claude/</code>,
            Windows: <code className="mono text-fg">%APPDATA%\Claude\</code>) and
            restart the app:
          </p>
          <CodeBlock label="claude_desktop_config.json" single={`{
  "mcpServers": {
    "omem": {
      "command": "omem-mcp",
      "env": {
        "OMEM_API_KEY": "omem_sk_...",
        "OMEM_BASE_URL": "http://127.0.0.1:8787",
        "OMEM_PROJECT": "proj_...",
        "OMEM_AGENT": "claude"
      }
    }
  }
}`} />
          <p>
            <code className="mono text-fg">omem-mcp</code> speaks MCP over stdio
            and starts with nothing else configured. Claude gets{" "}
            <code className="mono text-fg">remember</code>,{" "}
            <code className="mono text-fg">recall</code> and{" "}
            <code className="mono text-fg">why</code> tools, plus the reasoning
            verbs.
          </p>

          <h2>What makes this memory different</h2>
          <p>
            The model proposes memories; a belief revision engine decides what
            is actually believed. When two remembered facts contradict each
            other, both survive, flagged, with sides. Ask the{" "}
            <code className="mono text-fg">why</code> tool about anything and you
            get the evidence chain: who said it, when, what contradicts it.
            Retract a fact and everything concluded from it is withdrawn in the
            same request. Nothing is silently overwritten because a newer
            message arrived.
          </p>
          <p>
            Everything stays local: SQLite on your disk, zero runtime
            dependencies, and the server provably makes no outbound
            connections. The air-gap test in CI fails the build if any code
            path so much as looks up an external hostname.
          </p>

          <h2>Where to go next</h2>
          <p>
            The <Link href="/docs/quickstart">quickstart</Link> covers the same
            server from the SDK side, and the{" "}
            <Link href="/guides/agent-memory-python">Python guide</Link> shows
            the belief-tracking surface the MCP tools sit on.
          </p>
          <div className="mt-8 flex flex-wrap gap-3">
            <ButtonLink href="/docs/quickstart">Quickstart</ButtonLink>
            <ButtonLink href="https://github.com/troybrandonc-bit/Omem" variant="secondary" external>
              Source on GitHub
            </ButtonLink>
          </div>
        </article>
      </Section>
    </MarketingShell>
  );
}
