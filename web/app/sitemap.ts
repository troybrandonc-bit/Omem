import type { MetadataRoute } from "next";

/**
 * The sitemap the site never had. The compare and guide pages exist to catch
 * searches ("mem0 alternative", "langgraph long term memory"), and a static
 * export with no sitemap leaves Google to find them by luck. Only the public
 * marketing surface is listed; the dashboard routes are an application, not
 * content, and robots.ts tells crawlers the same thing.
 *
 * Trailing slashes because next.config sets trailingSlash and the canonical
 * URL should be the one the server actually serves.
 */
export const dynamic = "force-static";

const BASE = "https://infrastructure.omem-cloud.com";

const ROUTES = [
  "",
  "/accountability",
  "/pilot",
  "/objectives",
  "/docs",
  "/docs/quickstart",
  "/docs/sdk",
  "/guides",
  "/guides/langgraph-long-term-memory",
  "/guides/mcp-memory-server",
  "/guides/agent-memory-python",
  "/guides/ai-agent-audit-trail",
  "/guides/human-in-the-loop-ai-agents",
  "/guides/should-agent-memory-decide-truth",
  "/compare",
  "/compare/mem0",
  "/compare/zep",
  "/compare/letta",
  "/pricing",
  "/security",
  "/changelog",
  "/privacy",
  "/terms",
];

export default function sitemap(): MetadataRoute.Sitemap {
  const lastModified = new Date();
  return ROUTES.map(r => ({
    url: r ? `${BASE}${r}/` : `${BASE}/`,
    lastModified,
    changeFrequency: r === "/changelog" ? "weekly" : "monthly",
    priority: r === "" ? 1 : r === "/accountability" ? 0.9 : r.startsWith("/compare/") || r.startsWith("/guides/") ? 0.8 : 0.6,
  }));
}
