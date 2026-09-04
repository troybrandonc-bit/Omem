---
title: "The Testimony Record: An Interchange Format for What an Automated System Believed and Did"
abbrev: "Testimony Record"
docname: draft-clifford-testimony-record-00
category: info
ipr: trust200902
submissionType: independent
area: "Applications and Real-Time"
keyword:
  - accountability
  - provenance
  - audit
  - autonomous agents
stand_alone: yes
pi: [toc, sortrefs, symrefs]

author:
  -
    ins: T. Clifford
    name: Troy Clifford
    organization: Machine Testimony
    email: troy@machinetestimony.com
    uri: https://machinetestimony.org

# RFC 2119 and RFC 8174 are deliberately absent here: the bcp14
# boilerplate below declares them itself, and naming them in both places
# makes kramdown warn that the reference is inline and in the header.
normative:
  RFC8259:
  RFC7493:
  RFC3339:
  RFC7464:

informative:
  RFC9162:
  I-D.ietf-scitt-architecture:
  TR-SPEC:
    title: "The Testimony Record"
    author:
      ins: T. Clifford
      name: Troy Clifford
    date: 2026
    target: https://infrastructure.omem-cloud.com/spec/testimony-record/
  CENSUS:
    title: "The Testimony Record Conformance Census: What Eight Agent Systems Record About What They Did"
    author:
      ins: T. Clifford
      name: Troy Clifford
    date: 2026-09
    seriesinfo:
      DOI: 10.5281/zenodo.22290922
  EU-AI-ACT:
    title: "Regulation (EU) 2024/1689 laying down harmonised rules on artificial intelligence"
    author:
      org: European Parliament and Council of the European Union
    date: 2024

--- abstract

This document specifies the Testimony Record, an append-only interchange format
for the account an automated system gives of its own operation: what it
believed, what evidence each belief rested on, which of its beliefs
contradicted one another, what actions it attempted, and who authorised the
consequential ones.

The format is defined so that a party who was not present, and who has no
access to the emitting system, can read a record and check specific properties
of it. Four conformance levels are defined, each stating a property that can be
verified mechanically rather than asserted.

This is not a logging format. Logs record what a program did. A Testimony
Record states what a system claimed to know, what disagreed with it, and what
it was permitted to do about it.

--- middle

# Introduction

Automated systems increasingly hold beliefs about people and take actions on
the strength of them. When such an action is later questioned, the questions
asked are consistent: what did the system believe at that moment, where did
that belief come from, was there anything contradicting it, and who allowed the
action to proceed.

Existing formats answer none of these. Structured logging records events.
Distributed tracing records calls. Neither retains what a system concluded, nor
whether two of its conclusions disagreed, nor whether a person with a name
permitted a consequential action or a process did so unattended.

The gap is not hypothetical. A survey of eight widely used agent memory and
agent framework implementations {{CENSUS}} found that several pause a
consequential action to wait for human approval, and none records the identity
of the person who approved. A run in which an engineer read the arguments and
decided produces a record indistinguishable from one in which a script approved
everything automatically.

## Scope

This document specifies a serialisation and a set of conformance levels. It
does not specify how a system forms beliefs, how it should resolve
disagreements, what risk classification it should apply, or how it should
authenticate an approver. Those are properties of an implementation. This
document specifies what such a system must be able to write down about them.

## Design Constraints

Three observations shape the format.

First, a record whose completeness cannot be checked is worth little regardless
of its accuracy. A conformance claim the reader cannot verify is an adjective.

Second, silently resolving a disagreement destroys the only evidence that the
system was ever uncertain. Both sides of a contradiction are therefore
retained, and resolution, if it occurs, is recorded as an event with an actor.

Third, an ungrounded belief must be expressible. A system that cannot state
"believed, and nothing supports this" will, under pressure to produce
well-formed output, produce support that does not exist.

# Conventions and Definitions

{::boilerplate bcp14-tagged}

Record:
: A sequence of entries describing one system over one period.

Entry:
: A single JSON object; one element of the serialisation.

Emitter:
: The system that produced the record.

Actor:
: A JSON object carrying at least `id` and `kind`, where `kind` is one of
  `agent`, `human`, `system` or `connector`. It MAY carry `name` and `role`.

