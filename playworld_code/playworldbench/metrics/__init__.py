"""Metric context and exact dual-stream video sampling."""

from .dual_sampling import (
    CONTACT_SHEET_JPEG_QUALITY,
    CONTACT_SHEET_JPEG_SUBSAMPLING,
    DETAIL_SPEC,
    PRIMARY_SPEC,
    DualSamplingArtifacts,
    SamplingSpec,
    export_artifacts,
    generate_dual_sampling,
)
from .gemini_metrics import build_scoring_context, build_scoring_prompt
from .instruction_gate import build_gate_context, build_gate_prompt, gate_kind
from .oe_split_averages import aggregate_fail_one_oe_split, markdown_table

__all__ = [
    "DETAIL_SPEC",
    "PRIMARY_SPEC",
    "CONTACT_SHEET_JPEG_QUALITY",
    "CONTACT_SHEET_JPEG_SUBSAMPLING",
    "DualSamplingArtifacts",
    "SamplingSpec",
    "build_scoring_context",
    "build_scoring_prompt",
    "build_gate_context",
    "build_gate_prompt",
    "gate_kind",
    "aggregate_fail_one_oe_split",
    "markdown_table",
    "export_artifacts",
    "generate_dual_sampling",
]
