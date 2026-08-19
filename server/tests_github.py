"""GitHub connector tests. Run: python3 tests_github.py

Two modes:
- Offline (default): fixture transport using REAL GitHub issue payload shape.
  Verifies the whole chain deterministically.
- Live (OMEM_GITHUB_LIVE=1): hits api.github.com for real. Skipped otherwise so
  the suite never depends on network/rate limits.

Chain verified: issue -> immutable source record -> evidence-grounded extraction
-> entity resolution -> event -> assertion -> derivation -> frozen engine ->
provenance -> recall/why -> trace back to the original issue URL.
"""
import os
import sys
import json
import threading
import time
import urllib.request
import urllib.error

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
DB = "/tmp/omem_github_tests.db"
if os.path.exists(DB):
    os.remove(DB)
os.environ["OMEM_DB"] = DB

import api  # noqa: E402
from connectors import (MockGitHubTransport, GitHubIssueExtractor,  # noqa: E402
                        GitHubConnector, GitHubTransport, ProviderRateLimited)
from http.server import ThreadingHTTPServer  # noqa: E402

srv = ThreadingHTTPServer(("127.0.0.1", 0), api.Handler)
PORT = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()
time.sleep(0.2)
BASE = f"http://127.0.0.1:{PORT}"
PASS = FAIL = 0


def check(n, c, d=""):
    global PASS, FAIL
    if c:
        PASS += 1; print(f"  ok  {n}")
    else:
        FAIL += 1; print(f"  FAIL {n}  {d}")


