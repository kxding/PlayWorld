#!/usr/bin/env python3
"""VQA judge: score one video with dual-scale visual evidence and Gemini."""

from __future__ import annotations

import argparse
import json
import mimetypes
import os
import tempfile
import time
from pathlib import Path
from typing import Any, Callable

from google.genai import types

from playworldbench.gemini_client import create_gemini_client
from metrics.vqa.sampling import (
    DualSamplingArtifacts,
    export_artifacts,
    generate_dual_sampling,
)
from metrics.vqa.rubric import (
    build_scoring_context,
    build_scoring_prompt,
)
from metrics.vqa.instruction_gate import build_gate_context, build_gate_prompt


def load_task(dataset: Path, task_id: str) -> dict[str, Any]:
    with dataset.open(encoding="utf-8") as handle:
        records = json.load(handle)
    for record in records:
        if record.get("task_id") == task_id:
            return record
    raise KeyError(f"Task {task_id!r} was not found in {dataset}")


def json_from_response(text: str) -> Any:
    value = text.strip()
    if value.startswith("```"):
        value = value.split("\n", 1)[1].rsplit("```", 1)[0]
    return json.loads(value)


def image_part(path: Path) -> types.Part:
    mime_type = mimetypes.guess_type(path.name)[0] or "image/jpeg"
    return types.Part.from_bytes(data=path.read_bytes(), mime_type=mime_type)


def wait_until_active(client: Any, uploaded: Any, timeout: int = 600) -> Any:
    deadline = time.monotonic() + timeout
    current = uploaded
    while time.monotonic() < deadline:
        state = str(getattr(current, "state", "ACTIVE")).upper()
        if state.endswith("ACTIVE"):
            return current
        if state.endswith("FAILED"):
            raise RuntimeError(f"Gemini file processing failed: {current}")
        time.sleep(2)
        current = client.files.get(name=current.name)
    raise TimeoutError(f"Gemini file processing exceeded {timeout} seconds")


def evidence_size(artifacts: DualSamplingArtifacts, reference_image: Path | None) -> int:
    paths = [*artifacts.primary.sheets, *artifacts.detail.sheets]
    if reference_image:
        paths.append(reference_image)
    return sum(path.stat().st_size for path in paths)


def build_evidence_parts(
    prompt: str,
    artifacts: DualSamplingArtifacts,
    reference_image: Path | None,
    make_image_part: Callable[[Path], types.Part] = image_part,
) -> list[types.Part]:
    parts = [types.Part.from_text(text=prompt)]
    if reference_image:
        parts.extend(
            [
                types.Part.from_text(
                    text="REFERENCE IMAGE: initial scene/style context only; do not score it as a generated frame."
                ),
                make_image_part(reference_image),
            ]
        )

    for stream in (artifacts.primary, artifacts.detail):
        spec = stream.spec
        parts.append(
            types.Part.from_text(
                text=(
                    f"BEGIN {spec.name.upper()} EVIDENCE: {spec.fps:g} FPS, "
                    f"{spec.cell_width}x{spec.cell_height} cells, "
                    f"{spec.grid_columns}x{spec.grid_rows} chronological row-major grid."
                )
            )
        )
        for index, sheet in enumerate(stream.sheets, 1):
            first_frame = (index - 1) * spec.frames_per_sheet
            last_frame = min(first_frame + spec.frames_per_sheet, len(stream.frames)) - 1
            parts.append(
                types.Part.from_text(
                    text=(
                        f"{spec.name.upper()} SHEET {index}/{len(stream.sheets)}; "
                        f"sample indices {first_frame}-{last_frame}; continue chronologically."
                    )
                )
            )
            parts.append(make_image_part(sheet))
        parts.append(types.Part.from_text(text=f"END {spec.name.upper()} EVIDENCE."))
    return parts


