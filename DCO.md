# Developer Certificate of Origin

OMEM uses the **Developer Certificate of Origin**, not a contributor licence
agreement. You certify that you wrote the patch, or have the right to send it,
by adding one line to your commit:

```
Signed-off-by: Your Name <your.email@example.com>
```

`git commit -s` adds it for you. There is nothing to sign, no bot to wait for,
no account anywhere, and you do it per commit rather than once per lifetime.

## Why this and not a CLA

This project used to ask for a CLA. The stated reason was that it kept a
commercial product possible without having to track down every past
contributor — and that reason does not survive contact with the licence.

MIT already grants the right to *use, copy, modify, merge, publish, distribute,
**sublicense**, and sell*. Anyone, this project included, can already build a
commercial product on MIT-licensed contributions; you keep the copyright notice
and that is the whole obligation. Nobody needs to be tracked down for that.

What a CLA actually buys is narrower: the right to relicense the project *away*
from MIT later, the way HashiCorp and Elastic moved to the BSL. That is a real
option and some projects want it. This one does not:
[CONTRIBUTING.md](CONTRIBUTING.md) says the core stays MIT, and a CLA reserving
the right to change that would have made the promise hollow.

So the CLA was charging contributors real friction — an unreviewed legal
document, a signature bot, a signature store — for an option this project had
publicly committed never to exercise. The one genuine thing it provided was the
assurance that contributors had the right to contribute what they sent. That is
exactly what the DCO provides, in the four clauses below, and nothing else.

## What you are certifying

The text below is the Developer Certificate of Origin, version 1.1, reproduced
verbatim. It is the same text used by the Linux kernel, Git, Docker and many
others. It may be copied but not changed, so it is quoted here rather than
paraphrased.

---

```
Developer Certificate of Origin
Version 1.1

Copyright (C) 2004, 2006 The Linux Foundation and its contributors.
1 Letterman Drive
Suite D4700
San Francisco, CA, 94129

Everyone is permitted to copy and distribute verbatim copies of this
license document, but changing it is not allowed.


Developer's Certificate of Origin 1.1

By making a contribution to this project, I certify that:

(a) The contribution was created in whole or in part by me and I
    have the right to submit it under the open source license
    indicated in the file; or

(b) The contribution is based upon previous work that, to the best
    of my knowledge, is covered under an appropriate open source
    license and I have the right under that license to submit that
    work with modifications, whether created in whole or in part
    by me, under the same license (unless I am permitted to submit
    under a different license), as indicated in the file; or

(c) The contribution was provided directly to me by some other
    person who certified (a), (b) or (c) and I have not modified
    it.

(d) I understand and agree that this project and the contribution
    are public and that a record of the contribution (including all
    personal information I submit with it, including my sign-off) is
    maintained indefinitely and may be redistributed consistent with
    this project or the open source license(s) involved.
```

---

## Practical notes

**Use a real name and a working address.** The sign-off is a statement you are
making, so it needs to identify you. Pseudonyms that you use consistently and
that reach you are fine; `anonymous@example.com` is not.

**It becomes part of the public record**, permanently — that is clause (d), and
it is the one people most often miss. Sign off with an address you are willing
to have in a git log forever.

**Forgot to sign off?** Amend the last commit with `git commit --amend -s`, or
fix a whole branch with
`git rebase --signoff main`, then force-push. The check will go green on the
next push; nothing needs to be reopened.

**Your contribution is MIT**, the same licence as the rest of the project. The
DCO is a statement about provenance, not a transfer of ownership: you keep the
copyright in what you wrote.
