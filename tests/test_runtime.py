from __future__ import annotations

import os
import tempfile
from pathlib import Path
import unittest

from core.runtime import RuntimeConfig, build_services


class RuntimeTests(unittest.TestCase):
    def test_normalized_backend_rejects_unknown_value(self) -> None:
        config = RuntimeConfig(backend="something-else")
        with self.assertRaises(ValueError):
            config.normalized_backend()

    def test_normalized_backend_accepts_claude(self) -> None:
        config = RuntimeConfig(backend="claude", anthropic_api_key="test-key")
        self.assertEqual(config.normalized_backend(), "claude")

    def test_build_services_supports_claude(self) -> None:
        config = RuntimeConfig(backend="claude", anthropic_api_key="test-key", anthropic_model="claude-test")
        services = build_services(config)
        self.assertEqual(services.backend_label, "claude:claude-test")

    def test_from_env_reads_dotenv_and_defaults_blank_backend_to_ollama(self) -> None:
        original_env = {key: os.environ.get(key) for key in [
            "EVAL_ENV_FILE",
            "EVAL_LOOP_BACKEND",
            "OLLAMA_MODEL",
            "ANTHROPIC_API_KEY",
        ]}
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                env_path = Path(tmpdir) / ".env"
                env_path.write_text(
                    "EVAL_LOOP_BACKEND=\n"
                    "OLLAMA_MODEL=from-dotenv\n"
                    "ANTHROPIC_API_KEY=from-dotenv-key\n"
                )
                os.environ["EVAL_ENV_FILE"] = str(env_path)
                os.environ.pop("EVAL_LOOP_BACKEND", None)
                os.environ.pop("OLLAMA_MODEL", None)
                os.environ.pop("ANTHROPIC_API_KEY", None)
                config = RuntimeConfig.from_env()
                self.assertEqual(config.backend, "auto")
                self.assertEqual(config.model_name, "from-dotenv")
                self.assertEqual(config.anthropic_api_key, "from-dotenv-key")
        finally:
            for key, value in original_env.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value


if __name__ == "__main__":
    unittest.main()
