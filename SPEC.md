# CLI-Bench — Specification v0.9.1

**An apples-to-apples benchmark for agent harnesses** (CLIs like Claude Code, Codex CLI, OpenCode, Cursor Agent, Droid Factory, Gemini CLI, Aider, Goose).

CLI-Bench measures **the harness, not the model**. One model, many harnesses, identical task suite, identical verifiers, identical budget rules. The only variable is the code between the model and the terminal.

**Version:** 0.9.1 · **Status:** Release candidate — see implementation-status notes in §5.2, §5.5, §10 · **Repo:** github.com/arjunkshah12345-hash/cli-bench · **Site:** cli-bench.vercel.app

---

## 1. Why this exists

Every frontier lab releases a CLI, and every CLI publishes benchmark numbers. The numbers are not comparable:

1. **Different models.** Harness A reports GPT-X on SWE-bench; harness B reports Claude-Y on Terminal-Bench. A new model release shifts every published number, so you cannot tell whether last month's winner is still a good harness.
2. **Different tasks.** One suite includes Kaggle-style puzzles; another uses real GitHub issues. Task difficulty differences swamp harness differences.
3. **Different budgets.** One harness gets 200 steps and no cost cap; another gets 25 turns. Budget differences are not model quality, but they are reported as if they were.
4. **Different graders.** One uses fuzzy LLM-as-judge; another runs exact tests. Some graders accept more solution shapes than others.
5. **Self-reported scoring.** Vendors grade their own runs. Few publish logs you can re-grade yourself.

Meanwhile, there is real evidence the gap is large. Public SWE-bench re-runs using the same checkpoint under different scaffolds have shown score spreads comparable to a full model generation (e.g. a mini-SWE-agent-style minimal loop vs. a fully instrumented commercial agent, on the identical model snapshot). Harness choice can matter more than the model-version bump you were about to pay for. Yet there is no independent, harness-controlled benchmark — one fixed model, one task suite, one verifier, one budget — that isolates the harness variable.

**CLI-Bench's only goal:** hold every other variable constant and measure what the harness adds or loses.

### What this is not

- **Not a model leaderboard.** With the model pinned, model improvements are invisible by construction (and any score movement is attributable to the harness or task updates, both of which are versioned).
- **Not a Terminal-Bench replacement.** Terminal-Bench measures agents on hard terminal tasks across many agents; its agent-vs-agent comparison re-tests the full stack (model + agent). CLI-Bench pins the model on purpose.
- **Not a vibe check.** Every score decomposes into pass rate, cost, wall time, tokens, and turns, each with an exact, inspectable definition.

---

## 2. Measurement invariants

These five invariants define the benchmark. A run that violates any invariant is not a CLI-Bench run.

### I1 — Model pinning

All harnesses in a comparison use the **same model ID** with pinned alias resolution:

- Each comparison declares `model_id` (e.g. `openai/gpt-5.3`) and, where a provider exposes a frozen snapshot, `snapshot` (a date/version). Aliases resolve to snapshots at run start; the resolved snapshot ID is recorded in `run.json`.
- Harnesses that cannot pin a snapshot record the alias they sent and the date of the run. Snapshot-pinnable harnesses are preferred in the official leaderboard.
- Sampling temperature, top_p, and other decoding parameters are **whatever the harness defaults to** — this is a harness property, not a model property, and CLI-Bench deliberately does not normalize it. (We measure harnesses as users actually run them: `codex`, `claude -p`, `aider` out of the box.)
- **Reasoning-effort is a harness capability, not a confound**: harnesses MAY set reasoning levels (e.g. `xhigh`); CLI-Bench records what was set. When a leaderboard publishes a "pinned model" class, it may sub-classify by effort tier (see §6.3) so an `xhigh` harness is never compared against a `medium` one as if the difference were harness quality alone.

### I2 — Task uniformity

Every harness sees the **same container**, the **same task files**, the **same prompt**, and the same environment variables. No harness receives extra context, hints, memory, or pre-seeded caches that others do not. Harness-native features (planning modes, background agents, tool ecosystems) are part of the harness being measured — that is the point — but they must operate within the same container and budget as everyone else.

