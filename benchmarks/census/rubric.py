"""The requirements a Testimony Record needs, restated as capability questions.

`scripts/testimony_validate.py` answers "does this record conform?". It cannot
answer "could this system produce such a record?", because a system that has
never heard of the specification emits nothing for it to read. Pointed at any
third-party agent framework it would return "none" for all of them, which is
not a finding. It is an artefact of asking the wrong question.

So this module asks the other question. For each requirement behind a
conformance level, it states the capability in terms any system can be assessed
against by reading its source and its documentation:

    not  "does it write `type: belief` with an `evidence` array"
    but  "can the source a stored fact came from be recovered from the store"

A system that satisfies the capability but writes it in its own format has the
information, and getting it into the Testimony Record format is then a
translation. A system that does not have the information cannot translate its
way to conformance at any price. That difference is the only thing this census
is trying to measure.

`applies_to` names the kind of system a requirement is about. A vector store is
not failing at approval gates; it is not an approval gate. Scoring it as a
failure would be dishonest, so subjects declare their scope and requirements
outside it resolve to `not_applicable`.

Copyright 2026 Michael Brandon Clifford. MIT licensed.
"""
from __future__ import annotations

# The capabilities a system can be in the business of having. A subject
# declares which of these it claims, and is assessed only on those.
CAPABILITIES = {
    "stores": "keeps facts across turns or sessions",
    "derives": "infers, extracts or enriches beyond what it was told",
    "acts": "takes or gates actions with effects outside itself",
}

# `undetermined` exists because the alternative is a guess. A system can keep
# the record this rubric asks about in a component the assessor cannot read: a
# hosted server, a closed dependency, anything outside the repository in front
# of them. Scoring that `absent` would state a fact about software nobody
# looked at, which is the exact failure the evidence rules exist to prevent.
# It blocks a conformance level exactly as `absent` does, because a level
# claimed on unchecked facts is not a level.
VERDICTS = ("present", "partial", "absent", "undetermined", "not_applicable")

LEVELS = {
    "TR-1": ("Recorded", "The record exists and is append-only."),
    "TR-2": ("Explained",
             "Every belief resolves to its evidence, and disagreements survive."),
    "TR-3": ("Gated", "Actions carry a verdict, and approvals carry a name."),
    "TR-4": ("Verifiable", "The record can be shown not to have changed."),
}
LEVEL_ORDER = ["TR-1", "TR-2", "TR-3", "TR-4"]


class Req:
    __slots__ = ("id", "level", "applies_to", "question", "present_means",
                 "partial_means")

    def __init__(self, id, level, applies_to, question, present_means,
                 partial_means):
        self.id = id
        self.level = level
        self.applies_to = applies_to
        self.question = question
        self.present_means = present_means
        self.partial_means = partial_means

    def as_dict(self) -> dict:
        return {k: getattr(self, k) for k in self.__slots__}


