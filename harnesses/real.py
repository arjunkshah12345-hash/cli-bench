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

import contextlib
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
            provider, sep, bare = ctx.model.rpartition("/")
            bare = bare if sep else provider  # "claude-sonnet-4-5" vs "anthropic/claude-sonnet-4-5"
            cmd.extend(self.model_flags(bare, ctx.model))
        if self.prompt_mode == "argv":
            cmd.append(self.prompt_text(ctx.task))
        elif self.prompt_mode == "flag" and self.prompt_flag:
            cmd.extend([self.prompt_flag, self.prompt_text(ctx.task)])
        return cmd

    def model_flags(self, bare: str, full: str) -> list[str]:
        """Default: standard -m/--model flag. Override for exotic CLIs."""
        return ["-m", bare]

    def available(self) -> bool:
        if not shutil.which(self.binary):
            return False
        if self.profile.auth_env_mode == "any":
            return any(os.environ.get(var) for var in self.profile.auth_env)
        return all(os.environ.get(var) for var in self.profile.auth_env)

    def missing_reason(self) -> str:
        if not shutil.which(self.binary):
            return f"binary {self.binary!r} not on PATH" + (
                f" ({self.missing_hint})" if self.missing_hint else ""
            )
        missing = [v for v in self.profile.auth_env if not os.environ.get(v)]
        if self.profile.auth_env_mode == "any":
            if self.available():
                return ""
            return f"missing env (need one of): {', '.join(missing)}"
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
                first: dict[str, Any] = next(iter(obj["modelUsage"].values()), {})
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
        "codex",
        "exec",
        "--json",
        "--skip-git-repo-check",
        "--ignore-user-config",
        "--approve-for-me",
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
            # API-key auth still works without it.
            with contextlib.suppress(OSError):
                shutil.copy2(src, home / "auth.json")
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
                    "usage": {
                        "input_tokens": 0,
                        "output_tokens": 0,
                        "reasoning_tokens": 0,
                        "cached_tokens": 0,
                    },
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
                    "usage": {
                        "input_tokens": 0,
                        "output_tokens": 0,
                        "reasoning_tokens": 0,
                        "cached_tokens": 0,
                    },
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
            raw_usage = obj.get("usage")
            u: dict[str, Any] = raw_usage if isinstance(raw_usage, dict) else {}
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
        transcript_fidelity="native",
        backends=["local", "docker"],
        auth_env=[],  # provider keys read from opencode auth config (`opencode auth login`)
        model_families=[],  # multi-provider
        notes="opencode run emits stream-json (part.started/part.updated/step_finish); "
        "step_finish carries native token counts; model via -m provider/model",
    )
    missing_hint = "npm i -g opencode-ai && opencode auth login"

    def available(self) -> bool:
        if not shutil.which(self.binary):
            return False
        # Provider credentials live in opencode's own auth store (or env).
        auth = Path.home() / ".local" / "share" / "opencode" / "auth.json"
        try:
            data = json.loads(auth.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            data = {}
        return bool(data) or any(
            os.environ.get(v) for v in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "OPENROUTER_API_KEY")
        )

    def missing_reason(self) -> str:
        if not shutil.which(self.binary):
            return f"binary {self.binary!r} not on PATH" + (
                f" ({self.missing_hint})" if self.missing_hint else ""
            )
        if self.available():
            return ""
        return "no provider credentials (run: opencode auth login)"

    def model_flags(self, bare: str, full: str) -> list[str]:
        # opencode wants provider/model form.
        return ["-m", full]

    def parse_native(self, obj: dict[str, Any]) -> dict[str, Any] | None:
        typ = obj.get("type")
        part = obj.get("part")
        if not isinstance(part, dict):
            part = {}
        ptype = part.get("type")
        if typ == "step_finish":
            tokens = obj.get("tokens")
            if not isinstance(tokens, dict):
                tokens = {}
            cache = tokens.get("cache")
            if not isinstance(cache, dict):
                cache = {}
            return {
                "ts": None,
                "event": "usage",
                "usage": {
                    "input_tokens": tokens.get("input", 0) or 0,
                    "output_tokens": tokens.get("output", 0) or 0,
                    "reasoning_tokens": tokens.get("reasoning", 0) or 0,
                    "cached_tokens": cache.get("read", 0) or 0,
                },
                "usage_estimated": False,
            }
        if typ == "text" and ptype == "text":
            text = str(part.get("text", ""))
            return {
                "ts": None,
                "event": "log",
                "text": text[:2000],
                "usage": estimate_text_usage(text),
                "usage_estimated": True,
            }
        if typ == "tool" and ptype == "tool":
            return {
                "ts": None,
                "event": "tool",
                "tool": _canonical_tool(str(part.get("tool", ""))),
                "text": str(part.get("tool", ""))[:200],
                "usage": {"input_tokens": 0, "output_tokens": 0, "reasoning_tokens": 0, "cached_tokens": 0},
            }
        if typ == "error":
            err = str(obj.get("error") or part.get("error") or "unknown")
            return {
                "ts": None,
                "event": "log",
                "text": f"[error] {err}"[:2000],
                "usage": estimate_text_usage(err),
                "usage_estimated": True,
            }
        # step_start / part.started / part.updated / log lines: not needed.
        return None


