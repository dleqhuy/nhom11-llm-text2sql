from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine, Result

from .sql_policy import enforce_readonly, split_statements


def json_safe(value: Any) -> Any:
    """Match JSON serialization used by DBHub closely for PostgreSQL values."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Decimal):
        # node-postgres returns numeric/decimal as strings by default.
        return str(value)
    if isinstance(value, (bytes, bytearray, memoryview)):
        return bytes(value).hex()
    # DBHub's PostgreSQL connector configures date/time parsers to return the
    # server's textual representation, so normally these arrive here as str.
    # Keep a deterministic fallback for any SQLAlchemy-native objects.
    return str(value)


def statement_payload(result: Result, sql: str, max_rows: int | None) -> dict[str, Any]:
    """Build the same per-statement shape as DBHub's toStatementsPayload()."""
    if not result.returns_rows:
        row_count = result.rowcount if result.rowcount is not None and result.rowcount >= 0 else 0
        return {"sql": sql, "rows": [], "count": row_count}

    rows: list[dict[str, Any]] = []
    truncated = False
    iterator = result.mappings()

    # The DBHub connector applies a max_rows+1 probe at the SQL layer. We mimic
    # the observable result here by fetching one extra row and dropping it.
    probe_limit = max_rows + 1 if max_rows is not None else None
    for row in iterator:
        if probe_limit is not None and len(rows) >= probe_limit:
            break
        rows.append({k: json_safe(v) for k, v in row.items()})

    if max_rows is not None and len(rows) > max_rows:
        truncated = True
        rows = rows[:max_rows]

    payload: dict[str, Any] = {"sql": sql, "rows": rows, "count": len(rows)}
    if truncated:
        payload["truncated"] = True
    return payload


def execute_sql(
    engine: Engine,
    sql: str,
    *,
    readonly: bool = False,
    max_rows: int | None = None,
) -> dict[str, Any]:
    """Execute SQL with DBHub-compatible per-statement result formatting."""
    if not isinstance(sql, str) or not sql.strip():
        raise ValueError("sql must be a non-empty string")
    if max_rows is not None and max_rows < 1:
        raise ValueError("max_rows must be positive")
    if readonly:
        enforce_readonly(sql)

    statements = split_statements(sql)
    if not statements:
        raise ValueError("No SQL statements found")

    payloads: list[dict[str, Any]] = []
    # DBHub executes a multi-statement batch in one transaction/session so that
    # all result sets are ordered and the batch is atomic on error.
    with engine.begin() as conn:
        if readonly:
            conn.execute(text("SET TRANSACTION READ ONLY"))
        for statement in statements:
            payloads.append(statement_payload(conn.execute(text(statement)), statement, max_rows))

    return {"statements": payloads}
