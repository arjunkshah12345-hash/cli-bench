# Adding a task

A task is a directory under `suite/<category>/<task-id>/` with:

| File          | Required | Purpose                                                        |
| ------------- | -------- | -------------------------------------------------------------- |
| `task.yaml`   | yes      | id, title, prompt, category, difficulty, budgets, seeds, tags  |
| `verifier.sh` | yes      | exit 0 = pass; runs on a **pristine copy** of the final state  |
| `env/`        | yes      | seed material copied into the workspace                        |
| `seed.py`     | if seeded| materializes seed `i` (env `CBENCH_SEED`), deterministic       |
| `Dockerfile`  | yes      | hermetic environment for the docker backend                    |
| `pristine/`   | optional | reference copies for verifiers that diff against originals     |

## Authoring rules (SPEC §6)

1. **Harness-neutral prompts.** No tool hints ("use ripgrep"), no time hints, no file hints beyond what a competent engineer would need.
2. **Programmatic verification only.** No LLM calls inside `verifier.sh`. Check invariants, not exact strings — unless exactness is the spec (serialization tasks).
3. **Adversarial-to-lucky verifiers.** Assume the agent tried the shortest path. Run the tests repeatedly (`debug/flaky-test` runs 15×). Mutation-test written tests (`tooling/test-gen`). Compare against independent reference implementations (`feature/csv-normalizer`). Check relative speed, not absolute time (`perf/hot-loop`).
4. **Seeds are instances, not retries.** If the task has any parameter space, `seed.py` must produce materially different workspaces per seed, deterministically (`CBENCH_SEED` env var).
5. **Sabotage is automatic.** Deleting/emptying any shipped file fails the task. If a task legitimately requires deleting shipped files (`houdini/no-cheat` rotation), list them under `sabotage_exempt` in `task.yaml`.
6. **Budgets are real.** Set `time_budget_s` and `max_cost_usd` so a competent engineer-harness finishes with ~50% headroom. Run your task against at least one real harness before submitting.
7. **No mid-cycle edits.** Once shipped in a suite version, `verifier.sh`, `task.yaml`, and `env/` are frozen. Fixes ship in the next version.

## Verifier environment

Verifiers run via `bash verifier.sh` in a fresh directory containing:

- a pristine copy of the final workspace (env `CBENCH_WORKSPACE` points at it),
- the task's `verifier.sh` and any task-level `*.py` helpers (reference implementations),
- a copy of `pristine/` if present.

You get the host's `python3`/`bash` (docker backend: the task image's toolchain). Keep verifier runtime < 60s.

## Acceptance checklist

- [ ] verifier fails on the untouched workspace (never starts green)
- [ ] verifier passes for a correct solution you wrote yourself (put it in `solution/`)
- [ ] verifier fails for plausible near-miss solutions (write two)
- [ ] seeds differ materially (diff two seed outputs and eyeball)
- [ ] no LLM calls, no network, no absolute wall-clock assertions
- [ ] `task.yaml` validates: `cbench list` loads it cleanly
