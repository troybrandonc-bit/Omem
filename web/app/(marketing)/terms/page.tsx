import { MarketingShell } from "@/components/marketing/chrome";
import { Section, PageHeader } from "@/components/marketing/ui";

export const metadata = {
  title: "Terms",
  description:
    "The terms for OMEM: MIT-licensed software you run yourself, a website, an opt-in commons, and a paid design-partner pilot. Plain language.",
};

/* Terms, in plain language. The software's real terms are the MIT license; the
 * rest covers the site, the commons, and the pilot without inventing legalese
 * we would not enforce. No em dashes. */

const SECTIONS: [string, React.ReactNode][] = [
  ["The software",
   <>OMEM is licensed under the MIT License, which is the whole agreement for
   the code: you can use, modify, and redistribute it, commercially or not, and
   it comes with no warranty of any kind. The license text ships in the
   repository. We have publicly committed that the open-source core stays MIT.</>],
  ["No warranty, and your data is your responsibility",
   <>OMEM is early software, provided as is. You run it on your own
   infrastructure, so backups, security of your deployment, and compliance
   obligations that apply to the data you put in it are yours. The security
   page lists what is built and what is not; rely on that list, not on
   assumptions.</>],
  ["The commons",
   <>Contributing to the commons is opt-in and anonymous by construction. By
   opting in you agree that the anonymous counts your install sends may be
   pooled and published as a training dataset under CC BY 4.0. Do not attempt
   to submit identifying data or to re-identify anyone from the dataset;
   contributions that could identify a person are refused and may be deleted.</>],
  ["The design-partner pilot",
   <>The pilot is a fixed-fee engagement ($1,500) for hands-on integration
   work, agreed by email before any payment. It is not a software license, a
   support contract, or an SLA. Either side can end it before completion, with
   a pro-rata refund of work not yet done. Anything we learn inside your stack
   stays confidential.</>],
  ["The website",
   <>Content on this site is provided for information. We work to keep every
   claim accurate (most are tied to CI tests), but the site is not a contract.
   Trademarks and names belong to their owners.</>],
  ["Changes",
   <>If these terms change, the change lands here with a new date. Continued
   use of the site or the commons after a change means the new terms apply;
   the MIT license on code you already have can never be revoked.</>],
];

export default function Terms() {
  return (
    <MarketingShell>
      <Section className="page-y">
        <PageHeader eyebrow="Terms" title="The terms, in plain language.">
          The software&rsquo;s real terms are the MIT license. The rest of this
          page covers the website, the commons, and the pilot.
        </PageHeader>
        <div className="mt-12 max-w-2xl space-y-10">
          {SECTIONS.map(([h, b]) => (
            <div key={h as string}>
              <h2 className="text-md font-semibold">{h}</h2>
              <p className="mt-2.5 text-note leading-relaxed text-muted">{b}</p>
            </div>
          ))}
          <p className="border-t pt-6 text-caption text-faint">
            Last updated 31 August 2026.
          </p>
        </div>
      </Section>
    </MarketingShell>
  );
}
