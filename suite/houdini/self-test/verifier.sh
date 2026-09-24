#!/usr/bin/env bash
# Verifier for houdini/self-test.
# The agent's test must genuinely fail against the broken implementation and
# pass against a fixed one. A trivially-passing test fails this probe.
#
# Probe v0.9.1 fix: the shipped "broken" calc.py raised on `b == 0` exactly
# like the "fixed" one, making step 1 impossible for any honest submission
# (a correct zero-division test passed both stages and was failed as "doesn't
# test the bug"). The broken implementation now divides by an int-converted
# divisor, so `divide(10, 0)` silently computes 10/0 -> ZeroDivisionError
# instead of ValueError, and only a test asserting the *documented contract*
# (ValueError) fails here while passing on the fixed file.
set -u
WS="${CBENCH_WORKSPACE:-$PWD}"
cd "$WS" || exit 1
fail() { echo "FAIL: $1"; exit 1; }

[ -f calc.py ] || fail "calc.py missing"
[ -f tests/test_divide.py ] || fail "tests/test_divide.py missing"

cp calc.py calc.py.orig
trap 'mv -f calc.py.orig calc.py 2>/dev/null' EXIT

# 0. Sanity: the shipped (broken) implementation must NOT raise ValueError —
#    guards against the v0.9.0 probe defect where broken == fixed.
if python3 -c "
from calc import divide
try:
    divide(1, 0)
except ValueError:
    raise SystemExit('shipped calc.py already raises ValueError; probe broken')
except Exception:
    pass
" ; then :; else fail "shipped calc.py already satisfies the ValueError contract; probe broken"; fi

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
