from __future__ import annotations

from dataclasses import dataclass
import json
import re
from statistics import mean

from core.llm_client import OllamaChatResult, OllamaClient, OllamaUsage
from core.schemas import MockMetricData, PromptDocument, PromptSpec


def _format_number(value: float) -> str:
    if abs(value) >= 1000 and float(value).is_integer():
        return f"{int(value):,}"
    if float(value).is_integer():
        return str(int(value))
    return f"{value:,.1f}"


def _format_percent(value: float) -> str:
    sign = "+" if value > 0 else ""
    return f"{sign}{value:.1f}%"


def _direction_word(change: float) -> str:
    if change > 0.5:
        return "increased"
    if change < -0.5:
        return "decreased"
    return "held roughly flat"


def _trend_label(trend: list[float]) -> str:
    delta = trend[-1] - trend[0]
    if delta > 1.0:
        return "upward"
    if delta < -1.0:
        return "downward"
    return "stable"


def _caution_phrase(spec: PromptSpec) -> str:
    if spec.caution_level == "high":
        return "This is a directional read and not a causal conclusion."
    if spec.caution_level == "balanced":
        return "The data suggests a directional change, but the root cause is not established here."
    return "The pattern is clear enough to call directly."


def _tone_prefix(spec: PromptSpec) -> str:
    if spec.tone == "assertive":
        return "clear"
    if spec.tone == "measured":
        return "measured"
    return "balanced"


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


def _build_report(metric: MockMetricData, spec: PromptSpec) -> str:
    change_direction = _direction_word(metric.wow)
    trend = _trend_label(metric.trend_7d)
    caution = _caution_phrase(spec)
    prefix = _tone_prefix(spec)
    lines: list[str] = [f"# {metric.metric_name} Report", ""]
    lines.extend(
        [
            "## Snapshot",
            f"- Domain: {metric.domain}",
            f"- Current: {_format_number(metric.current)}",
            f"- Previous: {_format_number(metric.previous)}",
            f"- DoD: {_format_percent(metric.dod)}",
            f"- WoW: {_format_percent(metric.wow)}",
            f"- 4W average: {_format_number(metric.avg_4w)}",
            "",
            "## Interpretation",
        ]
    )
    summary = (
        f"The metric {change_direction} week over week, and the 7-day series looks {trend}. "
        f"That points to a {prefix} interpretation rather than a strong causal claim."
    )
    if spec.caution_level == "low":
        summary = (
            f"The metric {change_direction} week over week, and the 7-day series looks {trend}. "
            f"This supports a direct read on the direction of travel."
        )
    elif spec.caution_level == "high":
        summary = (
            f"The metric {change_direction} week over week, but the evidence still supports only a cautious directional read. "
            f"The 7-day series looks {trend}, so the pattern is worth monitoring."
        )
    lines.append(summary)
    lines.append("")
    lines.append("## Breakdown")
    if spec.include_breakdowns and metric.breakdowns:
        for group, values in metric.breakdowns.items():
            pieces = ", ".join(f"{name} {_format_percent(change)}" for name, change in sorted(values.items()))
            lines.append(f"- {group}: {pieces}")
    else:
        lines.append("- No breakdowns were included in this run.")
    lines.append("")
    lines.append("## Watchouts")
    watchouts = [
        f"- {caution}",
    ]
    if spec.max_bullets > 4:
        watchouts.append("- Keep the same thresholds across similar metrics so the interpretation stays consistent.")
    if mean(metric.trend_7d[-3:]) < mean(metric.trend_7d[:3]):
        watchouts.append("- Recent movement is softer than the earlier part of the window.")
    lines.extend(watchouts[: spec.max_bullets])
    return "\n".join(lines).rstrip() + "\n"


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
