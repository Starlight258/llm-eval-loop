from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from core.schemas import EvaluationResult, EvaluationRunRecord


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class EvaluationStore:
    def __init__(self, database_path: str | Path):
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.database_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _initialize(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS prompt_versions (
                    prompt_version TEXT PRIMARY KEY,
                    label TEXT NOT NULL,
                    prompt_text TEXT NOT NULL,
                    applied_rules TEXT NOT NULL,
                    good_example TEXT NOT NULL,
                    bad_example TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS evaluation_runs (
                    run_id TEXT PRIMARY KEY,
                    dataset_id TEXT NOT NULL,
                    prompt_version TEXT NOT NULL,
                    report_text TEXT NOT NULL,
                    groundedness_score REAL NOT NULL,
                    appropriateness_score REAL NOT NULL,
                    calibration_score REAL NOT NULL,
                    consistency_score REAL NOT NULL,
                    readability_score REAL NOT NULL,
                    overall_score REAL NOT NULL,
                    failed_sentences TEXT NOT NULL,
                    judge_feedback TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(prompt_version) REFERENCES prompt_versions(prompt_version)
                )
                """
            )
            conn.commit()

    def save_prompt_version(
        self,
        *,
        prompt_version: str,
        label: str,
        prompt_text: str,
        applied_rules: str,
        good_example: str,
        bad_example: str,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO prompt_versions (
                    prompt_version, label, prompt_text, applied_rules, good_example, bad_example, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    prompt_version,
                    label,
                    prompt_text,
                    applied_rules,
                    good_example,
                    bad_example,
                    _utc_now(),
                ),
            )
            conn.commit()

    def save_evaluation_run(
        self,
        *,
        dataset_id: str,
        prompt_version: str,
        report_text: str,
        evaluation: EvaluationResult,
    ) -> EvaluationRunRecord:
        run_id = str(uuid4())
        created_at = _utc_now()
        record = EvaluationRunRecord(
            run_id=run_id,
            dataset_id=dataset_id,
            prompt_version=prompt_version,
            report_text=report_text,
            groundedness_score=evaluation.scores.groundedness_score,
            appropriateness_score=evaluation.scores.appropriateness_score,
            calibration_score=evaluation.scores.calibration_score,
            consistency_score=evaluation.scores.consistency_score,
            readability_score=evaluation.scores.readability_score,
            overall_score=evaluation.overall_score,
            failed_sentences=evaluation.failed_sentences,
            judge_feedback=evaluation.judge_feedback,
            created_at=created_at,
        )
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO evaluation_runs (
                    run_id, dataset_id, prompt_version, report_text,
                    groundedness_score, appropriateness_score, calibration_score,
                    consistency_score, readability_score, overall_score,
                    failed_sentences, judge_feedback, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.run_id,
                    record.dataset_id,
                    record.prompt_version,
                    record.report_text,
                    record.groundedness_score,
                    record.appropriateness_score,
                    record.calibration_score,
                    record.consistency_score,
                    record.readability_score,
                    record.overall_score,
                    json.dumps(record.failed_sentences),
                    record.judge_feedback,
                    record.created_at,
                ),
            )
            conn.commit()
        return record

    def list_runs(self) -> list[EvaluationRunRecord]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM evaluation_runs ORDER BY created_at ASC").fetchall()
        return [
            EvaluationRunRecord(
                run_id=row["run_id"],
                dataset_id=row["dataset_id"],
                prompt_version=row["prompt_version"],
                report_text=row["report_text"],
                groundedness_score=row["groundedness_score"],
                appropriateness_score=row["appropriateness_score"],
                calibration_score=row["calibration_score"],
                consistency_score=row["consistency_score"],
                readability_score=row["readability_score"],
                overall_score=row["overall_score"],
                failed_sentences=json.loads(row["failed_sentences"]),
                judge_feedback=row["judge_feedback"],
                created_at=row["created_at"],
            )
            for row in rows
        ]

    def list_prompt_versions(self) -> list[dict[str, str]]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM prompt_versions ORDER BY created_at ASC").fetchall()
        return [dict(row) for row in rows]

