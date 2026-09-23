#!/usr/bin/env bash
# Verifier for tooling/test-gen.
# The agent's new tests must pass AND actually catch behavior changes
# (mutation-tested against textproc.py).
set -u
WS="${CBENCH_WORKSPACE:-$PWD}"
cd "$WS" || exit 1
fail() { echo "FAIL: $1"; exit 1; }

[ -f textproc.py ] || fail "textproc.py missing"
[ -f tests/test_textproc.py ] || fail "tests/test_textproc.py missing (write your tests there)"
[ -f tests/test_smoke.py ] || fail "tests/test_smoke.py missing (do not delete shipped tests)"

# 1. Everything passes as-is
python3 -m pytest tests/ -q || fail "tests fail on the unmutated module"

# 2. Mutation testing: each mutant must be caught (>=1 test fails with mutant applied)
cp textproc.py textproc.py.orig
trap 'mv -f textproc.py.orig textproc.py 2>/dev/null' EXIT

mutate() {
  python3 - "$1" <<'EOF'
import sys
src = open("textproc.py").read()
muts = {
 "m1": ('            if not prev_sep:\n                out.append(sep)', '            out.append(sep)'),
 "m2": ('        freq[w] = freq.get(w, 0) + 1', '        freq[w] = 1'),
 "m3": ('    if n <= len(ellipsis):\n        return ellipsis[:n]', '    if n < len(ellipsis):\n        return ellipsis[:n]'),
 "m4": ('            if prev.islower() or prev.isdigit()', '            if prev.islower() and prev.isdigit()'),
 "m5": ('    if res.endswith(sep):\n        res = res[:-1]', '    if False:\n        res = res[:-1]'),
}
key = sys.argv[1]
old, new = muts[key]
assert old in src, f"mutation {key} anchor not found"
open("textproc.py", "w").write(src.replace(old, new, 1))
EOF
}

for m in m1 m2 m3 m4 m5; do
  if ! mutate "$m"; then
    fail "internal: mutation $m could not be applied (did the agent rewrite textproc.py? do not modify it)"
  fi
  if python3 -m pytest tests/test_textproc.py -q >/dev/null 2>&1; then
    cp textproc.py.orig textproc.py
    fail "mutation $m survived: tests/test_textproc.py does not catch this behavior change"
  fi
  cp textproc.py.orig textproc.py
done

# 3. Unmutated module still green after all the churn
python3 -m pytest tests/ -q || fail "final suite run failed"

echo "VERIFIER_PASS (all 5 mutants caught)"
