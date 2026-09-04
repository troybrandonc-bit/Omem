# The Testimony Record as an Internet-Draft

`draft-clifford-testimony-record-00.md` is the specification rewritten in
Internet-Draft form, for submission to the IETF datatracker.

## Why this exists

The specification is currently one person's document on one person's website.
Anyone deciding whether to implement it has to decide, first, whether that
person will still be maintaining it in three years. That is a fair question and
the honest answer today is that they cannot know.

An Internet-Draft does not fix that, and it is not a standard. What it does is
give the format an identifier that does not belong to us:
`draft-clifford-testimony-record-00`, a datatracker URL, an archived text that
stays readable whether or not anything of ours is still online, and a public
record of what it said on the day it was published. Nobody grants permission
for this. Anyone may submit a draft, and there is no gatekeeper at the door.

The cost is honest too: most drafts expire after six months and become nothing.
A draft is a place to put a specification, not evidence that anyone wanted it.

## Building it

The source is [kramdown-rfc](https://github.com/cabo/kramdown-rfc) markdown,
which is what most authors write now. There are two routes.

**Without installing anything.** Upload the `.md` file to
<https://author-tools.ietf.org/>. It renders the text, HTML and PDF, and runs
`idnits`, which is the checker the submission tool runs. Do this before
submitting, because it catches boilerplate problems the local build does not.

**Locally**, which needs Ruby and Python:

    gem install kramdown-rfc2629
    pip install xml2rfc

    kdrfc --v3 --xml spec/draft-clifford-testimony-record-00.md
    xml2rfc --text --v3 spec/draft-clifford-testimony-record-00.xml

CI runs exactly these two commands on every commit, under the
`internet-draft renders` job, and uploads the built `.xml` and `.txt` as an
artifact. A draft that does not build is a draft the datatracker will reject at
submission, and finding that out at submission is the worst time to find it
out.

## Submitting it

1. Get a datatracker account at <https://datatracker.ietf.org/accounts/create/>.
2. Build the `.xml` (the submission tool prefers XML; it generates the text
   itself).
3. Submit at <https://datatracker.ietf.org/submit/>.
4. The `-00` version posts immediately. Later versions replace it, and the
   numbering is part of the record: `-01` exists because `-00` said something
   that turned out to be wrong, and both stay public.

A draft expires six months after posting unless a new version is submitted.
Resubmitting an unchanged draft to keep it alive is normal and costs nothing.

## Keeping it true

`server/tests_draft_sync.py` compares this document against
`scripts/testimony_validate.py` on every commit: entry types, required members,
enumerated values, the untrusted identity sources, and the specification version.
Neither file can gain, lose or rename a field without the other failing.

That check exists because the first draft of this document, written in an hour,
omitted `proposed_by` from `decision`, omitted `subject` and `proposition` from
`conflict`, and invented two fields called `held_from` and `held_until` that
exist nowhere. A specification that disagrees with its own reference
implementation is worse than no specification, because somebody builds the wrong
thing and then cannot work out why their record is being rejected.

The check covers what a machine can compare. It does not check the prose, and
the prose is where the next mistake will be.

## What is deliberately not in it

The draft specifies the format and the four conformance levels. It does not
specify how a system forms beliefs, how it resolves disagreements, what risk
classification it applies, or how it authenticates an approver. Those are
implementation decisions, and a specification that made them would be
describing one product rather than a format.

It also does not claim compliance with any regulation. The section on the EU AI
Act says what shaped the levels and then says that whether a deployment
satisfies a legal obligation is a matter for the parties to it. Anything
stronger would be a claim we are not in a position to make.
