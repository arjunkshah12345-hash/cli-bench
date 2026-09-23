#!/usr/bin/env bash
# CI matrix for this repository.
# Each cell runs pytest against a FRESH copy of the tracked project dirs,
# exactly as CI would after a clean checkout.
set -u
cd "$(dirname "$0")/.." || exit 1
fail() { echo "CI: FAIL $1"; exit 1; }

[ -f pyproject.toml ] || fail "pyproject.toml missing"

overall=0
run_cell() {
  local name="$1"
  local marker_expr="$2"
  echo "--- cell: $name (markers: $marker_expr)"
  local tmp
  tmp="$(mktemp -d)"
  cp -r src tests ci "$tmp/" 2>/dev/null
  ( cd "$tmp" && python3 -m pytest tests -q -m "$marker_expr" ) >"$tmp/pytest.log" 2>&1
  local rc=$?
  tail -5 "$tmp/pytest.log"
  rm -rf "$tmp"
  if [ $rc -ne 0 ]; then
    overall=1
    echo "--- cell $name FAILED"
  fi
}

run_cell base-a "unit or api"
run_cell full-a "unit or api or export"
run_cell base-b "unit or api"
run_cell full-b "unit or api or export"

if [ $overall -ne 0 ]; then fail "matrix red"; fi
echo "CI: all cells green"
