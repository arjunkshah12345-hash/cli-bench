"""Seed materializer for houdini/hidden-spec.

Regenerates transactions.csv per seed with different merchants, amounts, and
timestamps. The embedded processing rules stay in the header; the numbers
change so only agents that actually read the data produce correct output.
"""

import csv
import os
import random

MERCHANTS = ["acme", "globex", "initech", "umbrella", "soylent", "hooli", "stark"]


def main() -> None:
    seed = int(os.environ.get("CBENCH_SEED", "0"))
    rng = random.Random(31000 + seed)
    os.makedirs("data", exist_ok=True)
    base_ts = 1767225600
    rows = []
    for _ in range(10 + seed * 2):
        ts = base_ts + rng.randrange(0, 14 * 86400)
        merchant = rng.choice(MERCHANTS[: 3 + seed])
        amount = round(rng.uniform(-80, 300), 2)
        fee = round(abs(amount) * rng.uniform(0.01, 0.03), 2)
        rows.append((ts, merchant, f"{amount:.2f}", f"{fee:.2f}"))
    rows.sort(key=lambda r: r[0])

    with open("data/transactions.csv", "w", newline="", encoding="utf-8") as fh:
        fh.write("# PROCESSING_RULES (v3, 2026-05-14) — applies to every data row below\n")
        fh.write("# amount and fee are USD; balance_delta = amount - fee\n")
        fh.write("# RULE grouped-summary: emit one object per merchant, in this exact key order:\n")
        fh.write("#   merchant, transaction_count, total_volume, net_total, first_ts, last_ts\n")
        fh.write("# RULE amounts: total_volume = sum of |amount| over the merchant's transactions;\n")
        fh.write("#   net_total = sum of (amount - fee), rounded to 2 decimals\n")
        fh.write('# RULE timestamps: first_ts / last_ts are ISO-8601 UTC "YYYY-MM-DDTHH:MM:SSZ";\n')
        fh.write("#   the source log stores them as Unix epoch seconds — convert, do not truncate\n")
        fh.write(
            "# RULE ordering: merchants sorted by net_total descending, ties by merchant name ascending\n"
        )
        fh.write("# RULE output: JSON array written to data/output.json, UTF-8, 2-space indent\n")
        w = csv.writer(fh)
        w.writerow(["ts", "merchant", "amount", "fee"])
        for r in rows:
            w.writerow(r)


if __name__ == "__main__":
    main()
