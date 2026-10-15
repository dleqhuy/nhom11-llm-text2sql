"""CLI: preflight -> generate -> evaluate. Run from back-end with python -m evaluation.run."""

import argparse
import asyncio
import csv
import hashlib
import json
import os
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import psycopg
from dotenv import dotenv_values
from openai_codex import AsyncCodex, CodexConfig

from scripts.generate_sql import generate, save_results

from .metrics import cm, em, ex, ves

ROOT = Path(__file__).resolve().parents[2]


def connect(timeout):
    # This installation combines all 11 Mini-Dev domains in BIRD.public.
    url = os.environ.get("EVALUATION_DATABASE_URL") or dotenv_values(
        ROOT / "mcp-text2sql/.env"
    ).get("DATABASE_URL")
    if not url:
        raise ValueError("Set EVALUATION_DATABASE_URL")
    return psycopg.connect(
        url.replace("postgresql+psycopg://", "postgresql://"),
        connect_timeout=10,
        options=f"-c default_transaction_read_only=on -c statement_timeout={timeout * 1000}",
    )


def dataset(path):
    rows = json.loads(path.read_text())
    ids = [r["question_id"] for r in rows]
    if len(ids) != len(set(ids)) or not rows:
        raise ValueError("Dataset is empty or has duplicate question_id")
    return rows


def preflight(args, rows):
    results = []
    with connect(args.timeout) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT current_database(), current_schema(), version()")
            db, schema, version = cur.fetchone()
        conn.rollback()
        for row in rows:
            item = {"question_id": row["question_id"], "db_id": row["db_id"]}
            try:
                with conn.transaction():
                    with conn.cursor() as cur:
                        cur.execute("EXPLAIN " + row["SQL"])
                        cur.fetchall()
                item["status"] = "ok"
            except Exception as error:
                item.update(status="failed", error=str(error))
            results.append(item)
    save_results(
        args.output / "preflight.json",
        {
            "database": db,
            "schema": schema,
            "postgresql": version,
            "rows": results,
            "failed": sum(r["status"] != "ok" for r in results),
        },
    )
    print(
        f"Preflight: {len(results)} questions; {sum(r['status'] != 'ok' for r in results)} errors",
        flush=True,
    )
    return sum(r["status"] != "ok" for r in results)


async def predict(args, rows):
    path = args.output / "predictions.json"
    fingerprint = hashlib.sha256(args.input.read_bytes()).hexdigest()
    metadata = {
        "model": args.model,
        "reasoning_effort": "low",
        "dataset": "birdsql/bird_mini_dev PostgreSQL",
        "dataset_sha256": fingerprint,
        "questions": len(rows),
        "database_counts": dict(Counter(r["db_id"] for r in rows)),
        "deployment": "11 domains combined in BIRD.public",
        "mcp_url": args.mcp_url,
        "protocol": "postgres-ast-v1",
        "generation_concurrency": args.concurrency,
    }
    manifest = args.output / "manifest.json"
    if manifest.exists():
        old = json.loads(manifest.read_text())
        for key in metadata:
            if old.get(key) != metadata[key]:
                raise ValueError(
                    f"Cannot resume with changed {key}; choose another output folder"
                )
    else:
        save_results(
            manifest, {**metadata, "started_at": datetime.now(timezone.utc).isoformat()}
        )
    results = (
        {r["question_id"]: r for r in json.loads(path.read_text())}
        if path.exists()
        else {}
    )
    config = CodexConfig(
        config_overrides=(
            f"mcp_servers.text2sql.url={json.dumps(args.mcp_url)}",
            "mcp_servers.text2sql.enabled=true",
            "mcp_servers.text2sql.required=true",
            'mcp_servers.text2sql.enabled_tools=["search_objects", "execute_sql"]',
            'model_reasoning_effort="low"',
        )
    )
    semaphore = asyncio.Semaphore(args.concurrency)
    async with AsyncCodex(config=config) as codex:

        async def one(row):
            if (
                results.get(row["question_id"], {}).get("generation_status")
                == "completed"
            ):
                return
            async with semaphore:
                try:
                    result = await asyncio.wait_for(
                        generate(codex, row, args.model), args.generation_timeout
                    )
                except TimeoutError:
                    result = {
                        **row,
                        "generated_sql": None,
                        "generation_status": "failed",
                        "generation_error": "Generation timeout",
                    }
                result["model"] = args.model
                results[row["question_id"]] = result
                save_results(
                    path,
                    [
                        results[r["question_id"]]
                        for r in rows
                        if r["question_id"] in results
                    ],
                )
                print(
                    f"[{len(results)}/{len(rows)}] {row['question_id']}: {result['generation_status']}",
                    flush=True,
                )

        await asyncio.gather(*(one(r) for r in rows))
    return int(any(r["generation_status"] != "completed" for r in results.values()))


