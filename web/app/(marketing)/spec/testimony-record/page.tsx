import { MarketingShell } from "@/components/marketing/chrome";
import { Section, CodeBlock, ButtonLink } from "@/components/marketing/ui";

export const metadata = {
  title: "The Testimony Record Specification, version 0.1",
  description:
    "An open specification for the record an AI agent leaves behind: what it believed, from which evidence, what contradicted it, which actions were proposed, and who approved or refused them. Four conformance levels, a JSON Schema, and a mapping to EU AI Act Article 12. Free to implement.",
};

/* The specification page. This is the standard-setting asset, not a product
 * page: the text is vendor-neutral and free to implement, the name and the
 * conformance marks are owned, and the canonical version lives here. Prose
 * only where prose is needed; the normative parts are tables and schema. No
 * em dashes. */

const ENTRY = `{"spec":"testimony-record/0.1","type":"belief","id":"b_41",
 "at":"2026-09-01T09:14:22Z","subject":"customer:acme",
 "proposition":"plan_annual_pro","polarity":"affirm","state":"contradicted",
 "asserted_by":{"id":"crm-sync","kind":"agent"},"evidence":["e_12"]}

{"spec":"testimony-record/0.1","type":"conflict","id":"c_7",
 "at":"2026-09-01T09:14:23Z","subject":"customer:acme",
 "proposition":"plan_annual_pro","sides":["b_41","b_42"],"resolution":null}

{"spec":"testimony-record/0.1","type":"decision","id":"d_3",
 "at":"2026-09-01T09:15:02Z","action_type":"issue_refund","risk_class":"high",
 "risk_source":"registry","proposed_by":{"id":"support-agent","kind":"agent"},
 "inputs":["b_44","b_45"],"verdict":"refused",
 "reason":"high-risk action requires explicit approval","executed":false}

{"spec":"testimony-record/0.1","type":"approval","id":"a_9",
 "at":"2026-09-01T09:21:40Z","decision":"d_4",
 "approver":{"id":"troy@example.com","kind":"human","name":"T. Clifford",
 "role":"owner"},"method":"console","identity_source":"auth-session"}`;

const VALIDATE = `# any record, from any implementation
python3 testimony_validate.py record.jsonl
# ...
# Conformance: TR-3
# To reach TR-4, fix:
#   - the record publishes an integrity scheme

# in CI, fail the build below a level you promised
python3 testimony_validate.py record.jsonl --require TR-3`;

const EXPORT = `# any OMEM server, running anywhere you can reach it
python3 export_testimony.py --url http://127.0.0.1:8787 \\
    --key omem_sk_... --project proj_... --out record.jsonl

python3 testimony_validate.py record.jsonl --require TR-4
# Conformance: TR-4`;

const LEVELS: Array<[string, string, string]> = [
  ["TR-1 Recorded",
   "The record exists and is append-only.",
   "Belief and evidence entries are written as they happen. Entries are never edited or deleted in place. A correction is a new entry."],
  ["TR-2 Explained",
   "Every belief resolves to its evidence, and disagreements survive.",
   "Each belief entry cites the evidence it rests on, or is explicitly marked ungrounded. When two beliefs about the same proposition disagree, both are retained and a conflict entry names them. Resolution, if any, records who resolved it and how."],
  ["TR-3 Gated",
   "Actions carry a verdict, and approvals carry a name.",
   "Every consequential action produces a decision entry whose risk class comes from a registry outside the proposing model's control. Refusals are recorded as faithfully as permissions. An approval entry identifies a person or named role holder, sourced from the authentication layer rather than from anything the model can write."],
  ["TR-4 Verifiable",
   "The record can be shown not to have changed.",
   "The implementation publishes an integrity scheme (deterministic replay, a hash chain, signatures, or an external anchor) under which an independent party can reproduce or verify the record's state at a past moment, and detect alteration."],
];

const A12: Array<[string, string]> = [
  ["Automatic recording of events over the system's lifetime (Art. 12(1))",
   "TR-1. Entries are written as events occur, not reconstructed afterwards."],
  ["Logs enabling identification of risk situations and post-market monitoring (Art. 12(2))",
   "TR-2 and TR-3. Conflicts surface disagreement; decision entries surface refusals and the actions that were attempted."],
  ["Records kept by providers and deployers, at least six months (Art. 19, Art. 26)",
   "Out of scope for the format, but TR-1's append-only requirement makes retention a storage decision rather than a reconstruction problem."],
  ["Human oversight, including the ability to intervene (Art. 14)",
   "TR-3. The approval entry is the evidence that oversight was real and attributable."],
];

