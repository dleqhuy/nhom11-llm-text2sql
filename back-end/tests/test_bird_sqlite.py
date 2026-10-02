import json
import sqlite3

import pytest

from experiments.bird_sqlite import BirdSQLite, QueryLimitError, QueryTimeoutError
from scripts.check_bird_gold import check_gold


@pytest.fixture
def database_root(tmp_path):
    root = tmp_path / "databases"
    nested = root / "school"
    nested.mkdir(parents=True)
    with sqlite3.connect(nested / "school.sqlite") as connection:
        connection.execute("CREATE TABLE pupils (id INTEGER PRIMARY KEY, name TEXT)")
        connection.executemany(
            "INSERT INTO pupils (name) VALUES (?)", [("An",), ("Binh",)]
        )
    with sqlite3.connect(root / "other.sqlite") as connection:
        connection.execute("CREATE TABLE scores (score INTEGER)")
        connection.execute("INSERT INTO scores VALUES (10)")
    return root


def test_resolves_nested_and_flat_databases_and_reads_schema(database_root):
    bird = BirdSQLite(database_root)
    assert bird.database_path("school").name == "school.sqlite"
    assert bird.database_path("other").name == "other.sqlite"
    table = bird.schema("school")[0]
    assert table.name == "pupils"
    assert [column.name for column in table.columns] == ["id", "name"]
    assert table.columns[0].primary_key
    assert "CREATE TABLE pupils" in table.create_sql
    assert bird.execute("school", "SELECT name FROM pupils ORDER BY id").rows == (
        ("An",),
        ("Binh",),
    )


def test_rejects_unknown_or_unsafe_db_id(database_root):
    bird = BirdSQLite(database_root)
    with pytest.raises(ValueError, match="Invalid db_id"):
        bird.database_path("../school")
    with pytest.raises(FileNotFoundError, match="missing"):
        bird.database_path("missing")


@pytest.mark.parametrize(
    "sql",
    [
        "DELETE FROM pupils",
        "UPDATE pupils SET name='Changed'",
        "CREATE TABLE x (a INTEGER)",
        "ATTACH DATABASE ':memory:' AS extra",
        "PRAGMA query_only=OFF",
        "SELECT name FROM pupils; DELETE FROM pupils",
    ],
)
def test_rejects_mutating_and_multi_statement_sql(database_root, sql):
    bird = BirdSQLite(database_root)
    with pytest.raises((sqlite3.Error, ValueError)):
        bird.execute("school", sql)
    assert bird.execute("school", "SELECT COUNT(*) FROM pupils").rows == ((2,),)


def test_limits_rows_and_stops_long_query(database_root):
    bird = BirdSQLite(database_root)
    with pytest.raises(QueryLimitError):
        bird.execute("school", "SELECT name FROM pupils", max_rows=1)
    with pytest.raises(QueryTimeoutError):
        bird.execute(
            "school",
            "WITH RECURSIVE numbers(n) AS "
            "(SELECT 1 UNION ALL SELECT n+1 FROM numbers WHERE n<100000000) "
            "SELECT SUM(n) FROM numbers",
            timeout_seconds=0.001,
        )


def test_checks_gold_queries_and_reports_failures(database_root, tmp_path):
    gold = tmp_path / "gold.json"
    gold.write_text(
        json.dumps(
            [
                {
                    "question_id": 1,
                    "db_id": "school",
                    "SQL": "SELECT COUNT(*) FROM pupils",
                },
                {"question_id": 2, "db_id": "other", "SQL": "SELECT score FROM scores"},
                {"question_id": 3, "db_id": "school", "SQL": "SELECT * FROM absent"},
            ]
        ),
        encoding="utf-8",
    )
    count, failures = check_gold(gold, database_root)
    assert count == 3
    assert len(failures) == 1
    assert failures[0][0:2] == (3, "school")
