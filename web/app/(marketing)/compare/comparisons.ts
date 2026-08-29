/* The comparison content, in one place.
 *
 * The rule for every word here: fair or absent. These pages exist for the
 * person searching "mem0 alternative" at the moment they are choosing, and
 * the fastest way to lose that person is to misdescribe the thing they were
 * just evaluating. Each alternative gets an honest "what it is good at"
 * before a word of contrast, claims about others stay at the category level
 * where they cannot rot, and every claim about OMEM is one the repository's
 * CI actually asserts. */

export interface Comparison {
  slug: string;
  name: string;
  eyebrow: string;
  title: string;
  lede: string;
  goodAt: { k: string; d: string }[];
  differs: { k: string; d: string }[];
  chooseThem: string[];
  chooseOmem: string[];
}

export const SHARED_DIFFERS = [
  {
    k: "Belief state, not stored strings",
    d: "Every claim has a state (believed, contradicted, unknown) computed from the evidence at query time. Two agents asserting opposite things produces CONTRADICTED with both sides on the record, never a silent overwrite.",
  },
  {
    k: "Conflicts are declared, never guessed",
    d: "Two claims disagree only when someone declared them opposed. No model reads your memories to decide they conflict, which is what keeps the same question giving the same answer a year later.",
  },
  {
    k: "Answers for itself",
    d: "Ask why about any belief and get the evidence chain: who said it, the quoted source, what was concluded from it, what contradicts it. The whole state replays from an append-only log, and omem-verify proves it rather than claims it.",
  },
  {
    k: "Takes things back",
    d: "Retract a fact and everything concluded from it is withdrawn in the same request, cascade included. Declared inference rules come with truth maintenance built in.",
  },
  {
    k: "Hunches that know they are hunches",
    d: "The intuition layer forms expectations from single examples, keeps a case file per hypothesis, interrogates its own guesses, and never lets a hunch pass as a belief. expects() and believes() are different verbs.",
  },
  {
    k: "Zero dependencies, committed license",
    d: "Stdlib-only Python (CI fails the build if a runtime dependency appears), SQLite by default, runs air-gapped. MIT, with a written commitment in CONTRIBUTING.md that the core stays MIT.",
  },
];

export const COMPARISONS: Comparison[] = [
  {
    slug: "mem0",
    name: "Mem0",
    eyebrow: "OMEM vs Mem0",
    title: "Mem0 remembers what was said. OMEM decides nothing about what is true.",
    lede: "Mem0 is a popular memory layer that extracts memories from conversations and retrieves them by relevance, with a managed platform if you want one. OMEM is a belief engine: it tracks what is currently believed, on what evidence, and what disagrees. Different questions, honestly different tools.",
    goodAt: [
      { k: "Fast conversational personalization", d: "Drop it into a chat product and it starts remembering user preferences with very little ceremony. That is a real strength and the reason for its adoption." },
      { k: "A managed service exists", d: "If you want memory as a hosted platform with someone else running it, that option is on the table. OMEM is self-hosted only, by design." },
      { k: "A large community", d: "Plenty of integrations, examples and answered questions. Ecosystem maturity counts for something real." },
    ],
    differs: [],
    chooseThem: [
      "You want a hosted, managed memory service",
      "The job is remembering user preferences in a chat product, and audit questions never come up",
      "You want the largest possible community around your memory layer",
    ],
    chooseOmem: [
      "Someone will eventually ask why the agent believed something, and you need a real answer",
      "Conflicting information must be surfaced, not silently resolved by recency",
      "You need to reconstruct what the agent believed at a past moment, exactly",
      "Your deployment is self-hosted, regulated, or air-gapped",
    ],
  },
  {
    slug: "zep",
    name: "Zep",
    eyebrow: "OMEM vs Zep",
    title: "Zep builds a knowledge graph of your sessions. OMEM keeps a court record.",
    lede: "Zep assembles conversations into a temporal knowledge graph and serves fast, relevant context, with a managed cloud. OMEM optimizes for a different property: every belief is an auditable claim with evidence, state, and a replayable history. Speed of recall versus defensibility of the record.",
    goodAt: [
      { k: "Temporal knowledge graphs", d: "Entities and relations extracted from sessions into a graph that understands time. Genuinely strong engineering, and a good fit for context assembly." },
      { k: "Session summarization at scale", d: "Long conversations become usable context without you building that pipeline." },
      { k: "A managed cloud", d: "If you want the graph without operating it, that exists. OMEM has no cloud; you run it." },
    ],
    differs: [],
    chooseThem: [
      "You want managed infrastructure and automatic graph construction from sessions",
      "The goal is rich context assembly rather than an auditable belief record",
      "Summarized history is acceptable as the source of truth",
    ],
    chooseOmem: [
      "The record matters: who asserted what, on what evidence, and what happened when it was contradicted",
      "Extraction must be inspectable and deterministic, with a model only ever proposing",
      "You need declared inference with take-backs, not just retrieval",
      "Zero-dependency, self-hosted, air-gap-friendly deployment is a requirement",
    ],
  },
  {
    slug: "letta",
    name: "Letta",
    eyebrow: "OMEM vs Letta",
    title: "Letta is an agent framework with memory. OMEM is memory for the agents you already have.",
    lede: "Letta (the MemGPT lineage) is an agent runtime where agents manage their own memory hierarchy. It answers the whole question of how to build an agent. OMEM answers one question extremely thoroughly: what does this agent believe, and why. It sits under whatever framework you already chose, through MCP, a REST API, or the SDK.",
    goodAt: [
      { k: "The whole agent runtime", d: "Agents, tools, and self-editing memory in one system, from the team that started the MemGPT line of thinking. If you are starting fresh, that completeness is attractive." },
      { k: "Self-editing memory hierarchy", d: "The core/archival memory design is a genuinely interesting answer to the context window problem." },
      { k: "An opinionated, integrated stack", d: "Fewer decisions for you to make, because the framework made them." },
    ],
    differs: [],
    chooseThem: [
      "You are starting from zero and want the framework and the memory as one decision",
      "Agents editing their own memory is the behaviour you want",
      "You are comfortable inside one integrated stack",
    ],
    chooseOmem: [
      "You already have an agent stack (LangGraph, Claude via MCP, your own) and need the belief layer under it",
      "Memory must survive audits: evidence chains, declared conflicts, replayable history",
      "You want the memory to be framework-agnostic so the stack can change without losing the record",
      "The intuition loop matters: hypotheses with case files, interrogation, calibration",
    ],
  },
];

export function getComparison(slug: string) {
  return COMPARISONS.find(c => c.slug === slug);
}
