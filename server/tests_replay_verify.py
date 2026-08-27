"""State is reproducible from the log, and an anchor detects when it is not.

Run: python3 tests_replay_verify.py

The point of these checks is the difference between the two failures they can
report. A log that replays to different state twice means the replay depends on
something outside the log. A log that replays consistently but disagrees with an
anchor recorded earlier means the LOG changed. The second is the one that
detects tampering, and the first cannot: a rewritten log replays perfectly
consistently with itself.

So the tampering check here rewrites an op in the database directly, the way
someone with write access would, and asserts that determinism still passes and
the anchor still fails. If both moved together, the anchor would be measuring
nothing the determinism check did not already cover.
"""
import json
import os
import subprocess
import sys
import threading
import time
import http.client

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

TMP = os.environ.get("TEMP") or "/tmp"
DB = os.path.join(TMP, "omem_replay_verify_tests.db")
ANCHOR = os.path.join(TMP, "omem_replay_anchor.json")
for f in (DB, ANCHOR):
    if os.path.exists(f):
        os.remove(f)
os.environ["OMEM_DB"] = DB
os.environ["OMEM_SEED_DEMO"] = "0"

import api  # noqa: E402
from http.server import ThreadingHTTPServer  # noqa: E402
import replay_verify  # noqa: E402

PASS = FAIL = 0


def check(n, c, d=""):
    global PASS, FAIL
    if c:
        PASS += 1
        print("  ok  " + n)
    else:
        FAIL += 1
        print("  FAIL " + n + "  " + str(d))


srv = ThreadingHTTPServer(("127.0.0.1", 0), api.Handler)
PORT = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()
time.sleep(0.2)


def call(m, path, body=None, key=None):
    c = http.client.HTTPConnection("127.0.0.1", PORT, timeout=10)
    h = {"Content-Type": "application/json"}
    if key:
        h["Authorization"] = "Bearer " + key
    c.request(m, path, body=json.dumps(body).encode() if body is not None else None, headers=h)
    r = c.getresponse()
    t = r.read().decode()
    st = r.status
    c.close()
    try:
        return st, json.loads(t or "{}")
    except Exception:
        return st, {}


# Unique per run. The sqlite path deletes its database at the top of this file
# and starts clean; a PostgreSQL one persists, so a second run of this suite
# against the same cluster hit "that address already has an account", signup
# returned no key, and the failure surfaced twelve lines later as
# KeyError: 'api_key'. CI never saw it because its postgres container is fresh
# every time, which is exactly the kind of thing that only breaks for whoever
# runs it locally twice.
st, acct = call("POST", "/v1/signup",
                {"email": "replay-%d-%d@x.com" % (os.getpid(), int(time.time()))})
assert "api_key" in acct, "signup did not return a key: %s" % str(acct)[:200]
KEY, PID = acct["api_key"]["secret"], acct["project"]["id"]
call("POST", "/v1/agents?project=" + PID, {"id": "agent:a", "kind": "ai"}, KEY)
call("POST", "/v1/entities?project=" + PID, {"id": "cust:1", "type": "customer"}, KEY)
call("POST", "/v1/assertions?project=" + PID,
     {"agent": "agent:a", "subjects": ["cust:1"], "proposition": "prefers_annual"}, KEY)
call("POST", "/v1/declare-contradiction?project=" + PID,
     {"token_a": "prefers_annual", "token_b": "prefers_monthly"}, KEY)
call("POST", "/v1/assertions?project=" + PID,
     {"agent": "agent:a", "subjects": ["cust:1"], "proposition": "prefers_monthly"}, KEY)

row = [r for r in api.STORE.projects_all() if r["id"] == PID][0]
ops = api.STORE.ops_for(PID)

print("== the digest is a function of the log ==")
d1, counts = replay_verify.state_digest(replay_verify.replay(api, row, ops))
d2, _ = replay_verify.state_digest(replay_verify.replay(api, row, ops))
check("two replays of one log agree", d1 == d2, d1 + " vs " + d2)
check("the digest is a sha256 hex", len(d1) == 64 and all(c in "0123456789abcdef" for c in d1), d1)
check("it counted the assertions", counts["assertions"] == 2, str(counts))

print("== the digest reflects BELIEF, not just rows ==")
# Two claims asserted about one subject with nothing said about whether they
# conflict: both BELIEVED_TRUE. Then declare them opposed. That adds no
# assertion row and changes no field on an existing one -- the only thing that
# moves is what the project BELIEVES, both sides becoming CONTRADICTED.
#
# So this isolates the property. A digest over stored rows alone cannot move
# here, and one that does not move is measuring storage rather than memory.
call("POST", "/v1/entities?project=" + PID, {"id": "cust:2", "type": "customer"}, KEY)
call("POST", "/v1/assertions?project=" + PID,
     {"agent": "agent:a", "subjects": ["cust:2"], "proposition": "ships_weekly"}, KEY)
call("POST", "/v1/assertions?project=" + PID,
     {"agent": "agent:a", "subjects": ["cust:2"], "proposition": "ships_monthly"}, KEY)
rows_before = len(api.STORE.ops_for(PID))
before, _ = replay_verify.state_digest(replay_verify.replay(api, row, api.STORE.ops_for(PID)))

call("POST", "/v1/declare-contradiction?project=" + PID,
     {"token_a": "ships_weekly", "token_b": "ships_monthly"}, KEY)
