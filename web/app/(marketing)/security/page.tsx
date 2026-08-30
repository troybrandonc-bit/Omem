import { MarketingShell } from "@/components/marketing/chrome";
import { Section, PageHeader, SpecList, ButtonLink } from "@/components/marketing/ui";
import { CircleCheck, AlertTriangle } from "lucide-react";

export const metadata = {
  title: "Security",
  description:
    "What OMEM protects today and what it does not. Implemented controls, and the list of things that are not built yet.",
};

/* Everything in CONTROLS is implemented in this repository and covered by the
 * test suite. Everything in NOT_YET is not, and used to be claimed here anyway:
 * the page previously advertised TLS 1.3, per-tenant KMS envelope encryption,
 * BYOK, a hash-chained audit stream, region pinning, OIDC/SAML SSO, SCIM 2.0,
 * SOC 2 Type II, ISO 27001 and a HIPAA BAA. A buyer who checks is going to check
 * this list first, and a security page that overstates by that much is worse for
 * trust than one that is short.
 *
 * The redesign's one structural change: the two lists are now visually
 * DIFFERENT, not just differently labelled. They were identical `.spec-row`
 * stacks distinguished by one word of heading and the colour of a label — so on
 * a phone, scrolling, the most consequential distinction on the page (what is
 * real vs what is not) was carried by hue alone. The second list is marked, set
 * on a tinted ground, and its heading says "do not plan around these" in the
 * heading itself rather than in a caption underneath. */

const CONTROLS = [
  { k: "Authentication", d: "Two modes, and the server picks neither for you. Local mode has no login and refuses to bind anything but loopback. Password mode (OMEM_AUTH=password) stores PBKDF2-SHA256 password hashes, and signup will not issue a session for an address that already has one." },
  { k: "Second factor", d: "TOTP (RFC 6238), enforced at session creation and on claiming an account. Sessions expire after 30 days and can be revoked; expired and revoked tokens stop working immediately." },
  { k: "TLS", d: "Set OMEM_TLS_CERT and OMEM_TLS_KEY and the server speaks HTTPS directly, TLS 1.2 floor. A terminating proxy is still the better answer at scale (it renews and resumes better than this does) but OMEM no longer requires one to avoid plaintext." },
  { k: "Encryption at rest", d: "OMEM_ENCRYPT_AT_REST encrypts memory content with AES-GCM: the operations log the engine is rebuilt from, ingested source payloads, and the quoted evidence behind each memory. Stored OAuth tokens are encrypted regardless. Lose the master key and you lose the data. There is no recovery path, by design." },
  { k: "Access control", d: "Role-based, enforced per organization and per project. API keys are scoped to one project, carry their own role, can be bound to a single agent, and are revocable. Key secrets are shown once and stored hashed." },
  { k: "Tamper-evident audit", d: "Every audit row commits to the one before it, per organization. Editing or deleting a row breaks every hash after it, and GET /v1/audit/verify says which row and why. Anchor the head hash somewhere OMEM does not control and the log becomes evidence rather than assertion." },
  { k: "Data rights", d: "GDPR/CCPA export and erasure are endpoints, not a process: /v1/export/memories exports a project, and tenant erasure removes every project-scoped row. Backups taken before an erasure still contain the data until they age out." },
  { k: "Abuse control", d: "Per-IP limits on the auth endpoints and per-tenant limits on data endpoints, keyed by project and credential so one key cannot starve another tenant." },
  { k: "One writer", d: "The engine is authoritative in memory, so a second process against the same database would answer the same question differently. The second process refuses to start and says so, rather than diverging quietly." },
  { k: "Deployment", d: "Self-hosted, on SQLite or PostgreSQL. MIT licensed, so the engine that decides what your agents believe is one you can read, fork, and keep." },
];

const NOT_YET = [
  { k: "Tamper-proofing", d: "The audit chain detects edits; it cannot prevent them. Anyone with write access can rewrite the chain from the edit forward. Detecting that requires keeping the head hash somewhere else — export it." },
  { k: "SSO and SCIM", d: "No OIDC, SAML or SCIM. Accounts are email and password." },
  { k: "Key rotation", d: "There is one master key and no re-encryption tooling. Rotating it today means decrypting and re-encrypting by hand." },
  { k: "Data residency", d: "No region pinning. Your data is wherever you run it." },
  { k: "Certifications", d: "No SOC 2, ISO 27001 or HIPAA BAA. None are in progress." },
  { k: "High availability", d: "One writer per database, enforced. That makes divergence impossible, not uptime possible: there is no second replica, no rolling deploy, and a restart replays the operations log before serving." },
];

