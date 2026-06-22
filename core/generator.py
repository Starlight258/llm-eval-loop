from __future__ import annotations

from dataclasses import dataclass
from statistics import mean

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


@dataclass
class ReportGenerator:
    def generate(self, metric: MockMetricData, prompt: PromptDocument | PromptSpec) -> str:
        spec = prompt.spec if isinstance(prompt, PromptDocument) else prompt
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
                pieces = ", ".join(
                    f"{name} {_format_percent(change)}" for name, change in sorted(values.items())
                )
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

