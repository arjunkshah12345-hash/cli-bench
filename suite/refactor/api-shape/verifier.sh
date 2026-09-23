#!/usr/bin/env bash
# Verifier for refactor/api-shape.
set -u
WS="${CBENCH_WORKSPACE:-$PWD}"
cd "$WS" || exit 1
fail() { echo "FAIL: $1"; exit 1; }

# 1. New API names importable, old names gone (checked in tests too, but verify directly)
python3 - <<'EOF' || fail "new API names not importable or old names still present"
import sys
sys.path.insert(0, ".")
import pkg.geometry as g
for new in ("rect_area", "rect_perimeter", "circle_area", "circle_circumference"):
    assert callable(getattr(g, new)), new
for old in ("calc_rect_area", "calc_rect_perimeter", "calc_circle_area", "calc_circle_circumference"):
    assert not hasattr(g, old), old
EOF

# 2. No stale references to old names anywhere in shipped modules
if grep -rn "calc_" --include="*.py" pkg sites | grep -v "^Binary"; then
  fail "stale calc_* reference remains"
fi

# 3. Full test suite passes
python3 -m pytest tests/ -q || fail "test suite failed"

# 4. CLI call site works
OUT=$(python3 sites/e_cli.py 3 4) || fail "CLI failed"
echo "$OUT" | grep -q "area=12" || fail "CLI output wrong: $OUT"
echo "$OUT" | grep -q "perimeter=14" || fail "CLI output wrong: $OUT"

echo "VERIFIER_PASS"
