# Adding a harness

Adapters are small Python classes in `harnesses/`. Copy [TEMPLATE.py](../harnesses/TEMPLATE.py) and fill in six fields:

```python
from cli_bench.harness import HarnessProfile
from harnesses.real import CLIHarness


class MyAgent(CLIHarness):
    name = "myagent"  # unique, lowercase; becomes leaderboard key
    binary = "myagent"  # must be on PATH; checked by available()
    version_cmd = ["myagent", "--version"]
    prompt_mode = "argv"  # "argv" appends prompt; "flag" uses prompt_flag
    cmd_template = ["myagent", "--headless", "--yes"]
    prompt_flag = "--task"  # only for prompt_mode = "flag"
    profile = HarnessProfile(
        approval_flags=["--yes"],  # declared honestly, shown on the leaderboard
        transcript_fidelity="stdout",  # or "native" if you parse structured logs
        backends=["local", "docker"],
        auth_env=["MYAGENT_API_KEY"],  # runner fails fast with missing_reason()
        notes="one line a reviewer should know",
    )
    missing_hint = "npm i -g myagent"  # shown when binary/env missing
```

## Rules

1. **Headless only.** The adapter must run the CLI in its documented non-interactive mode. No TUI driving, no pty scraping.
2. **Default-adjacent config.** Approval/agency flags are allowed (declare them), but config that pre-seeds task knowledge (memories, skill folders) is not. Profile must list any directories the harness reads at startup.
3. **Parse what you can.** If the CLI emits JSON events, implement `parse_native(obj)` (see `ClaudeCode` in `real.py`) and set `transcript_fidelity="native"`. Otherwise stdout lines become `log` events with estimated usage — fine, but flagged on the leaderboard.
4. **Smoke test required.** Add a test that runs your adapter's `build_cmd` against a trivial ctx and asserts the argv shape. See `tests/test_adapters.py`.

## Checklist before opening a PR

- [ ] `name` is unique; `binary` is the real executable name
- [ ] headless invocation verified against the real CLI (paste the command in the PR)
- [ ] approval flags match what a power user would set for autonomous work
- [ ] `auth_env` lists every required variable; `missing_reason()` message is actionable
- [ ] smoke test added and green
- [ ] `harnesses/real.py` `ALL` list updated (if added there rather than a new module)

The registry auto-discovers adapters in `harnesses/*.py` (files starting with `_` and `TEMPLATE.py` are skipped).
