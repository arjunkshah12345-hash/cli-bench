#!/usr/bin/env bash
# Verifier for data/log-analysis.
set -u
WS="${CBENCH_WORKSPACE:-$PWD}"
cd "$WS" || exit 1
fail() { echo "FAIL: $1"; exit 1; }

[ -f answers.json ] || fail "answers.json missing"
[ -f data/app.log ] || fail "data/app.log missing (was it deleted?)"
[ -f QUESTIONS.md ] || fail "QUESTIONS.md missing (was it deleted?)"

python3 - <<'EOF' || fail "answers do not match the log"
import json
from collections import Counter

with open("data/app.log", encoding="utf-8") as fh:
    events = [json.loads(line) for line in fh if line.strip()]

reqs = [e for e in events if e.get("context") == "request"]
errors = [e for e in reqs if e.get("level") == "ERROR"]
codes = Counter(str(e["http_status"]) for e in errors if "http_status" in e)
lats = sorted(e["latency_ms"] for e in reqs)
import math
rank = max(1, math.ceil(0.95 * len(lats)))
p95 = float(lats[rank - 1])
minutes = Counter(e["ts"][:16] for e in reqs)
busiest = minutes.most_common(1)[0][0]
slowest = max(reqs, key=lambda e: e["latency_ms"])["request_id"]
top = Counter(e["endpoint"] for e in reqs).most_common(1)[0][0]

expected = {
    "total_requests": len(reqs),
    "error_rate": round(len(errors) / len(reqs), 4),
    "top_endpoint": top,
    "p95_latency_ms": round(p95, 2),
    "error_counts_by_code": dict(codes),
    "busiest_minute": busiest,
    "slowest_request_id": slowest,
}

got = json.load(open("answers.json"))
problems = []
for k, v in expected.items():
    if got.get(k) != v:
        problems.append(f"{k}: got {got.get(k)!r}, expected {v!r}")
extra = set(got) - set(expected)
if extra:
    problems.append(f"extra keys: {sorted(extra)}")
if problems:
    raise SystemExit("\n".join(problems))
EOF

echo "VERIFIER_PASS"
