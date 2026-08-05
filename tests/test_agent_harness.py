from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from playworldbench.agent import (
    AgentHarness,
    ControlDecision,
    ControlOperation,
    HarnessConfig,
    ScriptedPolicy,
    WorldAction,
    parse_action_sequence,
)
from playworldbench.agent.base import Observation, PlayworldEngine
from playworldbench.agent.base import PlayWorldEngine


class FakeEngine(PlayworldEngine):
    def __init__(self, *, connect_failures=0, generation_failures=0, action_failure=False):
        super().__init__("https://example.invalid")
        self.connect_failures = connect_failures
        self.generation_failures = generation_failures
        self.action_failure = action_failure
        self.connect_calls = 0
        self.generation_calls = 0
        self.recover_calls = 0
        self.perform_calls = 0
        self.executed = []
        self.connected = False

    def connect(self):
        self.connect_calls += 1
        if self.connect_calls <= self.connect_failures:
            raise RuntimeError("injected connect failure")
        self.connected = True

    def close(self):
        self.connected = False

    def recover(self):
        self.recover_calls += 1
        self.connected = True

    def release_all(self):
        pass

    def upload_and_generate(self, image: Path, prompt: str):
        self.generation_calls += 1
        if self.generation_calls <= self.generation_failures:
            raise RuntimeError("injected generation failure")

    def observe(self):
        if not self.connected:
            raise RuntimeError("not connected")
        return Observation(b"fake-jpeg", self.target_url, "fake", 0.0)

    def perform(self, action: WorldAction):
        self.perform_calls += 1
        if self.action_failure:
            raise RuntimeError("injected action failure")
        self.executed.append(action)

    def _upload_image(self, image: Path):
        pass

    def _submit_prompt(self, prompt: str):
        pass

    def _wait_until_world_ready(self):
        pass


def task() -> dict:
    return {
        "task_id": "GC001",
        "prompt": "test task",
        "action_sequence_steps": [
            "hold(W,100ms)",
            "hold(D,200ms)",
            "hold(S,300ms)",
            "hold(A,400ms)",
        ],
    }


class HarnessTest(unittest.TestCase):
    def test_public_engine_spelling_is_compatible(self):
        self.assertIs(PlayWorldEngine, PlayworldEngine)

    def config(self, **overrides):
        values = {
            "connect_attempts": 3,
            "generation_attempts": 2,
            "observation_attempts": 2,
            "policy_attempts": 2,
            "retry_delay_seconds": 0,
            "natural_end_wait_seconds": 0,
            "policy_failure_fallback": "stop",
        }
        values.update(overrides)
        return HarnessConfig(**values)

    def test_retries_screenshots_results_and_four_decisions(self):
        engine = FakeEngine(connect_failures=2, generation_failures=1)
        policy = ScriptedPolicy(
            {
                0: ControlDecision(ControlOperation.KEEP_ACTION, reason="keep"),
                1: ControlDecision(
                    ControlOperation.EXTEND_ACTION, reason="extend", extension_ms=50
                ),
                2: ControlDecision(
                    ControlOperation.CORRECT_ACTION,
                    reason="correct",
                    corrected_action=WorldAction("A", 75),
                ),
                3: ControlDecision(ControlOperation.STOP_ACTION, reason="done"),
            }
        )
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            image = root / "input.jpg"
            image.write_bytes(b"image")
            result = AgentHarness(engine, policy, root, self.config()).run_task(
                task(), image
            )
            run_dir = Path(result["run_dir"])
            self.assertEqual(result["status"], "stopped")
            self.assertEqual(engine.connect_calls, 3)
            self.assertEqual(engine.generation_calls, 2)
            self.assertEqual(engine.recover_calls, 1)
            self.assertEqual(
                engine.executed,
                [WorldAction("W", 100), WorldAction("D", 250), WorldAction("A", 75)],
            )
            self.assertTrue((run_dir / "result.json").is_file())
            self.assertTrue((run_dir / "events.jsonl").is_file())
            self.assertTrue((run_dir / "screenshots/probe.jpg").is_file())
            self.assertTrue((run_dir / "screenshots/before_actions.jpg").is_file())
            self.assertTrue((run_dir / "screenshots/after_actions.jpg").is_file())
            self.assertTrue((run_dir / "screenshots/natural_end.jpg").is_file())
            events = [
                json.loads(line)
                for line in (run_dir / "events.jsonl").read_text().splitlines()
            ]
            self.assertTrue(any(item["event"] == "retry" for item in events))
            self.assertEqual(sum(item["event"] == "decision" for item in events), 4)

    def test_policy_failure_uses_safe_stop(self):
        engine = FakeEngine()

        def failing_policy(*_):
            raise RuntimeError("agent unavailable")

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            image = root / "input.jpg"
            image.write_bytes(b"image")
            result = AgentHarness(
                engine, failing_policy, root, self.config()
            ).run_task(task(), image)
            self.assertEqual(result["status"], "stopped")
            self.assertEqual(engine.executed, [])
            self.assertIn("policy failed", result["actions"][0]["decision"].reason)

    def test_ambiguous_action_failure_is_not_retried(self):
        engine = FakeEngine(action_failure=True)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            image = root / "input.jpg"
            image.write_bytes(b"image")
            result = AgentHarness(
                engine,
                lambda *_: ControlDecision(ControlOperation.KEEP_ACTION),
                root,
                self.config(),
            ).run_task(task(), image)
            self.assertEqual(result["status"], "failed")
            self.assertEqual(engine.perform_calls, 1)
            self.assertEqual(result["actions"][0]["status"], "failed")

    def test_wait_action_is_parsed(self):
        self.assertEqual(
            parse_action_sequence(["wait(450ms)", "hold(W,100ms)"]),
            [WorldAction("WAIT", 450), WorldAction("W", 100)],
        )


if __name__ == "__main__":
    unittest.main()
