import { readFileSync } from "fs";
import { join } from "path";
import { MarketingShell } from "@/components/marketing/chrome";
import { Section, Eyebrow, HeroHeading } from "@/components/marketing/ui";

export const metadata = {
  title: "The claims ledger: every sentence, and the test that would go red",
  description:
    "Every load-bearing sentence OMEM says about itself, next to the executable statement that would fail if it stopped being true. A claim with no row here is opinion, and the ledger itself is guarded by a test.",
};

/* The claims ledger, rendered from CLAIMS.md at build time rather than
 * retyped, so the page cannot disagree with the file CI checks. Reading the
 * source of truth is the whole point: a second copy would be a claim about a
 * claim, and this project's rule is that a sentence with no test is opinion. */

const REPO = "https://github.com/troybrandonc-bit/Omem/blob/main/";

type Row = { claim: string; proofs: string[] };

/* A backticked item in the second column is usually a path and sometimes a
 * flag, and a flag rendered as a link is a 404 the reader finds before we do. */
const isPath = (s: string) => s.includes("/") || /\.(py|ts|tsx|yml|yaml|json|md|txt)$/.test(s);

/* Claim text carries inline code of its own. Rendering the backticks
 * literally would be the page disagreeing with the file it is quoting. */
function withCode(text: string) {
  return text.split(/(`[^`]+`)/g).map((part, i) =>
    part.startsWith("`") && part.endsWith("`") && part.length > 2
      ? <code key={i} className="font-mono text-2xs">{part.slice(1, -1)}</code>
      : <span key={i}>{part}</span>);
}

function ledger(): Row[] {
  const md = readFileSync(join(process.cwd(), "..", "CLAIMS.md"), "utf8");
  const rows: Row[] = [];
  for (const line of md.split("\n")) {
    const t = line.trim();
    if (!t.startsWith("|") || !t.endsWith("|")) continue;
    const cells = t.slice(1, -1).split("|").map(c => c.trim());
    if (cells.length !== 2) continue;
    if (/^-+$/.test(cells[0].replace(/[:\s]/g, ""))) continue;
    if (cells[0] === "The claim") continue;
    rows.push({
      claim: cells[0],
      proofs: (cells[1].match(/`[^`]+`/g) || []).map(p => p.slice(1, -1)),
    });
  }
  return rows;
}

export default function Claims() {
  const rows = ledger();
  return (
    <MarketingShell>
      <Section className="hero-y">
        <Eyebrow>The claims ledger</Eyebrow>
        <HeroHeading className="mt-3">
          Every sentence, next to the test that would go red.
        </HeroHeading>
        <div className="mt-10 max-w-[52rem]">
          <p className="lede">
            Marketing that cannot fail is indistinguishable from marketing that
            is false. Everything below can fail. Each row pairs a load bearing
            claim with the executable statement that would stop passing if the
            claim stopped being true, and a claim with no row here is opinion
            rather than a promise.
          </p>
          <p className="mt-5 max-w-read text-body text-muted">
            This page is generated from{" "}
            <a className="link" href={REPO + "CLAIMS.md"}>CLAIMS.md</a> when the
            site is built, so it cannot drift from the file. The ledger is
            itself guarded: a row whose file is missing, or a row with no proof
            at all, fails{" "}
            <a className="link" href={REPO + "server/tests_claims_ledger.py"}>
              tests_claims_ledger.py
            </a>{" "}
            before the sentence it backs can ship. Every run is public in{" "}
            <a className="link"
               href="https://github.com/troybrandonc-bit/Omem/actions">
              the workflow log
            </a>.
          </p>
        </div>
      </Section>

      <Section className="section-y">
        <div className="overflow-x-auto">
          <table className="w-full min-w-[42rem] border-collapse text-note">
            <thead>
              <tr className="border-b border-[color:var(--line-strong)] text-left">
                <th className="py-3 pr-6 font-semibold">The claim</th>
                <th className="py-3 font-semibold">What would go red</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r, i) => (
                <tr key={i} className="border-b border-[color:var(--line)] align-top">
                  <td className="py-4 pr-6 text-body">{withCode(r.claim)}</td>
                  <td className="py-4">
                    <ul className="space-y-1">
                      {r.proofs.map(p => (
                        <li key={p} className="font-mono text-2xs">
                          {isPath(p)
                            ? <a className="link" href={REPO + p}>{p}</a>
                            : <span className="text-muted">{p}</span>}
                        </li>
                      ))}
                    </ul>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="mt-8 max-w-read text-note text-muted">
          {rows.length} claims. If one of these ever goes red and the sentence
          is still on the site, that is a bug worth reporting, and the fastest
          way to report it is the failing run.
        </p>
      </Section>
    </MarketingShell>
  );
}
