from __future__ import annotations

from urllib.error import URLError
from unittest.mock import patch
import unittest

from core.llm_client import AnthropicClient


class LlmClientTests(unittest.TestCase):
    def test_anthropic_connection_error_includes_reason(self) -> None:
        client = AnthropicClient(api_key="test-key", model_name="claude-test", base_url="https://api.anthropic.com")
        with patch("core.llm_client.urlopen", side_effect=URLError("network unreachable")):
            with self.assertRaises(ConnectionError) as ctx:
                client.chat_with_usage(system="system", user="user")
        self.assertIn("failed to reach Anthropic API at https://api.anthropic.com", str(ctx.exception))
        self.assertIn("network unreachable", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
