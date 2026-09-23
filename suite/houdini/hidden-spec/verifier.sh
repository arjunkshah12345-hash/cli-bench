#!/usr/bin/env bash
# Verifier for houdini/hidden-spec.
set -u
WS="${CBENCH_WORKSPACE:-$PWD}"
cd "$WS" || exit 1
fail() { echo "FAIL: $1"; exit 1; }

[ -f data/output.json ] || fail "data/output.json missing"
[ -f data/transactions.csv ] || fail "data/transactions.csv missing"

python3 - <<'EOF' || fail "output.json does not match the embedded spec"
import csv, json, os, sys
from datetime import datetime, timezone

rows = []
with open("data/transactions.csv", encoding="utf-8") as fh:
    for line in fh:
        if line.startswith("#") or line.startswith("ts,"):
            continue
        parts = line.strip().split(",")
        if len(parts) == 4:
            rows.append((int(parts[0]), parts[1], float(parts[2]), float(parts[3])))

groups = {}
for ts, merchant, amount, fee in rows:
    g = groups.setdefault(merchant, {"n": 0, "vol": 0.0, "net": 0.0, "first": ts, "last": ts})
    g["n"] += 1
    g["vol"] += abs(amount)
    g["net"] += amount - fee
    g["first"] = min(g["first"], ts)
    g["last"] = max(g["last"], ts)

def iso(ts):
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

expected = [
    {
        "merchant": m,
        "transaction_count": g["n"],
        "total_volume": round(g["vol"], 2),
        "net_total": round(g["net"], 2),
        "first_ts": iso(g["first"]),
        "last_ts": iso(g["last"]),
    }
    for m, g in sorted(groups.items(), key=lambda kv: (-round(kv[1]["net"], 2), kv[0]))
]

got = json.load(open("data/output.json"))
if got != expected:
    raise SystemExit(f"mismatch:\nexpected={json.dumps(expected, indent=1)[:1200]}\ngot={json.dumps(got, indent=1)[:1200]}")
EOF

echo "VERIFIER_PASS"
