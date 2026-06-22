from __future__ import annotations

import re
from dataclasses import dataclass
from statistics import mean

from core.schemas import EvaluationResult, EvaluationScores, MockMetricData

STRONG_WORDS = {
    "collapse",
    "collapsed",
    "surge",
    "surged",
    "dramatic",
    "dramatically",
    "severe",
    "material",
    "alarming",
    "clear",
    "obvious",
}

HEDGE_WORDS = {"may", "might", "appears", "suggests", "likely", "possibly", "caution", "cautious"}


def _sentences(report_text: str) -> list[str]:
    raw = [line.strip() for line in re.split(r"[\n\.]+", report_text) if line.strip()]
    return raw


def _expected_direction(metric: MockMetricData) -> str:
    if metric.wow > 0.5:
        return "up"
    if metric.wow < -0.5:
        return "down"
    return "flat"


def _has_mismatch(report_text: str, metric: MockMetricData) -> bool:
    direction = _expected_direction(metric)
    text = report_text.lower()
    if direction == "up" and any(word in text for word in {"down", "decline", "decrease", "drop", "softening"}):
        return True
    if direction == "down" and any(word in text for word in {"up", "increase", "rise", "surge", "growth"}):
        return True
    return False


def _find_strong_sentences(sentences: list[str], metric: MockMetricData) -> list[str]:
    weak_change = abs(metric.wow) < 3.0 and abs(metric.dod) < 2.0
    failed: list[str] = []
    for sentence in sentences:
        lower = sentence.lower()
        if any(word in lower for word in STRONG_WORDS) and weak_change:
            failed.append(sentence)
    return failed


def _groundedness_score(metric: MockMetricData, report_text: str) -> float:
    score = 5.0
    expected_numbers = {
        f"{metric.current:,.0f}",
        f"{metric.previous:,.0f}",
        f"{metric.avg_4w:,.0f}",
        f"{metric.dod:+.1f}%",
        f"{metric.wow:+.1f}%",
    }
    lower = report_text.lower()
    for value in expected_numbers:
        if value.lower() not in lower:
            score -= 0.4
    if _has_mismatch(report_text, metric):
        score -= 1.5
    return max(1.0, score)


def _appropriateness_score(metric: MockMetricData, sentences: list[str]) -> float:
    score = 5.0
    weak_change = abs(metric.wow) < 3.0
    strong_sentences = _find_strong_sentences(sentences, metric)
    if strong_sentences and weak_change:
        score -= 2.0
    if weak_change and not any(word in " ".join(sentences).lower() for word in {"caution", "suggest", "may", "might", "appears"}):
        score -= 1.0
    return max(1.0, score)


def _calibration_score(metric: MockMetricData, sentences: list[str]) -> float:
    score = 5.0
    text = " ".join(sentences).lower()
    weak_change = abs(metric.wow) < 3.0 or abs(metric.dod) < 2.0
    if weak_change and not any(word in text for word in HEDGE_WORDS):
        score -= 1.5
    if not weak_change and any(word in text for word in {"uncertain", "maybe"}):
        score -= 0.5
    return max(1.0, score)


def _consistency_score(metric: MockMetricData, sentences: list[str]) -> float:
    score = 5.0
    text = " ".join(sentences).lower()
    if "clear" in text and abs(metric.wow) < 1.0:
        score -= 1.0
    if "cautious" in text and abs(metric.wow) > 4.0:
        score -= 0.5
    return max(1.0, score)


def _readability_score(report_text: str) -> float:
    score = 5.0
    lines = [line for line in report_text.splitlines() if line.strip()]
    if not any(line.startswith("## ") for line in lines):
        score -= 1.0
    bullet_count = sum(1 for line in lines if line.strip().startswith("- "))
    if bullet_count < 4:
        score -= 0.5
    if bullet_count > 7:
        score -= 1.0
    avg_len = mean(len(line) for line in lines)
    if avg_len > 95:
        score -= 0.5
    return max(1.0, score)


@dataclass
class EvaluationAgent:
    def evaluate(self, metric: MockMetricData, report_text: str) -> EvaluationResult:
        sentences = _sentences(report_text)
        groundedness = _groundedness_score(metric, report_text)
        appropriateness = _appropriateness_score(metric, sentences)
        calibration = _calibration_score(metric, sentences)
        consistency = _consistency_score(metric, sentences)
        readability = _readability_score(report_text)
        failed_sentences = _find_strong_sentences(sentences, metric)
        if _has_mismatch(report_text, metric):
            failed_sentences.append("Direction words contradict the source data.")
        feedback = self._build_feedback(metric, groundedness, appropriateness, calibration, consistency, readability)
        suggestions = self._build_suggestions(groundedness, appropriateness, calibration, consistency, readability)
        return EvaluationResult(
            scores=EvaluationScores(
                groundedness_score=groundedness,
                appropriateness_score=appropriateness,
                calibration_score=calibration,
                consistency_score=consistency,
                readability_score=readability,
            ),
            failed_sentences=failed_sentences,
            judge_feedback=feedback,
            improvement_suggestions=suggestions,
        )

    def _build_feedback(
        self,
        metric: MockMetricData,
        groundedness: float,
        appropriateness: float,
        calibration: float,
        consistency: float,
        readability: float,
    ) -> str:
        return (
            f"{metric.metric_name}: groundedness={groundedness:.1f}, appropriateness={appropriateness:.1f}, "
            f"calibration={calibration:.1f}, consistency={consistency:.1f}, readability={readability:.1f}."
        )

    def _build_suggestions(
        self,
        groundedness: float,
        appropriateness: float,
        calibration: float,
        consistency: float,
        readability: float,
    ) -> list[str]:
        suggestions: list[str] = []
        if groundedness < 4.5:
            suggestions.append("Restate the exact source numbers and avoid paraphrasing them loosely.")
        if appropriateness < 4.5:
            suggestions.append("Tone down strong adjectives unless the movement is materially large.")
        if calibration < 4.5:
            suggestions.append("Add an explicit hedge when the trend is directional but not decisive.")
        if consistency < 4.5:
            suggestions.append("Use the same threshold logic in the overview and the breakdown section.")
        if readability < 4.5:
            suggestions.append("Tighten long bullets and keep the markdown structure shallow.")
        return suggestions

