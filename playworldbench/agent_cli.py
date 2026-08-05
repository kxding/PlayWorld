#!/usr/bin/env python3
"""Single-task and batch CLI for the fault-tolerant PlayworldEngine harness."""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from playworldbench.agent import (
    AgentHarness,
    GeminiPolicy,
    Genie3Engine,
    HappyOysterEngine,
    HarnessConfig,
    KeepAllPolicy,
    ScriptedPolicy,
)
from playworldbench.agent.recording import json_default


def load_tasks(path: Path, task_ids: list[str] | None) -> list[dict[str, Any]]:
    records = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(records, list):
        raise ValueError(f"Dataset must be a JSON array: {path}")
    if not task_ids:
        return records
    by_id = {record["task_id"]: record for record in records}
    missing = [task_id for task_id in task_ids if task_id not in by_id]
    if missing:
        raise KeyError(f"Tasks not found in {path}: {', '.join(missing)}")
    return [by_id[task_id] for task_id in task_ids]


def make_policy(args: argparse.Namespace, task: dict[str, Any]):
    if args.policy == "keep":
        return KeepAllPolicy()
    if args.policy == "scripted":
        if args.decisions_file is None:
            raise ValueError("--policy scripted requires --decisions-file")
        return ScriptedPolicy.from_json(args.decisions_file)
    if args.policy == "gemini":
        if not os.environ.get("GEMINI_API_KEY"):
            raise ValueError("Set GEMINI_API_KEY for --policy gemini")
        return GeminiPolicy(
            str(task["prompt"]),
            model=args.gemini_model,
            max_extension_ms=args.max_extension_ms,
            task_context=task,
        )
    raise ValueError(args.policy)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--engine", choices=("happyoyster", "genie3"), required=True)
    parser.add_argument("--url", required=True)
    parser.add_argument("--cdp-url", default="http://127.0.0.1:9222")
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--datasuite-root", type=Path, required=True)
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument("--task-id", action="append", dest="task_ids")
    selection.add_argument("--all", action="store_true")
    parser.add_argument("--policy", choices=("keep", "scripted", "gemini"), default="keep")
    parser.add_argument("--decisions-file", type=Path)
    parser.add_argument(
        "--gemini-model",
        default=os.environ.get("GEMINI_MODEL", "gemini-3.1-pro-preview"),
    )
    parser.add_argument("--max-extension-ms", type=int, default=5000)
    parser.add_argument("--output-root", type=Path, default=Path("runs"))
    parser.add_argument("--connect-attempts", type=int, default=3)
    parser.add_argument("--generation-attempts", type=int, default=3)
    parser.add_argument("--observation-attempts", type=int, default=3)
    parser.add_argument("--policy-attempts", type=int, default=3)
    parser.add_argument("--retry-delay-seconds", type=float, default=1.0)
    parser.add_argument("--natural-end-wait-seconds", type=float, default=2.0)
    parser.add_argument(
        "--policy-failure-fallback", choices=("stop", "keep", "fail"), default="stop"
    )
    parser.add_argument("--continue-on-error", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    tasks = load_tasks(args.dataset, None if args.all else args.task_ids)
    args.output_root.mkdir(parents=True, exist_ok=True)
    config = HarnessConfig(
        connect_attempts=args.connect_attempts,
        generation_attempts=args.generation_attempts,
        observation_attempts=args.observation_attempts,
        policy_attempts=args.policy_attempts,
        retry_delay_seconds=args.retry_delay_seconds,
        natural_end_wait_seconds=args.natural_end_wait_seconds,
        policy_failure_fallback=args.policy_failure_fallback,
    )
    engine_type = HappyOysterEngine if args.engine == "happyoyster" else Genie3Engine
    results = []
    for task in tasks:
        image = args.datasuite_root / task["image_path"]
        if not image.is_file():
            raise FileNotFoundError(
                f"Task {task['task_id']} image was not found: {image}"
            )
        engine = engine_type(args.url, args.cdp_url)
        harness = AgentHarness(
            engine=engine,
            policy=make_policy(args, task),
            output_root=args.output_root,
            config=config,
        )
        result = harness.run_task(task, image)
        results.append(result)
        print(json.dumps(result, ensure_ascii=False, default=json_default))
        if result["status"] == "failed" and not args.continue_on_error:
            break

    summary = {
        "engine": args.engine,
        "policy": args.policy,
        "dataset": str(args.dataset),
        "requested_task_count": len(tasks),
        "completed_task_count": sum(item["status"] == "completed" for item in results),
        "stopped_task_count": sum(item["status"] == "stopped" for item in results),
        "failed_task_count": sum(item["status"] == "failed" for item in results),
        "results": results,
    }
    summary_path = args.output_root / f"batch_{datetime.now():%Y%m%d_%H%M%S}.json"
    temporary_summary = summary_path.with_suffix(".json.tmp")
    temporary_summary.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, default=json_default) + "\n",
        encoding="utf-8",
    )
    temporary_summary.replace(summary_path)
    print(f"summary={summary_path}")


if __name__ == "__main__":
    main()
