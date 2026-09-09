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
 * Copyright 2026 Garnet Taurus Ltd. MIT licensed. */

export const SPEC = "testimony-record/0.2";
export const SPECS = ["testimony-record/0.1", "testimony-record/0.2"];
export const LEVELS = ["TR-1", "TR-2", "TR-3", "TR-4"] as const;
export type Level = (typeof LEVELS)[number];

const TYPES = new Set([
  "belief", "evidence", "conflict", "decision", "approval", "integrity", "scope",
]);

const RFC3339 =
  /^\d{4}-\d{2}-\d{2}[Tt]\d{2}:\d{2}:\d{2}(\.\d+)?([Zz]|[+-]\d{2}:\d{2})$/;

/* Identity the proposing model could have written is not identity.
 *
 * These were a denylist, which meant any word not on it passed:
 * identity_source "the-model-said-so" reached TR-4. An unlisted source is now
 * declared as an extension with an "x-" prefix so that it is visible as one.
 * None of this makes the claim provable, which is why both checks report as
 * attested however the field is spelled. */
const UNTRUSTED_SOURCES = new Set([
  "model", "plan", "request", "request-body", "prompt", "agent",
]);

const RISK_SOURCES = new Set([
  "registry", "policy", "catalogue", "catalog", "configuration", "config",
  "regulation", "operator", "human",
]);

const IDENTITY_SOURCES = new Set([
  "auth-session", "session", "api-key", "jwt", "oidc", "oauth", "saml", "mtls",
  "webauthn", "passkey", "signed-token", "directory", "sso", "ldap",
  "kerberos",
]);

function sourceProblem(value: unknown, allowed: Set<string>): string {
  const v = str(value).trim().toLowerCase();
  if (!v) return "not stated";
  if (UNTRUSTED_SOURCES.has(v))
    return `${JSON.stringify(v)} is the proposing side of the same system`;
  if (v.startsWith("x-")) return v.length > 2 ? "" : "'x-' names no extension";
  if (!allowed.has(v))
    return `${JSON.stringify(v)} is not a known source; an unlisted one is ` +
      `written as 'x-${v}'`;
  return "";
}

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
  // `executed` answers whether the system observed the action run. It
  // cannot answer what happened when the action was dispatched and the
  // acknowledgement was lost, because a boolean has no room for "cannot
  // say", and a reader who takes `executed: false` to mean the effect did
  // not happen will retry an action that already ran. Optional, so every
  // 0.2 record stays valid.
  ["decision", "outcome", ["confirmed", "not_attempted", "unconfirmed"]],
  ["integrity", "scheme", ["replay", "hash-chain", "signature", "external-anchor"]],
];

export type Entry = Record<string, unknown> & { _line?: number };
export type Basis = "verified" | "attested";

export type Check = {
  level: Level; check: string; ok: boolean; detail: string; basis: Basis;
};

/* Checks the record asserts and that no reader can confirm from the record
 * alone. Named rather than passed at each call site, so that this file and the
 * Python cannot come to disagree about which kind a check is; the cross
 * validator test compares the basis of every check between them. */
/* Three members are declared to be an Actor: a belief's `asserted_by`, a
 * decision's `proposed_by`, and an approval's `approver`. The Conventions
 * section defines one as an object carrying at least `id` and `kind`, and
 * until 8 September 2026 neither validator checked that: presence was required
 * and shape was not, so `asserted_by: "review.v4"` passed TR-1 and TR-2.
 *
 * Found by babyblueviper1, who built a validator from the draft's prose alone
 * and disagreed with the corpus on exactly one of fifty-four cases. They were
 * right, and a port of the Python could never have found it, because a port
 * inherits the reading rather than the text. */
const ACTOR_FIELDS: Record<string, string> = {
  // machine-testimony#86: `scope` carries `declared_by`, defined as an Actor,
  // and this map had three keys so the shape check never reached it.
  belief: "asserted_by", decision: "proposed_by", approval: "approver",
  scope: "declared_by",
};
const ACTOR_KINDS = new Set(["agent", "human", "system", "connector"]);

