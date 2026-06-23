from __future__ import annotations

from dataclasses import dataclass

from core.prompt_loader import build_prompt_document, update_prompt_spec
from core.schemas import EvaluationResult, PromptDocument


def _append_instruction(current: str, addition: str) -> str:
    if addition in current:
        return current
    if not current.strip():
        return addition
    return f"{current.rstrip()}\n\n{addition}"


def _contains_direction_failure(evaluation: EvaluationResult) -> bool:
    return any("Direction words contradict the source data." in sentence for sentence in evaluation.failed_sentences)


@dataclass
class PromptOptimizer:
    def propose_next(self, current: PromptDocument, evaluation: EvaluationResult, iteration: int) -> PromptDocument:
        spec = current.spec
        label = f"generator_v{iteration + 2}"
        instruction_additions: list[str] = []
        notes: list[str] = []
        tone = spec.tone
        caution_level = spec.caution_level
        max_bullets = spec.max_bullets
        good_example = spec.good_example
        bad_example = spec.bad_example

        if evaluation.scores.groundedness_score < 4.5 or _contains_direction_failure(evaluation):
            instruction_additions.append(
                "Keep the sign of WoW and DoD consistent. If the source data is positive, describe it as increasing or growing; if it is negative, describe it as decreasing or falling. Never reverse the direction."
            )
            good_example = "The metric increased week over week, so the direction is positive."
            bad_example = "The metric declined week over week even though the source data is positive."
            notes.append("Reinforced direction consistency and exact number usage.")

        if evaluation.scores.appropriateness_score < 4.5:
            tone = "measured"
            caution_level = "balanced"
            instruction_additions.append(
                "Avoid dramatic language unless the movement is materially large."
            )
            notes.append("Reduced overconfident phrasing.")

        if evaluation.scores.calibration_score < 4.5:
            caution_level = "high"
            instruction_additions.append(
                "Add one short hedge when the movement is modest so the conclusion stays calibrated."
            )
            good_example = "The metric appears weaker, although the data only supports a directional read."
            bad_example = "The metric is definitely broken, and the cause is obvious."
            notes.append("Added hedging for modest movement.")

        if evaluation.scores.consistency_score < 4.5:
            instruction_additions.append(
                "Use the same threshold logic in the snapshot, interpretation, and watchouts sections."
            )
            notes.append("Aligned threshold logic across sections.")

        if evaluation.scores.readability_score < 4.5:
            max_bullets = min(max_bullets, 4)
            notes.append("Kept the markdown shallow.")

        if not instruction_additions:
            instruction_additions.append(
                "Preserve the current structure and keep the report grounded in the source data."
            )
            notes.append("No major issues detected, so the next version keeps the same approach.")

        next_spec = update_prompt_spec(
            spec,
            label=label,
            tone=tone,
            caution_level=caution_level,
            max_bullets=max_bullets,
            instructions=_append_instruction(spec.instructions, "\n\n".join(instruction_additions)),
            good_example=good_example,
            bad_example=bad_example,
            notes=" ".join(notes),
        )
        return build_prompt_document(next_spec)
