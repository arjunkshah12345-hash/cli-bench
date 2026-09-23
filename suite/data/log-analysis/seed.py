"""Seed materializer for data/log-analysis.

Generates data/app.log deterministically per CBENCH_SEED: different endpoints,
traffic mix, error injection points, and latency profile per seed.
"""

import json
import os
import random
from datetime import UTC, datetime, timedelta

ENDPOINTS = ["/api/users", "/api/orders", "/api/search", "/api/health", "/api/items", "/api/cart"]
STATUSES = [200, 200, 200, 201, 400, 404, 429, 500, 502]
WEIGHTS = [38, 20, 15, 7, 6, 5, 4, 3, 2]


def main() -> None:
    seed = int(os.environ.get("CBENCH_SEED", "0"))
    rng = random.Random(4200 + seed)

    os.makedirs("data", exist_ok=True)
    start = datetime(2026, 3, 1, 0, 0, 0, tzinfo=UTC)
    n_lines = 1200 + seed * 137
    # per-seed endpoint popularity shuffle → different top_endpoint & busiest_minute
    ep_weights = [WEIGHTS[i] for i in rng.sample(range(len(ENDPOINTS)), len(ENDPOINTS))]

    lines = []
    req_no = 0
    for _i in range(n_lines):
        ts = start + timedelta(seconds=rng.randrange(0, 5400))
        roll = rng.random()
        if roll < 0.86:  # request line
            req_no += 1
            ep = rng.choices(ENDPOINTS, weights=ep_weights)[0]
            status = rng.choices(STATUSES, weights=WEIGHTS)[0]
            base_lat = {
                "api/users": 40,
                "api/orders": 90,
                "api/search": 220,
                "api/health": 3,
                "api/items": 55,
                "api/cart": 70,
            }[ep.lstrip("/")]
            latency = max(1, int(rng.gauss(base_lat, base_lat * 0.35)))
            # spike: 0.4% of requests get a huge latency (p95 shaper)
            if rng.random() < 0.004:
                latency = int(latency * rng.uniform(6, 14))
            level = "ERROR" if status >= 500 else "WARN" if status >= 400 else "INFO"
            lines.append(
                {
                    "ts": ts.isoformat().replace("+00:00", "Z"),
                    "level": level,
                    "context": "request",
                    "endpoint": ep,
                    "http_status": status,
                    "latency_ms": latency,
                    "request_id": f"req-{seed}-{req_no:05d}",
                }
            )
        elif roll < 0.94:
            lines.append(
                {
                    "ts": ts.isoformat().replace("+00:00", "Z"),
                    "level": "INFO",
                    "context": "system",
                    "msg": rng.choice(["heartbeat", "gc pause 12ms", "checkpoint written"]),
                }
            )
        else:
            lines.append(
                {
                    "ts": ts.isoformat().replace("+00:00", "Z"),
                    "level": rng.choice(["INFO", "WARN"]),
                    "context": "db",
                    "msg": rng.choice(["pool at 60%", "slow query 240ms", "vacuum scheduled"]),
                }
            )

    with open("data/app.log", "w", encoding="utf-8") as fh:
        for line in lines:
            fh.write(json.dumps(line) + "\n")


if __name__ == "__main__":
    main()