export default function Spec() {
  return (
    <MarketingShell>
      <Section className="page-y">
        <article className="prose-omem max-w-3xl">
          <div className="tech-label mb-3">Specification</div>
          <h1 className="display text-3xl">The Testimony Record Specification</h1>

          <p className="lede">
            An open format for the record an AI agent leaves behind: what it
            believed, from which evidence, what contradicted it, which actions
            it proposed, and who approved or refused them. Free to implement,
            in any language, on any stack.
          </p>

          <table>
            <tbody>
              <tr><td><strong>Version</strong></td><td>0.1 (draft, September 2026)</td></tr>
              <tr><td><strong>Editor</strong></td><td>Troy Clifford</td></tr>
              <tr><td><strong>Canonical URL</strong></td><td><span className="mono">infrastructure.omem-cloud.com/spec/testimony-record/</span></td></tr>
              <tr><td><strong>Schema</strong></td><td><a href="/testimony-record-v0.1.schema.json"><span className="mono">testimony-record-v0.1.schema.json</span></a></td></tr>
              <tr><td><strong>Example</strong></td><td><a href="/testimony-record-example.jsonl"><span className="mono">testimony-record-example.jsonl</span></a>, a conforming record at TR-4</td></tr>
              <tr><td><strong>Validator</strong></td><td><a href="https://github.com/troybrandonc-bit/Omem/blob/main/scripts/testimony_validate.py"><span className="mono">testimony_validate.py</span></a>, one file, no dependencies, MIT</td></tr>
              <tr><td><strong>Exporter</strong></td><td><a href="https://github.com/troybrandonc-bit/Omem/blob/main/scripts/export_testimony.py"><span className="mono">export_testimony.py</span></a>, writes a record from any running OMEM server, MIT</td></tr>
              <tr><td><strong>Status</strong></td><td>Draft. Stable enough to build against, open to comment before 1.0.</td></tr>
            </tbody>
          </table>

          <h2>Why this exists</h2>
          <p>
            When software acts on someone&rsquo;s behalf, two questions
            eventually arrive: <em>why did it do that</em>, and <em>who allowed
            it</em>. Request logs answer neither. They record what happened, not
            what the system believed at the moment it acted, and most memory
            layers overwrite the losing side of a disagreement the instant a new
            fact arrives, so the evidence is gone before anyone asks.
          </p>
          <p>
            Every team shipping agents is now building some version of this
            record, and each one is building a different one. That is a waste,
            and it makes the records incomparable exactly where comparability
            matters: a client&rsquo;s security review, an auditor&rsquo;s
            sample, a regulator&rsquo;s request. This specification describes
            the smallest record that can answer both questions, so an
            implementation can be judged against something other than its own
            marketing.
          </p>

          <h2>Scope</h2>
          <p>
            This specification defines <strong>what a conforming record
            contains and what it must never do</strong>. It does not specify
            storage, transport, query interfaces, retention periods, or how an
            agent decides anything. Those are implementation choices, and
            deliberately so: the format has to survive being implemented by
            systems that disagree about everything else.
          </p>
          <p>
            The key words MUST, MUST NOT, SHOULD and MAY are used as described
            in RFC 2119.
          </p>

          <h2>The record</h2>
          <p>
            A Testimony Record is an <strong>append-only sequence of
            entries</strong>. Entries are never edited or removed in place; a
            correction is a new entry that supersedes an old one, and the old
            one remains readable. Serialisation is one JSON object per line
            (JSON Lines), UTF-8, each line carrying the version it conforms to.
          </p>
          <p>There are six entry types:</p>
          <ul>
            <li><strong>belief</strong>: a claim about a subject, its state at write time, who asserted it, and the evidence it rests on.</li>
            <li><strong>evidence</strong>: where something came from, with enough identity (source, time, optional digest) to be shown unchanged later.</li>
            <li><strong>conflict</strong>: two or more beliefs that disagree, both retained, with resolution recorded only if it happens.</li>
            <li><strong>decision</strong>: an action that was proposed, its risk class, the beliefs it rested on, and the verdict, including refusals.</li>
            <li><strong>approval</strong>: a named human or role holder permitting a decision, with the identity sourced from authentication.</li>
            <li><strong>integrity</strong>: a statement about how the record can be verified not to have changed.</li>
          </ul>

          <CodeBlock single={ENTRY} filename="record.jsonl"
            label="Four entries from a conforming record" />

          <h2>Requirements</h2>
          <p>A conforming implementation:</p>
          <ul>
            <li>MUST write entries append-only, and MUST NOT edit or delete an entry to change what was recorded.</li>
            <li>MUST retain both sides of a disagreement. Silently resolving a conflict by discarding one side is the specific failure this format exists to prevent.</li>
            <li>MUST be able to express an ungrounded belief. A system that cannot say &ldquo;believed, but nothing supports it&rdquo; will eventually fabricate support.</li>
            <li>MUST source an action&rsquo;s risk class from outside the proposing model. A plan that can declare its own risk class is not gated.</li>
            <li>MUST record refusals as durably as permissions.</li>
            <li>MUST source approver identity from the authentication layer, and MUST NOT accept it from content the model can write.</li>
            <li>SHOULD record the time a claim held separately from the time it was written, so a past state can be reconstructed.</li>
            <li>MAY redact evidence content while keeping the citation, for records that contain personal data.</li>
          </ul>

          <h2>Conformance levels</h2>
          <p>
            Levels are cumulative. An implementation claiming a level MUST meet
            every requirement of the levels below it.
          </p>
          <table>
            <thead><tr><th>Level</th><th>In one line</th><th>What it requires</th></tr></thead>
            <tbody>
              {LEVELS.map(([lvl, one, req]) => (
                <tr key={lvl}>
                  <td><strong>{lvl}</strong></td>
                  <td>{one}</td>
                  <td>{req}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p>
            Most systems shipping today are at TR-1 without meaning to be. The
            gap that matters commercially is TR-2 to TR-3: that is where a
            record stops being a log and starts being an answer.
          </p>

          <h2>Checking a claim</h2>
          <p>
            A conformance level that cannot be checked by the person hearing it
            is an adjective. So the validator is published alongside the
            specification: one file, standard library only, no network, MIT. It
            checks the things a JSON Schema cannot, which is the relationships
            between entries: that cited evidence exists, that both sides of a
            contradiction are still present, that the risk class did not come
            from the model proposing the action, and that the approver was a
            person the authentication layer named.
          </p>
          <CodeBlock single={VALIDATE} filename="terminal"
            label="Validate a record and print the level it reaches" />
          <p>
            Copy it into your own repository and run it in your own CI. Vendors
            checking their own homework is the problem, not the solution.
          </p>

          <h2>Mapping to the EU AI Act</h2>
          <p>
            The specification is not legal advice and conformance is not
            compliance. It is written so that the engineering work overlaps
            with the record-keeping obligations that became enforceable for
            high-risk systems in August 2026.
          </p>
          <table>
            <thead><tr><th>Obligation</th><th>Where the format meets it</th></tr></thead>
            <tbody>
              {A12.map(([o, m]) => (
                <tr key={o}><td>{o}</td><td>{m}</td></tr>
              ))}
            </tbody>
          </table>

          <h2>Versioning and governance</h2>
          <p>
            Every entry names its version. Within a major version, entry types
            and required fields are only ever added, never removed or
            repurposed, so a reader written against 0.1 keeps working. Breaking
            changes get a new major version and both remain published.
          </p>
          <p>
            This specification is edited by its author. Proposals, objections
            and implementation reports are welcome as issues on the{" "}
            <a href="https://github.com/troybrandonc-bit/Omem/issues">OMEM
            repository</a>, and the editor decides what enters a version. That
            is stated plainly rather than dressed up as a committee: a small
            standard with a named editor moves faster than a large one with a
            process, and you can see exactly who to argue with.
          </p>

          <h2>Licence, name, and conformance claims</h2>
          <p>
            The specification text is{" "}
            <a href="https://creativecommons.org/licenses/by/4.0/">CC BY 4.0</a>:
            copy it, quote it, translate it, build products on it, including
            commercially, with attribution. The JSON Schema and any reference
            code are MIT. <strong>Implementing this specification costs
            nothing and requires no permission.</strong>
          </p>
          <p>
            &ldquo;Testimony Record&rdquo; and the conformance level marks
            (TR-1 through TR-4) are trademarks of the author. You may state
            that a product &ldquo;implements the Testimony Record
            Specification&rdquo; or &ldquo;conforms to TR-3&rdquo; when it
            genuinely meets those requirements, and that claim is expected to
            survive being checked. What you may not do is publish a modified
            document under the same name, because a standard that anyone can
            redefine is not one.
          </p>
          <p className="text-note text-muted">
            Copyright 2026 Michael Brandon Clifford. Specification text under
            CC BY 4.0; schema and reference code under MIT.
          </p>

          <h2>Reference implementation</h2>
          <p>
            <a href="https://github.com/troybrandonc-bit/Omem">OMEM</a> is the
            reference implementation and emits records at TR-4: beliefs are
            append-only with provenance, contradictions are kept with both
            sides marked, risky actions wait for a named approver with refusals
            recorded, and the engine replays the whole record byte-identically
            on every commit. It is MIT, self-hosted, and installs with one
            command.
          </p>
          <p>
            Point the exporter at any running server and it writes a record
            this validator accepts. Nothing in the output is composed for the
            occasion: belief states come from the memory, risk classes from the
            action registry rather than from the plan that proposed the action,
            and approver identities from the authenticated principal.
          </p>
          <CodeBlock single={EXPORT} filename="terminal"
            label="Export a record from a running server, then check it" />
          <p>
            That round trip runs in CI on every commit, against a real server:
            a contradiction is created, a high-risk action is refused, a named
            reviewer approves it, and the export is validated. If OMEM ever
            stops conforming to this document, the build goes red before anyone
            else finds out.
          </p>
          <p>
            If you implement this in another system, send a record and it gets
            checked and <a href="/spec/testimony-record/implementations">listed
            on the implementations page</a>, along with the conformance mark
            for the level it reaches. Comparable records from systems that
            compete with each other are worth more than any one
            implementation, including this one.
          </p>

          <div className="mt-10 flex flex-wrap gap-3">
            <ButtonLink href="/testimony-record-v0.1.schema.json">The JSON Schema</ButtonLink>
            <ButtonLink href="/docs/quickstart" variant="secondary">Run the reference implementation</ButtonLink>
          </div>
        </article>
      </Section>
    </MarketingShell>
  );
}
