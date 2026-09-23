import math

import pytest
from pkg.geometry import circle_area, circle_circumference, rect_area, rect_perimeter
from sites.a_report import build_report
from sites.b_summary import summarize
from sites.c_export import export_shapes
from sites.d_batch import process_circles
from sites.e_cli import main as cli_main


def test_api_names_exist():
    for fn in (rect_area, rect_perimeter, circle_area, circle_circumference):
        assert callable(fn)


def test_old_names_gone():
    import pkg.geometry as g

    for old in ("calc_rect_area", "calc_rect_perimeter", "calc_circle_area", "calc_circle_circumference"):
        assert not hasattr(g, old), f"old name {old} still present"


def test_values():
    assert rect_area(3, 4) == 12
    assert rect_perimeter(3, 4) == 14
    assert abs(circle_area(1) - math.pi) < 1e-9
    assert abs(circle_circumference(1) - 2 * math.pi) < 1e-9


def test_negative_dimensions_raise():
    with pytest.raises(ValueError):
        rect_area(-1, 2)
    with pytest.raises(ValueError):
        circle_area(-1)


def test_report_site():
    out = build_report([(2, 3)], [1.0])
    assert "area=6" in out and "circle" in out


def test_summary_site():
    s = summarize([(1, 1), (2, 2)], [1.0, 2.0])
    assert s["total_rect_perimeter"] == 10
    assert abs(s["total_circle_circumference"] - 6 * math.pi) < 1e-9


def test_export_site(tmp_path):
    p = tmp_path / "out.json"
    data = export_shapes([(2, 5)], str(p))
    assert data[0]["area"] == 10
    assert "area" in p.read_text()


def test_batch_site():
    kept = process_circles([1.0, 2.0], min_area=4.0)
    assert len(kept) == 1 and kept[0][0] == 2.0


def test_cli_site(capsys):
    sys_argv = __import__("sys").argv
    __import__("sys").argv = ["e_cli.py", "3", "4"]
    try:
        assert cli_main() == 0
        captured = capsys.readouterr()
        assert "area=12" in captured.out and "perimeter=14" in captured.out
    finally:
        __import__("sys").argv = sys_argv