const ATTESTED = new Set([
  "no decisions required: the system declares it does not act",
  "the risk class is declared to come from outside the proposing model",
  "the approver's name is declared to come from authentication",
  "a replay scheme names the engine and its version",
  "an anchor of a kind this validator cannot recompute rests on its authority",
  "and the authority named in it issued that token",
]);

export type Report = {
  spec: string;
  scope: "acts" | "record only";
  level: Level | null;
  levelsMet: Record<Level, boolean>;
  basis: Record<Level, { verified: number; attested: number }>;
  checks: Check[];
  entries: Entry[];
  parseErrors: string[];
};

/* SHA-256 by hand, because the digest has to be recomputed here and
 * crypto.subtle is asynchronous. Making validate() async would push an await
 * into every caller, including a page that has no other reason to have one. */
const K256 = new Uint32Array([
  0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1,
  0x923f82a4, 0xab1c5ed5, 0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3,
  0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174, 0xe49b69c1, 0xefbe4786,
  0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
  0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147,
  0x06ca6351, 0x14292967, 0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13,
  0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85, 0xa2bfe8a1, 0xa81a664b,
  0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
  0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a,
  0x5b9cca4f, 0x682e6ff3, 0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208,
  0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2,
]);

const rotr = (x: number, n: number) => ((x >>> n) | (x << (32 - n))) >>> 0;

export function sha256Hex(msg: Uint8Array): string {
  const H = new Uint32Array([
    0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a,
    0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19,
  ]);
  const padded = new Uint8Array(((msg.length + 9 + 63) >> 6) << 6);
  padded.set(msg);
  padded[msg.length] = 0x80;
  const dv = new DataView(padded.buffer);
  const bits = msg.length * 8;
  dv.setUint32(padded.length - 8, Math.floor(bits / 4294967296));
  dv.setUint32(padded.length - 4, bits >>> 0);

  const w = new Uint32Array(64);
  for (let off = 0; off < padded.length; off += 64) {
    for (let i = 0; i < 16; i++) w[i] = dv.getUint32(off + i * 4);
    for (let i = 16; i < 64; i++) {
      const a15 = w[i - 15], a2 = w[i - 2];
      const s0 = (rotr(a15, 7) ^ rotr(a15, 18) ^ (a15 >>> 3)) >>> 0;
      const s1 = (rotr(a2, 17) ^ rotr(a2, 19) ^ (a2 >>> 10)) >>> 0;
      w[i] = (w[i - 16] + s0 + w[i - 7] + s1) >>> 0;
    }
    let a = H[0], b = H[1], c = H[2], d = H[3];
    let e = H[4], f = H[5], g = H[6], h = H[7];
    for (let i = 0; i < 64; i++) {
      const S1 = (rotr(e, 6) ^ rotr(e, 11) ^ rotr(e, 25)) >>> 0;
      const ch = ((e & f) ^ (~e & g)) >>> 0;
      const t1 = (h + S1 + ch + K256[i] + w[i]) >>> 0;
      const S0 = (rotr(a, 2) ^ rotr(a, 13) ^ rotr(a, 22)) >>> 0;
      const maj = ((a & b) ^ (a & c) ^ (b & c)) >>> 0;
      const t2 = (S0 + maj) >>> 0;
      h = g; g = f; f = e; e = (d + t1) >>> 0;
      d = c; c = b; b = a; a = (t1 + t2) >>> 0;
    }
    H[0] = (H[0] + a) >>> 0; H[1] = (H[1] + b) >>> 0;
    H[2] = (H[2] + c) >>> 0; H[3] = (H[3] + d) >>> 0;
    H[4] = (H[4] + e) >>> 0; H[5] = (H[5] + f) >>> 0;
    H[6] = (H[6] + g) >>> 0; H[7] = (H[7] + h) >>> 0;
  }
  return Array.from(H, (x) => x.toString(16).padStart(8, "0")).join("");
}

/* The canonical form a digest is taken over. Members ordered by name, no
 * insignificant whitespace, members beginning with "_" dropped as reader
 * annotations, entries joined by one line feed with none at the end.
 *
 * Numbers are the one place two languages write the same value differently:
 * Python writes 1.0 where this writes 1, and 1e-05 where this writes 0.00001.
 * Outside the range where they agree the value is refused rather than hashed
 * into a digest the other cannot reproduce. */
