from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from core.loop import run_evaluation_loop
from core.prompt_loader import load_prompt_document
from core.schemas import MockMetricData
from storage.db import EvaluationStore


BASE_DIR = Path(__file__).resolve().parents[1]


class PromptOptimizerTests(unittest.TestCase):
    def test_loop_persists_prompt_history_and_stops(self) -> None:
        metric = MockMetricData(**json.loads((BASE_DIR / "data/mock_marketplace.json").read_text()))
        prompt = load_prompt_document(BASE_DIR / "prompts/generator_v1.yaml")
        with tempfile.TemporaryDirectory() as tmpdir:
            store = EvaluationStore(Path(tmpdir) / "runs.sqlite")
            result = run_evaluation_loop("mock_marketplace", metric, prompt, store)
            self.assertGreaterEqual(len(result.runs), 1)
            self.assertGreaterEqual(len(result.prompt_history), 1)
            self.assertIn(result.stopped_reason, {"max_iterations_reached", "score_declined"})
            self.assertTrue(store.list_runs())
            self.assertTrue(store.list_prompt_versions())


if __name__ == "__main__":
    unittest.main()

