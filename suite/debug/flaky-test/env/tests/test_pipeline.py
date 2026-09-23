import json
from pathlib import Path

from jobs import TransientError, WorkerPool


def _conf():
    p = Path(__file__).resolve().parent.parent / "config.json"
    if p.exists():
        return json.loads(p.read_text())
    return {"workers": 12, "jobs": 12, "bookkeeping_latency": 0.0003, "scatter_us": 100}


def test_all_jobs_complete():
    conf = _conf()
    pool = WorkerPool(n_workers=conf["workers"], bookkeeping_latency=conf["bookkeeping_latency"])
    calls = {}

    def make_fn(job_id):
        def fn():
            calls[job_id] = calls.get(job_id, 0) + 1
            if job_id % 2 == 1 and calls[job_id] == 1:
                raise TransientError("first attempt fails")
            # vary job duration so completion times scatter
            import time

            time.sleep(conf["scatter_us"] * ((job_id * 7) % 13) / 1_000_000)

        return fn

    jobs = [(i, make_fn(i)) for i in range(conf["jobs"])]
    out = pool.run(jobs)
    assert out["completed"] == conf["jobs"], f"completed={out['completed']}"
    assert out["unrecoverable"] == []
    assert pool.pending == 0, f"pending={pool.pending}"


def test_retry_eventually_succeeds():
    pool = WorkerPool(n_workers=4, max_retries=3, bookkeeping_latency=0)
    calls = {"n": 0}

    def fn():
        calls["n"] += 1
        if calls["n"] < 3:
            raise TransientError("not yet")

    pool.run([(1, fn)])
    assert calls["n"] == 3
    assert pool.completed == 1


def test_unrecoverable_reported():
    pool = WorkerPool(n_workers=2, bookkeeping_latency=0)

    def fn():
        raise ValueError("permanent")

    out = pool.run([(1, fn), (2, lambda: None)])
    assert out["unrecoverable"] == [1]
    assert out["completed"] == 1
