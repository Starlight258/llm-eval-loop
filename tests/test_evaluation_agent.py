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


if __name__ == "__main__":
    unittest.main()
