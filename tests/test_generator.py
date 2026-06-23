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
                    "The metric decreased week over week and the trend is downward.\n\n"
                    "## Breakdown\n"
                    "- category: books -1.2%, electronics -2.4%\n\n"
                    "## Watchouts\n"
                    "- The movement is directional."
                )

        metric = MockMetricData(**json.loads((BASE_DIR / "data/mock_marketplace.json").read_text()))
        with tempfile.TemporaryDirectory() as tmpdir:
            prompt = load_test_prompt(tmpdir)
        report = ReportGenerator(llm_client=FakeClient()).generate(metric, prompt)
        self.assertIn("Marketplace Listing Count Report", report)
        self.assertIn("572,000", report)
        self.assertIn("584,000", report)
        self.assertIn("-5.2%", report)

    def test_generator_canonicalizes_mismatched_numbers(self) -> None:
        class FakeClient:
            def chat(self, *, system: str, user: str) -> str:
                return (
                    "# App Engagement Daily Active Users Report\n\n"
                    "## Snapshot\n"
                    "- Domain: App Engagement\n"
                    "- Current: 184,500 users\n"
                    "- Previous: 181,200 users\n"
                    "- DoD: +1.8%\n"
                    "- WoW: +4.9%\n"
                    "- 4W Average: 176,000 users\n\n"
                    "## Interpretation\n"
                    "The daily active user count has increased by 3,300 (+1.8%).\n\n"
                    "## Breakdown\n"
                    "- Platform: Android +2.2%, iOS +1.4%, Web +0.9%\n\n"
                    "## Watchouts\n"
                    "- Keep monitoring."
                )

        metric = MockMetricData(**json.loads((BASE_DIR / "data/mock_engagement.json").read_text()))
        with tempfile.TemporaryDirectory() as tmpdir:
            prompt = load_test_prompt(tmpdir)
        report = ReportGenerator(llm_client=FakeClient()).generate(metric, prompt)
        self.assertIn("1,845,000", report)
        self.assertIn("1,812,000", report)
        self.assertIn("33,000", report)
        self.assertNotIn("184,500", report)

    def test_generator_includes_optional_human_feedback_in_prompt(self) -> None:
        class FakeClient:
            def __init__(self) -> None:
                self.last_user = ""

            def chat(self, *, system: str, user: str) -> str:
                self.last_user = user
                return (
                    "# App Engagement Daily Active Users Report\n\n"
                    "## Snapshot\n"
                    "- Domain: App Engagement\n"
                    "- Current: 1,845,000 users\n"
                    "- Previous: 1,812,000 users\n"
                    "- DoD: +1.8%\n"
                    "- WoW: +4.9%\n"
                    "- 4W Average: 1,760,000 users\n\n"
                    "## Interpretation\n"
                    "The daily active user count has increased by 33,000.\n\n"
                    "## Breakdown\n"
                    "- platform: Android +2.2%, iOS +1.4%, Web +0.9%\n\n"
                    "## Watchouts\n"
                    "- Keep monitoring."
                )

        metric = MockMetricData(**json.loads((BASE_DIR / "data/mock_engagement.json").read_text()))
        with tempfile.TemporaryDirectory() as tmpdir:
            prompt = load_test_prompt(tmpdir)
        client = FakeClient()
        ReportGenerator(llm_client=client).generate(
            metric,
            prompt,
            human_feedback="Tone down the certainty and keep the watchouts short.",
        )
        self.assertIn("Human feedback for this draft", client.last_user)
        self.assertIn("Tone down the certainty", client.last_user)


if __name__ == "__main__":
    unittest.main()
