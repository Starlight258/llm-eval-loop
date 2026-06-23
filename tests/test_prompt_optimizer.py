from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from core.loop import run_evaluation_loop
from core.prompt_loader import load_prompt_document
from core.prompt_optimizer import PromptOptimizer
from core.runtime import RuntimeConfig, RuntimeServices
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
    def test_loop_stops_when_token_budget_is_exceeded(self) -> None:
        class FakeGenerator:
            def __init__(self) -> None:
                self.last_usage = None

            def generate(self, metric: MockMetricData, prompt, *, human_feedback: str = "") -> str:
                from core.llm_client import OllamaUsage

                self.last_usage = OllamaUsage(prompt_tokens=1, completion_tokens=1)
                return (
                    "# listing_count Report\n\n"
                    "## Snapshot\n"
                    "- Domain: Marketplace\n"
                    "- Current: 572,000\n"
                    "- Previous: 583,000\n"
                    "- DoD: -2.0%\n"
                    "- WoW: -2.0%\n"
                    "- 4W average: 560,000\n\n"
                    "## Interpretation\n"
                    "The metric decreased week over week and the trend is downward.\n\n"
                    "## Breakdown\n"
                    "- category: books -1.2%, electronics -2.4%\n\n"
                    "## Watchouts\n"
                    "- The movement is directional."
                )

        class FakeEvaluator:
            def __init__(self) -> None:
                self.last_usage = None

            def evaluate(self, metric: MockMetricData, report: str) -> EvaluationResult:
                from core.llm_client import OllamaUsage

                self.last_usage = OllamaUsage(prompt_tokens=1, completion_tokens=1)
                return EvaluationResult(
                    scores=EvaluationScores(
                        groundedness_score=4.1,
                        appropriateness_score=4.2,
                        calibration_score=4.0,
                        consistency_score=4.1,
                        readability_score=4.2,
                    ),
                    failed_sentences=["The conclusion is slightly verbose."],
                    judge_feedback="ok",
                    improvement_suggestions=["tighten wording"],
                )

        services = RuntimeServices(
            generator=FakeGenerator(),
            evaluator=FakeEvaluator(),
            backend_label="ollama:fake",
        )
        metric = MockMetricData(**json.loads((BASE_DIR / "data/mock_marketplace.json").read_text()))
        with tempfile.TemporaryDirectory() as tmpdir:
            store = EvaluationStore(Path(tmpdir) / "runs.sqlite")
            prompt = load_test_prompt(tmpdir)
            result = run_evaluation_loop(
                "mock_marketplace",
                metric,
                prompt,
                store,
                runtime=RuntimeConfig(max_total_tokens=1),
                services=services,
                human_feedback="Prefer a softer tone and one concise watchout.",
            )
            self.assertEqual(result.stopped_reason, "token_budget_exceeded")
            self.assertFalse(result.acceptance_passed)
            self.assertEqual(len(result.runs), 1)
            self.assertIn("Human feedback was supplied", result.human_review_notes)

    def test_loop_keeps_prompt_history_in_memory_and_stops(self) -> None:
        class FakeGenerator:
            def generate(self, metric: MockMetricData, prompt, *, human_feedback: str = "") -> str:
                return (
                    "# listing_count Report\n\n"
                    "## Snapshot\n"
                    "- Domain: Marketplace\n"
                    "- Current: 572,000\n"
                    "- Previous: 583,000\n"
                    "- DoD: -2.0%\n"
                    "- WoW: -2.0%\n"
                    "- 4W average: 560,000\n\n"
                    "## Interpretation\n"
                    "The metric decreased week over week and the trend is downward.\n\n"
                    "## Breakdown\n"
                    "- category: books -1.2%, electronics -2.4%\n\n"
                    "## Watchouts\n"
                    "- The movement is directional."
                )

        class FakeEvaluator:
            def __init__(self) -> None:
                self.calls = 0

            def evaluate(self, metric: MockMetricData, report: str) -> EvaluationResult:
                self.calls += 1
                if self.calls == 1:
                    scores = EvaluationScores(
                        groundedness_score=4.5,
                        appropriateness_score=4.2,
                        calibration_score=4.0,
                        consistency_score=4.4,
                        readability_score=4.8,
                    )
                    failed_sentences = ["The conclusion is slightly verbose."]
                else:
                    scores = EvaluationScores(
                        groundedness_score=4.6,
                        appropriateness_score=4.7,
                        calibration_score=4.8,
                        consistency_score=4.7,
                        readability_score=4.8,
                    )
                    failed_sentences = []
                return EvaluationResult(
                    scores=scores,
                    failed_sentences=failed_sentences,
                    judge_feedback="ok",
                    improvement_suggestions=["tighten wording"],
                )

        services = RuntimeServices(
            generator=FakeGenerator(),
            evaluator=FakeEvaluator(),
            backend_label="ollama:fake",
        )
        metric = MockMetricData(**json.loads((BASE_DIR / "data/mock_marketplace.json").read_text()))
        with tempfile.TemporaryDirectory() as tmpdir:
            store = EvaluationStore(Path(tmpdir) / "runs.sqlite")
            prompt = load_test_prompt(tmpdir)
            result = run_evaluation_loop("mock_marketplace", metric, prompt, store, services=services)
            self.assertGreaterEqual(len(result.runs), 1)
            self.assertGreaterEqual(len(result.prompt_history), 1)
            self.assertTrue(result.acceptance_checks)
            self.assertIn(result.stopped_reason, {"passed_acceptance_criteria", "score_declined", "max_iterations_reached"})
            self.assertTrue(store.list_runs())
            self.assertTrue(store.list_prompt_versions())
            self.assertGreaterEqual(result.total_prompt_tokens + result.total_completion_tokens, 0)

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
            self.assertIn("Copy the Snapshot numbers exactly", next_prompt.spec.instructions)
            self.assertIn("State the change as the delta between current and previous", next_prompt.spec.instructions)

    def test_optimizer_uses_optional_human_feedback(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            prompt = load_test_prompt(tmpdir)
            evaluation = EvaluationResult(
                scores=EvaluationScores(
                    groundedness_score=4.8,
                    appropriateness_score=4.8,
                    calibration_score=4.8,
                    consistency_score=4.8,
                    readability_score=4.8,
                ),
                failed_sentences=[],
                judge_feedback="ok",
                improvement_suggestions=[],
            )
            next_prompt = PromptOptimizer().propose_next(
                prompt,
                evaluation,
                iteration=0,
                human_feedback="Make the tone less assertive and keep the watchouts to one bullet.",
            )
            self.assertNotIn("Make the tone less assertive and keep the watchouts to one bullet.", next_prompt.spec.instructions)
            self.assertEqual(next_prompt.spec.tone, "measured")
            self.assertEqual(next_prompt.spec.max_bullets, 3)
            self.assertIn("Applied human feedback as scoped prompt rules.", next_prompt.spec.notes)

    def test_optimizer_adds_snapshot_stability_rules_for_dod_wow_feedback(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            prompt = load_test_prompt(tmpdir)
            evaluation = EvaluationResult(
                scores=EvaluationScores(
                    groundedness_score=4.8,
                    appropriateness_score=4.8,
                    calibration_score=4.8,
                    consistency_score=4.8,
                    readability_score=4.8,
                ),
                failed_sentences=[],
                judge_feedback="ok",
                improvement_suggestions=[],
            )
            next_prompt = PromptOptimizer().propose_next(
                prompt,
                evaluation,
                iteration=0,
                human_feedback="DoD와 WoW를 구분해라",
            )
            self.assertIn("Keep the Snapshot section labels and units unchanged.", next_prompt.spec.instructions)
            self.assertIn("Preserve the source percent format for DoD and WoW", next_prompt.spec.instructions)
            self.assertIn("Applied human feedback as scoped prompt rules.", next_prompt.spec.notes)

    def test_loop_separates_baseline_and_feedback_runs(self) -> None:
        class FakeGenerator:
            def __init__(self) -> None:
                self.calls: list[str] = []

            def generate(self, metric: MockMetricData, prompt, *, human_feedback: str = "") -> str:
                self.calls.append(human_feedback)
                if not human_feedback:
                    return (
                        "# listing_count Report\n\n"
                        "## Snapshot\n"
                        "- Domain: Marketplace\n"
                        "- Current: 572,000\n"
                        "- Previous: 583,000\n"
                        "- DoD: -2.0%\n"
                        "- WoW: -2.0%\n"
                        "- 4W average: 560,000\n\n"
                        "## Interpretation\n"
                        "The metric decreased week over week and the trend is downward.\n\n"
                        "## Breakdown\n"
                        "- category: books -1.2%, electronics -2.4%\n\n"
                        "## Watchouts\n"
                        "- The movement is directional."
                    )
                return (
                    "# listing_count Report\n\n"
                    "## Snapshot\n"
                    "- Domain: Marketplace\n"
                    "- Current: 572,000\n"
                    "- Previous: 583,000\n"
                    "- DoD: -2.0%\n"
                    "- WoW: -2.0%\n"
                    "- 4W average: 560,000\n\n"
                    "## Interpretation\n"
                    "The metric decreased week over week and the trend is downward.\n\n"
                    "## Breakdown\n"
                    "- category: books -1.2%, electronics -2.4%\n\n"
                    "## Watchouts\n"
                    "- The movement is directional."
                )

        class FakeEvaluator:
            def __init__(self) -> None:
                self.calls = 0

            def evaluate(self, metric: MockMetricData, report: str) -> EvaluationResult:
                self.calls += 1
                if self.calls == 1:
                    scores = EvaluationScores(
                        groundedness_score=4.0,
                        appropriateness_score=4.0,
                        calibration_score=4.0,
                        consistency_score=4.0,
                        readability_score=4.0,
                    )
                else:
                    scores = EvaluationScores(
                        groundedness_score=4.8,
                        appropriateness_score=4.8,
                        calibration_score=4.8,
                        consistency_score=4.8,
                        readability_score=4.8,
                    )
                return EvaluationResult(
                    scores=scores,
                    failed_sentences=[],
                    judge_feedback="ok",
                    improvement_suggestions=[],
                )

        services = RuntimeServices(
            generator=FakeGenerator(),
            evaluator=FakeEvaluator(),
            backend_label="ollama:fake",
        )
        metric = MockMetricData(**json.loads((BASE_DIR / "data/mock_marketplace.json").read_text()))
        with tempfile.TemporaryDirectory() as tmpdir:
            store = EvaluationStore(Path(tmpdir) / "runs.sqlite")
            prompt = load_test_prompt(tmpdir)
            result = run_evaluation_loop(
                "mock_marketplace",
                metric,
                prompt,
                store,
                services=services,
                human_feedback="Please soften the tone and keep watchouts shorter.",
                max_feedback_iterations=1,
            )
        self.assertEqual(result.baseline_run, result.runs[0])
        self.assertEqual(len(result.feedback_runs), 1)
        self.assertEqual(len(result.runs), 2)
        self.assertEqual(services.generator.calls[0], "")
        self.assertEqual(services.generator.calls[1], "")
        self.assertGreater(result.best_run.overall_score, result.baseline_run.overall_score)

    def test_loop_stops_when_feedback_score_is_equal(self) -> None:
        class FakeGenerator:
            def __init__(self) -> None:
                self.calls: list[str] = []

            def generate(self, metric: MockMetricData, prompt, *, human_feedback: str = "") -> str:
                self.calls.append(human_feedback)
                return (
                    "# listing_count Report\n\n"
                    "## Snapshot\n"
                    "- Domain: Marketplace\n"
                    "- Current: 572,000\n"
                    "- Previous: 583,000\n"
                    "- DoD: -2.0%\n"
                    "- WoW: -2.0%\n"
                    "- 4W average: 560,000\n\n"
                    "## Interpretation\n"
                    "The metric decreased week over week and the trend is downward.\n\n"
                    "## Breakdown\n"
                    "- category: books -1.2%, electronics -2.4%\n\n"
                    "## Watchouts\n"
                    "- The movement is directional."
                )

        class FakeEvaluator:
            def __init__(self) -> None:
                self.calls = 0

            def evaluate(self, metric: MockMetricData, report: str) -> EvaluationResult:
                self.calls += 1
                scores = EvaluationScores(
                    groundedness_score=4.0,
                    appropriateness_score=4.0,
                    calibration_score=4.0,
                    consistency_score=4.0,
                    readability_score=4.0,
                )
                return EvaluationResult(
                    scores=scores,
                    failed_sentences=[],
                    judge_feedback="ok",
                    improvement_suggestions=[],
                )

        services = RuntimeServices(
            generator=FakeGenerator(),
            evaluator=FakeEvaluator(),
            backend_label="ollama:fake",
        )
        metric = MockMetricData(**json.loads((BASE_DIR / "data/mock_marketplace.json").read_text()))
        with tempfile.TemporaryDirectory() as tmpdir:
            store = EvaluationStore(Path(tmpdir) / "runs.sqlite")
            prompt = load_test_prompt(tmpdir)
            result = run_evaluation_loop(
                "mock_marketplace",
                metric,
                prompt,
                store,
                services=services,
                human_feedback="Keep the tone measured.",
                max_feedback_iterations=3,
            )
        self.assertEqual(result.stopped_reason, "score_declined")
        self.assertEqual(len(result.runs), 2)
        self.assertEqual(len(result.feedback_runs), 1)


if __name__ == "__main__":
    unittest.main()
