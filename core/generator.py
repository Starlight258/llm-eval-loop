from __future__ import annotations

from dataclasses import dataclass
import json

from core.llm_client import OllamaChatResult, OllamaClient, OllamaUsage
from core.schemas import MockMetricData, PromptDocument, PromptSpec


@dataclass
class ReportGenerator:
    llm_client: OllamaClient | None = None
    model_name: str = "qwen2.5:3b"
    last_usage: OllamaUsage | None = None

    def generate(
        self,
        metric: MockMetricData,
        prompt: PromptDocument | PromptSpec,
        *,
        human_feedback: str = "",
    ) -> str:
        spec = prompt.spec if isinstance(prompt, PromptDocument) else prompt
        if self.llm_client is None:
            raise RuntimeError("Ollama client is required for report generation")
        report = self._generate_with_llm(metric, spec, human_feedback=human_feedback)
        return report

    def _generate_with_llm(self, metric: MockMetricData, spec: PromptSpec, *, human_feedback: str = "") -> str:
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
            "Copy the source numbers exactly in the Snapshot section. Do not scale, round, or renormalize them. "
            "Keep the current, previous, average, DoD, and WoW values in the same magnitude as the source data.\n"
            "When you describe change, compute the delta from current and previous first and state that delta explicitly. "
            "Include both the absolute delta and the percent change when relevant, for example 'up by 33,000 (+1.8%)'. "
            "Do not use the full current value as the size of the change.\n"
            "Do not invent labels like 'Wildcard' or 'new high'. Use the source labels DoD, WoW, and 4W average.\n"
            "Stay grounded, keep the wording cautious when the movement is modest, keep the whole report short, "
            "and never describe a positive WoW/DoD as a decline or a negative WoW/DoD as growth."
        )
        result = self._chat(system=system, user=user)
        self.last_usage = result.usage
        return result.content

    def _chat(self, *, system: str, user: str) -> OllamaChatResult:
        if hasattr(self.llm_client, "chat_with_usage"):
            result = self.llm_client.chat_with_usage(system=system, user=user)  # type: ignore[union-attr]
            if hasattr(result, "content") and hasattr(result, "usage"):
                usage = getattr(result, "usage")
                return OllamaChatResult(
                    content=str(getattr(result, "content")),
                    usage=OllamaUsage(
                        prompt_tokens=int(getattr(usage, "prompt_tokens", 0) or 0),
                        completion_tokens=int(getattr(usage, "completion_tokens", 0) or 0),
                    ),
                )
            if isinstance(result, tuple) and len(result) == 2:
                content, usage = result
                if not isinstance(usage, OllamaUsage):
                    usage = OllamaUsage()
                return OllamaChatResult(content=str(content), usage=usage)
            if isinstance(result, str):
                return OllamaChatResult(content=result, usage=OllamaUsage())
        content = self.llm_client.chat(system=system, user=user)  # type: ignore[union-attr]
        return OllamaChatResult(content=content, usage=OllamaUsage())
