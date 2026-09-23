"""Seed materializer for feature/csv-normalizer.

Generates a 400-row messy input.csv. Deterministic per CBENCH_SEED: every seed
produces materially different data (names, dates, formats, malformation rate).
"""

import csv
import os
import random
from datetime import date, timedelta

FIRST = [
    "alice",
    "bob",
    "carol",
    "dave",
    "erin",
    "frank",
    "grace",
    "heidi",
    "ivan",
    "judy",
    "mallory",
    "niaj",
    "olivia",
    "peggy",
    "rupert",
    "sybil",
    "trent",
    "victor",
    "wendy",
    "zoe",
]
LAST = [
    "anderson",
    "brown",
    "chen",
    "diaz",
    "evans",
    "foster",
    "garcia",
    "hughes",
    "ibarra",
    "jones",
    "khan",
    "lopez",
    "moore",
    "nguyen",
    "o'brien",
    "patel",
    "quinn",
    "rodriguez",
    "smith",
    "tanaka",
]
PLANS = ["basic", "pro", "enterprise"]
PLAN_BASE = {"basic": (29, 49), "pro": (99, 149), "enterprise": (499, 999)}
DATE_FORMATS = ["iso", "us", "long", "datetime"]


def messy_name(rng: random.Random, first: str, last: str) -> str:
    name = f"{first} {last}"
    return rng.choice([name, name.upper(), name.lower(), name.title(), f"  {name}  ", ""])


def messy_email(rng: random.Random, i: int, first: str, last: str) -> str:
    base = f"{first}.{last}.{i}@example.com"
    variant = rng.random()
    if variant < 0.08:
        return ""
    if variant < 0.12:
        return base.replace("@", "")  # invalid
    if variant < 0.16:
        return base.replace("@", " at ").replace(".", " dot ")  # spaces → invalid
    return rng.choice([base, base.upper(), f" {base} "])


def messy_date(rng: random.Random, d: date) -> str:
    fmt = rng.choice(DATE_FORMATS)
    if fmt == "iso":
        return d.isoformat()
    if fmt == "us":
        return f"{d.month:02d}/{d.day:02d}/{d.year}"
    if fmt == "long":
        return d.strftime("%B ") + f"{d.day}, {d.year}"
    return d.isoformat() + f" {rng.randrange(0, 24):02d}:{rng.randrange(0, 60):02d}:00"


def messy_plan(rng: random.Random) -> str:
    r = rng.random()
    if r < 0.04:
        return rng.choice(["", "premium", "FREE-TIER", "Basic "])
    p = rng.choice(PLANS)
    return rng.choice([p, p.upper(), p.capitalize()])


def messy_mrr(rng: random.Random, plan: str) -> str:
    r = rng.random()
    if r < 0.05:
        return "free"
    if r < 0.08:
        return ""
    if plan in PLAN_BASE:
        lo, hi = PLAN_BASE[plan]
        v = rng.choice([lo, hi])
    else:
        v = rng.choice([19, 39, 59])
    style = rng.random()
    if style < 0.3:
        return str(v)
    if style < 0.6:
        return f"${v}.00"
    if style < 0.8:
        return f"{v}.00"
    return f"{v:,}.00"


def main() -> None:
    seed = int(os.environ.get("CBENCH_SEED", "0"))
    rng = random.Random(9000 + seed)
    base = date(2024, 1, 1)
    with open("data/input.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["id", "Name", "Email", "SignupDate", "Plan", "MRR_USD"])
        for i in range(1, 401):
            first, last = rng.choice(FIRST), rng.choice(LAST)
            d = base + timedelta(days=rng.randrange(0, 730))
            plan = messy_plan(rng)
            w.writerow(
                [
                    i,
                    messy_name(rng, first, last),
                    messy_email(rng, i, first, last),
                    messy_date(rng, d),
                    plan,
                    messy_mrr(rng, plan),
                ]
            )


if __name__ == "__main__":
    main()