_ops = api.STORE.ops_for(PID)
after, _ = replay_verify.state_digest(replay_verify.replay(api, row, _ops))

_p = replay_verify.replay(api, row, _ops)
_state = _p.engine.proposition_state(["cust:2"], "ships_weekly", _p.now())
check("the belief actually flipped", _state == "CONTRADICTED", _state)
check("no assertion was added, only a declaration",
      len(_ops) == rows_before + 1, "%d -> %d" % (rows_before, len(_ops)))
check("declaring a contradiction moves the digest", before != after,
      before[:12] + " vs " + after[:12])

# Every remaining check runs the CLI as a subprocess against the same database,
# so the server has to be down first: two writers is exactly what OMEM refuses.
srv.shutdown()

print("== record an anchor, then verify against it ==")
r = subprocess.run([sys.executable, "replay_verify.py", "--json", "--record"],
                   cwd=HERE, capture_output=True, text=True,
                   env={**os.environ, "PYTHONIOENCODING": "utf-8"})
check("recording succeeds", r.returncode == 0, r.stdout[-200:] + r.stderr[-200:])
recorded = os.path.join(HERE, replay_verify.DIGEST_FILE)
check("it wrote a digest file", os.path.exists(recorded))
if os.path.exists(recorded):
    with open(recorded, encoding="utf-8") as fh:
        blob = json.load(fh)
    with open(ANCHOR, "w", encoding="utf-8") as fh:
        json.dump(blob, fh)
    check("the file names this project", PID in blob.get("projects", {}), str(blob)[:160])

r = subprocess.run([sys.executable, "replay_verify.py", "--json", "--anchor", ANCHOR],
                   cwd=HERE, capture_output=True, text=True,
                   env={**os.environ, "PYTHONIOENCODING": "utf-8"})
check("an untouched log matches its anchor", r.returncode == 0, r.stdout[-300:])
out = json.loads(r.stdout) if r.stdout.strip().startswith("{") else {}
check("and says so per project",
      (out.get("projects", {}).get(PID, {}).get("anchor")) == "match", str(out)[:200])

print("== a rewritten log still replays cleanly, and the anchor catches it ==")
# Tamper the way the system stores, not the way it looks in a plaintext dump.
# Reading the args column and json.loads-ing it works only while
# OMEM_ENCRYPT_AT_REST is off; with it on the column holds a "v1g." ciphertext
# token and the parse dies. Going through the same encrypt/decrypt helpers
# store.py uses means this exercises the identical scenario under both, which
# matters because encryption-on is a CI job and the whole point here is an
# attacker with database write access.
#
# And go through STORE.db rather than sqlite3.connect(DB). Under
# OMEM_DATABASE_URL the ops are in PostgreSQL and that sqlite file is empty, so
# a direct connection found no rows and died on None. The store's adapter is
# the same one the server writes through and translates placeholders for both
# backends, which is the point: an attacker edits the database the server
# actually uses.
from secrets_provider import decrypt_content, encrypt_content  # noqa: E402

#
# Scoped to THIS project. Without the project_id filter the query took the
# first assert op in the whole table, which is this project's only when the
# database contains nothing else. On PostgreSQL the suites share one database,
# so it rewrote an earlier suite's op instead, left this project untouched, and
# the anchor correctly reported "match" -- a tampering test that tampered with
# the wrong row and then passed for the wrong reason.
_db = api.STORE.db
_row = _db.execute(
    "SELECT seq, args FROM ops WHERE project_id=? AND kind='assert' ORDER BY seq",
    (PID,)).fetchone()
args = json.loads(decrypt_content(_row["args"]))
args["proposition"] = "prefers_monthly"          # rewrite what the agent said
_db.execute("UPDATE ops SET args=? WHERE seq=?",
            (encrypt_content(json.dumps(args)), _row["seq"]))
_db.commit()

r = subprocess.run([sys.executable, "replay_verify.py", "--json", "--anchor", ANCHOR],
                   cwd=HERE, capture_output=True, text=True,
                   env={**os.environ, "PYTHONIOENCODING": "utf-8"})
out = json.loads(r.stdout) if r.stdout.strip().startswith("{") else {}
entry = out.get("projects", {}).get(PID, {})
check("verification fails", r.returncode == 1, "exit " + str(r.returncode))
check("the anchor is what reports it", entry.get("anchor") == "MISMATCH", str(entry)[:200])
check("determinism still passes, so the anchor is not redundant",
      entry.get("deterministic") is True, str(entry)[:200])
check("and it names the digest it expected",
      entry.get("anchor_expected", "").startswith(blob["projects"][PID]["digest"][:8]),
      str(entry)[:200])

print("== a missing anchor file is an error, not a pass ==")
r = subprocess.run([sys.executable, "replay_verify.py", "--anchor", ANCHOR + ".nope"],
                   cwd=HERE, capture_output=True, text=True,
                   env={**os.environ, "PYTHONIOENCODING": "utf-8"})
check("missing anchor exits non-zero", r.returncode == 2, "exit " + str(r.returncode))

print("== an unknown project is an error ==")
r = subprocess.run([sys.executable, "replay_verify.py", "--project", "proj_nope"],
                   cwd=HERE, capture_output=True, text=True,
                   env={**os.environ, "PYTHONIOENCODING": "utf-8"})
check("unknown project exits non-zero", r.returncode == 1, "exit " + str(r.returncode))

try:
    os.remove(recorded)
except OSError:
    pass

print("\n%d passed, %d failed" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)
