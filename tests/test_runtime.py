from __future__ import annotations

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


if __name__ == "__main__":
    unittest.main()
