import { MarketingShell } from "@/components/marketing/chrome";
import { Section, PageHeader } from "@/components/marketing/ui";

export const metadata = {
  title: "Privacy",
  description:
    "What OMEM collects and what it does not. The software runs on your machine and phones home to nobody; this page covers the website, the pilot form, and the commons collector.",
};

/* The privacy page. Short because the honest answer is short: the product is
 * self-hosted and sends us nothing, so the only data we ever touch comes from
 * this website's form, an email you send, or an anonymous contribution to the
 * commons. Plain language on purpose; no em dashes. */

const SECTIONS: [string, React.ReactNode][] = [
  ["The software: your data never reaches us",
   <>OMEM is self-hosted. Your memory data, your agents&rsquo; beliefs, and your
   API keys live in a database on your own machine or server. The software makes
   no calls to us: a CI test fails the build if any network connection leaves
   your machine (<span className="mono">server/tests_airgap.py</span>). We
   cannot see, access, or recover your data, which also means backups are
   yours to keep.</>],
  ["This website",
   <>The site is static pages served by Cloudflare. We use Cloudflare&rsquo;s
   cookieless, aggregate web analytics to count visits; it sets no cookies and
   builds no profile of you. The only thing the site stores in your browser is
   your light/dark theme choice, in localStorage, which never leaves your
   device.</>],
  ["The pilot form",
   <>If you submit the form on <span className="mono">/pilot</span>, the name,
   email, and message you type are relayed by Web3Forms to our inbox so we can
   reply. We use them to answer you and for nothing else. Ask us to delete the
   thread at any time and we will.</>],
  ["The commons collector",
   <>If you opt in to contributing to the commons, your install sends anonymous
   counts only: two behaviour tokens and how many people held both, under a
   random instance id. The door refuses anything that could identify a person
   (names, emails, ids, values) on arrival, and the exported training dataset
   is built from those counts alone. Opting in is a choice you make once, is
   off by default, and is revocable in Settings. No account, no IP log tied to
   contributions, nothing to link a pattern back to a person or an install.</>],
  ["What we never do",
   <>No advertising trackers, no selling or sharing data, no profiles, no
   cross-site anything. If a future feature would change any answer on this
   page, the page changes first and the feature ships opt-in.</>],
  ["Erasure",
   <>Inside your own OMEM install, the right to be forgotten is a real
   operation: one request rewrites the record and is replay-verified. For
   anything we hold (a pilot email thread), write to us and it is deleted.</>],
];

export default function Privacy() {
  return (
    <MarketingShell>
      <Section className="page-y">
        <PageHeader eyebrow="Privacy" title="What we collect, which is almost nothing.">
          The product runs on your machine and sends us nothing. The short list
          below is everything else, stated plainly.
        </PageHeader>
        <div className="mt-12 max-w-2xl space-y-10">
          {SECTIONS.map(([h, b]) => (
            <div key={h as string}>
              <h2 className="text-md font-semibold">{h}</h2>
              <p className="mt-2.5 text-note leading-relaxed text-muted">{b}</p>
            </div>
          ))}
          <p className="border-t pt-6 text-caption text-faint">
            Last updated 31 August 2026. Questions: use the form at{" "}
            <a href="/pilot" className="underline hover:text-fg">/pilot</a> or open
            a GitHub issue.
          </p>
        </div>
      </Section>
    </MarketingShell>
  );
}