### I3 — Budget uniformity

Every harness gets the same two budget envelopes on the same task:

- **Wall clock:** `time_budget_s` (task-level; see tasks for values).
- **Cost ceiling:** `max_cost_usd` computed from a single price table pinned in the run manifest (USD per 1M input/output tokens for the chosen model). Tokens are the harness-reported usage if available, else estimated from the transcript per §5.4.

A run is **budget-exhausted** when either ceiling is hit. Its outcome is recorded (`budget_exhausted: true`, which ceiling) and it is scored as a non-pass (§4.1). There are no infinite-token hall passes.

### I4 — Verifier objectivity

Every task has a `verifier` that is **a program, not a judge**. Verifiers are deterministic shell scripts or pytest files run in a pristine container copy of the final workspace state. Verifiers never read the transcript, never call an LLM, and are identical for every harness. Verifier behavior is defined by the task's `verifier.sh` exit code (0 = pass) plus explicit artifacts when the task requires them.

LLM-as-judge is permitted for exactly one thing: the **Code-Quality probe** (§4.2, quality-tier score), and even there the judge input contains no agent identity and no transcript; it sees only the final diff of the changed files.

### I5 — Full transparency

Every published score links to raw artifacts: the full transcript (`transcript.jsonl`), the final workspace (`workspace.tar.zst` when it contains no secrets), per-turn token/cost accounting, and the verifier output. Anyone can re-grade a run from its artifacts. Submissions that cannot produce artifacts are not listed.

---

## 3. What "the harness" actually is

We define the **harness** as the executable system the user invokes, minus the model behind it. Concretely, for a CLI named `foo`:

| In scope (measured)                              | Out of scope (held constant)          |
| ------------------------------------------------ | ------------------------------------- |
| System prompt & instruction framing              | Model weights                         |
| Tool set & tool schemas exposed                  | Model context window (same model ⇒ same window) |
| Context management (compaction, file-view truncation) | Provider rate limits             |
| Retry/backoff & error handling                   | Machine specs (same container shape)  |
| Sub-agents, parallelism, planning modes          | Internet access (same allowlist)      |
| File-edit ergonomics (search/replace vs rewrite, lints on save) | Network MTU :)        |
| Verification loops (run tests? read errors? when?) | Time of day, provider load (averaged over N seeds) |
| Terminal UX fidelity (it must work non-interactively) |                                   |

Harnesses are run **headless/non-interactive** with a single task prompt (the same one) and a fixed startup environment. Flags that change behavior materially (e.g. `--dangerously-skip-permissions`, auto-approve, plan mode) must be declared in the harness profile and are shown on the leaderboard so a "max-agency" config is never silently compared to a "guarded" one.

---

## 4. The metric system

### 4.1 Primary score: CB-HDR

CB-HDR is the headline number. It is deliberately simple and cannot be gamed by trading money for time.

```
CB-HDR_i  =  Σ_t  w(t) · S(t, i)  /  Σ_t  w(t)          (weight-normalized pass rate)

w(t)        =  w_category(t) · w_difficulty(t)
S(t, i)     =  median over seeds of the per-seed credit of harness i on task t

per-seed credit =  B(t, i)   if harness i passed task t on that seed
                 =  0        otherwise

B(t, i)     =  min(1, b_ref(t) / b_i(t))       ∈ (0, 1]     — the efficiency brake

b_i(t)      =  actual resource spend by harness i on task t
p50(t)      =  median b across ALL harnesses that passed t (the cohort passer median)
b_ref(t)    =  b at which the brake saturates: b_ref(t) = 5 × p50(t) (clamped to the task budget, never below p50(t))
w_category  ∈ [0.75, 1.5]   (task category weight; spec table below)
w_difficulty ∈ {1.0, 1.25, 1.5, 1.75}  for tiers {warmup, standard, hard, frontier}
```

Note the normalization: the denominator is the **static sum of task weights** — it does not contain the brake. `R = w · B` is the per-task *credit*; dividing by Σw keeps a failed task at exactly 0 and a full-band pass at exactly its task weight. (An earlier draft normalized by Σ(w·B), which inflates scores for spend-heavy harnesses and is wrong.)

