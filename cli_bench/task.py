"""Task loading and validation for CLI-Bench."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

CATEGORIES = [
    "refactor",
    "feature",
    "debugging",
    "tooling",
    "data",
    "ops",
    "security",
    "perf",
    "docs",
    "cleanup",
]
DIFFICULTIES = ["warmup", "standard", "hard", "frontier"]
DIFFICULTY_WEIGHTS = {
    "warmup": 1.0,
    "standard": 1.25,
    "hard": 1.5,
    "frontier": 1.75,
}
CATEGORY_WEIGHTS = {
    "refactor": 1.25,
    "feature": 1.25,
    "debugging": 1.2,
    "tooling": 1.1,
    "data": 1.1,
    "ops": 1.0,
    "security": 1.0,
    "perf": 1.0,
    "docs": 0.9,
    "cleanup": 0.75,
}


class TaskValidationError(ValueError):
    """Raised when a task.yaml fails validation."""


@dataclass
class Task:
    """A parsed and validated benchmark task."""

    id: str
    title: str
    prompt: str
    category: str
    difficulty: str
    time_budget_s: int
    max_cost_usd: float
    seeds: int
    requires: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    path: Path = field(default_factory=Path)
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def weight(self) -> float:
        return CATEGORY_WEIGHTS[self.category] * DIFFICULTY_WEIGHTS[self.difficulty]

    @property
    def is_quality_probe(self) -> bool:
        return "quality_probe" in self.tags

    def verifier(self) -> Path:
        return self.path / "verifier.sh"

    def env_dir(self) -> Path:
        return self.path / "env"

    def dockerfile(self) -> Path:
        return self.path / "Dockerfile"

    def checksums(self) -> dict[str, str]:
        """SHA-256 over env/ + verifier.sh (SPEC §7.1)."""
        out: dict[str, str] = {}
        verifier = self.verifier()
        if verifier.exists():
            out["verifier.sh"] = _sha256(verifier.read_bytes())
        env = self.env_dir()
        if env.exists():
            for p in sorted(env.rglob("*")):
                if p.is_file():
                    out[str(p.relative_to(self.path))] = _sha256(p.read_bytes())
        return out

    def to_manifest(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "category": self.category,
            "difficulty": self.difficulty,
            "time_budget_s": self.time_budget_s,
            "max_cost_usd": self.max_cost_usd,
            "seeds": self.seeds,
            "tags": self.tags,
            "requires": self.requires,
            "weight": self.weight,
            "checksums": self.checksums(),
        }


def load_task(task_dir: Path) -> Task:
    meta_path = task_dir / "task.yaml"
    if not meta_path.exists():
        raise TaskValidationError(f"{task_dir}: missing task.yaml")
    raw = yaml.safe_load(meta_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise TaskValidationError(f"{meta_path}: task.yaml must be a mapping")

    required = ["id", "title", "prompt", "category", "difficulty", "time_budget_s", "max_cost_usd", "seeds"]
    missing = [k for k in required if k not in raw]
    if missing:
        raise TaskValidationError(f"{meta_path}: missing fields {missing}")

    if raw["category"] not in CATEGORIES:
        raise TaskValidationError(f"{meta_path}: unknown category {raw['category']!r}")
    if raw["difficulty"] not in DIFFICULTIES:
        raise TaskValidationError(f"{meta_path}: unknown difficulty {raw['difficulty']!r}")
    if not raw["id"].strip() or "/" not in raw["id"]:
        raise TaskValidationError(f"{meta_path}: id must look like 'category/name'")

    for req in raw.get("requires", []):
        if not isinstance(req, str):
            raise TaskValidationError(f"{meta_path}: requires entries must be strings")

    return Task(
        id=raw["id"],
        title=raw["title"],
        prompt=raw["prompt"],
        category=raw["category"],
        difficulty=raw["difficulty"],
        time_budget_s=int(raw["time_budget_s"]),
        max_cost_usd=float(raw["max_cost_usd"]),
        seeds=int(raw["seeds"]),
        requires=list(raw.get("requires", [])),
        tags=list(raw.get("tags", [])),
        path=task_dir.resolve(),
        raw=raw,
    )


def load_suite(suite_dir: Path, include_houdini: bool = False) -> list[Task]:
    """Load every scored task under suite/.

    Houdini anti-gaming probes are excluded by default (they gate, not score);
    pass include_houdini=True (CLI: --with-houdini) to append them.
    """
    suite_dir = suite_dir.resolve()
    if not suite_dir.exists():
        raise FileNotFoundError(f"suite dir not found: {suite_dir}")
    tasks: list[Task] = []
    for task_yaml in sorted(suite_dir.glob("*/*/task.yaml")):
        task = load_task(task_yaml.parent)
        if task.id.startswith("houdini/") and not include_houdini:
            continue
        tasks.append(task)
    if not tasks:
        raise FileNotFoundError(f"no tasks found under {suite_dir}")
    seen: set[str] = set()
    for t in tasks:
        if t.id in seen:
            raise TaskValidationError(f"duplicate task id: {t.id}")
        seen.add(t.id)
    return tasks


def load_houdini(suite_dir: Path) -> list[Task]:
    return [
        load_task(p.parent) for p in sorted(suite_dir.glob("*/*/task.yaml")) if "houdini" in str(p.parent)
    ]


def checksums_match(task: Task, recorded: dict[str, str]) -> bool:
    return json.dumps(task.checksums(), sort_keys=True) == json.dumps(recorded, sort_keys=True)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
