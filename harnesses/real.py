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
import tempfile
from pathlib import Path
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
        # Model pinning: pass the requested model to every CLI that accepts a
        # model flag (SPEC §5.5). The runner additionally hard-fails when a
        # harness's native report contradicts the requested model.
        if ctx.model:
            provider, _, bare = ctx.model.rpartition("/")
            bare = bare or provider  # "claude-sonnet-4-5" vs "anthropic/claude-sonnet-4-5"
            cmd.extend(self.model_flags(bare, ctx.model))
        if self.prompt_mode == "argv":
            cmd.append(self.prompt_text(ctx.task))
        elif self.prompt_mode == "flag":
            cmd.extend([self.prompt_flag, self.prompt_text(ctx.task)])
        return cmd

    def model_flags(self, bare: str, full: str) -> list[str]:
        """Default: standard -m/--model flag. Override for exotic CLIs."""
        return ["-m", bare]

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
        model_families=["anthropic"],
        notes="headless print mode; stream-json events parsed natively; model via --model",
    )
    missing_hint = "npm i -g @anthropic-ai/claude-code"

    def model_flags(self, bare: str, full: str) -> list[str]:
        return ["--model", bare]

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
            ev = {"ts": None, "event": "final", "exit": 0 if obj.get("is_error") is False else 1}
            if obj.get("modelUsage"):
                first = next(iter(obj["modelUsage"].values()), {})
                if first.get("model"):
                    ev["model"] = str(first["model"])
            elif obj.get("model"):
                ev["model"] = str(obj["model"])
            return ev
        return None


