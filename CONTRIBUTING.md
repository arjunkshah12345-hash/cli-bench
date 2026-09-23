# Contributing

Thanks for helping make harness evaluation more honest. Two contribution surfaces matter most: **tasks** and **harness adapters**.

## Setup

```bash
git clone https://github.com/arjunkshah12345-hash/cli-bench
cd cli-bench
uv venv && source .venv/bin/activate
uv pip install -e ".[dev]"
pytest -q          # self-tests
cbench list        # suite loads
```

## Ground rules

1. **Suite & scoring changes are frozen per version.** Once a suite version ships, its tasks, prompts, verifiers, and scoring code do not change. Fixes land in a new version, with a changelog note saying what gets re-scored (SPEC §10).
2. **Every task PR must include:** verifier proof (fails untouched, passes your solution, fails two near-misses), seed materiality evidence, and a Dockerfile.
3. **Every harness adapter PR must include:** a smoke test and the exact headless command you verified against the real CLI.
4. **No LLM grading on the primary score.** The only LLM in the pipeline is the blind, identity-free Code-Quality judge (SPEC §4.3).
5. **Conflicts of interest.** If you are affiliated with a harness vendor, you may not approve score-affecting PRs for that harness. Disclose in `MAINTAINERS.md`.

## PR process

- Small PRs win. One task, one adapter, or one doc change per PR.
- CI runs: ruff, mypy (non-blocking), pytest, a mock end-to-end run, and verifier self-checks on the full suite.
- Score-affecting changes additionally require a reproduction run proving no published entry re-ranks beyond its CI width.

## Reporting gaming

If you find a way to cheat a task (verifier hole, seed leakage, prompt ambiguity), open a **security-style advisory** (or email the maintainers) rather than a public issue. Confirmed gaming retires the task and credits the reporter in the changelog.
