from __future__ import annotations

import json
from pathlib import Path
import unittest

from core.generator import ReportGenerator
from core.prompt_loader import load_prompt_document
from core.schemas import MockMetricData


BASE_DIR = Path(__file__).resolve().parents[1]


class GeneratorTests(unittest.TestCase):
    def test_generator_uses_source_values(self) -> None:
        metric = MockMetricData(**json.loads((BASE_DIR / "data/mock_marketplace.json").read_text()))
        prompt = load_prompt_document(BASE_DIR / "prompts/generator_v1.yaml")
        report = ReportGenerator().generate(metric, prompt)
        self.assertIn("listing_count Report", report)
        self.assertIn("572,000", report)
        self.assertIn("-2.0%", report)


if __name__ == "__main__":
    unittest.main()

