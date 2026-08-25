## What this changes

<!-- One or two sentences. If it fixes an issue, "Fixes #123". -->

## Why

<!-- Especially if the obvious implementation would have been wrong. That
     sentence is what stops the next person reintroducing the bug. -->

## How it was tested

<!-- "All suites pass" is fine. Silence is not. -->

```
cd server && python run_tests.py
```

## Checklist

- [ ] Every server suite passes
- [ ] New behaviour has a test that tries to break it, not one that proves it works on a good day
- [ ] `CHANGELOG.md` updated if this affects someone *using* OMEM (engineering detail goes in `CHANGELOG-dev-notes.md`)
- [ ] `cd web && npx tsc --noEmit` passes, if the dashboard changed
- [ ] Every commit is signed off (`git commit -s`) — see [DCO.md](../DCO.md)

### Design rules

Confirm the ones that apply — see [CONTRIBUTING.md](../CONTRIBUTING.md):

- [ ] The engine still never decides two claims contradict by reading them
- [ ] Model output and error text are still data, never instructions
- [ ] No new third-party runtime dependency in the server or Python SDK
- [ ] Nothing newly displayed is fabricated; unwired capabilities are labelled
- [ ] `server/omem_engine/` is unchanged (it is frozen and CI checks it byte-for-byte)
