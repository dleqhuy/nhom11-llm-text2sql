"""Check whether every selected BIRD gold SQL query runs on its SQLite DB."""

import argparse
import json
import sqlite3
from pathlib import Path

from experiments.bird_sqlite import BirdSQLite, QueryLimitError, QueryTimeoutError


def check_gold(gold_path: Path, database_root: Path, *, timeout_seconds: float = 5.0):
    rows = json.loads(gold_path.read_text(encoding="utf-8"))
    if not isinstance(rows, list):
        raise ValueError("Gold file must contain a JSON array")
    databases = BirdSQLite(database_root)
    missing = []
    for db_id in sorted({row["db_id"] for row in rows}):
        try:
            databases.database_path(db_id)
        except FileNotFoundError:
            missing.append(db_id)
    if missing:
        raise FileNotFoundError("Missing BIRD SQLite databases: " + ", ".join(missing))
    failures = []
    for row in rows:
        question_id = row["question_id"]
        try:
            databases.execute(row["db_id"], row["SQL"], timeout_seconds=timeout_seconds)
        except (
            FileNotFoundError,
            ValueError,
            sqlite3.Error,
            QueryTimeoutError,
            QueryLimitError,
        ) as exc:
            failures.append((question_id, row["db_id"], str(exc)))
    return len(rows), failures


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--gold", type=Path, default=Path("data/bird_split/gold_120.json")
    )
    parser.add_argument("--db-root", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=5.0)
    args = parser.parse_args()
    try:
        count, failures = check_gold(
            args.gold, args.db_root, timeout_seconds=args.timeout
        )
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    print(f"Gold SQL executed: {count - len(failures)}/{count}")
    for question_id, db_id, error in failures:
        print(f"  question_id={question_id} db_id={db_id}: {error}")
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