Subject:
: The thing a belief is about. Frequently a person.

Proposition:
: A claim about a subject, expressed as a stable token or URI rather than as
  prose, so that two entries can be compared.

Consequential action:
: An action with an effect outside the emitter.

# Serialisation

A record is a sequence of JSON texts {{RFC8259}} in the I-JSON {{RFC7493}}
profile, encoded in UTF-8. Two framings are defined and carry the same entries:

Line-delimited:
: One JSON text per line, separated by LF. This is the common on-disk form and
  is used throughout this document for readability.

Sequence:
: JSON Text Sequences {{RFC7464}}, each JSON text preceded by RS (0x1E). This
  is the self-delimiting form, and the one the media type in
  {{iana-considerations}} names.

Converting between them is mechanical. A parser MAY accept both, and can
distinguish them by the leading octet.

Every entry MUST contain the following members.

spec:
: The specification version this entry conforms to. This document specifies
  `testimony-record/0.2`. All entries in one record MUST name the same version.

type:
: One of `belief`, `evidence`, `conflict`, `decision`, `approval`, `integrity`,
  `scope`.

id:
: A string unique within the record. An identifier MUST NOT be reused, in this
  record or in a later one from the same emitter.

at:
: The time the entry was written, as an {{RFC3339}} timestamp. This is the
  write time and not the time any described fact held. Entries MUST appear in
  non-decreasing write-time order.

An entry MAY carry members not defined here. A consumer MUST ignore members it
does not recognise.

# Entry Types

## scope

At most one per record, declaring what the emitting system does. Introduced in
`testimony-record/0.2`; a record naming `testimony-record/0.1` MUST NOT carry
one.

acts:
: Boolean. REQUIRED. Whether the emitter takes or gates consequential actions.

declared_by:
: An Actor. OPTIONAL. What made the declaration.

A record with no scope entry is read as `acts: true`, which is what every
`testimony-record/0.1` record means. A record declaring `acts: false` MUST NOT
contain a decision entry. A record that contradicts its own declaration is not
describing the system it claims to describe, and fails at the lowest
conformance level rather than at the level it would otherwise have skipped.

## belief

subject, proposition:
: REQUIRED. What the belief concerns, and what is claimed.

polarity:
: REQUIRED. `affirm` or `deny`.

state:
: REQUIRED. `believed_true`, `believed_false`, `contradicted` or `unknown`, as
  at write time. A later entry may supersede it. This entry is never edited.

asserted_by:
: REQUIRED. An Actor.

evidence:
: An array of evidence entry identifiers. REQUIRED at TR-2 and above. An empty
  array asserts that the belief is ungrounded, and MUST be representable.

## evidence

kind:
: REQUIRED. `document`, `message`, `event`, `api`, `human` or `derived`.

source:
: REQUIRED. A stable identifier for where the material came from.

digest:
: OPTIONAL, RECOMMENDED. A content hash, so a cited source can be shown
  unchanged without the record carrying its content.

excerpt:
: OPTIONAL. The quoted material itself.

redacted:
: OPTIONAL boolean. True where content was deliberately withheld. The citation
  still stands, and a digest allows the holder of the source to show it
  unchanged.

## conflict

subject, proposition:
: REQUIRED. What is disagreed about.

sides:
: REQUIRED. Two or more belief identifiers. Every one of them MUST be present
  in the record as a belief entry.

resolution:
: An object or null. Null is valid, and frequently the honest value: a
  disagreement that nothing resolved is a fact about the system. A non-null
  resolution MUST carry `method`, `by`, `at` and `kept`, and `kept` MUST be one
  of the identifiers in `sides`.

Where a belief has `state` of `contradicted`, a conflict entry naming that
subject and proposition MUST be present.

## decision

action_type:
: REQUIRED. What was proposed.

risk_class:
: REQUIRED. `low`, `medium` or `high`.

risk_source:
: REQUIRED at TR-3. Where the risk class came from. A risk class originating in
  the output of the model proposing the action is not a gate. The values
  `model`, `plan`, `prompt`, `request`, `request-body` and `agent` therefore do
  not satisfy this requirement, and neither does omitting the member. A
  conforming value names something the proposing model cannot write: a policy
  registry, an action-type table, an operator's configuration.

