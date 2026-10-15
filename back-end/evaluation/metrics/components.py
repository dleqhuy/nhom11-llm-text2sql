"""PostgreSQL AST components; explicitly NOT the official Spider evaluator.

Preserves literal values, DISTINCT, aliases and nested query structure. Component
members are unordered, but the internals of an expression remain ordered.
"""

from collections import Counter

import sqlglot
from sqlglot import exp


def parse(sql):
    statements = sqlglot.parse(sql, read="postgres")
    if len(statements) != 1 or not isinstance(statements[0], exp.Query):
        raise ValueError("Expected exactly one SELECT/query")
    tree = statements[0]
    for ident in tree.find_all(exp.Identifier):
        if not ident.args.get("quoted"):
            ident.set("this", ident.this.lower())
    return tree


def components(sql):
    tree = parse(sql)
    groups = {
        k: Counter()
        for k in ("select", "where", "group_by", "order_by", "keywords", "structure")
    }

    def render(node):
        return node.sql(dialect="postgres", pretty=False, comments=False)

    # Each SELECT scope is kept distinct to avoid matching a nested clause to its parent.
    for index, select in enumerate(tree.find_all(exp.Select)):
        prefix = f"scope{index}:"
        for node in select.expressions:
            groups["select"][prefix + render(node)] += 1
        for arg, name in [
            ("where", "where"),
            ("group", "group_by"),
            ("order", "order_by"),
        ]:
            clause = select.args.get(arg)
            if clause is None:
                continue
            nodes = (
                list(clause.this.flatten())
                if arg == "where" and isinstance(clause.this, exp.And)
                else ([clause.this] if arg == "where" else clause.expressions)
            )
            for node in nodes:
                groups[name][prefix + render(node)] += 1
        for key, value in select.args.items():
            if value and key not in {"expressions", "where", "group", "order"}:
                values = value if isinstance(value, list) else [value]
                for v in values:
                    groups["structure"][
                        prefix
                        + key
                        + ":"
                        + (render(v) if isinstance(v, exp.Expression) else str(v))
                    ] += 1
        for key in ("where", "group", "order", "having", "limit", "distinct"):
            if select.args.get(key):
                groups["keywords"][prefix + key] += 1
    if not isinstance(tree, exp.Select):
        groups["structure"]["query:" + render(tree)] += 1
    return groups
