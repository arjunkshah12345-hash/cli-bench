"""Real-world CLI harness adapters.

Each adapter runs its CLI headless with a single task prompt. Auth is assumed
pre-configured by the operator; `available()` checks the binary is on PATH and
declared env vars exist. Profiles record approval flags so a "max-agency"
config is never silently compared to a "guarded" one (SPEC §3).

Transcript parsing: adapters with native event logs parse them; all others
fall back to the stdout log-event stream (SPEC §5.3). Capability differences
in logging fidelity are themselves recorded in the profile.
"""

from __future__ import annotations

import json
import os
import shutil
from typing import Any

from cli_bench.harness import CommandHarness, HarnessProfile, estimate_text_usage

_TOOL_MAP = {
    "bash": "bash",
    "shell": "bash",
    "terminal": "bash",
    "command": "bash",
    "edit": "edit",
    "edit_file": "edit",
    "str_replace_editor": "edit",
    "apply_patch": "edit",
    "write": "write",
    "write_file": "write",
    "create_file": "write",
    "read": "read",
    "read_file": "read",
    "view": "read",
    "grep": "grep",
    "search": "grep",
    "glob": "glob",
    "find": "glob",
    "browser": "browser",
    "task": "task",
    "agent": "task",
}


def _canonical_tool(raw: str) -> str:
    raw = (raw or "").lower().strip()
    if raw.startswith("mcp:"):
        return raw
    for key, canon in _TOOL_MAP.items():
        if raw == key:
            return canon
    return "other"


class CLIHarness(CommandHarness):
    """Shared implementation for shelling out to a real CLI."""

    binary: str = ""
    missing_hint: str = ""
    prompt_flag: str | None = None  # when prompt_mode == "flag"
    extra_env: dict[str, str] = {}

    def build_cmd(self, ctx: Any) -> list[str]:
        cmd = list(self.cmd_template)
        if self.prompt_mode == "argv":
            cmd.append(self.prompt_text(ctx.task))
        elif self.prompt_mode == "flag":
            cmd.extend([self.prompt_flag, self.prompt_text(ctx.task)])
        return cmd

    def available(self) -> bool:
        if not shutil.which(self.binary):
            return False
        return all(os.environ.get(var) for var in self.profile.auth_env)

    def missing_reason(self) -> str:
        if not shutil.which(self.binary):
            return f"binary {self.binary!r} not on PATH" + (
                f" ({self.missing_hint})" if self.missing_hint else ""
            )
        missing = [v for v in self.profile.auth_env if not os.environ.get(v)]
        return f"missing env: {', '.join(missing)}" if missing else ""

    def version(self) -> str:
        if not self.version_cmd:
            return "n/a"
        try:
            import subprocess

            out = subprocess.run(self.version_cmd, capture_output=True, text=True, timeout=15, check=False)
            first = (out.stdout or out.stderr).strip().splitlines()
            return first[0] if first else "unknown"
        except (OSError, ValueError):
            return "unknown"

    def parse_transcript(self, raw_lines: list[str]) -> list[dict[str, Any]]:
        """Default real-harness parser: stdout log events + estimated usage.

        Adapters with native JSONL logs override parse_events() instead.
        """
        events: list[dict[str, Any]] = []
        for i, line in enumerate(raw_lines):
            parsed = self.parse_event_line(line)
            if parsed is not None:
                events.append(parsed)
                continue
            est = estimate_text_usage(line)
            events.append(
                {
                    "ts": None,
                    "event": "log",
                    "turn": i,
                    "text": line[:2000],
                    "usage": est,
                    "usage_estimated": True,
                }
            )
        return events

    def parse_event_line(self, line: str) -> dict[str, Any] | None:
        """Return a transcript event if the line is a native JSON event, else None."""
        line = line.strip()
        if not line.startswith("{"):
            return None
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            return None
        if not isinstance(obj, dict):
            return None
        return self.parse_native(obj)

    def parse_native(self, obj: dict[str, Any]) -> dict[str, Any] | None:
        return None  # override in adapters with known native schemas


