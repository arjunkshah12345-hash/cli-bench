"""Unit tests for the scoring system."""

import math

import pytest

from cli_bench.scoring import RunGroup, Trial, brake, load_run_group, p50_spend, score_group
from cli_bench.usage_proxy import cost_usd, effective_tokens


def test_brake_full_credit_at_or_below_median():
    assert brake(100, 100) == 1.0
    assert brake(50, 100) == 1.0
    assert brake(1, 100) == 1.0


def test_brake_decay_is_smooth():
    # at 2x median, B ≈ 5p50/2p50 clamped → 1.0 unless budget clamps...
    # B = min(1, 5*p50/spend): 2x median still earns 1.0 only if 5*p50 >= spend*1
    # 2x median: 5p50/2p50 = 2.5 → capped at 1. Brake starts past 5x.
    assert brake(2 * 100, 100) == 1.0
    # at 10x median: 5p50/10p50 = 0.5
    assert math.isclose(brake(10 * 100, 100), 0.5)
    # at 25x median: 0.2
    assert math.isclose(brake(25 * 100, 100), 0.2)
    # beyond: floor at 0
    assert brake(1000 * 100, 100) < 0.01


def test_brake_zero_and_edge_cases():
    assert brake(0, 100) == 0.0  # no spend, no credit
    assert brake(100, 0) == 1.0  # no passer median (sole passer)
    assert brake(100, 100, budget_tokens=50) == 1.0  # budget clamp saturates


def test_effective_tokens_cache_discount():
    u = {"input_tokens": 100, "output_tokens": 50, "reasoning_tokens": 25, "cached_tokens": 1000}
    assert effective_tokens(u) == 100 + 50 + 25 + int(0.1 * 1000)


def test_cost_usd_math():
    usage = {"input_tokens": 1_000_000, "cached_tokens": 0, "output_tokens": 100_000, "reasoning_tokens": 0}
    # price table 1.0.0 for openai/gpt-5.3: (1.25, 0.125, 10.0) per 1M
    c = cost_usd(usage, "openai/gpt-5.3")
    assert math.isclose(c, 1.25 + 100_000 / 1e6 * 10.0, rel_tol=1e-4)


def test_cost_usd_unknown_model_raises():
    with pytest.raises(KeyError):
        cost_usd({}, "nonexistent/model")


def _make_group():
    """Synthetic group: 2 harnesses × 2 tasks × 2 seeds, hand-checkable."""
    trials = []
    # task alpha: both harnesses pass everything
    for seed in (0, 1):
        trials.append(Trial("fast", "alpha", seed, "pass", spend=100, duration_s=1.0, cost_usd=0.01))
        trials.append(Trial("slow", "alpha", seed, "pass", spend=300, duration_s=3.0, cost_usd=0.03))
    # task beta: fast fails, slow passes
    for seed in (0, 1):
        trials.append(Trial("fast", "beta", seed, "fail", spend=200, duration_s=2.0, cost_usd=0.02))
        trials.append(Trial("slow", "beta", seed, "pass", spend=400, duration_s=4.0, cost_usd=0.04))
    group = RunGroup(
        run_id="test",
        path=None,
        model="openai/gpt-5.3",
        suite_version="1.0.0",
        backend="local",
        created="",
        price_table="1.0.0",
        trials=trials,
        task_meta={
            "alpha": {"weight": 1.0, "time_budget_s": 600},
            "beta": {"weight": 3.0, "time_budget_s": 600},
        },
    )
    return group


def test_p50_spend_only_counts_passes():
    group = _make_group()
    # alpha passers: 100,100,300,300 → median 200
    assert p50_spend(group.trials, "alpha") == 200
    # beta passers: only slow (400, 400) → 400
    assert p50_spend(group.trials, "beta") == 400


