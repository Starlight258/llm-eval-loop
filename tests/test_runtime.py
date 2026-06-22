from __future__ import annotations

import unittest

from core.runtime import RuntimeConfig


class RuntimeTests(unittest.TestCase):
    def test_normalized_backend_rejects_unknown_value(self) -> None:
        config = RuntimeConfig(backend="something-else")
        self.assertEqual(config.normalized_backend(), "auto")


if __name__ == "__main__":
    unittest.main()
