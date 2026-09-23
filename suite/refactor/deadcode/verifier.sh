#!/usr/bin/env bash
# Verifier for refactor/deadcode.
# Pass requires:
#   1. the shipped test suite passes (behavior preserved)
#   2. dead functions are gone from app.py
#   3. live functions remain defined
set -u
WS="${CBENCH_WORKSPACE:-$PWD}"
cd "$WS" || exit 1
fail() { echo "FAIL: $1"; exit 1; }

# Dead functions must be gone (grep for def + a distinctive internal token)
if grep -qE "def\s+legacy_multiply" app.py; then fail "legacy_multiply still defined"; fi
if grep -qE "def\s+circle_area_v2" app.py; then fail "circle_area_v2 still defined"; fi
if grep -qE "def\s+unused_util" app.py; then fail "unused_util still defined"; fi

# Live functions must remain
for fn in "def add" "def sub" "def mul" "def circle_area" "def mean" "def stddev"; do
  grep -qE "$fn" app.py || fail "missing $fn after pruning"
done

# Tests must be unmodified in spirit: they must still exist and pass
[ -f tests/test_app.py ] || fail "tests/test_app.py missing"
python3 -m pytest tests/ -q || fail "test suite failed"

echo "VERIFIER_PASS"
