"""Environment file loading (stdlib only, no python-dotenv dependency).

The Python API server previously read os.environ exclusively, so a `.env.local`
placed next to the frontend (a Next.js convention) never reached it. This loads
env files explicitly at server start.

Search order (first match for a given key wins; real environment variables
always take precedence so container/CI config is never overridden):
    server/.env.local, server/.env,
    <repo root>/.env.local, <repo root>/.env,
    <repo root>/web/.env.local   (convenience: where people naturally put it)

Format: KEY=VALUE per line, `#` comments, optional `export ` prefix, and
surrounding single/double quotes stripped.
"""
from __future__ import annotations
import os

_SERVER_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_SERVER_DIR)

CANDIDATES = [
    os.path.join(_SERVER_DIR, ".env.local"),
    os.path.join(_SERVER_DIR, ".env"),
    os.path.join(_ROOT, ".env.local"),
    os.path.join(_ROOT, ".env"),
    os.path.join(_ROOT, "web", ".env.local"),
]


def parse_env_file(path: str) -> dict[str, str]:
    out: dict[str, str] = {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            for raw in f:
                line = raw.strip()
                if not line or line.startswith("#"):
                    continue
                if line.startswith("export "):
                    line = line[len("export "):].strip()
                if "=" not in line:
                    continue
                key, _, val = line.partition("=")
                key = key.strip()
                val = val.strip()
                # strip inline comments only when the value is unquoted
                if val[:1] not in ("'", '"') and " #" in val:
                    val = val.split(" #", 1)[0].strip()
                if len(val) >= 2 and val[0] == val[-1] and val[0] in ("'", '"'):
                    val = val[1:-1]
                if key:
                    out[key] = val
    except OSError:
        pass
    return out


def load_env(verbose: bool = False) -> list[str]:
    """Load env files into os.environ without overriding existing variables.
    Returns the list of files that contributed at least one value."""
    loaded: list[str] = []
    for path in CANDIDATES:
        if not os.path.exists(path):
            continue
        values = parse_env_file(path)
        applied = 0
        for k, v in values.items():
            if k not in os.environ:  # real env wins
                os.environ[k] = v
                applied += 1
        if applied:
            loaded.append(path)
            if verbose:
                print(f"  loaded {applied} vars from {path}")
    return loaded
