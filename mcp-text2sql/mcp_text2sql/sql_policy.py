from __future__ import annotations

import re

import sqlparse

# DBHub's PostgreSQL allowed-keyword list.
READ_ONLY = re.compile(r"^(?:SELECT|WITH|EXPLAIN|SHOW)\b", re.I | re.S)
DML = re.compile(r"^(?:INSERT|UPDATE|DELETE|MERGE)\b", re.I | re.S)
DDL = re.compile(r"^(?:CREATE|ALTER|DROP|TRUNCATE|RENAME)\b", re.I | re.S)
ADMIN = re.compile(r"^(?:GRANT|REVOKE|VACUUM|REINDEX|CLUSTER|DISCARD|CHECKPOINT|CALL|DO|COPY)\b", re.I | re.S)
ESCAPE = re.compile(
    r"\b(?:pg_read_file|pg_read_binary_file|pg_ls_dir)\s*\(",
    re.I,
)
MUTATING = re.compile(
    r"\b(?:insert|update|delete|drop|alter|create|truncate|merge|grant|revoke|rename)\b",
    re.I,
)
SELECT_INTO = re.compile(r"\bselect\b[\s\S]+\binto\b", re.I)


def split_statements(sql: str) -> list[str]:
    return [s.strip() for s in sqlparse.split(sql) if s.strip()]


def strip_comments(statement: str) -> str:
    return sqlparse.format(statement, strip_comments=True).strip()


def classify(statement: str) -> str:
    """Approximate DBHub's dialect-aware classifier for PostgreSQL."""
    s = strip_comments(statement)
    if not s:
        return "read"
    # DBHub strips string literals before checking escape-hatch functions and
    # mutating keywords. sqlparse's token stream gives us a conservative
    # approximation without treating text inside quoted literals as SQL.
    normalized = _strip_string_literals(s)
    if ESCAPE.search(normalized):
        return "admin"
    if READ_ONLY.match(normalized):
        first = normalized.split(None, 1)[0].lower()
        if first == "with" and MUTATING.search(normalized):
            return "admin"
        if first in {"select", "with"} and SELECT_INTO.search(normalized):
            return "admin"
        # EXPLAIN ANALYZE executes the underlying statement. Re-classify the
        # statement following EXPLAIN so DML/DDL cannot pass the gate.
        if first == "explain" and re.match(r"^explain\s+(?:analyze|\([^)]*\banalyze\b)", normalized, re.I):
            body = re.sub(r"^explain\s+(?:analyze|\([^)]*\)\s*)", "", normalized, flags=re.I).strip()
            if body and classify(body) != "read":
                return "admin"
        return "read"
    if DML.match(normalized):
        return "dml"
    if DDL.match(normalized):
        return "ddl"
    if ADMIN.match(normalized):
        return "admin"
    return "unknown"


def _strip_string_literals(sql: str) -> str:
    out: list[str] = []
    for token in sqlparse.parse(sql)[0].flatten():
        if token.ttype in sqlparse.tokens.Literal.String:
            out.append(" ")
        else:
            out.append(str(token))
    return "".join(out)


def classify_sql(sql: str) -> str:
    severity = {"read": 0, "dml": 1, "ddl": 2, "admin": 3, "unknown": 4}
    classes = [classify(s) for s in split_statements(sql)] or ["unknown"]
    return max(classes, key=severity.__getitem__)


def enforce_readonly(sql: str) -> None:
    cls = classify_sql(sql)
    if cls != "read":
        raise PermissionError(
            "Read-only mode is enabled. Only the following SQL operations are allowed: "
            "select, with, explain, show"
        )
