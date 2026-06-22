from __future__ import annotations

import json
from pathlib import Path
import unittest

from core.evaluation_agent import EvaluationAgent
from core.generator import ReportGenerator
from core.prompt_loader import load_prompt_document
from core.schemas import MockMetricData


BASE_DIR = Path(__file__).resolve().parents[1]


class EvaluationAgentTests(unittest.TestCase):
    def test_scores_are_bounded(self) -> None:
        metric = MockMetricData(**json.loads((BASE_DIR / "data/mock_signup_funnel.json").read_text()))
        prompt = load_prompt_document(BASE_DIR / "prompts/generator_v1.yaml")
        report = ReportGenerator().generate(metric, prompt)
        result = EvaluationAgent().evaluate(metric, report)
        self.assertGreaterEqual(result.overall_score, 1.0)
        self.assertLessEqual(result.overall_score, 5.0)
        self.assertTrue(result.failed_sentences)


if __name__ == "__main__":
    unittest.main()

