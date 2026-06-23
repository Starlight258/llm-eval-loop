from __future__ import annotations

from dataclasses import dataclass
import json
import re

from core.llm_client import OllamaChatResult, OllamaClient, OllamaUsage
from core.schemas import MockMetricData, PromptDocument, PromptSpec


def _format_number(value: float) -> str:
    if abs(value) >= 1000 and float(value).is_integer():
        return f"{int(value):,}"
    if float(value).is_integer():
        return str(int(value))
    return f"{value:,.1f}"


def _format_percent(value: float) -> str:
    return f"{value:+.1f}%"


def _trend_label(trend: list[float]) -> str:
    delta = trend[-1] - trend[0]
    if delta > 1.0:
        return "upward"
    if delta < -1.0:
        return "downward"
    return "stable"


def _direction_word(change: float) -> str:
    if change > 0.5:
        return "increased"
    if change < -0.5:
        return "decreased"
    return "held roughly flat"


def _canonical_title(metric: MockMetricData) -> str:
    metric_label = metric.metric_name.replace("_", " ").title()
    return f"# {metric.domain} {metric_label} Report"


def _canonical_snapshot(metric: MockMetricData) -> str:
    lines = [
        "## Snapshot",
        f"- Domain: {metric.domain}",
        f"- Metric Name: {metric.metric_name}",
        f"- Current: {_format_number(metric.current)}",
        f"- Previous: {_format_number(metric.previous)}",
        f"- DoD: {_format_percent(metric.dod)}",
        f"- WoW: {_format_percent(metric.wow)}",
        f"- 4W Average: {_format_number(metric.avg_4w)}",
    ]
    return "\n".join(lines)


def _canonical_interpretation(metric: MockMetricData, spec: PromptSpec) -> str:
    delta = metric.current - metric.previous
    direction = _direction_word(metric.wow)
    trend = _trend_label(metric.trend_7d)
    if spec.caution_level == "high":
        return (
            "## Interpretation\n"
            f"The metric {direction} week over week by {_format_number(abs(delta))} ({_format_percent(metric.wow)}). "
            f"The 7-day trend is {trend}, so this remains a directional read rather than a causal conclusion."
        )
    if spec.caution_level == "low":
        return (
            "## Interpretation\n"
            f"The metric {direction} week over week by {_format_number(abs(delta))} ({_format_percent(metric.wow)}). "
            f"The 7-day trend is {trend}, which supports a direct read on the direction of travel."
        )
    return (
        "## Interpretation\n"
        f"The metric {direction} week over week by {_format_number(abs(delta))} ({_format_percent(metric.wow)}). "
        f"The 7-day trend is {trend}, so the change should be read cautiously."
    )


def _canonical_breakdown(metric: MockMetricData, spec: PromptSpec) -> str:
    lines = ["## Breakdown"]
    if spec.include_breakdowns and metric.breakdowns:
        for group, values in metric.breakdowns.items():
            pieces = ", ".join(f"{name} {_format_percent(change)}" for name, change in sorted(values.items()))
            lines.append(f"- {group}: {pieces}")
    else:
        lines.append("- No breakdowns were included in this run.")
    return "\n".join(lines)


def _canonical_watchouts(metric: MockMetricData, spec: PromptSpec) -> str:
    trend = _trend_label(metric.trend_7d)
    lines = ["## Watchouts"]
    if spec.caution_level == "high":
        lines.append("- Keep monitoring the directional trend for follow-up signals.")
    else:
        lines.append(f"- The {trend} trend should be monitored for persistence.")
    if spec.max_bullets > 1:
        lines.append("- Check platform-level movement for any divergence from the overall trend.")
    return "\n".join(lines[: spec.max_bullets + 1])


def _build_canonical_report(metric: MockMetricData, spec: PromptSpec) -> str:
    sections = [
        _canonical_title(metric),
        "",
        _canonical_snapshot(metric),
        "",
        _canonical_interpretation(metric, spec),
        "",
        _canonical_breakdown(metric, spec),
        "",
        _canonical_watchouts(metric, spec),
    ]
    return "\n".join(sections).rstrip() + "\n"


def _expected_direction(metric: MockMetricData) -> str:
    if metric.wow > 0.5:
        return "up"
    if metric.wow < -0.5:
        return "down"
    return "flat"


def _has_direction_mismatch(report_text: str, metric: MockMetricData) -> bool:
    direction = _expected_direction(metric)
    text = report_text.lower()
    if direction == "up" and any(re.search(rf"\b{word}\b", text) for word in {"down", "decline", "decrease", "drop", "softening"}):
        return True
    if direction == "down" and any(re.search(rf"\b{word}\b", text) for word in {"up", "increase", "rise", "surge", "growth"}):
        return True
    return False


def _snapshot_mismatch(report_text: str, metric: MockMetricData) -> bool:
    normalized = report_text.replace(",", "").lower()
    expected_values = [
        f"{metric.current:.0f}".lower(),
        f"{metric.previous:.0f}".lower(),
        f"{metric.avg_4w:.0f}".lower(),
        f"{metric.dod:+.1f}%".lower(),
        f"{metric.wow:+.1f}%".lower(),
    ]
    return any(value not in normalized for value in expected_values)


def _numeric_change_mismatch(report_text: str, metric: MockMetricData) -> bool:
    expected_delta = abs(metric.current - metric.previous)
    if expected_delta == 0:
        return False
    lower = report_text.lower()
    if not any(word in lower for word in {"increased", "decreased", "rose", "fell", "up", "down", "grew", "dropped"}):
        return False
    normalized = report_text.replace(",", "")
    candidates = {f"{expected_delta:,.0f}".replace(",", ""), f"{expected_delta:,.1f}".replace(",", "")}
    return not any(candidate in normalized for candidate in candidates)


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
        if _has_direction_mismatch(report, metric) or _snapshot_mismatch(report, metric) or _numeric_change_mismatch(report, metric):
            return _build_canonical_report(metric, spec)
        return report

    def _generate_with_llm(self, metric: MockMetricData, spec: PromptSpec, *, human_feedback: str = "") -> str:
        system = (
            "You write compact analyst reports in Markdown. "
            "Use only the provided data. Do not add unsupported causal claims. "
            "Keep the direction of change consistent with the source data."
        )
        feedback_block = ""
        if human_feedback.strip():
            feedback_block = (
                f"Human feedback for this draft:\n{human_feedback.strip()}\n\n"
                "Use the feedback when it helps the report, but do not override the source data."
            )
        user = (
            f"Prompt spec:\n{json.dumps(spec.__dict__, ensure_ascii=False, indent=2)}\n\n"
            f"Metric data:\n{json.dumps(metric.__dict__, ensure_ascii=False, indent=2)}\n\n"
            f"{feedback_block}"
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
