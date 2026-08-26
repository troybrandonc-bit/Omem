"""Bundle the server into the wheel at build time.

`omem-server` is the headline of the README: pip install, run, done. It works by
importing the server from `omem/_server/`, and that directory did not exist and
nothing created it. Whoever published 0.1.2 copied `server/` in by hand, so the
published wheel worked and the repository could not reproduce it. Anyone who
cloned this and built got a wheel whose main command printed "bundled server not
found. Reinstall omem-infrastructure."

A build hook rather than a committed copy, because a second copy of 26,000 lines
is a second copy to drift. `server/` stays the only source; this puts it in the
distribution at the moment one is built, and `.gitignore` keeps the generated
copy out of version control.

Both targets run it. The sdist has to carry `_server` too: a wheel built FROM an
sdist has no `../../server` to copy from, so if the sdist omitted it the
resulting wheel would be quietly broken in exactly the way this exists to
prevent. When the source tree is absent and `_server` is already present, that
is the sdist case and the existing copy is correct.

What is excluded and why: `tests*.py` and `run_tests.py` (server_cli puts the
server directory FIRST on sys.path, so shipping them would put importable
top-level modules named `tests`/`run_tests` into every user's process),
`data/` (a developer's local database), `.env` (secrets), `__pycache__`, and
`.hypothesis` (the property-testing example cache).

The last two were found in a published wheel rather than reasoned about in
advance: 0.2.2 shipped 48 `.hypothesis` files, a fifth of the whole archive and
every byte of it one developer's local cache, plus `run_tests.py` -- which the
paragraph above already explains should not be there, and which the filter
missed only because it tested `startswith("tests")` against a name beginning
`run_`.
"""
import os
import shutil

from hatchling.builders.hooks.plugin.interface import BuildHookInterface

EXCLUDED_DIRS = {"__pycache__", "data", ".pytest_cache", ".hypothesis"}
DEST = os.path.join("omem", "_server")


def _skip(name: str) -> bool:
    return (name.startswith("tests")
            or name == "run_tests.py"
            or name.startswith(".env")
            or name.endswith((".pyc", ".db", ".db-wal", ".db-shm")))


class BundleServerHook(BuildHookInterface):
    PLUGIN_NAME = "custom"

    def initialize(self, version, build_data):
        dest = os.path.join(self.root, DEST)
        # sdk/python -> repo root -> server
        source = os.path.abspath(os.path.join(self.root, "..", "..", "server"))

        if not os.path.isdir(source):
            if os.path.isdir(dest):
                return          # building from an sdist: the copy is already here
            raise RuntimeError(
                f"cannot bundle the server: {source} does not exist and {dest} is "
                "not already populated, so `omem-server` would be installed broken")

        if os.path.isdir(dest):
            shutil.rmtree(dest)
        os.makedirs(dest)

        copied = 0
        for root, dirs, files in os.walk(source):
            dirs[:] = [d for d in dirs if d not in EXCLUDED_DIRS]
            target = os.path.join(dest, os.path.relpath(root, source))
            os.makedirs(target, exist_ok=True)
            for f in files:
                if _skip(f):
                    continue
                shutil.copy2(os.path.join(root, f), os.path.join(target, f))
                copied += 1

        # A silent zero would ship the same broken command this exists to fix.
        if not os.path.isfile(os.path.join(dest, "api.py")):
            raise RuntimeError("bundled server is missing api.py; refusing to build")
        self.app.display_info(f"bundled {copied} server files into {DEST}")
        self._bundle_dashboard(dest)

    def _bundle_dashboard(self, server_dest):
        """Copy the built dashboard in, if one has been built.

        This is what makes `pip install omem-infrastructure` enough to get a UI:
        the Python server finds these files next to itself and serves them, so
        there is no Node at runtime, no second process and no second port.

        Deliberately NOT fatal when absent. The dashboard needs `npm ci && npm
        run build` with OMEM_STATIC=1, which is a Node toolchain and a good deal
        of memory. CI has both and plenty of machines do not. A wheel without
        it is a perfectly good wheel that serves the API and says the dashboard
        is not bundled, which is a far better failure than being unable to cut a
        release at all. The server bundle above IS fatal, because without it
        `omem-server` does not exist.
        """
        source = os.path.abspath(os.path.join(self.root, "..", "..", "web", "out"))
        dest = os.path.join(self.root, "omem", "_dashboard")

        if not os.path.isdir(source):
            if os.path.isdir(dest):
                return          # building from an sdist: the copy is already here
            self.app.display_warning(
                "no dashboard bundled (web/out not found). The wheel will serve "
                "the API only. Build it with: cd web && OMEM_STATIC=1 npm run build")
            return

        if os.path.isdir(dest):
            shutil.rmtree(dest)
        shutil.copytree(source, dest)
        n = sum(len(f) for _, _, f in os.walk(dest))
        if not os.path.isfile(os.path.join(dest, "index.html")):
            raise RuntimeError(
                "web/out exists but has no index.html, a partial or failed "
                "export would ship a dashboard that 404s on its own front page")
        self.app.display_info(f"bundled {n} dashboard files into omem/_dashboard")
