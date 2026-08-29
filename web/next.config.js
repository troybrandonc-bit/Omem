/** @type {import('next').NextConfig} */

// Two builds from one config.
//
//   npm run dev            development, proxying /api/omem -> the Python server
//   OMEM_STATIC=1 build    a static export, bundled into the Python wheel
//
// The static export is what makes `pip install omem-infrastructure` enough to
// get a dashboard: the Python server serves these files itself, so there is no
// Node at runtime, no second process and no second port. Getting there costs
// two things, both handled here:
//
//   - No rewrites. `rewrites()` needs a Node server, which an export does not
//     have. It is unnecessary anyway once Python serves the files and the API
//     from the same origin — the client just calls /v1/... directly (see
//     lib/api.ts), which also means no CORS.
//   - No dynamic routes. An export writes one file per route at build time, and
//     /assertions/[id] has no id until runtime. Those pages moved to
//     /assertion?id=..., which needs no file per id.
const isStatic = process.env.OMEM_STATIC === "1";

// A static export is always served from the SAME ORIGIN as the API: the Python
// server that bundles it, and on the marketing site the dashboard is unused. The
// /api/omem rewrite below only exists under `npm run dev`, so in an export the
// client must call /v1/... directly (BASE="" in lib/api.ts, gated on
// NEXT_PUBLIC_OMEM_BUNDLED). Default that flag on for every static build unless
// the operator set it explicitly. Without this, a bundled dashboard fetches
// /api/omem/v1/health, which 404s on the Python server, and the UI reports "OMEM
// not responding, start omem-server" while the server is in fact up. Setting it
// here (before Next reads the environment) means neither the release build nor a
// hand build has to remember the flag.
if (isStatic && process.env.NEXT_PUBLIC_OMEM_BUNDLED === undefined) {
  process.env.NEXT_PUBLIC_OMEM_BUNDLED = "1";
}

module.exports = {
  ...(isStatic ? { output: "export" } : {}),
  // Export has no image optimizer (that is a server feature), so the loader has
  // to be disabled or the build fails on any next/image usage.
  images: { unoptimized: true },
  // Emit out/memory/index.html rather than out/memory.html. Directory-style
  // output is far simpler to serve from a static handler, because every route
  // resolves the same way instead of needing a ".html" fallback.
  trailingSlash: true,

  // The webpack filesystem cache serialises large "packs" and can exhaust the
  // Node zone allocator on small machines (RangeError: Failed to allocate
  // memory). An in-memory cache costs a little rebuild time and removes the
  // failure entirely.
  webpack: (config, { dev }) => {
    if (dev) config.cache = { type: "memory" };
    return config;
  },

  async rewrites() {
    if (isStatic) return [];
    return [{ source: "/api/omem/:path*", destination: (process.env.OMEM_API_URL || "http://127.0.0.1:8787") + "/:path*" }];
  },
};
