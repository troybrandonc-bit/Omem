"""DEVELOPMENT-ONLY seed. Explicitly refuses to run against a non-dev DB path.
Usage: python3 seed.py
The demo project is already seeded at boot; this adds a richer dev org so the
dashboard has multi-source, multi-agent data to explore. NEVER run in production.
"""
import os
import sys

if os.environ.get("OMEM_ENV") == "production":
    print("REFUSING: seed.py must never run in production (OMEM_ENV=production).")
    sys.exit(1)

print("Development seed: the demo project (labeled) is created automatically at API boot.")
print("Start the server with `python3 api.py` and open /overview, or connect a source on /sources.")
print("This script is a placeholder guard so seed data never leaks into production metrics.")
