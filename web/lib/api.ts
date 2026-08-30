// Typed client for the OMEM API. Every method hits a real endpoint on the
// backend (server/api.py), which delegates to the authoritative OMEM engine.
// No memory semantics live here. This is transport + types only.

// Where the API is.
//
//   bundled (static export served BY the Python server) -> "" , i.e. same
//     origin, so the client calls /v1/... directly. No proxy, no CORS, no
//     configuration, and it works on whatever host and port the server was
//     started on rather than a hardcoded one.
//   npm run dev -> "/api/omem", the rewrite in next.config.js.
//
// NEXT_PUBLIC_OMEM_API still overrides both, for a dashboard hosted apart from
// its server.
const BASE = process.env.NEXT_PUBLIC_OMEM_API
  ?? (process.env.NEXT_PUBLIC_OMEM_BUNDLED === "1" ? "" : "/api/omem");

export type PropositionState = "BELIEVED_TRUE" | "BELIEVED_FALSE" | "CONTRADICTED" | "UNKNOWN";

export interface BeliefInterval { start: number; end: number | null; }
export interface Assertion {
  id: string; label?: string | null; agent: string; subjects: string[];
  proposition: string; assertion_time: number; event_time: number | null;
  confidence: number | null; belief_interval: BeliefInterval; open: boolean;
  grounded: string | boolean; provenance_count: number; is_retraction: boolean;
  // Real wall-clock seconds this was written, for a human-readable "when".
  // assertion_time above is the LOGICAL clock the engine reasons in.
  recorded_at?: number | null;
}

/** A real timestamp, read the way a person reads a feed: the clock for today,
 *  a relative age for the last week, a date before that. Falls back to the
 *  logical tick only when no wall-clock is known (older records). Returns the
 *  short text plus a full timestamp for the title attribute. */
