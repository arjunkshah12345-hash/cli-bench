#!/usr/bin/env bash
# Verifier for docs/api-ref — mechanical accuracy checks (the LLM-judge
# quality score is computed separately; this gate is objective).
set -u
WS="${CBENCH_WORKSPACE:-$PWD}"
cd "$WS" || exit 1
fail() { echo "FAIL: $1"; exit 1; }

[ -f API.md ] || fail "API.md missing"
[ -f library.py ] || fail "library.py missing (do not delete it)"

python3 - <<'EOF' || fail "API.md accuracy checks failed"
import inspect
import sys

sys.path.insert(0, ".")
import library

text = open("API.md", encoding="utf-8").read()
problems = []

public = [
    "chunk_list",
    "flatten",
    "pluralize",
    "truncate_chars",
    "valid_identifier",
]

for fn in public:
    obj = getattr(library, fn)
    if fn not in text:
        problems.append(f"{fn}: not documented")
        continue
    for param in inspect.signature(obj).parameters:
        if param not in text:
            problems.append(f"{fn}: parameter {param!r} not mentioned")

# exception accuracy
if "ValueError" not in text:
    problems.append("ValueError not mentioned (chunk_list/truncate_chars raise it)")

# example blocks exist
if "```" not in text:
    problems.append("no code examples found")

if problems:
    raise SystemExit("\n".join(problems))
EOF

echo "VERIFIER_PASS"
