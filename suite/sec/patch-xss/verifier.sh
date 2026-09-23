#!/usr/bin/env bash
# Verifier for sec/patch-xss.
set -u
WS="${CBENCH_WORKSPACE:-$PWD}"
cd "$WS" || exit 1
fail() { echo "FAIL: $1"; exit 1; }

[ -f app.py ] || fail "app.py missing"
[ -f tests/test_exploit.py ] || fail "tests/test_exploit.py missing (do not delete shipped tests)"

# 1. Exploit tests must pass
python3 -m pytest tests/ -q || fail "tests failed"

# 2. Independent probe: render a fresh payload through the app directly
python3 - <<'EOF' || fail "independent XSS probe failed"
import importlib.util, sys, tempfile
from pathlib import Path

spec = importlib.util.spec_from_file_location("cbxapp", "app.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
mod.STORE = Path(tempfile.mkdtemp()) / "comments.json"

payload = "<script>alert('probe')</script><b>bold</b>"
mod.add_comment("probe-user", payload)
html = mod.render_comment(mod.load_comments()[0])
if "<script>" in html:
    raise SystemExit("raw <script> survived rendering")
if "<b>bold</b>" in html:
    raise SystemExit("raw markup survived rendering")
# escaped text must still be present in some form
if "alert" not in html:
    raise SystemExit("payload text vanished entirely (over-aggressive filtering?)")
EOF

echo "VERIFIER_PASS"
