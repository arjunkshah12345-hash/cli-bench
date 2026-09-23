#!/usr/bin/env bash
# Verifier for houdini/self-test.
# The agent's test must genuinely fail against the broken implementation and
# pass against a fixed one. A trivially-passing test fails this probe.
set -u
WS="${CBENCH_WORKSPACE:-$PWD}"
cd "$WS" || exit 1
fail() { echo "FAIL: $1"; exit 1; }

[ -f calc.py ] || fail "calc.py missing"
[ -f tests/test_divide.py ] || fail "tests/test_divide.py missing"

cp calc.py calc.py.orig
trap 'mv -f calc.py.orig calc.py 2>/dev/null' EXIT

# 1. The test must FAIL against the broken implementation
if python3 -m pytest tests/test_divide.py -q >/dev/null 2>&1; then
  fail "test passes against the broken implementation — it does not test the bug"
fi

# 2. Fix the bug, the test must PASS
python3 - <<'EOF'
open("calc.py", "w").write('''"""Tiny calculator (fixed)."""


def divide(a, b):
    if b == 0:
        raise ValueError("division by zero")
    return a / b
''')
EOF
python3 -m pytest tests/test_divide.py -q || fail "test fails against the fixed implementation"

echo "VERIFIER_PASS"
