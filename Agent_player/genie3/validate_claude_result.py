#!/usr/bin/env python3
import json
import sys
from pathlib import Path


def response_ok(record, required_keys):
    if not record.get("enabled", True):
        return True
    if record.get("error") or record.get("retry_error"):
        return False
    if record.get("http_status") != 200:
        return False
    if record.get("parse_error"):
        if record.get("retry_http_status") != 200 or not record.get("retry_raw_response"):
            return False
    return all(key in record and record[key] is not None for key in required_keys)


def validate(result):
    upload = result.get("upload") or {}
    upload_image = result.get("upload_image") or {}
    if not upload.get("image") or not upload_image.get("source"):
        return False
    if not Path(upload_image["source"]).is_file():
        return False

    perspective = str(result.get("perspective_normalized") or result.get("perspective") or "").lower()
    if perspective.replace("-", " ").startswith("first"):
        if (result.get("create_fields") or {}).get("character"):
            return False

    record_specs = (
        ("adaptive_corrections", ("correction_steps", "actions")),
        ("live_hold_stop_checks", ("stop_current_hold", "confidence", "reason")),
        ("rotation_loop_checks", ("closed_loop_ok", "in_place_ok", "orientation_ok", "reason")),
        ("final_orientation_checks", ("final_orientation_ok", "starting_side_ok", "anchor_visible", "reason")),
    )
    enabled_records = 0
    for field, required in record_specs:
        for record in result.get(field) or []:
            if record.get("enabled", True):
                enabled_records += 1
            if not response_ok(record, required):
                return False

    if not result.get("wait_and_observe_task") and enabled_records == 0:
        return False
    if result.get("rotation_loop_task") and result.get("rotation_loop_check_enabled"):
        if result.get("rotation_loop_verified") is not True:
            return False
    if result.get("final_orientation_task") and result.get("final_orientation_check_enabled"):
        checks = result.get("final_orientation_checks") or []
        if not checks or checks[-1].get("final_orientation_ok") is not True:
            return False
    return True


def main():
    try:
        result = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    except (IndexError, OSError, json.JSONDecodeError):
        return 1
    return 0 if validate(result) else 1


if __name__ == "__main__":
    raise SystemExit(main())