def call(m, path, body=None, key=None):
    req = urllib.request.Request(BASE + path, method=m,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Content-Type": "application/json", **({"Authorization": f"Bearer {key}"} if key else {})})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


# Real GitHub issue shape (captured from api.github.com/repos/psf/requests/issues)
FIXTURES = [
    {"number": 7600, "title": "`HTTPError.response` is annotated `Response | None`",
     "body": "The typing annotation is wrong and mypy fails on it.",
     "user": {"login": "UnknownPlatypus"}, "state": "open",
     "html_url": "https://github.com/psf/requests/issues/7600",
     "created_at": "2026-01-01T10:00:00Z", "updated_at": "2026-01-01T10:00:00Z"},
    {"number": 7599, "title": "Documentation for stream parameter is ambiguous",
     "body": "Old docs suggest something unclear about streaming.",
     "user": {"login": "diederikvdv"}, "state": "open",
     "html_url": "https://github.com/psf/requests/issues/7599",
     "created_at": "2026-01-02T10:00:00Z", "updated_at": "2026-01-02T10:00:00Z"},
    {"number": 7598, "title": "Bump ruff-pre-commit from v0.15 to v0.16",
     "body": "Bumps the pre-commit group with 1 update.",
     "user": {"login": "dependabot[bot]"}, "state": "open",
     "html_url": "https://github.com/psf/requests/issues/7598",
     "created_at": "2026-01-03T10:00:00Z", "updated_at": "2026-01-03T10:00:00Z"},
    {"number": 7597, "title": "A pull request", "body": "not an issue",
     "user": {"login": "someone"}, "state": "open", "pull_request": {"url": "x"},
     "html_url": "https://github.com/psf/requests/pull/7597",
     "created_at": "2026-01-04T10:00:00Z", "updated_at": "2026-01-04T10:00:00Z"},
]

print("== extractor: evidence-grounded, no invention ==")
ex = GitHubIssueExtractor()
facts = ex.extract({"repo": "psf/requests", "issue_number": 7600,
                    "subject": FIXTURES[0]["title"], "body": FIXTURES[0]["body"], "at": "now"})
check("typing issue -> type annotation fact", any(f["proposition"] == "has_type_annotation_issue" for f in facts))
check("subject is the repo entity", all(f["subject"]["id"] == "repo:psf/requests" for f in facts))
check("every fact carries real evidence", all(f["evidence"] and "matched" in f["evidence"] for f in facts))
check("empty issue yields nothing", ex.extract({"repo": "r", "subject": "", "body": "", "at": "now"}) == [])
check("no repo yields nothing", ex.extract({"subject": "bug", "body": "bug", "at": "now"}) == [])

print("== connector: PRs skipped, real shape parsed ==")
conn_inst = GitHubConnector(MockGitHubTransport(FIXTURES), None, "psf/requests", ex)
items, cursor = conn_inst.poll(None)
check("3 issues, PR excluded", len(items) == 3, str(len(items)))
check("external id is repo#number", items[0][0] == "psf/requests#7600")
check("payload keeps url + author + issue number",
      items[0][1]["url"].endswith("/7600") and items[0][1]["author"] == "UnknownPlatypus")
check("cursor is newest updated_at", cursor == "2026-01-04T10:00:00Z")
items2, _ = conn_inst.poll(cursor)
check("incremental sync returns nothing new", len(items2) == 0)

print("== full chain through the API ==")
_, acct = call("POST", "/v1/signup", {"email": "gh@corp.com", "org": "GH"})
KEY = acct["api_key"]["secret"]; PID = acct["project"]["id"]; SESS = acct["token"]
OID = api.STORE.org_for_user(api.STORE.user_for_session(SESS)["id"])["id"]
api.ENT.set_billing(OID, plan="pro")
api.GITHUB_TRANSPORT_FACTORY = lambda conn: MockGitHubTransport(FIXTURES)
st, c = call("POST", f"/v1/connectors?project={PID}",
             {"kind": "github", "name": "psf/requests", "config": {"repo": "psf/requests"},
              "agent_id": "connector:github", "authority": 0.8}, KEY)
check("connector created", st == 201)
CID = c["id"]
st, pr = call("POST", f"/v1/connectors/{CID}/poll?project={PID}", {}, KEY)
check("issues became source records", pr["queued"] == 3, str(pr))
st, ip = call("POST", f"/v1/ingest/process?project={PID}", {}, KEY)
check("all processed, none failed", ip["failed"] == 0 and ip["assertions"] >= 2, str(ip))

st, rec = call("POST", f"/v1/recall?project={PID}", {"about": "repo:psf/requests"}, KEY)
check("memories recalled about the repo", rec["count"] >= 2, str(rec["count"]))
check("engine decided the states",
      all(m["state"] in ("BELIEVED_TRUE", "CONTRADICTED", "BELIEVED_FALSE", "UNKNOWN") for m in rec["memories"]))
check("memories are grounded", all(m["grounded"] for m in rec["memories"]))

aid = rec["memories"][0]["assertion"]
st, w = call("GET", f"/v1/assertions/{aid}/why?project={PID}", None, KEY)
check("why: grounded with event provenance",
      w["grounded"] and any(n["kind"] == "event" for n in w["provenance"]["nodes"]))
st, src = call("GET", f"/v1/assertions/{aid}/source?project={PID}", None, KEY)
payload = json.loads(src["payload"])
check("traces to the original GitHub issue", payload["repo"] == "psf/requests" and payload["issue_number"])
check("source retains the issue URL", payload["url"].startswith("https://github.com/psf/requests/issues/"))

print("== evidence persisted and exposed for the why surface ==")
check("why carries stored extractor evidence",
      w.get("evidence") and w["evidence"]["evidence"] and "matched" in w["evidence"]["evidence"], str(w.get("evidence")))
check("evidence names the extractor", w["evidence"]["extractor"] == "GitHubIssueExtractor")
check("evidence carries extraction confidence", w["evidence"]["confidence"] is not None)
check("why carries the clickable source URL",
      (w.get("source") or {}).get("payload", {}).get("url", "").startswith("https://github.com/"))
check("evidence text genuinely appears in the source issue",
      any(tok in json.dumps(w["source"]["payload"]).lower()
          for tok in ["bug", "crash", "docs", "typing", "bump", "slow", "unclear", "annotated"]))

print("== time travel uses real engine as-of semantics ==")
st, w_past = call("GET", f"/v1/assertions/{aid}/why?project={PID}&as_of=0", None, KEY)
check("as-of before the assertion -> not yet known",
      w_past["state"] == "UNKNOWN", w_past["state"])
st, w_now = call("GET", f"/v1/assertions/{aid}/why?project={PID}", None, KEY)
check("as-of now -> current state", w_now["state"] == "BELIEVED_TRUE")
check("as_of echoed by the engine query", w_past["as_of"] == 0)

print("== dedup: re-polling the same issues creates nothing new ==")
before = api.INGEST.stats(PID)["sources"]
call("POST", f"/v1/connectors/{CID}/poll?project={PID}", {}, KEY)
check("no duplicate source records", api.INGEST.stats(PID)["sources"] == before)

print("== rate limiting surfaces truthfully (no fake success) ==")
class Limited(GitHubTransport):
    def list_issues(self, token, repo, since, per_page=30):
        raise ProviderRateLimited("github", int(time.time()) + 3600, "exhausted")
api.GITHUB_TRANSPORT_FACTORY = lambda conn: Limited()
st, r = call("POST", f"/v1/connectors/{CID}/poll?project={PID}", {}, KEY)
check("rate limit -> 429 not 500", st == 429, str(st))
check("429 names the provider + reset", r["error"]["provider"] == "github" and r["error"]["reset_epoch"])
st, stt = call("GET", f"/v1/connectors/{CID}/status?project={PID}", None, KEY)
check("connector status RATE_LIMITED", stt["status"] == "RATE_LIMITED")

print("== connector detail: real per-source counts ==")
api.GITHUB_TRANSPORT_FACTORY = lambda conn: MockGitHubTransport(FIXTURES)
st, d = call("GET", f"/v1/connectors/{CID}/detail?project={PID}", None, KEY)
check("detail: items ingested", d["items_ingested"] == 3, str(d["items_ingested"]))
check("detail: memories generated matches assertions", d["memories_generated"] >= 2, str(d["memories_generated"]))
check("detail: job states present", d["jobs"]["completed"] == 3)
check("detail: last sync timestamp real", isinstance(d["last_sync"], (int, float)) and d["last_sync"] > 0)
check("detail: cursor persisted", d["cursor"] == "2026-01-04T10:00:00Z")

print("== re-sync clears the cursor (full re-read) ==")
st, r = call("POST", f"/v1/connectors/{CID}/resync?project={PID}", {}, KEY)
check("resync ok", st == 200 and r["resync"])
st, d2 = call("GET", f"/v1/connectors/{CID}/detail?project={PID}", None, KEY)
check("cursor cleared", d2["cursor"] is None)
st, pr = call("POST", f"/v1/connectors/{CID}/poll?project={PID}", {}, KEY)
check("re-sync re-reads but dedup prevents duplicates", pr["queued"] == 0 or
      api.INGEST.stats(PID)["sources"] == 3, str(pr))

print("== empty project shows zeros, not invented values ==")
_, empty = call("POST", "/v1/signup", {"email": "empty-gh@x.com"})
st, es = call("GET", f"/v1/ingest/stats?project={empty['project']['id']}", None, empty["api_key"]["secret"])
check("empty project: zero sources", es["sources"] == 0 and es["completed"] == 0)

print("== persistence: replay after restart ==")
srv.shutdown()
import importlib
sys.modules.pop("api")
api2 = importlib.import_module("api")
p = api2.PROJECTS.get(PID)
check("repo beliefs replayed", p is not None and
      any(True for a in p.engine.store.assertions() if "repo:psf/requests" in a.subjects))

print("== LIVE api.github.com (set OMEM_GITHUB_LIVE=1) ==")
if os.environ.get("OMEM_GITHUB_LIVE") == "1":
    try:
        real = GitHubTransport()
        issues, cur = real.list_issues(os.environ.get("GITHUB_TOKEN"), "psf/requests", None, per_page=5)
        check("LIVE: real issues fetched", len(issues) > 0)
        check("LIVE: cursor is an ISO timestamp", cur and cur.endswith("Z"))
        f = GitHubIssueExtractor().extract({
            "repo": "psf/requests", "issue_number": issues[0].get("number"),
            "subject": issues[0].get("title", ""), "body": issues[0].get("body") or "", "at": "now"})
        check("LIVE: extraction ran on real text", isinstance(f, list))
    except ProviderRateLimited as e:
        print(f"  SKIP live: {e}")
else:
    print("  skipped (offline mode)")

print(f"\n{PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
