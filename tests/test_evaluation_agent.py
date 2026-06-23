from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from core.evaluation_agent import EvaluationAgent
from core.generator import ReportGenerator
from core.prompt_loader import load_prompt_document
from core.schemas import MockMetricData


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


class EvaluationAgentTests(unittest.TestCase):
    def test_scores_are_bounded(self) -> None:
        class FakeGenClient:
            def chat(self, *, system: str, user: str) -> str:
                return (
                    "# signup_funnel Report\n\n"
                    "## Snapshot\n"
                    "- Domain: Signup Funnel\n"
                    "- Current: 31.4\n"
                    "- Previous: 32.1\n"
                    "- DoD: -0.7%\n"
                    "- WoW: -1.9%\n"
                    "- 4W average: 33.2\n\n"
                    "## Interpretation\n"
                    "The metric decreased week over week.\n\n"
                    "## Breakdown\n"
                    "- step: email_verification -0.5%, profile_setup -0.9%, first_session -1.4%\n\n"
                    "## Watchouts\n"
                    "- Keep monitoring."
                )

        class FakeJudgeClient:
            def chat(self, *, system: str, user: str) -> str:
                return json.dumps(
                    {
                        "groundedness_score": 4.5,
                        "appropriateness_score": 4.2,
                        "calibration_score": 4.0,
                        "consistency_score": 4.4,
                        "readability_score": 4.8,
                        "failed_sentences": ["The conclusion is slightly verbose."],
                        "judge_feedback": "ok",
                        "improvement_suggestions": ["tighten wording"],
                    }
                )

        metric = MockMetricData(**json.loads((BASE_DIR / "data/mock_signup_funnel.json").read_text()))
        with tempfile.TemporaryDirectory() as tmpdir:
            prompt_path = Path(tmpdir) / "generator_v1.yaml"
            prompt_path.write_text(PROMPT_TEXT)
            prompt = load_prompt_document(prompt_path)
        report = ReportGenerator(llm_client=FakeGenClient()).generate(metric, prompt)
        result = EvaluationAgent(llm_client=FakeJudgeClient()).evaluate(metric, report)
        self.assertGreaterEqual(result.overall_score, 1.0)
        self.assertLessEqual(result.overall_score, 5.0)
        self.assertTrue(result.failed_sentences)

    def test_numeric_change_mismatch_penalizes_groundedness(self) -> None:
        class FakeGenClient:
            def chat(self, *, system: str, user: str) -> str:
                return (
                    "# app_engagement Report\n\n"
                    "## Snapshot\n"
                    "- Domain: App Engagement\n"
                    "- Current: 1,845,000\n"
                    "- Previous: 1,812,000\n"
                    "- DoD: +1.8%\n"
                    "- WoW: +4.9%\n"
                    "- 4W average: 1,760,000\n\n"
                    "## Interpretation\n"
                    "The daily active user count has increased by 1,845,000, up from 1,812,000.\n\n"
                    "## Breakdown\n"
                    "- platform: Android +2.2%, iOS +1.4%, Web +0.9%\n\n"
                    "## Watchouts\n"
                    "- Keep monitoring."
                )

        class FakeJudgeClient:
            def chat(self, *, system: str, user: str) -> str:
                return json.dumps(
                    {
                        "groundedness_score": 4.8,
                        "appropriateness_score": 4.8,
                        "calibration_score": 4.8,
                        "consistency_score": 4.8,
                        "readability_score": 4.8,
                        "failed_sentences": [],
                        "judge_feedback": "ok",
                        "improvement_suggestions": [],
                    }
                )

        metric = MockMetricData(**json.loads((BASE_DIR / "data/mock_engagement.json").read_text()))
        report = (
            "# App Engagement Daily Active Users Report\n\n"
            "## Snapshot\n"
            "- Domain: App Engagement\n"
            "- Current: 1,845,000\n"
            "- Previous: 1,812,000\n"
            "- DoD: +1.8%\n"
            "- WoW: +4.9%\n"
            "- 4W Average: 1,760,000\n\n"
            "## Interpretation\n"
            "The daily active user count has increased by 1,845,000.\n\n"
            "## Breakdown\n"
            "- platform: Android +2.2%, iOS +1.4%, Web +0.9%\n\n"
            "## Watchouts\n"
            "- Keep monitoring."
        )
        result = EvaluationAgent(llm_client=FakeJudgeClient()).evaluate(metric, report)
        self.assertLess(result.scores.groundedness_score, 4.5)
        self.assertTrue(any("Numeric change mismatch" in sentence for sentence in result.failed_sentences))

    def test_malformed_json_is_repaired_once(self) -> None:
        class FakeGenClient:
            def chat(self, *, system: str, user: str) -> str:
                return (
                    "# signup_funnel Report\n\n"
                    "## Snapshot\n"
                    "- Domain: Signup Funnel\n"
                    "- Current: 31.4\n"
                    "- Previous: 32.1\n"
                    "- DoD: -0.7%\n"
                    "- WoW: -1.9%\n"
                    "- 4W average: 33.2\n\n"
                    "## Interpretation\n"
                    "The metric decreased week over week.\n\n"
                    "## Breakdown\n"
                    "- step: email_verification -0.5%, profile_setup -0.9%, first_session -1.4%\n\n"
                    "## Watchouts\n"
                    "- Keep monitoring."
                )

        class RepairingJudgeClient:
            def __init__(self) -> None:
                self.calls = 0

            def chat(self, *, system: str, user: str) -> str:
                self.calls += 1
                if self.calls == 1:
                    return (
                        "{\n"
                        '  "groundedness_score": 4.5,\n'
                        '  "appropriateness_score": 4.2,\n'
                        '  "calibration_score": 4.0,\n'
                        '  "consistency_score": 4.4,\n'
                        '  "readability_score": 4.8,\n'
                        '  "failed_sentences": ["The conclusion is slightly verbose."],\n'
                        '  "judge_feedback": "ok"\n'
                        '  "improvement_suggestions": ["tighten wording"]\n'
                        "}"
                    )
                return json.dumps(
                    {
                        "groundedness_score": 4.5,
                        "appropriateness_score": 4.2,
                        "calibration_score": 4.0,
                        "consistency_score": 4.4,
                        "readability_score": 4.8,
                        "failed_sentences": ["The conclusion is slightly verbose."],
                        "judge_feedback": "ok",
                        "improvement_suggestions": ["tighten wording"],
                    }
                )

        metric = MockMetricData(**json.loads((BASE_DIR / "data/mock_signup_funnel.json").read_text()))
        with tempfile.TemporaryDirectory() as tmpdir:
            prompt_path = Path(tmpdir) / "generator_v1.yaml"
            prompt_path.write_text(PROMPT_TEXT)
            prompt = load_prompt_document(prompt_path)
        report = ReportGenerator(llm_client=FakeGenClient()).generate(metric, prompt)
        judge = RepairingJudgeClient()
        result = EvaluationAgent(llm_client=judge).evaluate(metric, report)
        self.assertEqual(judge.calls, 2)
        self.assertGreaterEqual(result.overall_score, 1.0)
        self.assertLessEqual(result.overall_score, 5.0)

    def test_snapshot_value_mismatch_penalizes_groundedness(self) -> None:
        class FakeGenClient:
            def chat(self, *, system: str, user: str) -> str:
                return (
                    "# app_engagement Report\n\n"
                    "## Snapshot\n"
                    "- Domain: App Engagement\n"
                    "- Current: 184,500 users\n"
                    "- Previous: 181,200 users\n"
                    "- DoD: +1.8%\n"
                    "- WoW: +4.9%\n"
                    "- 4W average: 176,000 users\n\n"
                    "## Interpretation\n"
                    "The daily active user count has increased by 33,000, and the trend is positive.\n\n"
                    "## Breakdown\n"
                    "- platform: Android +2.2%, iOS +1.4%, Web +0.9%\n\n"
                    "## Watchouts\n"
                    "- Keep monitoring."
                )

        class FakeJudgeClient:
            def chat(self, *, system: str, user: str) -> str:
                return json.dumps(
                    {
                        "groundedness_score": 4.9,
                        "appropriateness_score": 4.8,
                        "calibration_score": 4.8,
                        "consistency_score": 4.8,
                        "readability_score": 4.8,
                        "failed_sentences": [],
                        "judge_feedback": "ok",
                        "improvement_suggestions": [],
                    }
                )

        metric = MockMetricData(**json.loads((BASE_DIR / "data/mock_engagement.json").read_text()))
        report = (
            "# App Engagement Daily Active Users Report\n\n"
            "## Snapshot\n"
            "- Domain: App Engagement\n"
            "- Current: 184,500 users\n"
            "- Previous: 181,200 users\n"
            "- DoD: +1.8%\n"
            "- WoW: +4.9%\n"
            "- 4W Average: 176,000 users\n\n"
            "## Interpretation\n"
            "The daily active user count has increased by 33,000.\n\n"
            "## Breakdown\n"
            "- platform: Android +2.2%, iOS +1.4%, Web +0.9%\n\n"
            "## Watchouts\n"
            "- Keep monitoring."
        )
        result = EvaluationAgent(llm_client=FakeJudgeClient()).evaluate(metric, report)
        self.assertLess(result.scores.groundedness_score, 4.5)
        self.assertTrue(any("Snapshot value mismatch" in sentence for sentence in result.failed_sentences))


if __name__ == "__main__":
    unittest.main()
