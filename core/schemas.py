from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_score(value: float, name: str) -> float:
    if not 1.0 <= float(value) <= 5.0:
        raise ValueError(f"{name} must be between 1 and 5")
    return float(value)


@dataclass(frozen=True)
class MockMetricData:
    domain: str
    metric_name: str
    current: float
    previous: float
    dod: float
    wow: float
    avg_4w: float
    trend_7d: list[float]
    breakdowns: dict[str, dict[str, float]] = field(default_factory=dict)
    description: str = ""
    unit: str = ""

    def __post_init__(self) -> None:
        if not self.metric_name:
            raise ValueError("metric_name is required")
        if not self.domain:
            raise ValueError("domain is required")
        if len(self.trend_7d) < 2:
            raise ValueError("trend_7d needs at least two points")


@dataclass(frozen=True)
class PromptSpec:
    label: str
    instructions: str
    tone: str = "balanced"
    caution_level: str = "balanced"
    max_bullets: int = 4
    include_breakdowns: bool = True
    good_example: str = ""
    bad_example: str = ""
    notes: str = ""

    def __post_init__(self) -> None:
        if not self.label:
            raise ValueError("label is required")
        if self.max_bullets < 1:
            raise ValueError("max_bullets must be positive")


@dataclass(frozen=True)
class PromptDocument:
    label: str
    prompt_version: str
    spec: PromptSpec
    raw_text: str
    source_path: str = ""


@dataclass(frozen=True)
class EvaluationScores:
    groundedness_score: float
    appropriateness_score: float
    calibration_score: float
    consistency_score: float
    readability_score: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "groundedness_score", _ensure_score(self.groundedness_score, "groundedness_score"))
        object.__setattr__(self, "appropriateness_score", _ensure_score(self.appropriateness_score, "appropriateness_score"))
        object.__setattr__(self, "calibration_score", _ensure_score(self.calibration_score, "calibration_score"))
        object.__setattr__(self, "consistency_score", _ensure_score(self.consistency_score, "consistency_score"))
        object.__setattr__(self, "readability_score", _ensure_score(self.readability_score, "readability_score"))

    @property
    def overall_score(self) -> float:
        return (
            3 * self.appropriateness_score
            + 2 * self.groundedness_score
            + self.calibration_score
            + self.consistency_score
            + self.readability_score
        ) / 8.0


@dataclass(frozen=True)
class EvaluationResult:
    scores: EvaluationScores
    failed_sentences: list[str]
    judge_feedback: str
    improvement_suggestions: list[str]

    @property
    def overall_score(self) -> float:
        return self.scores.overall_score


@dataclass(frozen=True)
class PromptVersionRecord:
    prompt_version: str
    label: str
    prompt_text: str
    applied_rules: str
    good_example: str
    bad_example: str
    created_at: str = field(default_factory=_utc_now)


@dataclass(frozen=True)
class EvaluationRunRecord:
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
    created_at: str = field(default_factory=_utc_now)


@dataclass(frozen=True)
class LoopResult:
    dataset_id: str
    final_prompt_version: str
    final_run: EvaluationRunRecord
    best_run: EvaluationRunRecord
    runs: list[EvaluationRunRecord]
    prompt_history: list[PromptVersionRecord]
    acceptance_passed: bool
    acceptance_checks: list[str]
    acceptance_failures: list[str]
    elapsed_seconds: float
    total_prompt_tokens: int
    total_completion_tokens: int
    stopped_reason: str
    human_review_notes: str
