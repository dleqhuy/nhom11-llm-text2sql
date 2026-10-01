import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from scripts.generate_sql import generate, load_questions, make_prompt, save_results


def test_prompt_excludes_reference_sql():
    row = {
        "db_id": "db",
        "question": "How many?",
        "evidence": "Count rows",
        "SQL": "SECRET",
    }
    assert "SECRET" not in make_prompt(row)
    assert json.loads(make_prompt(row))["evidence"] == "Count rows"


def test_load_filters_database_and_limits(tmp_path):
    source = tmp_path / "questions.json"
    source.write_text(
        json.dumps(
            [
                {"db_id": "other", "question": "Other"},
                {"db_id": "db", "question": "One"},
                {"db_id": "db", "question": "Two"},
            ]
        )
    )
    assert [r["question"] for r in load_questions(source, "db", 1)] == ["One"]
    with pytest.raises(ValueError, match="No questions"):
        load_questions(source, "missing")


def test_generation_uses_ephemeral_and_structured_output(tmp_path):
    thread = SimpleNamespace(
        run=AsyncMock(
            return_value=SimpleNamespace(
                status="completed", final_response='{"sql":"SELECT 1"}'
            )
        )
    )
    codex = SimpleNamespace(thread_start=AsyncMock(return_value=thread))
    row = {"question_id": 1, "db_id": "db", "question": "One", "SQL": "reference"}
    result = asyncio.run(generate(codex, row))
    assert codex.thread_start.call_args.kwargs["ephemeral"] is True
    assert "output_schema" in thread.run.call_args.kwargs
    assert result["SQL"] == "reference"
    assert result["generated_sql"] == "SELECT 1"
    output = tmp_path / "output.json"
    save_results(output, [result])
    assert json.loads(output.read_text())[0]["generation_status"] == "completed"


def test_failed_generation_is_recorded():
    codex = SimpleNamespace(
        thread_start=AsyncMock(side_effect=RuntimeError("MCP unavailable"))
    )
    result = asyncio.run(generate(codex, {"question": "One"}))
    assert result["generated_sql"] is None
    assert result["generation_error"] == "MCP unavailable"
