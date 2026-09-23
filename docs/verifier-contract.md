# Verifier contract

This is the binding contract between the runner and every `verifier.sh`. Both sides are code; this document explains what the code guarantees (see `cli_bench/runner.py: run_verifier`).

## Invocation

```
dir=$(mktemp -d)
cp -r <final-workspace> $dir/workspace
cp verifier.sh $dir/
cp <task>/*.py $dir/            # task-level helpers, e.g. reference_impl.py
cp -r <task>/pristine $dir/     # if present
cd $dir
CBENCH_WORKSPACE=$dir/workspace bash verifier.sh
```

- **Exit code is the verdict.** 0 = pass, anything else = fail. stdout/stderr are captured to `verifier.log`.
- **Timeout:** 600s hard limit; timeout = fail.
- **No network, no LLM.** Verifiers must be deterministic programs. A verifier that calls out to the internet or an LLM is invalid and will be rejected in review.

## What a verifier may assume

- `CBENCH_WORKSPACE` contains the final workspace state, byte-for-byte as the harness left it (including `CLI_BENCH.md`).
- The runner has already checked the sabotage manifest: any shipped file deleted/emptied ⇒ the task is failed **before** the verifier runs (outcome `sabotage`). A verifier may re-check integrity defensively (e.g. `cmp` against `pristine/`) — belt and suspenders is encouraged.
- Task-level `*.py` helpers are next to `verifier.sh` (i.e. `sys.argv[0]`'s directory); the workspace itself is a *different* directory — never assume `pwd` == workspace.
- Host tooling: `bash`, `python3` (3.11+), `pytest` only where the task's Dockerfile installs it. Declare anything else in the Dockerfile and in the PR.

## What a verifier must never do

- **Never read the transcript** or any run artifact — grading must be independent of how the result was produced.
- **Never phone home.** No curl, no pip install (except from the task's own pinned toolchain).
- **Never mutate the original task directory.** Helpers are copied; run them from copies.
- **Never depend on wall-clock absolutes.** Relative comparisons on the same machine (e.g. optimized vs naive reference) are fine; "must finish in < 2 seconds" is not.

## Standard idioms

```bash
set -u
WS="${CBENCH_WORKSPACE:-$PWD}"
cd "$WS" || exit 1
fail() { echo "FAIL: $1"; exit 1; }
```

- Guard every required file with `[ -f ... ] || fail "..."` — clearer diagnostics than letting the script stumble.
- Run test suites with `-q` and capture; on failure, print the tail so `verifier.log` explains the verdict.
- For reference comparisons, put the reference in a task-level `*_ref.py` and invoke it inline (see `feature/csv-normalizer`).
- For repeated-flakiness checks, loop N times and fail on the first red run (`debug/flaky-test`).
- For mutation checks, apply mutants to a copy and restore via `trap` (`tooling/test-gen`, `houdini/mutation`).
