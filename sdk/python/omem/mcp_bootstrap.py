"""Make `omem-mcp` work with nothing configured.

Before this, using OMEM from an MCP client took six steps: pip install, start
omem-server, keep it running, copy a project id and an API key out of the
terminal, paste both into a JSON config, restart the client. A typical MCP
server is one JSON block. Being in the registry and then losing people at step
three is worse than not being listed.

With this, the whole configuration is:

    {"mcpServers": {"omem": {"command": "omem-mcp"}}}

Nothing here is new capability. The server already ships inside the wheel and
already provisions a project and key on first run; this just does those steps
for you and remembers the answer.

HOW IT RESOLVES, in order:

  1. OMEM_API_KEY set -> use exactly what you configured, unchanged. Explicit
     configuration always wins; this file never overrides it.
  2. A server is already answering on OMEM_BASE_URL and we have credentials
     stored for it -> use that. Someone running `omem-server` in a terminal
     gets their own data, not a second copy.
  3. Otherwise -> start the bundled server in this process on a loopback port
     nobody else is using, against ~/.omem, and provision once.

TWO THINGS THAT WOULD BREAK IT IF DONE NAIVELY:

  stdout is the MCP transport. A single stray print corrupts the JSON-RPC
  stream and the client reports an unhelpful parse error, so everything here
  writes to stderr and stdout is captured during setup.

  One writer per database. Booting a second engine over a database another
  process is writing would leave two engines answering the same question
  differently with nothing erroring. The lock is acquired before serving, and
  a failure to get it means an `omem-server` is already up: that is a reason to
  connect to it, not to fight it.
"""
import contextlib
import io
import json
import os
import socket
import sys
import threading
import time
import urllib.error
import urllib.request

DEFAULT_URL = "http://127.0.0.1:8787"


def _log(msg):
    """Never stdout. That belongs to the protocol."""
    sys.stderr.write("omem-mcp: %s\n" % msg)
    sys.stderr.flush()


def _data_dir():
    d = os.environ.get("OMEM_DATA_DIR") or os.path.join(
        os.path.expanduser("~"), ".omem")
    os.makedirs(d, exist_ok=True)
    return d


def _creds_path(d):
    return os.path.join(d, "mcp-credentials.json")


def _load_creds(d):
    try:
        with open(_creds_path(d), encoding="utf-8") as fh:
            c = json.load(fh)
        if c.get("api_key") and c.get("project"):
            return c
    except (OSError, ValueError):
        pass
    return None


def _save_creds(d, creds):
    path = _creds_path(d)
    try:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(creds, fh, indent=2)
        try:
            os.chmod(path, 0o600)      # best effort; no-op on some filesystems
        except OSError:
            pass
    except OSError as e:
        _log("could not save credentials to %s (%s). A new project will be "
             "created next start." % (path, e))


def _reachable(url, timeout=1.5):
    try:
        req = urllib.request.Request(url.rstrip("/") + "/v1/health")
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return 200 <= r.status < 500
    except urllib.error.HTTPError:
        return True                     # answering, just not 200
    except Exception:
        return False


