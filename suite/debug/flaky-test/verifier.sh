#!/usr/bin/env bash
# Verifier for debug/flaky-test.
# The fixed suite must pass REPEATEDLY, not just once.
set -u
WS="${CBENCH_WORKSPACE:-$PWD}"
cd "$WS" || exit 1
fail() { echo "FAIL: $1"; exit 1; }

[ -f jobs.py ] || fail "jobs.py missing"
[ -f tests/test_pipeline.py ] || fail "tests/test_pipeline.py missing"

for i in $(seq 1 15); do
  if ! python3 -m pytest tests/ -q -x >/dev/null 2>&1; then
    fail "test suite failed on repetition $i (fix must be reliable, not lucky)"
  fi
done

echo "VERIFIER_PASS (15/15 repetitions green)"
