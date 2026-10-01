from __future__ import annotations

import re
from typing import Any

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

OBJECT_TYPES = {"schema", "table", "view", "column", "procedure", "function", "index"}
DETAIL_LEVELS = {"names", "summary", "full"}
SYSTEM_SCHEMAS = {"pg_catalog", "information_schema", "pg_toast"}


def like_regex(pattern: str) -> re.Pattern[str]:
    parts: list[str] = []
    for c in pattern:
        parts.append(".*" if c == "%" else "." if c == "_" else re.escape(c))
    return re.compile("^" + "".join(parts) + "$", re.I)


def default_schemas(engine: Engine) -> list[str]:
    names = inspect(engine).get_schema_names()
    return [s for s in names if s not in SYSTEM_SCHEMAS and not s.startswith("pg_toast")]


def columns(engine: Engine, schema: str, table: str) -> list[dict[str, Any]]:
    return [
        {
            "name": c["name"],
            "type": str(c["type"]),
            "nullable": bool(c.get("nullable", True)),
            "default": c.get("default"),
            **({"description": c["comment"]} if c.get("comment") else {}),
        }
        for c in inspect(engine).get_columns(table, schema=schema)
    ]


def indexes(engine: Engine, schema: str, table: str) -> list[dict[str, Any]]:
    insp = inspect(engine)
    raw = insp.get_indexes(table, schema=schema)
    # SQLAlchemy's PostgreSQL inspector exposes unique indexes but not always
    # the primary flag. Query pg_index so primary is 1:1 with DBHub.
    with engine.connect() as conn:
        rows = conn.execute(
            text("""
                SELECT i.relname AS name, ix.indisprimary AS primary
                FROM pg_class t
                JOIN pg_namespace n ON n.oid=t.relnamespace
                JOIN pg_index ix ON ix.indrelid=t.oid
                JOIN pg_class i ON i.oid=ix.indexrelid
                WHERE n.nspname=:schema AND t.relname=:table
            """), {"schema": schema, "table": table}
        ).mappings().all()
    primary = {r["name"]: bool(r["primary"]) for r in rows}
    return [
        {
            "name": i["name"],
            "columns": i.get("column_names") or [],
            "unique": bool(i.get("unique")),
            "primary": primary.get(i["name"], False),
        }
        for i in raw
    ]


def routine_rows(conn, schema: str | None, kind: str) -> list[dict[str, Any]]:
    params = {"kind": kind}
    where = "p.prokind=:kind"
    if schema is not None:
        where += " AND n.nspname=:schema"
        params["schema"] = schema
    sql = f"""
    SELECT n.nspname AS schema,p.proname AS name,
           CASE p.prokind WHEN 'p' THEN 'procedure' ELSE 'function' END AS type,
           l.lanname AS language,pg_get_function_result(p.oid) AS return_type,
           pg_get_function_arguments(p.oid) AS parameter_list,
           pg_get_functiondef(p.oid) AS definition
    FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
    JOIN pg_language l ON l.oid=p.prolang
    WHERE {where}
      AND n.nspname NOT IN ('pg_catalog','information_schema')
    ORDER BY n.nspname,p.proname
    """
    return [dict(r._mapping) for r in conn.execute(text(sql), params)]


