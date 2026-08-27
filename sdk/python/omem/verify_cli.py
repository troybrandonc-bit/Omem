"""`omem-verify` console command: prove the state follows from the log.

Same launcher shape as server_cli: the bundled server lives under _server/ and
uses flat imports, so its directory goes on sys.path first and then the module
runs. Keeping this a thin wrapper means the verifier itself stays in server/,
next to the engine it verifies, rather than being a second copy that could
drift from it.

    omem-verify                  verify every project in ./omem-data
    omem-verify --record         write digests to .omem-state.json
    omem-verify --anchor F       compare against digests recorded earlier

The database is found the same way `omem-server` writes it, so running this in
the directory you ran the server from just works.
"""
import os
import sys


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    server_dir = os.path.join(here, "_server")
    if not os.path.isdir(server_dir):
        sys.stderr.write(
            "omem-verify: bundled server not found. Reinstall omem-infrastructure.\n")
        sys.exit(1)
    sys.path.insert(0, server_dir)

    data_dir = os.environ.get("OMEM_DATA_DIR") or os.path.join(os.getcwd(), "omem-data")
    os.environ.setdefault("OMEM_DB", os.path.join(data_dir, "omem.db"))
    os.environ.setdefault("OMEM_SEED_DEMO", "0")

    db = os.environ["OMEM_DB"]
    if not os.path.exists(db):
        sys.stderr.write(
            f"omem-verify: no database at {db}\n"
            "Run omem-server in this directory first, or set OMEM_DB.\n")
        sys.exit(2)

    import replay_verify  # noqa: E402  (after sys.path and env)
    sys.exit(replay_verify.main())


if __name__ == "__main__":
    main()
