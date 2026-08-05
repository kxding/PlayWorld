"""Durable run artifacts for the agent harness."""

from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def json_default(value: Any) -> Any:
    if is_dataclass(value):
        return asdict(value)
    if hasattr(value, "value"):
        return value.value
    if isinstance(value, Path):
        return str(value)
    raise TypeError(f"Cannot serialize {type(value).__name__}")


class RunRecorder:
    def __init__(self, output_root: Path, task_id: str):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        self.run_dir = output_root / f"{task_id}_{timestamp}"
        self.screenshot_dir = self.run_dir / "screenshots"
        self.screenshot_dir.mkdir(parents=True, exist_ok=False)
        self.event_path = self.run_dir / "events.jsonl"

    def event(self, event_type: str, **payload: Any) -> None:
        record = {"timestamp": utc_now(), "event": event_type, **payload}
        with self.event_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False, default=json_default))
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())

    def screenshot(self, name: str, data: bytes) -> str:
        path = self.screenshot_dir / name
        path.write_bytes(data)
        return str(path.relative_to(self.run_dir))

    def write_json(self, name: str, value: Any) -> Path:
        path = self.run_dir / name
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(value, ensure_ascii=False, indent=2, default=json_default) + "\n",
            encoding="utf-8",
        )
        temporary.replace(path)
        return path

    def retry(self, operation: str, attempt: int, error: Exception) -> None:
        self.event(
            "retry",
            operation=operation,
            attempt=attempt,
            error_type=type(error).__name__,
            error=str(error),
        )


def retry_call(
    operation: str,
    function,
    *,
    attempts: int,
    delay_seconds: float,
    recorder: RunRecorder,
    recover=None,
):
    if attempts < 1:
        raise ValueError("attempts must be at least 1")
    for attempt in range(1, attempts + 1):
        try:
            return function()
        except Exception as error:
            recorder.retry(operation, attempt, error)
            if attempt == attempts:
                raise
            if recover is not None:
                recover(error, attempt)
            if delay_seconds > 0:
                time.sleep(delay_seconds)
    raise AssertionError("unreachable")
