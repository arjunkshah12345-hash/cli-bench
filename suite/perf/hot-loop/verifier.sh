#!/usr/bin/env bash
# Verifier for perf/hot-loop.
# Correctness tests + relative speed: agent impl must be >= 10x faster than a
# naive reference run in THIS process on the same machine. No absolute-time
# flakiness: the ratio is the test.
set -u
WS="${CBENCH_WORKSPACE:-$PWD}"
cd "$WS" || exit 1
fail() { echo "FAIL: $1"; exit 1; }

[ -f matrix_ops.py ] || fail "matrix_ops.py missing"
[ -f tests/test_correctness.py ] || fail "tests missing"

# stdlib-only constraint
if grep -E "^\s*(import|from)\s+(numpy|scipy|numba|torch|jax)" matrix_ops.py; then
  fail "non-stdlib import detected in matrix_ops.py"
fi

# public API preserved
python3 - <<'EOF' || fail "public signature changed"
import inspect
import matrix_ops
sig = inspect.signature(matrix_ops.count_pairs_within)
assert list(sig.parameters) == ["points", "r"], sig
EOF

# 1. Behavior preserved
python3 -m pytest tests/ -q || fail "correctness tests failed"

# 2. Adversarial equivalence: randomized outputs must match a naive reference
python3 - <<'EOF' || fail "equivalence check failed"
import json
import random
from matrix_ops import count_pairs_within

def naive(points, r):
    n = len(points); c = 0; r2 = r * r
    for i in range(n):
        xi, yi = points[i]
        for j in range(i + 1, n):
            dx = points[j][0] - xi; dy = points[j][1] - yi
            if dx * dx + dy * dy <= r2: c += 1
    return c

rng = random.Random(777)
for trial in range(6):
    n = rng.randrange(5, 180)
    pts = [(rng.uniform(-5, 5), rng.uniform(-5, 5)) for _ in range(n)]
    if trial % 2:  # clustered / duplicate-heavy case
        base = [(rng.uniform(-2, 2), rng.uniform(-2, 2)) for _ in range(3)]
        pts = [rng.choice(base) for _ in range(n)]
    r = rng.uniform(0.2, 2.5)
    got, exp = count_pairs_within(pts, r), naive(pts, r)
    assert got == exp, f"trial {trial}: got {got}, expected {exp} (n={n}, r={r:.2f})"
EOF

# 3. Speed: >= 10x vs naive reference on this machine, 3 dataset shapes
python3 - <<'EOF' || fail "not fast enough (need >= 10x vs naive)"
import json, math, random, time
from matrix_ops import count_pairs_within

def naive(points, r):
    n = len(points); c = 0; r2 = r * r
    for i in range(n):
        xi, yi = points[i]
        for j in range(i + 1, n):
            dx = points[j][0] - xi; dy = points[j][1] - yi
            if dx * dx + dy * dy <= r2: c += 1
    return c

cfg = {"n_uniform": 3000, "n_clustered": 3000, "n_gridded": 2000,
       "r_uniform": 0.35, "r_clustered": 0.6, "r_gridded": 0.7, "clusters": 7}
try:
    cfg.update(json.load(open("speedcheck_config.json")))
except Exception:
    pass

rng = random.Random(31337)
uniform = [(rng.uniform(0, 100), rng.uniform(0, 100)) for _ in range(cfg["n_uniform"])]
centers = [(rng.uniform(0, 100), rng.uniform(0, 100)) for _ in range(cfg["clusters"])]
clustered = []
while len(clustered) < cfg["n_clustered"]:
    cx, cy = rng.choice(centers)
    clustered.append((cx + rng.gauss(0, 1.5), cy + rng.gauss(0, 1.5)))
gridded = [(float(x), float(y)) for x in range(0, 1000) for y in range(0, 1000)]
rng.shuffle(gridded)
gridded = gridded[: cfg["n_gridded"]]

datasets = [
    ("uniform", uniform, cfg["r_uniform"]),
    ("clustered", clustered, cfg["r_clustered"]),
    ("gridded", gridded, cfg["r_gridded"]),
]

# correctness cross-check on a sample of each dataset first
for name, pts, r in datasets:
    sample = pts[:200]
    assert count_pairs_within(sample, r) == naive(sample, r), f"mismatch on {name} sample"

# warm both, then time
count_pairs_within(uniform[:500], cfg["r_uniform"]); naive(uniform[:500], cfg["r_uniform"])
ratios = []
for name, pts, r in datasets:
    t0 = time.perf_counter(); fast = count_pairs_within(pts, r); t_fast = time.perf_counter() - t0
    t0 = time.perf_counter(); slow = naive(pts, r); t_slow = time.perf_counter() - t0
    assert fast == slow, f"wrong count on {name}: {fast} != {slow}"
    ratios.append(t_slow / t_fast)
    print(f"  {name}: {t_slow:.3f}s naive vs {t_fast:.4f}s optimized = {t_slow/t_fast:.1f}x")

worst = min(ratios)
if worst < 10.0:
    raise SystemExit(f"worst-case speedup {worst:.1f}x < 10x")
EOF

echo "VERIFIER_PASS"
