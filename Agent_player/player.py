#!/usr/bin/env python3
"""Template for adding another browser-controlled world-model player.

Copy this file or subclass :class:`Player`, then implement the model-specific
page hooks. Dataset loading, the action DSL, keyboard safety, observations, and
result recording are shared so a new adapter does not need to reinvent them.
"""

from __future__ import annotations

import json
import re
import time
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

from playwright.sync_api import Browser, BrowserContext, Page, Playwright, sync_playwright


ACTION_RE = re.compile(r"^hold\(([^,]+),(\d+)ms\)$", re.IGNORECASE)
WAIT_RE = re.compile(r"^wait\((\d+)ms\)$", re.IGNORECASE)
KEY_ALIASES = {
    "UP": "ArrowUp",
    "DOWN": "ArrowDown",
    "LEFT": "ArrowLeft",
    "RIGHT": "ArrowRight",
    "SPACE": "Space",
}


@dataclass(frozen=True)
class ActionStep:
    """One model-independent action from the benchmark action DSL."""

    keys: tuple[str, ...] = ()
    duration_ms: int = 0
    kind: str = "hold"
    raw: str = ""


@dataclass(frozen=True)
class PlayerTask:
    """Minimum task record understood by every player."""

    task_id: str
    prompt: str
    image_path: Path
    action_sequence_steps: tuple[str, ...]
    perspective: str = "unknown"
    image_caption: str = ""

    @classmethod
    def from_record(cls, record: dict[str, Any], data_root: Path) -> "PlayerTask":
        required = ("task_id", "prompt", "image_path")
        missing = [name for name in required if not record.get(name)]
        if missing:
            raise ValueError(f"Task is missing required fields: {', '.join(missing)}")
        steps = record.get("action_sequence_steps") or record.get("action_sequence") or ()
        if isinstance(steps, str):
            steps = tuple(part.strip() for part in steps.split(";") if part.strip())
        else:
            steps = tuple(str(part).strip() for part in steps if str(part).strip())
        image_path = Path(record["image_path"])
        if not image_path.is_absolute():
            image_path = data_root / image_path
        return cls(
            task_id=str(record["task_id"]),
            prompt=str(record["prompt"]),
            image_path=image_path,
            action_sequence_steps=steps,
            perspective=str(record.get("perspective") or "unknown"),
            image_caption=str(record.get("image_caption") or ""),
        )


def parse_action_step(value: str) -> ActionStep:
    """Parse ``hold(W,1000ms)``, chords, or ``wait(500ms)``."""

    text = value.strip()
    wait_match = WAIT_RE.fullmatch(text)
    if wait_match:
        return ActionStep(duration_ms=int(wait_match.group(1)), kind="wait", raw=text)
    hold_match = ACTION_RE.fullmatch(text)
    if not hold_match:
        raise ValueError(f"Unsupported action step: {value!r}")
    keys = tuple(
        KEY_ALIASES.get(token.strip().upper(), token.strip())
        for token in hold_match.group(1).split("+")
        if token.strip()
    )
    if not keys:
        raise ValueError(f"Action contains no key: {value!r}")
    return ActionStep(keys=keys, duration_ms=int(hold_match.group(2)), raw=text)


def load_tasks(dataset: Path, data_root: Path, task_ids: Iterable[str] = ()) -> list[PlayerTask]:
    records = json.loads(dataset.read_text(encoding="utf-8"))
    if not isinstance(records, list):
        raise ValueError("Dataset must be a JSON array")
    requested = tuple(task_ids)
    if requested:
        by_id = {str(record.get("task_id")): record for record in records}
        missing = [task_id for task_id in requested if task_id not in by_id]
        if missing:
            raise KeyError(f"Task IDs not found: {', '.join(missing)}")
        records = [by_id[task_id] for task_id in requested]
    return [PlayerTask.from_record(record, data_root) for record in records]


