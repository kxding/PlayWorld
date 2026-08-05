"""Exact aggregation for Gemini score averages · Fail = 1 · OE split."""

from __future__ import annotations

import math
from typing import Any


OE_INSIGHT_TASKS = frozenset(
    f"OE{index:03d}" for index in (1,2,3,4,5,6,7,8,9,10,11,12,13,18,20,22,23,25,33,35,38,40,63,64,65,66,71,72,73,74)
)
OE_OUT_OF_SIGHT_TASKS = frozenset(
    f"OE{index:03d}" for index in (14,15,16,17,19,21,24,26,27,28,29,30,31,32,34,36,37,39,41,42,43,44,45,46,47,48,49,50,51,52,53,55,56,57,58,59,60,61,62,67,68,69,70)
)

DEFAULT_MODELS = (
    ("Genie", "Genie3"),
    ("LingbotVA", "LingBot-World"),
    ("Lingbotworld-VA2", "LingBot-World-Infinity"),
    ("HYWorld2", "HYWorld2"),
    ("HappyOyster", "HappyOyster"),
    ("SANA_WM", "SANA_WM"),
    ("gamecraft2", "gamecraft2"),
    ("hy_worldplay", "hy_worldplay"),
    ("matrixgame3_native", "matrixgame3_native"),
)


def score_key(item: dict[str, Any]) -> str:
    return f"{item['model']}::{item['path']}"


def _finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def normalized_score(key: str, result: dict[str, Any]) -> float | None:
    if result.get("error"):
        return None
    categories = result.get("categories") or result.get("category_scores_1_to_5")
    if "/GC" in key and isinstance(categories, dict):
        weighted = []
        for name, category in categories.items():
            if not isinstance(category, dict):
                continue
            score = _finite(category.get("score"))
            weight = _finite(category.get("weight"))
            if name == "identity_id" and weight is not None:
                weight = 2.0
            if score is not None and weight is not None and weight > 0:
                weighted.append((score, weight))
        if weighted:
            return round(sum(score * weight for score, weight in weighted) / sum(weight for _, weight in weighted), 2)
    return _finite(result.get("score", result.get("final_score_1_to_5")))


def embedded_review(result: dict[str, Any], group: str, view: str) -> dict[str, Any] | None:
    if group == "IF" and view == "third-person":
        review = result.get("ifInstructionFollowingCheck") or result.get("if_instruction_following_check")
    elif group == "OE":
        review = result.get("oeInstructionFollowingCheck") or result.get("oe_instruction_following_check")
    else:
        return None
    return review if isinstance(review, dict) and review.get("verdict") in {"pass", "partial", "fail"} and not review.get("error") else None


def aggregate_fail_one_oe_split(
    videos: list[dict[str, Any]],
    scores: dict[str, dict[str, Any]],
    gc_task_completion: dict[str, Any] | None = None,
    models: tuple[tuple[str, str], ...] = DEFAULT_MODELS,
) -> list[dict[str, Any]]:
    completion = (gc_task_completion or {}).get("results", gc_task_completion or {})
    expected = {
        group: {item["task"] for item in videos if not item.get("isFullProcess") and item.get("group") == group}
        for group in ("GC", "IF")
    }

    def review_for(item: dict[str, Any], result: dict[str, Any]) -> dict[str, Any] | None:
        embedded = embedded_review(result, str(item.get("group")), str(item.get("view")))
        if embedded is not None:
            return embedded
        value = completion.get(score_key(item))
        return value if isinstance(value, dict) and value.get("verdict") in {"pass", "partial", "fail"} and not value.get("error") else None

    def group_values(model: str, group: str) -> dict[str, Any]:
        values: list[float] = []
        non_fail = 0
        present: set[str] = set()
        for item in videos:
            if item.get("isPlaceholder") or item.get("isFullProcess") or item.get("model") != model or item.get("group") != group:
                continue
            present.add(item["task"])
            result = scores.get(score_key(item))
            value = normalized_score(score_key(item), result or {})
            if value is None:
                continue
            uses_gate = group == "GC" or (group == "IF" and item.get("view") == "third-person")
            if uses_gate:
                review = review_for(item, result or {})
                if review is None:
                    continue
                passed = _finite(review.get("instruction_following_score")) == 1
                values.append(value if passed else 1.0)
                non_fail += int(passed)
            else:
                values.append(value)
                non_fail += 1
        values.extend(1.0 for task in expected[group] if task not in present)
        return _summary(values, non_fail)

    def oe_values(model: str, task_set: frozenset[str], gated: bool) -> dict[str, Any]:
        values: list[float] = []
        non_fail = 0
        present: set[str] = set()
        for item in videos:
            if item.get("isPlaceholder") or item.get("isFullProcess") or item.get("model") != model or item.get("group") != "OE" or item.get("task") not in task_set:
                continue
            present.add(item["task"])
            result = scores.get(score_key(item))
            value = normalized_score(score_key(item), result or {})
            if value is None:
                continue
            if gated:
                review = review_for(item, result or {})
                if review is None:
                    continue
                passed = _finite(review.get("instruction_following_score")) == 1
                values.append(value if passed else 1.0)
                non_fail += int(passed)
            else:
                values.append(value)
                non_fail += 1
        values.extend(1.0 for task in task_set if task not in present)
        return _summary(values, non_fail)

    rows = []
    for model, label in models:
        groups = {
            "gc": group_values(model, "GC"),
            "if": group_values(model, "IF"),
            "insight": oe_values(model, OE_INSIGHT_TASKS, False),
            "out_of_sight": oe_values(model, OE_OUT_OF_SIGHT_TASKS, True),
        }
        means = [value["average"] for value in groups.values() if value["average"] is not None]
        rows.append({"model": model, "label": label, **groups, "overall": sum(means) / len(means) if means else None})
    return rows


def _summary(values: list[float], non_fail: int) -> dict[str, Any]:
    return {"average": sum(values) / len(values) if values else None, "non_fail": non_fail, "denominator": len(values)}


def markdown_table(rows: list[dict[str, Any]]) -> str:
    lines = [
        "| Method | GC | IF | In-sight Evolution | Out-of-sight Evolution | Overall |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in rows:
        cells = []
        for name in ("gc", "if", "insight", "out_of_sight"):
            value = row[name]
            cells.append(f"{value['average']:.2f} (n={value['non_fail']}/{value['denominator']})" if value["average"] is not None else "N/A")
        overall = f"{row['overall']:.2f}" if row["overall"] is not None else "N/A"
        lines.append(f"| {row['label']} | {' | '.join(cells)} | {overall} |")
    return "\n".join(lines) + "\n"


__all__ = ["DEFAULT_MODELS", "OE_INSIGHT_TASKS", "OE_OUT_OF_SIGHT_TASKS", "aggregate_fail_one_oe_split", "markdown_table", "normalized_score", "score_key"]