def search_objects(
    engine: Engine,
    *,
    object_type: str,
    pattern: str = "%",
    schema: str | None = None,
    table: str | None = None,
    detail_level: str = "names",
    limit: int = 100,
) -> dict[str, Any]:
    if object_type not in OBJECT_TYPES:
        raise ValueError(f"Unsupported object_type: {object_type}")
    if detail_level not in DETAIL_LEVELS:
        raise ValueError(f"Unsupported detail_level: {detail_level}")
    if not 1 <= limit <= 1000:
        raise ValueError("limit must be between 1 and 1000")

    insp = inspect(engine)
    all_schemas = default_schemas(engine)
    if table is not None and (schema is None or object_type not in {"column", "index"}):
        raise ValueError("The 'table' parameter only applies to object_type 'column' or 'index', not '%s'" % object_type)
    if schema is not None and schema not in all_schemas:
        raise ValueError(f"Schema '{schema}' does not exist. Available schemas: {', '.join(all_schemas)}")

    scopes = [schema] if schema else all_schemas
    rgx = like_regex(pattern)
    result: list[dict[str, Any]] = []

    if object_type == "schema":
        for s in scopes:
            if rgx.search(s):
                if detail_level == "names":
                    result.append({"name": s})
                else:
                    try:
                        result.append({"name": s, "table_count": len(insp.get_table_names(schema=s))})
                    except Exception:
                        result.append({"name": s, "table_count": 0})
                if len(result) >= limit:
                    break

    elif object_type in {"table", "view"}:
        getter = insp.get_table_names if object_type == "table" else insp.get_view_names
        for s in scopes:
            if len(result) >= limit:
                break
            try:
                names = getter(schema=s)
            except Exception:
                continue
            for name in names:
                if not rgx.search(name):
                    continue
                if detail_level == "names":
                    result.append({"name": name, "schema": s})
                elif detail_level == "summary":
                    try:
                        cs = columns(engine, s, name)
                        item: dict[str, Any] = {"name": name, "schema": s, "column_count": len(cs)}
                        if object_type == "table":
                            with engine.connect() as conn:
                                item["row_count"] = conn.execute(text("""
                                    SELECT CASE WHEN c.reltuples >= 0 THEN c.reltuples::bigint ELSE NULL END
                                    FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
                                    WHERE n.nspname=:schema AND c.relname=:name
                                """), {"schema": s, "name": name}).scalar()
                                comment = conn.execute(text("SELECT obj_description(to_regclass(:q)::oid,'pg_class')"), {"q": f'{s}.{name}'}).scalar()
                            if comment:
                                item["comment"] = comment
                        result.append(item)
                    except Exception:
                        result.append({
                            "name": name, "schema": s,
                            "column_count": None,
                            **({"row_count": None} if object_type == "table" else {}),
                        })
                else:
                    try:
                        cs = columns(engine, s, name)
                        comment = None
                        with engine.connect() as conn:
                            comment = conn.execute(text("SELECT obj_description(to_regclass(:q)::oid,'pg_class')"), {"q": f'{s}.{name}'}).scalar()
                        item = {"name": name, "schema": s, "column_count": len(cs)}
                        if object_type == "table":
                            with engine.connect() as conn:
                                item["row_count"] = conn.execute(text("""
                                    SELECT CASE WHEN c.reltuples >= 0 THEN c.reltuples::bigint ELSE NULL END
                                    FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
                                    WHERE n.nspname=:schema AND c.relname=:name
                                """), {"schema": s, "name": name}).scalar()
                        if comment:
                            item["comment"] = comment
                        item["columns"] = cs
                        item["indexes"] = indexes(engine, s, name) if object_type == "table" else []
                        result.append(item)
                    except Exception as exc:
                        result.append({"name": name, "schema": s, "error": f"Unable to fetch full details: {exc}"})
                if len(result) >= limit:
                    break

    elif object_type == "column":
        for s in scopes:
            if len(result) >= limit:
                break
            try:
                objs = [table] if table else insp.get_table_names(schema=s) + insp.get_view_names(schema=s)
            except Exception:
                continue
            for t in objs:
                if len(result) >= limit:
                    break
                try:
                    cs = columns(engine, s, t)
                except Exception:
                    continue
                for c in cs:
                    if rgx.search(c["name"]):
                        item = {"name": c["name"], "table": t, "schema": s}
                        if detail_level != "names":
                            item.update({k: c[k] for k in ("type", "nullable", "default")})
                            if c.get("description"):
                                item["description"] = c["description"]
                        result.append(item)
                        if len(result) >= limit:
                            break

    elif object_type == "index":
        for s in scopes:
            if len(result) >= limit:
                break
            try:
                objs = [table] if table else insp.get_table_names(schema=s)
            except Exception:
                continue
            for t in objs:
                if len(result) >= limit:
                    break
                try:
                    idxs = indexes(engine, s, t)
                except Exception:
                    continue
                for idx in idxs:
                    if rgx.search(idx["name"]):
                        item = {"name": idx["name"], "table": t, "schema": s}
                        if detail_level != "names":
                            item.update({"columns": idx["columns"], "unique": idx["unique"], "primary": idx["primary"]})
                        result.append(item)
                        if len(result) >= limit:
                            break

    else:
        kind = "p" if object_type == "procedure" else "f"
        with engine.connect() as conn:
            rows = routine_rows(conn, schema, kind)
        for r in rows:
            if rgx.search(r["name"]):
                item = {"name": r["name"], "schema": r["schema"]}
                if detail_level != "names":
                    item.update({"type": r["type"], "language": r["language"], "return_type": r["return_type"]})
                    if detail_level == "full":
                        item.update({"parameters": r["parameter_list"], "definition": r["definition"]})
                result.append(item)
                if len(result) >= limit:
                    break

    return {
        "object_type": object_type,
        "pattern": pattern,
        **({"schema": schema} if schema is not None else {}),
        **({"table": table} if table is not None else {}),
        "detail_level": detail_level,
        "count": len(result),
        "results": result,
        "truncated": len(result) == limit,
    }
