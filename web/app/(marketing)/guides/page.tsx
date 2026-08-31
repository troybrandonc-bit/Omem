import Link from "next/link";
import { MarketingShell } from "@/components/marketing/chrome";
import { Section, PageHeader } from "@/components/marketing/ui";

export const metadata = {
  title: "Guides",
  description:
    "Guides for trustworthy AI agents with OMEM: an audit trail for agents, human-in-the-loop approvals, LangGraph long-term memory, an MCP memory server for Claude, and belief-tracked memory from Python.",
};

/* Each guide targets one question people actually type into a search bar,
 * answers it completely on this domain, and only then mentions that the
 * engine underneath does more. A guide that is secretly a landing page gets
 * closed; one that solves the problem gets bookmarked. */

const GUIDES = [
  {
    href: "/guides/eu-ai-act-article-12-ai-agents",
    title: "EU AI Act Article 12 for AI agents: what to log, with working code",
    lede: "The high-risk logging duty, read as engineering: why ordinary logs fail it, the four properties a compliant agent record needs, and a working self-hosted implementation.",
  },
  {
    href: "/guides/ai-agent-audit-trail",
    title: "An audit trail for AI agents",
    lede: "What a defensible trail must contain, why request logs do not qualify, and how to record what the agent believed, why, and who approved its actions.",
  },
  {
    href: "/guides/human-in-the-loop-ai-agents",
    title: "Human-in-the-loop approvals for AI agents",
    lede: "Gate risky actions behind a named approver: a closed set of actions, risk decided by the system, and refusals kept on the record.",
  },
  {
    href: "/guides/should-agent-memory-decide-truth",
    title: "Should an agent's memory decide what is true?",
    lede: "The essay: overwriting on conflict is a truth judgment nobody chose, and the case for memory that keeps both sides and proves why.",
  },
  {
    href: "/guides/langgraph-long-term-memory",
    title: "Long-term memory for a LangGraph agent",
    lede: "Wire a LangGraph agent to a store where put supersedes instead of overwriting, delete retracts instead of erasing, and every memory can answer where it came from.",
  },
  {
    href: "/guides/mcp-memory-server",
    title: "A memory MCP server for Claude",
    lede: "One command and one block of JSON give Claude Desktop remember, recall and why tools against a server running on your machine.",
  },
  {
    href: "/guides/agent-memory-python",
    title: "Agent memory in Python, with receipts",
    lede: "Beliefs instead of rows: contradictions surfaced, updates that keep history, retractions that take conclusions with them, and why() for everything.",
  },
];

export default function GuidesIndex() {
  return (
    <MarketingShell>
      <Section className="page-y">
        <PageHeader eyebrow="Guides" title="Solve the problem first. The pitch can wait." />
        <p className="lede mt-6 max-w-3xl">
          Working guides and one essay, each self-contained, most runnable on a
          laptop in a few minutes with nothing external. They use OMEM because
          that is what this site is, but every one solves its problem completely
          before it says anything a landing page would.
        </p>
        <ul className="mt-12 max-w-3xl border-t">
          {GUIDES.map(g => (
            <li key={g.href} className="border-b">
              <Link href={g.href} className="group block py-7">
                <h2 className="display text-xl group-hover:underline underline-offset-4">
                  {g.title}
                </h2>
                <p className="mt-2 text-note text-muted">{g.lede}</p>
              </Link>
            </li>
          ))}
        </ul>
      </Section>
    </MarketingShell>
  );
}
