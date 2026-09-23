#!/usr/bin/env bash
# Verifier for feature/rate-limiter.
set -u
WS="${CBENCH_WORKSPACE:-$PWD}"
cd "$WS" || exit 1
fail() { echo "FAIL: $1"; exit 1; }

[ -f rate_limiter.py ] || fail "rate_limiter.py missing"
python3 -m pytest tests/ -q || fail "test suite failed"

echo "VERIFIER_PASS"
