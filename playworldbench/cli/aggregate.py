#!/usr/bin/env python3
"""Build the exact Fail=1 OE-split Gemini average table from cached results."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from playworldbench.metrics.oe_split_averages import aggregate_fail_one_oe_split, markdown_table


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--videos-manifest", type=Path, required=True)
    parser.add_argument("--scores", type=Path, required=True)
    parser.add_argument("--gc-task-completion", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--output-markdown", type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    videos = json.loads(args.videos_manifest.read_text(encoding="utf-8"))
    scores = json.loads(args.scores.read_text(encoding="utf-8"))
    completion = json.loads(args.gc_task_completion.read_text(encoding="utf-8"))
    rows = aggregate_fail_one_oe_split(videos, scores, completion)
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    rendered = markdown_table(rows)
    if args.output_markdown:
        args.output_markdown.parent.mkdir(parents=True, exist_ok=True)
        args.output_markdown.write_text(rendered, encoding="utf-8")
    print(rendered, end="")


if __name__ == "__main__":
    main()
