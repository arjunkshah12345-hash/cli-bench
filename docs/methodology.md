# Methodology

This document is the practitioner's companion to [SPEC.md](../SPEC.md) §4. It explains what each number means, how it is computed, and where it can mislead you.

## The three numbers

### CB-HDR (primary) — Cost-Braked Harness Delta Rate

For each task `t` and harness `i`:

1. Collect the effective token spend of every **passing** trial of `t` across all harnesses. The median of these is `p50(t)`.
2. Harness `i`'s credit on `t` for one seed is:
   - `0` if it failed (fail, budget-out, crash, sabotage),
   - `B = min(1, 5·p50 / spend)` if it passed, where the 5·p50 cap is itself clamped to the task's token budget when one is computable.
3. Per task: take the **median credit across seeds**, multiply by the task weight `w = category_weight × difficulty_weight`.
4. CB-HDR = Σ weighted credit / Σ weights.

Properties worth internalizing:

- **Passing cheaply is full credit.** The brake never rewards slowness; it only discounts extravagance. A harness that passes at half the median spend earns the same 1.0 as one at exactly median — we do not reward speed on the primary axis, we publish time separately. This is deliberate: brake constants that reward sub-median spend turn the benchmark into a latency race and punish thorough harnesses.
- **The brake is smooth.** Full credit anywhere up to 5× the passer median (a deliberate noise-tolerance band); beyond that it decays linearly — 10× median → 0.5, 25× median → 0.2. There is no cliff below the band, so run-to-run noise cannot swing a harness between full and zero credit.
- **Failures are zero regardless of spend.** Burning 10× tokens and failing is still zero. The brake only shapes credit among passers.
- **p50 is cross-harness by construction.** You are compared against what your peers needed, not against a fixed bar that rot as models improve.

### HDR — raw pass rate

Unweighted fraction of tasks passed (median over seeds, mean over tasks). Published next to CB-HDR always. If a harness's HDR is high but CB-HDR is low, it passes by brute force; if CB-HDR is high but HDR is middling, it is efficient on what it can do. Neither is hidden.

### HDR-C — pass rate at equal cost

CB-HDR discounts wasteful passes continuously. HDR-C asks a blunter question: *holding every harness to the same per-task budget bar, what fraction of tasks can you pass at all?* The bar per task is `envelope(t) = X × p50(t)`, where `p50(t)` is the **cohort's passer-median spend** — identical for every harness on that task, so scores are comparable across manifests (`X = 1.0` by default; `--envelope-factor`). A harness earns credit on a task iff it passed it **and the median spend of its own passing seeds** is within the envelope; tasks with no passer in the cohort are excluded. HDR-C is deliberately harsh: a harness that only passes what it can pass cheaply scores the same as a spendthrift that passes the same set. (For a single-harness group the bar degenerates to that harness's own median and the score saturates at 1.0 — it becomes meaningful from the second harness onward.)

## Seeds and variance

- Each task runs with ≥3 seeds. Where the task has a parameter space (CSV rows, race-window widths, dataset shapes), seeds are **materially different instances** generated deterministically by `seed.py`. Otherwise seeds are repeat trials.
- Per-task scores take the median across seeds before aggregation, which caps the influence of a single lucky/unlucky trial.
- 95% confidence intervals come from a bootstrap over tasks (500 resamples, seeded RNG → CIs are reproducible). **Differences smaller than the CI overlap are not claimed as rankings** anywhere official.

## Effective tokens (the spend unit)

`spend = input + output + reasoning + 0.1 × cache_read`

The 0.1× cache discount acknowledges that cached reads are genuinely cheaper; harnesses that structure their context to maximize caching should not be punished as if every cached token were fresh. Usage sources, in priority order: harness-reported usage (native), provider-reported usage, transcript estimate (chars/4, flagged `estimated`). The method is recorded per run and shown on the leaderboard.

## What the brake does NOT fix

- **Skill priors.** A harness whose system prompt encodes great engineering habits deserves credit — that is the harness working. But it also means scores partly measure prompt-writing, which transfers only as well as prompts do across models. The model pin makes this a fixed artifact per suite run.
- **Tool ecosystem differences.** A harness with a browser tool can pass tasks others cannot. Capability-matched leaderboard views (filter by `requires:` tags) are planned for v1.1; until then the overall table includes everything and the profile column tells you why.

## Reproducibility

`runs/<id>/run.json` records: suite version, model id, backend, host fingerprint, per-task checksums, seeds, harness names + versions + approval flags. Given the same suite tag and environment class, `cbench run` + `cbench score` reproduce the score up to model sampling noise, which is exactly what the CIs express.
