"""TEMPLATE.py — copy me to implement a new harness adapter.

Minimal contract (SPEC §8):

    class MyAgent(CLIHarness):
        name = "myagent"                # unique, lowercase
        binary = "myagent"              # executable on PATH
        version_cmd = ["myagent", "--version"]
        prompt_mode = "argv"            # argv | flag
        cmd_template = ["myagent", "--headless"]   # prompt is appended (or flag+prompt)
        profile = HarnessProfile(
            approval_flags=["--headless"],
            transcript_fidelity="stdout",          # or "native" if you parse logs
            backends=["local", "docker"],
            auth_env=["MYAGENT_API_KEY"],
            notes="what a reviewer should know",
        )
        missing_hint = "npm i -g myagent"

If your CLI emits native JSON events, override parse_native(obj) — see
ClaudeCode in real.py. Otherwise stdout lines become log events with
estimated usage automatically.

PR checklist:
- [ ] smoke test included (tests/test_adapters.py style)
- [ ] headless mode documented (no TUI driving)
- [ ] approval flags declared honestly in profile
"""

from cli_bench.harness import HarnessProfile
from harnesses.real import CLIHarness


class MyAgent(CLIHarness):
    name = "myagent"
    binary = "myagent"
    version_cmd = ["myagent", "--version"]
    prompt_mode = "argv"
    cmd_template = ["myagent", "--headless"]
    profile = HarnessProfile(
        approval_flags=["--headless"],
        plan_first=False,
        transcript_fidelity="stdout",
        backends=["local", "docker"],
        auth_env=["MYAGENT_API_KEY"],
        notes="example adapter",
    )
    missing_hint = "npm i -g myagent"
