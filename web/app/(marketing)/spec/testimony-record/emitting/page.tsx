import { MarketingShell } from "@/components/marketing/chrome";
import { Section, CodeBlock } from "@/components/marketing/ui";

export const metadata = {
  title: "Emitting a Testimony Record",
  description:
    "How to emit a Testimony Record from a system you already have. The record is a translation of facts you almost certainly store already, not a rewrite of how your system works. Worked example, in forty lines, with no dependency on anything.",
};

/* The gap this page fills. There was a specification, a schema, a validator, a
 * badge and a register, and nothing telling somebody how to actually emit one
 * from a system they already run. The first external implementer read the
 * validator source to work out what he was aiming at. He was unusually
 * motivated. The next person will not be.
 *
 * Written for somebody who has never heard of us and does not want our
 * software. OMEM appears once, at the bottom, as a reference implementation
 * they can ignore. No em dashes. */

const SCOPE = `{"spec":"testimony-record/0.2","type":"scope","id":"scope_1",
 "at":"2026-09-04T09:00:00Z","system":"your-system","acts":false,
 "note":"a memory store. It records and derives. Nothing actuates on it."}`;

const SCHEMA = `-- the shape almost every memory system already has
CREATE TABLE sources (
  id        TEXT PRIMARY KEY,
  kind      TEXT,        -- email, document, ticket, message
  uri       TEXT,        -- where it came from
  fetched   TEXT,        -- when you read it
  body      TEXT
);

CREATE TABLE facts (
  id         TEXT PRIMARY KEY,
  subject    TEXT,       -- who or what the fact is about
  claim      TEXT,       -- what is claimed
  negated    INTEGER,    -- 0 asserts, 1 denies
  source_id  TEXT REFERENCES sources(id),
  written_at TEXT,
  superseded INTEGER     -- 0 current, 1 replaced by a later fact
);`;

const EXPORT = `import hashlib, json, sqlite3

SPEC = "testimony-record/0.2"

# The evidence vocabulary is closed: document, message, event, api, human,
# derived. Map your own kinds onto it rather than passing yours through, and
# default to something rather than emitting a kind the schema will reject.
KIND = {"email": "message", "chat": "message", "ticket": "document",
        "doc": "document", "webhook": "event", "api": "api"}

db = sqlite3.connect("memory.db")
db.row_factory = sqlite3.Row
out = []

# 1. Every source you kept becomes an evidence entry. The digest lets a reader
#    show the cited source is unchanged without you handing over the body of
#    it, which matters the first time somebody asks for your record in a review.
for s in db.execute("SELECT * FROM sources"):
    out.append({"spec": SPEC, "type": "evidence", "id": f"ev_{s['id']}",
                "at": s["fetched"], "kind": KIND.get(s["kind"], "document"),
                "source": s["uri"], "retrieved_at": s["fetched"],
                "digest": "sha256:" + hashlib.sha256(
                    (s["body"] or "").encode()).hexdigest(),
                "redacted": True})

# 2. Every fact becomes a belief citing the source it came from. A fact with
#    no source exports with an empty list. Say that rather than hide it: a
#    system that cannot express "believed, and nothing supports it" will
#    eventually invent support.
at = {}
for f in db.execute("SELECT * FROM facts"):
    at[f["id"]] = f["written_at"]
    out.append({"spec": SPEC, "type": "belief", "id": f"b_{f['id']}",
                "at": f["written_at"], "subject": f["subject"],
                "proposition": f["claim"],
                "polarity": "deny" if f["negated"] else "affirm",
                "state": "believed_true" if not f["superseded"] else "unknown",
                "asserted_by": {"id": "your-system", "kind": "system"},
                "evidence": [f"ev_{f['source_id']}"] if f["source_id"] else []})

# 3. Where two current facts disagree, both are already above. This names the
#    disagreement so a reader does not have to notice it by diffing rows. A
#    contradiction is only visible once its second side arrives, so it is dated
#    by the later of the two.
rows = db.execute("""
  SELECT a.id AS x, b.id AS y, a.subject, a.claim
  FROM facts a JOIN facts b
    ON a.subject = b.subject AND a.claim = b.claim
   AND a.negated <> b.negated AND a.id < b.id
  WHERE a.superseded = 0 AND b.superseded = 0""")
for i, c in enumerate(rows, 1):
    out.append({"spec": SPEC, "type": "conflict", "id": f"c_{i}",
                "at": max(at[c["x"]], at[c["y"]]), "subject": c["subject"],
                "proposition": c["claim"], "sides": [f"b_{c['x']}", f"b_{c['y']}"],
                "declared_by": {"id": "your-system", "kind": "system"},
                "resolution": None})

# 4. Say what your system is. If it takes no actions, say so and the gate
#    requirements are satisfied by having nothing to gate. It is dated at or
#    before everything else, because it describes the whole record.
first = min(e["at"] for e in out)
out.append({"spec": SPEC, "type": "scope", "id": "scope_1", "at": first,
            "system": "your-system", "acts": False})

# 5. Append-only means the file reads in time order. Within one timestamp,
#    evidence precedes the belief that cites it. Getting this wrong is the
#    most common way a first record fails TR-1.
RANK = {"scope": 0, "evidence": 1, "belief": 2, "conflict": 3}
out.sort(key=lambda e: (e["at"], RANK.get(e["type"], 4)))

# 6. One digest over everything above, so a later edit to the file shows.
body = "\\n".join(json.dumps(e, sort_keys=True) for e in out)
out.append({"spec": SPEC, "type": "integrity", "id": "i_1",
            "at": out[-1]["at"], "scheme": "hash-chain",
            "digest": "sha256:" + hashlib.sha256(body.encode()).hexdigest(),
            "covers": [e["id"] for e in out]})

for e in out:
    print(json.dumps(e))`;

