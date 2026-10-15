"""Component precision/recall/F1, macro averaged over nonempty components."""

from .components import components


def score(predicted, reference):
    pred, gold = components(predicted), components(reference)
    details = {}
    for name in gold:
        p, g = sum(pred[name].values()), sum(gold[name].values())
        matched = sum((pred[name] & gold[name]).values())
        if not (p or g):
            continue
        precision = matched / p if p else 0.0
        recall = matched / g if g else 0.0
        details[name] = {
            "precision": precision,
            "recall": recall,
            "f1": 2 * matched / (p + g),
        }
    return {
        "score": sum(x["f1"] for x in details.values()) / len(details),
        "components": details,
    }
