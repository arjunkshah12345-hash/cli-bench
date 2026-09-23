"""Tests over the shipped task suite itself."""

from pathlib import Path

import pytest

from cli_bench.task import checksums_match, load_houdini, load_suite

SUITE = Path(__file__).resolve().parent.parent / "suite"
EXPECTED_SCORED = {
    "refactor/deadcode",
    "refactor/api-shape",
    "feature/rate-limiter",
    "feature/csv-normalizer",
    "debug/flaky-test",
    "debug/wrong-answer",
    "tooling/test-gen",
    "data/log-analysis",
    "ops/ci-green",
    "sec/patch-xss",
    "perf/hot-loop",
    "docs/api-ref",
}
EXPECTED_HOUDINI = {"houdini/self-test", "houdini/mutation", "houdini/hidden-spec", "houdini/no-cheat"}


def test_suite_loads_twelve_scored_tasks():
    tasks = load_suite(SUITE)
    assert {t.id for t in tasks} == EXPECTED_SCORED


def test_houdini_probes_load_separately():
    probes = load_houdini(SUITE)
    assert {t.id for t in probes} == EXPECTED_HOUDINI


@pytest.mark.parametrize("tid", sorted(EXPECTED_SCORED | EXPECTED_HOUDINI))
def test_task_files_complete(tid):
    d = SUITE / tid
    assert (d / "task.yaml").exists(), tid
    assert (d / "verifier.sh").exists(), tid
    assert (d / "Dockerfile").exists(), tid
    assert (d / "env").is_dir(), tid
    verifier_text = (d / "verifier.sh").read_text()
    assert "CBENCH_WORKSPACE" in verifier_text, f"{tid}: verifier must honor CBENCH_WORKSPACE"


def test_weights_match_spec():
    tasks = {t.id: t for t in load_suite(SUITE)}
    assert tasks["refactor/deadcode"].weight == pytest.approx(1.25 * 1.25)  # refactor × standard
    assert tasks["refactor/api-shape"].weight == pytest.approx(1.25 * 1.5)  # refactor × hard
    assert tasks["docs/api-ref"].weight == pytest.approx(0.9 * 1.0)  # docs × warmup
    assert tasks["debug/flaky-test"].weight == pytest.approx(1.2 * 1.5)


def test_quality_probe_tag():
    tasks = {t.id: t for t in load_suite(SUITE)}
    assert tasks["docs/api-ref"].is_quality_probe
    assert not tasks["perf/hot-loop"].is_quality_probe


def test_checksums_stable_and_matching():
    tasks = load_suite(SUITE)
    for t in tasks:
        c1 = t.checksums()
        c2 = t.checksums()
        assert c1 == c2
        assert checksums_match(t, c1)
        assert "verifier.sh" in c1


def test_no_cheat_declares_sabotage_exempt():
    probes = {t.id: t for t in load_houdini(SUITE)}
    exempt = probes["houdini/no-cheat"].raw.get("sabotage_exempt", [])
    assert any("app.log" in p and "app.log.1" not in p for p in exempt)


def test_budgets_are_sane():
    for t in load_suite(SUITE):
        assert 60 <= t.time_budget_s <= 3600, t.id
        assert 0.05 <= t.max_cost_usd <= 5.0, t.id
        assert t.seeds >= 3, t.id


def test_prompts_are_harness_neutral():
    banned = ["ripgrep", "use rg", "cursor", "codex ", "claude", "aider", "claude code", "copilot"]
    for t in load_suite(SUITE):
        low = t.prompt.lower()
        for b in banned:
            assert b.lower() not in low, f"{t.id}: prompt mentions {b!r} (harness-specific hint)"


@pytest.mark.parametrize("tid", sorted(EXPECTED_SCORED))
def test_verifier_fails_on_untouched_env(tid):
    """The never-starts-green guarantee, checked for every scored task."""
    import os
    import shutil
    import subprocess
    import sys
    import tempfile

    task_dir = SUITE / tid
    with tempfile.TemporaryDirectory() as td:
        vdir = Path(td)
        ws = vdir / "workspace"
        shutil.copytree(task_dir / "env", ws)
        for helper in task_dir.glob("*.py"):
            shutil.copy2(helper, vdir / helper.name)
        pristine = task_dir / "pristine"
        if pristine.exists():
            shutil.copytree(pristine, vdir / "pristine")
        shutil.copy2(task_dir / "verifier.sh", vdir / "verifier.sh")
        seed_py = task_dir / "seed.py"
        if seed_py.exists():
            subprocess.run(
                [sys.executable, str(seed_py)],
                cwd=ws,
                env={**os.environ, "CBENCH_SEED": "0"},
                capture_output=True,
                timeout=120,
                check=True,
            )
        proc = subprocess.run(
            ["bash", str(vdir / "verifier.sh")],
            cwd=vdir,
            env={**os.environ, "CBENCH_WORKSPACE": str(ws)},
            capture_output=True,
            text=True,
            timeout=600,
        )
        assert proc.returncode != 0, (
            f"{tid}: verifier passed on untouched env — task starts green!\n{proc.stdout[-500:]}"
        )