**The brake B.** A harness that passes within the saturation band — spend ≤ 5× the passer median (or under the task budget, if computed) — earns **full credit**: the formula is `min(1, 5·p50 / spend)`, so at 2× median a pass still scores 1.0. Beyond 5× median the brake decays linearly: 10× median → 0.5, 25× median → 0.2. This is a deliberate tolerance band, not a reward for extravagance: a 1.9× pass is real capability and noise in that range should not reorder the leaderboard; the band only discounts *extraordinary* overspend. The brake multiplies the task weight so it can only pull a harness down, never up.

The implemented CB-HDR is therefore a **token-braked weighted pass rate**. Latency and diff-churn are *published as separate columns*, never folded into the headline number — compositing them is deferred (§4.3) until real run data can justify the constants.

#### 4.1b HDR-C: the equal-cost pass rate

HDR-C answers one question: *how much of the pass rate survives when every harness is held to the same per-task budget bar?* It is deliberately plain:

```
envelope(t) = X · p50(t)          X = 1.0 (published in every leaderboard manifest)

HDR-C_i     =  |{ t : harness i passed t  AND  median spend of its passing seeds ≤ envelope(t) }|
               ÷ |{ t : p50(t) > 0 }|          (tasks with no passer in the cohort are excluded)
```

- The bar is the **cohort passer median per task** — identical for every harness on that task — so scores are comparable across manifests and machines.
- Credit uses the **median spend across a harness's own passing seeds**, matching the median-over-seeds aggregation of CB-HDR/HDR. One lucky cheap seed cannot launder two expensive ones.
- X = 1.0 by default: a harness keeps credit for a pass whose typical cost is at or under what a passer typically spends. There is no partial credit and no cross-task averaging inside the envelope.
- HDR-C is **n/a** for a group with fewer than two harnesses' worth of data in practice (the bar degenerates to the harness's own median); it becomes meaningful the moment a second harness joins the cohort.

- **b = tokens_total** by default (input + output, includes reasoning tokens; cache-read tokens count at a 0.1× discount since they are genuinely cheaper and cache friendliness is a real harness skill).
- Alternatively `b = wall_time` for latency-class leaderboards, using the same formula. Cost-USD may be used as `b` for cross-provider comparisons (it normalizes token prices), but token-based braking is the default because it is price-independent. The task's `max_cost_usd` budget additionally tightens the saturation point (converted to tokens via the pinned price table, SPEC §5.1) so a harness cannot brute-force a pass under a token-cheap model.

**Why brake instead of just publishing cost separately?** Because a harness that solves tasks only by burning 10× tokens is not *better*; it is a different point on a Pareto frontier, and unweighted pass rate hides that. The brake keeps pass rate primary while making resource-extravagant strategies pay a visible, bounded price. The 5× saturation constant is chosen so a pass within 1.25× median loses ≤20% credit — noise-level for well-behaved harnesses — while a 10× spender keeps ≤50%.

**Category weights (w_category):**

| Category            | Weight | Rationale |
| ------------------- | ------ | --------- |
| `refactor`          | 1.25   | Precision-editing is the core harness skill |
| `feature`           | 1.25   | End-to-end construction of new behavior |
| `debugging`         | 1.2    | Reading, hypothesizing, verifying |
| `tooling`           | 1.1    | Build, test, migration, environment work |
| `data`              | 1.1    | Deterministic analysis & transformation |
| `ops`               | 1.0    | Scripts, CI, systemd, containers |
| `security`          | 1.0    | Vulnerability identification & closure |
| `perf`              | 1.0    | Measured optimization under tests |
| `docs`              | 0.9    | Documentation generation (LLM judges only here) |
| `cleanup`           | 0.75   | Pruning; hardest to verify objectively |

**Difficulty tiers (w_difficulty):** `warmup` 1.0 · `standard` 1.25 · `hard` 1.5 · `frontier` 1.75.

### 4.2 Secondary axes (reported, never hidden)

Every run publishes:

