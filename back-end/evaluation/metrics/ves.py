"""VES contribution = EX * sqrt(mean(reference_time / predicted_time)).

Alternate execution order and discard warmup; benchmark is sequential. Client
wall time includes fetching rows. This is a documented PostgreSQL adaptation.
"""

import math
import statistics

from .ex import equivalent, execute


def score(connection, predicted, reference, repetitions=5):
    if repetitions < 1:
        raise ValueError("repetitions must be positive")
    ratios = []
    for iteration in range(repetitions + 1):
        if iteration % 2:
            p, pt = execute(connection, predicted)
            g, gt = execute(connection, reference)
        else:
            g, gt = execute(connection, reference)
            p, pt = execute(connection, predicted)
        if not equivalent(p, g):
            return {"score": 0.0, "unstable_results": True}
        if iteration:
            ratios.append(gt / max(pt, 1e-12))
    return {"score": math.sqrt(statistics.mean(ratios)), "time_ratios": ratios}
