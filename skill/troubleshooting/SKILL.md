---
name: troubleshooting
description: Living runbook of known infra issues that block Builder/Review GAs (Origami install fails, sim boot times out, ImageMagick missing, etc.). Each entry: symptom, evidence signature, workaround, verification. Referenced by Builder/Review pre-flight checks. Any agent that ships a fix appends the entry.
metadata:
  type: reference
---

# troubleshooting — known infra blockers

Living document. Add an entry whenever a fix ships for a runner-level failure
that blocked the Builder or Review GA. Builder and Review pre-flight checks
read this file before starting real work — an entry here is how future runs
skip the same wall.

Scope: infra only. Product bugs go through the normal issue flow. If a
failure is caused by something under the runner's control (runner image
drift, missing tool, upstream URL rot, license expiration, sim boot
flakiness) it belongs here.

## Format

Each entry is:

### <one-line symptom>
- **Signature**: how to detect (log lines, exit codes, error text)
- **Cause**: what broke (upstream change, runner image drift, license expiration, etc.)
- **Workaround**: the fix — a diff, a step to run, a config to add
- **Verified**: SHA of the fix PR + date

Keep entries short. The signature block should be greppable — paste the
actual log line, not a paraphrase.

## Example entry

### Origami installer fetches an expired FBCDN URL
- **Signature**: `hdiutil attach` fails, log shows 403 from scontent-*.xx.fbcdn.net
- **Cause**: Sparkle appcast URLs carry `&oe=<hex>` expiration signatures. If the runner reaches the URL after expiration, download fails.
- **Workaround**: re-fetch the appcast for a fresh signed URL. Never cache the DMG URL between workflow runs.
- **Verified**: (PR TBD, date TBD)
