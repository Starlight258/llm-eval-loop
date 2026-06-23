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
        metric = MockMetricData(**json.loads((BASE_DIR / "data/mock_signup_funnel.json").read_text()))
        with tempfile.TemporaryDirectory() as tmpdir:
            prompt_path = Path(tmpdir) / "generator_v1.yaml"
            prompt_path.write_text(PROMPT_TEXT)
            prompt = load_prompt_document(prompt_path)
        report = ReportGenerator().generate(metric, prompt)
        result = EvaluationAgent().evaluate(metric, report)
        self.assertGreaterEqual(result.overall_score, 1.0)
        self.assertLessEqual(result.overall_score, 5.0)
        self.assertTrue(result.failed_sentences)


if __name__ == "__main__":
    unittest.main()
