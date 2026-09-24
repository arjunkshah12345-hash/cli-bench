"""Harness adapter base class, profile, and registry."""

from __future__ import annotations

import os
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from cli_bench.task import Task

CANONICAL_TOOLS = [
    "bash",
    "edit",
    "read",
    "write",
    "grep",
    "glob",
    "browser",
    "task",
    "other",
]


@dataclass
class HarnessProfile:
    """Declared behavior flags for a harness (shown on the leaderboard)."""

    approval_flags: list[str] = field(default_factory=list)
    plan_first: bool = False
    transcript_fidelity: str = "stdout"  # "native" | "stdout"
    backends: list[str] = field(default_factory=lambda: ["local"])
    auth_env: list[str] = field(default_factory=list)
    # "all" (default): every declared var must be set. "any": at least one —
    # for multi-provider harnesses (e.g. aider takes OPENAI_API_KEY *or*
    # ANTHROPIC_API_KEY depending on the pinned --model).
    auth_env_mode: str = "all"
    model_families: list[str] = field(default_factory=list)  # empty = multi-provider
    notes: str = ""


@dataclass
class RunResult:
    outcome: str  # "pass" | "fail" | "budget_time" | "budget_cost" | "crash" | "sabotage" | "missing"
    exit_code: int | None
    duration_s: float
    usage: dict[str, int]
    usage_estimated: bool
    stdout: str
    stderr: str


class Harness:
    """Base class for harness adapters.

    Subclasses set `name`, `version_cmd`, `prompt_mode` and implement `build_cmd`.
    """

    name: str = "abstract"
    version_cmd: list[str] = []
    prompt_mode: str = "stdin"  # stdin | argv | file
    profile: HarnessProfile = HarnessProfile()

    def build_cmd(self, ctx: Any) -> list[str]:
        raise NotImplementedError

    def effective_model(self, events: list[dict[str, Any]]) -> str | None:
        """Extract the model the harness *actually* ran, when it reports one.

        Adapters with native model ids (e.g. Claude Code's result.model_id)
        surface them as events; the runner uses this to prove the requested
        model was the effective one (SPEC §5.5). Returns None when unknown.
        """
        for ev in events:
            if ev.get("event") == "final" and ev.get("model"):
                return str(ev["model"])
        for ev in events:
            if ev.get("model"):
                return str(ev["model"])
        return None

    def prompt_text(self, task: Task) -> str:
        return task.prompt

    def parse_transcript(self, raw_lines: list[str]) -> list[dict[str, Any]]:
        """Default: emit one log event per stdout line + usage estimate (chars/4)."""
        events: list[dict[str, Any]] = []
        for i, line in enumerate(raw_lines):
            if not line.strip():
                continue
            est = estimate_text_usage(line)
            events.append(
                {
                    "ts": time.time(),
                    "event": "log",
                    "turn": i,
                    "text": line[:2000],
                    "usage": est,
                    "usage_estimated": True,
                }
            )
        return events

    def available(self) -> bool:
        return True

    def version(self) -> str:
        if not self.version_cmd:
            return "n/a"
        try:
            out = subprocess.run(self.version_cmd, capture_output=True, text=True, timeout=15, check=False)
            return (
                (out.stdout or out.stderr).strip().splitlines()[0]
                if (out.stdout or out.stderr)
                else "unknown"
            )
        except (OSError, subprocess.TimeoutExpired):
            return "unknown"


