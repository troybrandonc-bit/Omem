/* A port of scripts/testimony_validate.py, so a record can be checked in a
 * browser without installing anything.
 *
 * WHY A SECOND IMPLEMENTATION. The Python validator is the reference and this
 * has to agree with it: two validators that disagree are worse than one, since
 * a conformance claim then depends on which you ran. server/tests_testimony_js.py
 * runs both over the same records and fails if any verdict differs, which is
 * the only thing that makes shipping this defensible.
 *
 * It also means the specification has two independent implementations of its
 * own checker, which is a small thing to be able to say when the register page
 * spends a paragraph on one implementation not being a standard.
 *
 * Check names are identical to the Python, deliberately. They are what the two
 * are compared on.
 *
 * Copyright 2026 Michael Brandon Clifford. MIT licensed. */

export const SPEC = "testimony-record/0.2";
export const SPECS = ["testimony-record/0.1", "testimony-record/0.2"];
export const LEVELS = ["TR-1", "TR-2", "TR-3", "TR-4"] as const;
export type Level = (typeof LEVELS)[number];

const TYPES = new Set([
  "belief", "evidence", "conflict", "decision", "approval", "integrity", "scope",
]);

const RFC3339 =
  /^\d{4}-\d{2}-\d{2}[Tt]\d{2}:\d{2}:\d{2}(\.\d+)?([Zz]|[+-]\d{2}:\d{2})$/;

/* Identity the proposing model could have written is not identity. */
const UNTRUSTED_SOURCES = new Set([
  "model", "plan", "request", "request-body", "prompt", "agent",
]);

const REQUIRED: Record<string, string[]> = {
  scope: ["acts"],
  belief: ["subject", "proposition", "polarity", "state", "asserted_by"],
  evidence: ["kind", "source"],
  conflict: ["subject", "proposition", "sides"],
  decision: ["action_type", "risk_class", "proposed_by", "verdict", "executed"],
  approval: ["decision", "approver"],
  integrity: ["scheme", "digest"],
};

const ENUMS: [string, string, string[]][] = [
  ["belief", "polarity", ["affirm", "deny"]],
  ["belief", "state", ["believed_true", "believed_false", "contradicted", "unknown"]],
  ["evidence", "kind", ["document", "message", "event", "api", "human", "derived"]],
  ["decision", "risk_class", ["low", "medium", "high"]],
  ["decision", "verdict", ["permitted", "refused"]],
  ["integrity", "scheme", ["replay", "hash-chain", "signature", "external-anchor"]],
];

export type Entry = Record<string, unknown> & { _line?: number };
export type Check = { level: Level; check: string; ok: boolean; detail: string };

export type Report = {
  spec: string;
  scope: "acts" | "record only";
  level: Level | null;
  levelsMet: Record<Level, boolean>;
  checks: Check[];
  entries: Entry[];
  parseErrors: string[];
};

function parse(text: string): { entries: Entry[]; errors: string[] } {
  const entries: Entry[] = [];
  const errors: string[] = [];
  text.split(/\r?\n/).forEach((raw, i) => {
    const line = raw.trim();
    if (!line || line.startsWith("#")) return;
    let obj: unknown;
    try {
      obj = JSON.parse(line);
    } catch {
      errors.push(`line ${i + 1}: not valid JSON`);
      return;
    }
    if (obj === null || typeof obj !== "object" || Array.isArray(obj)) {
      errors.push(`line ${i + 1}: not a JSON object`);
      return;
    }
    entries.push({ ...(obj as Record<string, unknown>), _line: i + 1 });
  });
  return { entries, errors };
}

const str = (v: unknown) => (typeof v === "string" ? v : "");
const arr = (v: unknown) => (Array.isArray(v) ? v : []);
const obj = (v: unknown) =>
  v && typeof v === "object" && !Array.isArray(v)
    ? (v as Record<string, unknown>)
    : {};

