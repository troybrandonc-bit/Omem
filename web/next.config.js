/** @type {import('next').NextConfig} */
module.exports = {
  // The webpack filesystem cache serialises large "packs" and can exhaust the
  // Node zone allocator on Windows dev machines (RangeError: Failed to allocate
  // memory). An in-memory cache costs a little rebuild time and removes the
  // failure entirely; production builds are unaffected.
  webpack: (config, { dev }) => {
    if (dev) config.cache = { type: "memory" };
    return config;
  },
  async rewrites() {
    return [{ source: "/api/omem/:path*", destination: (process.env.OMEM_API_URL || "http://127.0.0.1:8787") + "/:path*" }];
  },
};
