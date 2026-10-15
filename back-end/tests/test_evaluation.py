import math

import pytest

from evaluation.metrics import cm, em, ex, ves


def test_component_reordering_and_partial_credit():
    assert (
        em.score(
            "SELECT a,b FROM t WHERE x=1 AND y=2", "SELECT b,a FROM t WHERE y=2 AND x=1"
        )
        == 1
    )
    result = cm.score("SELECT a,c FROM t", "SELECT a,b FROM t")
    assert result["components"]["select"]["f1"] == 0.5
    assert em.score("SELECT a FROM t", "SELECT a FROM other") == 0


def test_values_boolean_logic_and_nested_queries_remain_distinct():
    assert em.score("SELECT a FROM t WHERE x=1", "SELECT a FROM t WHERE x=2") == 0
    assert (
        em.score(
            "SELECT a FROM t WHERE x=1 OR y=2", "SELECT a FROM t WHERE x=1 AND y=2"
        )
        == 0
    )
    assert (
        em.score(
            "SELECT a FROM t WHERE a IN (SELECT b FROM u)",
            "SELECT a FROM t WHERE a IN (SELECT c FROM u)",
        )
        == 0
    )
    with pytest.raises(ValueError):
        em.score("SELECT 1; DELETE FROM t", "SELECT 1")


def test_execution_set_policy():
    assert ex.equivalent([(1,), (2,), (1,)], [(2,), (1,)])
    assert not ex.equivalent([(1, 2)], [(2, 1)])
    assert ex.equivalent([(None, {"x": [1]})], [(None, {"x": [1]})])
    assert not ex.equivalent([(1,)], [])


def test_ves_uses_square_root_and_rechecks_correctness(monkeypatch):
    monkeypatch.setattr(
        ves, "execute", lambda conn, sql: ([(1,)], 4.0 if sql == "gold" else 1.0)
    )
    assert ves.score(None, "pred", "gold", 3)["score"] == math.sqrt(4)
    monkeypatch.setattr(ves, "execute", lambda conn, sql: ([(sql,)], 1.0))
    assert ves.score(None, "pred", "gold", 3)["score"] == 0


def test_evaluation_rejects_incomplete_predictions(tmp_path):
    import json
    from types import SimpleNamespace

    from evaluation.run import evaluate

    (tmp_path / "predictions.json").write_text(json.dumps([]))
    with pytest.raises(ValueError, match="incomplete"):
        evaluate(SimpleNamespace(output=tmp_path), [{"question_id": 1}])


def test_reference_dataset_is_fully_parseable():
    import json

    from evaluation.metrics.components import components
    from evaluation.run import ROOT

    path = ROOT / "mini_dev_pg-00000-of-00001.json"
    if not path.exists():
        pytest.skip("Local Mini-Dev dataset is not installed")
    rows = json.loads(path.read_text())
    for row in rows:
        assert components(row["SQL"])["select"], row["question_id"]