def _signup(url, timeout=20):
    """Create a project and key. The server does this on any fresh database."""
    body = json.dumps({"email": "mcp@omem.local"}).encode()
    req = urllib.request.Request(url.rstrip("/") + "/v1/signup", data=body,
                                 headers={"Content-Type": "application/json"},
                                 method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        d = json.loads(r.read().decode())
    return {"api_key": d["api_key"]["secret"], "project": d["project"]["id"],
            "base_url": url}


def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _release_quietly(lock):
    """Best effort. A failure here must never be the last thing a user sees."""
    try:
        lock.release()
    except Exception:
        pass


def _start_embedded(data_dir):
    """Serve the bundled server in this process. Returns its base URL, or None.

    In-process rather than a subprocess so the server dies with the MCP client
    instead of outliving it. An MCP client can be closed at any moment and a
    stray detached server holding the writer lock is a confusing thing to leave
    on somebody's machine.
    """
    here = os.path.dirname(os.path.abspath(__file__))
    server_dir = os.path.join(here, "_server")
    if not os.path.isdir(server_dir):
        _log("bundled server not found; reinstall omem-infrastructure")
        return None
    sys.path.insert(0, server_dir)
    os.environ.setdefault("OMEM_DB", os.path.join(data_dir, "omem.db"))
    os.environ.setdefault("OMEM_SEED_DEMO", "0")

    # Importing and booting must not touch stdout. It does not today, and a
    # future print would be an invisible protocol corruption rather than a
    # visible bug, so it is captured rather than trusted.
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            import api  # noqa: E402
            from http.server import ThreadingHTTPServer  # noqa: E402
            try:
                api.STORE.writer_lock.acquire()
            except (Exception, SystemExit):
                # SystemExit, not Exception: WriterLock.acquire raises
                # SystemExit so that `omem-server` prints the refusal and stops.
                # `except Exception` does not catch it, so an unavailable lock
                # killed omem-mcp outright instead of falling back.
                _log("another OMEM process is writing this database; "
                     "will use the running server instead")
                return None
            # Hand the lock back when this process ends. An MCP client starts
            # and stops its servers constantly, and the holder is presumed dead
            # only after STALE_AFTER (90s) -- so without this, restarting a
            # client within a minute and a half refuses to start, which is
            # exactly the workflow MCP has.
            import atexit
            atexit.register(_release_quietly, api.STORE.writer_lock)
            port = _free_port()
            httpd = ThreadingHTTPServer(("127.0.0.1", port), api.Handler)
    except Exception as e:
        _log("could not start the bundled server: %s: %s" % (type(e).__name__, e))
        return None
    finally:
        if buf.getvalue():
            _log("suppressed server output: %s" % buf.getvalue().strip()[:300])

    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    url = "http://127.0.0.1:%d" % port
    for _ in range(60):
        if _reachable(url, timeout=0.5):
            return url
        time.sleep(0.1)
    _log("bundled server did not become healthy")
    return None


def resolve():
    """Return (api_key, base_url, project), provisioning if needed.

    Returns (None, None, None) when it cannot, so the caller can print
    something better than a stack trace.
    """
    explicit = os.environ.get("OMEM_API_KEY")
    if explicit:
        return (explicit,
                os.environ.get("OMEM_BASE_URL", DEFAULT_URL),
                os.environ.get("OMEM_PROJECT"))

    data_dir = _data_dir()
    creds = _load_creds(data_dir)

    # Reuse a server someone is already running, but only with credentials
    # issued by it. A key from a different database is not a login there.
    running = os.environ.get("OMEM_BASE_URL", DEFAULT_URL)
    if creds and creds.get("base_url") == running and _reachable(running):
        _log("using the OMEM server already running at %s" % running)
        return creds["api_key"], running, creds["project"]

    url = _start_embedded(data_dir)
    if url is None:
        if _reachable(running):
            try:
                creds = _signup(running)
                _save_creds(data_dir, creds)
                _log("registered with the running server at %s" % running)
                return creds["api_key"], running, creds["project"]
            except Exception as e:
                _log("could not register with %s: %s" % (running, e))
        return None, None, None

    # The embedded server may be reopening the same database as a previous run,
    # in which case the stored credentials are still valid for it.
    if creds:
        try:
            req = urllib.request.Request(
                url + "/v1/assertions?project=" + creds["project"],
                headers={"Authorization": "Bearer " + creds["api_key"]})
            with urllib.request.urlopen(req, timeout=5) as r:
                if r.status == 200:
                    _log("started OMEM (data in %s)" % data_dir)
                    return creds["api_key"], url, creds["project"]
        except Exception:
            pass                        # stale or from another database; reissue

    try:
        creds = _signup(url)
    except Exception as e:
        _log("could not create a project: %s: %s" % (type(e).__name__, e))
        return None, None, None
    creds["base_url"] = url
    _save_creds(data_dir, creds)
    _log("started OMEM and created a project (data in %s)" % data_dir)
    return creds["api_key"], url, creds["project"]
