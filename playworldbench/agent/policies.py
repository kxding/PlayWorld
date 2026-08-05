"""Pluggable keep, scripted, and Gemini visual-agent policies."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from .actions import ControlDecision, ControlOperation, WorldAction
from .base import Observation
from playworldbench.gemini_client import create_gemini_client


ALLOWED_KEYS = frozenset(
    {"W", "A", "S", "D", "WAIT", "ARROWUP", "ARROWDOWN", "ARROWLEFT", "ARROWRIGHT"}
)


def decision_from_dict(value: dict[str, Any]) -> ControlDecision:
    try:
        operation = ControlOperation(str(value["operation"]).lower())
    except (KeyError, ValueError) as error:
        raise ValueError(f"Invalid control operation: {value}") from error

    corrected = None
    if operation is ControlOperation.CORRECT_ACTION:
        raw = value.get("corrected_action")
        if not isinstance(raw, dict):
            raise ValueError("correct_action requires a corrected_action object")
        key = str(raw.get("key", "")).upper()
        if key not in ALLOWED_KEYS:
            raise ValueError(f"Unsupported corrected key: {key}")
        corrected = WorldAction(key=key, duration_ms=int(raw["duration_ms"]))

    return ControlDecision(
        operation=operation,
        reason=str(value.get("reason", "")),
        extension_ms=int(value.get("extension_ms", 0) or 0),
        corrected_action=corrected,
    )


class KeepAllPolicy:
    def __call__(
        self, _: Observation, __: WorldAction, ___: int
    ) -> ControlDecision:
        return ControlDecision(ControlOperation.KEEP_ACTION, reason="use benchmark plan")


class ScriptedPolicy:
    """Read decisions by zero-based action index; unspecified steps use keep_action."""

    def __init__(self, decisions: dict[int, ControlDecision]):
        self.decisions = decisions

    @classmethod
    def from_json(cls, path: Path) -> "ScriptedPolicy":
        raw = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(raw, list):
            decisions = {index: decision_from_dict(item) for index, item in enumerate(raw)}
        elif isinstance(raw, dict):
            decisions = {int(index): decision_from_dict(item) for index, item in raw.items()}
        else:
            raise ValueError("Decision file must contain a list or index-to-decision object")
        return cls(decisions)

    def __call__(
        self, _: Observation, __: WorldAction, index: int
    ) -> ControlDecision:
        return self.decisions.get(
            index,
            ControlDecision(ControlOperation.KEEP_ACTION, reason="no scripted override"),
        )


class GeminiPolicy:
    def __init__(
        self,
        task_prompt: str,
        *,
        model: str = "gemini-3.1-pro-preview",
        api_key: str | None = None,
        max_extension_ms: int = 5000,
        task_context: dict[str, Any] | None = None,
    ):
        self.client = create_gemini_client(api_key=api_key)
        self.task_prompt = task_prompt
        self.model = model
        self.max_extension_ms = max_extension_ms
        self.task_context = task_context or {}
        self.last_trace: dict[str, Any] | None = None

    def __call__(
        self, observation: Observation, planned: WorldAction, index: int
    ) -> ControlDecision:
        from google.genai import types

        remaining = self.task_context.get("action_sequence_steps", [])[index + 1 :]
        prompt = f"""You control an interactive world one action at a time.
Scene: {self.task_context.get('image_caption', 'not provided')}
Perspective: {self.task_context.get('perspective', 'not provided')}
Long-horizon objective: {self.task_prompt}
Current zero-based action index: {index}
Planned action: key={planned.key}, duration_ms={planned.duration_ms}
Remaining base actions: {json.dumps(remaining, ensure_ascii=False)}
Screenshot timestamp: {observation.timestamp}

Inspect the current screenshot and choose exactly one operation:
- keep_action: execute the planned action unchanged.
- stop_action: the task is complete, unsafe, or cannot benefit from another action.
- extend_action: keep the same key but add extension_ms (1-{self.max_extension_ms}).
- correct_action: replace it with corrected_action using key W/A/S/D, WAIT, or an arrow key and a positive duration_ms.

Return JSON only:
{{"operation":"keep_action|stop_action|extend_action|correct_action","reason":"brief visual reason","extension_ms":0,"corrected_action":null}}
"""
        started = time.monotonic()
        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=types.Content(
                    role="user",
                    parts=[
                        types.Part.from_bytes(
                            data=observation.screenshot, mime_type="image/jpeg"
                        ),
                        types.Part.from_text(text=prompt),
                    ],
                ),
                config=types.GenerateContentConfig(
                    response_mime_type="application/json", temperature=0.0
                ),
            )
        except Exception as error:
            self.last_trace = {
                "model": self.model,
                "prompt": prompt,
                "latency_seconds": time.monotonic() - started,
                "error": f"{type(error).__name__}: {error}",
            }
            raise
        text = response.text.strip()
        self.last_trace = {
            "model": self.model,
            "prompt": prompt,
            "raw_response": response.text,
            "latency_seconds": time.monotonic() - started,
        }
        if text.startswith("```"):
            text = text.split("\n", 1)[1].rsplit("```", 1)[0]
        decision = decision_from_dict(json.loads(text))
        if (
            decision.operation is ControlOperation.EXTEND_ACTION
            and decision.extension_ms > self.max_extension_ms
        ):
            raise ValueError(
                f"extension_ms exceeds maximum {self.max_extension_ms}: "
                f"{decision.extension_ms}"
            )
        return decision
