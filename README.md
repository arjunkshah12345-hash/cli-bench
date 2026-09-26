<div align="center">

<img src="assets/logo.svg" alt="CLI-Bench" width="120" />

# CLI-Bench

**An apples-to-apples benchmark for agent harnesses.**

One model. Many CLIs. Same tasks, same verifier, same budget. Measure the harness, not the model.

[![Suite](https://img.shields.io/badge/suite-0.9.1-000000)](SPEC.md)
[![License](https://img.shields.io/badge/license-Apache--2.0-000000)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.11%2B-000000)](#)
[![Score types](https://img.shields.io/badge/score-CB%2DHDR%20·%20HDR%20·%20HDR%2DC-000000)](#the-two-scores)

[Website](https://cli-bench.vercel.app) · [SPEC.md](SPEC.md) · [Methodology](docs/methodology.md) · [Add a harness](docs/adding-a-harness.md) · [Add a task](docs/adding-a-task.md)

</div>

---

**New models ship weekly; new CLIs ship too.** Comparing the CLIs themselves is hard: every published agent number is a *system* number — model + scaffold fused together. Re-run the same model snapshot under different harnesses and the spread can rival a full model generation. When you pick Cursor Agent vs Codex vs OpenCode vs Claude Code vs Droid, you are mostly picking a harness — and that choice is rarely measured in isolation.

**CLI-Bench is a reproducible benchmark framework for coding-agent CLI harnesses**: deterministic verifiers, seeded tasks, raw-artifact transparency, anti-gaming probes, and full resource accounting. Related work: [HarnessBench](https://github.com/reacher-z/HarnessBench) (fixes the base model, varies the harness, for online tasks) and A-Code Bench (17 harnesses, model held constant) share the same instinct — CLI-Bench focuses narrowly on *coding-agent CLIs*, with deterministic per-task verification, seeded task instances, Houdini anti-gaming probes, and per-trial artifacts.

**CLI-Bench pins everything except the harness:**

| Variable    | Status in CLI-Bench                                                |
| ----------- | ------------------------------------------------------------------ |
| Model       | **Pinned per cohort** — one exact model ID per comparison cohort; adapters pass it to the CLI and the runner hard-fails if a harness's native model report contradicts it (§5.5). Harnesses that cannot run a family are never mixed into that cohort |
| Tasks       | **Identical suite** — same files, same prompt bytes, checksummed   |
| Grading     | **Programmatic verifiers only** — no LLM judge on the primary score |
| Budget      | **Identical** — same wall-clock and token ceilings per task        |
| Environment | **Identical container** (Docker; planned) or fingerprinted sandbox (local, implemented)  |
| The harness | **The only free variable** — that's the whole point                |

## The two scores

CLI-Bench keeps the headline number honest and makes every trade-off visible:

- **CB-HDR** *(primary)* — Cost-Braked Harness Delta Rate: a **token-braked weighted pass rate**. Per task, each pass is credited in full up to 5× the **median resource spend of the harnesses that passed that task** (a deliberate noise-tolerance band), then decays linearly: 10× median → 0.5, 25× median → 0.2. Fail → 0, no matter how cleverly. A harness cannot buy rank with tokens.
- **HDR** — the raw, unbraked weighted pass rate. Published always; it is the input to everything else.
- **HDR-C** *(complement)* — equal-cost pass rate: per task, one budget bar for every harness — `envelope = 1.0 × the cohort's passer-median spend`. A harness keeps credit for a pass only if the **median spend of its own passing seeds** lands under the bar; tasks with no passer anywhere are excluded. Rewards harnesses that extract more value from fewer tokens. (n/a for a single-harness group — the bar degenerates to the harness's own median.)

Plus reported axes that never hide trade-offs: wall time, tokens (in/out/reasoning/cached), turns, retry churn, and a code-quality probe judged blind on diffs only. Full formulas and worked examples: [SPEC.md §4](SPEC.md#4-the-metric-system).

## Suite v0.9.1 — 12 tasks × 3 seeds

| Category  | Task                     | Tier     | What it measures                                |
| --------- | ------------------------ | -------- | ----------------------------------------------- |
| refactor  | `refactor/deadcode`      | standard | Prune dead code without breaking behavior       |
| refactor  | `refactor/api-shape`     | hard     | Reshape a public API; migrate every call site   |
| feature   | `feature/rate-limiter`   | hard     | Token-bucket limiter to spec, atomic semantics  |
| feature   | `feature/csv-normalizer` | standard | Normalize messy CSV against a written spec      |
| debugging | `debug/flaky-test`       | hard     | Diagnose and fix a genuinely flaky test         |
| debugging | `debug/wrong-answer`     | standard | Fix a logic bug from failing tests alone        |
| tooling   | `tooling/test-gen`       | standard | Raise coverage; mutation-tested tests           |
| data      | `data/log-analysis`      | standard | Exact answers from a large structured log       |
| ops       | `ops/ci-green`           | hard     | Failing CI matrix → green, assertions untouched |
| security  | `sec/patch-xss`          | hard     | Close an XSS; exploit tests must flip to passing |
| perf      | `perf/hot-loop`          | standard | 10× speedup, semantics preserved (machine-relative) |
| docs      | `docs/api-ref`           | warmup   | Accurate API reference from source (quality probe) |

Anti-cheat is built in: verifier checksums, workspace-diff sabotage detection (deleting shipped tests fails the task), mutation-tested coverage, pristine-copy tripwires, and a 4-probe **Houdini** gate that only rewards *not* cheating. [SPEC.md §7](SPEC.md#7-anti-cheat).

## Quickstart

**Run everything with mocks (no API keys, ~1 min):**

```bash
git clone https://github.com/arjunkshah12345-hash/cli-bench
cd cli-bench
uv venv && source .venv/bin/activate
uv pip install -e ".[dev]"
cbench list
cbench run --harness mock-a --harness mock-b --suite suite/ --seeds 1 --parallel 4
cbench score runs/<run-dir>
cbench report runs/<run-dir> -o results.json
```

**Run a real harness (needs provider creds):**

```bash
cbench run --harness codex --model openai/gpt-5.3 --suite suite/ --seeds 3
cbench score runs/<run-dir>
```

**Available adapters:** `mock-a`, `mock-b` (self-test), `claude-code`, `codex`, `opencode`, `cursor-agent`, `droid`, `gemini`, `aider`, `goose`, `prime-agent`. See [docs/adding-a-harness.md](docs/adding-a-harness.md) to add yours.

**Backends:** `--backend local` (default, sandboxed temp dirs, works on macOS/Linux) or `--backend docker` (specified, **not yet implemented** — the CLI refuses with an explicit error).

**Model cohorts:** adapters declare which model families they can run; `cbench run` refuses out-of-cohort pairings (`--allow-incompatible` overrides and is recorded in the manifest). If a harness natively reports the model it ran and it differs from the request, the run **aborts before scoring**. Details: [SPEC.md §5.5](SPEC.md#55-model-pinning-cohorts-and-effective-model-verification).

## Honest limitations

We publish these on the website because they change how you should read every number:

1. **Auth-side leakage** — a harness from the same lab as the pinned model may enjoy better defaults. We run a cross-family control and report it as an axis.
2. **Estimated tokens** — harnesses without usage reporting get ±10–20% estimated costs; comparisons within the estimate class are fair.
3. **Task coverage** — 12 tasks × 3 seeds ranks harnesses with CIs; it cannot resolve sub-point deltas. We bootstrap CIs and refuse to discuss smaller gaps.
4. **Snapshots beat aliases** — harnesses that can't pin a model snapshot are flagged `provisional`.
5. **Results, verifiably** — the first measured cohort cell is committed: codex @ gpt-5.6-luna, 12 tasks × 3 seeds, CB-HDR 0.592, suite 0.9.1 (see [`results/20260924-codex-gpt-5.6-luna/`](results/20260924-codex-gpt-5.6-luna/README.md) with per-task breakdowns and raw per-trial artifacts). Your runs slot into the same format.

## Repository layout

```
cli_bench/        # runner, scoring, report, adapters registry, usage proxy
harnesses/        # adapter implementations + TEMPLATE.py
suite/            # 12 tasks + 4 houdini probes: task.yaml, verifier.sh, seed.py, Dockerfile
scripts/          # calibration smoke runner
website/          # the website (cli-bench.vercel.app)
docs/             # methodology, contracts, contribution guides
assets/           # logo, banner, OG image
```

## Submitting results (planned)

The submission pipeline (PR-reviewed `results/` directory with CI re-runs and checksum verification) is **planned, not yet implemented** — see [SPEC.md §10](SPEC.md#10-governance). Today: run the suite on your machine, publish your `run.json` + artifacts wherever you like, and link them in an issue or PR if you want them discussed.

## Contributing

Tasks rot and harnesses multiply — both are first-class contribution surfaces. Read [docs/adding-a-task.md](docs/adding-a-task.md) or [docs/adding-a-harness.md](docs/adding-a-harness.md), then open a PR.

## License

Apache-2.0. See [LICENSE](LICENSE).