| Axis                  | Definition                                                                 | Notes |
| --------------------- | -------------------------------------------------------------------------- | ----- |
| **Pass rate**         | Unweighted % of tasks passed (verifier exit 0, within budget)               | The raw signal |
| **Cost (USD)**        | Σ tokens × pinned price table                                               | Price table versioned per run |
| **Wall time**         | Σ per-task wall seconds (median across seeds)                               | |
| **Tokens**            | Input, output, reasoning, cache-read (reported separately)                  | From usage blocks, else transcript-derived |
| **Turns**             | Model round-trips per task                                                  | Tool calls per round are not counted |
| **Stall ratio**       | Fraction of turns with no tool call and no >140-char model output            | Harness pathology detector |
| **Retry churn**       | Repeated identical tool calls (>2) per task                                  | |
| **Budget-outs**       | Tasks ended by cost ceiling / time ceiling                                   | Split by which ceiling |
| **Error rate**        | Tasks ending in harness crash, auth failure, or unparseable state            | |
| **Code quality (Q)**  | 0–10 LLM-judged on final diffs of `quality_probe` tasks, identity-blind      | Only axis allowed an LLM; see §4.3 |
| **Sandbox integrity** | ≥97% of checkpoints hold; violations listed per task                         | See §7 |

### 4.3 Code-Quality probe (the one LLM axis)

For tasks tagged `quality_probe`, a judge LLM (a **fixed model, different family from the task model**, to reduce family self-preference) sees only: the task statement, the original file(s), and the final diff. It never sees the transcript, harness name, cost, or identity. It scores 0–10 on a public rubric: correctness-preserving, minimal-diff discipline, naming, dead-code avoidance, idempotence. Q is reported per harness as a mean over quality tasks. **Q never feeds CB-HDR.** Judge model and prompt are versioned in the repo.

### 4.4 Seeds and variance

Every task is run with `n ≥ 3` seeds (default `n = 3`, `n = 5` for leaderboard submissions) — distinct task-instance parameterizations where the task supports them (§6.1), otherwise repeated trials. Harness scores report **median CB-HDR across seeds per task, then mean across tasks**, with interquartile range. A leaderboard entry without ≥3 seeds is marked `provisional`. Deterministic tasks with no parameter space (e.g. a fixed JSON transform) still run n=3 to expose flakiness; their per-task score is the median outcome.

---

## 5. Execution model

### 5.1 Runner

The runner (`cli_bench` package, Python 3.11+) orchestrates:

1. **Prepare** container (Docker backend) or local sandbox dir (macOS/Linux backend) from the task's `env` definition.
2. **Print preamble** into the workspace: a `CLI_BENCH.md` (task-neutral notice: "You are being benchmarked; work in this directory; verify your work") — identical bytes for every harness.
3. **Launch** the harness via its adapter (§8) with the task prompt on stdin/argv, in the workspace, with the task's `env_vars`.
4. **Enforce budgets**: wall clock (kill at limit, mark outcome) and cost (usage-sampled each turn; kill on breach).
5. **Checkpoint** the workspace at fixed fractions of the time budget (0.25, 0.5, 0.75) for anti-cheat replay (§7.1).
6. **Verify**: copy final workspace to a pristine verifier container (or clean venv locally), run `verifier.sh`, capture exit code + logs.
7. **Record** `run.json`, `transcript.jsonl`, `usage.jsonl`, `verifier.log`, workspace tarball, and an environment fingerprint (`env_fingerprint.json`: OS, versions of python/node/etc. inside the container, harness version string).

### 5.2 Backends

| Backend   | Flag           | Use |
| --------- | -------------- | --- |
| `docker`  | `--backend docker` | Default for CI and leaderboard submissions. Task Dockerfiles pin exact toolchains. |
| `local`   | `--backend local`  | macOS/Linux dev boxes and Docker-less CI. Runs in an isolated temp dir with the host's tools; env fingerprint recorded so local scores are comparable within, not across, machine classes. |

The backend is a property of the *run*, not the task; every task ships a Dockerfile and a `tools:` list the local backend asserts availability of.