const NUM_MIN = 1e-4, NUM_MAX = 1e21, SAFE_INT = 9007199254740992;

export class Unportable extends Error {}

function canonicalValue(v: unknown): string {
  if (v === null) return "null";
  if (typeof v === "boolean") return v ? "true" : "false";
  if (typeof v === "number") {
    if (!Number.isFinite(v)) throw new Unportable(`a digest cannot cover ${v}`);
    if (Number.isInteger(v)) {
      if (Math.abs(v) > SAFE_INT)
        throw new Unportable(`${v} does not survive a round trip through ` +
          "ECMAScript, so no digest over it is portable");
      if (Math.abs(v) < NUM_MAX) return JSON.stringify(v);
    }
    if (!(Math.abs(v) >= NUM_MIN && Math.abs(v) < NUM_MAX))
      throw new Unportable(`${v} is outside the range where Python and ` +
        "ECMAScript write a number the same way");
    return JSON.stringify(v);
  }
  if (typeof v === "string") return JSON.stringify(v);
  if (Array.isArray(v)) return "[" + v.map(canonicalValue).join(",") + "]";
  const o = v as Record<string, unknown>;
  return "{" + Object.keys(o).filter((k) => !k.startsWith("_")).sort()
    .map((k) => JSON.stringify(k) + ":" + canonicalValue(o[k])).join(",") + "}";
}

export function digestOf(entries: Entry[]): string {
  const text = entries.map((e) => canonicalValue(e)).join("\n");
  return sha256Hex(new TextEncoder().encode(text));
}

/* Enough base64 and DER to read the message imprint out of an RFC 3161 token.
 * Refusing to look at all was how a token signed over somebody else's record
 * used to pass this level. */
const B64 = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";

export function b64(text: string): Uint8Array | null {
  const clean = text.replace(/[\s=]/g, "");
  const out = new Uint8Array((clean.length * 3) >> 2);
  let acc = 0, bits = 0, n = 0;
  for (const ch of clean) {
    const v = B64.indexOf(ch);
    if (v < 0) return null;
    acc = (acc << 6) | v;
    bits += 6;
    if (bits >= 8) { bits -= 8; out[n++] = (acc >> bits) & 0xff; }
  }
  return out.subarray(0, n);
}

const SHA256_OID = [0x06, 0x09, 0x60, 0x86, 0x48, 0x01, 0x65, 0x03, 0x04,
  0x02, 0x01];

/* The anchor kinds this validator can recompute for itself. `kind` has always
 * been required on an anchor and until 7 September 2026 nothing read it: every
 * token was parsed as an RFC 3161 TimeStampResp whatever the record said it
 * was. So an anchor committed to Bitcoin proof-of-work through OpenTimestamps
 * failed the anchor check ("the anchor's authority signed this record's
 * digest", as it was then called) and could not
 * reach TR-4, marked down for carrying evidence no operator and no key can
 * move rather than a token from a single authority. That is the error the
 * rubric's applies_to exists to prevent, committed inside the validator.
 *
 * An anchor of another kind is reported as ATTESTED rather than failed, which
 * is the exact meaning of the word: the record asserts somebody else holds
 * evidence, the fields saying who and what are present and checked, and this
 * reader cannot confirm it. The level is still reached and rests on one fewer
 * verified check, which the per-level basis counts already report. */
const CHECKABLE_KINDS = new Set(["rfc3161", "scitt"]);

/* Narrower than the set above, and the difference matters. A genTime is an
 * RFC 3161 field. When scitt joined the checkable kinds the clock check
 * inherited it from the same constant and began handing COSE receipts to a
 * TimeStampResp parser, which is the bug that refusing unknown kinds already
 * was: one kind's format applied to another because it was the one built. */
const TIMESTAMPED_KINDS = new Set(["rfc3161"]);
const VDS_RFC9162_SHA256 = 1;

/* Enough CBOR to read a COSE_Sign1 receipt, and the RFC 9162 inclusion proof.
 * The port of the same code in testimony_validate.py; the two are compared on
 * every record by CI, so they have to reach the same verdict here too. */