proposed_by:
: REQUIRED. An Actor.

verdict:
: REQUIRED. `permitted` or `refused`.

executed:
: REQUIRED. Boolean. A decision with `verdict` of `refused` MUST NOT record
  `executed` as true.

reason:
: REQUIRED where the verdict is `refused`.

inputs:
: OPTIONAL. Identifiers of the beliefs the decision rested on.

approval:
: The identifier of an approval entry. REQUIRED where `risk_class` is `high`
  and `executed` is true.

## approval

decision:
: REQUIRED. The identifier of the decision this approval permits, which MUST be
  present in the record.

approver:
: REQUIRED. An Actor whose `kind` is `human`.

identity_source:
: REQUIRED. Where the approver's identity was obtained. It MUST NOT be content
  the proposing model can write, and the same values excluded for `risk_source`
  are excluded here. An authenticated session, a signed assertion or a
  directory lookup satisfies this. A name the model produced does not.

method:
: OPTIONAL. How the approval was given.

The approver MUST NOT be the principal named in the approved decision's
`proposed_by`. An implementation that lets an acting agent's own credential
sign off its own action does not meet the level, however the name in the entry
is spelled.

## integrity

scheme:
: REQUIRED. `replay`, `hash-chain`, `signature` or `external-anchor`.

digest:
: REQUIRED. The value under which alteration would be detected.

engine, engine_version:
: REQUIRED where the scheme is `replay`. A replay nobody else can reproduce is
  not a verification.

covers:
: OPTIONAL. Identifiers of the entries the digest is computed over, each of
  which MUST be present in the record.

# Conformance Levels

Each level states a property of the record. The level reached is the highest
for which nothing at that level or below is unmet.

## TR-1: Recorded

The record parses, is not empty, and names one known specification version
throughout. Every entry has a known type, its required members, allowed values
for enumerated members, a unique identifier and a well-formed write time.
Entries are in non-decreasing write-time order, which is what append-only looks
like from outside. At most one scope entry is present, and a record declaring
that it does not act contains no decisions.

## TR-2: Explained

Every belief states its evidence, including by stating that there is none, and
every cited evidence entry is present. Every conflict names at least two sides,
and every side is retained as a belief in the record. A belief marked
contradicted has a conflict entry naming it. A resolved conflict records the
method, the actor, the time, and which side was kept.

## TR-3: Gated

The record contains at least one decision, unless the emitter has declared that
it does not act. Every decision's risk class comes from outside the proposing
model's control. A refused action did not execute, and records its reason. An
executed high-risk action has an approval entry. Every approval names a human,
sourced from authentication rather than from model output, and that human is
not the proposer.

An emitter declaring `acts: false` satisfies this level by having no actions to
gate. This is satisfaction rather than exemption: such a system may reach TR-4.

## TR-4: Verifiable

The record publishes an integrity scheme, every integrity entry carries a
digest, a replay scheme names the engine and its version, and anything an
integrity entry claims to cover is present in the record.

## On the Ordering

The levels are cumulative, which conflates two independent properties: whether
a system gates its actions, and whether its record can be shown unaltered. A
system may hold a genuine hash chain and gate nothing, and before the scope
entry existed such a system reported TR-2 however good its integrity was.

The scope entry resolves the case where the system does not act. It does not
resolve the general case. Implementations reporting conformance SHOULD report
each level's own result alongside the level reached, so that a satisfied level
sitting behind an unmet one below remains visible, and SHOULD report the
declared scope with the level, because "TR-4, record only" is a different
sentence from "TR-4".

# Security Considerations

A record is evidence about a system, and frequently about people.

A record is not a secure log below TR-4. Nothing in the format prevents an
entry being altered after the fact. Non-decreasing write times demonstrate that
a record is consistent with having been appended to, not that it was. Consumers
MUST NOT treat conformance at TR-1 through TR-3 as tamper evidence.

