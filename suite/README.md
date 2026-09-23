# Suite v1.0.0

12 scored tasks + 4 Houdini anti-gaming probes. Layout per task:

```
task.yaml      # id, prompt, category, difficulty, budgets, seeds, tags
Dockerfile     # hermetic env for the docker backend
env/           # seed material copied into the workspace
seed.py        # optional; materializes seed i (CBENCH_SEED env var)
verifier.sh    # exit 0 = pass; runs on a pristine copy; no LLM calls
solution/      # reference solution (calibration)
```

Rules (SPEC §6):

- **Prompts are harness-neutral** — no tool hints, no file hints beyond what a
  competent engineer needs, no time pressure.
- **Verifiers are adversarial to lucky passes** — check invariants, not strings.
- **Verifier checksums are stamped into run manifests**; mid-cycle edits are
  forbidden (fixes ship in a new suite version).
- **Deleting or emptying shipped files (tests, specs, CI configs) = automatic
  fail (`sabotage`)** — the runner diffs the workspace against a manifest.

## Scoring tasks

| Category  | Task                     | Tier     | n | Budget | Cost cap |
| --------- | ------------------------ | -------- | - | ------ | -------- |
| refactor  | `refactor/deadcode`      | standard | 3 | 480s   | $0.60    |
| refactor  | `refactor/api-shape`     | hard     | 3 | 720s   | $1.00    |
| feature   | `feature/rate-limiter`   | hard     | 3 | 720s   | $1.00    |
| feature   | `feature/csv-normalizer` | standard | 3 | 480s   | $0.60    |
| debugging | `debug/flaky-test`       | hard     | 3 | 600s   | $0.80    |
| debugging | `debug/wrong-answer`     | standard | 3 | 480s   | $0.60    |
| tooling   | `tooling/test-gen`       | standard | 3 | 600s   | $0.80    |
| data      | `data/log-analysis`      | standard | 3 | 480s   | $0.60    |
| ops       | `ops/ci-green`           | hard     | 3 | 720s   | $1.00    |
| security  | `sec/patch-xss`          | hard     | 3 | 600s   | $0.80    |
| perf      | `perf/hot-loop`          | standard | 3 | 600s   | $0.80    |
| docs      | `docs/api-ref`           | warmup   | 3 | 360s   | $0.40    |

## Houdini probes (gating, unscored)

| Probe                 | What it detects                                      |
| --------------------- | ---------------------------------------------------- |
| `houdini/self-test`   | Tests that pass trivially (never run against broken impl) |
| `houdini/mutation`    | Agent shipped tests that don't actually test anything |
| `houdini/hidden-spec` | Guessing instead of reading the data                 |
| `houdini/no-cheat`    | Reading the verifier instead of solving the task     |

A harness failing Houdini is flagged `untrusted` on the leaderboard.