class Codex(CLIHarness):
    """codex exec --json (verified against codex 0.153.0).

    Isolation: CODEX_HOME is redirected to a throwaway copy holding only
    auth.json, so the user's ~/.codex/config.toml, AGENTS.md, agentguide.md,
    skills and session history cannot leak into a benchmark trial. The user
    profile is *not* part of the harness under test.

    Model pinning: -m <bare slug> (codex rejects provider-prefixed ids under
    ChatGPT auth). The effective model is *proven* post-run from the session
    rollout file (turn_context.payload.model), not assumed.
    """

    name = "codex"
    binary = "codex"
    version_cmd = ["codex", "--version"]
    prompt_mode = "argv"
    cmd_template = [
        "codex", "exec", "--json", "--skip-git-repo-check",
        "--ignore-user-config", "--approve-for-me",
    ]
    profile = HarnessProfile(
        approval_flags=["--approve-for-me (implies workspace-write sandbox)"],
        plan_first=False,
        transcript_fidelity="native",
        backends=["local"],
        auth_env=["OPENAI_API_KEY"],  # satisfied either by an API key or `codex login`
        model_families=["openai"],
        notes="codex exec --json (0.15x schema); CODEX_HOME sandboxed per trial; "
        "effective model proven from session rollout (SPEC 5.5)",
    )
    missing_hint = "npm i -g @openai/codex && codex login"

    def __init__(self) -> None:
        super().__init__()
        self._homes: list[Path] = []  # CODEX_HOME copies made per trial

    def available(self) -> bool:
        if not shutil.which(self.binary):
            return False
        if os.environ.get("OPENAI_API_KEY"):
            return True
        # ChatGPT-mode login: codex stores OAuth tokens in ~/.codex/auth.json.
        auth = Path.home() / ".codex" / "auth.json"
        try:
            data = json.loads(auth.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return False
        return bool(data.get("tokens", {}).get("access_token"))

    def missing_reason(self) -> str:
        if not shutil.which(self.binary):
            return f"binary {self.binary!r} not on PATH" + (
                f" ({self.missing_hint})" if self.missing_hint else ""
            )
        if self.available():
            return ""
        return "no OPENAI_API_KEY and no ChatGPT login (run: codex login)"

    def command_env(self) -> dict[str, str]:
        """Fresh CODEX_HOME per trial: auth only, zero user config/skills."""
        home = Path(tempfile.mkdtemp(prefix="cbench-codex-home-"))
        src = Path.home() / ".codex" / "auth.json"
        if src.exists():
            try:
                shutil.copy2(src, home / "auth.json")
            except OSError:
                pass  # API-key auth still works without it
        self._homes.append(home)
        return {"CODEX_HOME": str(home)}

    def model_flags(self, bare: str, full: str) -> list[str]:
        # codex -m takes the bare slug ("gpt-5.6-luna"), not "openai/gpt-5.6-luna".
        return ["-m", bare]

    # --- transcript parsing (codex exec --json, 0.15x event schema) ---------

    def parse_native(self, obj: dict[str, Any]) -> dict[str, Any] | None:
        typ = obj.get("type")
        item = obj.get("item") if isinstance(obj.get("item"), dict) else {}
        if typ == "thread.started":
            return {"ts": None, "event": "thread", "thread_id": str(obj.get("thread_id", ""))}
        if typ == "item.completed" and item:
            itype = item.get("type")
            if itype == "agent_message":
                text = str(item.get("text", ""))
                return {
                    "ts": None,
                    "event": "log",
                    "text": text[:2000],
                    "usage": estimate_text_usage(text),
                    "usage_estimated": True,
                }
            if itype == "command_execution":
                return {
                    "ts": None,
                    "event": "tool",
                    "tool": "bash",
                    "text": str(item.get("command", ""))[:300],
                    "usage": {"input_tokens": 0, "output_tokens": 0, "reasoning_tokens": 0, "cached_tokens": 0},
                }
            if itype == "file_change":
                paths = ",".join(
                    str(c.get("path", "")) for c in item.get("changes", []) if isinstance(c, dict)
                )
                return {
                    "ts": None,
                    "event": "tool",
                    "tool": "edit",
                    "text": paths[:300],
                    "usage": {"input_tokens": 0, "output_tokens": 0, "reasoning_tokens": 0, "cached_tokens": 0},
                }
            if itype == "error":
                return {
                    "ts": None,
                    "event": "log",
                    "text": f"[error] {item.get('message', '')}"[:2000],
                    "usage": estimate_text_usage(str(item.get("message", ""))),
                    "usage_estimated": True,
                }
            return None
        if typ == "turn.completed":
            u = obj.get("usage") if isinstance(obj.get("usage"), dict) else {}
            return {
                "ts": None,
                "event": "usage",
                "usage": {
                    "input_tokens": u.get("input_tokens", 0) or 0,
                    "output_tokens": u.get("output_tokens", 0) or 0,
                    "reasoning_tokens": u.get("reasoning_output_tokens", 0) or 0,
                    "cached_tokens": u.get("cached_input_tokens", 0) or 0,
                },
                "usage_estimated": False,
            }
        # Legacy (pre-0.15) schema, kept for older pinned codex builds.
        msg = obj.get("msg", {})
        mtype = msg.get("type", obj.get("type"))
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
        return None

    # --- effective-model proof (SPEC 5.5) ------------------------------------

    def effective_model(self, events: list[dict[str, Any]]) -> str | None:
        # thread.started -> session rollout file -> turn_context.payload.model
        thread_id = next((e["thread_id"] for e in events if e.get("thread_id")), None)
        if thread_id:
            m = self._model_from_rollout(thread_id)
            if m:
                return m
        return super().effective_model(events)

    def _model_from_rollout(self, thread_id: str) -> str | None:
        homes = list(self._homes)
        env_home = os.environ.get("CODEX_HOME")
        if env_home:
            homes.append(Path(env_home))
        homes.append(Path.home() / ".codex")
        for home in homes:
            sessions = home / "sessions"
            if not sessions.exists():
                continue
            for p in sorted(sessions.rglob(f"*{thread_id}.jsonl")):
                try:
                    for line in p.read_text(encoding="utf-8").splitlines():
                        if '"turn_context"' not in line:
                            continue
                        obj = json.loads(line)
                        if obj.get("type") == "turn_context":
                            m = (obj.get("payload") or {}).get("model")
                            if m:
                                return str(m)
                except (OSError, json.JSONDecodeError):
                    continue
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
        model_families=[],  # multi-provider
        notes="opencode run; multi-provider; model via -m provider/model",
    )
    missing_hint = "npm i -g opencode-ai"

    def model_flags(self, bare: str, full: str) -> list[str]:
        # opencode wants provider/model form.
        return ["-m", full]


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
        model_families=[],  # multi-provider
        notes="headless print mode; --force auto-approves; model via --model",
    )
    missing_hint = "curl cursor.com/install"

    def model_flags(self, bare: str, full: str) -> list[str]:
        return ["--model", full]


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
        model_families=[],  # multi-provider
        notes="factory droid exec; full-auto approval; model via -m/--model",
    )
    missing_hint = "curl -fsSL https://app.factory.ai/cli | sh"

    def model_flags(self, bare: str, full: str) -> list[str]:
        return ["-m", full]


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
        model_families=["google"],
        notes="non-interactive print mode; --yolo auto-approves; model via -m/--model",
    )
    missing_hint = "npm i -g @google/gemini-cli"

    def model_flags(self, bare: str, full: str) -> list[str]:
        return ["-m", bare]


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
    ]
    prompt_flag = "--message"
    prompt_mode = "flag"
    profile = HarnessProfile(
        approval_flags=["--yes-always"],
        plan_first=False,
        transcript_fidelity="stdout",
        backends=["local", "docker"],
        auth_env=["OPENAI_API_KEY", "ANTHROPIC_API_KEY"],  # one of, per --model
        model_families=[],  # multi-provider
        notes="pair-programmer mode; multi-provider; model via --model",
    )
    missing_hint = "python -m pip install aider-install && aider-install"

    def model_flags(self, bare: str, full: str) -> list[str]:
        return ["--model", full]


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
        model_families=[],  # multi-provider
        notes="block/_square goose run; multi-provider; model via --model flag (GOOSE_MODEL fallback)",
    )
    missing_hint = "curl -fsSL https://github.com/block/goose/releases/download/stable/download_cli.sh | bash"

    def model_flags(self, bare: str, full: str) -> list[str]:
        return ["--model", full]


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