class CursorAgent(CLIHarness):
    name = "cursor-agent"
    binary = "cursor-agent"
    version_cmd = ["cursor-agent", "--version"]
    prompt_mode = "argv"
    # Probed against 2026.09.26: -p is headless print mode; --trust pre-accepts
    # the workspace-trust prompt (headless --print cannot show it — without a
    # trusted workspace the process exits 0 with no output at all); --force
    # auto-approves tool calls. The init event names the effective model and
    # the result event carries native usage (SPEC 5.5).
    cmd_template = ["cursor-agent", "-p", "--trust", "--force"]
    profile = HarnessProfile(
        approval_flags=["--trust (workspace trust pre-accepted)", "--force (tool auto-approval)"],
        plan_first=False,
        transcript_fidelity="native",
        backends=["local"],
        auth_env=["CURSOR_API_KEY"],
        model_families=[],  # multi-provider via Cursor's routing
        notes="headless stream-json print mode; --trust skips the workspace-trust "
        "prompt that silently kills unattended runs; --force auto-approves; "
        "model via --model (init event proves the effective model, SPEC 5.5)",
    )
    missing_hint = "curl cursor.com/install && cursor-agent login"

    def available(self) -> bool:
        """CURSOR_API_KEY, or the CLI's own subscription login (cli-config authInfo)."""
        if not shutil.which(self.binary):
            return False
        if os.environ.get("CURSOR_API_KEY"):
            return True
        cfg = Path.home() / ".cursor" / "cli-config.json"
        try:
            auth = (json.loads(cfg.read_text(encoding="utf-8")) or {}).get("authInfo") or {}
        except (OSError, json.JSONDecodeError):
            return False
        return bool(auth.get("userId"))

    def missing_reason(self) -> str:
        if not shutil.which(self.binary):
            return f"binary {self.binary!r} not on PATH" + (" (curl cursor.com/install)")
        if self.available():
            return ""
        return "no CURSOR_API_KEY and no subscription login (run: cursor-agent login)"

    def model_flags(self, bare: str, full: str) -> list[str]:
        # Probed: bare cursor slug ("gpt-5.6-luna" → init model "GPT-5.6 Luna").
        return ["--model", bare]

    def parse_native(self, obj: dict[str, Any]) -> dict[str, Any] | None:
        typ = obj.get("type")
        if typ == "system":
            ev: dict[str, Any] = {
                "ts": None,
                "event": "log",
                "text": f"init model={obj.get('model', '')}"[:200],
                "usage": {"input_tokens": 0, "output_tokens": 0, "reasoning_tokens": 0, "cached_tokens": 0},
            }
            if obj.get("model"):
                ev["model"] = str(obj["model"])
            return ev
        if typ == "result":
            u = obj.get("usage")
            if not isinstance(u, dict):
                u = {}
            return {
                "ts": None,
                "event": "final",
                "text": str(obj.get("result", ""))[:2000],
                "usage": {
                    "input_tokens": u.get("inputTokens", 0) or 0,
                    "output_tokens": u.get("outputTokens", 0) or 0,
                    "reasoning_tokens": 0,
                    "cached_tokens": u.get("cacheReadTokens", 0) or 0,
                },
                "usage_estimated": False,
            }
        if typ == "tool_call":
            call = obj.get("tool_call")
            if not isinstance(call, dict):
                call = {}
            shell = call.get("shellToolCall")
            if not isinstance(shell, dict):
                shell = {}
            tool = str(shell.get("command", "") or "edit")
            return {
                "ts": None,
                "event": "tool",
                "tool": _canonical_tool("bash" if shell else "edit"),
                "text": tool[:200],
                "usage": {"input_tokens": 0, "output_tokens": 0, "reasoning_tokens": 0, "cached_tokens": 0},
            }
        if typ == "error":
            err = str(obj.get("error") or obj.get("message") or "unknown")
            return {
                "ts": None,
                "event": "log",
                "text": f"[error] {err}"[:2000],
                "usage": estimate_text_usage(err),
                "usage_estimated": True,
            }
        # user / assistant / thinking events: informative but not load-bearing.
        return None