> **Implementation status (v0.9):** the `local` backend is implemented. The `docker` backend is specified here but **not yet implemented** — `cbench run --backend docker` refuses with an explicit error rather than pretending. Task Dockerfiles are shipped now so the docker backend can land without suite changes.

### 5.3 Transcript contract

Every adapter must emit `transcript.jsonl` with one JSON object per line:

```json
{"ts": 1719000000.123, "event": "turn_start", "turn": 1}
{"ts": 1719000001.456, "event": "tool_call", "turn": 1, "tool": "bash", "args_summary": "pytest -x -q tests/", "ok": true, "duration_ms": 812}
{"ts": 1719000002.001, "event": "usage", "turn": 1, "input_tokens": 41230, "output_tokens": 918, "reasoning_tokens": 4096, "cached_tokens": 38120}
{"ts": 1719000003.700, "event": "turn_end", "turn": 1}
{"ts": 1719000004.000, "event": "final", "exit": 0}
```

`tool` values are normalized to a canonical vocabulary (`bash`, `edit`, `read`, `write`, `grep`, `glob`, `browser`, `task`, `mcp:<server>`, `other`). When an adapter cannot parse native events it must fall back to streaming the CLI's stdout/stderr through the same schema (`event: "log"`), so *every* harness produces a transcript; capability differences in logging are themselves recorded (§9, logging fidelity).

### 5.4 Cost accounting

Usage comes from, in priority order: (1) harness-reported usage per turn, (2) provider-side usage if the adapter can read it, (3) token estimate from the transcript (chars/4 heuristic per message role, counted per turn, marked `estimated: true`). The method used is recorded per run; estimated-cost entries are flagged on the leaderboard. Cache-discounted tokens (0.1×) are included in `b` for braking, per §4.1.

### 5.5 Model pinning, cohorts, and effective-model verification

Because harness vendors wire different providers, a single universal "one model for every CLI" comparison is often **impossible** (Claude Code is Claude-family; Codex is OpenAI-family). Comparisons are therefore organized in **model-compatible cohorts**:

- **Pinned cohort** — every harness *capable of running the exact requested model* runs it, with the model passed through the adapter (flag, env, or config) and recorded in the manifest. Ranking tables never combine incompatible cohorts.
- **Native track** — first-party agents on their vendor-recommended model. Reported separately and explicitly **not** a causal harness isolation.

