import threading
import time

from rate_limiter import TokenBucketLimiter


def test_initial_burst():
    limiter = TokenBucketLimiter(rate=1.0, capacity=5)
    for _ in range(5):
        assert limiter.acquire() is True
    assert limiter.acquire() is False


def test_refill():
    limiter = TokenBucketLimiter(rate=50.0, capacity=2)
    assert limiter.acquire(2) is True
    assert limiter.acquire() is False
    time.sleep(0.06)  # ~3 tokens
    assert limiter.acquire(2) is True


def test_partial_request_fails_cleanly():
    limiter = TokenBucketLimiter(rate=0.0, capacity=3)
    assert limiter.acquire(2) is True
    # only 1 token left; asking for 2 must not consume the remaining token
    assert limiter.acquire(2) is False
    assert limiter.acquire(1) is True


def test_retry_after():
    limiter = TokenBucketLimiter(rate=10.0, capacity=1)
    assert limiter.acquire() is True
    wait = limiter.retry_after()
    assert 0.0 <= wait <= 0.2
    time.sleep(wait + 0.02)
    assert limiter.acquire() is True


def test_try_acquire_all_success():
    limiter = TokenBucketLimiter(rate=0.0, capacity=5)
    assert limiter.try_acquire_all([1, 2, 2]) is True
    assert limiter.acquire() is False


def test_try_acquire_all_atomic_rollback():
    limiter = TokenBucketLimiter(rate=0.0, capacity=5)
    assert limiter.try_acquire_all([1, 2, 3]) is False  # needs 6 > 5
    # bucket must be completely unchanged: still 5 tokens
    assert limiter.try_acquire_all([5]) is True


def test_over_capacity_never_succeeds():
    limiter = TokenBucketLimiter(rate=100.0, capacity=4)
    assert limiter.acquire(5) is False
    time.sleep(0.05)
    assert limiter.acquire(5) is False  # even full refill cannot exceed capacity


def test_thread_safety():
    limiter = TokenBucketLimiter(rate=0.0, capacity=100)
    successes = []

    def worker():
        successes.append(limiter.acquire(1))

    threads = [threading.Thread(target=worker) for _ in range(100)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    # exactly 100 tokens available across 100 workers: every acquire must succeed
    assert sum(successes) == 100


def test_thread_safety_overload():
    limiter = TokenBucketLimiter(rate=0.0, capacity=10)
    successes = []
    lock = threading.Lock()

    def worker():
        ok = limiter.acquire(1)
        with lock:
            successes.append(ok)

    threads = [threading.Thread(target=worker) for _ in range(50)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    # exactly 10 of 50 succeed, never more
    assert sum(successes) == 10
