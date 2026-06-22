from __future__ import annotations

from dataclasses import dataclass

from core.prompt_loader import build_prompt_document, update_prompt_spec
from core.schemas import EvaluationResult, PromptDocument


@dataclass
class PromptOptimizer:
    def propose_next(self, current: PromptDocument, evaluation: EvaluationResult, iteration: int) -> PromptDocument:
        spec = current.spec
        if iteration == 0:
            next_spec = update_prompt_spec(
                spec,
                label="generator_v2",
                tone="measured",
                caution_level="balanced",
                max_bullets=4,
                instructions=(
                    spec.instructions
                    + "\n\nUse exact source numbers, avoid dramatic language, and add one short caveat when the movement is modest."
                ),
                good_example="The metric declined modestly week over week, so the direction is negative but not conclusive.",
                bad_example="The metric collapsed, which proves the user base is broken.",
                notes="First optimization pass focuses on grounding and calibration.",
            )
            return build_prompt_document(next_spec)

        next_spec = update_prompt_spec(
            spec,
            label="generator_v3",
            tone="measured",
            caution_level="high",
            max_bullets=5,
            instructions=(
                spec.instructions
                + "\n\nAdd a short caution after every section, keep wording highly qualified, and never skip the caveat."
            ),
            good_example="The metric appears weaker, although the data only supports a directional read.",
            bad_example="The metric is definitely broken, and the cause is obvious.",
            notes="Second optimization pass overcompensates to protect calibration.",
        )
        return build_prompt_document(next_spec)

