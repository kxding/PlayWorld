"""Trajectory-only instruction-following gate used by the Fail=1 table."""

from __future__ import annotations

import json
from typing import Any


GATE_SCHEMA = {
    "applicable": "yes/no",
    "task_id": "task identifier",
    "perspective": "first-person/third-person/other",
    "verdict": "pass/partial/fail/not_applicable",
    "instruction_following_score": "1 for pass or partial; 0 for fail; null when not applicable",
    "meaningful_requested_trajectory_progress": "yes/partial/no/not_applicable",
    "revisit_required": "yes/no",
    "revisit_observed": "yes/no/not_applicable",
    "observed_action_zh": "what action trajectory is actually visible",
    "trajectory_evidence_zh": "chronological trajectory-only evidence",
    "failure_reason_zh": "reason for partial/fail, otherwise empty",
    "confidence_1_to_5": "integer 1-5",
}


def gate_kind(task: dict[str, Any]) -> str | None:
    task_id = str(task.get("source_task_id") or task.get("task_id") or "")
    perspective = str(task.get("perspective") or "").lower()
    sub_category = str(task.get("sub_category") or "").lower().replace("-", "").replace("_", "").replace(" ", "")
    if task_id.startswith("GC"):
        return "gc"
    if task_id.startswith("IF") and perspective == "third-person":
        return "if_third_person"
    if task_id.startswith("OE") and "outofsight" in sub_category:
        return "oe_out_of_sight"
    return None


def build_gate_context(
    video_item: dict[str, Any],
    task: dict[str, Any],
    sampling_metadata: dict[str, Any],
) -> dict[str, Any]:
    kind = gate_kind(task)
    prompt = str(task.get("prompt") or "")
    revisit_required = any(
        token in prompt.lower()
        for token in ("return", "turn back", "come back", "walk back", "circle back", "original view", "original position", "original direction", "360")
    )
    return {
        "metric": "PlayWorld instruction-following trajectory gate",
        "gate_kind": kind,
        "task_id": task.get("source_task_id") or task.get("task_id"),
        "model": video_item.get("model"),
        "perspective": task.get("perspective") or video_item.get("view"),
        "objective": prompt,
        "base_action_sequence": task.get("action_sequence"),
        "base_action_steps": task.get("action_sequence_steps"),
        "revisit_required": revisit_required,
        "sampling": sampling_metadata,
        "score_policy": {"pass": 1, "partial": 1, "fail": 0},
    }


def build_gate_prompt(
    video_item: dict[str, Any],
    task: dict[str, Any],
    sampling_metadata: dict[str, Any],
) -> str:
    context = build_gate_context(video_item, task, sampling_metadata)
    if context["gate_kind"] is None:
        raise ValueError("Instruction gate applies only to GC, third-person IF, and out-of-sight OE")
    return (
        "Judge only whether the observed action trajectory follows the requested objective. "
        "Do not compare object identity, scene appearance, background consistency, rendering quality, "
        "or whether returned content looks like the initial frame. Use the PRIMARY 10-FPS stream for "
        "chronological motion evidence; DETAIL frames must not change the trajectory verdict.\n\n"
        "PASS: the requested controlled trajectory is substantially completed.\n"
        "PARTIAL: meaningful prompt-directed progress is visible but the trajectory is incomplete. "
        "For a return/revisit task, passing through the starting pose, direction, or viewpoint at any "
        "intermediate time qualifies as PARTIAL even if visual content differs.\n"
        "FAIL: there is no meaningful requested trajectory progress, or motion is unrelated/opposite.\n"
        "Set instruction_following_score=1 for PASS/PARTIAL and 0 for FAIL.\n\n"
        f"Context:\n{json.dumps(context, ensure_ascii=False, indent=2)}\n\n"
        f"Return JSON only:\n{json.dumps(GATE_SCHEMA, ensure_ascii=False, indent=2)}"
    )


__all__ = ["GATE_SCHEMA", "build_gate_context", "build_gate_prompt", "gate_kind"]
