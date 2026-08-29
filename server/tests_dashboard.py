"""The bundled dashboard, served by the API server.

`pip install omem-infrastructure` should be enough to get a UI: no Node, no
second process, no second port. That means the Python server serves a static
export of web/ alongside the API, and these are the properties that has to hold.

The one that actually bit during development: the dashboard handler was placed
at the END of _route_get, which is unreachable, because every API route above it
resolves ?project= and bails out with "project not found", and a request for
`/` carries no project. It looked correct and served 404s for everything.

Run: python3 tests_dashboard.py
"""
import os
import shutil
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))

# A stand-in for `npm run build` output. The real export is far bigger, but the
# server only cares about the shape: an index at the root, nested routes as
# directories, and fingerprinted assets under /_next/static.
BUNDLE = tempfile.mkdtemp(prefix="omem-dash-")
os.makedirs(os.path.join(BUNDLE, "_next", "static"), exist_ok=True)
os.makedirs(os.path.join(BUNDLE, "memory"), exist_ok=True)
open(os.path.join(BUNDLE, "index.html"), "w").write("<html><body>OMEM</body></html>")
open(os.path.join(BUNDLE, "memory", "index.html"), "w").write("<html><body>Memory</body></html>")
open(os.path.join(BUNDLE, "_next", "static", "app.css"), "w").write("body{margin:0}")

# Something outside the bundle, to prove traversal cannot reach it.
OUTSIDE = tempfile.mkdtemp(prefix="omem-outside-")
open(os.path.join(OUTSIDE, "secret.txt"), "w").write("SHOULD NEVER BE SERVED")

_DB = os.path.join(HERE, "data", "test_dashboard.db")
for _s in (_DB, _DB + "-wal", _DB + "-shm"):
    if os.path.exists(_s):
        os.remove(_s)
os.environ["OMEM_DB"] = _DB
os.environ["OMEM_SEED_DEMO"] = "0"
os.environ["OMEM_DASHBOARD_DIR"] = BUNDLE

sys.path.insert(0, HERE)
import api  # noqa: E402

PORT = 8823
BASE = f"http://127.0.0.1:{PORT}"
_passed = _failed = 0


def check(name, cond, detail=""):
    global _passed, _failed
    if cond:
        _passed += 1
        print(f"  ok  {name}")
    else:
        _failed += 1
        print(f"  FAIL {name} {detail}")


def get(path):
    try:
        r = urllib.request.urlopen(BASE + path, timeout=5)
        return r.status, dict(r.headers), r.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read()


api.bootstrap_local_workspace()
srv = api.ThreadingHTTPServer(("127.0.0.1", PORT), api.Handler)
threading.Thread(target=srv.serve_forever, daemon=True).start()
time.sleep(0.4)

print("== the dashboard is served ==")
check("the bundle was found", api.DASHBOARD_ROOT is not None, str(api.DASHBOARD_ROOT))

st, h, body = get("/")
check("GET / serves the dashboard, not a 401", st == 200, str(st))
check("  as HTML", h.get("Content-Type", "").startswith("text/html"), h.get("Content-Type"))
check("  with the index content", b"OMEM" in body)

st, h, body = get("/memory/")
check("a nested route serves its index.html", st == 200 and b"Memory" in body, str(st))

st, h, _ = get("/_next/static/app.css")
check("assets are served with the right type", st == 200 and "text/css" in h.get("Content-Type", ""))
check("  and fingerprinted assets cache hard",
      "immutable" in h.get("Cache-Control", ""), h.get("Cache-Control"))

st, h, _ = get("/")
check("but HTML does not cache, or an upgrade keeps serving the old app",
      "no-cache" in h.get("Cache-Control", ""), h.get("Cache-Control"))

print("== the API still wins ==")
st, _, body = get("/v1/health")
check("/v1/health is the API, not a static file", st == 200 and b'"status"' in body, str(st))
check("  and _serve_dashboard refuses /v1 outright",
      api.Handler._serve_dashboard(object.__new__(api.Handler), "/v1/anything") is False)

print("== the /api/omem dev prefix is de-aliased ==")
# A dashboard built for `npm run dev` (or an older wheel built without the
# bundled flag) calls /api/omem/v1/... The server strips that prefix so those
# dashboards reach the API instead of 404ing and reporting the server down.
st, _, body = get("/api/omem/v1/health")
check("/api/omem/v1/health reaches the same API", st == 200 and b'"status"' in body, str(st))

print("== path traversal ==")
for probe in ["/../secret.txt", "/../../secret.txt", "/..%2fsecret.txt",
              "/memory/../../secret.txt"]:
    st, _, body = get(probe)
    check(f"refused: {probe}", st != 200 and b"SHOULD NEVER" not in body, str(st))
check("resolution refuses to escape the bundle",
      api._dashboard_file("/../secret.txt") is None)
check("  including a nested escape",
      api._dashboard_file("/memory/../../secret.txt") is None)

print("== unknown paths ==")
st, _, _ = get("/no-such-page")
check("an unknown path is not served", st != 200, str(st))

print("== a build with no dashboard still works ==")
# A wheel whose dashboard build failed must serve the API and say so, rather
# than failing to install or refusing to start.
_saved = api.DASHBOARD_ROOT
api.DASHBOARD_ROOT = None
try:
    check("no bundle means the handler declines",
          api.Handler._serve_dashboard(object.__new__(api.Handler), "/") is False)
    check("  and resolution returns nothing", api._dashboard_file("/") is None)
finally:
    api.DASHBOARD_ROOT = _saved
st, _, body = get("/v1/health")
check("the API is unaffected either way", st == 200)

srv.shutdown()
shutil.rmtree(BUNDLE, ignore_errors=True)
shutil.rmtree(OUTSIDE, ignore_errors=True)
print(f"\n{_passed} passed, {_failed} failed")
sys.exit(1 if _failed else 0)
