# Security policy

OMEM decides what your agents believe. A bug here is not a crash, it is an agent
acting confidently on something it should not believe, so security reports get
treated as the highest-priority class of issue in this project.

## Reporting a vulnerability

**Do not open a public issue.**

Use either:

- **[GitHub private vulnerability reporting](https://github.com/troybrandonc-bit/Omem/security/advisories/new)**
  (Security → Report a vulnerability). Preferred: it goes straight to the
  maintainer, stays private until we publish, and needs no email address from you.
- **security@omem-cloud.com**, if you would rather not use GitHub. Encrypted mail
  is welcome; say so and we will exchange keys before you send details.

Either reaches the same person. Do not open a public issue for a vulnerability,
and do not post details in a pull request comment.

Include what you need to include and nothing more: the version, what you did,
what happened, and what you expected. A proof of concept helps and is not
required. If you are not sure whether something counts, report it. A report
that turns out to be nothing costs an email, and the alternative costs more.

## What to expect

| | |
|---|---|
| First response | Within 3 business days |
| Triage decision | Within 7 days |
| Fix for a confirmed high-severity issue | As fast as one maintainer can, and you will get a date rather than silence |
| Credit | Named in the advisory unless you ask not to be |

This project currently has **one maintainer**. That is stated plainly because it
is the honest bound on the numbers above, and you should weigh it when deciding
how to deploy OMEM. It is not an excuse for a slow response to something serious.

If a report goes unanswered for more than a week, escalate by opening a public
issue that says only *"awaiting a response on a private security report"*, no
details. That is a nudge, not a disclosure.

## Disclosure

Coordinated. We will agree a date with you, publish a
[GitHub Security Advisory](https://github.com/advisories) with a CVE where one
is warranted, ship the fix, and yank affected versions on PyPI where the
severity justifies it. If you want to publish your own writeup, say so and we
will line the dates up rather than race you.

## Supported versions

OMEM is pre-1.0 and moves fast. **Only the latest minor version receives
security fixes.** There is no long-term support branch yet; when there is, it
will be documented here rather than assumed.

| Version | Supported |
|---|---|
| 0.2.x | Yes |
| 0.1.x | **No, see below** |

## Known past vulnerabilities

Listed here rather than buried in the changelog, because someone evaluating this
project deserves to find them without digging.

### 0.1.0 to 0.1.2: authentication bypass (fixed in 0.2.0)

`POST /v1/session {"email": "..."}` returned a valid 30-day session for **any**
address. There was no password anywhere in 0.1.x, so knowing an email address
was the entire credential, including for addresses in `OMEM_ADMIN_EMAILS`,
which reach every project on the server. Enrolling TOTP did not help, because
`/v1/signup` returned a session for an existing address without checking it.

**If you ran 0.1.x on anything other than loopback, treat its data as exposed**,
rotate every API key, and upgrade. These versions are yanked on PyPI: an
existing pin still resolves, but no new install will select them.

Fixed in 0.2.0, which added two explicit auth modes, refuses to bind a
non-loopback address in `local` mode, and refuses to start in `password` mode
without a real `OMEM_MASTER_KEY`. See [CHANGELOG.md](CHANGELOG.md).

## Scope

**In scope:** the server (`server/`), the SDKs (`sdk/`), the MCP server, the
dashboard (`web/`), and the published `omem-infrastructure` package.

**In scope and worth saying explicitly**, because they are the ones people
assume are out of scope:

- Anything that lets a proposed repair plan execute an action OMEM did not
  register. The healing subsystem treats LLM output and error text as data; a
  path where either becomes an instruction is a vulnerability, not a bug.
- Anything that lets one tenant read or write another tenant's rows.
- Anything that lets a caller change belief state without an assertion, or edit
  the audit chain without breaking it.
- Secrets surviving redaction into durable storage.

**Out of scope:** deployments in `OMEM_AUTH=local` mode exposed to a network
(this is documented as unsafe and the server refuses non-loopback binds unless
you override it), issues requiring an already-compromised host, missing hardening
headers on the dashboard with no demonstrated impact, and denial of service by
brute volume against a single-process server, which is a known property, not a
finding.

## What OMEM does not protect against

We keep a public list of what is not yet built, including the things a buyer
would want. It is on the security page in the dashboard
(`web/app/(marketing)/security/page.tsx`) and it is deliberately as prominent as
the list of what *is* built. Nothing on that list is a vulnerability report, it
is already known and already published.