def score(args: argparse.Namespace) -> dict[str, Any]:
    task = load_task(args.dataset, args.task_id)
    metric_task = dict(task)
    metric_task["task_id"] = task.get("source_task_id") or task["task_id"]
    video_item = {
        "model": args.world_model,
        # Metric routing historically uses the GC/IF/OE prefix. Public IDs are
        # all GCxxx, so route with the preserved source ID.
        "task": metric_task["task_id"],
        "group": task.get("source_category") or task.get("category"),
        "view": task.get("perspective"),
        "caption": task.get("image_caption"),
        "status": "generated",
    }

    with tempfile.TemporaryDirectory(prefix="worldmodelbench_sampling_") as temp:
        artifacts = generate_dual_sampling(args.video, Path(temp))
        effective_reference = None if args.mode == "gate" else args.reference_image
        sampling_metadata = artifacts.metadata()
        sampling_metadata["contact_sheet_bytes"] = evidence_size(artifacts, None)
        sampling_metadata["reference_image_bytes"] = (
            effective_reference.stat().st_size if effective_reference else 0
        )
        frames_count = len(artifacts.primary.frames)
        if args.mode == "gate":
            context = build_gate_context(video_item, metric_task, sampling_metadata)
            prompt = build_gate_prompt(video_item, metric_task, sampling_metadata)
        else:
            context = build_scoring_context(
                video_item,
                metric_task,
                frames_count,
                fps=10,
                sampling_metadata=sampling_metadata,
            )
            prompt = build_scoring_prompt(
                video_item,
                metric_task,
                frames_count,
                fps=10,
                sampling_metadata=sampling_metadata,
            )

        if args.context_output:
            args.context_output.parent.mkdir(parents=True, exist_ok=True)
            args.context_output.write_text(
                json.dumps(context, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        if args.sampling_output_dir:
            export_artifacts(artifacts, args.sampling_output_dir)

        result = None
        transport = "none"
        if not args.dry_run:
            client = create_gemini_client()
            total_bytes = evidence_size(artifacts, effective_reference)
            transport = args.evidence_transport
            if transport == "auto":
                transport = "files" if total_bytes > args.inline_limit_mb * 1024**2 else "inline"

            uploaded_files: list[Any] = []

            def upload_part(path: Path) -> types.Part:
                uploaded = client.files.upload(file=path)
                uploaded_files.append(uploaded)
                uploaded = wait_until_active(client, uploaded)
                return types.Part(
                    file_data=types.FileData(
                        file_uri=uploaded.uri,
                        mime_type=uploaded.mime_type,
                    )
                )

            make_part = upload_part if transport == "files" else image_part
            try:
                response = client.models.generate_content(
                    model=args.model,
                    contents=types.Content(
                        role="user",
                        parts=build_evidence_parts(
                            prompt,
                            artifacts,
                            effective_reference,
                            make_part,
                        ),
                    ),
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        temperature=0.1,
                    ),
                )
                result = json_from_response(response.text)
            finally:
                for uploaded in uploaded_files:
                    try:
                        client.files.delete(name=uploaded.name)
                    except Exception:
                        pass

    return {
        "task_id": task["task_id"],
        "mode": args.mode,
        "source_task_id": task.get("source_task_id"),
        "gemini_model": None if args.dry_run else args.model,
        "sampling": sampling_metadata,
        "evidence_transport": transport,
        "score": result,
        "dry_run": args.dry_run,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("score", "gate"), default="score")
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--video", type=Path, required=True)
    parser.add_argument("--reference-image", type=Path)
    parser.add_argument("--world-model", default="unknown")
    parser.add_argument(
        "--cache-key",
        help="Exact manifest key, for example HYWorld2::HYWorld2/GC001/recording.mp4",
    )
    parser.add_argument("--scores-cache", type=Path)
    parser.add_argument("--gc-completion-cache", type=Path)
    parser.add_argument(
        "--model", default=os.environ.get("GEMINI_MODEL", "gemini-3.1-pro-preview")
    )
    parser.add_argument("--context-output", type=Path)
    parser.add_argument("--sampling-output-dir", type=Path)
    parser.add_argument(
        "--evidence-transport",
        choices=("auto", "inline", "files"),
        default="auto",
        help="Auto uses Gemini Files API when contact-sheet bytes exceed the inline limit.",
    )
    parser.add_argument("--inline-limit-mb", type=float, default=18.0)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Generate and validate both sampling streams without calling Gemini.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not args.dry_run and not os.environ.get("GEMINI_API_KEY"):
        raise SystemExit("Set GEMINI_API_KEY before running this script")
    result = score(args)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    if args.cache_key and result["score"] is not None:
        if args.mode == "score" and args.scores_cache:
            _update_cache(args.scores_cache, args.cache_key, result["score"])
        if args.mode == "gate" and args.gc_completion_cache:
            _update_cache(
                args.gc_completion_cache,
                args.cache_key,
                result["score"],
                results_wrapper=True,
            )


def _update_cache(
    path: Path,
    key: str,
    value: Any,
    *,
    results_wrapper: bool = False,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    root = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    target = root.setdefault("results", {}) if results_wrapper else root
    target[key] = value
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(root, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


if __name__ == "__main__":
    main()
