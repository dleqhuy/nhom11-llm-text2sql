from __future__ import annotations

import json
import os

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP
from mcp.types import CallToolResult

from mcp_text2sql.db import make_engine
from mcp_text2sql.execute_sql import execute_sql as run_sql
from mcp_text2sql.search_objects import search_objects as search_db_objects

load_dotenv()

mcp = FastMCP(
    "mcp-text2sql",
    instructions="Use execute_sql for read-only PostgreSQL queries and search_objects to discover database objects.",
    host=os.getenv("MCP_HOST", "127.0.0.1"),
    port=int(os.getenv("MCP_PORT", "7000")),
    streamable_http_path="/mcp",
)
engine = make_engine(os.environ["DATABASE_URL"])
READONLY = os.getenv("READONLY", "true").lower() in {"1", "true", "yes"}
MAX_ROWS = int(os.getenv("MAX_ROWS", "1000"))


def _success(data) -> CallToolResult:
    # DBHub's createToolSuccessResponse(): JSON pretty-printed with indent=2,
    # wrapped in MCP text content with application/json.
    return CallToolResult(content=[
            {
                "type": "text",
                "text": json.dumps({"success": True, "data": data}, indent=2, ensure_ascii=False, default=str),
                "mimeType": "application/json",
            }
        ]
    )


def _failure(message: str, code: str, details=None) -> CallToolResult:
    payload = {"success": False, "error": message, "code": code}
    if details:
        payload["details"] = details
    return CallToolResult(
        content=[
            {
                "type": "text",
                "text": json.dumps(payload, indent=2, ensure_ascii=False, default=str),
                "mimeType": "application/json",
            }
        ],
        isError=True,
    )


@mcp.tool(name="execute_sql")
def execute_sql(sql: str) -> CallToolResult:
    """Execute read-only PostgreSQL SQL and return result sets capped by MAX_ROWS."""
    try:
        data = run_sql(
            engine,
            sql,
            readonly=READONLY,
            max_rows=MAX_ROWS,
        )
        # DBHub always includes the effective source id in execute_sql data.
        data["source_id"] = os.getenv("SOURCE_ID", "default")
        return _success(data)
    except PermissionError as exc:
        return _failure(str(exc), "READONLY_VIOLATION")
    except Exception as exc:
        return _failure(str(exc), "EXECUTION_ERROR")


@mcp.tool(name="search_objects")
def search_objects(
    object_type: str,
    pattern: str = "%",
    schema: str | None = None,
    table: str | None = None,
    detail_level: str = "names",
    limit: int = 100,
) -> CallToolResult:
    """Search PostgreSQL schemas, tables, views, columns, procedures, functions and indexes."""
    try:
        data = search_db_objects(
            engine,
            object_type=object_type,
            pattern=pattern,
            schema=schema,
            table=table,
            detail_level=detail_level,
            limit=limit,
        )
        return _success(data)
    except ValueError as exc:
        message = str(exc)
        if message.startswith("Schema '") and "does not exist" in message:
            return _failure(message, "SCHEMA_NOT_FOUND")
        if message.startswith("The 'table' parameter requires"):
            return _failure(message, "SCHEMA_REQUIRED")
        if message.startswith("The 'table' parameter only applies"):
            return _failure(message, "INVALID_TABLE_FILTER")
        if message.startswith("Unsupported object_type"):
            return _failure(message, "INVALID_OBJECT_TYPE")
        return _failure(message, "SEARCH_ERROR")
    except Exception as exc:
        return _failure(f"Error searching database objects: {exc}", "SEARCH_ERROR")


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
