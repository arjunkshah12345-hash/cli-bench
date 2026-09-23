"""UsageProxy: token & cost accounting for harness runs.

Priority (per SPEC §5.4):
  1. Native usage reported by the adapter per turn.
  2. Transcript-derived estimation (chars/4 heuristic), marked estimated=true.

Cache-read tokens are discounted 0.1x for CB braking (SPEC §4.1).
"""

from __future__ import annotations

import json
import math
import statistics
from typing import Any

# USD per 1M tokens: (input, cached_input, output). Versioned; pinned in run manifests.
PRICE_TABLES: dict[str, dict[str, tuple[float, float, float]]] = {
    "1.0.0": {
        "openai/gpt-5.3": (1.25, 0.125, 10.0),
        "openai/gpt-5-mini": (0.25, 0.025, 2.0),
        "anthropic/claude-opus-4-6": (5.0, 0.5, 25.0),
        "anthropic/claude-sonnet-4-5": (3.0, 0.3, 15.0),
        "google/gemini-3-pro": (1.25, 0.31, 10.0),
    }
}

CACHE_DISCOUNT = 0.1
CHARS_PER_TOKEN = 4.0


class BudgetError(Exception):
    """Raised when a run exceeds its cost ceiling."""


def estimate_usage_from_text(text: str) -> dict[str, int]:
    """chars/4 heuristic for transcript lines without native usage."""
    tokens = max(1, int(len(text) / CHARS_PER_TOKEN))
    return {"input_tokens": tokens, "output_tokens": 0, "reasoning_tokens": 0, "cached_tokens": 0}


def merge_usage(dst: dict[str, int], src: dict[str, int]) -> dict[str, int]:
    for key in ("input_tokens", "output_tokens", "reasoning_tokens", "cached_tokens"):
        dst[key] = dst.get(key, 0) + src.get(key, 0)
    return dst


def effective_tokens(usage: dict[str, int]) -> int:
    """Token spend b used for braking: input + output + reasoning + cache-discounted reads."""
    return int(
        usage.get("input_tokens", 0)
        + usage.get("output_tokens", 0)
        + usage.get("reasoning_tokens", 0)
        + CACHE_DISCOUNT * usage.get("cached_tokens", 0)
    )


def cost_usd(usage: dict[str, int], model: str, price_table: str = "1.0.0") -> float:
    table = PRICE_TABLES.get(price_table)
    if table is None:
        raise KeyError(f"unknown price table {price_table!r}")
    if model not in table:
        raise KeyError(f"model {model!r} not in price table {price_table!r}")
    inp, cached, out = table[model]
    total = (
        usage.get("input_tokens", 0) * inp / 1e6
        + usage.get("cached_tokens", 0) * cached / 1e6
        + (usage.get("output_tokens", 0) + usage.get("reasoning_tokens", 0)) * out / 1e6
    )
    return round(total, 6)


def aggregate_usage(usage_events: list[dict[str, Any]]) -> dict[str, int]:
    agg = {"input_tokens": 0, "output_tokens": 0, "reasoning_tokens": 0, "cached_tokens": 0}
    for ev in usage_events:
        merge_usage(agg, ev)
    return agg


def median_or_zero(values: list[float]) -> float:
    return statistics.median(values) if values else 0.0


def read_jsonl(path: Any) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return events


def safe_div(numerator: float, denominator: float) -> float:
    if denominator == 0:
        return 0.0
    return numerator / denominator


def is_finite(x: float) -> bool:
    return math.isfinite(x)
