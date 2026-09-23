"""Seed materializer for feature/rate-limiter.

The task interface is fixed, so seeds vary a starter config that the agent may
(or may not) consult. Seed 0 is the canonical baseline.
"""

import json
import os

PARAMS = {
    0: {"refill_policy": "continuous", "initial_tokens": "capacity"},
    1: {"refill_policy": "continuous", "initial_tokens": "capacity"},
    2: {"refill_policy": "continuous", "initial_tokens": "capacity"},
}


def main() -> None:
    seed = int(os.environ.get("CBENCH_SEED", "0"))
    params = PARAMS.get(seed, PARAMS[0])
    with open("starter_config.json", "w", encoding="utf-8") as fh:
        json.dump(params, fh, indent=2)


if __name__ == "__main__":
    main()
