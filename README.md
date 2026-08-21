# CLA signatures

This orphan branch stores CLA signatures and nothing else. It is written by
`.github/workflows/cla.yml` (contributor-assistant), which appends a record to
`signatures/cla.json` when a contributor comments the signature line on a pull
request.

Do not protect this branch: the action has to push to it, and a protection rule
makes every CLA check fail with "Branch cla-signatures not found".

Do not merge this branch into main. It shares no history with it.
