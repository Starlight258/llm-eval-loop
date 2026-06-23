from __future__ import annotations

from unittest.mock import patch
import unittest

from core.llm_client import AnthropicClient


class LlmClientTests(unittest.TestCase):
    def test_anthropic_connection_error_includes_reason(self) -> None:
        client = AnthropicClient(api_key="test-key", model_name="claude-test", base_url="https://api.anthropic.com")
        fake_client = type(
            "FakeAnthropicClient",
            (),
            {
                "messages": type(
                    "Messages",
                    (),
                    {
                        "create": staticmethod(lambda **kwargs: (_ for _ in ()).throw(RuntimeError("network unreachable"))),
                    },
                )(),
            },
        )()
        with patch.object(AnthropicClient, "_create_client", return_value=fake_client):
            with self.assertRaises(ConnectionError) as ctx:
                client.chat_with_usage(system="system", user="user")
        self.assertIn("failed to reach Anthropic API at https://api.anthropic.com", str(ctx.exception))
        self.assertIn("network unreachable", str(ctx.exception))

    def test_anthropic_payload_omits_temperature(self) -> None:
        client = AnthropicClient(api_key="test-key", model_name="claude-opus-4-8")
        captured_payloads: list[dict[str, object]] = []

        class FakeMessages:
            def create(self, **kwargs):
                captured_payloads.append(kwargs)
                return type(
                    "Response",
                    (),
                    {
                        "content": [type("Block", (), {"text": "Hello!"})()],
                        "usage": type("Usage", (), {"input_tokens": 1, "output_tokens": 1})(),
                    },
                )()

        def fake_create_client(self):
            return type("FakeAnthropicClient", (), {"messages": FakeMessages()})()

        with patch.object(AnthropicClient, "_create_client", fake_create_client):
            result = client.chat_with_usage(system="system", user="user")
        self.assertEqual(result.content, "Hello!")
        self.assertEqual(captured_payloads[0]["model"], "claude-opus-4-8")
        self.assertNotIn("temperature", captured_payloads[0])

    def test_anthropic_payload_includes_temperature_for_supported_models(self) -> None:
        client = AnthropicClient(api_key="test-key", model_name="claude-3-opus-20240229", temperature=0.0)
        captured_payloads: list[dict[str, object]] = []

        class FakeMessages:
            def create(self, **kwargs):
                captured_payloads.append(kwargs)
                return type(
                    "Response",
                    (),
                    {
                        "content": [type("Block", (), {"text": "Hello!"})()],
                        "usage": type("Usage", (), {"input_tokens": 1, "output_tokens": 1})(),
                    },
                )()

        def fake_create_client(self):
            return type("FakeAnthropicClient", (), {"messages": FakeMessages()})()

        with patch.object(AnthropicClient, "_create_client", fake_create_client):
            result = client.chat_with_usage(system="system", user="user")
        self.assertEqual(result.content, "Hello!")
        self.assertEqual(captured_payloads[0]["temperature"], 0.0)


if __name__ == "__main__":
    unittest.main()