A self-declared scope is believed by the validator. An emitter that acts and
declares otherwise skips the gate requirements. Two things limit the damage: a
record contradicting its own declaration fails at TR-1, and the declaration is
reported with the level rather than hidden inside it. Neither is a substitute
for external attestation. Consumers requiring assurance beyond self-assertion
should look to the SCITT architecture {{I-D.ietf-scitt-architecture}} and to
transparency logs {{RFC9162}}.

An approval is only as strong as its identity source. The format requires
identity to originate outside anything the proposing model can write, and
requires the approver not to be the proposer, but it cannot verify that an
implementation honoured either. These are the failures a reader cannot
otherwise detect, which is why they are stated as requirements rather than left
to implementations.

An identifier reused across records defeats them both. Identifier uniqueness is
checked within a record. An emitter that restarts its counter produces two
records that cannot be read together.

# Privacy Considerations

Belief entries frequently concern identifiable people, and evidence entries may
reference material about them.

Implementations SHOULD omit content and carry a digest instead. A citation with
a digest lets a holder of the source show it unchanged, without the record
becoming a second copy of the material. The `redacted` member exists so that a
withheld excerpt is visibly withheld rather than silently absent, which is the
difference between a record that can be audited and one that merely looks
complete.

Append-only recording is in tension with erasure obligations. This document
takes no position on how an implementation should resolve that tension, but
notes that the two obvious resolutions both fail: rewriting history destroys
the property that made the record worth keeping, and recording a deletion
alongside the deleted content erases nothing. An implementation SHOULD be able
to record that a destruction occurred without re-retaining what was destroyed.

# IANA Considerations

IANA is requested to register the following media type in the "Media Types"
registry.

Type name:
: application

Subtype name:
: testimony-record+json-seq

Required parameters:
: N/A

Optional parameters:
: N/A

Encoding considerations:
: binary; a JSON text sequence {{RFC7464}} of UTF-8 encoded JSON texts

Security considerations:
: See {{security-considerations}} of this document.

Interoperability considerations:
: All entries in one record name a single specification version. Consumers
  ignore members they do not recognise.

Published specification:
: This document

Applications that use this media type:
: Systems recording and exchanging accounts of automated decision-making, and
  tools that validate such accounts

Fragment identifier considerations:
: N/A

Additional information:
: Deprecated alias names for this type: N/A. Magic number(s): N/A. File
  extension(s): .trseq for the sequence framing; .jsonl is in common use for
  the line-delimited framing. Macintosh file type code(s): N/A.

Person and email address to contact for further information:
: Troy Clifford <troy@machinetestimony.com>

Intended usage:
: COMMON

Restrictions on usage:
: None

Author:
: Troy Clifford

Change controller:
: The IESG

# Relationship to Regulation

The European Union Artificial Intelligence Act {{EU-AI-ACT}} requires
record-keeping over the lifetime of high-risk systems, and human oversight
capable of intervention. This document does not implement those obligations and
makes no claim of compliance with them. It is noted only that the levels
defined here were shaped by the same questions: TR-1 by automatic recording as
events occur, TR-2 and TR-3 by the identification of risk situations, and TR-3
by the attributability of oversight. Whether a given deployment satisfies a
legal obligation is a matter for the parties to that obligation and their
regulator.

--- back

# Implementation Status

At the time of writing, this format has a reference validator and a reference
emitter, and a second independent validator implementation in TypeScript that
is checked against the first on a corpus of records covering each level and
each failure mode.

The reference validator is a single standard-library file with no network
access, published under an MIT licence, so that a conformance claim can be
checked by the party hearing it rather than by the party making it {{TR-SPEC}}.

A survey of eight agent memory and agent framework implementations against
these requirements is published with a DOI {{CENSUS}}. It includes the
reference implementation, which the survey states carries no evidential weight,
and records two defects the survey found in it during preparation.

The `scope` entry, the conditional TR-3 requirement, and the recommendation to
report per-level results are new in `testimony-record/0.2` and have one
implementation each at the time of writing.

# Acknowledgements
{:numbered="false"}

Phill Clapham reported that the reference validator refused TR-3 to any record
containing no decision entries, a requirement that appears nowhere in the
specification text, with the effect that a system holding a genuine hash chain
and gating nothing could not reach TR-4 however good its integrity was. The
scope entry and the per-level reporting in this document are the result.
