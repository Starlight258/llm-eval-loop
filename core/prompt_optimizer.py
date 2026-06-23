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
                "Keep WoW and DoD aligned with the source data. State the change as the delta between current and previous, not as the absolute current value. If the movement is positive, describe it as up or higher; if it is negative, describe it as down or lower. Do not flip the direction."
            )
            good_example = "The metric increased by 33,000 week over week, which matches the positive direction in the data."
            bad_example = "The metric increased by 1,845,000 week over week even though the source data only changed by 33,000."
            notes.append("Reinforced direction consistency and exact delta usage.")

        if evaluation.scores.appropriateness_score < 4.5:
            tone = "measured"
            caution_level = "balanced"
            instruction_additions.append(
                "Keep the tone measured unless the movement is clearly large."
            )
            good_example = "The metric moved higher this week, but the change is still small enough to keep the read measured."
            bad_example = "The metric exploded, so the result is obviously exceptional."
            notes.append("Reduced overconfident phrasing.")

        if evaluation.scores.calibration_score < 4.5:
            caution_level = "high"
            instruction_additions.append(
                "When the movement is modest, add one short hedge and avoid turning a small shift into a firm conclusion."
            )
            good_example = "The metric moved lower this week, but the pattern is still too small to call a clear trend."
            bad_example = "The metric is broken, and this clearly shows the issue is severe."
            notes.append("Added hedging for modest movement.")

        if evaluation.scores.consistency_score < 4.5:
            instruction_additions.append(
                "Use the same threshold logic in the snapshot, interpretation, and watchouts sections so the report does not contradict itself."
            )
            good_example = "The snapshot and watchouts both treat the change as modest, so the report stays consistent."
            bad_example = "The snapshot calls the move small, but the interpretation describes it as a major shift."
            notes.append("Aligned threshold logic across sections.")

        if evaluation.scores.readability_score < 4.5:
            max_bullets = min(max_bullets, 4)
            instruction_additions.append(
                "Keep bullets short and avoid stacking too many points in one section."
            )
            good_example = "The report stays compact, with each section making one clear point."
            bad_example = "The report uses long bullets and tries to cover too many ideas at once."
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