export function validate(text: string): Report {
  const checks: Check[] = [];
  const add = (level: Level, check: string, ok: boolean, detail = "") =>
    checks.push({ level, check, ok, detail });

  const { entries, errors } = parse(text);
  let spec = SPEC;
  let scope: "acts" | "record only" = "acts";

  /* TR-1: the record exists, is well formed, and is append-only */
  add("TR-1", "every line parses as a JSON object", errors.length === 0,
    errors.slice(0, 3).join("; "));
  add("TR-1", "the record is not empty", entries.length > 0);

  const named = new Set(entries.map((e) => str(e.spec)));
  const badSpec = entries.filter((e) => !SPECS.includes(str(e.spec)));
  add("TR-1", "every entry names a known specification version",
    entries.length > 0 && badSpec.length === 0,
    `${badSpec.length} entr(ies) with an unknown or missing spec field`);
  add("TR-1", "the record names one specification version, not several",
    named.size <= 1,
    `mixed versions in one record: ${[...named].filter(Boolean).sort().join(", ")}`);
  const known = [...named].filter((n) => SPECS.includes(n));
  if (known.length === 1) spec = known[0];

  const badType = entries.filter((e) => !TYPES.has(str(e.type)));
  add("TR-1", "every entry has a known type", badType.length === 0,
    `${badType.length} unknown type(s)`);

  const missing: string[] = [];
  for (const e of entries)
    for (const f of REQUIRED[str(e.type)] ?? [])
      if (!(f in e)) missing.push(`line ${e._line}: ${str(e.type)} missing '${f}'`);
  add("TR-1", "required fields are present for each type", missing.length === 0,
    missing.slice(0, 3).join("; "));

  const badEnum: string[] = [];
  for (const e of entries)
    for (const [t, f, allowed] of ENUMS)
      if (str(e.type) === t && f in e && !allowed.includes(str(e[f])))
        badEnum.push(`line ${e._line}: ${f}=${JSON.stringify(e[f])}`);
  add("TR-1", "enumerated fields use allowed values", badEnum.length === 0,
    badEnum.slice(0, 3).join("; "));

  const ids = entries.filter((e) => "id" in e).map((e) => str(e.id));
  const dupes = [...new Set(ids.filter((i, n) => ids.indexOf(i) !== n))].sort();
  add("TR-1", "entry ids are unique and never reused", dupes.length === 0,
    `reused: ${dupes.slice(0, 3).join(", ")}`);

  const badTime = entries.filter((e) => !RFC3339.test(str(e.at)));
  add("TR-1", "every entry has an RFC 3339 write time", badTime.length === 0,
    `${badTime.length} entr(ies) with a missing or malformed 'at'`);

  const times = entries.map((e) => str(e.at)).filter(Boolean);
  const ordered = times.every((t, i) => i === 0 || times[i - 1] <= t);
  add("TR-1", "entries are in non-decreasing time order (append-only)", ordered,
    "an entry is written before the one above it, which an append-only " +
    "record cannot do");

  const of = (t: string) => entries.filter((e) => str(e.type) === t);
  const byId = new Map(entries.filter((e) => "id" in e).map((e) => [str(e.id), e]));

  /* scope: what the emitting system says it does. Absent, it acts, which is
   * what every 0.1 record means. */
  const scopes = of("scope");
  add("TR-1", "at most one scope entry", scopes.length <= 1,
    `${scopes.length} scope entries; a record describes one system`);
  const declared = scopes[0];
  if (declared && str(declared.spec) === "testimony-record/0.1")
    add("TR-1", "scope is not used in a 0.1 record", false,
      "the scope entry was introduced in testimony-record/0.2; a 0.1 record " +
      "carrying one is claiming a version it does not name");
  const acts = declared ? Boolean(declared.acts) : true;
  scope = acts ? "acts" : "record only";

  const decisions = of("decision");
  const approvals = of("approval");
  add("TR-1", "a record that declares no actions contains none",
    acts || decisions.length === 0,
    `scope says acts=false but the record carries ${decisions.length} ` +
    "decision entr(ies)");

  /* TR-2: beliefs resolve to evidence, disagreements survive */
  const beliefs = of("belief");
  const noField = beliefs.filter((b) => !("evidence" in b));
  add("TR-2", "every belief states its evidence, even when there is none",
    noField.length === 0,
    `${noField.length} belief(s) omit the field; an ungrounded belief must ` +
    "say so explicitly with an empty list");

  const dangling: string[] = [];
  for (const b of beliefs)
    for (const ev of arr(b.evidence))
      if (str(byId.get(str(ev))?.type) !== "evidence")
        dangling.push(`line ${b._line}: cites ${JSON.stringify(ev)}`);
  add("TR-2", "cited evidence exists in the record", dangling.length === 0,
    dangling.slice(0, 3).join("; "));

  const conflicts = of("conflict");
  const thin = conflicts.filter((c) => arr(c.sides).length < 2);
  add("TR-2", "each conflict names at least two sides", thin.length === 0,
    `${thin.length} conflict(s) with fewer than two sides`);

  const lost: string[] = [];
  for (const c of conflicts)
    for (const s of arr(c.sides))
      if (str(byId.get(str(s))?.type) !== "belief")
        lost.push(`line ${c._line}: side ${JSON.stringify(s)} is not a belief in this record`);
  add("TR-2", "both sides of every conflict are retained", lost.length === 0,
    lost.slice(0, 3).join("; "));

  const key = (s: unknown, p: unknown) => `${str(s)} ${str(p)}`;
  const declaredConf = new Set(
    conflicts.filter((c) => "subject" in c && "proposition" in c)
      .map((c) => key(c.subject, c.proposition)));
  const undeclared = [...new Set(
    beliefs.filter((b) => str(b.state) === "contradicted")
      .map((b) => key(b.subject, b.proposition)))]
    .filter((k) => !declaredConf.has(k));
  add("TR-2", "a contradicted belief has a conflict entry naming it",
    undeclared.length === 0,
    `undeclared: ${undeclared.slice(0, 3).map((k) => k.split(" ").join(" / ")).join("; ")}`);

  const badRes: string[] = [];
  for (const c of conflicts) {
    const res = c.resolution;
    if (res === null || res === undefined) continue;
    const r = obj(res);
    if (Object.keys(r).length === 0) continue;
    for (const f of ["method", "by", "at", "kept"])
      if (!(f in r)) badRes.push(`line ${c._line}: resolution missing '${f}'`);
    if ("kept" in r && !arr(c.sides).map(str).includes(str(r.kept)))
      badRes.push(`line ${c._line}: kept side is not one of the sides`);
  }
  add("TR-2", "a resolved conflict records who resolved it and what was kept",
    badRes.length === 0, badRes.slice(0, 3).join("; "));

  /* TR-3: actions carry a verdict, approvals carry a name */
  if (acts)
    add("TR-3", "the record contains at least one decision", decisions.length > 0,
      "a record from a system that acts, with no decisions in it, cannot " +
      "demonstrate a gate. If this system does not act, say so with a scope " +
      "entry rather than leaving it to be inferred.");
  else
    add("TR-3", "no decisions required: the system declares it does not act", true);

  const selfDeclared = decisions.filter(
    (d) => !("risk_source" in d) ||
      UNTRUSTED_SOURCES.has(str(d.risk_source).toLowerCase()));
  add("TR-3", "risk class comes from outside the proposing model",
    selfDeclared.length === 0,
    `${selfDeclared.length} decision(s) declare their own risk class or do ` +
    "not say where it came from");

  const ranAnyway = decisions.filter(
    (d) => str(d.verdict) === "refused" && d.executed === true);
  add("TR-3", "a refused action did not execute", ranAnyway.length === 0,
    `${ranAnyway.length} refused decision(s) recorded as executed`);

  const noReason = decisions.filter(
    (d) => str(d.verdict) === "refused" && !d.reason);
  add("TR-3", "every refusal records its reason", noReason.length === 0,
    `${noReason.length} refusal(s) without a reason`);

  const unapproved: string[] = [];
  for (const d of decisions) {
    if (str(d.risk_class) !== "high" || d.executed !== true) continue;
    const a = byId.get(str(d.approval)) ?? {};
    if (str(a.type) !== "approval" || str(a.decision) !== str(d.id))
      unapproved.push(`line ${d._line}: ${str(d.action_type)}`);
  }
  add("TR-3", "an executed high-risk action has an approval entry",
    unapproved.length === 0, unapproved.slice(0, 3).join("; "));

  const badApprover: string[] = [];
  for (const a of approvals) {
    const who = obj(a.approver);
    if (str(who.kind) !== "human")
      badApprover.push(`line ${a._line}: approver kind ${JSON.stringify(who.kind)}`);
    const src = str(a.identity_source).toLowerCase();
    if (!src || UNTRUSTED_SOURCES.has(src))
      badApprover.push(`line ${a._line}: identity_source ${JSON.stringify(a.identity_source)}`);
    const approved = byId.get(str(a.decision)) ?? {};
    if (str(approved.type) !== "decision")
      badApprover.push(`line ${a._line}: approves a decision not in the record`);
    else {
      /* An approver who is also the proposer is worth nothing, however the
       * name in the entry is spelled. */
      const proposer = str(obj(approved.proposed_by).id);
      if (proposer && proposer === str(who.id))
        badApprover.push(`line ${a._line}: approver is the proposer ${JSON.stringify(proposer)}`);
    }
  }
  add("TR-3", "approvals name a person, sourced from authentication",
    badApprover.length === 0, badApprover.slice(0, 3).join("; "));

  /* TR-4: the record can be shown not to have changed */
  const integrity = of("integrity");
  add("TR-4", "the record publishes an integrity scheme", integrity.length > 0,
    "no integrity entry, so nothing states how alteration would be detected");

  const weak = integrity.filter((g) => !g.digest);
  add("TR-4", "every integrity entry carries a digest", weak.length === 0,
    `${weak.length} integrity entr(ies) without one`);

  const unnamed = integrity.filter(
    (g) => str(g.scheme) === "replay" && !(g.engine && g.engine_version));
  add("TR-4", "a replay scheme names the engine and its version",
    unnamed.length === 0,
    `${unnamed.length} replay entr(ies) that cannot be reproduced by a third party`);

  /* An external anchor is the one scheme whose evidence somebody else holds,
     which is the whole reason it is worth more than a digest the producer
     computed. Saying "external-anchor" without naming who anchored it, or
     without the token they returned, is the claim without the thing. */
  const hollow: string[] = [];
  for (const g of integrity) {
    if (str(g.scheme) !== "external-anchor") continue;
    const a = g.anchor as Record<string, unknown> | undefined;
    if (!a || typeof a !== "object" || Array.isArray(a)) {
      hollow.push(`line ${g._line}: no anchor object`);
      continue;
    }
    for (const f of ["kind", "authority", "token"])
      if (!a[f]) hollow.push(`line ${g._line}: anchor missing ${JSON.stringify(f)}`);
  }
  add("TR-4", "an external anchor names its authority and carries its token",
    hollow.length === 0, hollow.slice(0, 3).join("; "));

  const stale: string[] = [];
  for (const g of integrity)
    for (const cid of arr(g.covers))
      if (!byId.has(str(cid)))
        stale.push(`line ${g._line}: covers ${JSON.stringify(cid)}, not in the record`);
  add("TR-4", "integrity entries cover entries that exist", stale.length === 0,
    stale.slice(0, 3).join("; "));

  /* The level reached is the highest with nothing failing below it. */
  const failed = (lvl: Level) => checks.some((c) => c.level === lvl && !c.ok);
  const levelsMet = Object.fromEntries(
    LEVELS.map((l) => [l, !failed(l)])) as Record<Level, boolean>;
  let level: Level | null = null;
  for (const lvl of LEVELS) {
    if (failed(lvl)) break;
    level = lvl;
  }

  return { spec, scope, level, levelsMet, checks, entries, parseErrors: errors };
}