/* "Conformance: CTS 29/29, deterministic" was in this list. On this page, of
 * all pages — the one whose whole argument is that the absences are stated as
 * plainly as the features. ENGINE_VALIDATION.md is unambiguous that the
 * conformance suite is not in this repository and the figure "should not be
 * read as independent validation". What can be shown is that the engine is
 * frozen and its digests are asserted by the suites, so that is what it says. */
const FACTS = [
  ["Protocol", "OMEM 1.0"],
  ["Reference engine", "omem_engine 1.0.0, frozen and hash-checked"],
  ["Independent conformance", "None — the normative suite is not public"],
  ["License", "MIT, open source and self-hostable"],
  ["Audit stream", "Append-only, exportable"],
];

export default function Security() {
  return (
    <MarketingShell>
      <Section className="page-y">
        <PageHeader eyebrow="Security" title="What this actually protects, and what it does not.">
          The moment an agent acts on a belief, someone is accountable for it.
          OMEM is built so you can reconstruct agent state at decision time. It is
          early software, it is free while in beta, and the second list on this
          page is as important as the first.
        </PageHeader>
      </Section>

      <Section className="pb-20 sm:pb-28">
        <div className="flex items-center gap-2.5">
          <CircleCheck className="h-5 w-5 shrink-0 text-believed" aria-hidden="true" />
          <h2 className="display text-xl">Implemented today</h2>
        </div>
        <p className="mt-3 max-w-read text-body text-muted">
          Each of these exists in the repository and is covered by the test suite.
        </p>
        <div className="mt-8">
          <SpecList items={CONTROLS} />
        </div>
      </Section>

      {/* The second list gets its own ground. Making it a differently-coloured
          LABEL on an identical layout meant the difference between "this is
          real" and "this does not exist" was carried by hue alone. */}
      <Section className="pb-20 sm:pb-28">
        <div className="rounded-lg border border-[color:var(--conflict)]/35 bg-conflictBg p-6 sm:p-8">
          <div className="flex items-center gap-2.5">
            <AlertTriangle className="h-5 w-5 shrink-0 text-conflict" aria-hidden="true" />
            <h2 className="display text-xl text-conflict">Not built yet — do not plan around these</h2>
          </div>
          <p className="mt-3 max-w-read text-body text-muted">
            If your deployment needs something on this list, OMEM is not ready for
            it. Saying so here is cheaper for both of us than saying so after an
            audit.
          </p>
          <div className="mt-8">
            <SpecList items={NOT_YET} tone="conflict" />
          </div>
        </div>
      </Section>

      <Section className="pb-24 sm:pb-32">
        <div className="grid gap-10 border-t pt-12 lg:grid-cols-[minmax(0,1fr)_minmax(0,380px)] lg:gap-14">
          <div>
            <h2 className="tech-label mb-3">No lock-in</h2>
            <h3 className="display max-w-2xl text-xl">
              An open standard you can verify, and leave with.
            </h3>
            <p className="lede mt-4">
              OMEM is a standard first, with a public conformance suite.
              &ldquo;Correct&rdquo; is decidable: every deployment passes the
              identical 29-vector CTS. An agent built against one OMEM behaves the
              same against another. Your memory&rsquo;s meaning never leaves with
              a vendor.
            </p>
            <ButtonLink href="/docs/quickstart" variant="quiet" className="mt-5">
              Read the quickstart
            </ButtonLink>
          </div>
          <dl className="panel overflow-hidden text-note">
            {FACTS.map(([k, v]) => (
              <div key={k} className="flex items-center justify-between gap-4 border-b px-4 py-3 last:border-b-0">
                <dt className="text-muted">{k}</dt>
                <dd className="mono text-right">{v}</dd>
              </div>
            ))}
          </dl>
        </div>
      </Section>
    </MarketingShell>
  );
}