class Player(ABC):
    """Reusable lifecycle for one interactive world-model website.

    A new model normally implements only ``select_page``, ``create_world``,
    ``wait_until_ready``, and optionally ``download_video``.
    """

    model_name = "template"

    def __init__(self, cdp_url: str, output_root: Path):
        self.cdp_url = cdp_url
        self.output_root = output_root
        self.runtime: Playwright | None = None
        self.browser: Browser | None = None
        self.context: BrowserContext | None = None
        self.page: Page | None = None
        self._pressed: set[str] = set()

    def __enter__(self) -> "Player":
        self.connect()
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def connect(self) -> None:
        self.runtime = sync_playwright().start()
        self.browser = self.runtime.chromium.connect_over_cdp(self.cdp_url)
        self.context = self.browser.contexts[0] if self.browser.contexts else self.browser.new_context(
            accept_downloads=True
        )
        self.page = self.select_page(self.context)

    @abstractmethod
    def select_page(self, context: BrowserContext) -> Page:
        """Return an existing signed-in model page or open the model URL."""

    @abstractmethod
    def create_world(self, task: PlayerTask, output_dir: Path) -> None:
        """Upload the reference image and submit the model-specific prompt."""

    @abstractmethod
    def wait_until_ready(self, task: PlayerTask, output_dir: Path) -> None:
        """Wait until the interactive canvas accepts keyboard actions."""

    def download_video(self, task: PlayerTask, output_dir: Path) -> Path | None:
        """Optional model-specific native-video download hook."""

        return None

    def observe(self, path: Path) -> Path:
        if self.page is None:
            raise RuntimeError("Player is not connected")
        path.parent.mkdir(parents=True, exist_ok=True)
        self.page.screenshot(path=str(path), type="jpeg", quality=85)
        return path

    def perform(self, action: ActionStep) -> None:
        if self.page is None:
            raise RuntimeError("Player is not connected")
        if action.kind == "wait":
            time.sleep(action.duration_ms / 1000)
            return
        self.page.bring_to_front()
        for key in action.keys:
            self.page.keyboard.down(key)
            self._pressed.add(key)
        try:
            time.sleep(action.duration_ms / 1000)
        finally:
            for key in reversed(action.keys):
                self.page.keyboard.up(key)
                self._pressed.discard(key)

    def release_all(self) -> None:
        if self.page is not None:
            for key in tuple(self._pressed):
                try:
                    self.page.keyboard.up(key)
                except Exception:
                    pass
                self._pressed.discard(key)

    def run_task(self, task: PlayerTask) -> dict[str, Any]:
        output_dir = self.output_root / task.task_id
        output_dir.mkdir(parents=True, exist_ok=True)
        result: dict[str, Any] = {
            "model": self.model_name,
            "task": {**asdict(task), "image_path": str(task.image_path)},
            "status": "started",
            "executed_actions": [],
        }
        try:
            self.create_world(task, output_dir)
            self.wait_until_ready(task, output_dir)
            self.observe(output_dir / "before_actions.jpg")
            for raw_step in task.action_sequence_steps:
                action = parse_action_step(raw_step)
                self.perform(action)
                result["executed_actions"].append(raw_step)
            self.observe(output_dir / "after_actions.jpg")
            video = self.download_video(task, output_dir)
            result.update(status="completed", video_path=str(video) if video else None)
        except Exception as error:
            result.update(status="failed", error=f"{type(error).__name__}: {error}")
            raise
        finally:
            self.release_all()
            (output_dir / "result.json").write_text(
                json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
        return result

    def close(self) -> None:
        self.release_all()
        # CDP attaches to the user's signed-in Chrome. Do not close that browser.
        if self.runtime is not None:
            self.runtime.stop()
        self.runtime = None
        self.browser = None
        self.context = None
        self.page = None


class NewModelPlayer(Player):
    """Copy/rename this class and replace the TODO hooks for another model."""

    model_name = "new_model"

    def select_page(self, context: BrowserContext) -> Page:
        raise NotImplementedError("TODO: select or open the signed-in model page")

    def create_world(self, task: PlayerTask, output_dir: Path) -> None:
        raise NotImplementedError("TODO: upload task.image_path and submit task.prompt")

    def wait_until_ready(self, task: PlayerTask, output_dir: Path) -> None:
        raise NotImplementedError("TODO: wait for the interactive world canvas")


if __name__ == "__main__":
    raise SystemExit(
        "player.py is the adapter template. Run player_genie3.py or "
        "player_happyoyster.py, or subclass Player for another model."
    )
