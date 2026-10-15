"""Exact component match using the project's PostgreSQL AST protocol."""

from .components import components


def score(predicted, reference):
    return float(components(predicted) == components(reference))
