import { MarketingShell } from "@/components/marketing/chrome";
import { Section, CodeBlock, ButtonLink } from "@/components/marketing/ui";

export const metadata = {
  title: "Implementations of the Testimony Record",
  description:
    "Systems that emit conforming Testimony Records, the level each one reaches, and the date its record was last checked. Nothing here is self-reported: a listing follows a record that passed the published validator. Free to be listed.",
};

/* The implementations register. This page is the certification surface: what
 * makes a standard a standard is that somebody checks conformance and the
 * check means something. Listings are earned by sending a record that passes,
 * never by asking. Keep it honest even when the list is short, because a
 * padded register is worth less than an empty one. No em dashes. */

const CHECK = `# what a listing requires: a record your system produced,
# and the command that produced it
python3 testimony_validate.py your-record.jsonl --require TR-2

# in your own CI, on every commit
- uses: troybrandonc-bit/Omem/.github/actions/testimony-conformance@main
  with:
    record: record.jsonl
    require: TR-3`;

type Row = {
  name: string;
  href: string;
  what: string;
  level: string;
  checked: string;
  how: string;
};

const IMPLEMENTATIONS: Row[] = [
  {
    name: "OMEM",
    href: "https://github.com/troybrandonc-bit/Omem",
    what: "Belief revision memory and an approval gate for AI agents. MIT, self-hosted.",
    level: "TR-4",
    checked: "1 September 2026",
    how: "export_testimony.py against a running server. The export is validated in CI on every commit, so the level is checked continuously rather than once.",
  },
];

export default function Implementations() {
  return (
    <MarketingShell>
      <Section className="page-y">
        <article className="prose-omem max-w-3xl">
          <div className="tech-label mb-3">Testimony Record</div>
          <h1 className="display text-3xl">Implementations</h1>

          <p className="lede">
            Systems that emit conforming records, the level each one reaches,
            and when its record was last checked. Nothing on this page is self
            reported. A listing follows a record that passed the validator,
            which anyone can run against the same file.
          </p>

          <table>
            <thead>
              <tr>
                <th>Implementation</th>
                <th>Level</th>
                <th>Checked</th>
              </tr>
            </thead>
            <tbody>
              {IMPLEMENTATIONS.map((r) => (
                <tr key={r.name}>
                  <td>
                    <a href={r.href}>{r.name}</a>
                    <div className="text-note text-muted">{r.what}</div>
                    <div className="text-note text-muted">{r.how}</div>
                  </td>
                  <td className="mono">{r.level}</td>
                  <td className="text-note">{r.checked}</td>
                </tr>
              ))}
            </tbody>
          </table>

          <p>
            One implementation is not a standard, and the editor of a
            specification listing only his own software has written a manual.
            That is the honest state of this page today. It changes when other
            people emit records, which is the whole reason the format, the
            schema and the validator cost nothing to use and ask no permission.
          </p>

          <h2>Getting listed</h2>
          <p>
            Send a record your system produced, along with the command that
            produced it, to <span className="mono">hello@omem-cloud.com</span>.
            It gets run through the published validator. If it passes, the
            implementation is listed here with the level it reached and the
            date it was checked. There is no fee, no membership, and no
            requirement to use OMEM or anything else in particular. An
            implementation in any language, on any stack, counts the same.
          </p>
          <p>
            Records are checked, not trusted. If a later version stops
            conforming, the listing says so rather than quietly keeping the
            old level.
          </p>

          <CodeBlock single={CHECK} filename="terminal"
            label="Check your own record before sending it" />

          <h2>The conformance marks</h2>
          <p>
            An implementation may display the mark for the level its record
            actually reaches, in its README, its documentation, or its product.
            The marks are served from this domain so they cannot drift:
          </p>

          <div className="my-6 flex flex-wrap items-center gap-4">
            {[1, 2, 3, 4].map((n) => (
              /* eslint-disable-next-line @next/next/no-img-element */
              <img key={n} src={`/badge/testimony-record-tr${n}.svg`}
                   alt={`testimony record TR-${n}`} width={173} height={20} />
            ))}
          </div>

          <CodeBlock single={`[![testimony record TR-3](https://infrastructure.omem-cloud.com/badge/testimony-record-tr3.svg)](https://infrastructure.omem-cloud.com/spec/testimony-record/)`}
            filename="README.md" label="Displaying a mark" />

          <p>
            The specification text is CC BY 4.0 and the schema and reference
            code are MIT, so implementing costs nothing and needs no
            permission. The name and the marks are different: they exist to
            identify records that actually pass, so displaying a level a record
            does not reach is the one thing that is not allowed. If a claim
            looks wrong, the editor may ask to see a record.
          </p>

          <div className="mt-10 flex flex-wrap gap-3">
            <ButtonLink href="/spec/testimony-record">Read the specification</ButtonLink>
            <ButtonLink href="/testimony-record-example.jsonl" variant="secondary">A conforming record</ButtonLink>
          </div>
        </article>
      </Section>
    </MarketingShell>
  );
}
