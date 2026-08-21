# Contributing to OMEM

Thanks for looking. This is a small project with one maintainer, so the most
useful thing you can do is tell us when something breaks or feels wrong, that
feedback is worth more right now than most patches.

## Before you write code

**Open an issue first for anything non-trivial.** Not bureaucracy: OMEM has some
firm design rules (below) and it is miserable to write a good patch and then be
told it cannot be merged for a reason nobody mentioned. A two-line issue saves
that.

Small things (a typo, a broken link, a clearly-wrong error message) just send
the PR.

## The contributor licence agreement

You will be asked to sign a CLA the first time you open a pull request. It is a
checkbox on the PR, handled by a bot.

We are telling you why rather than hoping you do not ask: OMEM is MIT and the
core will stay MIT, but the project intends to build a commercial product around
it, and a CLA keeps that possible without having to track down every past
contributor. Some people decline to sign CLAs on principle, and that is a
legitimate position. If that is you, open an issue describing the fix instead
and it will get implemented with credit to you.

See [CLA.md](CLA.md).

## Design rules that are not negotiable

These are not style preferences. A patch that breaks one of them will be
rejected however good it is, so it is worth reading first.

**1. The engine never decides what is true.** Two claims conflict only when a
caller has declared the pair contradictory. No inferring a contradiction by
reading text, no similarity threshold, no model in the loop. This is the whole
product; the day it starts guessing, the same question stops having the same
answer a year later.

**2. Model output and error text are data, never instructions.** A proposed
repair plan, a retrieved memory, an exception string. None of these may select
or invent an executable action. Only registered handlers run, and risk class
comes from the registry, never from the thing proposing the action.

**3. No third-party runtime dependencies in the server or the Python SDK.**
`pip install omem-infrastructure` pulls nothing else, and that is a product
promise, not an accident. Optional extras (`[encryption]`, `[postgres]`) are the
escape hatch. Dev and test dependencies are fine.

**4. Nothing displayed may be fabricated.** Every number, state and explanation
in the dashboard maps to a real query. If a capability is not wired up, the UI
says so. See the Usage and Settings pages. Trust is shown as ordering, never as
a numeric score.

**5. The engine is frozen.** `server/omem_engine/` is the authoritative
reference and CI checks it byte-for-byte. Changes there need a design discussion
first, and a very good reason.

## Working on it

```bash
# server - Python 3.9+, no dependencies
cd server
python api.py            # http://127.0.0.1:8787

# dashboard - only needed if you are changing the UI
cd web
npm install
npm run dev              # http://localhost:3000, proxying to 8787
```

## Tests

**Every suite must pass before you open a PR.** They are plain scripts, not
pytest:

```bash
cd server
for t in tests*.py; do python "$t" || echo "FAILED: $t"; done
```

CI additionally runs everything against PostgreSQL and against encrypted
storage. If your change touches storage, run those locally:

```bash
OMEM_DATABASE_URL=postgresql://... python tests.py
OMEM_ENCRYPT_AT_REST=1 OMEM_MASTER_KEY=$(python3 -c 'import secrets;print(secrets.token_urlsafe(32))') python tests.py
```

Type-check the dashboard with `cd web && npx tsc --noEmit`.

**New behaviour needs a new test.** The suites are adversarial on purpose,
`tests_healing.py` tries prompt injection, `tests_p9_abuse.py` tries to exhaust
the server. Write the test that tries to break your feature, not the one that
proves it works on a good day.

## Style

Read the surrounding code and match it. Two things are more consistent here than
in most codebases and are worth copying:

**Comments explain why, not what.** Especially when the obvious implementation
is wrong. If you fix a subtle bug, leave the sentence that stops the next person
reintroducing it.

**Dashboard work follows the design system** in `web/.interface-design/system.md`
and `web/DESIGN-README.md`. Colour only where it carries belief state, borders
not shadows, state shown as shape first so it survives a greyscale screenshot,
and full Tailwind class names, never interpolated, because Tailwind will not
generate them.

## Commits and pull requests

- One logical change per PR. A drive-by reformat inside a bugfix makes the fix
  unreviewable.
- Write the commit message for someone reading `git log` in a year.
- Say what you tested. "All suites pass" is fine; silence is not.
- Update `CHANGELOG.md` if the change affects someone using OMEM. Engineering
  detail goes in `CHANGELOG-dev-notes.md` instead.

## Reporting bugs

Include the version, what you ran, what happened, and what you expected. If it
involves belief state, the assertion ids and the `/why` output are worth more
than a description.

**Security issues do not go in the issue tracker.** See [SECURITY.md](SECURITY.md).

## What is most useful right now

- **Breakage reports.** Early software, used in ways we have not tried.
- **The five-minute experience.** If the quickstart did not work, that is a bug
  in the quickstart.
- **TypeScript SDK parity.** It lags the Python SDK; `sdk/typescript/test_parity.mjs`
  runs against a real server and will tell you what is missing.
- **Docs.** Especially anywhere the reason for a design decision is not written
  down.

## Licence

Contributions are licensed under the MIT License, the same as the project. See
[LICENSE](LICENSE).
