"""Seed materializer for perf/hot-loop: per-seed speed-check dataset params."""

import json
import os

PARAMS = {
    0: {
        "n_uniform": 3000,
        "n_clustered": 3000,
        "n_gridded": 2000,
        "r_uniform": 0.35,
        "r_clustered": 0.6,
        "r_gridded": 0.7,
        "clusters": 7,
    },
    1: {
        "n_uniform": 2600,
        "n_clustered": 3400,
        "n_gridded": 1800,
        "r_uniform": 0.4,
        "r_clustered": 0.5,
        "r_gridded": 0.6,
        "clusters": 9,
    },
    2: {
        "n_uniform": 3400,
        "n_clustered": 2600,
        "n_gridded": 2200,
        "r_uniform": 0.3,
        "r_clustered": 0.7,
        "r_gridded": 0.8,
        "clusters": 5,
    },
}


def main() -> None:
    seed = int(os.environ.get("CBENCH_SEED", "0"))
    params = PARAMS.get(seed, PARAMS[0])
    with open("speedcheck_config.json", "w", encoding="utf-8") as fh:
        json.dump(params, fh, indent=2)


if __name__ == "__main__":
    main()
