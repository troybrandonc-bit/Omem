"""The n8n community node behaves, end to end, against a live server.
Run: python3 tests_n8n_node.py   (after building sdk/n8n-nodes-omem)

Drives the actual compiled node (dist/nodes/Omem/Omem.node.js) through a mock
n8n context, the same way n8n would call it: remember, the believes flip to
CONTRADICTED, conflicts, why, recall, observe, learn. Skips (its own outcome,
never a silent pass) when node or the built dist is absent, and the CI
integrations job builds the package so it never skips there.
"""
import json
import os
import shutil
import subprocess
import sys
import threading
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PKG = os.path.join(ROOT, "sdk", "n8n-nodes-omem")
DIST = os.path.join(PKG, "dist", "nodes", "Omem", "Omem.node.js")

node_bin = shutil.which("node")
if not node_bin or not os.path.exists(DIST):
    print("SKIP: needs `node` on PATH and a built sdk/n8n-nodes-omem/dist "
          "(npm install --ignore-scripts && npm run build). The CI "
          "integrations job builds it; plain server runs skip here.")
    sys.exit(0)

sys.path.insert(0, HERE)
TMP = os.environ.get("TEMP") or "/tmp"
DB = os.path.join(TMP, "omem_n8n_node.db")
if os.path.exists(DB):
    os.remove(DB)
os.environ["OMEM_DB"] = DB
os.environ.setdefault("OMEM_TENANT_RL_BURST", "10000")
os.environ.setdefault("OMEM_TENANT_RL_RPS", "10000")

import api  # noqa: E402
from http.server import ThreadingHTTPServer  # noqa: E402

srv = ThreadingHTTPServer(("127.0.0.1", 0), api.Handler)
PORT = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()
time.sleep(0.2)
BASE = "http://127.0.0.1:%d" % PORT

r = urllib.request.urlopen(urllib.request.Request(
    BASE + "/v1/signup", method="POST",
    data=json.dumps({"email": "n8nci@kronos.com"}).encode(),
    headers={"Content-Type": "application/json"}), timeout=15)
signup = json.load(r)

HARNESS = r"""
const { Omem } = require(process.env.N8N_NODE_PATH);
const creds = { baseUrl: process.env.OMEM_BASE, apiKey: process.env.OMEM_KEY, project: process.env.OMEM_PROJ };
function ctx(params) {
  return {
    getInputData: () => [{ json: {} }],
    getCredentials: async () => creds,
    getNodeParameter: (name) => params[name],
    getNode: () => ({ name: 'OMEM' }),
    continueOnFail: () => false,
    helpers: { httpRequest: async (o) => {
      const url = o.qs ? o.url + '?' + new URLSearchParams(o.qs) : o.url;
      const r = await fetch(url, { method: o.method, headers: o.headers, body: o.body ? JSON.stringify(o.body) : undefined });
      const text = await r.text();
      if (!r.ok) throw new Error(`HTTP ${r.status}: ${text.slice(0, 200)}`);
      return JSON.parse(text);
    }},
  };
}
(async () => {
  const node = new Omem();
  const run = (p) => node.execute.call(ctx(p)).then(r => r[0][0].json);
  let pass = 0, fail = 0;
  const check = (n, c, d) => { if (c) { pass++; console.log('  ok  ' + n); } else { fail++; console.log('  FAIL ' + n + ' ' + (d ?? '')); } };

  const r1 = await run({ operation: 'remember', agent: 'n8n', about: 'customer:alice', claim: 'prefers_annual_billing', evidenceNote: 'call note' });
  check('remember returns assertion id', typeof r1.id === 'string', JSON.stringify(r1).slice(0,120));
  const r2 = await run({ operation: 'believes', about: 'customer:alice', claim: 'prefers_annual_billing' });
  check('believes = BELIEVED_TRUE', r2.state === 'BELIEVED_TRUE', JSON.stringify(r2).slice(0,120));
  await run({ operation: 'remember', agent: 'n8n2', about: 'customer:alice', claim: 'not:prefers_annual_billing', evidenceNote: '' });
  const r3 = await run({ operation: 'believes', about: 'customer:alice', claim: 'prefers_annual_billing' });
  check('believes flips to CONTRADICTED', r3.state === 'CONTRADICTED', JSON.stringify(r3).slice(0,120));
  const r4 = await run({ operation: 'conflicts' });
  check('conflicts lists the disagreement', JSON.stringify(r4).includes('prefers_annual_billing'));
  const r5 = await run({ operation: 'why', assertionId: r1.id });
  check('why returns state + provenance', typeof r5.state === 'string' && !!r5.provenance);
  const r6 = await run({ operation: 'recall', recallAbout: 'customer:alice', asOf: '', limit: 10 });
  check('recall finds memories', (r6.count ?? 0) >= 1, JSON.stringify(r6).slice(0,120));
  const r7 = await run({ operation: 'observe', agent: 'n8n', text: 'Alice prefers email over calls.', source: 'n8n' });
  check('observe accepted', !!r7 && r7.observed === true, JSON.stringify(r7).slice(0,120));
  const r8 = await run({ operation: 'learn', agent: 'n8n', text: 'The customer wants to upgrade.', learnAbout: 'customer:alice', source: 'n8n' });
  check('learn produced beliefs', Array.isArray(r8.learned));

  console.log(`${pass} passed, ${fail} failed`);
  process.exit(fail ? 1 : 0);
})().catch(e => { console.error('HARNESS ERROR:', e.message); process.exit(1); });
"""

harness_path = os.path.join(TMP, "omem_n8n_harness.js")
with open(harness_path, "w", encoding="utf-8") as f:
    f.write(HARNESS)

env = {**os.environ,
       "N8N_NODE_PATH": DIST,
       "OMEM_BASE": BASE,
       "OMEM_KEY": signup["api_key"]["secret"],
       "OMEM_PROJ": signup["project"]["id"]}
p = subprocess.run([node_bin, harness_path], capture_output=True, text=True,
                   timeout=180, env=env)
sys.stdout.write(p.stdout)
if p.returncode != 0:
    sys.stdout.write(p.stderr[:500])
    print("\n0 passed, 1 failed (harness rc=%d)" % p.returncode)
    sys.exit(1)
sys.exit(0)
