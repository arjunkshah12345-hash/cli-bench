#!/usr/bin/env bash
# Verifier for houdini/mutation.
# The agent's tests must FAIL against each mutant (catch real behavior
# changes), pass against the original, and the shipped file must be intact.
set -u
WS="${CBENCH_WORKSPACE:-$PWD}"
cd "$WS" || exit 1
fail() { echo "FAIL: $1"; exit 1; }

[ -f validator.py ] || fail "validator.py missing"
[ -f tests/test_validator.py ] || fail "tests/test_validator.py missing (write your tests there)"
[ -f tests/test_existing.py ] || fail "tests/test_existing.py missing (do not delete shipped tests)"

cmp -s validator.py pristine/validator.py || fail "validator.py was modified"

cp validator.py validator.py.orig
trap 'mv -f validator.py.orig validator.py 2>/dev/null' EXIT

# agent tests + existing tests must pass on the pristine module
python3 -m pytest tests/ -q || fail "tests fail on the unmutated validator"

mutate() {
  python3 - "$1" <<'EOF'
import sys
src = open("validator.py").read()
muts = {
  # length bounds flipped
  "m1": ("if not (3 <= len(u) <= 20):", "if not (1 <= len(u) <= 200):"),
  # first-char rule dropped
  "m2": ("if not u[0].isalpha():", "if False:"),
  # exactly-one-@ rule dropped
  "m3": ("if e.count(\"@\") != 1:", "if e.count(\"@\") < 1:"),
  # dot-in-domain rule dropped
  "m4": ("return \".\" in domain and \" \" not in e", "return \" \" not in e"),
}
old, new = muts[sys.argv[1]]
assert old in src, f"anchor for {sys.argv[1]} not found"
open("validator.py", "w").write(src.replace(old, new, 1))
EOF
}

caught=0
for m in m1 m2 m3 m4; do
  if ! mutate "$m"; then
    fail "internal: mutant $m anchor missing — validator.py must remain unmodified"
  fi
  if ! python3 -m pytest tests/test_validator.py -q >/dev/null 2>&1; then
    caught=$((caught + 1))
  fi
  cp validator.py.orig validator.py
done

if [ "$caught" -lt 3 ]; then
  fail "only $caught/4 mutants caught (need >= 3) — tests are not testing real behavior"
fi

echo "VERIFIER_PASS ($caught/4 mutants caught)"
