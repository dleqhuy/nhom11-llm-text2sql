"""BIRD-style result-set equality: ignores row order and duplicate rows.

Column order and values are preserved. Execution fetches ALL rows, never MCP's
truncated preview. Both queries use one repeatable-read, read-only snapshot.
"""

from time import perf_counter

from .components import parse


def execute(connection, sql):
    parse(sql)
    start = perf_counter()
    with connection.cursor() as cursor:
        cursor.execute(sql)
        rows = cursor.fetchall()
    return rows, perf_counter() - start


def freeze(value):
    if isinstance(value, dict):
        return tuple(sorted((k, freeze(v)) for k, v in value.items()))
    if isinstance(value, (list, tuple)):
        return tuple(freeze(v) for v in value)
    return value


def equivalent(predicted, reference):
    return {freeze(row) for row in predicted} == {freeze(row) for row in reference}


def score(connection, predicted, reference):
    gold, gold_time = execute(connection, reference)
    pred, pred_time = execute(connection, predicted)
    return {
        "score": float(equivalent(pred, gold)),
        "reference_seconds": gold_time,
        "predicted_seconds": pred_time,
    }
