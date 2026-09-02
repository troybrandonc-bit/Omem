# OMEM product marketing context

The canonical context doc the marketing skills read before any task. Update it
when positioning changes; do not re-derive this per task.

## What OMEM is

Open-source (MIT) system of record for what an AI agent believed and did, built on belief revision, not a vector
store. It keeps both sides of a contradiction, tracks what was believed and
when, answers "why" with a provenance chain, and puts a human approval step
before a risky action runs. Self-hosted, one `pip install omem-infrastructure`,
no dependencies, dashboard included. Runs on the user's machine and phones home
to nobody (CI-asserted).

## Positioning (decided 30 Aug 2026, roast-tested)

**Lead with accountability, never with memory.** "Prove why your agent did
that, and approve before it acts." Belief-revision memory is commoditised
(Mem0, Zep, and a near-clone MnemeBrain all ship contradiction-keeping +
provenance); the accountability surface sold to teams shipping agents to
clients is the differentiated, monetisable wedge. The engine is the HOW that
makes the answer trustworthy, not the pitch.

**The identity beneath it (the objective):** teach AI what people are like
while holding a fact about no one. OMEM learns priors ("people who do X tend
to do Y") as counts that name nobody; consenting installs pool them into a
shared bank offered as an AI training corpus (CC BY). A prior always yields to
the individual.

## ICP: two audiences, different motions

- **Adopters (free core, community):** indie and small-team AI agent builders,
  LLM devs, self-hosters who hit "two facts conflict and one silently wins."
  They value MIT, no deps, runs-on-my-machine, auditability. Found on
  r/LocalLLaMA, r/LLMDevs, r/AI_Agents, r/selfhosted, HN, GitHub.
- **Buyers (revenue):** technical leads at small teams and AI agencies (3-15
  people) shipping agents TO clients, who face client security reviews and get
  asked "why did it do that" and "can a human approve first". They buy the
  audit trail and approval gate, reachable by demand-signal outbound, not
  broadcast. IMPORTANT: the free adopter and the paying buyer are different
  people; do not assume a funnel between them.

## Offer and pricing

- Software: free, MIT, forever (public commitment; never propose relicensing).
- Design-partner pilot: $1,500, hands-on, ~2 weeks; buys the founder's time to
  wire the approval gate + provenance trail into the buyer's agent. Not a
  license. CTA is the form at /pilot.
- Future paid tier: "OMEM Approve", the governed layer on top of the OSS
  judgment queue (SSO-gated approvals, policy on who judges what, audit
  exports). Not yet built; funded by pilots.

## Proof points (all real, never fabricate others)

- Every load-bearing claim is CI-asserted (the claims ledger, CLAIMS.md).
- Witness benchmark (testimony, not recall) with published card; Mem0/Graphiti
  adapters run with the user's own keys.
- Airgap test: one non-loopback connection fails the build.
- Frozen engine: byte-identical replay; upgrades never rewrite the past.
- Right to be forgotten, executed for real and replay-verified.
- NO third-party social proof yet (no stars milestone, no testimonials, no
  logos). Do not invent any.

## Voice (non-negotiable)

Precise, declarative, honest about what it is and is not. No hype, no
"revolutionary", no fabricated numbers, no exclamation points, NO EM DASHES.
First person singular for founder outreach (Troy). Honesty is the brand: the
site keeps a "not built yet" list on purpose.

## Channels and assets

- Site: infrastructure.omem-cloud.com (Cloudflare Pages, deploys from main).
  Key pages: / (accountability hero), /accountability, /pilot (form),
  /objectives, /compare/{mem0,zep,letta}, /guides, /security, /pricing.
- Collector: commons.omem-cloud.com (password-walled; public holes are
  contribution-in and anonymised dataset-out only).
- Social: X @Omem_ai, Reddit u/Omem-ai (+ r/OMEM planned). First Reddit posts
  went live 31 Aug 2026.
- Drafted assets: distribution/reddit/posts-ready.md, marketing/essay
  (cornerstone), marketing/outbound-kit.md, marketing/plan.md (AARRR),
  marketing/roast-verdict.md, marketing/competitive-positioning.md.

## Competitors (researched 30 Aug 2026)

Mem0 ($24M A, AWS Agent SDK default), Zep/Graphiti (temporal KG, provenance),
Letta/MemGPT, Cognee, MnemeBrain (solo, near-identical engine pitch, tiny).
Rule: never fight on engine rigor; fight on product + buyer (accountability).

## Constraints

Solo founder (Troy), ~$0 paid budget, pre-revenue, needs pilots. Skills should
bias to zero-cost compounding assets and founder-led channels. Claude drafts,
Troy posts/sends anything public.