export function cborLoad(b: Uint8Array, i = 0): [any, number] {
  const ib = b[i], mt = ib >> 5, ai = ib & 0x1f;
  i += 1;
  let val: number | null;
  if (ai < 24) val = ai;
  else if (ai === 24) { val = b[i]; i += 1; }
  else if (ai === 25) { val = (b[i] << 8) | b[i + 1]; i += 2; }
  else if (ai === 26) {
    val = ((b[i] << 24) >>> 0) + (b[i + 1] << 16) + (b[i + 2] << 8) + b[i + 3];
    i += 4;
  } else if (ai === 27) {
    val = 0;
    for (let k = 0; k < 8; k++) val = val * 256 + b[i + k];
    i += 8;
  } else if (ai === 31) val = null;
  else throw new Error("reserved additional info " + ai);

  if (mt === 0) return [val, i];
  if (mt === 1) return [-1 - (val as number), i];
  if (mt === 2 || mt === 3) {
    if (val === null) throw new Error("indefinite strings not supported");
    const raw = b.slice(i, i + val);
    i += val;
    return [mt === 2 ? raw : new TextDecoder().decode(raw), i];
  }
  if (mt === 4) {
    const out: any[] = [];
    if (val === null) {
      while (b[i] !== 0xff) { const [v, j] = cborLoad(b, i); out.push(v); i = j; }
      return [out, i + 1];
    }
    for (let n = 0; n < val; n++) { const [v, j] = cborLoad(b, i); out.push(v); i = j; }
    return [out, i];
  }
  if (mt === 5) {
    const out = new Map<any, any>();
    if (val === null) {
      while (b[i] !== 0xff) {
        const [k, j] = cborLoad(b, i); const [v, j2] = cborLoad(b, j);
        out.set(k, v); i = j2;
      }
      return [out, i + 1];
    }
    for (let n = 0; n < val; n++) {
      const [k, j] = cborLoad(b, i); const [v, j2] = cborLoad(b, j);
      out.set(k, v); i = j2;
    }
    return [out, i];
  }
  if (mt === 6) return cborLoad(b, i);
  if (mt === 7) {
    if (ai === 20) return [false, i];
    if (ai === 21) return [true, i];
    return [null, i];
  }
  throw new Error("major type " + mt);
}

function bytesOfHex(h: string): Uint8Array {
  const out = new Uint8Array(h.length / 2);
  for (let i = 0; i < out.length; i++)
    out[i] = parseInt(h.substr(i * 2, 2), 16);
  return out;
}

function shaBytes(...parts: Uint8Array[]): Uint8Array {
  let n = 0;
  for (const p of parts) n += p.length;
  const all = new Uint8Array(n);
  let at = 0;
  for (const p of parts) { all.set(p, at); at += p.length; }
  return bytesOfHex(sha256Hex(all));
}

export function reconstructRoot(leaf: Uint8Array, index: number, size: number,
                                path: Uint8Array[]): Uint8Array {
  if (index >= size)
    throw new Error(`leaf index ${index} outside a tree of ${size}`);
  let fn = index, sn = size - 1;
  let r = shaBytes(new Uint8Array([0]), leaf);
  for (const p of path) {
    if (sn === 0) throw new Error("audit path longer than the tree is deep");
    if ((fn & 1) !== 0 || fn === sn) {
      r = shaBytes(new Uint8Array([1]), p, r);
      while ((fn & 1) === 0 && fn !== 0) { fn >>= 1; sn >>= 1; }
    } else {
      r = shaBytes(new Uint8Array([1]), r, p);
    }
    fn >>= 1; sn >>= 1;
  }
  if (sn !== 0) throw new Error(`audit path too short for a tree of ${size}`);
  return r;
}

export function readReceipt(raw: Uint8Array) {
  const [body] = cborLoad(raw);
  if (!Array.isArray(body) || body.length !== 4)
    throw new Error("not a COSE_Sign1");
  const [protectedHdr] = body[0] && body[0].length
    ? cborLoad(body[0]) : [new Map()];
  const unprotected: Map<any, any> = body[1] instanceof Map ? body[1] : new Map();
  const proofs = unprotected.get(396);
  const list = proofs instanceof Map ? proofs.get(-1) : null;
  const inclusion = Array.isArray(list) ? list[0] : null;
  let size: number | null = null, index: number | null = null;
  let path: Uint8Array[] = [];
  if (inclusion) {
    const [parsed] = cborLoad(inclusion);
    if (Array.isArray(parsed) && parsed.length === 3) {
      size = parsed[0]; index = parsed[1]; path = parsed[2];
    }
  }
  const hdr: Map<any, any> = protectedHdr instanceof Map ? protectedHdr : new Map();
  return { vds: hdr.get(395), alg: hdr.get(1), treeSize: size,
           leafIndex: index, path, detached: body[2] === null };
}