REQUIREMENTS = [
    # -- TR-1 Recorded -------------------------------------------------------
    Req("R1.1", "TR-1", "stores",
        "When the system stores a fact, does it durably record when that "
        "happened?",
        "a write time is stored with the fact and survives restart",
        "a timestamp exists in application logs but not with the fact itself"),
    Req("R1.2", "TR-1", "stores",
        "When a stored fact changes, is the previous version still readable?",
        "an update writes a new version and the old one remains queryable",
        "history exists for some entity kinds, or only inside a retention window"),
    # R1.3 asks about the ORDINARY write path, and R1.5 handles erasure
    # separately, because the first draft of this rubric collapsed them and
    # thereby scored a lawful response to a GDPR erasure request as a
    # conformance failure. Every system deployed in the EU has to be able to
    # destroy data on request. A rubric that marks them all down for obeying
    # the law is measuring its author's oversight, not their engineering.
    Req("R1.3", "TR-1", "stores",
        "Does the ordinary write path ever destroy what was previously "
        "recorded?",
        "no routine call edits or deletes in place; a correction is a new entry",
        "the routine update path overwrites, though history is kept elsewhere"),
    Req("R1.4", "TR-1", "stores",
        "Are entries distinguishable by kind, or is everything one "
        "undifferentiated blob of text?",
        "assertions, sources and actions are separate typed records",
        "a type field exists but is free-form or advisory"),
    Req("R1.5", "TR-1", "stores",
        "When data must be destroyed for a legal reason, is the destruction "
        "itself recorded?",
        "erasure is a privileged act that leaves a durable, queryable trace "
        "that it happened, without re-retaining what was erased",
        "erasure is possible and logged, but the log is ordinary application "
        "logging rather than part of the record"),

    # -- TR-2 Explained ------------------------------------------------------
    Req("R2.1", "TR-2", "stores",
        "Can the source a stored fact came from be recovered from the store, by "
        "following a link rather than by guessing?",
        "each fact carries a resolvable reference to the message, document or "
        "event it came from",
        "the raw source is retained somewhere but is not linked from the fact"),
    Req("R2.2", "TR-2", "derives",
        "Can a fact the system inferred be told apart from one it was told?",
        "derived facts are marked as derived and name what they came from",
        "a provenance field exists but does not distinguish told from inferred"),
    Req("R2.3", "TR-2", "stores",
        "When two stored facts about the same proposition disagree, do both "
        "survive?",
        "both are retained; neither is silently overwritten by the later one",
        "both survive only until a consolidation or summarisation step runs"),
    Req("R2.4", "TR-2", "stores",
        "Is the disagreement itself queryable, or must a reader diff rows to "
        "notice it?",
        "a conflict is a first-class object that can be listed",
        "conflicts are discoverable by query but are not recorded as such"),
    # The specification says resolution is recorded "if any". A system that
    # never resolves a contradiction, and leaves it standing as a contradiction,
    # satisfies this completely. An earlier draft of this rubric scored that as
    # a miss, which would have marked down the more conservative design for
    # being more conservative.
    Req("R2.5", "TR-2", "stores",
        "When a conflict is resolved, does the record say who resolved it and "
        "by what method?",
        "resolution records an actor and a method, or the system never resolves "
        "conflicts and unresolved is a durable, visible state",
        "resolution happens but the actor is 'the system', with no detail, or "
        "is decided implicitly by recency"),

    # -- TR-3 Gated ----------------------------------------------------------
    Req("R3.1", "TR-3", "acts",
        "Does a consequential action produce a durable entry whether or not it "
        "ran?",
        "attempted actions are recorded, including those that never executed",
        "executed actions are recorded but attempts that were stopped are not"),
    Req("R3.2", "TR-3", "acts",
        "Does an action's risk class come from somewhere the proposing model "
        "cannot write to?",
        "risk comes from a registry, policy file or config outside model output",
        "risk is configurable but the model's own output can override it"),
    Req("R3.3", "TR-3", "acts",
        "Are refusals recorded as faithfully as permissions?",
        "a refused action leaves a record of the same standing as a permitted one",
        "refusals appear in application logs but not in the durable record"),
    Req("R3.4", "TR-3", "acts",
        "Does a refusal record why it was refused?",
        "a machine-readable reason accompanies the refusal",
        "a human-readable message exists but no structured reason"),
    Req("R3.5", "TR-3", "acts",
        "Does an approval identify a person or a named role holder?",
        "the approver is a person or a role, not a model or a process",
        "an approval step exists but the approver may be an automated principal"),
    Req("R3.6", "TR-3", "acts",
        "Does the approver's identity come from the authentication layer rather "
        "than from something the model can write?",
        "identity is taken from the authenticated session, not the request body",
        "identity is supplied by the caller and merely conventionally trusted"),
    Req("R3.7", "TR-3", "acts",
        "Is the acting agent prevented from approving its own action?",
        "the approver principal cannot be the proposing principal",
        "separation is documented as a recommendation but is not enforced"),

    # -- TR-4 Verifiable -----------------------------------------------------
    Req("R4.1", "TR-4", "stores",
        "Does the system publish a scheme under which the record's past state "
        "can be verified?",
        "a documented integrity scheme exists: replay, hash chain, signatures "
        "or an external anchor",
        "backups or exports exist, which preserve data but prove nothing of it"),
    Req("R4.2", "TR-4", "stores",
        "Can an independent party run that verification without the vendor's "
        "cooperation?",
        "the verification can be run by the record holder against their own copy",
        "verification is offered as a vendor service or needs vendor-held keys"),
    Req("R4.3", "TR-4", "stores",
        "Would alteration of a past entry be detectable after the fact?",
        "alteration breaks a digest, chain or replay that anyone can check",
        "alteration is restricted by access control, which is prevention rather "
        "than detection"),
]

BY_ID = {r.id: r for r in REQUIREMENTS}
BY_LEVEL: dict[str, list] = {}
for _r in REQUIREMENTS:
    BY_LEVEL.setdefault(_r.level, []).append(_r)


def applicable(req, claims) -> bool:
    """Whether a subject claiming `claims` should be assessed on `req`."""
    return req.applies_to in claims
