"""omem-mcp works with nothing configured. Run: python3 tests_mcp_zeroconf.py

Being listed in the MCP registry and then requiring six setup steps is worse
than not being listed: people arrive, hit "start a server and copy a key out of
the terminal", and leave. The whole client config should be

    {"mcpServers": {"omem": {"command": "omem-mcp"}}}

so that is what this asserts, by running the real console entry point as a
subprocess and speaking real JSON-RPC to it, with every OMEM_* variable
stripped from the environment.

The three failure modes it covers are the ones that actually bite:

  stdout must carry only JSON-RPC. Any diagnostic printed there corrupts the
  stream and the client reports a parse error that names nothing useful.

  A restart must work immediately. MCP clients start and kill their servers
  constantly, and the writer lock presumed a dead holder alive for 90 seconds,
  so a restart inside that window was refused.

  Explicit configuration must still win, or anyone who already set
  OMEM_API_KEY silently gets a different database than the one they configured.
"""
import json
import os
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
SDK = os.path.abspath(os.path.join(HERE, "..", "sdk", "python"))
TMP = os.environ.get("TEMP") or "/tmp"
DATA = os.path.join(TMP, "omem_mcp_zeroconf_test")

PASS = FAIL = 0


def check(n, c, d=""):
    global PASS, FAIL
    if c:
        PASS += 1
        print("  ok  " + n)
    else:
        FAIL += 1
        print("  FAIL " + n + "  " + str(d)[:220])


if not os.path.isdir(os.path.join(SDK, "omem", "_server")):
    print("SKIP: sdk/python/omem/_server is not present. It is generated at "
          "build time by hatch_build.py; this suite needs the bundled copy.")
    sys.exit(0)

if os.path.isdir(DATA):
    shutil.rmtree(DATA, ignore_errors=True)


