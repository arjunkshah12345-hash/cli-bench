"""Seed materializer for tooling/test-gen (uniform across seeds in 1.0.0)."""

import os


def main() -> None:
    _ = int(os.environ.get("CBENCH_SEED", "0"))


if __name__ == "__main__":
    main()
