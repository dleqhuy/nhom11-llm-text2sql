"""Validate and split the 500-question BIRD Mini-Dev SQLite dataset."""

from __future__ import annotations

import hashlib
import json
import random
from collections import Counter, defaultdict
from pathlib import Path

TARGETS = {"simple": 36, "moderate": 60, "challenging": 24}
OUTPUT_NAMES = ("test_en.json", "gold_120.json", "examples_380.json", "manifest.json")


def load_source(path: Path) -> tuple[list[dict], str]:
    raw = path.read_bytes()
    rows = json.loads(raw.decode("utf-8-sig"))
    if not isinstance(rows, list):
        raise ValueError("BIRD source must be a JSON array")
    return rows, hashlib.sha256(raw).hexdigest()


def validate_source(rows: list[dict]) -> None:
    if len(rows) != 500:
        raise ValueError(f"Expected Mini-Dev's 500 questions; found {len(rows)}")

    seen_ids: set[int] = set()
    databases: set[str] = set()
    difficulties: Counter[str] = Counter()
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise ValueError(f"Question {index} must be an object")
        question_id = row.get("question_id")
        if isinstance(question_id, bool) or not isinstance(question_id, int):
            raise ValueError(f"Question {index} has no integer question_id")
        if question_id in seen_ids:
            raise ValueError(f"Duplicate question_id: {question_id}")
        seen_ids.add(question_id)

        for field in ("db_id", "question", "SQL"):
            if not isinstance(row.get(field), str) or not row[field].strip():
                raise ValueError(f"Question {question_id} has no {field}")
        if not isinstance(row.get("evidence"), str):
            raise ValueError(f"Question {question_id} has invalid evidence")
        difficulty = row.get("difficulty")
        if difficulty not in TARGETS:
            raise ValueError(f"Question {question_id} has invalid difficulty")
        databases.add(row["db_id"])
        difficulties[difficulty] += 1

    if len(databases) != 11:
        raise ValueError(f"Expected 11 databases; found {len(databases)}")
    for difficulty, target in TARGETS.items():
        if difficulties[difficulty] < target:
            raise ValueError(f"Not enough {difficulty} questions for target {target}")


def _round_robin_sample(rows: list[dict], count: int, rng: random.Random) -> list[dict]:
    by_database: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        by_database[row["db_id"]].append(row)
    for db_id in sorted(by_database):
        bucket = by_database[db_id]
        bucket.sort(key=lambda row: row["question_id"])
        rng.shuffle(bucket)

    database_ids = sorted(by_database)
    rng.shuffle(database_ids)
    selected: list[dict] = []
    while len(selected) < count:
        for db_id in database_ids:
            if by_database[db_id]:
                selected.append(by_database[db_id].pop())
                if len(selected) == count:
                    break
    return selected


def split_source(rows: list[dict], seed: int) -> tuple[list[dict], list[dict]]:
    """Select 36/60/24 test questions, rotating databases within each level."""
    validate_source(rows)
    rng = random.Random(seed)
    selected: list[dict] = []
    for difficulty, target in TARGETS.items():
        pool = [row for row in rows if row["difficulty"] == difficulty]
        selected.extend(_round_robin_sample(pool, target, rng))
    selected_ids = {row["question_id"] for row in selected}
    test = sorted(selected, key=lambda row: row["question_id"])
    examples = sorted(
        (row for row in rows if row["question_id"] not in selected_ids),
        key=lambda row: row["question_id"],
    )
    return test, examples


def prepare_dataset(
    source: Path, output_dir: Path, *, seed: int, source_version: str
) -> dict:
    if not source_version.strip():
        raise ValueError("source_version is required to identify the dataset release")
    rows, source_sha256 = load_source(source)
    test, examples = split_source(rows, seed)

    destinations = {name: output_dir / name for name in OUTPUT_NAMES}
    existing = [name for name, path in destinations.items() if path.exists()]
    if existing:
        raise FileExistsError(f"Output already exists: {', '.join(existing)}")

    test_questions = [
        {
            key: row[key]
            for key in ("question_id", "db_id", "question", "evidence", "difficulty")
        }
        for row in test
    ]
    gold = [{key: row[key] for key in ("question_id", "db_id", "SQL")} for row in test]
    example_questions = [
        {
            key: row[key]
            for key in (
                "question_id",
                "db_id",
                "question",
                "evidence",
                "SQL",
                "difficulty",
            )
        }
        for row in examples
    ]
    manifest = {
        "dataset": "BIRD Mini-Dev SQLite (500-question release)",
        "source_version": source_version.strip(),
        "source_sha256": source_sha256,
        "seed": seed,
        "test_count": len(test),
        "example_count": len(examples),
        "test_difficulty": dict(
            sorted(Counter(row["difficulty"] for row in test).items())
        ),
        "test_database": dict(sorted(Counter(row["db_id"] for row in test).items())),
        "test_question_ids": [row["question_id"] for row in test],
        "example_question_ids": [row["question_id"] for row in examples],
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    for name, data in (
        ("test_en.json", test_questions),
        ("gold_120.json", gold),
        ("examples_380.json", example_questions),
        ("manifest.json", manifest),
    ):
        destinations[name].write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    return manifest