# --- adapters ------------------------------------------------------------------


class ClaudeCode(CLIHarness):
    name = "claude-code"
    binary = "claude"
    version_cmd = ["claude", "--version"]
    prompt_mode = "argv"
    cmd_template = ["claude", "-p", "--output-format", "stream-json", "--verbose"]
    profile = HarnessProfile(
        approval_flags=["--dangerously-skip-permissions"],
        plan_first=False,
        transcript_fidelity="native",
        backends=["local", "docker"],
        auth_env=["ANTHROPIC_API_KEY"],
        notes="headless print mode; stream-json events parsed natively",
    )
    missing_hint = "npm i -g @anthropic-ai/claude-code"

    def build_cmd(self, ctx: Any) -> list[str]:
        cmd = super().build_cmd(ctx)
        # Full agency: auto-approve in the sandboxed workspace.
        if "--dangerously-skip-permissions" not in cmd:
            cmd.insert(2, "--dangerously-skip-permissions")
        return cmd

    def parse_native(self, obj: dict[str, Any]) -> dict[str, Any] | None:
        etype = obj.get("type")
        if etype == "assistant":
            msg = obj.get("message", {})
            usage = msg.get("usage", {})
            ev: dict[str, Any] = {
                "ts": None,
                "event": "turn",
                "turn": obj.get("turn", 0),
                "usage_estimated": False,
            }
            for block in msg.get("content", []) or []:
                if block.get("type") == "tool_use":
                    ev["tool"] = _canonical_tool(block.get("name", ""))
            if usage:
                ev["usage"] = {
                    "input_tokens": usage.get("input_tokens", 0),
                    "output_tokens": usage.get("output_tokens", 0),
                    "reasoning_tokens": usage.get("reasoning_tokens", 0) or 0,
                    "cached_tokens": (usage.get("cache_read_input_tokens", 0) or 0)
                    + (usage.get("cache_creation_input_tokens", 0) or 0),
                }
            return ev
        if etype == "result":
            return {"ts": None, "event": "final", "exit": 0 if obj.get("is_error") is False else 1}
        return None


class Codex(CLIHarness):
    name = "codex"
    binary = "codex"
    version_cmd = ["codex", "--version"]
    prompt_mode = "argv"
    cmd_template = ["codex", "exec", "--json", "--skip-git-repo-check", "--full-auto"]
    profile = HarnessProfile(
        approval_flags=["--full-auto"],
        plan_first=False,
        transcript_fidelity="native",
        backends=["local", "docker"],
        auth_env=["OPENAI_API_KEY"],
        notes="codex exec; experimental JSON events parsed when stable",
    )
    missing_hint = "npm i -g @openai/codex"

    def parse_native(self, obj: dict[str, Any]) -> dict[str, Any] | None:
        # codex exec --json emits {"id","msg":{"type":"agent_message"|...}}
        msg = obj.get("msg", {})
        mtype = msg.get("type", obj.get("type"))
        if mtype == "agent_message":
            return {
                "ts": None,
                "event": "log",
                "text": str(msg.get("message", ""))[:2000],
                "usage": estimate_text_usage(str(msg.get("message", ""))),
                "usage_estimated": True,
            }
        if mtype == "token_count":
            info = msg.get("info") or {}
            total = info.get("total_token_usage", {})
            return {
                "ts": None,
                "event": "usage",
                "usage": {
                    "input_tokens": total.get("input_tokens", 0) or 0,
                    "output_tokens": total.get("output_tokens", 0) or 0,
                    "reasoning_tokens": total.get("reasoning_output_tokens", 0) or 0,
                    "cached_tokens": total.get("cached_input_tokens", 0) or 0,
                },
                "usage_estimated": False,
            }
        if mtype == "task_complete":
            return {"ts": None, "event": "final", "exit": 0}
        return None


