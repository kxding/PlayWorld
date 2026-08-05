"""Action and agent-decision types shared by every world engine."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum


ACTION_PATTERN = re.compile(r"hold\((?P<key>[^,]+),(?P<duration>\d+)ms\)", re.I)
WAIT_PATTERN = re.compile(r"wait\((?P<duration>\d+)ms\)", re.I)


@dataclass(frozen=True)
class WorldAction:
    key: str
    duration_ms: int

    def __post_init__(self) -> None:
        if not self.key.strip():
            raise ValueError("Action key cannot be empty")
        if self.duration_ms <= 0:
            raise ValueError("Action duration must be positive")


class ControlOperation(str, Enum):
    KEEP_ACTION = "keep_action"
    STOP_ACTION = "stop_action"
    EXTEND_ACTION = "extend_action"
    CORRECT_ACTION = "correct_action"


@dataclass(frozen=True)
class ControlDecision:
    operation: ControlOperation
    reason: str = ""
    extension_ms: int = 0
    corrected_action: WorldAction | None = None

    def __post_init__(self) -> None:
        if self.operation is ControlOperation.EXTEND_ACTION and self.extension_ms <= 0:
            raise ValueError("extend_action requires extension_ms > 0")
        if self.operation is ControlOperation.CORRECT_ACTION and self.corrected_action is None:
            raise ValueError("correct_action requires corrected_action")


def parse_action_sequence(value: str | list[str]) -> list[WorldAction]:
    chunks = value if isinstance(value, list) else value.split(";")
    actions: list[WorldAction] = []
    for chunk in chunks:
        expression = chunk.strip()
        wait_match = WAIT_PATTERN.fullmatch(expression)
        if wait_match:
            actions.append(
                WorldAction(key="WAIT", duration_ms=int(wait_match.group("duration")))
            )
            continue
        match = ACTION_PATTERN.fullmatch(expression)
        if not match:
            raise ValueError(f"Unsupported action expression: {chunk!r}")
        actions.append(
            WorldAction(
                key=match.group("key").strip().upper(),
                duration_ms=int(match.group("duration")),
            )
        )
    return actions
