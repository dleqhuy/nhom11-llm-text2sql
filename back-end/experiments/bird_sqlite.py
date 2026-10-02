"""Read BIRD SQLite databases without allowing database mutations."""

from __future__ import annotations

import re
import sqlite3
import time
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path

DB_ID_PATTERN = re.compile(r"[A-Za-z0-9_]+\Z")
ALLOWED_ACTIONS = {
    sqlite3.SQLITE_SELECT,
    sqlite3.SQLITE_READ,
    sqlite3.SQLITE_FUNCTION,
    sqlite3.SQLITE_RECURSIVE,
}


class QueryTimeoutError(TimeoutError):
    """The SQLite progress handler stopped a long-running query."""


class QueryLimitError(ValueError):
    """A query returned more rows than the configured safe limit."""


@dataclass(frozen=True)
class Column:
    name: str
    type: str
    primary_key: bool


@dataclass(frozen=True)
class Table:
    name: str
    kind: str
    columns: tuple[Column, ...]
    create_sql: str | None


@dataclass(frozen=True)
class QueryResult:
    columns: tuple[str, ...]
    rows: tuple[tuple, ...]


class BirdSQLite:
    """Resolve BIRD's ``db_id/db_id.sqlite`` layout or flat SQLite files."""

    def __init__(self, database_root: Path):
        self.root = database_root.resolve()
        if not self.root.is_dir():
            raise FileNotFoundError(f"Database directory does not exist: {self.root}")

    def database_path(self, db_id: str) -> Path:
        if not DB_ID_PATTERN.fullmatch(db_id):
            raise ValueError(f"Invalid db_id: {db_id!r}")
        candidates = (
            self.root / db_id / f"{db_id}.sqlite",
            self.root / f"{db_id}.sqlite",
        )
        found = [path.resolve() for path in candidates if path.is_file()]
        if len(found) != 1:
            raise FileNotFoundError(
                f"Expected one SQLite file for {db_id!r} under {self.root}; "
                f"found {len(found)}"
            )
        path = found[0]
        if not path.is_relative_to(self.root):
            raise ValueError(f"SQLite path escapes database directory: {path}")
        return path

    def _connect(self, db_id: str) -> sqlite3.Connection:
        path = self.database_path(db_id)
        connection = sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True)
        connection.execute("PRAGMA query_only=ON")
        return connection

    def schema(self, db_id: str) -> tuple[Table, ...]:
        with closing(self._connect(db_id)) as connection:
            records = connection.execute(
                "SELECT name, type, sql FROM sqlite_master "
                "WHERE type IN ('table', 'view') AND name NOT LIKE 'sqlite_%' "
                "ORDER BY name"
            ).fetchall()
            tables = []
            for name, kind, create_sql in records:
                quoted_name = '"' + name.replace('"', '""') + '"'
                columns = tuple(
                    Column(name=row[1], type=row[2], primary_key=bool(row[5]))
                    for row in connection.execute(f"PRAGMA table_info({quoted_name})")
                )
                tables.append(Table(name, kind, columns, create_sql))
            return tuple(tables)

    def execute(
        self,
        db_id: str,
        sql: str,
        *,
        timeout_seconds: float = 5.0,
        max_rows: int = 100_000,
    ) -> QueryResult:
        if not sql.strip():
            raise ValueError("SQL must not be empty")
        if timeout_seconds <= 0 or max_rows <= 0:
            raise ValueError("timeout_seconds and max_rows must be positive")

        deadline = time.monotonic() + timeout_seconds
        timed_out = False

        def progress() -> int:
            nonlocal timed_out
            timed_out = time.monotonic() >= deadline
            return int(timed_out)

        def authorize(action, arg1, arg2, db_name, source) -> int:
            if action not in ALLOWED_ACTIONS:
                return sqlite3.SQLITE_DENY
            # SQLite reports no database name for COUNT(*) without a column read.
            if action == sqlite3.SQLITE_READ and db_name not in ("main", None):
                return sqlite3.SQLITE_DENY
            if action == sqlite3.SQLITE_FUNCTION and (
                (arg2 or "").lower() in {"load_extension", "readfile", "writefile"}
                or (arg2 or "").lower().startswith("pragma_")
            ):
                return sqlite3.SQLITE_DENY
            return sqlite3.SQLITE_OK

        with closing(self._connect(db_id)) as connection:
            connection.set_authorizer(authorize)
            connection.set_progress_handler(progress, 1_000)
            try:
                cursor = connection.execute(sql)
                if cursor.description is None:
                    raise ValueError("Only queries returning rows are allowed")
                rows = tuple(cursor.fetchmany(max_rows + 1))
                if len(rows) > max_rows:
                    raise QueryLimitError(f"Query returned more than {max_rows} rows")
                return QueryResult(
                    tuple(column[0] for column in cursor.description), rows
                )
            except sqlite3.OperationalError as exc:
                if timed_out:
                    raise QueryTimeoutError(
                        f"SQLite query exceeded {timeout_seconds} seconds"
                    ) from exc
                raise
            finally:
                connection.set_progress_handler(None, 0)
                connection.set_authorizer(None)