const CHECK = `python3 export.py > record.jsonl
python3 testimony_validate.py record.jsonl

# the validator is one file, standard library only, and makes no network
# calls. Copy it into your own repository and run it in your own CI rather
# than depending on ours. A conformance claim nobody else can check is an
# adjective.`;

type Row = [string, string, string];
const MAP: Row[] = [
  ["A fact you store", "belief", "What it is about, what is claimed, whether it asserts or denies, and who put it there."],
  ["The document or message it came from", "evidence", "Kept as its own entry so a belief can point at it. A digest is enough; you do not have to publish the content."],
  ["Two stored facts that disagree", "conflict", "Names both sides. Neither is deleted to produce it."],
  ["An action your system took, or refused", "decision", "Only if your system acts. Refusals count as much as permissions."],
  ["A person who allowed one", "approval", "Only if your system acts. The identity comes from your auth layer, never from model output."],
  ["How you would show the file has not changed", "integrity", "A hash chain, signatures, deterministic replay, or an external anchor."],
];

const LEVELS: Row[] = [
  ["TR-1", "The record exists and is append-only", "Most systems reach this without meaning to. If you never edit a row to change what it said, you are close."],
  ["TR-2", "Beliefs cite evidence, disagreements survive", "The step that takes real work, and the one worth taking. It is where a log becomes an answer."],
  ["TR-3", "Actions carry a verdict, approvals carry a name", "Only applies if your system acts. If it does not, declare that and the level is satisfied."],
  ["TR-4", "The record can be shown not to have changed", "Independent of TR-3 in substance, and reachable by a record-only system that declares itself one."],
];

