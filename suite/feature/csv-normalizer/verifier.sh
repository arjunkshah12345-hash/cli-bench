#!/usr/bin/env bash
# Verifier for feature/csv-normalizer.
# Compares data/output.csv against an independent reference implementation
# run on data/input.csv. Shipped files (input.csv, SPEC.md) must be untouched.
set -u
WS="${CBENCH_WORKSPACE:-$PWD}"
cd "$WS" || exit 1
fail() { echo "FAIL: $1"; exit 1; }

[ -f data/output.csv ] || fail "data/output.csv missing"
[ -f data/input.csv ] || fail "data/input.csv missing (was it deleted?)"
[ -f data/SPEC.md ] || fail "data/SPEC.md missing (was it deleted?)"

# Reference output: generator (seed.py) + reference live in the verifier's own dir
HERE="$(cd "$(dirname "$0")" && pwd)"
python3 - "$HERE" <<'EOF' || fail "reference computation failed"
import csv, sys, os
sys.path.insert(0, sys.argv[1])
from reference_impl import normalize

ws = os.environ.get("CBENCH_WORKSPACE", ".")
with open(os.path.join(ws, "data/input.csv"), newline="", encoding="utf-8") as fh:
    rows = list(csv.reader(fh))[1:]
expected = normalize(rows)

with open(os.path.join(ws, "data/output.csv"), newline="", encoding="utf-8") as fh:
    got = list(csv.reader(fh))

if not got:
    raise SystemExit("output is empty")
if got[0] != ["id", "name", "email", "signup_date", "plan", "mrr_usd"]:
    raise SystemExit(f"bad header: {got[0]}")
body_got, body_exp = got[1:], expected
if len(body_got) != len(body_exp):
    raise SystemExit(f"row count: got {len(body_got)}, expected {len(body_exp)}")
diff = 0
for i, (g, e) in enumerate(zip(body_got, body_exp)):
    if g != e:
        diff += 1
        if diff <= 5:
            print(f"MISMATCH row {i+2}: got={g} expected={e}", file=sys.stderr)
if diff:
    raise SystemExit(f"{diff} mismatched rows")
EOF

echo "VERIFIER_PASS"
