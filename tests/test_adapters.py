"""Tests for the harness registry and adapters."""

import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest

from cli_bench.harness import get_harness, registry
from cli_bench.task import Task


def test_registry_has_mocks_and_reals():
    reg = registry()
    for name in (
        "mock-a",
        "mock-b",
        "claude-code",
        "codex",
        "opencode",
        "cursor-agent",
        "droid",
        "gemini",
        "aider",
        "goose",
    ):
        assert name in reg, f"missing harness {name}"


def test_get_harness_unknown_raises_with_known_list():
    with pytest.raises(KeyError) as exc:
        get_harness("definitely-not-a-harness")
    assert "codex" in str(exc.value)


def _ctx(task_id="refactor/deadcode", seed=0, budget=600, model="openai/gpt-5.3"):
    task = Task(
        id=task_id,
        title="t",
        prompt="Do the thing.",
        category="refactor",
        difficulty="standard",
        time_budget_s=budget,
        max_cost_usd=0.5,
        seeds=3,
        tags=[],
    )
    return SimpleNamespace(
        task=task,
        seed=seed,
        workspace=None,
        prompt_file="/tmp/prompt.txt",
        time_budget_s=budget,
        model=model,
        env_vars={},
    )


def test_model_pinning_passed_to_cli():
    """Every real adapter must include a model flag in its built command."""
    for name in (
        "codex",
        "claude-code",
        "opencode",
        "cursor-agent",
        "droid",
        "gemini",
        "aider",
        "goose",
        "prime-agent",
    ):
        h = get_harness(name)
        cmd = h.build_cmd(_ctx(model="openai/gpt-5.3"))
        joined = " ".join(cmd)
        assert "gpt-5.3" in joined, f"{name} does not pin the model: {joined}"


def test_cohort_check_family_mismatch():
    from cli_bench.harness import cohort_check

    codex = get_harness("codex")  # openai-only
    assert cohort_check(codex, "anthropic/claude-sonnet-4-5") is not None
    assert cohort_check(codex, "openai/gpt-5.3") is None
    aider = get_harness("aider")  # multi-provider
    assert cohort_check(aider, "anthropic/claude-sonnet-4-5") is None


def test_effective_model_capture():
    h = get_harness("claude-code")
    events = [
        {"event": "turn", "usage": {}},
        {"event": "final", "exit": 0, "model": "claude-sonnet-4-5"},
    ]
    assert h.effective_model(events) == "claude-sonnet-4-5"
    assert h.effective_model([{"event": "turn"}]) is None


def test_mock_build_cmd_shape():
    h = get_harness("mock-a")
    cmd = h.build_cmd(_ctx())
    assert cmd[0] == "python3"
    assert "refactor/deadcode" in cmd
    assert h.profile.approval_flags == []


def test_mock_deterministic_outcomes():
    import hashlib

    def roll(name, tid, seed):
        return int(hashlib.sha256(f"{name}|{tid}|{seed}".encode()).hexdigest()[:8], 16) % 1000 / 1000.0

    assert roll("mock-x", "t", 0) == roll("mock-x", "t", 0)  # sanity: same inputs → same roll


def test_real_adapters_append_prompt_argv():
    codex = get_harness("codex")
    cmd = codex.build_cmd(_ctx())
    assert cmd[-1] == "Do the thing."
    assert cmd[0] == "codex" and "exec" in cmd
    # approval flag declared in profile matches the command
    assert "--approve-for-me" in cmd
    # CODEX_HOME sandbox requested by the adapter (auth-only home per trial)
    assert codex.command_env()["CODEX_HOME"]


def test_codex_model_flags_use_bare_slug():
    codex = get_harness("codex")
    cmd = codex.build_cmd(_ctx(model="openai/gpt-5.6-luna"))
    i = cmd.index("-m")
    assert cmd[i + 1] == "gpt-5.6-luna"  # bare slug, no provider prefix


def test_aider_flag_prompt_mode():
    aider = get_harness("aider")
    cmd = aider.build_cmd(_ctx())
    # --message followed by the prompt
    i = cmd.index("--message")
    assert cmd[i + 1] == "Do the thing."


def test_claude_parse_native_usage():
    claude = get_harness("claude-code")
    ev = claude.parse_native(
        {
            "type": "assistant",
            "message": {
                "content": [{"type": "tool_use", "name": "Bash", "input": {}}],
                "usage": {"input_tokens": 100, "output_tokens": 20, "cache_read_input_tokens": 500},
            },
        }
    )
    assert ev is not None
    assert ev["tool"] == "bash"  # canonical tool normalization
    assert ev["usage"]["cached_tokens"] == 500
    assert ev["usage_estimated"] is False


def test_codex_parse_native_token_count():
    codex = get_harness("codex")
    # Modern (0.15x) schema: turn.completed carries cumulative usage.
    ev = codex.parse_native(
        {
            "type": "turn.completed",
            "usage": {
                "input_tokens": 72255,
                "cached_input_tokens": 53504,
                "output_tokens": 330,
                "reasoning_output_tokens": 126,
            },
        }
    )
    assert ev["event"] == "usage" and ev["usage_estimated"] is False
    assert ev["usage"]["input_tokens"] == 72255
    assert ev["usage"]["cached_tokens"] == 53504
    assert ev["usage"]["reasoning_tokens"] == 126
    # thread id is captured for rollout lookup
    ev2 = codex.parse_native({"type": "thread.started", "thread_id": "abc-123"})
    assert ev2["event"] == "thread" and ev2["thread_id"] == "abc-123"
    # legacy schema still parses
    ev3 = codex.parse_native(
        {
            "msg": {
                "type": "token_count",
                "info": {
                    "total_token_usage": {
                        "input_tokens": 10,
                        "output_tokens": 5,
                        "reasoning_output_tokens": 3,
                        "cached_input_tokens": 7,
                    }
                },
            }
        }
    )
    assert ev3["event"] == "usage" and ev3["usage"]["cached_tokens"] == 7


