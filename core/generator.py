from __future__ import annotations

from dataclasses import dataclass
import json
import re

from core.llm_client import OllamaChatResult, OllamaClient, OllamaUsage
from core.schemas import MockMetricData, PromptDocument, PromptSpec


def _expected_direction(metric: MockMetricData) -> str:
    if metric.wow > 0.5:
        return "up"
    if metric.wow < -0.5:
        return "down"
    return "flat"


def _has_direction_mismatch(report_text: str, metric: MockMetricData) -> bool:
    direction = _expected_direction(metric)
    text = report_text.lower()
    if direction == "up" and any(re.search(rf"\\b{word}\\b", text) for word in {"down", "decline", "decrease", "drop", "softening"}):
        return True
    if direction == "down" and any(re.search(rf"\\b{word}\\b", text) for word in {"up", "increase", "rise", "surge", "growth"}):
        return True
    return False


@dataclass
class ReportGenerator:
    llm_client: OllamaClient | None = None
    model_name: str = "llama3.2:3b"
    last_usage: OllamaUsage | None = None

    def generate(self, metric: MockMetricData, prompt: PromptDocument | PromptSpec) -> str:
        spec = prompt.spec if isinstance(prompt, PromptDocument) else prompt
        if self.llm_client is None:
            raise RuntimeError("Ollama client is required for report generation")
        report = self._generate_with_llm(metric, spec)
        if _has_direction_mismatch(report, metric):
            raise ValueError("LLM report direction contradicts the source data")
        return report

    def _generate_with_llm(self, metric: MockMetricData, spec: PromptSpec) -> str:
        system = (
            "You write compact analyst reports in Markdown. "
            "Use only the provided data. Do not add unsupported causal claims. "
            "Keep the direction of change consistent with the source data."
        )
        user = (
            f"Prompt spec:\n{json.dumps(spec.__dict__, ensure_ascii=False, indent=2)}\n\n"
            f"Metric data:\n{json.dumps(metric.__dict__, ensure_ascii=False, indent=2)}\n\n"
            "Write a Markdown report with these sections exactly:\n"
            "1. # title\n"
            "2. ## Snapshot with bullets for domain, current, previous, DoD, WoW, and 4W average\n"
            "3. ## Interpretation with 2 to 4 sentences\n"
            "4. ## Breakdown with bullets for any provided breakdowns\n"
            "5. ## Watchouts with 1 to 3 bullets\n"
            "Stay grounded, keep the wording cautious when the movement is modest, keep the whole report short, "
            "and never describe a positive WoW/DoD as a decline or a negative WoW/DoD as growth."
        )
        result = self._chat(system=system, user=user)
        self.last_usage = result.usage
        return result.content

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
