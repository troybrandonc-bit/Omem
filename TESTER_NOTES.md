What a tester sees (cleaned for testing)
========================================
- NO placeholder/demo data. A fresh signup starts with an EMPTY project — the
  dashboard shows only the memories you actually create, never fabricated rows.
  (The old sample "Alice/Bob" demo is off by default; set OMEM_SEED_DEMO=1 only
  if you want the sample project back for a screenshot.)
- The dashboard is trimmed to the memory surface: Home, Memory, Intelligence,
  Memory health, Agents, Entities, Timeline, Conflicts, Graph, Playground, API,
  Logs, Diagnostics, Usage, Team, Audit, Settings.
- Connector/ingestion features (Gmail, Slack, etc.) are NOT shown in the nav and
  are not part of the testing path. The code remains in the server but is dormant
  and does not affect using OMEM via the SDK, MCP, or the dashboard.
- All dashboard numbers are real (fetched from the API). When there is no data
  for something, it shows an empty state — never a random number.

Setup stays ~1 minute, zero dependencies — see QUICKSTART.md, which now
exists (this line pointed at a missing file).

Note: the web dashboard is optional and requires `npm install && npm run dev`
in web/. The core testing path (server + `pip install omem-infrastructure` +
SDK/MCP) needs none of that.
