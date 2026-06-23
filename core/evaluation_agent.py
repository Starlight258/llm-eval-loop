from __future__ import annotations

import json
from dataclasses import dataclass

from core.llm_client import OllamaChatResult, OllamaClient, OllamaUsage
from core.schemas import EvaluationResult, EvaluationScores, MockMetricData


@dataclass
class EvaluationAgent:
    llm_client: OllamaClient | None = None
    model_name: str = "llama3.2:3b"
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
        scores = EvaluationScores(
            groundedness_score=payload["groundedness_score"],
            appropriateness_score=payload["appropriateness_score"],
            calibration_score=payload["calibration_score"],
            consistency_score=payload["consistency_score"],
            readability_score=payload["readability_score"],
        )
        return EvaluationResult(
            scores=scores,
            failed_sentences=list(payload.get("failed_sentences", [])),
            judge_feedback=str(payload.get("judge_feedback", "")),
            improvement_suggestions=[str(item) for item in payload.get("improvement_suggestions", [])],
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
