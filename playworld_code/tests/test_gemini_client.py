from __future__ import annotations

import unittest

from playworldbench.gemini_client import load_gateway_headers


class GeminiClientConfigTest(unittest.TestCase):
    def test_gateway_headers_are_strings(self):
        self.assertEqual(
            load_gateway_headers('{"x-api-key":"secret","x-user-key":"user"}'),
            {"x-api-key": "secret", "x-user-key": "user"},
        )

    def test_gateway_headers_reject_non_string_values(self):
        with self.assertRaises(ValueError):
            load_gateway_headers('{"x-api-key":123}')


if __name__ == "__main__":
    unittest.main()
