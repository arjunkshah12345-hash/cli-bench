# Results — codex @ openai/gpt-5.6-luna (suite 0.9.1)

**First measured leaderboard entry.** Every number below is produced by this
repository's runner + verifier + scoring pipeline from raw artifacts in
[`runs/`](./runs/) — no illustrative or synthetic data.

- **Date:** 2026-09-23/24 (UTC) · **Suite: 0.9.1** (bumped from 0.9.0 mid-run: the
  csv-normalizer SPEC clarification is a task-content change, and SPEC §6 forbids
  silent edits within a released suite version)
- **Harness:** codex (`codex exec --json --skip-git-repo-check --ignore-user-config --approve-for-me`)
- **Pinned model:** `openai/gpt-5.6-luna` — **effective model proven per trial** from codex's
  session rollout (`turn_context.payload.model`), per SPEC §5.5. 36/36 trials matched.
- **Isolation:** `CODEX_HOME` redirected to a per-trial auth-only copy; no user
  config, AGENTS.md, skills, or session history leaked into any trial.
- **Suite:** 0.9.1, all 12 scored tasks × 3 seeds = **36 trials**, backend `local`, macOS arm64
- **Houdini gate: PASS (TRUSTED)** — all 4 probes × 3 seeds (12 probe trials) passed;
  gate evidence committed under `runs/codex/houdini__*`
- **Auth:** ChatGPT Plus subscription (codex login); pricing from pinned table 1.0.0
  ($0.20 / $0.02 cached / $1.20 per 1M tokens)
- **Total spend:** $1.38 for the full batch

## Headline

| metric | value |
|---|---|
| **CB-HDR** (weighted, cost-braked) | **0.592** (95% CI [0.30, 0.86], 500× bootstrap) |
| HDR (raw pass rate) | 0.583 (23/36) |
| HDR-C (equal-cost) | 1.0 — degenerate at n=1 (see note) |
| Median $/task | $0.033 |
| Median wall-clock/task | 95 s |
| Sabotage detections | 0 |
| Budget exits | 0 |
| Crashes | 0 |
| Houdini trust gate | **pass** (12/12 probe trials, `houdini_gate: "pass"` in leaderboard.json) |

> **HDR-C note:** the equal-cost bar is the **cohort passer median per task**
> (`envelope = 1.0 × p50(t)`); with a single harness in the group the bar is that
> harness's own median, so the score trivially saturates at 1.0 — computed and
> recorded in `leaderboard.json`, but uninformative. HDR-C becomes meaningful
> from the second harness in a cohort onward.

## Per-task results (3 seeds each)

| task | category | tier | pass | median spend (k tok, passes) | median $ (passes) | median s |
|---|---|---|---|---:|---:|---:|
| debug/wrong-answer | debugging | standard | **3/3** | 98.8 | 0.0220 | 41.4 |
| debug/flaky-test | debugging | hard | **3/3** | 191.8 | 0.0453 | 88.4 |
| docs/api-ref | docs | warmup | **3/3** | 138.8 | 0.0350 | 96.8 |
| feature/csv-normalizer | feature | standard | **3/3** | 107.7 | 0.0257 | 104.1 |
| feature/rate-limiter | feature | hard | **3/3** | 104.6 | 0.0252 | 60.2 |
| ops/ci-green | ops | hard | **3/3** | 200.8 | 0.0493 | 138.5 |
| refactor/deadcode | refactor | standard | **3/3** | 100.3 | 0.0228 | 30.2 |
| data/log-analysis | data | standard | 1/3 | 127.6 | 0.0297 | 69.3 |
| perf/hot-loop | perf | standard | 1/3 | 203.2 | 0.0499 | 156.9 |
| refactor/api-shape | refactor | hard | 0/3 | — | — | 96.3 |
| sec/patch-xss | security | hard | 0/3 | — | — | 100.4 |
| tooling/test-gen | tooling | standard | 0/3 | — | — | 95.4 |

## What the failures look like (verifier evidence, not vibes)

- **tooling/test-gen (0/3):** mutation testing did its job. Codex's generated
  suites all passed (38/38) but did not catch the planted behavior change —
  `mutation m3 survived`. Writing passing tests ≠ writing tests that can fail.
- **sec/patch-xss (0/3):** the exploit suite kept failing — script payloads
  neutralized in some paths but `img onerror` attributes survived sanitization.
- **refactor/api-shape (0/3):** partial migrations every time — 8/9 tests
  passing with one call-site left behind (`assert 12 == 10` in the summary site).
- **perf/hot-loop (1/3):** correctness always held; the optimizer hit 40.6× on
  uniform data but only 1.2× worst-case (gridded), under the 10× bar.
- **data/log-analysis (1/3):** borderline; two seeds failed the edge-case checks.

## Fairness notes

- **Task fix during the run:** `feature/csv-normalizer`'s SPEC said "Title Case
  each word" without defining apostrophe handling. Codex's first 3 trials
  (`O'Brien` → `O'Brien` via `str.title()`) failed against the reference
  (`O'brien`). The SPEC was made explicit (`O'Brien` → `O'brien`, no
  `str.title()`), after which it passed 3/3. Only the post-fix trials are
  included here; the pre-fix trials are **excluded** from scoring and noted in
  the batch manifest. Verifiers were never changed.
- **Native usage accounting** (`usage_estimated: false`) for all 36 trials —
  token totals come from codex's own `turn.completed` events, not estimation.
- One harness × one model is **one cohort cell**, not a leaderboard. Rankings
  begin when a second harness joins this cohort.

## Reproduce

```bash
pip install -e .
cbench run --harness codex --model openai/gpt-5.6-luna --seeds 3
cbench score <run-dir>
```

Requires codex ≥ 0.153 logged in (`codex login`) or `OPENAI_API_KEY`. Budget
roughly $1.40 at current gpt-5.6-luna pricing. Raw artifacts: [`runs/`](./runs/)
— per-trial `result.json`, native `stdout.log` (JSONL events), `transcript.jsonl`,
`verifier.log`, `workspace.zip`, and 25/50/75% checkpoints.

## Score digest (`leaderboard.json`)

```json
{
  "harness": "codex",
  "cb_hdr": 0.592,
  "ci95": [0.3008, 0.8601],
  "hdr": 0.5833,
  "passed": 23,
  "trials": 48,
  "houdini_gate": "pass",
  "houdini_probes": 12,
  "cost_usd": 0.036,
  "tokens": 163376,
  "duration_s": 83.0,
  "sabotage": 0,
  "budget_outs": 0,
  "crashes": 0
}
```