class Droid(CLIHarness):
    name = "droid"
    binary = "droid"
    version_cmd = ["droid", "--version"]
    prompt_mode = "argv"
    # Probed against droid 0.225.2: `droid exec full-auto` is not a valid
    # subcommand; autonomy is --auto <low|medium|high> and native events need
    # -o stream-json. The init event names the effective model (SPEC 5.5).
    cmd_template = ["droid", "exec", "-o", "stream-json", "--auto", "medium"]
    profile = HarnessProfile(
        approval_flags=["--auto medium (autonomous file edits + commands; no network)"],
        plan_first=False,
        transcript_fidelity="native",
        backends=["local"],
        auth_env=["FACTORY_API_KEY"],
        model_families=[],  # multi-provider
        notes="droid exec stream-json (0.22x schema); native init event reports the "
        "effective model; model via -m/--model",
    )
    missing_hint = "curl -fsSL https://app.factory.ai/cli | sh && droid exec login"

    def model_flags(self, bare: str, full: str) -> list[str]:
        return ["-m", full]

    def parse_native(self, obj: dict[str, Any]) -> dict[str, Any] | None:
        typ = obj.get("type")
        if typ == "system":
            ev: dict[str, Any] = {
                "ts": None,
                "event": "log",
                "text": f"init tools={len(obj.get('tools', []) or [])}"[:200],
                "usage": {"input_tokens": 0, "output_tokens": 0, "reasoning_tokens": 0, "cached_tokens": 0},
            }
            if obj.get("model"):
                ev["model"] = str(obj["model"])
            return ev
        data = obj.get("data")
        if not isinstance(data, dict):
            data = obj
        dtype = data.get("type")
        if dtype == "error" or (typ == "error"):
            err = str(data.get("message") or obj.get("message") or "unknown")
            return {
                "ts": None,
                "event": "log",
                "text": f"[error] {err}"[:2000],
                "usage": estimate_text_usage(err),
                "usage_estimated": True,
            }
        return None


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
        auth_env=["OPENAI_API_KEY", "ANTHROPIC_API_KEY"],
        auth_env_mode="any",  # one key suffices, matching the pinned --model provider
        model_families=[],  # multi-provider
        notes="pair-programmer mode; multi-provider; model via --model; needs the key for whichever provider the pinned model uses",
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

    def available(self) -> bool:
        if not shutil.which(self.binary):
            return False
        # goose needs a configured provider: its config file or a provider key.
        for cfg in (Path.home() / ".config" / "goose" / "config.yaml",):
            if cfg.exists():
                return True
        return any(os.environ.get(v) for v in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "OPENROUTER_API_KEY"))

    def missing_reason(self) -> str:
        if not shutil.which(self.binary):
            return f"binary {self.binary!r} not on PATH" + (
                f" ({self.missing_hint})" if self.missing_hint else ""
            )
        if self.available():
            return ""
        return "no provider configured (run: goose configure, or set OPENAI_API_KEY)"

    def model_flags(self, bare: str, full: str) -> list[str]:
        return ["--model", full]


class PrimeAgent(CLIHarness):
    """Prime Intellect's RLM harness (probed against 0.9.1).

    Headless contract: `prime-agent -p --mode json` with the prompt as a
    positional argument. Provider auth lives in prime-agent's own login store
    (no env var contract), so available() checks the store instead.
    """

    name = "prime-agent"
    binary = "prime-agent"
    version_cmd = ["prime-agent", "--version"]
    prompt_mode = "argv"
    cmd_template = ["prime-agent", "--print", "--mode", "json", "--no-session"]
    profile = HarnessProfile(
        approval_flags=["--print (non-interactive; tool use auto-approved in print mode)"],
        plan_first=False,
        transcript_fidelity="stdout",
        backends=["local"],
        auth_env=[],  # provider login is prime-agent's own stored credential
        model_families=[],  # multi-provider
        notes="Prime Intellect RLM harness; JSON print mode; model via --model; "
        "auth via prime-agent /login (OAuth or API key)",
    )
    missing_hint = "npm i -g prime-agent && prime-agent (then /login)"

    def model_flags(self, bare: str, full: str) -> list[str]:
        return ["--model", bare]

    def available(self) -> bool:
        if not shutil.which(self.binary):
            return False
        if os.environ.get("PRIME_API_KEY"):
            return True
        home = Path.home()
        return any(store.is_dir() for store in (home / ".config" / "prime-agent", home / ".prime-agent"))

    def missing_reason(self) -> str:
        if not shutil.which(self.binary):
            return f"binary {self.binary!r} not on PATH" + (
                f" ({self.missing_hint})" if self.missing_hint else ""
            )
        if self.available():
            return ""
        return "no provider login (run: prime-agent, then /login)"


ALL: list[type[CLIHarness]] = [
    ClaudeCode,
    Codex,
    OpenCode,
    CursorAgent,
    Droid,
    GeminiCli,
    Aider,
    Goose,
    PrimeAgent,
]