export default function Emitting() {
  return (
    <MarketingShell>
      <Section className="page-y">
        <article className="prose-omem max-w-3xl">
          <div className="tech-label mb-3">Testimony Record</div>
          <h1 className="display text-3xl">Emitting a record</h1>

          <p className="lede">
            Your system almost certainly stores most of this already. A
            Testimony Record is a translation of facts you keep anyway, not a
            change to how anything works, and for a system that only records
            it is an afternoon rather than a project.
          </p>

          <p>
            Nothing here depends on any particular software. The format is CC
            BY, the schema and the validator are MIT, and you do not have to
            ask anyone.
          </p>

          <h2>First, does your system act?</h2>
          <p>
            This is the question that decides how much work you are in for, so
            answer it before anything else. Does your system take or gate
            actions with effects outside itself: sending mail, moving money,
            writing to somebody else&rsquo;s database, running code?
          </p>
          <p>
            If it does not, say so in a scope entry. The gate requirements at
            TR-3 are then satisfied by your having nothing to gate, rather than
            excused, and a record-only system can still reach TR-4 on the
            strength of its integrity alone. Most memory systems are in this
            category and it saves you most of the work.
          </p>

          <CodeBlock single={SCOPE} filename="scope entry"
            label="Declaring that your system records rather than acts" />

          <p>
            Declare it honestly. A record that says it does not act and then
            contains a decision entry fails at TR-1, which is lower than the
            level it was trying to skip.
          </p>

          <h2>What maps to what</h2>
          <p>
            Six entry types. You will not need all of them.
          </p>

          <table>
            <thead>
              <tr><th>What you have</th><th>Entry</th><th></th></tr>
            </thead>
            <tbody>
              {MAP.map(([have, entry, note]) => (
                <tr key={entry + have}>
                  <td>{have}</td>
                  <td className="mono">{entry}</td>
                  <td className="text-note text-muted">{note}</td>
                </tr>
              ))}
            </tbody>
          </table>

          <h2>A worked example</h2>
          <p>
            Take a store with the two tables nearly every memory system has:
            the things it read, and the things it concluded.
          </p>

          <CodeBlock single={SCHEMA} filename="schema.sql"
            label="The system being exported" />

          <p>
            The export imports nothing you do not already have. Two details in
            it are the ones a first record usually gets wrong: the evidence
            vocabulary is closed, so your own kinds have to be mapped onto it,
            and the file has to read in time order, so the entries are sorted
            before anything is digested.
          </p>

          <CodeBlock single={EXPORT} filename="export.py"
            label="Exporting it as a Testimony Record" />

          <p>
            That record reaches TR-4 as a record-only system: every belief
            cites its source or declares itself ungrounded, both sides of a
            disagreement survive with the conflict named, and one digest covers
            the file.
          </p>

          <h2>Aim at the level you have earned</h2>
          <p>
            The levels are not a score and there is no advantage in claiming
            one you are not at. A record that overstates fails the validator in
            front of whoever you sent it to, which is worse than an honest
            lower level in every situation this format exists for.
          </p>

          <table>
            <thead>
              <tr><th>Level</th><th>What it says</th><th></th></tr>
            </thead>
            <tbody>
              {LEVELS.map(([lvl, what, note]) => (
                <tr key={lvl}>
                  <td className="mono">{lvl}</td>
                  <td>{what}</td>
                  <td className="text-note text-muted">{note}</td>
                </tr>
              ))}
            </tbody>
          </table>

          <h2>Check it yourself</h2>
          <p>
            Do not send anybody a record you have not run the validator over.
            It reports every level separately, so a level you have satisfied is
            visible even when something below it is not met.
          </p>

          <CodeBlock single={CHECK} filename="terminal"
            label="Validating your own record before anyone else does" />

          <h2>Two things people get wrong</h2>
          <p>
            <b>Exporting an empty evidence array everywhere.</b> An empty list
            is the correct export for a belief nothing supports, and the
            validator accepts it, which means a record citing nothing at all
            can pass TR-2 while meaning nothing. That is not a hypothetical:
            this specification&rsquo;s own reference implementation did exactly
            that for a month. If your store knows where a fact came from, cite
            it.
          </p>
          <p>
            <b>Resolving a disagreement on the way out.</b> If two of your
            facts contradict each other, both belong in the record. Picking the
            more recent one during export produces a record that is tidier than
            your system and less true than it.
          </p>

          <h2>Getting listed</h2>
          <p>
            Send a record your system produced, and the command that produced
            it, to <span className="mono">hello@omem-cloud.com</span>. It gets
            run through the published validator, and if it passes, the
            implementation is listed with the level it reached and the date it
            was checked. No fee, no membership, and no requirement to use any
            particular software. An implementation in any language on any stack
            counts the same.
          </p>
          <p>
            If you find the specification wrong rather than merely
            inconvenient, that is more useful than a listing. The erratum on
            the specification page came from an implementer who read the
            validator and found it refusing a level to systems that had earned
            it.
          </p>

          <p className="text-note text-muted">
            OMEM is the reference implementation and its exporter is readable
            if you want a second example against a more complicated store. You
            do not need it, and nothing on this page assumes it.
          </p>
        </article>
      </Section>
    </MarketingShell>
  );
}