export function imprints(token: Uint8Array): string[] {
  const out: string[] = [];
  for (let i = 0; i + SHA256_OID.length < token.length; i++) {
    let hit = true;
    for (let k = 0; k < SHA256_OID.length; k++)
      if (token[i + k] !== SHA256_OID[k]) { hit = false; break; }
    if (!hit) continue;
    let j = i + SHA256_OID.length;
    if (token[j] === 0x05 && token[j + 1] === 0x00) j += 2;
    if (token[j] === 0x04 && token[j + 1] === 0x20)
      out.push(Array.from(token.subarray(j + 2, j + 34),
        (x) => x.toString(16).padStart(2, "0")).join(""));
  }
  return out;
}

/* The moment the authority says it saw the imprint, as an RFC 3339 string.
 * In TSTInfo the genTime follows the messageImprint, so the search starts at
 * the imprint and not at the front of the token: a SignerInfo can carry its
 * own signing-time attribute, and a scan from byte zero could return the
 * signer's clock in place of the authority's. Anything that is not a DER
 * GeneralizedTime holding exactly the digits RFC 3161 requires is skipped
 * rather than guessed at, and a token this cannot read yields no check at all
 * rather than a failure. */
export function genTime(token: Uint8Array): string | null {
  let start = -1;
  for (let i = 0; i + SHA256_OID.length < token.length && start < 0; i++) {
    let hit = true;
    for (let k = 0; k < SHA256_OID.length; k++)
      if (token[i + k] !== SHA256_OID[k]) { hit = false; break; }
    if (hit) start = i;
  }
  if (start < 0) return null;
  for (let i = start + 1; i + 1 < token.length; i++) {
    if (token[i] !== 0x18) continue;
    const ln = token[i + 1];
    if (ln < 15 || ln > 24 || i + 2 + ln > token.length) continue;
    let text = "";
    for (let k = i + 2; k < i + 2 + ln; k++) {
      const c = token[k];
      if (c < 0x20 || c > 0x7e) { text = ""; break; }
      text += String.fromCharCode(c);
    }
    const m = /^(\d{4})(\d{2})(\d{2})(\d{2})(\d{2})(\d{2})(\.\d+)?Z$/.exec(text);
    if (!m) continue;
    return `${m[1]}-${m[2]}-${m[3]}T${m[4]}:${m[5]}:${m[6]}${m[7] || ""}Z`;
  }
  return null;
}

/* An RFC 3339 timestamp as seconds, or null if it is not one. Two timestamps
 * are compared here rather than sorted, and comparing the strings would be
 * wrong: `at` may carry an offset while a genTime is always Z, so
 * "2026-09-05T16:31:54+02:00" sorts after a Z time it actually precedes. */
const TS =
  /^(\d{4})-(\d{2})-(\d{2})[Tt](\d{2}):(\d{2}):(\d{2})(\.\d+)?([Zz]|([+-])(\d{2}):(\d{2}))$/;

