"""Optional adapter for the official VBench custom-input evaluator."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Iterable


# These are the dimensions the official VBench README documents for arbitrary
# custom videos. Prompt-suite-only dimensions are deliberately not exposed.
VBENCH_CUSTOM_DIMENSIONS = (
    "subject_consistency",
    "background_consistency",
    "motion_smoothness",
    "dynamic_degree",
    "aesthetic_quality",
    "imaging_quality",
)


def validate_vbench_dimensions(dimensions: Iterable[str]) -> tuple[str, ...]:
    values = tuple(dict.fromkeys(str(value) for value in dimensions))
    if not values:
        raise ValueError("At least one VBench dimension is required")
    unsupported = sorted(set(values) - set(VBENCH_CUSTOM_DIMENSIONS))
    if unsupported:
        raise ValueError(
            "Unsupported VBench custom-input dimensions: "
            + ", ".join(unsupported)
            + ". Supported: "
            + ", ".join(VBENCH_CUSTOM_DIMENSIONS)
        )
    return values


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            pass
    return repr(value)


def _run_name(path: Path) -> str:
    value = path.stem if path.is_file() else path.name
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("_.")
    return cleaned or "playworld_vbench"


def evaluate_with_vbench(
    videos_path: Path,
    *,
    full_info_path: Path,
    output_dir: Path,
    dimensions: Iterable[str] = VBENCH_CUSTOM_DIMENSIONS,
    device: str = "cuda",
    name: str | None = None,
) -> dict[str, Any]:
    """Run official VBench without copying videos into this repository.

    The official package owns model loading and per-dimension computation. This
    adapter only validates PlayWorld's supported custom-input subset, invokes
    the public API, and records the output artifacts it created.
    """

    dimensions = validate_vbench_dimensions(dimensions)
    if not videos_path.exists():
        raise FileNotFoundError(videos_path)
    if not full_info_path.is_file():
        raise FileNotFoundError(full_info_path)

    try:
        from vbench import VBench
    except ImportError as error:
        raise RuntimeError(
            "VBench is optional. Install it with `pip install -e '.[vbench]'`."
        ) from error

    output_dir.mkdir(parents=True, exist_ok=True)
    before = {path.resolve() for path in output_dir.rglob("*.json")}
    evaluator = VBench(device, str(full_info_path), str(output_dir))
    result = evaluator.evaluate(
        videos_path=str(videos_path),
        name=name or _run_name(videos_path),
        dimension_list=list(dimensions),
        mode="custom_input",
    )
    after = {path.resolve() for path in output_dir.rglob("*.json")}
    artifacts = sorted(str(path) for path in after)
    new_artifacts = sorted(str(path) for path in after - before)
    return {
        "backend": "official_vbench_custom_input",
        "videos_path": str(videos_path),
        "dimensions": list(dimensions),
        "device": device,
        "full_info_path": str(full_info_path),
        "output_dir": str(output_dir),
        "artifacts": artifacts,
        "new_artifacts": new_artifacts,
        "result": _json_safe(result),
    }


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


__all__ = [
    "VBENCH_CUSTOM_DIMENSIONS",
    "evaluate_with_vbench",
    "validate_vbench_dimensions",
    "write_json",
]
