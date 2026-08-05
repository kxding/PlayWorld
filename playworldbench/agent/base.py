"""Public PlayworldEngine abstraction over browser-driven world models."""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from playwright.sync_api import Browser, Page, Playwright, sync_playwright

from .actions import WorldAction


KEY_ALIASES = {
    "UP": "ArrowUp",
    "DOWN": "ArrowDown",
    "LEFT": "ArrowLeft",
    "RIGHT": "ArrowRight",
    "ARROWUP": "ArrowUp",
    "ARROWDOWN": "ArrowDown",
    "ARROWLEFT": "ArrowLeft",
    "ARROWRIGHT": "ArrowRight",
}


@dataclass(frozen=True)
class Observation:
    screenshot: bytes
    url: str
    title: str
    timestamp: float


class PlayworldEngine(ABC):
    """Stable public API; the browser automation library is an implementation detail."""

    def __init__(self, target_url: str, cdp_url: str = "http://127.0.0.1:9222"):
        self.target_url = target_url
        self.cdp_url = cdp_url
        self._runtime: Playwright | None = None
        self._browser: Browser | None = None
        self.page: Page | None = None
        self._pressed: set[str] = set()

    def __enter__(self) -> "PlayworldEngine":
        self.connect()
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def connect(self) -> None:
        if self.page is not None and not self.page.is_closed():
            return
        self._runtime = sync_playwright().start()
        self._browser = self._runtime.chromium.connect_over_cdp(self.cdp_url)
        pages = [page for context in self._browser.contexts for page in context.pages]
        self.page = next((page for page in pages if self.target_url in page.url), None)
        if self.page is None:
            context = self._browser.contexts[0]
            self.page = context.new_page()
            self.page.goto(self.target_url, wait_until="domcontentloaded")

    def upload_and_generate(self, image: Path, prompt: str) -> None:
        if self.page is None:
            raise RuntimeError("Engine is not connected")
        self._upload_image(image)
        self._submit_prompt(prompt)
        self._wait_until_world_ready()
        self.page.bring_to_front()

    @abstractmethod
    def _upload_image(self, image: Path) -> None:
        raise NotImplementedError

    @abstractmethod
    def _submit_prompt(self, prompt: str) -> None:
        raise NotImplementedError

    @abstractmethod
    def _wait_until_world_ready(self) -> None:
        raise NotImplementedError

    def first_visible(self, selectors: Iterable[str]):
        if self.page is None:
            raise RuntimeError("Engine is not connected")
        for selector in selectors:
            locator = self.page.locator(selector).first
            try:
                if locator.is_visible(timeout=500):
                    return locator
            except Exception:
                continue
        raise RuntimeError(f"None of the expected controls is visible: {list(selectors)}")

    def first_attached(self, selectors: Iterable[str]):
        if self.page is None:
            raise RuntimeError("Engine is not connected")
        for selector in selectors:
            locator = self.page.locator(selector).first
            try:
                if locator.count() > 0:
                    return locator
            except Exception:
                continue
        raise RuntimeError(f"None of the expected controls is attached: {list(selectors)}")

    def wait_for_any_visible(
        self,
        selectors: Iterable[str],
        *,
        timeout_ms: int,
        poll_interval_seconds: float = 0.5,
    ):
        selector_list = tuple(selectors)
        deadline = time.monotonic() + timeout_ms / 1000
        last_error = None
        while time.monotonic() < deadline:
            if self.page is None or self.page.is_closed():
                raise RuntimeError("Page closed while waiting for a world view")
            for selector in selector_list:
                locator = self.page.locator(selector).first
                try:
                    if locator.is_visible(timeout=200):
                        return locator
                except Exception as error:
                    last_error = error
            time.sleep(poll_interval_seconds)
        message = f"Timed out waiting for a visible world control: {list(selector_list)}"
        if last_error is not None:
            raise TimeoutError(message) from last_error
        raise TimeoutError(message)

    def perform(self, action: WorldAction) -> None:
        if self.page is None:
            raise RuntimeError("Engine is not connected")
        self.page.bring_to_front()
        token = action.key.upper()
        if token == "WAIT":
            time.sleep(action.duration_ms / 1000)
            return
        key = KEY_ALIASES.get(token, token)
        self.page.keyboard.down(key)
        self._pressed.add(key)
        try:
            time.sleep(action.duration_ms / 1000)
        finally:
            self.page.keyboard.up(key)
            self._pressed.discard(key)

    def release_all(self) -> None:
        if self.page is None:
            self._pressed.clear()
            return
        for key in tuple(self._pressed):
            try:
                self.page.keyboard.up(key)
            except Exception:
                pass
            self._pressed.discard(key)

    def is_healthy(self) -> bool:
        return self.page is not None and not self.page.is_closed()

    def recover(self) -> None:
        self.close()
        self.connect()

    def observe(self) -> Observation:
        if self.page is None:
            raise RuntimeError("Engine is not connected")
        return Observation(
            screenshot=self.page.screenshot(type="jpeg", quality=85),
            url=self.page.url,
            title=self.page.title(),
            timestamp=time.time(),
        )

    def close(self) -> None:
        try:
            self.release_all()
        except Exception:
            self._pressed.clear()
        # A CDP-attached browser belongs to the user, so do not close it here.
        if self._runtime is not None:
            try:
                self._runtime.stop()
            except Exception:
                pass
        self._runtime = None
        self._browser = None
        self.page = None


# Canonical public spelling used by the paper and README. Keep the historical
# spelling above so downstream imports from the first public extraction remain
# source compatible.
PlayWorldEngine = PlayworldEngine