def estimate_text_usage(text: str) -> dict[str, int]:
    tokens = max(1, len(text) // 4)
    return {"input_tokens": tokens, "output_tokens": 0, "reasoning_tokens": 0, "cached_tokens": 0}


def model_family(model_id: str) -> str:
    """Coarse provider family for cohort checks (SPEC §5.5).

    Understands provider-prefixed ids ("openai/gpt-5.3") and bare ids
    ("claude-sonnet-4-5", "gemini-2.5-pro").
    """
    m = (model_id or "").lower()
    if "/" in m:
        provider, _, bare = m.rpartition("/")
        prefix_map = {
            "anthropic": "anthropic",
            "openai": "openai",
            "google": "google",
            "vertex_ai": "google",
            "xai": "xai",
            "deepseek": "other-open",
            "moonshot": "other-open",
            "kimi": "other-open",
            "qwen": "other-open",
            "glm": "other-open",
            "zai": "other-open",
            "mistral": "other-open",
        }
        if provider in prefix_map:
            return prefix_map[provider]
        m = bare
    if m.startswith("claude"):
        return "anthropic"
    if m.startswith("gpt") or m.startswith("o1") or m.startswith("o3") or "codex" in m:
        return "openai"
    if m.startswith("gemini") or m.startswith("gemma"):
        return "google"
    if m.startswith("grok"):
        return "xai"
    if m.startswith("kimi") or m.startswith("deepseek") or m.startswith("qwen"):
        return "other-open"
    return "other"


def cohort_check(harness: Harness, model_id: str) -> str | None:
    """Return an error message if the harness cannot run this model family."""
    families = getattr(harness.profile, "model_families", []) or []
    if not families:
        return None  # multi-provider harness: any model accepted
    fam = model_family(model_id)
    if fam not in families:
        return (
            f"harness {harness.name!r} runs model families {families}, not {fam!r}; "
            f"{model_id!r} is out of cohort (use --allow-incompatible to override, "
            "recorded in the manifest)"
        )
    return None


# --- registry -----------------------------------------------------------------

_REGISTRY: dict[str, Harness] | None = None


def _load_entrypoints() -> dict[str, Harness]:
    """Discover adapters in harnesses/ directory (loadable via cli_bench.external)."""
    found: dict[str, Harness] = {}
    root = Path(__file__).resolve().parent.parent / "harnesses"
    if not root.exists():
        return found
    for py in sorted(root.glob("*.py")):
        if py.name.startswith("_") or py.name == "TEMPLATE.py":
            continue
        try:
            ns: dict[str, Any] = {}
            exec(compile(py.read_text(encoding="utf-8"), str(py), "exec"), ns)
            for obj in ns.values():
                if isinstance(obj, type) and issubclass(obj, Harness) and obj is not Harness:
                    inst = obj()
                    found[inst.name] = inst
        except Exception as exc:  # noqa: BLE001 - registry must not die on one bad adapter
            print(f"[registry] failed to load {py.name}: {exc}")
    return found


def registry() -> dict[str, Harness]:
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = {}
        _REGISTRY.update(_load_entrypoints())
        # Built-in mocks always present.
        _REGISTRY.setdefault("mock-a", MockHarness("mock-a", pass_rate=1.0, speed=0.35))
        _REGISTRY.setdefault("mock-b", MockHarness("mock-b", pass_rate=0.5, speed=1.2))
    return _REGISTRY


def get_harness(name: str) -> Harness:
    reg = registry()
    if name not in reg:
        known = ", ".join(sorted(reg))
        raise KeyError(f"unknown harness {name!r} (known: {known})")
    return reg[name]


class MockHarness(Harness):
    """Deterministic mock for self-testing the runner/scoring pipeline.

    Behaves like a model that: emits some output lines, optionally fails a
    fixed fraction of (task, seed) pairs, and optionally stalls toward the
    time budget.
    """

    def __init__(self, name: str, pass_rate: float = 0.5, speed: float = 1.0, stall: float = 0.0):
        self.name = name
        self.pass_rate = pass_rate
        self.speed = speed
        self.stall = stall
        self.profile = HarnessProfile(
            approval_flags=[],
            plan_first=False,
            transcript_fidelity="stdout",
            backends=["local"],
            notes="deterministic mock harness for pipeline self-tests",
        )

    def build_cmd(self, ctx: Any) -> list[str]:
        speed = self.speed
        # CI/smoke escape hatch: shrink simulated durations ~20x.
        if os.environ.get("CBENCH_MOCK_FAST"):
            speed = speed * 0.05
        return [
            "python3",
            "-c",
            _MOCK_SCRIPT,
            self.name,
            str(self.pass_rate),
            str(speed),
            str(self.stall),
            ctx.task.id,
            str(ctx.seed),
            str(ctx.time_budget_s),
            ctx.prompt_file,
        ]

    def version(self) -> str:
        return f"mock 1.0 ({self.name})"


_MOCK_SCRIPT = r"""
import hashlib, os, random, sys, time

name, pr, speed, stall, task_id, seed, budget, prompt_file = sys.argv[1:9]
pr, speed, stall = float(pr), float(speed), float(stall)
budget = float(budget)

digest = hashlib.sha256(f"{name}|{task_id}|{seed}".encode()).hexdigest()
roll = int(digest[:8], 16) % 1000 / 1000.0

# Simulate thinking: write lines to stdout over ~speed fraction of budget
lines = max(2, int(speed * 6))
duration = min(budget * 0.5 * speed, budget * 0.9)
if stall > 0:
    duration = min(budget * stall, budget * 0.95)
for i in range(lines):
    print(f"[{name}] step {i+1}/{lines} on {task_id} seed {seed}", flush=True)
    time.sleep(duration / max(lines, 1))

passed = roll < pr
if passed:
    # a passing run leaves its work product in the workspace
    open("mock_output.txt", "w").write(f"done by {name} on {task_id} seed {seed}\n")
print(f"[{name}] done: {'PASS' if passed else 'FAIL'} (roll={roll:.3f})", flush=True)
sys.exit(0 if passed else 1)
"""


class CommandHarness(Harness):
    """Convenience base for adapters that just shell out with a prompt."""

    def build_cmd(self, ctx: Any) -> list[str]:
        cmd = list(self.cmd_template)
        if self.prompt_mode == "argv":
            cmd.append(self.prompt_text(ctx.task))
        elif self.prompt_mode == "file":
            cmd.extend(self.file_flags(ctx))
        return cmd

    def file_flags(self, ctx: Any) -> list[str]:
        return []

    cmd_template: list[str] = []
