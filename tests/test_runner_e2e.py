"""End-to-end runner tests using the mock harness (no network, no API keys)."""

import json
from pathlib import Path

import pytest

from cli_bench.harness import MockHarness
from cli_bench.runner import run_task
from cli_bench.scoring import load_run_group, score_group


@pytest.fixture()
def mini_suite(tmp_path):
    """A tiny suite: one always-pass mock, one flaky-by-hash task."""
    suite = tmp_path / "suite" / "debugging" / "mini"
    (suite / "env").mkdir(parents=True)
    (suite / "env" / "hello.txt").write_text("hi\n")
    (suite / "task.yaml").write_text(
        "id: debugging/mini\n"
        "title: Mini\n"
        "prompt: |\n"
        "  Say hi.\n"
        "category: debugging\n"
        "difficulty: standard\n"
        "time_budget_s: 60\n"
        "max_cost_usd: 0.10\n"
        "seeds: 2\n"
        "requires: [python3]\n"
        "tags: []\n"
    )
    (suite / "verifier.sh").write_text(
        "#!/usr/bin/env bash\n"
        'WS="${CBENCH_WORKSPACE:-$PWD}"\n'
        "# never-starts-green: requires the harness work product AND intact seed material\n"
        'test -f "$WS/mock_output.txt" && test -f "$WS/hello.txt" && echo VERIFIER_PASS\n'
    )
    (suite / "Dockerfile").write_text("FROM python:3.12-slim\nWORKDIR /workspace\n")
    return tmp_path / "suite"


def test_run_task_pass_and_artifacts(tmp_path, mini_suite):
    from cli_bench.task import load_suite

    tasks = load_suite(mini_suite)
    assert len(tasks) == 1
    task = tasks[0]
    harness = MockHarness("mock-pass", pass_rate=1.0, speed=0.2)

    result = run_task(
        harness, task, seed=0, run_dir=tmp_path / "run", backend="local", model="openai/gpt-5.3"
    )
    assert result.outcome == "pass"
    assert result.verifier_ok is True
    art = result.artifact_dir
    assert (art / "stdout.log").exists()
    assert (art / "transcript.jsonl").exists()
    assert (art / "result.json").exists()
    assert (art / "workspace.zip").exists()
    # transcript has log events with estimated usage
    lines = [json.loads(ln) for ln in (art / "transcript.jsonl").read_text().splitlines() if ln.strip()]
    assert any(ev["event"] == "log" for ev in lines)
    # usage estimated (mock doesn't report native usage)
    assert result.usage_estimated is True
    assert result.usage["input_tokens"] > 0


def test_run_task_fail_when_mock_fails(tmp_path, mini_suite):
    from cli_bench.task import load_suite

    task = load_suite(mini_suite)[0]
    harness = MockHarness("mock-fail", pass_rate=0.0, speed=0.2)
    result = run_task(
        harness, task, seed=0, run_dir=tmp_path / "run", backend="local", model="openai/gpt-5.3"
    )
    assert result.outcome == "fail"
    assert result.verifier_ok is False


def test_run_task_sabotage_detection(tmp_path, mini_suite):
    """A harness that deletes shipped files gets outcome=sabotage."""
    from cli_bench.task import load_suite

    task = load_suite(mini_suite)[0]
    harness = MockHarness("mock-saboteur", pass_rate=1.0, speed=0.2)

    # Patch the mock script to delete the shipped file after "working"
    def sabotaging_cmd(ctx):
        # Wrap: run the mock but with the workspace file removed first via a shim script
        shim = Path(ctx.workspace) / "_shim.py"
        shim.write_text("import os, sys\nos.remove(os.path.join(os.getcwd(), 'hello.txt'))\n")
        return ["python3", str(shim)]

    harness.build_cmd = sabotaging_cmd
    result = run_task(
        harness, task, seed=0, run_dir=tmp_path / "run", backend="local", model="openai/gpt-5.3"
    )
    assert result.outcome == "sabotage"
    assert "hello.txt" in result.verifier_log


def test_full_pipeline_score(tmp_path, mini_suite):
    """run two mocks → score → leaderboard ordering sane."""
    from cli_bench.task import load_suite

    tasks = load_suite(mini_suite)
    task = tasks[0]
    run_dir = tmp_path / "run"
    (run_dir / "runs").mkdir(parents=True)
    (run_dir / "run.json").write_text(
        json.dumps(
            {
                "run_id": run_dir.name,
                "created": "now",
                "model": "openai/gpt-5.3",
                "suite_version": "1.0.0",
                "backend": "local",
                "task_meta": {task.id: {"weight": task.weight, "time_budget_s": task.time_budget_s}},
            }
        )
    )

    strong = MockHarness("mock-strong", pass_rate=1.0, speed=0.3)
    weak = MockHarness("mock-weak", pass_rate=0.0, speed=0.6)
    for harness in (strong, weak):
        for seed in (0, 1):
            run_task(harness, task, seed=seed, run_dir=run_dir, backend="local", model="openai/gpt-5.3")

    group = load_run_group(run_dir)
    assert len(group.trials) == 4
    scored = score_group(group)
    rows = {r["harness"]: r for r in scored["leaderboard"]}
    assert rows["mock-strong"]["cb_hdr"] > rows["mock-weak"]["cb_hdr"]
    assert rows["mock-strong"]["hdr"] == pytest.approx(1.0)
    assert rows["mock-weak"]["hdr"] == pytest.approx(0.0)
