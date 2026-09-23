"""Seed materializer for debug/flaky-test.

Seeds vary the concurrency shape and the race window width, so the flake
profile differs materially across seeds.
"""

import json
import os

PARAMS = {
    0: {"workers": 12, "jobs": 12, "bookkeeping_latency": 0.0003, "scatter_us": 100},
    1: {"workers": 8, "jobs": 16, "bookkeeping_latency": 0.0006, "scatter_us": 60},
    2: {"workers": 16, "jobs": 12, "bookkeeping_latency": 0.0002, "scatter_us": 140},
}


def main() -> None:
    seed = int(os.environ.get("CBENCH_SEED", "0"))
    params = PARAMS.get(seed, PARAMS[0])
    with open("config.json", "w", encoding="utf-8") as fh:
        json.dump(params, fh, indent=2)


if __name__ == "__main__":
    main()
