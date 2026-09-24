"""Runner: executes harnesses against tasks with budget enforcement and checkpoints."""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from cli_bench.harness import Harness
from cli_bench.task import Task
from cli_bench.usage_proxy import cost_usd, estimate_usage_from_text

CHECKPOINT_FRACTIONS = (0.25, 0.5, 0.75)
POLL_INTERVAL_S = 1.0
USAGE_POLL_S = 10.0
MAX_TRANSCRIPT_LINES = 20000

CLI_BENCH_MD = """# CLI-Bench workspace

You are operating inside a benchmarked workspace.

- Work inside this directory. Do not write outside it.
- A programmatic verifier will grade the final state of this directory.
- Verify your own work before finishing.
"""


@dataclass
class TaskContext:
    task: Task
    seed: int
    workspace: Path
    prompt_file: Path
    time_budget_s: int
    model: str
    env_vars: dict[str, str] = field(default_factory=dict)


@dataclass
class TaskRunResult:
    harness: str
    task_id: str
    seed: int
    outcome: str
    exit_code: int | None
    duration_s: float
    usage: dict[str, int]
    usage_estimated: bool
    cost_usd: float
    verifier_ok: bool | None
    verifier_log: str
    artifact_dir: Path
    requested_model: str = ""
    effective_model: str | None = None  # None = harness does not report a model id

    def to_dict(self) -> dict[str, Any]:
        return {
            "harness": self.harness,
            "task_id": self.task_id,
            "seed": self.seed,
            "outcome": self.outcome,
            "exit_code": self.exit_code,
            "duration_s": round(self.duration_s, 3),
            "usage": self.usage,
            "usage_estimated": self.usage_estimated,
            "cost_usd": self.cost_usd,
            "verifier_ok": self.verifier_ok,
            "requested_model": self.requested_model,
            "effective_model": self.effective_model,
            "artifact_dir": self.artifact_dir.name,
        }


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def prepare_workspace(task: Task, seed: int, base: Path) -> tuple[Path, dict[str, str]]:
    """Materialize the task workspace for a given seed. Returns (workspace, manifest)."""
    workspace = base / "workspace"
    workspace.mkdir(parents=True)
    env_dir = task.env_dir()
    if env_dir.exists():
        shutil.copytree(env_dir, workspace, dirs_exist_ok=True)

    seed_py = task.path / "seed.py"
    if seed_py.exists():
        proc = subprocess.run(
            [sys.executable, str(seed_py)],
            cwd=workspace,
            env={**os.environ, "CBENCH_SEED": str(seed)},
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        if proc.returncode != 0:
            raise RuntimeError(f"seed.py failed for {task.id} seed {seed}: {proc.stderr[-2000:]}")

    (workspace / "CLI_BENCH.md").write_text(CLI_BENCH_MD, encoding="utf-8")

    # Manifest of shipped files for sabotage detection (SPEC §7.1 #3).
    # Tasks may declare `sabotage_exempt` paths (e.g. decoy files) that agents
    # may legitimately remove.
    exempt = set(task.raw.get("sabotage_exempt", []))
    manifest: dict[str, str] = {}
    for p in sorted(workspace.rglob("*")):
        if p.is_file():
            rel = str(p.relative_to(workspace))
            if rel not in exempt:
                manifest[rel] = sha256_file(p)
    return workspace, manifest


def check_sabotage(workspace: Path, manifest: dict[str, str]) -> str | None:
    """Return a sabotage reason if shipped files were deleted or emptied."""
    for rel, digest in manifest.items():
        p = workspace / rel
        if not p.exists():
            return f"deleted shipped file: {rel}"
        if (
            p.is_file()
            and sha256_file(p) == hashlib.sha256(b"").hexdigest()
            and digest != hashlib.sha256(b"").hexdigest()
        ):
            return f"emptied shipped file: {rel}"
    return None


def _drain_pipes(proc: subprocess.Popen[str]) -> list[threading.Thread]:
    """Drain stdout/stderr on daemon threads so the child never blocks on a
    full pipe while the runner polls (long-running CLIs print constantly).
    Collected lines are appended into proc._cbench_* lists (set here).
    """
    stdout_lines: list[str] = []
    stderr_lines: list[str] = []
    proc._cbench_stdout = stdout_lines  # type: ignore[attr-defined]
    proc._cbench_stderr = stderr_lines  # type: ignore[attr-defined]

    def _pump(pipe: Any, sink: list[str]) -> None:
        try:
            for line in iter(pipe.readline, ""):
                sink.append(line.rstrip("\n"))
        except Exception:  # noqa: BLE001 - pipe closed under us
            pass
        finally:
            with contextlib.suppress(Exception):
                pipe.close()

    threads: list[threading.Thread] = []
    if proc.stdout is not None:
        t = threading.Thread(target=_pump, args=(proc.stdout, stdout_lines), daemon=True)
        t.start()
        threads.append(t)
    if proc.stderr is not None:
        t = threading.Thread(target=_pump, args=(proc.stderr, stderr_lines), daemon=True)
        t.start()
        threads.append(t)
    return threads


def _writer_proc(harness: Harness, ctx: TaskContext) -> subprocess.Popen[str]:
    cmd = harness.build_cmd(ctx)
    env = os.environ.copy()
    env.update(
        {
            "CBENCH_TASK_ID": ctx.task.id,
            "CBENCH_SEED": str(ctx.seed),
            "CBENCH_TIME_BUDGET_S": str(ctx.time_budget_s),
            "CBENCH_MODEL": ctx.model,
            **ctx.env_vars,
        }
    )
    # Per-adapter environment sandboxing (e.g. CODEX_HOME pointing at a clean
    # auth-only copy, so user config/skills cannot leak into a trial).
    env.update(getattr(harness, "command_env", lambda: {})())
    return subprocess.Popen(  # noqa: S603 - argv list, no shell
        cmd,
        cwd=ctx.workspace,
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )


def _estimate_cost_so_far(
    harness: Harness, raw_lines: list[str], model: str
) -> tuple[float, dict[str, int], bool]:
    """Cost-so-far for live budget enforcement.

    Uses the adapter's native parsing (turn.completed events etc.) whenever it
    yields real usage, so the kill decision uses the same accounting as final
    scoring; falls back to the chars/4 text estimate only for harnesses with
    no native reporting. Returns (cost_usd, usage, is_native).
    """
    transcript = harness.parse_transcript(raw_lines)
    native_usage = {"input_tokens": 0, "output_tokens": 0, "reasoning_tokens": 0, "cached_tokens": 0}
    native = False
    for ev in transcript:
        u = ev.get("usage")
        if isinstance(u, dict) and not ev.get("usage_estimated", False):
            native = True
            for k in native_usage:
                native_usage[k] += int(u.get(k, 0))
    if native:
        usage = native_usage
    else:
        usage = {"input_tokens": 0, "output_tokens": 0, "reasoning_tokens": 0, "cached_tokens": 0}
        for line in raw_lines:
            est = estimate_usage_from_text(line)
            for k in usage:
                usage[k] += est[k]
    try:
        return cost_usd(usage, model), usage, native
    except KeyError:
        return 0.0, usage, native


def _native_capable(harness: Harness) -> bool:
    """True when the adapter is documented to emit native usage events."""
    return harness.profile.transcript_fidelity == "native"


def run_task(
    harness: Harness,
    task: Task,
    seed: int,
    run_dir: Path,
    backend: str,
    model: str,
    price_table: str = "1.0.0",
) -> TaskRunResult:
    """Execute one (harness, task, seed) trial and write artifacts."""
    slug = task.id.replace("/", "__")
    art = run_dir / "runs" / harness.name / f"{slug}-s{seed}"
    art.mkdir(parents=True, exist_ok=True)

    trial_dir = Path(tempfile.mkdtemp(prefix="cbench-trial-"))
    usage_estimated = True
    try:
        workspace, manifest = prepare_workspace(task, seed, trial_dir)
        prompt_file = trial_dir / "prompt.txt"
        prompt_file.write_text(harness.prompt_text(task), encoding="utf-8")

        ctx = TaskContext(
            task=task,
            seed=seed,
            workspace=workspace,
            prompt_file=prompt_file,
            time_budget_s=task.time_budget_s,
            model=model,
            env_vars=dict(task.raw.get("env_vars", {})),
        )

        deadline = time.monotonic() + task.time_budget_s
        checkpoints = [deadline - task.time_budget_s * f for f in CHECKPOINT_FRACTIONS]
        checkpoint_idx = 0

        raw_lines: list[str] = []
        outcome = "crash"
        exit_code: int | None = None
        start = time.monotonic()
        proc = None
        try:
            proc = _writer_proc(harness, ctx)
            drainers = _drain_pipes(proc)
            last_usage_poll = time.monotonic()
            timed_out = cost_killed = False
            while True:
                rc = proc.poll()
                now = time.monotonic()
                if rc is not None:
                    exit_code = rc
                    break
                if now >= deadline:
                    timed_out = True
                    break
                if checkpoint_idx < len(checkpoints) and now >= checkpoints[checkpoint_idx]:
                    _zip_workspace(
                        workspace, art / f"checkpoint-{int(CHECKPOINT_FRACTIONS[checkpoint_idx] * 100)}.zip"
                    )
                    checkpoint_idx += 1
                if now - last_usage_poll >= USAGE_POLL_S:
                    last_usage_poll = now
                    raw_lines = proc._cbench_stdout  # type: ignore[attr-defined]
                    if len(raw_lines) < MAX_TRANSCRIPT_LINES:
                        est_cost, _, native_seen = _estimate_cost_so_far(harness, raw_lines, model)
                        # Only enforce against native usage (or when no budget set):
                        # text estimates are noise for verbose harnesses. One grace
                        # poll after native usage first appears lets the first turn
                        # events land before we trust them.
                        if (
                            task.max_cost_usd > 0
                            and (native_seen or _native_capable(harness))
                            and est_cost > task.max_cost_usd
                        ):
                            cost_killed = True
                            break
                time.sleep(POLL_INTERVAL_S)

            if proc.poll() is None:
                proc.kill()
            try:
                proc.wait(timeout=30)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
            for t in drainers:
                t.join(timeout=10)
            raw_lines = list(proc._cbench_stdout)[:MAX_TRANSCRIPT_LINES]  # type: ignore[attr-defined]

            duration = time.monotonic() - start
            if cost_killed:
                outcome = "budget_cost"
            elif timed_out:
                outcome = "budget_time"
            elif exit_code is not None and exit_code < 0:
                outcome = "crash"
            elif exit_code == 0:
                outcome = "pass_candidate"
            else:
                outcome = "fail"
        finally:
            if proc is not None and proc.poll() is None:
                proc.kill()

        (art / "stdout.log").write_text("\n".join(raw_lines), encoding="utf-8")
        stderr_text = "\n".join(getattr(proc, "_cbench_stderr", []))[-100000:]
        (art / "stderr.log").write_text(stderr_text, encoding="utf-8")

        transcript = harness.parse_transcript(raw_lines)
        _write_jsonl(art / "transcript.jsonl", transcript)

        usage, usage_estimated = _aggregate(transcript, raw_lines, model)
        cost = cost_usd(usage, model, price_table) if _priceable(model, price_table) else 0.0

        # Sabotage check on final workspace state (before verification).
        sabotage = check_sabotage(workspace, manifest)
        if sabotage and outcome == "pass_candidate":
            outcome = "sabotage"

        _zip_workspace(workspace, art / "workspace.zip")

        verifier_ok: bool | None = None
        verifier_log = ""
        # The artifact decides: a harness exit code is not the verdict (CLIs
        # exit nonzero for unrelated reasons). Budget kills, crashes, and
        # sabotage skip verification — there is nothing fair to grade.
        if outcome in ("pass_candidate", "fail"):
            verifier_ok, verifier_log = run_verifier(task, workspace)
            outcome = "pass" if verifier_ok else "fail"
        elif outcome == "sabotage":
            verifier_ok = False
            verifier_log = sabotage or "sabotage"

        effective_model = harness.effective_model(transcript)

        result = TaskRunResult(
            harness=harness.name,
            task_id=task.id,
            seed=seed,
            outcome=outcome,
            exit_code=exit_code,
            duration_s=duration,
            usage=usage,
            usage_estimated=usage_estimated,
            cost_usd=cost,
            verifier_ok=verifier_ok,
            verifier_log=verifier_log,
            artifact_dir=art,
            requested_model=model,
            effective_model=effective_model,
        )
        (art / "result.json").write_text(json.dumps(result.to_dict(), indent=2), encoding="utf-8")
        (art / "verifier.log").write_text(verifier_log, encoding="utf-8")
        return result
    finally:
        shutil.rmtree(trial_dir, ignore_errors=True)


def _aggregate(
    transcript: list[dict[str, Any]], raw_lines: list[str], model: str
) -> tuple[dict[str, int], bool]:
    usage = {"input_tokens": 0, "output_tokens": 0, "reasoning_tokens": 0, "cached_tokens": 0}
    estimated = True
    for ev in transcript:
        u = ev.get("usage")
        if isinstance(u, dict) and not ev.get("usage_estimated", False):
            estimated = False
        if isinstance(u, dict):
            for k in usage:
                usage[k] += int(u.get(k, 0))
    if all(v == 0 for v in usage.values()) and raw_lines:
        for line in raw_lines:
            est = estimate_usage_from_text(line)
            for k in usage:
                usage[k] += est[k]
        estimated = True
    return usage, estimated


def _priceable(model: str, price_table: str) -> bool:
    from cli_bench.usage_proxy import PRICE_TABLES

    return model in PRICE_TABLES.get(price_table, {})


def run_verifier(task: Task, workspace: Path) -> tuple[bool, str]:
    """Run verifier.sh against a pristine copy of the final workspace."""
    verify_dir = Path(tempfile.mkdtemp(prefix="cbench-verify-"))
    try:
        vws = verify_dir / "workspace"
        shutil.copytree(workspace, vws)
        verifier_src = task.verifier()
        if not verifier_src.exists():
            return False, f"missing verifier: {verifier_src}"
        verifier_dst = verify_dir / "verifier.sh"
        shutil.copy2(verifier_src, verifier_dst)
        # Task-level helper files (reference implementations, seed materializers)
        # are part of the verifier's own tooling, not the workspace.
        for helper in task.path.glob("*.py"):
            shutil.copy2(helper, verify_dir / helper.name)
        # Optional pristine copies of shipped files, for verifiers that must
        # diff the workspace against what the task originally contained.
        # Staged into the verify-workspace itself (houdini/mutation's verifier
        # does `cd "$CBENCH_WORKSPACE"` and then references pristine/ relative
        # to the workspace) AND the verifier's own dir (for verifiers that
        # resolve it from their invocation cwd). The in-workspace copy is
        # named .cbench_pristine so tasks cannot accidentally collide, and
        # the same-name relative path is what the shipped verifier uses.
        pristine = task.path / "pristine"
        if pristine.exists():
            shutil.copytree(pristine, verify_dir / "pristine")
            shutil.copytree(pristine, vws / "pristine", dirs_exist_ok=True)
        proc = subprocess.run(
            ["bash", str(verifier_dst)],  # noqa: S603
            cwd=verify_dir,
            env={**os.environ, "CBENCH_WORKSPACE": str(vws)},
            capture_output=True,
            text=True,
            timeout=600,
            check=False,
        )
        log = f"exit={proc.returncode}\n--- stdout ---\n{proc.stdout}\n--- stderr ---\n{proc.stderr}"
        return proc.returncode == 0, log[-100000:]
    except subprocess.TimeoutExpired:
        return False, "verifier timed out"
    finally:
        shutil.rmtree(verify_dir, ignore_errors=True)


def _zip_workspace(workspace: Path, dest: Path) -> None:
    try:
        with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as zf:
            for p in sorted(workspace.rglob("*")):
                if p.is_file() and ".git" not in p.parts:
                    zf.write(p, p.relative_to(workspace))
    except Exception as exc:  # noqa: BLE001 - artifact failure must not kill the run
        print(f"[runner] workspace zip failed: {exc}")


def _write_jsonl(path: Path, events: list[dict[str, Any]]) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        for ev in events:
            fh.write(json.dumps(ev, default=str) + "\n")


def host_fingerprint() -> dict[str, str]:
    return {
        "platform": platform.platform(),
        "python": sys.version.split()[0],
        "machine": platform.machine(),
    }
