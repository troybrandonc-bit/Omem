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
# Python 3 for the OMEM server (stdlib-only: no pip install needed)
RUN apt-get update && apt-get install -y --no-install-recommends python3 \
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
# The dashboard's server-side rewrite target (server is on localhost in-container)
ENV OMEM_API_URL=http://127.0.0.1:8787
# Demo data stays OFF (testers see only their own real data)
ENV OMEM_SEED_DEMO=0

CMD ["/app/start.sh"]