def test_score_group_cb_hdr_hand_computed():
    group = _make_group()
    scored = score_group(group)
    rows = {r["harness"]: r for r in scored["leaderboard"]}

    # alpha: p50=200; fast spend 100 → B=1; slow spend 300 → B=min(1,1000/300)=1
    # beta: p50=400; slow spend 400 → B=1; fast failed → 0
    # fast: (1.0*1 + 0)/ (1+3) = 0.25 ; slow: (1.0*1 + 3.0*1)/4 = 1.0
    assert math.isclose(rows["fast"]["cb_hdr"], 0.25)
    assert math.isclose(rows["slow"]["cb_hdr"], 1.0)
    # HDR: fast passes 1 of 2 tasks; slow passes 2 of 2
    assert math.isclose(rows["fast"]["hdr"], 0.5)
    assert math.isclose(rows["slow"]["hdr"], 1.0)
    # leaderboard sorted by cb_hdr desc
    assert scored["leaderboard"][0]["harness"] == "slow"


def test_score_group_ci_present_and_ordered():
    group = _make_group()
    scored = score_group(group)
    for row in scored["leaderboard"]:
        lo, hi = row["ci95"]
        assert lo <= row["cb_hdr"] + 1e-9
        assert hi >= lo - 1e-9


def test_score_group_hdr_c_penalizes_expensive_passes():
    group = _make_group()
    scored = score_group(group, envelope_factor=1.0)
    rows = {r["harness"]: r for r in scored["leaderboard"]}
    # envelope alpha = 1.0*200*1 = 200 → slow's 300-spend pass doesn't count
    # envelope beta = 1.0*400 → slow counts
    assert rows["fast"]["hdr_c"] == pytest.approx(0.5)  # alpha yes, beta fail
    assert rows["slow"]["hdr_c"] == pytest.approx(0.5)  # alpha no, beta yes


def test_score_group_excludes_never_passed_tasks():
    trials = [
        Trial("a", "doomed", 0, "fail", spend=10, duration_s=1.0, cost_usd=0.0),
        Trial("b", "doomed", 0, "fail", spend=10, duration_s=1.0, cost_usd=0.0),
        Trial("a", "ok", 0, "pass", spend=10, duration_s=1.0, cost_usd=0.0),
        Trial("b", "ok", 0, "fail", spend=10, duration_s=1.0, cost_usd=0.0),
    ]
    group = RunGroup(
        "x",
        None,
        "m",
        "1.0.0",
        "local",
        "",
        "1.0.0",
        trials,
        {"ok": {"weight": 1.0}, "doomed": {"weight": 1.0}},
    )
    scored = score_group(group, envelope_factor=1.0)
    assert scored["p50_spend"]["doomed"] == 0
    rows = {r["harness"]: r for r in scored["leaderboard"]}
    # doomed excluded from HDR-C denominators: a passes ok (within envelope), b doesn't
    assert rows["a"]["hdr_c"] == pytest.approx(1.0)
    assert rows["b"]["hdr_c"] == pytest.approx(0.0)


def test_load_run_group_roundtrip(tmp_path):
    import json

    run = tmp_path / "20260101-000000-test"
    art = run / "runs" / "fast" / "alpha-s0"
    art.mkdir(parents=True)
    (run / "run.json").write_text(
        json.dumps(
            {
                "run_id": run.name,
                "model": "openai/gpt-5.3",
                "suite_version": "1.0.0",
                "backend": "local",
                "created": "now",
                "task_meta": {},
            }
        )
    )
    (art / "result.json").write_text(
        json.dumps(
            {
                "harness": "fast",
                "task_id": "alpha",
                "seed": 0,
                "outcome": "pass",
                "usage": {"input_tokens": 10, "output_tokens": 5, "reasoning_tokens": 0, "cached_tokens": 0},
                "duration_s": 1.5,
                "cost_usd": 0.001,
            }
        )
    )
    group = load_run_group(run)
    assert len(group.trials) == 1
    assert group.trials[0].spend == 15
    scored = score_group(group)
    assert scored["leaderboard"][0]["harness"] == "fast"
