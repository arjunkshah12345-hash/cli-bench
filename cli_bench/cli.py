"""cbench — the CLI-Bench command line interface."""

from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path

from cli_bench import __version__
from cli_bench.harness import cohort_check, get_harness, registry
from cli_bench.report import write_report
from cli_bench.runner import host_fingerprint, run_task
from cli_bench.scoring import load_run_group, render_table, score_group
from cli_bench.task import load_suite


def _new_run_dir(runs_root: Path, label: str) -> Path:
    ts = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    run_dir = runs_root / f"{ts}-{label}"
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


def cmd_list(args: argparse.Namespace) -> int:
    tasks = load_suite(Path(args.suite))
    print(f"{'TASK':<32}{'CATEGORY':<11}{'TIER':<10}{'SEEDS':<6}{'BUDGET_S':<9}{'TAGS'}")
    for t in tasks:
        print(
            f"{t.id:<32}{t.category:<11}{t.difficulty:<10}{t.seeds:<6}{t.time_budget_s:<9}{','.join(t.tags) or '-'}"
        )
    print(f"\n{len(tasks)} tasks. Harnesses:")
    for name, h in sorted(registry().items()):
        avail = "✓" if h.available() else "✗ (binary not found)"
        print(f"  {name:<16}{avail:<18}{h.version()}")
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    tasks = load_suite(Path(args.suite))
    if args.only:
        wanted = set(args.only)
        tasks = [t for t in tasks if t.id in wanted]
        if not tasks:
            print("no tasks matched --only", file=sys.stderr)
            return 2
    harnesses = []
    for name in args.harness:
        h = get_harness(name)
        if not h.available():
            print(f"harness {name!r} is not available on this machine", file=sys.stderr)
            return 2
        if not args.allow_incompatible:
            err = cohort_check(h, args.model)
            if err:
                print(f"cohort error: {err}", file=sys.stderr)
                return 2
        else:
            print(
                f"warning: --allow-incompatible: {name} x {args.model} recorded in the manifest",
                file=sys.stderr,
            )
        harnesses.append(h)

    if args.backend == "docker":
        print(
            "error: the docker backend is specified in SPEC §5.2 but not implemented in this "
            "release; use --backend local (hermetic temp-dir sandbox).",
            file=sys.stderr,
        )
        return 2

    run_dir = _new_run_dir(Path(args.runs), "batch")
    meta = {
        "run_id": run_dir.name,
        "created": datetime.now(UTC).isoformat(timespec="seconds"),
        "model": args.model,
        "backend": args.backend,
        "suite_version": args.suite_version,
        "suite_dir": str(Path(args.suite).resolve()),
        "seeds": args.seeds,
        "harnesses": [h.name for h in harnesses],
        "host": host_fingerprint(),
        "task_meta": {
            t.id: {
                "weight": t.weight,
                "time_budget_s": t.time_budget_s,
                "max_cost_usd": t.max_cost_usd,
            }
            for t in tasks
        },
        "price_table": args.price_table,
        "allow_incompatible": bool(args.allow_incompatible),
    }
    (run_dir / "run.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(f"run dir: {run_dir}")

    jobs = []
    for h in harnesses:
        for t in tasks:
            for seed in range(args.seeds):
                jobs.append((h, t, seed))

    if args.parallel <= 1:
        for h, t, seed in jobs:
            _do_job(h, t, seed, run_dir, args)
    else:
        with ThreadPoolExecutor(max_workers=args.parallel) as pool:
            futures = [pool.submit(_do_job, h, t, seed, run_dir, args) for h, t, seed in jobs]
            for f in as_completed(futures):
                f.result()

    _verify_effective_models(run_dir, args.model)
    print("done. Next: cbench score", run_dir)
    return 0


def _verify_effective_models(run_dir: Path, requested: str) -> None:
    """Hard-fail the run if a native-reporting harness ran a different model.

    Harnesses that cannot report their effective model are recorded as null
    (not failures) — but native reports that contradict the request abort the
    batch, because the manifest would be a lie (SPEC §5.5).
    """
    offenders: list[str] = []
    for path in sorted((run_dir / "runs").rglob("result.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        eff = data.get("effective_model")
        # Compare bare ids too: codex reports "gpt-5.6-luna" while the
        # manifest may pin "openai/gpt-5.6-luna" — same model, different form.
        bare = requested.rpartition("/")[2] if requested else requested
        if eff and requested and eff not in (requested, bare):
            offenders.append(
                f"{data.get('harness')} {data.get('task_id')} s{data.get('seed')}: "
                f"requested {requested!r} but harness ran {eff!r}"
            )
    if offenders:
        print(
            "MODEL MISMATCH — run aborted before scoring; fix the adapter's model pinning:",
            file=sys.stderr,
        )
        for o in offenders[:20]:
            print(f"  {o}", file=sys.stderr)
        raise SystemExit(3)


def _do_job(h, t, seed, run_dir, args) -> None:
    try:
        result = run_task(h, t, seed, run_dir, backend=args.backend, model=args.model)
        print(f"  {h.name:<10}{t.id:<28}s{seed}  {result.outcome:<12}{result.duration_s:6.1f}s")
    except Exception as exc:  # noqa: BLE001 - one failed trial must not kill the batch
        print(f"  {h.name:<10}{t.id:<28}s{seed}  ERROR: {exc}", file=sys.stderr)


def cmd_score(args: argparse.Namespace) -> int:
    group = load_run_group(Path(args.run_dir))
    scored = score_group(group, envelope_factor=args.envelope_factor)
    (Path(args.run_dir) / "leaderboard.json").write_text(json.dumps(scored, indent=2), encoding="utf-8")
    print(render_table(scored))
    print(f"\nleaderboard.json written to {args.run_dir}")
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    report = write_report(
        [Path(p) for p in args.run_dirs],
        out_json=Path(args.out),
        out_md=Path(args.md) if args.md else None,
        envelope_factor=args.envelope_factor,
    )
    print(f"report written: {args.out} ({len(report['harnesses'])} harnesses)")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="cbench", description="CLI-Bench: benchmark agent harnesses, not models."
    )
    parser.add_argument("--version", action="version", version=f"cbench {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p_list = sub.add_parser("list", help="list tasks and harnesses")
    p_list.add_argument("--suite", default="suite")
    p_list.set_defaults(func=cmd_list)

    p_run = sub.add_parser("run", help="run harnesses against the suite")
    p_run.add_argument("--harness", action="append", required=True, help="harness name (repeatable)")
    p_run.add_argument("--model", default="openai/gpt-5.3", help="pinned model id")
    p_run.add_argument("--suite", default="suite")
    p_run.add_argument("--suite-version", dest="suite_version", default="0.9.0")
    p_run.add_argument("--seeds", type=int, default=3)
    p_run.add_argument("--backend", choices=["local", "docker"], default="local")
    p_run.add_argument("--runs", default="runs", help="output root for run dirs")
    p_run.add_argument("--parallel", type=int, default=1)
    p_run.add_argument(
        "--price-table", default="1.0.0", help="pinned price table version for cost accounting"
    )
    p_run.add_argument(
        "--allow-incompatible", action="store_true", help="skip model-cohort checks (recorded in manifest)"
    )
    p_run.add_argument("--only", action="append", help="restrict to task id (repeatable)")
    p_run.set_defaults(func=cmd_run)

    p_score = sub.add_parser("score", help="score a run dir")
    p_score.add_argument("run_dir")
    p_score.add_argument("--envelope-factor", type=float, default=1.0, help="HDR-C envelope X (default 1.0)")
    p_score.set_defaults(func=cmd_score)

    p_report = sub.add_parser("report", help="aggregate run dirs into site JSON/markdown")
    p_report.add_argument("run_dirs", nargs="+")
    p_report.add_argument("-o", "--out", default="results.json")
    p_report.add_argument("--md", default=None)
    p_report.add_argument("--envelope-factor", type=float, default=1.0)
    p_report.set_defaults(func=cmd_report)

    args = parser.parse_args(argv)
    return int(args.func(args) or 0)


if __name__ == "__main__":
    raise SystemExit(main())
