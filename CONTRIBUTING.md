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

## Sign your commits off

One line per commit, which `git commit -s` adds for you:

```
Signed-off-by: Your Name <your.email@example.com>
```

That is the [Developer Certificate of Origin](DCO.md): you are certifying that
you wrote the patch, or otherwise have the right to send it. Nothing to sign, no
bot, no account, and CI checks it.

Forgot? `git commit --amend -s` for the last commit, `git rebase --signoff main`
for a branch, then force-push.

This project asked for a CLA until recently. It was dropped because its stated
justification did not hold: MIT already grants the right to sublicense and sell,
so a commercial product built on contributed code never needed one. What a CLA
actually buys is the option to relicense *away* from MIT later — which this
project has committed not to do. [DCO.md](DCO.md) has the full reasoning.

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
python run_tests.py
```

Use the runner rather than a shell loop over `tests*.py`. It is what CI runs,
and it reports the thing a loop cannot: which suites **skipped**. A suite with
no PostgreSQL to talk to exits 0, so a loop prints nothing and looks exactly
like a pass. `run_tests.py` ends with a list headed "SKIPPED. These verified
NOTHING in this run", and returns non-zero if anything actually failed.

CI additionally runs everything against PostgreSQL and against encrypted
storage. If your change touches storage, run those locally:

```bash
OMEM_DATABASE_URL=postgresql://... python run_tests.py
OMEM_ENCRYPT_AT_REST=1 OMEM_MASTER_KEY=$(python3 -c 'import secrets;print(secrets.token_urlsafe(32))') python run_tests.py
```

Both are the full run, not a single suite: encrypting a column means every read
of it has to decrypt, and a missed read site fails somewhere other than the
suite that owns the column.

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

- **Sign off every commit** (`git commit -s`). CI fails the PR otherwise, and
  fixing it after the fact means a rebase and a force-push.
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
- **TypeScript SDK parity.** It lags the Python SDK. `cd sdk/typescript &&
  npm install && npm test` builds it and runs `test_parity.mjs` against a real
  server, which will tell you what is missing.
- **Docs.** Especially anywhere the reason for a design decision is not written
  down.

## Licence

Your contribution ships under the MIT License, the same as everything else here.
See [LICENSE](LICENSE). You keep the copyright in what you wrote — signing off
is a statement about provenance, not a transfer of ownership.

Worth knowing, because MIT is more permissive than people expect: it grants
anyone the right to *sublicense and sell*, so your contribution can end up in a
commercial product, including one built by this project. That is true of every
MIT project and is not something the DCO adds. What the project has committed to
is that **the core stays MIT** — it is not reserving a right to relicense it
later, which is precisely why there is no CLA. See [DCO.md](DCO.md).
