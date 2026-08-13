import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from Agent_player.agent_ablation import (
    AgentConfig,
    align_action_sources,
    build_agent_only_messages,
    observation_package,
    parse_agent_decision,
    transport_request,
    extract_response_text,
)


class AgentAblationTest(unittest.TestCase):
    def test_agent_only_package_and_prompt_do_not_contain_base_sequence(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            image_path = Path(temp_dir) / "observation.jpg"
            Image.new("RGB", (4, 4), (10, 20, 30)).save(image_path)
            package = observation_package(
                "reach the doorway",
                image_path,
                image_path,
                ["hold(w,650ms)"],
            )
            messages = build_agent_only_messages(package, 3)
        self.assertEqual(
            set(package),
            {"objective", "initial_observation", "latest_observation", "executed_actions"},
        )
        serialized = json.dumps(messages)
        self.assertNotIn("SECRET_BASE_SEQUENCE_RIGHT_RIGHT_W", serialized)
        for forbidden in ("upcoming_dataset_actions", "remaining_phase_actions", "phase_step"):
            self.assertNotIn(forbidden, serialized)

    def test_restricted_dsl(self):
        decision = parse_agent_decision(
            '{"status":"continue","actions":["hold(w,650ms)","wait(200ms)"],"reason":"go"}'
        )
        self.assertEqual(decision["actions"][0]["hold_ms"], 650)
        with self.assertRaises(ValueError):
            parse_agent_decision('{"status":"continue","actions":["click(10,20)"]}')

    def test_action_source_alignment(self):
        base = [
            {"type": "key", "keys": ["w"], "hold_ms": 650},
            {"type": "key", "keys": ["a"], "hold_ms": 650},
        ]
        executed = [
            {"type": "key", "keys": ["w"], "hold_ms": 650},
            {"type": "key", "keys": ["d"], "hold_ms": 650},
            {"type": "key", "keys": ["a"], "hold_ms": 650},
        ]
        records, deleted = align_action_sources(base, executed, "preset_agent")
        self.assertEqual([item["source"] for item in records], ["retained", "inserted", "retained"])
        self.assertEqual(deleted, [])

    def test_anthropic_transport_preserves_prompt_and_image(self):
        payload = {
            "model": "deployment-id",
            "max_completion_tokens": 120,
            "messages": [
                {"role": "system", "content": "same policy"},
                {"role": "user", "content": [
                    {"type": "text", "text": "same observation package"},
                    {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,YWJj"}},
                ]},
            ],
        }
        config = AgentConfig(
            "claude", "deployment-id", "https://example.test/v1/messages", {}, "anthropic"
        )
        url, translated = transport_request(config, payload)
        self.assertEqual(url, config.base_url)
        self.assertEqual(translated["system"], "same policy")
        self.assertEqual(translated["max_tokens"], 120)
        self.assertEqual(translated["messages"][0]["content"][0]["text"], "same observation package")
        self.assertEqual(translated["messages"][0]["content"][1]["source"]["data"], "YWJj")

    def test_provider_does_not_change_observation_messages(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            image_path = Path(temp_dir) / "observation.jpg"
            Image.new("RGB", (4, 4), (10, 20, 30)).save(image_path)
            package = observation_package("reach the doorway", image_path, image_path, ["hold(w,650ms)"])
            claude_messages = build_agent_only_messages(package, 3)
            gemini_messages = build_agent_only_messages(package, 3)
        self.assertEqual(claude_messages, gemini_messages)

    def test_gemini_generate_content_transport_preserves_prompt_and_image(self):
        payload = {
            "model": "gemini-3.1-pro-preview",
            "max_completion_tokens": 120,
            "messages": [
                {"role": "system", "content": "same policy"},
                {"role": "user", "content": [
                    {"type": "text", "text": "same observation package"},
                    {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,YWJj"}},
                ]},
            ],
        }
        config = AgentConfig(
            "gemini", "gemini-3.1-pro-preview", "https://example.test:generateContent", {},
            "gemini_generate_content",
        )
        url, translated = transport_request(config, payload)
        self.assertEqual(url, config.base_url)
        self.assertEqual(translated["systemInstruction"]["parts"][0]["text"], "same policy")
        self.assertEqual(translated["contents"][0]["parts"][0]["text"], "same observation package")
        self.assertEqual(translated["contents"][0]["parts"][1]["inlineData"]["data"], "YWJj")
        self.assertEqual(translated["generationConfig"]["maxOutputTokens"], 120)
        self.assertEqual(
            extract_response_text({"candidates": [{"content": {"parts": [{"text": "OK"}]}}]}),
            "OK",
        )


if __name__ == "__main__":
    unittest.main()