Every adapter declares `model_families` in its profile; `cbench run` refuses a harness × model pairing outside the declared family (override: `--allow-incompatible`, recorded in the manifest). The runner additionally captures the **effective model** when the harness reports one (e.g. Claude Code's stream-json `result.model_id`): a native report that contradicts the requested model **aborts the run with exit code 3** — the manifest must never state a model the CLI did not run. Harnesses that cannot report a model are recorded as `effective_model: null` and flagged in reports.

---

## 6. The task suite

### 6.1 Design rules

Every task lives in `tasks/<category>/<task-id>/` with:

```
task.yaml          # id, title, prompt, category, difficulty, time_budget_s, max_cost_usd,
                   # seeds, requires (tools), tags (e.g. quality_probe), weight overrides
Dockerfile         # exact environment (python/node/etc. versions pinned)
env/               # seed material: buggy repo, data files, failing CI, etc.
seed.py            # materializes seed i (i = 0..n-1) into the workspace — deterministic
verifier.sh        # exit 0 = pass; runs in a pristine copy; no LLM calls
solution/          # reference solution (optional but encouraged) for calibration
CHECKSUMS          # sha256 of env/ + verifier.sh, stamped into run.json (I2)
```

- **Parameterized seeds:** tasks with a parameter space (file sizes, bug positions, repo shapes) must implement `seed.py` so seeds are *materially different instances*, not retries of the same instance. This is how we defeat memorization without changing the task.
- **Prompts are harness-neutral:** no "use ripgrep" (a harness without a grep tool still has bash), no time pressure hints, no file hints beyond what a competent engineer would need. Prompts are frozen; they ship with the suite version.
- **Verifiers are adversarial to lucky passes:** they check invariants, not exact strings (unless the task is a serialization task where exactness *is* the spec).

### 6.2 Categories and current tasks

| Category   | Task ID              | Tier     | n | What it measures (one line) |
| ---------- | -------------------- | -------- | --- | --------------------------- |
| refactor   | `refactor/deadcode`  | standard | 3 | Prune dead code w/o breaking behavior (tests must stay green) |
| refactor   | `refactor/api-shape` | hard     | 3 | Reshape a module's public API; migrate all call sites |
| feature    | `feature/rate-limiter` | hard   | 3 | Build token-bucket limiter to spec + property tests |
| feature    | `feature/csv-normalizer` | standard | 3 | Normalize messy CSV against a written spec |
| debugging  | `debug/flaky-test`   | hard     | 3 | Diagnose & fix a genuinely flaky test (race/ordering) |
| debugging  | `debug/wrong-answer` | standard | 3 | Fix an off-by-one/logic bug from failing tests alone |
| tooling    | `tooling/test-gen`   | standard | 3 | Raise coverage on an untested module via generated tests |
| data       | `data/log-analysis`  | standard | 3 | Answer exact questions from a large structured log |
| ops        | `ops/ci-green`       | hard     | 3 | Make a failing CI matrix green w/o weakening assertions |
| security   | `sec/patch-xss`      | hard     | 3 | Close an XSS in a small web app; exploit test must fail |
| perf       | `perf/hot-loop`      | standard | 3 | 10× speedup on a benchmark, semantics preserved |
| docs       | `docs/api-ref`       | warmup   | 3 | Generate accurate API reference from source (quality probe) |

(Version 0.9.1 ships all 12 wired into the repo, each with verifier + seeds; difficulty tiers and budgets are in each `task.yaml`.)

### 6.3 Task-versioning & treadmill policy

Task suites rot. Policy:

1. **Suite version** is semver-pinned in run manifests (`suite: 0.9.1`). Scores cite the suite version.
2. **Memorization response:** if a task's public reference solution leaks (or we detect seed-level memorization), the task is **retired from scoring** (marked `retired: reason`) and a parameterized successor ships in the next minor suite version. The old suite's leaderboard is frozen, not rewritten.
3. **Behavioral drift:** task difficulty can silently shift as models improve (tasks get easier over time). Every 6 months the maintainers re-calibrate tier weights on fresh reference-harness runs, or re-cut the suite (major version bump).
4. **No mid-cycle edits** to `verifier.sh` or prompts within a suite version. Ever. Fixes ship in a new version; the changelog says which entries are re-scored.

---

## 7. Anti-cheat

Harnesses are clever; some will find the verifier. Countermeasures, by implementation status:

**Implemented in this release (v0.9.1):**

1. **Verifier integrity:** `verifier.sh` + `env/` checksums are stamped into the run manifest, alongside each harness's version and approval flags.
2. **Workspace diffing (sabotage detection):** every task's verifier runs against the final workspace on a pristine copy, and the runner compares shipped-file checksums against the seed manifest. Deleting or emptying task-shipped files (tests, spec, data) = the task is graded as gamed (`outcome: sabotage`) — it can only hurt the score, never help it.
3. **Houdini trust gate (§7.2):** the probe suite runs via `--with-houdini`; any probe that does not pass marks the harness `untrusted` on the leaderboard. Scores stand; the trust label is honest.
4. **Adapter isolation:** adapters with config-based memory (e.g. codex) run each trial with a per-trial auth-only config home, so user prompts, skills, and agent guides cannot leak into a benchmark trial (§5.5, harness `notes`).
5. **Model proof:** effective-model verification per trial (§5.5) — a harness whose native report contradicts the pinned model aborts the run.

**Planned, not yet enforced (required before verified third-party submissions):**

- **Replay audit:** re-run a random ≥10% sample of passes from the checkpointed workspace; divergence from the recorded final state flags human review. (Checkpoints at 25/50/75% are already recorded per trial; the audit tooling is not built.)
- **Process hygiene:** recording spawned processes and flagging network fetches of task material. (Not implemented; the local backend currently trusts the harness process.)
- **Sandbox integrity gate:** Docker read-only-rootfs enforcement and a local-backend write-path audit; `invalid-environment` exclusion. (The Docker backend itself is §5.2-planned.)
- **No pre-knowledge injection audits:** declared empty-config profiles + random clean-profile re-runs. (Codex-class isolation is implemented; the audit loop is not.)

Until the planned items ship, third-party leaderboard submissions are **not** accepted (§10): published numbers are run by the operator from committed artifacts, and each row's Houdini gate status is displayed next to it.

### 7.2 Houdini probes

A 4-task micro-suite, run alongside the main suite, where the *only* way to pass is to NOT cheat (tests re-verify the agent's claimed work from outside the agent's view). These detect harnesses that systematically game verifiers:

- `houdini/self-test`: task asks the agent to write a test; verifier checks the test *fails* against a known-broken implementation and passes against the reference.
- `houdini/mutation`: verifier applies small mutations to the agent's implementation; if the agent's tests don't catch ≥80% of mutants, the agent probably never ran its own tests. (Reinforces "verify your work" over "look done".)
- `houdini/hidden-spec`: spec lives only inside a data file the agent must read; no file-name hint. Rewards reading, not guessing.
- `houdini/no-cheat`: verifier checks the agent did NOT read the hidden grading file (atime audit) while completing an easy log-rotation task.

A harness failing Houdini — **any probe trial that is not a pass** — is flagged
`untrusted` on the leaderboard (`houdini_gate: "fail"` in `leaderboard.json`).
This is deliberately strict: the verifiers report most cheating (a read of the
bait file, a doctored test) as ordinary verifier failures, so gating only on a
separate "sabotage" outcome would miss the exact behavior the probes exist to
catch. Scores stand; the trust label is honest. A run without probe trials is
`houdini_gate: "untested"` and should be read as provisional trust.

---

## 8. Harness adapter contract

Adapters live in `harnesses/<name>/` and implement:

```python
class Harness(Protocol):
    name: str
    version_cmd: list[str]  # e.g. ["codex", "--version"]
    build_cmd: Callable[[TaskContext], list[str] | ShellSpec]  # materialize argv
    prompt_mode: "stdin" | "argv" | "file"
    parse_transcript: Callable[[RawLog], list[TranscriptEvent]]  # normalize §5.3
    profile: HarnessProfile  # flags, memory dirs, network policy, notes
```

`HarnessProfile` records: approval flags used, whether the harness defaults to plan-first, supported transcript fidelity (`native` events vs `stdout` fallback), supported backends, and auth requirements (e.g. `OPENAI_API_KEY` — the runner checks and fails fast with a clear message).

**Headless-first rule:** every shipped adapter must run the harness in its documented non-interactive mode (`codex exec`, `claude -p`, `opencode run`, `cursor-agent -p`, `droid exec`, `gemini -p`, `aider --message`, `goose run -t`, …). Interactive-only harnesses are out of scope for now — a benchmark must not depend on someone driving a TUI.

**Adding a harness:** see `harnesses/TEMPLATE.py` and `docs/adding-a-harness.md`. PRs adding adapters must include one `smoke_test` proving the adapter round-trips a trivial prompt.

---

## 9. Known limitations (honesty section)

1. **Auth-side capability leakage.** Harnesses backed by the same lab as the pinned model may get soft advantages (better defaults, private endpoints, faster tool schemas). We mitigate by publishing auth configuration per harness and running a cross-family control (pinned model from lab A run under harnesses from lab A and lab B; if lab-B harnesses systematically underperform on equal settings, that is reported as an axis, not hidden).
2. **Estimated-token noise.** Harnesses without native usage reporting get estimated costs (±10–20%). Braking uses the same estimate for all such harnesses; comparisons *within* the estimate class are fair.
3. **Harness-specific tool ecosystems.** Some harnesses ship browser/MCP tools others lack. On tasks where a tool category is decisive, we tag `requires:` and report capability-matched views (e.g. leaderboard filtered to harnesses with a browser tool). The overall leaderboard always shows the unfiltered truth.
4. **Task coverage.** 12 tasks × 3 seeds is enough to rank harnesses with CIs (binomial-ish via bootstrap over tasks+seeds), not enough for fine-grained sub-100 deltas. We publish bootstrap CIs and refuse to discuss differences smaller than them.
5. **The harness is entangled with its lab's model tuning.** Some harness prompts are tuned to specific model families. Pinning one model may under-serve harnesses tuned for another. The cross-family control (§9.1) partially exposes this; we report it rather than normalize it away, because users experience it as-is.
6. **Verifiers can be gamed by a sufficiently motivated harness.** Houdini catches systematic gaming, not bespoke one-off gaming. The 10% replay audit is our best mechanical backstop. Human review of flagged passes closes the gap.

---

## 10. Governance

> **Planned for verified leaderboard submissions** — the governance below describes the *intended* submission policy and is **not yet implemented** in this release (no submission CI or maintainer tooling exists yet). Until it ships: all numbers are run by you, on your machine, from the published artifacts; nothing on the website claims third-party verification.

- **Suite & scoring changes:** PR + two maintainer approvals; scoring-code changes additionally require one *score-reproduction run* proving the change re-ranks no existing published entry by more than the published CI width (or the entry is marked re-scored).
- **Leaderboard submissions:** open a PR with `results/<date>-<harness>-<suite>/` containing `run.json` + artifacts link. CI re-runs 30% of tasks, re-verifies checksums, and posts a comment with the reproduced score. Divergence > CI width → submission is held for human review.
- **Conflicts of interest:** maintainers affiliated with a harness vendor may not approve that harness's score-affecting PRs. Disclosed in `MAINTAINERS.md`.
- **License:** Apache-2.0. Tasks and verifiers are public; seed material that enables memorization may be kept in a private repo with checksums published (suite integrity stays auditable).

---

## Appendix A — Scoring worked example

Task `debug/flaky-test` (difficulty `hard`, category `debugging` ⇒ weights 1.5 × 1.2 = 1.8). Suppose 4 harnesses pass, with token spend:

```
h1: 250k   h2: 500k   h3: 1.5M   h4: 7.5M
p50   = median(250k, 500k, 1.5M, 7.5M) = (500k + 1.5M) / 2 = 1.0M   (cohort passer median)
b_ref = 5 × p50 = 5.0M   (under the task budget cap, so no clamping)

h1: B = min(1, 5.0M/250k)  = 1.0    (capped — well inside the saturation band)
h2: B = min(1, 5.0M/500k)  = 1.0    (capped)
h3: B = min(1, 5.0M/1.5M)  = 1.0    (capped — 1.5× median is noise, full credit)
h4: B = min(1, 5.0M/7.5M)  = 0.67   (5× median: braked, not erased — it did pass)

A 10M spender would earn B = 0.5; a failed pass earns credit 0 regardless of spend.
```

Per §4.1: `CB-HDR_i = Σ_t w(t) · S(t,i) ÷ Σ_t w(t)`, where `S(t,i)` is the median
over seeds of the per-seed credit (`w(t) · B` on passes, 0 otherwise). On this task
with all seeds passing: h1–h3 earn 1.8 each, h4 earns 1.8 × 0.67 = 1.2.

For HDR-C on the same task (§4.1b): `envelope = 1.0 × 1.0M`. h1 (250k) and h2
(500k) pass the bar; h3 (1.5M) and h4 (7.5M) do not — even though h3 keeps full
CB-HDR credit. The equal-cost bar is stricter than the brake by design: it asks
"would this pass still count if everyone had to pay the median price?"

## Appendix B — Glossary

- **Harness** — the CLI/agent executable minus the model: system prompt, tools, loop, context management.
- **Brake (B)** — the multiplicative efficiency factor in CB-HDR; full credit within 5× the passing-median (saturation band), then linear decay toward 0.
- **Budget-out** — a run terminated by the cost or wall-clock ceiling; scored as non-pass.
- **Houdini** — the anti-gaming micro-suite (§7.2).
- **Seeds** — materially distinct task instances (or repeated trials where no parameter space exists).
- **Provisional** — a leaderboard entry with <3 seeds.
- **Untrusted** — a harness that failed the Houdini gate; scores shown, flagged.