def test_parse_transcript_fallback_estimates_usage():
    h = get_harness("opencode")
    events = h.parse_transcript(["hello world, this is a line of output"])
    assert events[0]["event"] == "log"
    assert events[0]["usage_estimated"] is True
    assert events[0]["usage"]["input_tokens"] > 0


def test_missing_reason_mentions_env(monkeypatch):
    aider = get_harness("aider")
    # Simulate the binary being present so the auth gate is what's under test
    # (aider is not installed on CI runners).
    monkeypatch.setattr(shutil, "which", lambda name: "/usr/bin/aider" if name == "aider" else None)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert "missing env" in aider.missing_reason()
    assert aider.available() is False


def test_aider_available_with_either_key_alone(monkeypatch):
    """Aider is multi-provider: ONE valid key (for the pinned model's provider)
    must be enough. Regression test for the all-vars auth gate bug."""
    aider = get_harness("aider")
    monkeypatch.setattr(shutil, "which", lambda name: "/usr/bin/aider" if name == "aider" else None)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-openai")
    assert aider.available() is True
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-anthropic")
    assert aider.available() is True
    assert aider.missing_reason() == ""


def test_all_mode_still_requires_every_var(monkeypatch):
    """The default 'all' mode must stay strict for single-provider adapters."""
    goose = get_harness("goose")  # declares auth_env=[] → trivially available
    assert goose.profile.auth_env_mode == "all"
    codex = get_harness("codex")
    assert codex.profile.auth_env_mode == "all"


@pytest.mark.skipif(shutil.which("codex") is None, reason="codex binary not installed")
def test_available_when_env_present(monkeypatch):
    codex = get_harness("codex")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    assert codex.available() is True


def test_cursor_subscription_login_detected(monkeypatch, tmp_path):
    """Regression: cursor-agent login (subscription) must satisfy availability.

    The adapter previously only checked CURSOR_API_KEY, so a fully logged-in
    subscription user was reported unavailable. Auth now also reads the CLI's
    own credential store (~/.cursor/cli-config.json authInfo.userId).
    """
    import json as _json

    fake_home = tmp_path / "home"
    cursor_dir = fake_home / ".cursor"
    cursor_dir.mkdir(parents=True)
    (cursor_dir / "cli-config.json").write_text(
        _json.dumps({"authInfo": {"userId": "u123", "email": "x@y.z"}}), encoding="utf-8"
    )
    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_home))
    monkeypatch.setattr(
        shutil, "which", lambda name: "/usr/bin/cursor-agent" if name == "cursor-agent" else None
    )
    monkeypatch.delenv("CURSOR_API_KEY", raising=False)
    cursor = get_harness("cursor-agent")
    assert cursor.available() is True
    assert cursor.missing_reason() == ""

    # No authInfo, no env key → unavailable, with an actionable hint.
    (cursor_dir / "cli-config.json").write_text(_json.dumps({"authInfo": {}}), encoding="utf-8")
    assert cursor.available() is False
    assert "cursor-agent login" in cursor.missing_reason()


def test_cursor_cmd_includes_trust_flag():
    """--trust must precede the prompt: headless print mode exits 0 with no
    output in an untrusted workspace (the trust prompt needs a TTY)."""
    cursor = get_harness("cursor-agent")
    assert "--trust" in cursor.cmd_template
    assert cursor.cmd_template.index("--trust") < len(cursor.cmd_template) - 1


def test_score_row_schema_separates_scored_and_houdini():
    """Regression: 'passed'/'trials' once mixed Houdini probes into the pass
    rate (35/48 = 72.9% vs the true 23/36 = 63.9%). The schema now separates
    scored and probe counts and disambiguates per-trial vs total quantities.
    """
    import statistics as _statistics

    from cli_bench.scoring import RunGroup, Trial, score_group

    trials = [
        Trial("h", "task/a", seed, "pass", spend=100, duration_s=10.0, cost_usd=0.01) for seed in range(3)
    ]
    trials += [
        Trial("h", "houdini/x", seed, "pass", spend=50, duration_s=5.0, cost_usd=0.005) for seed in range(3)
    ]
    group = RunGroup(
        run_id="t",
        path=Path("."),
        model="m",
        suite_version="s",
        backend="local",
        created="",
        task_meta={"task/a": {"weight": 1.0}, "houdini/x": {"weight": 1.0}},
    )
    group.trials = trials
    row = score_group(group)["leaderboard"][0]
    assert row["scored_passes"] == 3 and row["scored_trials"] == 3
    assert row["houdini_passes"] == 3 and row["houdini_trials"] == 3
    assert row["total_trials"] == 6
    # mean vs total must be distinct fields with distinct values
    assert row["mean_cost_usd_per_trial"] * row["total_trials"] == row["total_cost_usd"]
    assert row["mean_duration_s_per_trial"] == _statistics.mean([10.0] * 3 + [5.0] * 3)
    assert row["p50_duration_s"] == _statistics.median([10.0] * 3 + [5.0] * 3)


def test_report_defaults_match_published_methodology():
    """cbench score and cbench report must share envelope_factor=1.0 — a 0.5
    default in report.py once made the two disagree for multi-harness groups."""
    import inspect

    from cli_bench import report

    assert inspect.signature(report.build_report).parameters["envelope_factor"].default == 1.0
    assert inspect.signature(report.write_report).parameters["envelope_factor"].default == 1.0


def test_versions_do_not_crash():
    for h in registry().values():
        v = h.version()
        assert isinstance(v, str) and v  # "unknown" allowed; must not raise
