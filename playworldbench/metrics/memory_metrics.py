"""No-GT Geo3D and dynamic-subject context consistency metrics.

This is a reusable extraction of the local WorldPlay metric protocol. Heavy
model dependencies are imported lazily so the base Gemini/Agent installation
does not require Torch, Transformers, OpenCV, or Ultralytics.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Iterable, Sequence


EARLY_FRACTIONS = (0.02, 0.09, 0.16, 0.23)
LATE_FRACTIONS = (0.77, 0.84, 0.91, 0.98)
WINDOW_PROTOCOL = "fixed_early_late_windows_v1"

DEFAULT_DEPTH_MODEL = "depth-anything/Depth-Anything-V2-Small-hf"
DEFAULT_CLIP_MODEL = "openai/clip-vit-base-patch32"
DEFAULT_YOLO_MODEL = "yolo11n.pt"

DYNAMIC_CLASS_NAMES = frozenset(
    {
        "person",
        "bicycle",
        "car",
        "motorcycle",
        "airplane",
        "bus",
        "train",
        "truck",
        "boat",
        "bird",
        "cat",
        "dog",
        "horse",
        "sheep",
        "cow",
        "elephant",
        "bear",
        "zebra",
        "giraffe",
        "skateboard",
        "surfboard",
    }
)


def fixed_window_indices(total_frames: int) -> tuple[int, ...]:
    if total_frames < 4:
        raise ValueError(f"At least four frames are required, got {total_frames}")
    return tuple(
        min(total_frames - 1, max(0, int(round(value * (total_frames - 1)))))
        for value in EARLY_FRACTIONS + LATE_FRACTIONS
    )


def aggregate_geo3d_similarities(
    early_similarities: Sequence[float],
    late_similarities: Sequence[float],
    *,
    alpha: float = 0.7,
) -> dict[str, float | bool | str]:
    """Aggregate adjacent depth similarities using the local no-GT protocol."""

    if not early_similarities or not late_similarities:
        raise ValueError("Geo3D requires early and late adjacent similarities")
    if not 0 <= alpha <= 1:
        raise ValueError("alpha must be between zero and one")
    early_mean = sum(early_similarities) / len(early_similarities)
    late_mean = sum(late_similarities) / len(late_similarities)
    early_min = min(early_similarities)
    late_min = min(late_similarities)
    score = alpha * ((early_mean + late_mean) / 2) + (1 - alpha) * min(
        early_min, late_min
    )
    return {
        "metric_version": "geo3d_depth_anything_v2_no_gt_v1",
        "score": round(score, 6),
        "early_mean": round(early_mean, 6),
        "early_min": round(early_min, 6),
        "late_mean": round(late_mean, 6),
        "late_min": round(late_min, 6),
        "alpha": alpha,
        "higher_is_better": True,
    }


def read_fixed_window_frames(video_path: Path):
    try:
        import cv2
    except ImportError as error:
        raise RuntimeError(
            "Memory metrics require optional dependencies. "
            "Install with `pip install -e '.[automatic]'`."
        ) from error

    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        raise OSError(f"Cannot open video: {video_path}")
    total = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    try:
        indices = fixed_window_indices(total)
        frames = []
        for index in indices:
            capture.set(cv2.CAP_PROP_POS_FRAMES, index)
            ok, frame = capture.read()
            if not ok:
                raise OSError(f"Cannot decode frame {index} from {video_path}")
            frames.append(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        fps = float(capture.get(cv2.CAP_PROP_FPS) or 0)
    finally:
        capture.release()
    return frames, indices, total, fps


class Geo3DEvaluator:
    def __init__(self, model: str | Path = DEFAULT_DEPTH_MODEL, device: str = "cuda"):
        try:
            import torch
            from transformers import AutoImageProcessor, AutoModelForDepthEstimation
        except ImportError as error:
            raise RuntimeError(
                "Geo3D requires torch and transformers; install `.[automatic]`."
            ) from error

        self.torch = torch
        self.device = torch.device(device)
        self.processor = AutoImageProcessor.from_pretrained(str(model))
        self.model = AutoModelForDepthEstimation.from_pretrained(str(model)).to(
            self.device
        ).eval()
        self.model_name = str(model)

    def evaluate(self, frames) -> dict[str, Any]:
        torch = self.torch
        functional = torch.nn.functional
        inputs = self.processor(images=frames, return_tensors="pt")
        pixel_values = inputs["pixel_values"].to(self.device)
        with torch.inference_mode(), torch.autocast(
            device_type=self.device.type,
            dtype=torch.bfloat16,
            enabled=self.device.type == "cuda",
        ):
            depths = self.model(pixel_values=pixel_values).predicted_depth.float()
        flat = depths.flatten(1)
        mins = flat.min(dim=1, keepdim=True).values
        maxs = flat.max(dim=1, keepdim=True).values
        normalized = (flat - mins) / (maxs - mins).clamp_min(1e-6)
        normalized = functional.normalize(normalized, dim=1)
        similarities = (normalized[:-1] * normalized[1:]).sum(dim=1)
        result = aggregate_geo3d_similarities(
            [float(value) for value in similarities[:3]],
            [float(value) for value in similarities[4:]],
        )
        result["depth_model"] = self.model_name
        return result


class DSCContextEvaluator:
    def __init__(
        self,
        yolo_model: str | Path = DEFAULT_YOLO_MODEL,
        clip_model: str | Path = DEFAULT_CLIP_MODEL,
        device: str = "cuda",
        confidence: float = 0.25,
    ):
        try:
            import torch
            from transformers import CLIPImageProcessor, CLIPVisionModelWithProjection
            from ultralytics import YOLO
        except ImportError as error:
            raise RuntimeError(
                "DSC_ctx requires torch, transformers, and ultralytics; "
                "install `.[automatic]`."
            ) from error

        self.torch = torch
        self.device = torch.device(device)
        self.confidence = confidence
        self.yolo = YOLO(str(yolo_model))
        self.clip_processor = CLIPImageProcessor.from_pretrained(str(clip_model))
        self.clip = CLIPVisionModelWithProjection.from_pretrained(
            str(clip_model)
        ).to(self.device).eval()
        self.clip_model_name = str(clip_model)
        self.yolo_model_name = str(yolo_model)

    def _detections(self, frames) -> list[list[dict[str, Any]]]:
        results = self.yolo.predict(
            source=frames,
            conf=self.confidence,
            imgsz=640,
            device=str(self.device),
            verbose=False,
        )
        detections = []
        for frame, result in zip(frames, results):
            height, width = frame.shape[:2]
            current = []
            if result.boxes is not None:
                for box in result.boxes:
                    class_id = int(box.cls.item())
                    class_name = str(self.yolo.names[class_id])
                    if class_name not in DYNAMIC_CLASS_NAMES:
                        continue
                    x1, y1, x2, y2 = [float(value) for value in box.xyxy[0].tolist()]
                    x1, y1 = max(0, x1), max(0, y1)
                    x2, y2 = min(width, x2), min(height, y2)
                    area_ratio = max(0.0, (x2 - x1) * (y2 - y1)) / (width * height)
                    if area_ratio < 0.001:
                        continue
                    current.append(
                        {
                            "class_id": class_id,
                            "class_name": class_name,
                            "confidence": float(box.conf.item()),
                            "area_ratio": area_ratio,
                            "xyxy": (int(x1), int(y1), int(x2), int(y2)),
                        }
                    )
            detections.append(current)
        return detections

    @staticmethod
    def _shared_class(detections: Sequence[Sequence[dict[str, Any]]]) -> int | None:
        candidates: dict[int, dict[str, Any]] = {}
        for phase, values in (("early", detections[:4]), ("late", detections[4:])):
            for frame_detections in values:
                seen = set()
                for detection in frame_detections:
                    class_id = detection["class_id"]
                    if class_id in seen:
                        continue
                    seen.add(class_id)
                    stats = candidates.setdefault(
                        class_id, {"early": 0, "late": 0, "quality": []}
                    )
                    stats[phase] += 1
                    stats["quality"].append(
                        detection["confidence"] * math.sqrt(detection["area_ratio"])
                    )
        valid = [
            (class_id, stats)
            for class_id, stats in candidates.items()
            if stats["early"] >= 2 and stats["late"] >= 2
        ]
        if not valid:
            return None
        return max(
            valid,
            key=lambda item: (
                min(item[1]["early"], item[1]["late"]),
                sum(item[1]["quality"]) / len(item[1]["quality"]),
            ),
        )[0]

    def evaluate(self, frames) -> dict[str, Any]:
        from PIL import Image

        detections = self._detections(frames)
        class_id = self._shared_class(detections)
        if class_id is None:
            return {
                "metric_version": "dsc_ctx_no_gt_fixed_windows_v1",
                "score": None,
                "status": "no_shared_dynamic_subject",
                "higher_is_better": True,
            }

        crops = []
        phases = []
        metadata = []
        for frame_id, (frame, values) in enumerate(zip(frames, detections)):
            matching = [value for value in values if value["class_id"] == class_id]
            if not matching:
                continue
            chosen = max(
                matching,
                key=lambda value: value["confidence"]
                * math.sqrt(value["area_ratio"]),
            )
            x1, y1, x2, y2 = chosen["xyxy"]
            crop = frame[y1:y2, x1:x2]
            if crop.size == 0 or min(crop.shape[:2]) < 10:
                continue
            crops.append(Image.fromarray(crop))
            phases.append("early" if frame_id < 4 else "late")
            metadata.append(chosen)

        early_count = phases.count("early")
        late_count = phases.count("late")
        if early_count < 2 or late_count < 2:
            return {
                "metric_version": "dsc_ctx_no_gt_fixed_windows_v1",
                "score": None,
                "status": "insufficient_subject_crops",
                "early_detections": early_count,
                "late_detections": late_count,
                "higher_is_better": True,
            }

        torch = self.torch
        inputs = self.clip_processor(images=crops, return_tensors="pt")
        with torch.inference_mode(), torch.autocast(
            device_type=self.device.type,
            dtype=torch.bfloat16,
            enabled=self.device.type == "cuda",
        ):
            features = self.clip(
                pixel_values=inputs["pixel_values"].to(self.device)
            ).image_embeds.float()
        features = torch.nn.functional.normalize(features, dim=1)
        pairwise = features[:early_count] @ features[early_count:].T
        return {
            "metric_version": "dsc_ctx_no_gt_fixed_windows_v1",
            "score": round(float(pairwise.mean()), 6),
            "status": "ok",
            "subject_class": metadata[0]["class_name"],
            "early_detections": early_count,
            "late_detections": late_count,
            "pairwise_min": round(float(pairwise.min()), 6),
            "pairwise_max": round(float(pairwise.max()), 6),
            "clip_model": self.clip_model_name,
            "detector": self.yolo_model_name,
            "higher_is_better": True,
        }


def evaluate_memory_metrics(
    video: Path,
    *,
    metrics: Iterable[str] = ("geo3d", "dsc_ctx"),
    device: str = "cuda",
    depth_model: str | Path = DEFAULT_DEPTH_MODEL,
    clip_model: str | Path = DEFAULT_CLIP_MODEL,
    yolo_model: str | Path = DEFAULT_YOLO_MODEL,
) -> dict[str, Any]:
    selected = tuple(dict.fromkeys(metrics))
    unsupported = sorted(set(selected) - {"geo3d", "dsc_ctx"})
    if unsupported or not selected:
        raise ValueError(f"Unsupported or empty memory metrics: {unsupported}")
    if not video.is_file():
        raise FileNotFoundError(video)

    frames, indices, total, fps = read_fixed_window_frames(video)
    output: dict[str, Any] = {
        "backend": "playworld_no_gt_memory",
        "video": str(video),
        "sampling": {
            "protocol": WINDOW_PROTOCOL,
            "early_fractions": list(EARLY_FRACTIONS),
            "late_fractions": list(LATE_FRACTIONS),
            "frame_indices": list(indices),
            "total_frames": total,
            "fps": fps,
        },
        "metrics": {},
    }
    if "geo3d" in selected:
        output["metrics"]["geo3d"] = Geo3DEvaluator(
            depth_model, device
        ).evaluate(frames)
    if "dsc_ctx" in selected:
        output["metrics"]["dsc_ctx"] = DSCContextEvaluator(
            yolo_model, clip_model, device
        ).evaluate(frames)
    return output


__all__ = [
    "DEFAULT_CLIP_MODEL",
    "DEFAULT_DEPTH_MODEL",
    "DEFAULT_YOLO_MODEL",
    "DSCContextEvaluator",
    "EARLY_FRACTIONS",
    "Geo3DEvaluator",
    "LATE_FRACTIONS",
    "WINDOW_PROTOCOL",
    "aggregate_geo3d_similarities",
    "evaluate_memory_metrics",
    "fixed_window_indices",
    "read_fixed_window_frames",
]
