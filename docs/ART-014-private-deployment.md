PROVENANCE

  artifact id:           ART-014
  title:                 The instrument on the outside wall — making the
                         dashboard deployment truly private
  source discipline:     science (anomaly detection / signal analysis)
  receiving discipline:  engineering (IT leadership — the CIO)
  translating persona:   Steve Jobs — declared stylistic translation lens
  orchestrator:          Jacob
  version:               v1.1
  status:                translated
  created / updated:     2026-05-21

---

## How to read this artifact

A scientist built something. An engineer must now place a lock on it. Between
those two disciplines sits a translation, and the persona is the translator —
a declared voice, nothing more. The `From:` line in the email below is part of
that stylistic device; it is not real correspondence. The technical content is
exact. Jacob, as orchestrator, decides what to forward and signs it himself.

Everything Dustin needs is in the email. Everything Jacob needs to act on is in
the two short sections after it.

---

## The email

```
From:    Steve Jobs <steve@apple.com>
To:      Dustin <dustin@[company-domain]>
Cc:      Jacob
Subject: The instrument is on the outside wall
Date:    2026-05-21
```

Dustin —

I want to tell you how this got here, because the story *is* the fix. Skip the
story and you'll patch the wrong thing.

A scientist built an instrument. Not brass and glass — code. It watches
something nobody can see directly: the drift in our spam rate, the precise
moment the rhythm of the data breaks and an anomaly surfaces. He built it
carefully. He kept the lab notebook locked — the repository is private, the
method is ours.

Then he did the natural thing, the *right* thing. An instrument no one can read
is useless, so he mounted the readout on a wall where the team could watch it.
One command. GitHub Pages. The dashboard went live, and it works beautifully.

Here is the turn in the story.

He mounted the readout on the correct wall — but the wrong *side* of it. GitHub
Pages is the **outside** wall of the building. The locked notebook is inside.
So today we have a private notebook sitting in a sealed room, and the live
readout from it is bolted to the street-facing wall, where anyone walking past
can stop and read our numbers. The repository being private protects the
notebook. It was never going to protect the wall. Those are two different
objects, and we quietly treated them as one. That assumption is the leak.

Now, the obvious patch: put a password on the page. Don't. A shared password is
not a lock — it's a sticky note on a glass door. One password for everyone means
you cannot say *who* read the numbers, you cannot revoke one person without
resetting all of them, and the first time it lands in a chat thread it belongs
to the world. That is not security. It is the *feeling* of security, and the
feeling is the dangerous part, because once we have it we stop looking at the
real wall.

Here is what we actually want — and you already know it, because it's how every
other system here already works: a person walks up, signs in with their normal
company credentials, and the system knows exactly who they are. They leave the
company, and they lose the dashboard the same hour they lose their email. That
is the entire requirement. Everything else is plumbing.

Three doors lead there:

  **Door 1 — Make the GitHub wall a private wall.**
  If we're on GitHub Enterprise Cloud, a Pages site can be set to Private:
  visible only to people with repo access, gated at GitHub login. Smallest
  change — the build pipeline never moves. But it leans on GitHub identity, the
  page still hangs on GitHub's public building, and there's no VPN boundary.
  A good *stopgap*. Not the destination.

  **Door 2 — Move the readout onto a wall we own.**
  The dashboard is just a folder of static files. Keep the build exactly as it
  is and change only the final step: instead of publishing to GitHub Pages,
  publish that folder to an internal server behind the VPN, or to static hosting
  in our own cloud tenant. This is the only door that makes "needs the VPN" a
  true sentence — because the wall is ours.

  **Door 3 — Put a doorman in front of it.**
  An identity-aware proxy — Cloudflare Access, Entra Application Proxy, Google
  IAP — forces sign-in against our corporate identity provider before a single
  byte of the page loads. Real per-user identity. Real revocation. A real audit
  trail of who looked and when.

My read: **Door 2 plus Door 3.** Keep the build, move the readout onto a wall we
own, put the company sign-in in front of it. If we already have GitHub
Enterprise Cloud, take Door 1 this week as a stopgap while 2 and 3 are stood up.

And hear this clearly: the work is *small*. The instrument is fine. The science
is fine. The build does not change — it is one folder of files and one deploy
step. We are not rebuilding anything. We are deciding which wall the readout
hangs on and who holds the key. That is a decision, not a project.

The three questions only you can answer:

  1. Are we on GitHub Enterprise Cloud?
  2. Internal server, or our own cloud tenant?
  3. VPN, identity provider, or both?

Answer those and the deploy step can be rewired the same day.

The instrument was never the problem. We just hung it facing the street. Let's
turn it around.

— Steve

---

## What Jacob acts on

- Build/deploy lives in `.github/workflows/dashboard.yml`, triggered on
  data-file changes pushed to `main`.
- The workflow runs `python -m spam_detection`, which generates
  `docs/index.html` — the dashboard.
- Deployment currently uses `actions/upload-pages-artifact` +
  `actions/deploy-pages`: the public GitHub Pages path. **This single step is
  the one that changes under Door 2.**
- The dashboard embeds spam-rate data, so the real exposure is the *data*, not
  just a page. Treat it accordingly.

## Closing reflection

A scientist's instinct is to publish the reading. An engineer's instinct is to
ask who can stand at the dial. Neither is wrong — the gap between them is just a
wall with two sides. Name the two sides apart, and the fix names itself: every
time something is "published," ask which wall it landed on, and who is allowed
to walk up to it.
