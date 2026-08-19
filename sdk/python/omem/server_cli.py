"""`omem-server` console command: starts the bundled OMEM server.

The whole server (engine + HTTP API) ships inside this package under _server/.
This launcher puts that directory on sys.path (the server uses flat local
imports) and calls its main(). It runs with zero third-party dependencies —
same instant-install story as the SDK.

Usage:
    omem-server                 # starts on http://127.0.0.1:8787
    omem-server 9000            # custom port
    OMEM_HOST=0.0.0.0 omem-server   # bind all interfaces

Data (the SQLite db) is written to ./omem-data in the CURRENT directory by
default, NOT inside the installed package (which may be read-only). Override
with OMEM_DATA_DIR.
"""
import os
import sys


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    server_dir = os.path.join(here, "_server")
    if not os.path.isdir(server_dir):
        sys.stderr.write(
            "omem-server: bundled server not found. Reinstall omem-infrastructure.\n")
        sys.exit(1)

    # The server uses flat imports (from store import Store, import recall, ...),
    # so it must be importable as top-level modules: put its dir first on path.
    sys.path.insert(0, server_dir)

    # Keep the SQLite db in a WRITABLE dir in the user's working directory, not
    # inside the installed package (which may be read-only). The server reads the
    # db path from OMEM_DB.
    data_dir = os.environ.get("OMEM_DATA_DIR") or os.path.join(os.getcwd(), "omem-data")
    os.makedirs(data_dir, exist_ok=True)
    os.environ.setdefault("OMEM_DB", os.path.join(data_dir, "omem.db"))

    # Demo/placeholder data stays OFF unless explicitly requested.
    os.environ.setdefault("OMEM_SEED_DEMO", "0")

    port = 8787
    if len(sys.argv) > 1:
        try:
            port = int(sys.argv[1])
        except ValueError:
            sys.stderr.write(f"omem-server: invalid port '{sys.argv[1]}'\n")
            sys.exit(2)

    host = os.environ.get("OMEM_HOST", "127.0.0.1")
    sys.stderr.write(f"OMEM server starting on http://{host}:{port}  (data in {data_dir})\n")

    import api  # noqa: E402  (imported after sys.path + cwd are set)
    api.main(port)


if __name__ == "__main__":
    main()