def evaluate(args, rows):
    path = args.output / "predictions.json"
    predictions = {r["question_id"]: r for r in json.loads(path.read_text())}
    if set(predictions) - {r["question_id"] for r in rows}:
        raise ValueError("Predictions contain unknown question IDs")
    if len(predictions) != len(rows):
        raise ValueError(
            "Generation is incomplete; wait for all dataset rows before evaluation"
        )
    for row in rows:
        pred = predictions[row["question_id"]]
        if any(pred.get(key) != row.get(key) for key in ("db_id", "question", "SQL")):
            raise ValueError(f"Prediction metadata mismatch: {row['question_id']}")
    manifest = json.loads((args.output / "manifest.json").read_text())
    if (
        manifest["dataset_sha256"]
        != hashlib.sha256(args.input.read_bytes()).hexdigest()
    ):
        raise ValueError("Dataset hash differs from generation")
    outputs = {name: [] for name in ("cm", "em", "ex", "ves")}
    with connect(args.timeout) as conn:
        for index, row in enumerate(rows, 1):
            pred = predictions.get(row["question_id"], {})
            sql = pred.get("generated_sql")
            base = {k: row[k] for k in ("question_id", "db_id", "difficulty")}
            scores = {
                name: {**base, "score": 0.0, "status": "missing_prediction"}
                for name in outputs
            }
            if sql:
                for name, metric in (("cm", cm), ("em", em)):
                    try:
                        value = metric.score(sql, row["SQL"])
                        scores[name].update(
                            value if isinstance(value, dict) else {"score": value},
                            status="ok",
                        )
                    except Exception as error:
                        scores[name].update(status="parse_error", error=str(error))
                try:
                    with conn.transaction():
                        conn.execute(
                            "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"
                        )
                        # Validate gold separately: invalid gold is an infrastructure error, not a model failure.
                        try:
                            gold, gold_time = ex.execute(conn, row["SQL"])
                        except Exception as error:
                            for name in ("ex", "ves"):
                                scores[name].update(
                                    score=None,
                                    status="reference_error",
                                    error=str(error),
                                )
                            raise
                        pred_rows, pred_time = ex.execute(conn, sql)
                        correct = ex.equivalent(pred_rows, gold)
                        scores["ex"].update(
                            score=float(correct),
                            status="ok",
                            reference_seconds=gold_time,
                            predicted_seconds=pred_time,
                        )
                        scores["ves"].update(status="incorrect_result")
                        if correct:
                            scores["ves"].update(
                                ves.score(conn, sql, row["SQL"], args.repetitions),
                                status="ok",
                            )
                except Exception as error:
                    for name in ("ex", "ves"):
                        if scores[name]["status"] == "missing_prediction":
                            scores[name].update(
                                status="execution_error", error=str(error)
                            )
                        elif (
                            name == "ves"
                            and scores["ex"]["score"] == 1
                            and scores[name]["status"] != "reference_error"
                        ):
                            scores[name].update(
                                score=None, status="timing_error", error=str(error)
                            )
            for name in outputs:
                outputs[name].append(scores[name])
                save_results(args.output / f"{name}.json", outputs[name])
            print(
                f"Evaluate [{index}/{len(rows)}] EX={scores['ex']['score']}", flush=True
            )

    def summarize(items):
        invalid = sum(x["score"] is None for x in items)
        return {
            "percent": None
            if invalid
            else 100 * sum(x["score"] for x in items) / len(items),
            "count": len(items),
            "unscorable": invalid,
            "statuses": dict(Counter(x["status"] for x in items)),
        }

    summary = {
        "manifest": manifest,
        "protocol": "postgres-ast-v1 (CM/EM are not official Spider scores)",
        "ves_repetitions": args.repetitions,
        "timeout_seconds": args.timeout,
        "prediction_count": len(predictions),
        "expected_count": len(rows),
        "metrics": {k: summarize(v) for k, v in outputs.items()},
    }
    for field in ("db_id", "difficulty"):
        summary[f"by_{field}"] = {
            group: {
                k: summarize([r for r in v if r[field] == group])
                for k, v in outputs.items()
            }
            for group in sorted({r[field] for r in rows})
        }
    save_results(args.output / "summary.json", summary)
    with (args.output / "predictions.csv").open(
        "w", encoding="utf-8-sig", newline=""
    ) as handle:
        columns = [
            "question_id",
            "db_id",
            "difficulty",
            "model",
            "question",
            "SQL",
            "generated_sql",
            "generation_status",
            "generation_error",
        ]
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(predictions[row["question_id"]] for row in rows)
    lines = [
        "# Kết quả BIRD Mini-Dev PostgreSQL",
        "",
        f"Model: `{manifest['model']}`; reasoning: low; dataset: {len(rows)} câu.",
        "",
        "CM/EM: PostgreSQL AST adaptation, không phải điểm Spider chính thức.",
        "",
        "| Độ đo | Điểm (%) | Không chấm được |",
        "|---|---:|---:|",
    ]
    for name, metric in summary["metrics"].items():
        value = "N/A" if metric["percent"] is None else f"{metric['percent']:.2f}"
        lines.append(f"| {name.upper()} | {value} | {metric['unscorable']} |")
    for field in ("db_id", "difficulty"):
        lines.extend(
            [
                "",
                f"## Theo {field}",
                "",
                "| Nhóm | Số câu | CM | EM | EX | VES |",
                "|---|---:|---:|---:|---:|---:|",
            ]
        )
        for group, values in summary[f"by_{field}"].items():
            points = [
                "N/A"
                if values[name]["percent"] is None
                else f"{values[name]['percent']:.2f}"
                for name in outputs
            ]
            lines.append(
                f"| {group} | {values['cm']['count']} | " + " | ".join(points) + " |"
            )
    (args.output / "report.md").write_text("\n".join(lines) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=["all", "preflight", "generate", "evaluate"])
    parser.add_argument(
        "--input", type=Path, default=ROOT / "mini_dev_pg-00000-of-00001.json"
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model", default="gpt-6-astra")
    parser.add_argument("--mcp-url", default="http://127.0.0.1:7000/mcp")
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--generation-timeout", type=int, default=600)
    parser.add_argument("--repetitions", type=int, default=5)
    args = parser.parse_args()
    if (
        min(args.timeout, args.concurrency, args.generation_timeout, args.repetitions)
        < 1
    ):
        parser.error("Timeouts, concurrency and repetitions must be positive")
    args.output.mkdir(parents=True, exist_ok=True)
    rows = dataset(args.input)
    if args.stage == "all":
        if preflight(args, rows):
            raise SystemExit("Reference SQL preflight failed; see preflight.json")
        generation_exit = asyncio.run(predict(args, rows))
        evaluate(args, rows)
        raise SystemExit(generation_exit)
    if args.stage == "generate":
        raise SystemExit(asyncio.run(predict(args, rows)))
    {"preflight": preflight, "evaluate": evaluate}[args.stage](args, rows)


if __name__ == "__main__":
    main()
