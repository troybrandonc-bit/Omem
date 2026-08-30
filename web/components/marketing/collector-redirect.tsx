"use client";
import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";

/* On the commons collector, the bare domain should land on the commons, not
 * the product pitch. The static bundle is shared across every install, so the
 * collector can only be recognised at runtime: this asks /v1/health once and
 * replaces the route with /commons when the answer says collector. Renders
 * nothing; on every other install the check fails or says no and the landing
 * page stays. */
export function CollectorRedirect() {
  const router = useRouter();
  useEffect(() => {
    // Only a server-bundled build can be a collector. The standalone public
    // site is not, so it must not fire a health call that would just fail --
    // the very thing lib/routes.ts exists to prevent on the landing page.
    if (process.env.NEXT_PUBLIC_OMEM_BUNDLED !== "1") return;
    let cancelled = false;
    api.health()
      .then(h => { if (!cancelled && h.commons_collector) router.replace("/commons"); })
      .catch(() => { /* not a collector, or no server: stay on the landing page */ });
    return () => { cancelled = true; };
  }, [router]);
  return null;
}
