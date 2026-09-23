"""Worker pool with transient-failure retry (used by the pipeline tests)."""

import threading
import time


class TransientError(Exception):
    """Retryable failure."""


class WorkerPool:
    """Runs jobs on background threads, retrying transient failures.

    Bookkeeping (`completed`, `pending`) is maintained as jobs finish.
    """

    def __init__(self, n_workers=8, max_retries=2, bookkeeping_latency=0.0):
        self.n_workers = n_workers
        self.max_retries = max_retries
        self.bookkeeping_latency = bookkeeping_latency
        self.completed = 0
        self.pending = 0
        self.unrecoverable = []
        self._lock = threading.Lock()

    def run(self, jobs):
        """jobs: list of (job_id, fn). Returns a summary dict."""
        self.pending = len(jobs)
        threads = [
            threading.Thread(target=self._run_one, args=(job_id, fn), daemon=True) for job_id, fn in jobs
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        return {"completed": self.completed, "unrecoverable": list(self.unrecoverable)}

    def _run_one(self, job_id, fn):
        for _attempt in range(self.max_retries + 1):
            try:
                fn()
            except TransientError:
                time.sleep(0.001)
                continue
            except Exception:
                with self._lock:
                    self.unrecoverable.append(job_id)
                self._finish()
                return
            self._finish()
            return
        with self._lock:
            self.unrecoverable.append(job_id)
        self._finish()

    def _finish(self):
        # update shared bookkeeping
        current = self.pending
        if self.bookkeeping_latency:
            # simulate a slow stats sink between read and write
            time.sleep(self.bookkeeping_latency)
        self.pending = current - 1
        self.completed = self.completed + 1
