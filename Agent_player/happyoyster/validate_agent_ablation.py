#!/usr/bin/env python3
import argparse
import json
from pathlib import Path


TASK_IDS = """GC001 GC002 GC004 GC007 GC009 GC014 GC023 GC038 GC046
IF003 IF004 IF006 IF009 IF016 IF028 IF037 IF041
OE014 OE019 OE030 OE039 OE041 OE043 OE052 OE053""".split()


def validate_case(root, condition, task_id, expected_model=None):
    case_dir = root / condition / task_id
    result_path = case_dir / "result.json"
    video_path = case_dir / f"{task_id}_native.mp4"
    condition_video_path = case_dir / f"{condition}.mp4"
    errors = []
    if not result_path.is_file():
        return ["missing result.json"]
    try:
        result = json.loads(result_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"invalid result.json: {exc}"]
    if not video_path.is_file() or video_path.stat().st_size <= 0:
        errors.append("missing/empty native mp4")
    if not condition_video_path.is_file() or condition_video_path.stat().st_size <= 0:
        errors.append(f"missing/empty {condition}.mp4")
    if result.get("status") != "actions_completed":
        errors.append(f"status={result.get('status')}")
    if result.get("download_status") not in {"downloaded", "downloaded_from_downloads"}:
        errors.append(f"download_status={result.get('download_status')}")
    if condition == "preset_only":
        expected_mode = "preset_only"
    elif condition.startswith("agent_only_"):
        expected_mode = "agent_only"
    elif condition.startswith("preset_agent_"):
        expected_mode = "preset_agent"
    else:
        errors.append(f"unrecognized condition={condition}")
        expected_mode = None
    if result.get("ablation_mode") != expected_mode:
        errors.append(f"ablation_mode={result.get('ablation_mode')}")
    if result.get("first_frame_upload_confirmed") is not True:
        errors.append("first frame not confirmed")
    perspective_ok = any(
        key.startswith("perspective_control") and isinstance(value, dict) and value.get("confirmed") is True
        for key, value in result.items()
    )
    if not perspective_ok:
        errors.append("perspective not confirmed")
    sources = [item.get("source") for item in result.get("executed_actions", [])]
    if expected_mode == "preset_only":
        if result.get("agent_provider") is not None or result.get("agent_model") is not None:
            errors.append("preset_only has agent metadata")
        if any(source != "retained" for source in sources):
            errors.append(f"invalid preset sources={sources}")
        if result.get("agent_decisions"):
            errors.append("preset_only called agent")
    elif expected_mode == "agent_only":
        if result.get("agent_provider") != "claude":
            errors.append(f"agent_provider={result.get('agent_provider')}")
        if expected_model and result.get("agent_model") != expected_model:
            errors.append(f"agent_model={result.get('agent_model')}")
        if any(source != "inserted" for source in sources):
            errors.append(f"invalid agent-only sources={sources}")
        for decision in result.get("agent_decisions", []):
            if decision.get("base_sequence_exposed") is not False:
                errors.append("base sequence exposure flag is not false")
            if decision.get("observation_package_fields") != [
                "executed_actions", "initial_observation", "latest_observation", "objective"
            ]:
                errors.append("observation package fields differ")
        forbidden = ("upcoming_dataset_actions", "remaining_phase_actions", "phase_step")
        serialized = json.dumps(result.get("agent_decisions", []), ensure_ascii=False)
        if any(name in serialized for name in forbidden):
            errors.append("base-sequence-derived field leaked into agent decision log")
    elif expected_mode == "preset_agent":
        expected_provider = "gemini" if condition.endswith("_gemini31pro") else "claude"
        if result.get("agent_provider") != expected_provider:
            errors.append(f"agent_provider={result.get('agent_provider')}")
        if expected_model and result.get("agent_model") != expected_model:
            errors.append(f"agent_model={result.get('agent_model')}")
        if not result.get("executed_actions"):
            errors.append("no executed actions")
        if any(source not in {"retained", "replaced", "inserted"} for source in sources):
            errors.append(f"invalid preset-agent sources={sources}")
        call_records = result.get("agent_call_records") or []
        if not call_records or result.get("agent_call_count") != len(call_records):
            errors.append("missing/inconsistent Agent call records")
        if not any(record.get("http_status") == 200 for record in call_records):
            errors.append("no successful Agent call")
    return errors


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("condition")
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[3] / "final-result/agentablation/happyoyster",
    )
    parser.add_argument("--model", default="claude-haiku-4-5-20251001")
    args = parser.parse_args()
    failed = {}
    for task_id in TASK_IDS:
        errors = validate_case(args.root, args.condition, task_id, args.model)
        if errors:
            failed[task_id] = errors
    passed = len(TASK_IDS) - len(failed)
    print(json.dumps({"condition": args.condition, "passed": passed, "failed": failed}, ensure_ascii=False, indent=2))
    if failed:
        print("RETRY_TASK_IDS=" + ",".join(failed))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
