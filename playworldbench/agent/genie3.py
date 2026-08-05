"""Genie 3 page adapter summarized from the original runner."""

from pathlib import Path

from .base import PlayworldEngine


class Genie3Engine(PlayworldEngine):
    UPLOAD = (
        '[data-testid="upload-image"] input[type="file"]',
        'input[accept*="image"]',
    )
    PROMPT = (
        '[data-testid="prompt-input"] textarea',
        'textarea[placeholder*="world" i]',
        'textarea',
    )
    GENERATE = (
        '[data-testid="create-world"]',
        'button:has-text("Create world")',
        'button:has-text("Generate")',
    )
    WORLD_READY = ('canvas:visible', '[role="application"] canvas')

    def _upload_image(self, image: Path) -> None:
        self.first_attached(self.UPLOAD).set_input_files(str(image))

    def _submit_prompt(self, prompt: str) -> None:
        field = self.first_visible(self.PROMPT)
        field.fill(prompt)
        self.first_visible(self.GENERATE).click()

    def _wait_until_world_ready(self) -> None:
        self.wait_for_any_visible(self.WORLD_READY, timeout_ms=300_000)
