import json

import pytest
from src.other_module import export

pytestmark = pytest.mark.export


def test_export_plain(tmp_path):
    p = tmp_path / "out.json"
    export({"a": 1}, str(p))
    assert json.loads(p.read_text()) == {"a": 1}


def test_export_pretty(tmp_path):
    p = tmp_path / "out.json"
    export({"a": 1}, str(p), pretty=True)
    assert json.loads(p.read_text()) == {"a": 1}
    assert "\n" in p.read_text()
