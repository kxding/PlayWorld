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
from .memory_metrics import (
    aggregate_geo3d_similarities,
    evaluate_memory_metrics,
    fixed_window_indices,
)
from .oe_split_averages import aggregate_fail_one_oe_split, markdown_table
from .vbench_adapter import (
    VBENCH_CUSTOM_DIMENSIONS,
    evaluate_with_vbench,
    validate_vbench_dimensions,
)

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
    "VBENCH_CUSTOM_DIMENSIONS",
    "aggregate_geo3d_similarities",
    "aggregate_fail_one_oe_split",
    "evaluate_memory_metrics",
    "evaluate_with_vbench",
    "fixed_window_indices",
    "markdown_table",
    "validate_vbench_dimensions",
    "export_artifacts",
    "generate_dual_sampling",
]
