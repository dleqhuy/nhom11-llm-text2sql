import json
from collections import Counter

import pytest

from experiments.dataset import prepare_dataset, split_source, validate_source


def source_rows():
    rows = []
    question_id = 0
    for difficulty, count in (("simple", 150), ("moderate", 250), ("challenging", 100)):
        for index in range(count):
            question_id += 1
            rows.append(
                {
                    "question_id": question_id,
                    "db_id": f"db_{index % 11}",
                    "question": f"Question {question_id}",
                    "evidence": "",
                    "SQL": f"SELECT {question_id}",
                    "difficulty": difficulty,
                }
            )
    return rows


def test_split_is_reproducible_stratified_and_disjoint():
    rows = source_rows()
    test, examples = split_source(rows, seed=11)
    repeated, _ = split_source(list(reversed(rows)), seed=11)

    assert [row["question_id"] for row in test] == [
        row["question_id"] for row in repeated
    ]
    assert Counter(row["difficulty"] for row in test) == {
        "simple": 36,
        "moderate": 60,
        "challenging": 24,
    }
    assert len(test) == 120 and len(examples) == 380
    assert len({row["db_id"] for row in test}) == 11
    assert {row["question_id"] for row in test}.isdisjoint(
        row["question_id"] for row in examples
    )


def test_output_separates_test_questions_from_gold_and_records_provenance(tmp_path):
    source = tmp_path / "mini_dev_sqlite.json"
    source.write_text(json.dumps(source_rows()), encoding="utf-8")
    output_dir = tmp_path / "prepared"
    manifest = prepare_dataset(source, output_dir, seed=11, source_version="v1-500")

    test = json.loads((output_dir / "test_en.json").read_text(encoding="utf-8"))
    gold = json.loads((output_dir / "gold_120.json").read_text(encoding="utf-8"))
    examples = json.loads(
        (output_dir / "examples_380.json").read_text(encoding="utf-8")
    )
    assert len(test) == len(gold) == 120
    assert len(examples) == 380
    assert all("SQL" not in row for row in test)
    assert all("SQL" in row for row in gold + examples)
    assert [row["question_id"] for row in test] == [row["question_id"] for row in gold]
    assert manifest["source_version"] == "v1-500"
    assert len(manifest["source_sha256"]) == 64


def test_rejects_wrong_release_duplicate_ids_and_invalid_difficulty():
    rows = source_rows()
    with pytest.raises(ValueError, match="500 questions"):
        validate_source(rows[:-1])
    rows[1]["question_id"] = rows[0]["question_id"]
    with pytest.raises(ValueError, match="Duplicate"):
        validate_source(rows)
    rows = source_rows()
    rows[0]["difficulty"] = "unknown"
    with pytest.raises(ValueError, match="difficulty"):
        validate_source(rows)


def test_does_not_overwrite_prepared_data(tmp_path):
    source = tmp_path / "mini_dev_sqlite.json"
    source.write_text(json.dumps(source_rows()), encoding="utf-8")
    output_dir = tmp_path / "prepared"
    prepare_dataset(source, output_dir, seed=11, source_version="v1-500")
    with pytest.raises(FileExistsError, match="Output already exists"):
        prepare_dataset(source, output_dir, seed=12, source_version="v1-500")
