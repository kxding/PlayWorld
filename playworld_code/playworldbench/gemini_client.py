"""Create Gemini clients from environment variables without persisting secrets."""

from __future__ import annotations

import json
import os
from typing import Any

from google import genai


def load_gateway_headers(value: str | None = None) -> dict[str, str]:
    raw = value if value is not None else os.environ.get("GEMINI_HEADERS_JSON", "")
    if not raw.strip():
        return {}
    parsed: Any = json.loads(raw)
    if not isinstance(parsed, dict) or not all(
        isinstance(key, str) and isinstance(item, str)
        for key, item in parsed.items()
    ):
        raise ValueError("GEMINI_HEADERS_JSON must be a JSON object of string values")
    return parsed


def create_gemini_client(*, api_key: str | None = None) -> genai.Client:
    """Build a standard or gateway-backed client from process environment only."""

    effective_api_key = api_key or os.environ.get("GEMINI_API_KEY")
    if not effective_api_key:
        raise ValueError("Set GEMINI_API_KEY before calling Gemini")

    base_url = os.environ.get("GEMINI_BASE_URL", "").strip()
    headers = load_gateway_headers()
    if not base_url and not headers:
        return genai.Client(api_key=effective_api_key)

    http_options: dict[str, Any] = {}
    if base_url:
        http_options["base_url"] = base_url
    if headers:
        http_options["headers"] = headers
    return genai.Client(api_key=effective_api_key, http_options=http_options)
