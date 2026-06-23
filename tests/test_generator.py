from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

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


def load_test_prompt(tmpdir: str):
    path = Path(tmpdir) / "generator_v1.yaml"
    path.write_text(PROMPT_TEXT)
    return load_prompt_document(path)


class GeneratorTests(unittest.TestCase):
    def test_generator_uses_source_values(self) -> None:
        metric = MockMetricData(**json.loads((BASE_DIR / "data/mock_marketplace.json").read_text()))
        with tempfile.TemporaryDirectory() as tmpdir:
            prompt = load_test_prompt(tmpdir)
        report = ReportGenerator().generate(metric, prompt)
        self.assertIn("listing_count Report", report)
        self.assertIn("572,000", report)
        self.assertIn("-2.0%", report)

    def test_generator_falls_back_when_llm_reverses_direction(self) -> None:
        class FakeClient:
            def chat(self, *, system: str, user: str) -> str:
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
                    "The metric increased week over week and the trend is clear.\n\n"
                    "## Breakdown\n"
                    "- No breakdowns were included in this run.\n\n"
                    "## Watchouts\n"
                    "- Keep watching the trend."
                )

        metric = MockMetricData(**json.loads((BASE_DIR / "data/mock_marketplace.json").read_text()))
        with tempfile.TemporaryDirectory() as tmpdir:
            prompt = load_test_prompt(tmpdir)
        report = ReportGenerator(llm_client=FakeClient()).generate(metric, prompt)
        self.assertIn("decreased week over week", report)
        self.assertNotIn("increased week over week", report)
        self.assertIn("572,000", report)
        self.assertIn("-2.0%", report)


if __name__ == "__main__":
    unittest.main()