export function formatWhen(recordedAt?: number | null, tick?: number | null): { text: string; title: string } {
  if (recordedAt == null || !isFinite(recordedAt)) {
    return { text: tick != null ? `t${tick}` : "", title: "logical time" };
  }
  const ms = recordedAt * 1000;
  const d = new Date(ms);
  const title = d.toLocaleString();
  const diff = Date.now() - ms;
  const day = 86_400_000;
  if (diff >= 0 && diff < day && d.getDate() === new Date().getDate()) {
    return { text: d.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" }), title };
  }
  if (diff >= 0 && diff < 7 * day) {
    const days = Math.max(1, Math.round(diff / day));
    return { text: `${days}d ago`, title };
  }
  return { text: d.toLocaleDateString(undefined, { month: "short", day: "numeric" }), title };
}
export interface Entity { id: string; type?: string; label?: string | null; connections?: number; }
export interface EntityPage { data: Entity[]; total: number; offset: number; limit: number; }
export interface NeighborNode { id: string; label: string; hops: number; }
export interface NeighborEdge { src: string; relation: string; dst: string; }
export interface NeighborGraph { entity: string; as_of: number; depth: number; nodes: NeighborNode[]; edges: NeighborEdge[]; }
export interface Agent { id: string; kind?: string; label?: string | null; recorded_existence?: number; claims?: Assertion[]; }
export interface EventPrim { id: string; kind?: string; label?: string | null; event_time?: number | null; recorded_at?: number | null; }
export interface ProvNode { id: string; kind: string; root?: boolean; label?: string | null; }
export interface ProvEdge { from: string; to: string; kind: string; }
export interface EvidenceRecord { assertion_id: string; source_record_id: string | null; evidence: string | null; confidence: number | null; extractor: string | null; created: number; }
export interface SourceView {
  kind: string; connector: string; external_id: string; received: number;
  title: string; from: string | null; from_name: string | null; from_email: string | null;
  to: string | null; sent_at: string | null; body: string; snippet: string; link: string | null;
}
export interface SourceRef { id: string; external_id: string; connector_id: string; received: number; payload: Record<string, unknown>; view?: SourceView; }
export interface WhyResult {
  assertion: Assertion; as_of: number; state: PropositionState; grounded: boolean;
  confidence?: { score: number; because: string[] };
  provenance: { nodes: ProvNode[]; edges: ProvEdge[] };
  revision_chain: Assertion[]; contradictions: Assertion[];
  subjects: (Entity | null)[]; agent: Agent | null;
  evidence?: EvidenceRecord | null;
  source?: SourceRef | null;
}
export interface Overview {
  now: number;
  // What real second each logical tick was recorded at, sorted by tick, so the
  // "as of" control can travel in real dates instead of tick numbers.
  clock?: { t: number; ts: number }[];
  counts: { entities: number; agents: number; events: number; assertions: number; open_beliefs: number; conflicts: number; };
  grounded_ratio: number; activity: LogEntry[];
}
export interface ConflictPair { pair: [Assertion, Assertion]; }
export interface GraphData { as_of: number; nodes: { id: string; kind: string; label?: string | null; proposition?: string }[]; edges: ProvEdge[]; }
export interface LogEntry { id: string; ts: number; method: string; path: string; status: number; summary: string; reason_code?: string | null; }
export interface LearnResult { learned: { assertion: string; subject: string; proposition: string; state: string; evidence?: string }[]; source: string; event?: string; note?: string; }
export interface RecallResult { about: string; count: number; memories: { assertion: string; proposition: string; subjects: string[]; state: string; assertion_time: number; grounded: boolean; provenance_count: number; source: string | null }[]; note: string; }
export interface DnsResult { ok?: boolean; host?: string | null; error?: string; addresses?: string[] }
export interface ProvidersCheck {
  summary: string;
  llm: { configured: boolean; base_url?: string; model?: string; dns?: DnsResult; reachable?: boolean; error?: string; sample?: string };
  google: { configured: boolean; hosts: Record<string, DnsResult> };
  stripe: { configured: boolean };
}
export interface ClassificationSummary { messages_scanned: number; threads: number; facts_extracted: number; by_classification: Record<string, number>; }
export interface MemoryScan {
  id: string; project_id: string; triggered_by: string | null; scope: string;
  state: string; total: number; examined: number; started: number; finished: number | null;
  summary: { total?: number; examined?: number; scope?: string; by_classification?: Record<string, number>; proposed_retractions?: number; proposed_review?: number; error?: string };
  applied: number; apply_ts: number | null;
}
export interface MemoryScanResult {
  id: number; scan_id: string; assertion_id: string; classification: string; reason: string;
  source_record_id: string | null; evidence: string | null; original_evidence: string | null;
  classifier_verdict: { classification?: string; confidence?: number; reasons?: string[] } | null;
  extractor_name: string | null; confidence: number | null;
  proposed_action: string | null; applied: number; apply_error: string | null; ts: number;
}
export interface ReviewItem {
  id: string; assertion_id: string; scan_id: string; classification: string; reason: string;
  subjects: string; proposition: string; source_evidence: string | null;
  status: string; reviewer: string | null; reviewed_ts: number | null; created: number;
}
export interface MemoryHealth {
  active_memories: number; total_assertions_ever: number;
  last_scan_id: string | null; last_scan_ts: number | null;
  by_classification: Record<string, number>; pending_review: number;
  recent_corrections: { assertion_id: string; proposition: string; subjects: string[]; ts: number }[];
  needs_scan: boolean;
}
export interface OrgIdentity { company_name: string | null; emails: string[]; domains: string[]; }
export interface RelationshipOverride { key_type: "domain" | "email" | "entity"; key: string; role: string; source: string; note: string | null; ts: number; }
export interface Contact {
  email: string; name: string | null; domain: string; role: string | null;
  messages: number; threads: number; first_contact: number | null; last_contact: number | null;
  entity_id: string; facts_stored: number;
}
export interface EmailDiagnostics {
  source: { id: string; external_id: string; received: number; from: string | null; to: string | null; cc: string | null; subject: string | null; body: string; thread_id: string | null };
  identity: OrgIdentity;
  participants: { sender_email: string; sender_name: string; sender_domain: string; sender_is_self: boolean; direction: string; counterparty_email: string | null; internal: boolean; to: string[]; cc: string[] };
  sender_role_override: string | null;
  classification_stored: { classification: string; confidence: number; category: string | null; reasons: string; signals: string; entered_pipeline: number } | null;
  classification_now: { classification: string; confidence: number; reasons: string[]; signals: string[]; business_type?: string | null };
  analysis: { category: string; marketing_score: number; marketing_signals: string[]; saas_self_notification: boolean; saas_signals: string[]; is_noise_category: boolean; is_business_category: boolean };
  sentences: { text: string; speech_act: string }[];
  fact_decisions: FactDecision[];
  assertions: { assertion_id: string; evidence: string | null; confidence: number | null; extractor: string | null; open: boolean; proposition: string | null; subjects: string[] }[];
}
export interface MemoryQuality {
  emails_scanned: number; by_classification: Record<string, number>;
  by_category: Record<string, number>; candidate_facts: number;
  facts_stored: number; facts_rejected: number; by_quality: Record<string, number>;
  active_memories: number; retracted_by_scanner: number; pending_review: number;
  entities_resolved: number;
}
export interface FactDecision {
  id: number; connector_id: string | null; source_record_id: string | null;
  subject: string; proposition: string; speech_act: string | null;
  quality: string; score: number | null; reasons: string[]; category: string | null;
  stored: number; evidence: string | null; ts: number;
}
export interface GmailRescanResult {
  sources_examined: number; newly_relevant: number; newly_excluded: number; unchanged: number;
  reclassified_include: { source_record_id: string; external_id: string | null; subject: string; from: string; old_classification: string; new_classification: string; new_confidence: number | null; reasons: string[] }[];
  reclassified_exclude: { source_record_id: string; external_id: string | null; subject: string; from: string; old_classification: string; new_classification: string; new_confidence: number | null; reasons: string[] }[];
  error?: string;
}
export interface MessageClassification { external_id: string; thread_id: string | null; subject: string; sender: string; classification: string; confidence: number; business_type: string | null; reasons: string[]; signals: string[]; method: string; entered_pipeline: number; facts_extracted: number; ts: number; }
export interface AdminMetrics { organizations: number; users: number; projects: number; api_requests: number; assertions_created: number; recalls: number; learn_calls: number; connected_sources: number; source_records: number; jobs: Record<string, number>; audit_events: number; db_bytes: number; scheduler_runs: number; estimated_mrr: number; revenue_note: string; }
export interface ConnectorDetail { connector_id: string; items_ingested: number; memories_generated: number; jobs: Record<string, number>; last_sync: number | null; cursor: string | null; status: string; last_error: string | null; rate_limit_reset?: number; }
export interface BackupStatus { failing: boolean; completed_count: number; interval_seconds: number; retain: number; last_successful: { started: number; bytes: number; path: string } | null; last_run: { status: string; error: string | null } | null; }
export interface CustomerStatus { org_id: string; status: string; pilot_start: number | null; pilot_end: number | null; notes: string | null; }
export interface AdminOrgDetail { org: string; status: CustomerStatus; projects: { id: string; name: string; usage: Record<string, number>; jobs: Record<string, number>; dead_letters: { id: number; last_error: string; attempts: number }[]; source_records: number; memories: number; conflicts: number; feedback: Record<string, number>; top_recalled: { assertion_id: string; count: number }[] }[]; }
export interface AdminOrg { id: string; name: string; created: number; projects: number; members: number; usage_total: number; last_activity: number | null; plan: string; customer: CustomerStatus; }
export interface Job { id: number; connector_id: string; state: string; attempts: number; last_error: string | null; next_attempt: number | null; created: number; updated: number; }
export interface AuditEvent { id: string; actor: string | null; action: string; resource: string | null; metadata: Record<string, unknown>; ts: number; }
export interface Member { user_id: string; role: string; email: string; }
export interface Retention { project_id: string; source_days: number | null; memory_days: number | null; }
export interface Plan { name: string; price: number | null; quota_memories: number | null; quota_sources: number | null; }
export interface BillingState { plan: string; subscription_status: string; plans: Record<string, Plan>; stripe_live: boolean; }
export interface Connector { id: string; kind: string; name: string; agent_id: string; authority: number; status: string; last_run: number | null; }
export interface IngestStats { sources: number; pending: number; running: number; completed: number; retrying: number; dead: number; cancelled: number; connectors: number; }
export interface DeadLetter { id: number; external_id: string; attempts: number; last_error: string; }
export interface SourceRecord { id: string; external_id: string; payload: string; received: number; view?: SourceView; }
export interface Intelligence {
  memory_health: { total_assertions: number; grounding_coverage: number; provenance_coverage: number; unresolved_conflicts: number };
  conflicts: { subjects: string[]; proposition: string }[];
  ingestion: IngestStats;
  sources: { name: string; kind: string; authority: number; status: string; last_run: number | null }[];
}
export interface Project { id: string; name: string; env: string; now: number; entities: number; agents: number; assertions: number; events: number; is_demo?: boolean; }

export class ApiError extends Error {
  code: number; reason_code?: string | null; doc_url?: string | null;
  constructor(code: number, message: string, reason_code?: string | null, doc_url?: string | null) {
    super(message); this.code = code; this.reason_code = reason_code; this.doc_url = doc_url;
  }
}

export function getSession(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("omem-session");
}
export function setSession(token: string | null) {
  if (token) localStorage.setItem("omem-session", token);
  else localStorage.removeItem("omem-session");
}

async function req<T>(method: string, path: string, body?: unknown): Promise<T> {
  const session = getSession();
  let res: Response;
  try {
    res = await fetch(`${BASE}${path}`, {
      method,
      headers: { "Content-Type": "application/json",
        ...(session ? { Authorization: `Bearer ${session}` } : {}) },
      body: body === undefined ? undefined : JSON.stringify(body),
      cache: "no-store",
    });
  } catch {
    throw new ApiError(0, "Cannot reach the OMEM API. Is the backend running? (cd server && python3 api.py 8787)");
  }
  const text = await res.text();
  // Parse defensively: the Next.js proxy (and other intermediaries) return
  // plain-text bodies like "Internal Server Error" when the backend is down.
  // That must surface as a readable error, never as a JSON.parse crash.
  let json: { error?: { message?: string; reason_code?: string; doc_url?: string } } | null = null;
  try {
    json = text ? JSON.parse(text) : null;
  } catch {
    if (!res.ok) {
      const snippet = text.trim().slice(0, 120);
      throw new ApiError(res.status,
        `The OMEM backend is unreachable or crashed (HTTP ${res.status}${snippet ? `: ${snippet}` : ""}). ` +
        "Check that the API server is running on the configured port.");
    }
    throw new ApiError(res.status, `The API returned a non-JSON response: ${text.trim().slice(0, 120)}`);
  }
  if (!res.ok) {
    const e = json?.error;
    throw new ApiError(res.status, e?.message || res.statusText, e?.reason_code, e?.doc_url);
  }
  return json as T;
}

const enc = encodeURIComponent;

export interface ApiKey { id: string; name: string; prefix: string; role: string; created: number; last_used: number | null; revoked: number; secret?: string; }
// ── self-healing ────────────────────────────────────────────────────────────
// The server watches its own components, records failures with a fingerprint so
// repeats are one entry rather than a thousand, and runs a recovery loop:
// claimed -> diagnosing -> repairing -> verifying -> recovered, or escalated
// when it cannot fix it. Shapes mirror server/healing.py exactly.
export type HealthState = "healthy" | "degraded" | "failed" | "recovering" | "unknown";
export type RecoveryState =
  | "failed" | "claimed" | "diagnosing" | "repairing" | "verifying" | "recovered" | "escalated";

// `origin` separates OMEM's own infrastructure (computed live by the server, and
// present on a fresh install) from components an agent reported. They are read the
// same way but they are not the same claim, and the UI must not merge them into one
// undifferentiated list of green marks.
export type HealthOrigin = "omem" | "agent";
export interface HealComponent {
  component: string; status: HealthState; reason: string | null; ts: number;
  origin: HealthOrigin;
}
export interface HealHealth {
  overall: HealthState; components: HealComponent[];
  /** How many components an agent has reported. Zero is the honest default state
   *  and reads differently from "zero components exist". */
  reported_count: number;
}
export interface HealFailure {
  id: string; component: string; error_type: string; message: string;
  severity: string; fingerprint: string; occurrences: number; resolved: boolean;
  context: Record<string, unknown>; ts: number;
}
/** What the policy layer let run. `type` is the only field OMEM trusts from a
 *  proposed plan; risk comes from the server's registry, never from here. */
export interface HealAction { type: string; args?: Record<string, unknown>; }
export interface HealPlan {
  diagnosis?: string; confidence?: number;
  actions?: HealAction[]; rollback?: HealAction[];
}
/** One executed action, as recorded. `detail` is redacted server-side. */
export interface HealActionRun {
  type: string; ok: boolean; error?: string;
  detail?: Record<string, unknown> | string;
}
export interface HealCheck { check: string; status: string; reason?: string; }
export interface HealVerification { ok?: boolean; checks?: HealCheck[]; }

export interface HealRecovery {
  id: string; failure_id: string; component: string; state: RecoveryState;
  owner: string | null; outcome: string | null;
  /** 1-based ordinal of this attempt for the strategy signature. */
  attempts: number;
  /** The cap after which this strategy is refused for this failure. */
  max_attempts: number;
  /** "memory" (a prior repair that verified) or "llm" (a fresh proposal).
   *  null on rows written before this was recorded, rendered as "not recorded",
   *  never guessed. */
  plan_source: "memory" | "llm" | null;
  /** Who the caller named as approving a high-risk action. A claim by the caller,
   *  not a verified second-party approval. The UI must say which. */
  approved_by: string | null;
  plan: HealPlan; actions_run: HealActionRun[];
  verification: HealVerification; ts: number;
}

/** The policy verdict on one proposed action. `risk` is the registry's, never the
 *  plan's. A plan cannot downgrade its own risk. */
export interface HealDecision {
  index?: number; permit: boolean; reason: string;
  risk?: "low" | "medium" | "high"; requires_approval?: boolean;
}
/** A plan that was considered. Outcomes "denied" and "escalated" produce one of
 *  these and NO recovery, because nothing was ever claimed or executed. */
export interface HealDiagnosis {
  diagnosis: string | null; confidence: number | null;
  outcome: "recovered" | "failed" | "denied" | "escalated" | string;
  actions: HealAction[]; decisions: HealDecision[]; ts: number;
}

/** One machine suggestion that two entities are one person. Nothing reaches
 *  the engine until a person decides; approve records the coreference under
 *  the approver's name. */
export interface MergeProposal {
  id: string; entity_a: string; entity_b: string;
  confidence: number; evidence: string; support: string[];
  status: "open" | "approved" | "rejected" | string;
  created: number; decided: number | null; decided_by: string | null;
  coreference_id: string | null;
}
export interface ResolveReport {
  examined: number; already_merged: number; dry_run: boolean;
  merged: { pair: [string, string]; evidence: string; coreference?: string }[];
  proposed: { proposal: string; pair: [string, string]; evidence?: string; existing?: boolean }[];
  refused: { pair: [string, string]; reason: string }[];
}
export interface InferenceRule {
  id: string; when_a: string; dir_a: string; when_b: string; dir_b: string;
  then_rel: string; then_dir: string; active: boolean;
  created: number; created_by: string | null;
}
export interface InferReport {
  rules: number; skipped_existing: number; skipped_spent: number;
  derived: { assertion: string; rule: string; proposition: string; pair: [string, string] }[];
  retracted: { assertion: string; proposition: string; reason?: string }[];
}
/** A declared shape broken by live relations: "Sarah works at two companies,
 *  and works_at was declared one-employer-at-a-time". Detection only -- a
 *  person resolves by naming the counterparty that survives, or dismisses,
 *  which is permanent for exactly this counterparty set. */
export interface Tension {
  id: string; constraint_id: string; relation: string; entity: string;
  holders: Record<string, string[]>; fp: string;
  status: "open" | "resolved" | "dismissed" | "lapsed" | string;
  created: number; decided: number | null; decided_by: string | null;
  kept: string | null;
}
export interface CheckReport {
  constraints: number; unchanged: number; spent: number;
  raised: { tension: string; relation: string; entity: string; between: string[] }[];
  lapsed: { tension: string; reason: string }[];
}
/** A hunch with its case file. Never a belief: believes() is unaffected,
 *  and answering records real evidence under the answerer's name. */
export interface Hypothesis {
  id: string; subject: string; proposition: string;
  born_from: string; generator: string; because: string;
  strength: number; status: string; passes: number;
  docket: { supports: unknown[]; undermines: unknown[]; gaps: string[] };
  created: number; decided: number | null;
}

/** A regularity OMEM mined across subjects: holds P -> holds Q, with the rate it
 *  held in the population it was learned from. Counts, never a person. */
export interface Prior {
  id: string; pattern: string; antecedent: string; consequent: string; context: string;
  in_population: { support: number; refute: number; subjects: number; rate: number };
  when_applied: { supported: number; refuted: number; rate: number | null };
  fires: boolean;
}

/** One pattern in the joint intelligence bank: priors merged across every
 *  project the caller owns. Counts about subjects in general -- nothing in a
 *  row can name a person, an organisation, or a value. */
export interface BankPattern {
  antecedent: string; consequent: string; pattern: string;
  support: number; refute: number; subjects: number;
  rate: number; sources: number;
}
export interface BankAnalytics {
  contributors: number; patterns: number; stances: number; strong: number;
  categories: Record<string, number>;
  timeline: { week: string; contributions: number }[];
}
export interface BankResult {
  patterns: BankPattern[]; projects: number; markdown: string; note: string;
  analytics: BankAnalytics;
  failsafe: {
    backup_dir: string; bank_file: string; bank_file_written: boolean;
    last_backup: { last_successful: { finished: number | null } | null;
                   failing: boolean; interval_seconds: number } | null;
  };
}

export type AuthMode = "local" | "password";
export interface SignupResult { token: string; email: string; existing: boolean; org?: { id: string; name: string }; project?: { id: string; name: string; env: string }; api_key?: ApiKey; }

export const api = {
  // `auth` tells the dashboard which of the server's two modes it is talking to
  // BEFORE it has a session: "local" (no login, server bound to loopback) or
  // "password" (real accounts). Guessing wrong either locks local users out of
  // a one-minute quickstart or silently signs somebody in on an exposed server.
  health: () => req<{ status: string; cts: string; auth?: AuthMode; commons_collector?: boolean; commons_ask?: boolean }>("GET", "/v1/health"),
  /** The operator's commons decision: null until the first-open prompt (or
   *  Settings) records one. Session-only on the server. */
  commonsChoice: () => req<{ contribute: "yes" | "no" | null; env_override: boolean; url: string; collector: boolean }>("GET", "/v1/commons-choice"),
  setCommonsChoice: (contribute: boolean) => req<{ contribute: string }>("POST", "/v1/commons-choice", { contribute }),
  signup: (b: { email: string; org?: string; project?: string; password?: string; code?: string }) =>
    req<SignupResult>("POST", "/v1/signup", b),
  login: (email: string, password?: string, code?: string) =>
    req<{ token: string; email: string }>("POST", "/v1/session",
      { email, ...(password ? { password } : {}), ...(code ? { code } : {}) }),
  me: () => req<{ email: string; org: { id: string; name: string } }>("GET", "/v1/me"),
  keys: (p: string) => req<{ data: ApiKey[] }>("GET", `/v1/keys?project=${enc(p)}`),
  createKey: (p: string, name: string) => req<ApiKey>("POST", `/v1/keys?project=${enc(p)}`, { name }),
  revokeKey: (p: string, id: string) => req<{ revoked: boolean }>("POST", `/v1/keys/${enc(id)}/revoke?project=${enc(p)}`, {}),
  createProject: (b: { name: string; env?: string }) => req<{ id: string; name: string; env: string }>("POST", "/v1/projects", b),
  connectors: (p: string) => req<{ data: Connector[] }>("GET", `/v1/connectors?project=${enc(p)}`),
  createConnector: (p: string, b: { kind: string; name: string; config?: unknown; authority?: number }) =>
    req<Connector>("POST", `/v1/connectors?project=${enc(p)}`, b),
  pollConnector: (p: string, id: string) => req<{ queued: number }>("POST", `/v1/connectors/${enc(id)}/poll?project=${enc(p)}`, {}),
  processIngest: (p: string) => req<{ processed: number; failed: number; assertions: number; remaining: number }>("POST", `/v1/ingest/process?project=${enc(p)}`, {}),
  ingestStats: (p: string) => req<IngestStats>("GET", `/v1/ingest/stats?project=${enc(p)}`),
  deadLetters: (p: string) => req<{ data: DeadLetter[] }>("GET", `/v1/ingest/dead-letters?project=${enc(p)}`),
  intelligence: (p: string) => req<Intelligence>("GET", `/v1/intelligence?project=${enc(p)}`),
  /** The regularities OMEM has learned about subjects in general. (Hunches live
   *  under `expectations`, defined below.) */
  priors: (p: string) => req<{ data: Prior[] }>("GET", `/v1/memory/priors?project=${enc(p)}`),
  /** The joint intelligence bank: those regularities merged across every
   *  project the caller OWNS. Owner-only and session-only on the server. */
  bank: () => req<BankResult>("GET", "/v1/org/bank"),
  /** The commons as a training corpus: JSONL plus its dataset card. */
  commonsDataset: () => req<{ patterns: number; license: string; jsonl: string; card: string; public: boolean; note: string }>("GET", "/v1/commons-dataset"),
  beginGmail: (p: string, name?: string) => req<{ connector_id: string; auth_url: string | null; real: boolean; note?: string; required_env?: string[] }>("POST", `/v1/oauth/gmail/begin?project=${enc(p)}`, { name }),
  gmailCallback: (
    p: string,
    connector_id?: string,
    account?: string,
    oauth?: { code: string; state: string },
  ) =>
    req<{ connected: boolean; real_exchange?: boolean }>("POST", `/v1/oauth/gmail/callback?project=${enc(p)}`, {
      connector_id,
      account,
      ...(oauth ?? {}),
    }),
  connectorStatus: (p: string, id: string) => req<{ connected: boolean; account: string | null; status: string; last_run: number | null }>("GET", `/v1/connectors/${enc(id)}/status?project=${enc(p)}`),
  entityResolution: (p: string, id: string) => req<{ data: { raw_key: string; method: string; evidence: string; ts: number }[] }>("GET", `/v1/entities/${enc(id)}/resolution?project=${enc(p)}`),
  usageMetrics: (p: string) => req<{ metrics: Record<string, number>; series: Record<string, number[]> }>("GET", `/v1/usage?project=${enc(p)}`),
  auditLog: () => req<{ data: AuditEvent[] }>("GET", "/v1/audit"),
  members: (p: string) => req<{ data: Member[] }>("GET", `/v1/members?project=${enc(p)}`),
  setRole: (email: string, role: string) => req<{ ok: boolean }>("POST", "/v1/members/role", { email, role }),
  getRetention: (p: string) => req<Retention>("GET", `/v1/retention?project=${enc(p)}`),
  setRetention: (p: string, b: { source_days?: number | null; memory_days?: number | null }) => req<Retention>("POST", `/v1/retention?project=${enc(p)}`, b),
  billing: () => req<BillingState>("GET", "/v1/billing"),
  observability: () => req<Record<string, unknown>>("GET", "/v1/observability"),
  jobs: (p: string) => req<{ data: Job[] }>("GET", `/v1/jobs?project=${enc(p)}`),
  retryDeadLetters: (p: string) => req<{ requeued: number }>("POST", `/v1/jobs/retry-dead?project=${enc(p)}`, {}),
  cancelJob: (p: string, id: number) => req<{ cancelled: boolean }>("POST", `/v1/jobs/${id}/cancel?project=${enc(p)}`, {}),
  learn: (p: string, b: { agent: string; text: string; about?: string; source?: string }) => req<LearnResult>("POST", `/v1/learn?project=${enc(p)}`, b),
  recall: (p: string, about: string) => req<RecallResult>("POST", `/v1/recall?project=${enc(p)}`, { about }),
  connectorDetail: (p: string, id: string) => req<ConnectorDetail>("GET", `/v1/connectors/${enc(id)}/detail?project=${enc(p)}`),
  resyncConnector: (p: string, id: string) => req<{ resync: boolean }>("POST", `/v1/connectors/${enc(id)}/resync?project=${enc(p)}`, {}),
  bulkDeleteConnectors: (p: string, b: { kind?: string; only_inactive?: boolean }) => req<{ deleted: number }>("POST", `/v1/connectors/bulk-delete?project=${enc(p)}`, b),
  deleteConnector: (p: string, id: string) => req<{ deleted: boolean; removed: Record<string, number> }>("DELETE", `/v1/connectors/${enc(id)}?project=${enc(p)}`),
  clearConnectorErrors: (p: string, id: string) => req<{ cleared: boolean }>("POST", `/v1/connectors/${enc(id)}/clear-errors?project=${enc(p)}`, {}),
  disconnectConnector: (p: string, id: string) => req<{ disconnected: boolean }>("POST", `/v1/connectors/${enc(id)}/disconnect?project=${enc(p)}`, {}),
  connectGithub: (p: string, repo: string) => req<Connector>("POST", `/v1/connectors?project=${enc(p)}`, { kind: "github", name: repo, config: { repo }, agent_id: "connector:github", authority: 0.8 }),
  providersCheck: () => req<ProvidersCheck>("GET", "/v1/providers/check"),
  classificationSummary: (p: string) => req<ClassificationSummary>("GET", `/v1/classifications/summary?project=${enc(p)}`),
  classifications: (p: string, classification?: string) => req<{ data: MessageClassification[] }>("GET", `/v1/classifications?project=${enc(p)}${classification ? `&classification=${enc(classification)}` : ""}`),
  filteredItems: (p: string) => req<{ data: { external_id: string; subject: string; reason: string; ts: number }[] }>("GET", `/v1/filtered?project=${enc(p)}`),
  uploadDocument: (p: string, b: { filename: string; text: string; customer?: string }) => req<{ connector: string; assertions: number }>("POST", `/v1/documents?project=${enc(p)}`, b),
  adminMetrics: () => req<AdminMetrics>("GET", "/v1/admin/metrics"),
  onboardingState: (p: string) => req<{ steps: { id: string; label: string; done: boolean }[]; completed: number; total: number }>("GET", `/v1/onboarding?project=${enc(p)}`),
  submitFeedback: (p: string, b: { kind: string; assertion_id?: string; comment?: string }) => req<{ recorded: boolean }>("POST", `/v1/feedback?project=${enc(p)}`, b),
  adminOrgDetail: (id: string) => req<AdminOrgDetail>("GET", `/v1/admin/orgs/${enc(id)}`),
  setCustomerStatus: (id: string, b: { status?: string; notes?: string }) => req<CustomerStatus>("POST", `/v1/admin/orgs/${enc(id)}/status`, b),
  getSettings: (p: string) => req<{ llm_enabled: string | null; llm_model: string | null }>("GET", `/v1/settings?project=${enc(p)}`),
  setSettings: (p: string, b: { llm_enabled?: string; llm_model?: string }) => req<{ llm_enabled: string | null; llm_model: string | null }>("POST", `/v1/settings?project=${enc(p)}`, b),
  backupStatus: () => req<BackupStatus>("GET", "/v1/admin/backups"),
  runBackup: () => req<BackupStatus>("POST", "/v1/admin/backups/run", {}),
  adminOrgs: () => req<{ data: AdminOrg[] }>("GET", "/v1/admin/orgs"),
  assertionSource: (p: string, id: string) => req<SourceRecord>("GET", `/v1/assertions/${enc(id)}/source?project=${enc(p)}`),
  projects: () => req<{ data: Project[] }>("GET", "/v1/projects"),
  healing: (p: string) => req<HealHealth>("GET", `/v1/healing/health?project=${enc(p)}`),
  healingFailures: (p: string, component?: string) =>
    req<{ data: HealFailure[] }>("GET",
      `/v1/healing/failures?project=${enc(p)}${component ? `&component=${enc(component)}` : ""}`),
  healingFailure: (p: string, id: string) =>
    req<{ failure: HealFailure; recoveries: HealRecovery[]; diagnoses?: HealDiagnosis[] }>(
      "GET", `/v1/healing/failures/${enc(id)}?project=${enc(p)}`),
  overview: (p: string) => req<Overview>("GET", `/v1/overview?project=${enc(p)}`),

  assertions: (p: string, opts?: { as_of?: number | "now"; subject?: string; agent?: string; open?: boolean }) => {
    const q = new URLSearchParams({ project: p });
    if (opts?.as_of !== undefined) q.set("as_of", String(opts.as_of));
    if (opts?.subject) q.set("subject", opts.subject);
    if (opts?.agent) q.set("agent", opts.agent);
    if (opts?.open) q.set("open", "true");
    return req<{ as_of: number; data: Assertion[] }>("GET", `/v1/assertions?${q}`);
  },
  assertion: (p: string, id: string, as_of?: number | "now") =>
    req<Assertion>("GET", `/v1/assertions/${enc(id)}?project=${enc(p)}${as_of !== undefined ? `&as_of=${as_of}` : ""}`),
  why: (p: string, id: string, as_of?: number | "now") =>
    req<WhyResult>("GET", `/v1/assertions/${enc(id)}/why?project=${enc(p)}${as_of !== undefined ? `&as_of=${as_of}` : ""}`),
  provenance: (p: string, id: string) =>
    req<{ assertion: string; grounded: boolean; nodes: ProvNode[]; edges: ProvEdge[] }>("GET", `/v1/assertions/${enc(id)}/provenance?project=${enc(p)}`),
  revisionChain: (p: string, id: string) =>
    req<{ chain: Assertion[] }>("GET", `/v1/assertions/${enc(id)}/revision-chain?project=${enc(p)}`),

  entities: (p: string, opts?: { q?: string; sort?: string; limit?: number; offset?: number }) => {
    let u = `/v1/entities?project=${enc(p)}`;
    if (opts?.q) u += `&q=${enc(opts.q)}`;
    if (opts?.sort) u += `&sort=${enc(opts.sort)}`;
    if (opts?.limit != null) u += `&limit=${opts.limit}`;
    if (opts?.offset != null) u += `&offset=${opts.offset}`;
    return req<EntityPage>("GET", u);
  },
  /** The bounded neighbourhood around one entity: it plus its related entities,
   *  with relation-labelled edges. This is how the graph scales -- you never
   *  fetch a million-node graph, only one entity's surroundings. */
  entityGraph: (p: string, entity: string, depth = 1) =>
    req<NeighborGraph>("GET", `/v1/memory/graph?project=${enc(p)}&entity=${enc(entity)}&depth=${depth}`),
  entity: (p: string, id: string) => req<Entity>("GET", `/v1/entities/${enc(id)}?project=${enc(p)}`),
  beliefsAbout: (p: string, id: string, as_of?: number | "now") =>
    req<{ as_of: number; data: Assertion[] }>("GET", `/v1/entities/${enc(id)}/beliefs?project=${enc(p)}${as_of !== undefined ? `&as_of=${as_of}` : ""}`),

  agents: (p: string) => req<{ data: Agent[] }>("GET", `/v1/agents?project=${enc(p)}`),
  agent: (p: string, id: string, as_of?: number | "now") =>
    req<Agent>("GET", `/v1/agents/${enc(id)}?project=${enc(p)}${as_of !== undefined ? `&as_of=${as_of}` : ""}`),

  events: (p: string) => req<{ data: EventPrim[] }>("GET", `/v1/events?project=${enc(p)}`),
  timeline: (p: string, as_of?: number | "now") =>
    req<{ as_of: number; events: EventPrim[] }>("GET", `/v1/timeline?project=${enc(p)}${as_of !== undefined ? `&as_of=${as_of}` : ""}`),
  conflicts: (p: string, as_of?: number | "now") =>
    req<{ as_of: number; conflicts: ConflictPair[] }>("GET", `/v1/conflicts?project=${enc(p)}${as_of !== undefined ? `&as_of=${as_of}` : ""}`),
  graph: (p: string, as_of?: number | "now") =>
    req<GraphData>("GET", `/v1/graph?project=${enc(p)}${as_of !== undefined ? `&as_of=${as_of}` : ""}`),
  partition: (p: string, as_of?: number | "now") =>
    req<{ as_of: number; partition: string[][] }>("GET", `/v1/coreference/partition?project=${enc(p)}${as_of !== undefined ? `&as_of=${as_of}` : ""}`),
  logs: (p: string) => req<{ data: LogEntry[] }>("GET", `/v1/logs?project=${enc(p)}`),

  // writes (playground / onboarding)
  createEntity: (p: string, b: { id?: string; type: string; label?: string }) => req<Entity>("POST", `/v1/entities?project=${enc(p)}`, b),
  createAgent: (p: string, b: { id?: string; kind?: string; label?: string }) => req<Agent>("POST", `/v1/agents?project=${enc(p)}`, b),
  createEvent: (p: string, b: { id?: string; kind: string; event_time?: number | "now"; label?: string }) => req<EventPrim>("POST", `/v1/events?project=${enc(p)}`, b),
  remember: (p: string, b: { agent: string; subjects: string[]; proposition: string; assertion_time?: number | "now"; because?: string[]; confidence?: number; label?: string }) =>
    req<Assertion>("POST", `/v1/assertions?project=${enc(p)}`, b),
  propositionState: (p: string, b: { subjects: string[]; proposition: string; as_of?: number | "now" }) =>
    req<{ state: PropositionState; as_of: number }>("POST", `/v1/queries/proposition-state?project=${enc(p)}`, b),
  supersede: (p: string, id: string, b: { new: { agent: string; subjects: string[]; proposition: string; assertion_time?: number | "now"; label?: string } }) =>
    req<Assertion>("POST", `/v1/assertions/${enc(id)}/supersede?project=${enc(p)}`, b),
  retract: (p: string, id: string, b: { agent: string; assertion_time?: number | "now" }) =>
    req<{ id: string; retracted: string }>("POST", `/v1/assertions/${enc(id)}/retract?project=${enc(p)}`, b),
  declareContradiction: (p: string, b: { token_a: string; token_b: string }) =>
    req<{ declared: string[] }>("POST", `/v1/declare-contradiction?project=${enc(p)}`, b),

  // memory scanner
  memoryHealth: (p: string) => req<MemoryHealth>("GET", `/v1/memory/health?project=${enc(p)}`),
  memoryScans: (p: string) => req<{ data: MemoryScan[] }>("GET", `/v1/memory/scans?project=${enc(p)}`),
  memoryScan: (p: string, id: string, classification?: string) =>
    req<{ scan: MemoryScan; results: MemoryScanResult[]; count: number }>(
      "GET", `/v1/memory/scans/${enc(id)}?project=${enc(p)}${classification ? `&classification=${enc(classification)}` : ""}`),
  startMemoryScan: (p: string, scope: "all" | "recent" = "all") =>
    req<MemoryScan>("POST", `/v1/memory/scan?project=${enc(p)}`, { scope }),
  applyMemoryScan: (p: string, id: string) =>
    req<{ retracted: number; review_added: number; skipped: number; errors: number; scan_id: string }>(
      "POST", `/v1/memory/scans/${enc(id)}/apply?project=${enc(p)}`, {}),
  reviewQueue: (p: string, status = "pending") =>
    req<{ data: ReviewItem[] }>("GET", `/v1/memory/review-queue?project=${enc(p)}&status=${enc(status)}`),
  reviewDecide: (p: string, id: string, decision: "approve" | "reject") =>
    req<{ id: string; decision: string; assertion_id: string }>(
      "POST", `/v1/memory/review-queue/${enc(id)}/decide?project=${enc(p)}`, { decision }),

  // identity resolution + declared inference rules
  runResolve: (p: string, apply = true) =>
    req<ResolveReport>("POST", `/v1/memory/resolve?project=${enc(p)}`, { apply }),
  mergeProposals: (p: string, status?: string) =>
    req<{ data: MergeProposal[]; count: number }>(
      "GET", `/v1/memory/merge-proposals?project=${enc(p)}${status ? `&status=${enc(status)}` : ""}`),
  mergeDecide: (p: string, id: string, decision: "approve" | "reject") =>
    req<{ proposal: string; status: string; coreference?: string; note?: string }>(
      "POST", `/v1/memory/merge-proposals/${enc(id)}/${decision}?project=${enc(p)}`, {}),
  inferenceRules: (p: string) =>
    req<{ data: InferenceRule[]; count: number }>("GET", `/v1/rules?project=${enc(p)}`),
  runInfer: (p: string) =>
    req<InferReport>("POST", `/v1/memory/infer?project=${enc(p)}`, {}),
  runCheck: (p: string) =>
    req<CheckReport>("POST", `/v1/memory/check?project=${enc(p)}`, {}),
  tensions: (p: string, status?: string) =>
    req<{ data: Tension[]; count: number }>(
      "GET", `/v1/memory/tensions?project=${enc(p)}${status ? `&status=${enc(status)}` : ""}`),
  tensionResolve: (p: string, id: string, keep: string) =>
    req<{ tension: string; status: string; kept: string; retracted: string[] }>(
      "POST", `/v1/memory/tensions/${enc(id)}/resolve?project=${enc(p)}`, { keep }),
  tensionDismiss: (p: string, id: string) =>
    req<{ tension: string; status: string }>(
      "POST", `/v1/memory/tensions/${enc(id)}/dismiss?project=${enc(p)}`, {}),
  expectations: (p: string, status?: string) =>
    req<{ data: Hypothesis[]; count: number }>(
      "GET", `/v1/memory/expectations?project=${enc(p)}${status ? `&status=${enc(status)}` : ""}`),
  answerExpectation: (p: string, id: string, answer: "yes" | "no") =>
    req<{ hypothesis: string; answered: string; recorded: string; verdict: string }>(
      "POST", `/v1/memory/expectations/${enc(id)}/answer?project=${enc(p)}`, { answer }),
  gmailRescan: (p: string, opts?: { connector_id?: string; window_days?: 7 | 30 | 90 | 365 }) =>
    req<GmailRescanResult>("POST", `/v1/memory/gmail-rescan?project=${enc(p)}`, opts ?? {}),
  memoryQuality: (p: string) => req<MemoryQuality>("GET", `/v1/memory/quality?project=${enc(p)}`),
  factDecisions: (p: string, opts?: { source?: string; stored?: 0 | 1 }) =>
    req<{ data: FactDecision[] }>("GET",
      `/v1/fact-decisions?project=${enc(p)}${opts?.source ? `&source=${enc(opts.source)}` : ""}${opts?.stored !== undefined ? `&stored=${opts.stored}` : ""}`),
  identity: (p: string) => req<OrgIdentity>("GET", `/v1/identity?project=${enc(p)}`),
  setIdentity: (p: string, b: OrgIdentity) => req<OrgIdentity>("POST", `/v1/identity?project=${enc(p)}`, b),
  relationships: (p: string) => req<{ data: RelationshipOverride[]; roles: string[] }>("GET", `/v1/relationships?project=${enc(p)}`),
  setRelationship: (p: string, b: { key_type: string; key: string; role: string | null; note?: string }) =>
    req<{ key_type: string; key: string; role?: string; removed?: boolean }>("POST", `/v1/relationships?project=${enc(p)}`, b),
  contacts: (p: string) => req<{ data: Contact[] }>("GET", `/v1/contacts?project=${enc(p)}`),
  emailDiagnostics: (p: string, source: string) =>
    req<EmailDiagnostics>("GET", `/v1/diagnostics/email?project=${enc(p)}&source=${enc(source)}`),
};

export const isGrounded = (g: string | boolean) => g === true || g === "GROUNDED";
