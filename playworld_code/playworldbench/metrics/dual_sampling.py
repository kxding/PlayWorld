"""Exact dual-scale video sampling used by the public Gemini metric."""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from PIL import Image


@dataclass(frozen=True)
class SamplingSpec:
    name: str
    fps: float
    cell_width: int
    cell_height: int
    grid_columns: int
    grid_rows: int

    @property
    def frames_per_sheet(self) -> int:
        return self.grid_columns * self.grid_rows

    @property
    def sheet_size(self) -> tuple[int, int]:
        return (
            self.cell_width * self.grid_columns,
            self.cell_height * self.grid_rows,
        )


PRIMARY_SPEC = SamplingSpec("primary", 10.0, 384, 216, 5, 5)
DETAIL_SPEC = SamplingSpec("detail", 0.5, 800, 450, 2, 2)
CONTACT_SHEET_JPEG_QUALITY = 70
CONTACT_SHEET_JPEG_SUBSAMPLING = 2


@dataclass(frozen=True)
class SamplingStream:
    spec: SamplingSpec
    frames: tuple[Path, ...]
    sheets: tuple[Path, ...]

    def metadata(self) -> dict:
        sheet_ranges = []
        for index in range(len(self.sheets)):
            first = index * self.spec.frames_per_sheet
            last = min(first + self.spec.frames_per_sheet, len(self.frames)) - 1
            sheet_ranges.append(
                {
                    "sheet_index": index + 1,
                    "first_sample_index": first,
                    "last_sample_index": last,
                    "first_time_seconds": first / self.spec.fps,
                    "last_time_seconds": last / self.spec.fps,
                    "filled_cells": last - first + 1,
                }
            )
        return {
            "fps": self.spec.fps,
            "sample_interval_seconds": 1 / self.spec.fps,
            "cell_size": [self.spec.cell_width, self.spec.cell_height],
            "grid": [self.spec.grid_columns, self.spec.grid_rows],
            "frames_per_sheet": self.spec.frames_per_sheet,
            "sheet_size": list(self.spec.sheet_size),
            "frames_count": len(self.frames),
            "sheets_count": len(self.sheets),
            "first_sample_time_seconds": 0.0,
            "last_sample_time_seconds": (len(self.frames) - 1) / self.spec.fps,
            "sheet_ranges": sheet_ranges,
            "ordering": "chronological row-major within each sheet",
        }


@dataclass(frozen=True)
class DualSamplingArtifacts:
    primary: SamplingStream
    detail: SamplingStream

    def metadata(self) -> dict:
        return {
            "strategy": "dual-scale full-video contact-sheet sampling",
            "chronological_order": True,
            "contact_sheet_encoding": {
                "format": "JPEG",
                "quality": CONTACT_SHEET_JPEG_QUALITY,
                "subsampling": "4:2:0",
            },
            "primary": self.primary.metadata(),
            "detail": self.detail.metadata(),
            "reference_image_role": "initial scene/style context only, if provided",
        }


def extract_frames(video: Path, output_dir: Path, spec: SamplingSpec) -> tuple[Path, ...]:
    output_dir.mkdir(parents=True, exist_ok=True)
    frame_pattern = output_dir / "frame_%06d.jpg"
    scale_and_pad = (
        f"fps=fps={spec.fps}:start_time=0:round=up,"
        f"scale={spec.cell_width}:{spec.cell_height}:force_original_aspect_ratio=decrease,"
        f"pad={spec.cell_width}:{spec.cell_height}:(ow-iw)/2:(oh-ih)/2:color=black"
    )
    subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(video),
            "-vf",
            scale_and_pad,
            "-q:v",
            "2",
            str(frame_pattern),
        ],
        check=True,
    )
    frames = tuple(sorted(output_dir.glob("frame_*.jpg")))
    if not frames:
        raise RuntimeError(f"No {spec.name} frames were extracted from {video}")
    return frames


def compose_sheets(
    frames: tuple[Path, ...], output_dir: Path, spec: SamplingSpec
) -> tuple[Path, ...]:
    output_dir.mkdir(parents=True, exist_ok=True)
    sheets: list[Path] = []
    for sheet_index, start in enumerate(range(0, len(frames), spec.frames_per_sheet), 1):
        canvas = Image.new("RGB", spec.sheet_size, "black")
        for local_index, frame_path in enumerate(
            frames[start : start + spec.frames_per_sheet]
        ):
            with Image.open(frame_path) as frame:
                if frame.size != (spec.cell_width, spec.cell_height):
                    raise ValueError(
                        f"Unexpected {spec.name} cell size {frame.size}: {frame_path}"
                    )
                x = (local_index % spec.grid_columns) * spec.cell_width
                y = (local_index // spec.grid_columns) * spec.cell_height
                canvas.paste(frame.convert("RGB"), (x, y))
        sheet_path = output_dir / f"{spec.name}_sheet_{sheet_index:04d}.jpg"
        # Preserve the exact sampling resolution/grid while keeping the
        # Base64-encoded generateContent request below common gateway limits.
        canvas.save(
            sheet_path,
            format="JPEG",
            quality=CONTACT_SHEET_JPEG_QUALITY,
            subsampling=CONTACT_SHEET_JPEG_SUBSAMPLING,
            optimize=True,
        )
        sheets.append(sheet_path)
    return tuple(sheets)


def build_stream(video: Path, root: Path, spec: SamplingSpec) -> SamplingStream:
    frames = extract_frames(video, root / spec.name / "frames", spec)
    sheets = compose_sheets(frames, root / spec.name / "sheets", spec)
    return SamplingStream(spec=spec, frames=frames, sheets=sheets)


def generate_dual_sampling(video: Path, root: Path) -> DualSamplingArtifacts:
    if not video.is_file():
        raise FileNotFoundError(video)
    return DualSamplingArtifacts(
        primary=build_stream(video, root, PRIMARY_SPEC),
        detail=build_stream(video, root, DETAIL_SPEC),
    )


def export_artifacts(artifacts: DualSamplingArtifacts, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    for stream in (artifacts.primary, artifacts.detail):
        stream_dir = destination / stream.spec.name
        stream_dir.mkdir(parents=True, exist_ok=True)
        for sheet in stream.sheets:
            shutil.copy2(sheet, stream_dir / sheet.name)
    (destination / "sampling_manifest.json").write_text(
        json.dumps(artifacts.metadata(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
