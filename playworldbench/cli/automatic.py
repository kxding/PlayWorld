#!/usr/bin/env python3
"""Unified CLI for non-Gemini automatic video metrics."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from playworldbench.metrics.memory_metrics import (
    DEFAULT_CLIP_MODEL,
    DEFAULT_DEPTH_MODEL,
    DEFAULT_YOLO_MODEL,
    evaluate_memory_metrics,
)
from playworldbench.metrics.vbench_adapter import (
    VBENCH_CUSTOM_DIMENSIONS,
    evaluate_with_vbench,
    validate_vbench_dimensions,
    write_json,
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Evaluate videos with optional VBench or no-GT memory metrics"
    )
    subparsers = parser.add_subparsers(dest="backend", required=True)

    vbench = subparsers.add_parser("vbench", help="Official VBench custom-input API")
    vbench.add_argument("--video", type=Path, required=True)
    vbench.add_argument("--full-info", type=Path, required=True)
    vbench.add_argument("--output-dir", type=Path, required=True)
    vbench.add_argument("--output", type=Path, required=True)
    vbench.add_argument("--device", default="cuda")
    vbench.add_argument("--name")
    vbench.add_argument(
        "--metrics",
        nargs="+",
        default=list(VBENCH_CUSTOM_DIMENSIONS),
        choices=VBENCH_CUSTOM_DIMENSIONS,
    )
    vbench.add_argument("--dry-run", action="store_true")

    memory = subparsers.add_parser(
        "memory", help="No-GT Geo3D and DSC_ctx fixed-window metrics"
    )
    memory.add_argument("--video", type=Path, required=True)
    memory.add_argument("--output", type=Path, required=True)
    memory.add_argument("--device", default="cuda")
    memory.add_argument(
        "--metrics", nargs="+", choices=("geo3d", "dsc_ctx"), default=("geo3d", "dsc_ctx")
    )
    memory.add_argument("--depth-model", default=DEFAULT_DEPTH_MODEL)
    memory.add_argument("--clip-model", default=DEFAULT_CLIP_MODEL)
    memory.add_argument("--yolo-model", default=DEFAULT_YOLO_MODEL)
    memory.add_argument("--dry-run", action="store_true")
    return parser.parse_args(argv)


def plan(args: argparse.Namespace) -> dict[str, Any]:
    if args.backend == "vbench":
        return {
            "backend": "official_vbench_custom_input",
            "video": str(args.video),
            "full_info": str(args.full_info),
            "output_dir": str(args.output_dir),
            "metrics": list(validate_vbench_dimensions(args.metrics)),
            "device": args.device,
        }
    return {
        "backend": "playworld_no_gt_memory",
        "video": str(args.video),
        "metrics": list(args.metrics),
        "device": args.device,
        "depth_model": args.depth_model,
        "clip_model": args.clip_model,
        "yolo_model": args.yolo_model,
    }


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    if args.dry_run:
        result = {"dry_run": True, **plan(args)}
    elif args.backend == "vbench":
        result = evaluate_with_vbench(
            args.video,
            full_info_path=args.full_info,
            output_dir=args.output_dir,
            dimensions=args.metrics,
            device=args.device,
            name=args.name,
        )
    else:
        result = evaluate_memory_metrics(
            args.video,
            metrics=args.metrics,
            device=args.device,
            depth_model=args.depth_model,
            clip_model=args.clip_model,
            yolo_model=args.yolo_model,
        )
    write_json(args.output, result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"output={args.output}")


if __name__ == "__main__":
    main()
