# ── Stage 1: build the Next.js dashboard ────────────────────────────────────
FROM node:20-slim AS web-build
WORKDIR /web
# install deps first (better layer caching)
COPY web/package.json web/package-lock.json* ./
RUN npm install --no-audit --no-fund
# build the app
COPY web/ ./
# the dashboard talks to the server via the /api/omem rewrite -> OMEM_API_URL,
# which we set at runtime; localhost inside the container is correct there.
RUN npm run build

# ── Stage 2: runtime with Python server + built web ─────────────────────────
FROM node:20-slim AS runtime
# Python 3 for the OMEM server (stdlib-only: no pip install needed).
#
# python3-cryptography as well, so OMEM_ENCRYPT_AT_REST actually works here:
# content encryption refuses to run on the stdlib HMAC fallback, and without
# this the feature would be unavailable in the deployment most likely to want
# it. The distro package keeps pip and a compiler out of the runtime layer.
#
# NOTE: no PostgreSQL driver. This image is SQLite-only; add psycopg2-binary
# yourself if you point it at OMEM_DATABASE_URL.
RUN apt-get update && apt-get install -y --no-install-recommends \
        python3 python3-cryptography \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# the OMEM server (engine + api)
COPY server/ ./server/
# the built dashboard from stage 1 (standalone-friendly copy: whole tree)
COPY --from=web-build /web ./web

# startup script runs BOTH processes and ties their lifetimes together
COPY docker/start.sh /app/start.sh
RUN chmod +x /app/start.sh

# server API + dashboard
EXPOSE 8787 3000

# The server must bind 0.0.0.0 inside the container (not 127.0.0.1) so the
# dashboard process and the host can reach it.
ENV OMEM_HOST=0.0.0.0
# In local mode the server refuses a non-loopback bind, because local mode has no
# passwords and reachability is therefore the whole access control. Inside a
# container that bind is unavoidable and says nothing about exposure — what the
# port is published to does, which is why docker-compose.yml publishes to
# 127.0.0.1. Acknowledge it here so the container starts; set OMEM_AUTH=password
# (and OMEM_MASTER_KEY) if you publish these ports to a network.
ENV OMEM_ALLOW_INSECURE_BIND=1
# The dashboard's server-side rewrite target (server is on localhost in-container)
ENV OMEM_API_URL=http://127.0.0.1:8787
# Demo data stays OFF (testers see only their own real data)
ENV OMEM_SEED_DEMO=0

# Not root. The server writes only to its data directory and the dashboard needs
# nothing writable at all, so there is no reason for a compromise here to start
# with uid 0.
RUN useradd --system --create-home --uid 10001 omem && mkdir -p /app/server/data && chown -R omem:omem /app
USER omem

CMD ["/app/start.sh"]
