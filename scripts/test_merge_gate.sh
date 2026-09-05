#!/usr/bin/env bash
#
# test_merge_gate.sh — thin wrapper around `merge-gate.sh --self-test`.
#
# The real fixtures + assertions live in scripts/merge-gate.sh under the
# `--self-test` flag (mirroring scripts/audit-p2s.sh --self-test). Keeping
# the fixtures inline with the code they test means adding a new priority
# rule and its test happens in one file.
#
# This wrapper exists so `scripts/test_*.sh` is a discoverable convention
# for running our test suite — `for t in scripts/test_*.sh; do bash "$t"; done`
# picks it up.
#
# Exit 0 on success, non-zero on any failing assertion.

set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
exec bash "$here/merge-gate.sh" --self-test
