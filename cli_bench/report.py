"""Report generation: JSON for the website + markdown for PRs."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from cli_bench.scoring import RunGroup, load_run_group, render_table, score_group


def build_report(run_paths: list[Path], envelope_factor: float = 1.0) -> dict[str, Any]:
    scored_runs = []
    for p in run_paths:
        group: RunGroup = load_run_group(Path(p))
        scored = score_group(group, envelope_factor=envelope_factor)
        scored_runs.append(scored)

    # Aggregate harness rows across runs (mean of per-run values, keyed by harness).
    agg: dict[str, dict[str, Any]] = {}
    for sr in scored_runs:
        for row in sr["leaderboard"]:
            h = agg.setdefault(
                row["harness"],
                {
                    "harness": row["harness"],
                    "runs": [],
                    "cb_hdr": [],
                    "hdr": [],
                    "hdr_c": [],
                    "scored_passes": [],
                    "scored_trials": [],
                    "houdini_passes": [],
                    "houdini_trials": [],
                    "mean_cost_usd_per_trial": [],
                    "total_cost_usd": [],
                    "mean_effective_tokens_per_trial": [],
                    "total_effective_tokens": [],
                    "mean_duration_s_per_trial": [],
                    "p50_duration_s": [],
                },
            )
            h["runs"].append(sr["run_id"])
            for key in (
                "cb_hdr",
                "hdr",
                "hdr_c",
                "mean_cost_usd_per_trial",
                "mean_effective_tokens_per_trial",
                "mean_duration_s_per_trial",
                "p50_duration_s",
            ):
                h[key].append(row[key])
            for key in (
                "scored_passes",
                "scored_trials",
                "houdini_passes",
                "houdini_trials",
                "total_cost_usd",
                "total_effective_tokens",
            ):
                h[key] = h.get(key, [])
                h[key].append(row[key])

    harness_rows = []
    for h in agg.values():
        mean = lambda xs: round(sum(xs) / len(xs), 4) if xs else 0.0  # noqa: E731
        total = lambda xs: round(sum(xs), 4) if xs else 0.0  # noqa: E731
        harness_rows.append(
            {
                "harness": h["harness"],
                "cb_hdr": mean(h["cb_hdr"]),
                "hdr": mean(h["hdr"]),
                "hdr_c": mean(h["hdr_c"]),
                "scored_passes": int(total(h["scored_passes"])),
                "scored_trials": int(total(h["scored_trials"])),
                "houdini_passes": int(total(h["houdini_passes"])),
                "houdini_trials": int(total(h["houdini_trials"])),
                "mean_cost_usd_per_trial": mean(h["mean_cost_usd_per_trial"]),
                "total_cost_usd": total(h["total_cost_usd"]),
                "mean_effective_tokens_per_trial": int(mean(h["mean_effective_tokens_per_trial"])),
                "total_effective_tokens": int(total(h["total_effective_tokens"])),
                "mean_duration_s_per_trial": mean(h["mean_duration_s_per_trial"]),
                "p50_duration_s": mean(h["p50_duration_s"]),
                "runs": h["runs"],
            }
        )
    harness_rows.sort(key=lambda r: -r["cb_hdr"])

    return {
        "generated": datetime.now(UTC).isoformat(timespec="seconds"),
        "suite_version": scored_runs[0]["suite_version"] if scored_runs else None,
        "model": scored_runs[0]["model"] if scored_runs else None,
        "envelope_factor": envelope_factor,
        "runs": [
            {k: sr[k] for k in ("run_id", "model", "suite_version", "backend", "created")}
            for sr in scored_runs
        ],
        "harnesses": harness_rows,
    }


def write_report(
    run_paths: list[Path], out_json: Path, out_md: Path | None = None, envelope_factor: float = 1.0
) -> dict[str, Any]:
    report = build_report(run_paths, envelope_factor=envelope_factor)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(report, indent=2), encoding="utf-8")

    if out_md is not None:
        lines = ["# CLI-Bench results", ""]
        for p, sr in zip(run_paths, report["runs"], strict=True):
            group = load_run_group(Path(p))
            scored = score_group(group, envelope_factor=envelope_factor)
            lines += [
                f"## {sr['run_id']}",
                "",
                f"Model: `{sr['model']}` · Suite `{sr['suite_version']}` · Backend `{sr['backend']}`",
                "",
                render_table(scored),
                "",
            ]
        out_md.parent.mkdir(parents=True, exist_ok=True)
        out_md.write_text("\n".join(lines), encoding="utf-8")
    return report
