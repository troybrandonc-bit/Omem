#!/usr/bin/env bash
set -e

echo "Starting OMEM server (API on :8787)…"
cd /app/server
python3 api.py 8787 &
SERVER_PID=$!

echo "Starting OMEM dashboard (on :3000)…"
cd /app/web
npm start -- -p 3000 &
WEB_PID=$!

# If either process exits, bring the whole container down so Docker restarts it
# cleanly instead of leaving a half-dead stack.
trap "kill $SERVER_PID $WEB_PID 2>/dev/null" EXIT
wait -n $SERVER_PID $WEB_PID
echo "A process exited; shutting down."
exit 1
