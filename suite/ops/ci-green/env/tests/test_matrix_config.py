from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.api]


def test_pyproject_declares_project():
    root = Path(__file__).resolve().parent.parent
    pp = root / "pyproject.toml"
    assert pp.exists(), "pyproject.toml must exist at repo root"
    text = pp.read_text()
    assert "[project]" in text


def test_ci_script_runs_matrix():
    root = Path(__file__).resolve().parent.parent
    ci = root / "ci" / "run_all.sh"
    assert ci.exists()
    text = ci.read_text()
    assert "pytest" in text
