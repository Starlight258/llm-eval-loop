from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from core.generator import ReportGenerator
from core.llm_client import AnthropicChatResult, AnthropicUsage
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
    def test_generator_returns_model_output_without_canonical_override(self) -> None:
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
        self.assertIn("# listing_count Report", report)
        self.assertIn("572,000", report)
        self.assertIn("583,000", report)
        self.assertNotIn("Marketplace Listing Count Report", report)

    def test_generator_ignores_optional_human_feedback_in_prompt(self) -> None:
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
        self.assertNotIn("Human feedback for this draft", client.last_user)
        self.assertNotIn("Tone down the certainty", client.last_user)

    def test_generator_preserves_anthropic_usage(self) -> None:
        class FakeClient:
            def chat_with_usage(self, *, system: str, user: str):
                return AnthropicChatResult(
                    content=(
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
                    ),
                    usage=AnthropicUsage(prompt_tokens=12, completion_tokens=34),
                )

        metric = MockMetricData(**json.loads((BASE_DIR / "data/mock_engagement.json").read_text()))
        with tempfile.TemporaryDirectory() as tmpdir:
            prompt = load_test_prompt(tmpdir)
        generator = ReportGenerator(llm_client=FakeClient())
        report = generator.generate(metric, prompt)
        self.assertIn("1,845,000", report)
        self.assertIsNotNone(generator.last_usage)
        self.assertEqual(generator.last_usage.prompt_tokens, 12)
        self.assertEqual(generator.last_usage.completion_tokens, 34)


if __name__ == "__main__":
    unittest.main()
