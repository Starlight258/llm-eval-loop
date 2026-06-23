from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from core.loop import run_evaluation_loop
from core.prompt_loader import load_prompt_document
from core.prompt_optimizer import PromptOptimizer
from core.schemas import EvaluationResult, EvaluationScores, MockMetricData
from storage.db import EvaluationStore


BASE_DIR = Path(__file__).resolve().parents[1]
PROMPT_TEXT = """\
label: generator_v1
tone: assertive
caution_level: low
max_bullets: 4
include_breakdowns: true
instructions: |
  Write a compact markdown report with a short snapshot, one interpretation paragraph, and a breakdown section.
  Prefer direct language and keep the report easy to scan.
good_example: |
  The metric declined week over week, so the direction is negative.
bad_example: |
  The metric might be bad for many reasons, but it is hard to say anything.
notes: |
  Baseline prompt for the first loop.
"""


def load_test_prompt(tmpdir: str):
    path = Path(tmpdir) / "generator_v1.yaml"
    path.write_text(PROMPT_TEXT)
    return load_prompt_document(path)


class PromptOptimizerTests(unittest.TestCase):
    def test_loop_keeps_prompt_history_in_memory_and_stops(self) -> None:
        metric = MockMetricData(**json.loads((BASE_DIR / "data/mock_marketplace.json").read_text()))
        with tempfile.TemporaryDirectory() as tmpdir:
            store = EvaluationStore(Path(tmpdir) / "runs.sqlite")
            prompt = load_test_prompt(tmpdir)
            result = run_evaluation_loop("mock_marketplace", metric, prompt, store)
            self.assertGreaterEqual(len(result.runs), 1)
            self.assertGreaterEqual(len(result.prompt_history), 1)
            self.assertIn(result.stopped_reason, {"max_iterations_reached", "score_declined"})
            self.assertTrue(store.list_runs())

    def test_optimizer_uses_evaluation_feedback(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            prompt = load_test_prompt(tmpdir)
            evaluation = EvaluationResult(
                scores=EvaluationScores(
                    groundedness_score=3.5,
                    appropriateness_score=4.0,
                    calibration_score=3.8,
                    consistency_score=4.7,
                    readability_score=4.8,
                ),
                failed_sentences=["Direction words contradict the source data."],
                judge_feedback="mock feedback",
                improvement_suggestions=["mock suggestion"],
            )
            next_prompt = PromptOptimizer().propose_next(prompt, evaluation, iteration=0)
            self.assertEqual(next_prompt.label, "generator_v2")
            self.assertEqual(next_prompt.spec.tone, "measured")
            self.assertEqual(next_prompt.spec.caution_level, "high")
            self.assertIn("Keep the sign of WoW and DoD consistent", next_prompt.spec.instructions)


if __name__ == "__main__":
    unittest.main()
