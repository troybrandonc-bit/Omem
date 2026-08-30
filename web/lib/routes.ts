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
 */
export const MARKETING_ROUTES = ["/docs", "/guides", "/pricing", "/security", "/changelog", "/compare", "/commons"] as const;

/** True for the public site: the landing page, or anything under a marketing
 *  section. Onboarding is treated the same way by `Shell` — it deliberately
 *  runs without the app chrome — but it DOES need a project, so it is not
 *  included here. */
export function isMarketingRoute(path: string | null | undefined): boolean {
  if (!path) return false;
  return path === "/" || MARKETING_ROUTES.some(r => path.startsWith(r));
}
