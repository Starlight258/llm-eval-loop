from __future__ import annotations

import json
import re
from dataclasses import dataclass

from core.llm_client import OllamaChatResult, OllamaClient, OllamaUsage
from core.schemas import EvaluationResult, EvaluationScores, MockMetricData


def _expected_direction(metric: MockMetricData) -> str:
    if metric.wow > 0.5:
        return "up"
    if metric.wow < -0.5:
        return "down"
    return "flat"


def _has_mismatch(report_text: str, metric: MockMetricData) -> bool:
    direction = _expected_direction(metric)
    text = report_text.lower()
    if direction == "up" and any(re.search(rf"\b{word}\b", text) for word in {"down", "decline", "decrease", "drop", "softening"}):
        return True
    if direction == "down" and any(re.search(rf"\b{word}\b", text) for word in {"up", "increase", "rise", "surge", "growth"}):
        return True
    return False


def _sentence_chunks(report_text: str) -> list[str]:
    return [chunk.strip() for chunk in re.split(r"[\n\.]+", report_text) if chunk.strip()]


def _expected_delta(metric: MockMetricData) -> float:
    return abs(metric.current - metric.previous)


def _parse_change_value(sentence: str) -> float | None:
    match = re.search(
        r"(?:increased|decreased|rose|fell|up|down|grew|dropped)(?:\s+by)?\s+([-+]?\d[\d,]*(?:\.\d+)?)",
        sentence,
        re.IGNORECASE,
    )
    if not match:
        return None
    return float(match.group(1).replace(",", ""))


def _numeric_change_mismatch_sentences(report_text: str, metric: MockMetricData) -> list[str]:
    expected_delta = _expected_delta(metric)
    if expected_delta == 0:
        return []
    tolerance = max(0.5, expected_delta * 0.25)
    failed: list[str] = []
    for sentence in _sentence_chunks(report_text):
        lower = sentence.lower()
        if not any(word in lower for word in {"increased", "decreased", "rose", "fell", "up", "down", "grew", "dropped"}):
            continue
        parsed = _parse_change_value(sentence)
        if parsed is None:
            continue
        if abs(parsed - expected_delta) > tolerance:
            failed.append(f"Numeric change mismatch: expected about {expected_delta:,.1f} but saw {parsed:,.1f}.")
    return failed


@dataclass
class EvaluationAgent:
    llm_client: OllamaClient | None = None
    model_name: str = "qwen2.5:3b"
    last_usage: OllamaUsage | None = None

    def evaluate(self, metric: MockMetricData, report_text: str) -> EvaluationResult:
        if self.llm_client is None:
            raise RuntimeError("Ollama client is required for evaluation")
        return self._evaluate_with_llm(metric, report_text)

    def _evaluate_with_llm(self, metric: MockMetricData, report_text: str) -> EvaluationResult:
        system = (
            "You are a strict evaluator for Markdown analyst reports. "
            "Score only, do not rewrite the report. Return JSON only. "
            "Treat direction mismatches between the report and source data as serious errors."
        )
        user = (
            "Evaluate the report using these rubric fields:\n"
            "- groundedness_score\n"
            "- appropriateness_score\n"
            "- calibration_score\n"
            "- consistency_score\n"
            "- readability_score\n\n"
            "Return a JSON object with these keys:\n"
            "{"
            '"groundedness_score": number, '
            '"appropriateness_score": number, '
            '"calibration_score": number, '
            '"consistency_score": number, '
            '"readability_score": number, '
            '"failed_sentences": [string], '
            '"judge_feedback": string, '
            '"improvement_suggestions": [string]'
            "}\n\n"
            f"Source data:\n{json.dumps(metric.__dict__, ensure_ascii=False, indent=2)}\n\n"
            f"Report:\n{report_text}\n"
            "All scores must be between 1 and 5."
        )
        result = self._chat(system=system, user=user)
        self.last_usage = result.usage
        raw = result.content
        payload = self._parse_json_payload(raw)
        local_failures: list[str] = []
        groundedness_penalty = 0.0
        if _has_mismatch(report_text, metric):
            local_failures.append("Direction words contradict the source data.")
            groundedness_penalty += 1.5
        numeric_failures = _numeric_change_mismatch_sentences(report_text, metric)
        if numeric_failures:
            local_failures.extend(numeric_failures)
            groundedness_penalty += 1.5
        scores = EvaluationScores(
            groundedness_score=max(1.0, float(payload["groundedness_score"]) - groundedness_penalty),
            appropriateness_score=payload["appropriateness_score"],
            calibration_score=payload["calibration_score"],
            consistency_score=payload["consistency_score"],
            readability_score=payload["readability_score"],
        )
        failed_sentences = list(payload.get("failed_sentences", []))
        for sentence in local_failures:
            if sentence not in failed_sentences:
                failed_sentences.append(sentence)
        judge_feedback = str(payload.get("judge_feedback", ""))
        if local_failures:
            note = " ".join(local_failures)
            judge_feedback = f"{judge_feedback} {note}".strip()
        improvement_suggestions = [str(item) for item in payload.get("improvement_suggestions", [])]
        if numeric_failures and "Describe the change using the delta between current and previous." not in improvement_suggestions:
            improvement_suggestions.append("Describe the change using the delta between current and previous.")
        if _has_mismatch(report_text, metric) and "Keep the direction aligned with the source data." not in improvement_suggestions:
            improvement_suggestions.append("Keep the direction aligned with the source data.")
        return EvaluationResult(
            scores=scores,
            failed_sentences=failed_sentences,
            judge_feedback=judge_feedback,
            improvement_suggestions=improvement_suggestions,
        )

    def _chat(self, *, system: str, user: str) -> OllamaChatResult:
        if hasattr(self.llm_client, "chat_with_usage"):
            result = self.llm_client.chat_with_usage(system=system, user=user)  # type: ignore[union-attr]
            if isinstance(result, OllamaChatResult):
                return result
            if isinstance(result, tuple) and len(result) == 2:
                content, usage = result
                if not isinstance(usage, OllamaUsage):
                    usage = OllamaUsage()
                return OllamaChatResult(content=str(content), usage=usage)
            if isinstance(result, str):
                return OllamaChatResult(content=result, usage=OllamaUsage())
        content = self.llm_client.chat(system=system, user=user)  # type: ignore[union-attr]
        return OllamaChatResult(content=content, usage=OllamaUsage())

    def _parse_json_payload(self, text: str) -> dict:
        candidate = text.strip()
        if candidate.startswith("```"):
            candidate = candidate.strip("`")
        start = candidate.find("{")
        end = candidate.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise ValueError("LLM response did not contain JSON")
        return json.loads(candidate[start : end + 1])