class OpenCode(CLIHarness):
    name = "opencode"
    binary = "opencode"
    version_cmd = ["opencode", "--version"]
    prompt_mode = "argv"
    cmd_template = ["opencode", "run", "--print-logs"]
    profile = HarnessProfile(
        approval_flags=[],
        plan_first=False,
        transcript_fidelity="stdout",
        backends=["local", "docker"],
        auth_env=[],  # provider keys read from opencode auth config
        notes="opencode run; provider auth via `opencode auth login`",
    )
    missing_hint = "npm i -g opencode-ai"


class CursorAgent(CLIHarness):
    name = "cursor-agent"
    binary = "cursor-agent"
    version_cmd = ["cursor-agent", "--version"]
    prompt_mode = "argv"
    cmd_template = ["cursor-agent", "-p", "--force"]
    profile = HarnessProfile(
        approval_flags=["--force"],
        plan_first=False,
        transcript_fidelity="stdout",
        backends=["local", "docker"],
        auth_env=["CURSOR_API_KEY"],
        notes="headless print mode; --force auto-approves edits/commands",
    )
    missing_hint = "curl cursor.com/install"


class Droid(CLIHarness):
    name = "droid"
    binary = "droid"
    version_cmd = ["droid", "--version"]
    prompt_mode = "argv"
    cmd_template = ["droid", "exec", "full-auto"]
    profile = HarnessProfile(
        approval_flags=["full-auto"],
        plan_first=False,
        transcript_fidelity="stdout",
        backends=["local", "docker"],
        auth_env=["FACTORY_API_KEY"],
        notes="factory droid exec; full-auto approval level",
    )
    missing_hint = "curl -fsSL https://app.factory.ai/cli | sh"


class GeminiCli(CLIHarness):
    name = "gemini"
    binary = "gemini"
    version_cmd = ["gemini", "--version"]
    prompt_mode = "argv"
    cmd_template = ["gemini", "-p", "--yolo"]
    profile = HarnessProfile(
        approval_flags=["--yolo"],
        plan_first=False,
        transcript_fidelity="stdout",
        backends=["local", "docker"],
        auth_env=["GEMINI_API_KEY"],
        notes="non-interactive print mode; --yolo auto-approves tools",
    )
    missing_hint = "npm i -g @google/gemini-cli"


class Aider(CLIHarness):
    name = "aider"
    binary = "aider"
    version_cmd = ["aider", "--version"]
    prompt_mode = "argv"
    cmd_template = [
        "aider",
        "--yes-always",
        "--no-git",
        "--no-pretty",
        "--no-stream",
        "--message",
    ]
    profile = HarnessProfile(
        approval_flags=["--yes-always"],
        plan_first=False,
        transcript_fidelity="stdout",
        backends=["local", "docker"],
        auth_env=["OPENAI_API_KEY", "ANTHROPIC_API_KEY"],  # one of, per --model
        notes="pair-programmer mode; message passed via --message",
    )
    missing_hint = "python -m pip install aider-install && aider-install"


class Goose(CLIHarness):
    name = "goose"
    binary = "goose"
    version_cmd = ["goose", "--version"]
    prompt_mode = "argv"
    cmd_template = ["goose", "run", "-t"]
    profile = HarnessProfile(
        approval_flags=[],
        plan_first=False,
        transcript_fidelity="stdout",
        backends=["local", "docker"],
        auth_env=[],
        notes="block/_square goose run; provider auth via goose configure",
    )
    missing_hint = "curl -fsSL https://github.com/block/goose/releases/download/stable/download_cli.sh | bash"


ALL: list[type[CLIHarness]] = [
    ClaudeCode,
    Codex,
    OpenCode,
    CursorAgent,
    Droid,
    GeminiCli,
    Aider,
    Goose,
]
