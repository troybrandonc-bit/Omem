/**
 * Which routes are the public site rather than the product.
 *
 * This existed twice, implicitly. `Shell` knew the list and bailed out early
 * for it (so the sidebar, the project switcher and the polling never mount on a
 * marketing page), but `Providers` — which wraps `Shell`, not the other way
 * round — did not, and fired `api.projects()` on mount regardless of where it
 * was mounted. So every visit to the landing page, the docs, pricing, security
 * and the changelog opened a request to the dashboard API.
 *
 * On a developer's machine with the server running that is invisible. For the
 * actual audience of those pages — somebody who has just arrived and has no
 * OMEM server at all — it is a guaranteed failed request on first paint, and it
 * is why a dev log reading the public site fills with ECONNREFUSED on :8787.
 *
 * The list lives here so the two callers cannot disagree about it. A route
 * added to the public site and not to this array would quietly get the app
 * chrome; a route added here and not to the site would quietly lose it.
 *
 * That warning came true. /spec/testimony-record, its implementations page,
 * /agent-audit-check and /vendor-review shipped without being added here, so
 * for a month the four pages the specification work exists to serve rendered
 * BootSkeleton — "Connecting to the OMEM server" — as their entire server
 * HTML, to Google, to every LLM crawler following llms.txt, and to anyone
 * whose JavaScript had not arrived. The readiness check says in its own source
 * that it never touches a server; the shell around it said it was contacting
 * one. They are in the sitemap, so they were being offered for indexing the
 * whole time.
 *
 * A comment was not enough, so `server/tests_marketing_routes.py` now walks
 * web/app/(marketing) and fails the build when a public page is missing from
 * this array, from the sitemap, or from llms.txt. Add the page; the test tells
 * you the rest.
 */
export const MARKETING_ROUTES = ["/accountability", "/pilot", "/objectives", "/docs", "/guides", "/pricing", "/security", "/changelog", "/compare", "/privacy", "/terms", "/spec", "/agent-audit-check", "/vendor-review"] as const;

/** True for the public site: the landing page, or anything under a marketing
 *  section. Onboarding is treated the same way by `Shell` — it deliberately
 *  runs without the app chrome — but it DOES need a project, so it is not
 *  included here. */
export function isMarketingRoute(path: string | null | undefined): boolean {
  if (!path) return false;
  return path === "/" || MARKETING_ROUTES.some(r => path.startsWith(r));
}
