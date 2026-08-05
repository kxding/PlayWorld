"""Gemini evaluation for the PlayWorld Fail=1 OE-split table."""

from .metrics import DETAIL_SPEC, PRIMARY_SPEC, generate_dual_sampling

__version__ = "0.1.0"

__all__ = [
    "DETAIL_SPEC",
    "PRIMARY_SPEC",
    "generate_dual_sampling",
]
