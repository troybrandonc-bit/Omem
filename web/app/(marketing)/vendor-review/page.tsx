import { MarketingShell } from "@/components/marketing/chrome";
import { Section, PageHeader, SpecList, ButtonLink } from "@/components/marketing/ui";

export const metadata = {
  title: "For your vendor security review",
  description:
    "The answers a procurement or security team needs about OMEM as a supplier: no data leaves your infrastructure, no subprocessors, no telemetry, and an MIT core you keep permanently if we stop existing. Written to be forwarded.",
};

/* This page exists to be FORWARDED. The champion inside a company does the
 * selling, and what they need is not a pitch but a link that survives being
 * read by someone paid to say no.
 *
 * /security answers "is the software secure". This answers the different
 * question procurement actually asks, which is "is this supplier acceptable",
 * and those have different answers for a one-person company.
 *
 * The rule here is the rule on /security: the absences are stated as plainly
 * as the strengths. A reviewer who finds one thing hidden re-reads everything
 * else looking for the next one, and they are right to. No em dashes. */

const NO_DATA = [
  { k: "Where your data goes", d: "Nowhere. OMEM runs on your infrastructure and holds your data there. There is no OMEM-hosted service, no account to create, and no upload step, so there is no transfer to assess and no residency question to answer." },
  { k: "What it sends us", d: "Nothing. No telemetry, no usage reporting, no crash reports, no licence check-in. A build fails in CI if any part of the system opens a connection to anything but loopback, and that test has run on every commit since 2026." },
  { k: "Subprocessors", d: "None. There is no cloud provider, no analytics vendor and no support tool in the path of your data, because your data never enters a path we operate. Most of a subprocessor questionnaire is not applicable, and this is the reason." },
  { k: "The licence check", d: "A signature verified offline against a public key compiled into the server. It opens no connection and reports no usage. There is no endpoint to allowlist, and nothing fails closed if your network blocks us." },
  { k: "Access by us", d: "None is possible. We hold no credentials to your install, there is no support tunnel and no break-glass path. If you want help, you send us what you choose to send us." },
];

const CONTINUITY = [
  { k: "If we stop existing", d: "You keep running it, permanently. The core is MIT: not a promise to open-source later, and not a source-available licence with conditions, but a grant already made that cannot be withdrawn from the version you hold." },
  { k: "Source escrow", d: "Unnecessary, which is worth saying plainly because it is usually a cost line in an agreement like this. Escrow exists to release source if a supplier fails. The source is already public, on GitHub and inside the package you installed. There is nothing to hold that you do not already have." },
  { k: "The format is not ours to withdraw", d: "The record OMEM writes is the Testimony Record, a published specification with a JSON Schema and a validator that depends on nothing of ours. If we disappear the format keeps working and other implementations can read what you already wrote." },
  { k: "Key-person risk", d: "Real, and named rather than dressed up. OMEM is maintained by one person. What that risk costs you is bounded by the two answers above: your deployment does not depend on our continuity, and neither does the readability of your records." },
  { k: "Lock-in", d: "The exit is the export. One endpoint returns every belief with its provenance, and the testimony exporter writes the whole record in an open format. Leaving costs a command rather than a project." },
];

const HONEST = [
  { k: "No SOC 2, ISO 27001, or HIPAA BAA", d: "None held, none in progress. If your policy requires one from every supplier regardless of architecture, we will fail that check, and you should stop here rather than spend three weeks discovering it." },
  { k: "No SSO or SCIM", d: "Accounts are email and password with TOTP. SSO gets built for the first customer who requires it, as part of their licence rather than in advance of it." },
  { k: "No uptime SLA", d: "You operate it, so the uptime is yours. We cannot credibly promise availability for a process we cannot see." },
  { k: "Small supplier", d: "One person, no outside funding. Everything above is designed so that this matters to you as little as it possibly can. It is not nothing, and we will not pretend otherwise." },
];

export default function VendorReview() {
  return (
    <MarketingShell>
      <Section className="page-y">
        <PageHeader eyebrow="Vendor review"
          title="The answers your security team is about to ask for.">
          Written to be forwarded. Most vendor questionnaires assume the supplier
          holds your data, so most of one is not applicable here, and the reason
          is architectural rather than a policy we could quietly change later.
          Where the answer is unfavourable it is on this page too, because a
          reviewer who finds one omission re-reads everything looking for the
          next one.
        </PageHeader>
      </Section>

      <Section className="pb-20 sm:pb-28">
        <div className="max-w-3xl">
          <h2 className="display text-xl">Your data, and what reaches us</h2>
          <p className="lede mt-4">
            Nothing reaches us. That is not a commitment we are asking you to
            take on trust: it is enforced by a test that fails the build.
          </p>
        </div>
        <div className="mt-8 max-w-3xl">
          <SpecList items={NO_DATA} />
        </div>
      </Section>

      <Section className="section-y">
        <div className="max-w-3xl">
          <span aria-hidden="true" className="block h-px w-full bg-[color:var(--border)]" />
          <h2 className="display mt-9 text-xl">
            What happens to you if we disappear
          </h2>
          <p className="lede mt-4">
            The usual answer from a small supplier is a promise. This one is a
            licence you already hold and a format you can already read.
          </p>
        </div>
        <div className="mt-8 max-w-3xl">
          <SpecList items={CONTINUITY} />
        </div>
      </Section>

      <Section className="section-y">
        <div className="max-w-3xl">
          <span aria-hidden="true" className="block h-px w-full bg-[color:var(--border)]" />
          <h2 className="display mt-9 text-xl text-conflict">
            Where we will fail your review
          </h2>
          <p className="lede mt-4">
            Listed so you find it here rather than in week three.
          </p>
        </div>
        <div className="mt-8 max-w-3xl">
          <SpecList items={HONEST} tone="conflict" />
        </div>
      </Section>

      <Section className="pb-24 sm:pb-32">
        <div className="spec-row border-t pt-10">
          <h2 className="tech-label pt-1">Checking any of this</h2>
          <div className="max-w-read space-y-4 text-body text-muted">
            <p>
              Every claim on this page is checkable without asking us. The source
              is public, the network test is in the CI configuration, the format
              has a validator that runs on your machine, and the licence
              verification is a file you can read.
            </p>
            <p>
              The technical control list, including what is not built yet, is on
              the <a href="/security" className="link-underline text-fg">security page</a>.
              A questionnaire we have not answered here is worth sending over:
              the answer goes on this page afterwards, so the next reviewer does
              not have to ask.
            </p>
          </div>
        </div>
        <div className="mt-10 flex flex-wrap gap-3">
          <ButtonLink href="/security">Technical controls</ButtonLink>
          <ButtonLink href="/docs/licence" variant="secondary">How a licence is installed</ButtonLink>
        </div>
      </Section>
    </MarketingShell>
  );
}
