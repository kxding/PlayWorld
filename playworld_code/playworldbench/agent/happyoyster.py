"""HappyOyster page adapter summarized from the original runner."""

from pathlib import Path

from .base import PlayworldEngine


class HappyOysterEngine(PlayworldEngine):
    UPLOAD = ('input[type="file"]', '[data-testid="image-upload"] input')
    PROMPT = ('textarea', '[contenteditable="true"]')
    GENERATE = (
        'button:has-text("Generate")',
        'button:has-text("生成")',
        '[data-testid="generate"]',
    )
    WORLD_READY = ('canvas', '[data-testid="world-canvas"]')

    def _upload_image(self, image: Path) -> None:
        self.first_attached(self.UPLOAD).set_input_files(str(image))

    def _submit_prompt(self, prompt: str) -> None:
        field = self.first_visible(self.PROMPT)
        field.fill(prompt)
        self.first_visible(self.GENERATE).click()

    def _wait_until_world_ready(self) -> None:
        self.wait_for_any_visible(self.WORLD_READY, timeout_ms=300_000)