def spawn(extra_env=None):
    """The real entry point, with every OMEM_* variable removed."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("OMEM_")}
    env["PYTHONPATH"] = SDK
    env["PYTHONIOENCODING"] = "utf-8"
    env["OMEM_DATA_DIR"] = DATA
    env.update(extra_env or {})
    return subprocess.Popen([sys.executable, "-m", "omem.mcp_server"],
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, text=True, env=env, cwd=SDK)


def rpc(p, msg):
    p.stdin.write(json.dumps(msg) + "\n")
    p.stdin.flush()
    line = p.stdout.readline()
    return json.loads(line) if line.strip() else None


print("== it starts with nothing configured ==")
p = spawn()
try:
    init = rpc(p, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    check("initialize answers", init and init.get("result", {}).get(
        "serverInfo", {}).get("name") == "omem", str(init)[:200])
    tl = rpc(p, {"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    names = sorted(t["name"] for t in tl["result"]["tools"])
    check("the three tools are there",
          names == ["omem_observe", "omem_recall", "omem_why"], str(names))

    obs = rpc(p, {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {
        "name": "omem_observe", "arguments": {
            "text": "We have decided to renew the annual contract.",
            "speaker": "pat@acme.com"}}})
    out = json.loads(obs["result"]["content"][0]["text"])
    check("observing writes a memory", len(out.get("memories", [])) >= 1, str(out)[:200])

    rec = rpc(p, {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {
        "name": "omem_recall", "arguments": {"context": "acme renewal"}}})
    pack = json.loads(rec["result"]["content"][0]["text"])
    check("and recall returns it", len(pack.get("memories", [])) >= 1, str(pack)[:200])
    check("with a belief state attached",
          all("status" in m for m in pack.get("memories", [])), str(pack)[:200])
finally:
    p.stdin.close()
    p.kill()               # hard, exactly as an MCP client may
    p.wait(timeout=10)

print("== an empty result says what would have worked ==")
# An empty observe is usually correct: most of what is said is not worth
# remembering. But it is also what a first-time caller sees, and "nothing met
# the bar" reads as broken rather than strict. They close the tab without
# filing anything, because from where they stand there is nothing to report.
#
# By far the most common cause is a missing speaker -- extraction resolves the
# party from it -- and the MCP schema used to list speaker as optional, so a
# model would omit it and get nothing every time.
p_e = spawn()
try:
    rpc(p_e, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    tl = rpc(p_e, {"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    obs = [t for t in tl["result"]["tools"] if t["name"] == "omem_observe"][0]
    check("speaker is declared required, not optional",
          "speaker" in obs["inputSchema"].get("required", []),
          str(obs["inputSchema"].get("required")))
    check("the description tells the caller to pass it",
          "speaker" in obs["description"] and "records nothing" in obs["description"],
          obs["description"][:160])
    check("and carries an example that actually works",
          "We have decided to renew" in obs["description"], obs["description"][:160])

    r = rpc(p_e, {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {
        "name": "omem_observe", "arguments": {"text": "We have decided to renew."}}})
    note = json.loads(r["result"]["content"][0]["text"]).get("note", "")
    check("omitting speaker names that as the reason", "speaker" in note, note[:140])

    r = rpc(p_e, {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {
        "name": "omem_observe", "arguments": {
            "text": "Should we renew annually?", "speaker": "pat@acme.com"}}})
    note = json.loads(r["result"]["content"][0]["text"]).get("note", "")
    check("a non-claim gets the other reason, not the speaker one",
          "speaker" not in note and "durable claim" in note, note[:140])
    check("and that note says what IS remembered",
          "decided" in note.lower() or "commitment" in note.lower(), note[:140])
finally:
    p_e.stdin.close()
    p_e.terminate()
    p_e.wait(timeout=10)

print("== a project was created and remembered ==")
creds = os.path.join(DATA, "mcp-credentials.json")
check("credentials were stored", os.path.exists(creds), creds)
if os.path.exists(creds):
    with open(creds, encoding="utf-8") as fh:
        c = json.load(fh)
    check("with a key and a project",
          bool(c.get("api_key")) and bool(c.get("project")), str(sorted(c)))
    first_project = c.get("project")
else:
    first_project = None

print("== restarting immediately works, and keeps the same project ==")
# The previous process was killed, so it never released the writer lock. Before
# the dead-holder check this was refused for STALE_AFTER (90s), which is the
# ordinary MCP restart.
p2 = spawn()
try:
    init = rpc(p2, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    check("it starts again straight away", init is not None and "result" in init,
          str(init)[:200])
    rec = rpc(p2, {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {
        "name": "omem_recall", "arguments": {"context": "acme renewal"}}})
    pack = json.loads(rec["result"]["content"][0]["text"])
    check("the earlier memory is still there",
          len(pack.get("memories", [])) >= 1, str(pack)[:200])
    with open(creds, encoding="utf-8") as fh:
        check("and the project id did not change",
              json.load(fh).get("project") == first_project, first_project)
finally:
    p2.stdin.close()
    p2.terminate()
    p2.wait(timeout=10)
    err2 = p2.stderr.read()

print("== stdout carries only JSON-RPC ==")
# Everything above parsed as JSON, which is the real assertion. This checks the
# diagnostics went somewhere, and that somewhere was stderr.
check("diagnostics are on stderr", "omem-mcp:" in err2, err2[:200])

print("== explicit configuration still wins ==")
p3 = spawn({"OMEM_API_KEY": "omem_sk_not_a_real_key", "OMEM_PROJECT": "proj_nope"})
try:
    init = rpc(p3, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    check("it still starts", init is not None and "result" in init, str(init)[:160])
finally:
    p3.stdin.close()
    p3.terminate()
    p3.wait(timeout=10)
    err3 = p3.stderr.read()
check("and did NOT provision its own project",
      "created a project" not in err3 and "started OMEM" not in err3, err3[:200])

shutil.rmtree(DATA, ignore_errors=True)
print("\n%d passed, %d failed" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)
