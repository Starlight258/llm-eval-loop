from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PromptVersionRow:
    prompt_version: str
    label: str
    prompt_text: str
    applied_rules: str
    good_example: str
    bad_example: str
    created_at: str


@dataclass(frozen=True)
class EvaluationRunRow:
    run_id: str
    dataset_id: str
    prompt_version: str
    report_text: str
    groundedness_score: float
    appropriateness_score: float
    calibration_score: float
    consistency_score: float
    readability_score: float
    overall_score: float
    failed_sentences: list[str]
    judge_feedback: str
    created_at: str

