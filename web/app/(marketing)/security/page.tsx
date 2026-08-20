import Link from "next/link";
import { MarketingShell } from "@/components/marketing/chrome";
import { Section } from "@/components/marketing/ui";

export const metadata = { title: "Security / OMEM" };

// Everything in CONTROLS is implemented in this repository and covered by the
// test suite. Everything in NOT_YET is not, and used to be claimed here anyway:
// the page previously advertised TLS 1.3, per-tenant KMS envelope encryption,
// BYOK, a hash-chained audit stream, region pinning, OIDC/SAML SSO, SCIM 2.0,
// SOC 2 Type II, ISO 27001 and a HIPAA BAA. A buyer who checks is going to
// check this list first, and a security page that overstates by that much is
// worse for trust than one that is short.

const CONTROLS = [
  { k: "AUTHENTICATION", d: "Two modes, and the server picks neither for you. Local mode has no login and refuses to bind anything but loopback. Password mode (OMEM_AUTH=password) stores PBKDF2-SHA256 password hashes, and signup will not issue a session for an address that already has one." },
  { k: "SECOND FACTOR", d: "TOTP (RFC 6238), enforced at session creation and on claiming an account. Sessions expire after 30 days and can be revoked; expired and revoked tokens stop working immediately." },
  { k: "TLS", d: "Set OMEM_TLS_CERT and OMEM_TLS_KEY and the server speaks HTTPS directly, TLS 1.2 floor. A terminating proxy is still the better answer at scale (it renews and resumes better than this does) but OMEM no longer requires one to avoid plaintext." },
  { k: "ENCRYPTION AT REST", d: "OMEM_ENCRYPT_AT_REST encrypts memory content with AES-GCM: the operations log the engine is rebuilt from, ingested source payloads, and the quoted evidence behind each memory. Stored OAuth tokens are encrypted regardless. Lose the master key and you lose the data. There is no recovery path, by design." },
  { k: "ACCESS CONTROL", d: "Role-based, enforced per organization and per project. API keys are scoped to one project, carry their own role, can be bound to a single agent, and are revocable. Key secrets are shown once and stored hashed." },
  { k: "TAMPER-EVIDENT AUDIT", d: "Every audit row commits to the one before it, per organization. Editing or deleting a row breaks every hash after it, and GET /v1/audit/verify says which row and why. Anchor the head hash somewhere OMEM does not control and the log becomes evidence rather than assertion." },
  { k: "DATA RIGHTS", d: "GDPR/CCPA export and erasure are endpoints, not a process: /v1/export/memories exports a project, and tenant erasure removes every project-scoped row. Backups taken before an erasure still contain the data until they age out." },
  { k: "ABUSE CONTROL", d: "Per-IP limits on the auth endpoints and per-tenant limits on data endpoints, keyed by project and credential so one key cannot starve another tenant." },
  { k: "ONE WRITER", d: "The engine is authoritative in memory, so a second process against the same database would answer the same question differently. The second process refuses to start and says so, rather than diverging quietly." },
  { k: "DEPLOYMENT", d: "Self-hosted, on SQLite or PostgreSQL. MIT licensed, so the engine that decides what your agents believe is one you can read, fork, and keep." },
];

const NOT_YET = [
  ["Tamper-PROOFING", "The audit chain detects edits; it cannot prevent them. Anyone with write access can rewrite the chain from the edit forward. Detecting that requires keeping the head hash somewhere else, export it."],
  ["SSO and SCIM", "No OIDC, SAML or SCIM. Accounts are email and password."],
  ["Key rotation", "There is one master key and no re-encryption tooling. Rotating it today means decrypting and re-encrypting by hand."],
  ["Data residency", "No region pinning. Your data is wherever you run it."],
  ["Certifications", "No SOC 2, ISO 27001 or HIPAA BAA. None are in progress."],
  ["High availability", "One writer per database, enforced. That makes divergence impossible, not uptime possible: there is no second replica, no rolling deploy, and a restart replays the operations log before serving."],
];

export default function Security() {
  return (
    <MarketingShell>
      <Section className="pt-20 pb-14">
        <div className="tech-label mb-4">Security</div>
        <h1 className="display max-w-xl text-[40px]">What this actually protects, and what it does not.</h1>
        <p className="mt-5 max-w-lg text-[15px] leading-relaxed text-muted">
          The moment an agent acts on a belief, someone is accountable for it. OMEM is built
          so you can reconstruct agent state at decision time. It is early software, it is free
          while in beta, and the second list on this page is as important as the first.
        </p>
      </Section>

      <Section className="pb-16">
        <div className="tech-label mb-4">Implemented today</div>
        <div className="border-t">
          {CONTROLS.map(c => (
            <div key={c.k} className="spec-row border-b py-6">
              <div className="text-xs font-medium text-accent">{c.k}</div>
              <p className="max-w-xl text-[14px] leading-relaxed text-muted">{c.d}</p>
            </div>
          ))}
        </div>
      </Section>

      <Section className="pb-16">
        <div className="tech-label mb-4">Not yet. Do not plan around these</div>
        <div className="border-t">
          {NOT_YET.map(([k, d]) => (
            <div key={k} className="spec-row border-b py-6">
              <div className="text-xs font-medium text-conflict">{k}</div>
              <p className="max-w-xl text-[14px] leading-relaxed text-muted">{d}</p>
            </div>
          ))}
        </div>
        <p className="mt-6 max-w-xl text-[13px] leading-relaxed text-muted">
          If your deployment needs something on this list, OMEM is not ready for it yet. Saying so
          here is cheaper for both of us than saying so after an audit.
        </p>
      </Section>

      <Section className="pb-8">
        <div className="spec-row border-t pt-12">
          <div className="tech-label pt-1">No lock-in</div>
          <div>
            <h2 className="display max-w-lg text-[28px]">An open standard you can verify, and leave with.</h2>
            <p className="mt-5 max-w-lg text-[15px] leading-relaxed text-muted">
              OMEM is a standard first, with a public conformance suite. &quot;Correct&quot; is decidable:
              every deployment passes the identical 29-vector CTS. An agent built against one
              OMEM behaves the same against another. Your memory&apos;s meaning never leaves with
              a vendor.
            </p>
            <dl className="mt-8 max-w-md overflow-hidden rounded-lg border bg-panel text-[13px] shadow-sm">
              {[["Protocol", "OMEM 1.0"], ["Conformance", "CTS 29/29 / deterministic"],
                ["Reference engine", "open source, self-hostable"], ["License", "MIT"],
                ["Audit stream", "append-only, exportable"]].map(([k, v]) => (
                <div key={k} className="flex items-center justify-between border-b px-4 py-2.5 last:border-b-0">
                  <dt className="text-muted">{k}</dt><dd className="num text-[13px]">{v}</dd>
                </div>
              ))}
            </dl>
            <Link href="/docs/quickstart" className="link-underline mt-8 inline-block text-[13px]">
              Read the quickstart
            </Link>
          </div>
        </div>
      </Section>
    </MarketingShell>
  );
}
