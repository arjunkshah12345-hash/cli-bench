"""Seed materializer for debug/wrong-answer.

v1.0.0 ships one bug shape; seeds re-materialize the same instance so the
runner's n=3 still measures trial variance. A per-seed bug table ships in
suite 1.1.
"""

import os


def main() -> None:
    seed = int(os.environ.get("CBENCH_SEED", "0"))
    # placeholder: uniform across seeds in 1.0.0
    _ = seed


if __name__ == "__main__":
    main()
