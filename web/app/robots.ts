import type { MetadataRoute } from "next";

/**
 * The static export ships the dashboard alongside the marketing site, and a
 * dashboard page indexed by a search engine is a dead end: it renders
 * "waiting for the OMEM server" to anyone without one running. Crawlers get
 * the public surface and are told, explicitly, that the application routes
 * are not content.
 */
export const dynamic = "force-static";

const APP_ROUTES = [
  "/admin", "/agent", "/agents", "/assertion", "/audit", "/conflicts",
  "/contacts", "/developers", "/diagnostics", "/entities", "/entity",
  "/graph", "/healing", "/intelligence", "/jobs", "/logs", "/memory",
  "/memory-health", "/oauth", "/onboarding", "/overview", "/playground",
  "/proposals", "/settings", "/sources", "/team", "/timeline", "/usage",
];

export default function robots(): MetadataRoute.Robots {
  return {
    rules: [{ userAgent: "*", allow: "/", disallow: APP_ROUTES.map(r => r + "/") }],
    sitemap: "https://infrastructure.omem-cloud.com/sitemap.xml",
  };
}