export function utcSeconds(text: string): number | null {
  const m = TS.exec(text || "");
  if (!m) return null;
  const y = +m[1], mo = +m[2], d = +m[3];
  const cum = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334];
  let days = y * 365 + Math.floor(y / 4) - Math.floor(y / 100)
    + Math.floor(y / 400) + cum[mo - 1] + d;
  if (mo <= 2 && (y % 4 === 0 && (y % 100 !== 0 || y % 400 === 0))) days -= 1;
  let total = days * 86400 + (+m[4]) * 3600 + (+m[5]) * 60 + (+m[6])
    + (m[7] ? parseFloat(m[7]) : 0);
  if (m[9]) {
    const off = (+m[10]) * 3600 + (+m[11]) * 60;
    total += m[9] === "+" ? -off : off;
  }
  return total;
}

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
    checks.push({
      level, check, ok, detail,
      basis: ATTESTED.has(check) ? "attested" : "verified",
    });

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

  /* A name is not an actor. "review.v4" says something produced the belief and
   * nothing about what kind of thing, which is the distinction the format
   * exists to keep: a claim asserted by a model and one asserted by a person
   * are different claims, and a string cannot tell them apart. */
  const shapeless: string[] = [];
  for (const e of entries) {
    const f = ACTOR_FIELDS[str(e.type)];
    if (!f || !(f in e)) continue;   /* absence is the required-fields check */
    const who = (e as Record<string, unknown>)[f];
    if (typeof who !== "object" || who === null || Array.isArray(who)) {
      shapeless.push(`line ${e._line}: ${str(e.type)}.${f} is not an object`);
      continue;
    }
    const w = who as Record<string, unknown>;
    if (!str(w.id).trim())
      shapeless.push(`line ${e._line}: ${str(e.type)}.${f} has no id`);
    if (!ACTOR_KINDS.has(str(w.kind)))
      shapeless.push(`line ${e._line}: ${str(e.type)}.${f} kind ` +
        `${JSON.stringify(w.kind)} is not one of ` +
        `${JSON.stringify(Array.from(ACTOR_KINDS).sort())}`);
  }
  add("TR-1", "every actor is an object naming an id and a kind",
    shapeless.length === 0, shapeless.slice(0, 3).join("; "));

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

  // machine-testimony#87. Three reference-shaped members were resolved and
  // `inputs` was not, though it is the only one that says what a decision
  // rested on.
  const stray: string[] = [];
  for (const d of of("decision"))
    for (const b of arr(d.inputs))
      if (str(byId.get(str(b))?.type) !== "belief")
        stray.push(`line ${d._line}: inputs cites ${JSON.stringify(b)}`);
  add("TR-2", "a decision's inputs name beliefs in the record", stray.length === 0,
    stray.slice(0, 3).join("; "));

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

  const selfDeclared: string[] = [];
  for (const d of decisions) {
    const why = sourceProblem(d.risk_source, RISK_SOURCES);
    if (why) selfDeclared.push(`line ${d._line}: ${why}`);
  }
  add("TR-3",
    "the risk class is declared to come from outside the proposing model",
    selfDeclared.length === 0, selfDeclared.slice(0, 3).join("; "));

  const ranAnyway = decisions.filter(
    (d) => str(d.verdict) === "refused" && d.executed === true);
  add("TR-3", "a refused action did not execute", ranAnyway.length === 0,
    `${ranAnyway.length} refused decision(s) recorded as executed`);

  // A decision carrying `outcome` must not contradict the rest of itself.
  // Saying it ran and that it was never attempted cannot both hold. Saying it
  // ran and that the effect is unconfirmed can: a provider returning 200 with
  // settlement pending is observed-run and effect-unconfirmed. Reported by
  // impartshadow, 6 September 2026.
  const contradicts: string[] = [];
  for (const d of decisions) {
    const out = d.outcome;
    if (out === undefined || out === null) continue;
    if (d.executed === true && out === "not_attempted") {
      contradicts.push(`line ${d._line}: executed with outcome '${out}'`);
    } else if (str(d.verdict) === "refused" && out !== "not_attempted") {
      contradicts.push(`line ${d._line}: refused with outcome '${out}'`);
    }
  }
  add("TR-3", "a decision does not contradict its own outcome",
    contradicts.length === 0, contradicts.slice(0, 3).join("; "));

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
    if (!str(who.id).trim())
      badApprover.push(`line ${a._line}: approver names nobody`);
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
  add("TR-3",
    "an approval names a person, other than the proposer, for a decision in " +
    "the record",
    badApprover.length === 0, badApprover.slice(0, 3).join("; "));

  const unsourced: string[] = [];
  for (const a of approvals) {
    const why = sourceProblem(a.identity_source, IDENTITY_SOURCES);
    if (why) unsourced.push(`line ${a._line}: ${why}`);
  }
  add("TR-3", "the approver's name is declared to come from authentication",
    unsourced.length === 0, unsourced.slice(0, 3).join("; "));

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

  /* Nothing here used to recompute anything. TR-4 was reached by a digest of
     sixty-four zeros, and an anchored record could carry a real, correctly
     signed token over some entirely different record. */
  const silent = integrity.filter((g) => arr(g.covers).length === 0)
    .map((g) => `line ${g._line}`);
  add("TR-4", "an integrity entry says which entries its digest is over",
    silent.length === 0, silent.slice(0, 3).join("; "));

  const wrong: string[] = [];
  for (const g of integrity) {
    const ids = arr(g.covers).map(str);
    if (!ids.length) continue;
    if (ids.some((cid) => !byId.has(cid))) continue;   /* reported as stale */
    const covered = ids.map((cid) => byId.get(cid) as Entry);
    let got: string;
    try {
      got = "sha256:" + digestOf(covered);
    } catch (e) {
      wrong.push(`line ${g._line}: ${(e as Error).message}`);
      continue;
    }
    if (str(g.digest) !== got)
      wrong.push(`line ${g._line}: says ${str(g.digest).slice(0, 22)}.., ` +
        `covers ${got.slice(0, 22)}..`);
  }
  add("TR-4", "a digest is the digest of the entries it covers",
    wrong.length === 0, wrong.slice(0, 3).join("; "));

  const adrift: string[] = [];
  const unread: string[] = [];
  let checkable = 0;
  for (const g of integrity) {
    if (str(g.scheme) !== "external-anchor") continue;
    const a = obj(g.anchor);
    const kind = str(a.kind).trim().toLowerCase();
    if (kind && !CHECKABLE_KINDS.has(kind)) {
      unread.push(kind);
      continue;        /* not this validator's to judge, nor its to fail */
    }
    checkable += 1;
    const tok = str(a.token), want = str(g.digest);
    if (!tok || !want.startsWith("sha256:")) continue;  /* reported as hollow */
    const raw = b64(tok);
    if (!raw) {
      adrift.push(`line ${g._line}: the token is not base64`);
      continue;
    }
    if (kind === "scitt") {
      /* What binds a receipt to this record is that the inclusion proof, taken
       * over THIS record's digest, lands on the tree head the anchor declares.
       * A receipt minted for another record reconstructs perfectly well and
       * lands somewhere else, which is why the head has to be declared. */
      const head = str(a.root).trim().toLowerCase();
      if (!head) {
        adrift.push(`line ${g._line}: a scitt anchor declares the tree head ` +
          `its proof lands on, and this one does not`);
        continue;
      }
      let rec;
      try {
        rec = readReceipt(raw);
      } catch (e) {
        adrift.push(`line ${g._line}: the receipt does not parse ` +
          `(${String(e).slice(0, 40)})`);
        continue;
      }
      if (rec.vds !== VDS_RFC9162_SHA256) {
        checkable -= 1;
        unread.push("scitt with vds " + rec.vds);
        continue;
      }
      let got: Uint8Array | null = null;
      try {
        got = reconstructRoot(bytesOfHex(want.slice(7)),
          rec.leafIndex as number, rec.treeSize as number, rec.path);
      } catch (e) {
        adrift.push(`line ${g._line}: the inclusion proof does not ` +
          `reconstruct (${String(e).slice(0, 40)})`);
        continue;
      }
      if (!got) continue;
      const gotHex = Array.from(got)
        .map((x: number) => x.toString(16).padStart(2, "0")).join("");
      if (gotHex !== head)
        adrift.push(`line ${g._line}: the proof over this record's digest ` +
          `lands on ${gotHex.slice(0, 16)}.., not the declared head`);
      continue;
    }

    const found = imprints(raw);
    if (!found.length)
      adrift.push(`line ${g._line}: no SHA-256 imprint in the token`);
    else if (!found.includes(want.slice(7).toLowerCase()))
      adrift.push(`line ${g._line}: the token is over a different digest ` +
        `(${found[0].slice(0, 16)}..)`);
  }
  // Two claims, and until 8 September 2026 they were reported as one. See
  // the note in the Python reference: nothing here verifies a signature, so
  // the imprint comparison keeps the verified mark it has earned and the
  // authority's issuance becomes the attested claim it always was.
  if (checkable) {
    add("TR-4", "the anchor's token is over this record's digest",
      adrift.length === 0, adrift.slice(0, 3).join("; "));
    add("TR-4", "and the authority named in it issued that token", true,
      "no signature is checked here: that would need a certificate this " +
      "validator does not carry");
  }
  if (unread.length)
    add("TR-4", "an anchor of a kind this validator cannot recompute rests " +
      "on its authority", true,
      "not checked here: " + Array.from(new Set(unread)).sort().join(", "));

  /* The one bound on the record's own clock a reader can settle. Every `at` is
   * written by the emitter, and nothing above checks one against anything
   * outside the emitter: RFC 3339 shape and non-decreasing order are both
   * verified and both establish only that its numbers are well formed and
   * monotone. A TimeStampResp carries the moment a third party saw the digest,
   * and this validator was reading the token far enough to check the imprint
   * and then throwing that moment away. One-sided by nature: it catches
   * forward dating past the anchor and nothing back-dated. Raised in #49. */
  /* Shipped 7 September with no allowance, and the first record anchored
   * moments after being written failed it: the emitter's clock was two seconds
   * ahead of DigiCert's, so entries were, by the authority's clock, from the
   * future. RFC 3161 has an Accuracy field for this and DigiCert omits it
   * ("Accuracy: unspecified"), so no principled tolerance can be derived from
   * the token and five minutes is the judgement Kerberos, SAML and OIDC use.
   * The measured offset is reported either way: it is the only outside reading
   * of the emitter's clock the record contains, which is the whole of #44. */
  const SKEW_ALLOWANCE = 300;
  const late: string[] = [];
  let bounded = false;
  let skew = 0;
  for (const g of integrity) {
    if (str(g.scheme) !== "external-anchor" || !Array.isArray(g.covers)) continue;
    const a = obj(g.anchor);
    const tok = str(a.token);
    const kind = str(a.kind).trim().toLowerCase();
    if (!tok || !TIMESTAMPED_KINDS.has(kind)) continue;
    const raw = b64(tok);   /* genTime is RFC 3161's; another kind has none */
    if (!raw) continue;                       /* reported as adrift, above */
    const seen = genTime(raw);
    const bound = seen === null ? null : utcSeconds(seen);
    if (bound === null) continue;   /* unreadable yields no check, not a fail */
    bounded = true;
    for (const cid of g.covers as unknown[]) {
      const e = byId.get(String(cid));
      if (!e) continue;                        /* reported as stale, above */
      const when = utcSeconds(str(e.at));
      if (when === null || when <= bound) continue;
      const ahead = when - bound;
      if (ahead > skew) skew = ahead;
      if (ahead > SKEW_ALLOWANCE)
        late.push(`line ${e._line}: written ${str(e.at)}, ${ahead} seconds ` +
          `after the ${seen} the authority saw it, which is longer than a ` +
          `clock is wrong`);
    }
  }
  if (bounded) {
    let detail = late.slice(0, 3).join("; ");
    if (late.length === 0 && skew)
      detail = `measured: the emitter's clock reads ${skew} second` +
        `${skew === 1 ? "" : "s"} ahead of the authority's. Within the ` +
        `${SKEW_ALLOWANCE}s allowed for clock error, and reported rather ` +
        `than hidden because it is the only outside reading of the emitter's ` +
        `clock in the record.`;
    add("TR-4", "no entry post-dates the anchor by more than a clock " +
      "could be wrong", late.length === 0, detail);
  }

  /* The level reached is the highest with nothing failing below it. */
  const failed = (lvl: Level) => checks.some((c) => c.level === lvl && !c.ok);
  const levelsMet = Object.fromEntries(
    LEVELS.map((l) => [l, !failed(l)])) as Record<Level, boolean>;
  let level: Level | null = null;
  for (const lvl of LEVELS) {
    if (failed(lvl)) break;
    level = lvl;
  }

  const basis = Object.fromEntries(LEVELS.map((l) => [l, {
    verified: checks.filter((c) => c.level === l && c.basis === "verified").length,
    attested: checks.filter((c) => c.level === l && c.basis === "attested").length,
  }])) as Report["basis"];

  return { spec, scope, level, levelsMet, basis, checks, entries,
    parseErrors: errors };
}
