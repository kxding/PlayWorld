#!/usr/bin/env python3
"""Complete HappyOyster player migrated from the worldplay_0622 runner."""

import json
import os
import re
import shutil
import time
import base64
import atexit
import io
import signal
import subprocess
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

try:
    import httpx
except ImportError:
    httpx = None

from PIL import Image
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

try:
    from .agent_ablation import (
        ablation_mode,
        align_action_sources,
        configured_agent,
        observation_package,
        post_chat_completion,
        request_agent_decision,
        validate_agent_config,
    )
except ImportError:  # Direct execution: python Agent_player/player_happyoyster.py
    from agent_ablation import (
        ablation_mode,
        align_action_sources,
        configured_agent,
        observation_package,
        post_chat_completion,
        request_agent_decision,
        validate_agent_config,
    )


REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = Path(os.environ.get("HAPPYOYSTER_DATA_ROOT", REPO_ROOT / "data"))
OUT_ROOT = Path(os.environ.get("HAPPYOYSTER_OUT_ROOT", REPO_ROOT / "outputs"))
DOWNLOADS_DIR = Path.home() / "Downloads"
HAPPYOYSTER_CREATE_URL = os.environ.get(
    "HAPPYOYSTER_CREATE_URL",
    "https://www.happyoyster.com/create",
)
HAPPYOYSTER_HOST_FRAGMENT = os.environ.get("HAPPYOYSTER_HOST_FRAGMENT", "happyoyster.com")
HAPPYOYSTER_CDP_URL = os.environ.get("HAPPYOYSTER_CDP_URL", "http://127.0.0.1:9222")
HAPPYOYSTER_TASK_FILE = os.environ.get("HAPPYOYSTER_TASK_FILE", "").strip()

KIGRESS_BASE_URL = os.environ.get("KIGRESS_BASE_URL", "").rstrip("/")
KIGRESS_API_KEY = os.environ.get("KIGRESS_API_KEY", "")
KIGRESS_USER_KEY = os.environ.get("KIGRESS_USER_KEY", "")
KIGRESS_MODEL = os.environ.get("KIGRESS_MODEL", "claude-haiku-4-5-20251001")
KIGRESS_BIZ_SCENE = os.environ.get("KIGRESS_BIZ_SCENE", "offline")
KIGRESS_HOST_HEADER = os.environ.get("KIGRESS_HOST_HEADER", "").strip()
KIGRESS_VERIFY_TLS = os.environ.get("KIGRESS_VERIFY_TLS", "1").strip().lower() not in {
    "0", "false", "no", "off",
}

DEFAULT_FILES = [
    ("GC", "final_GC.json"),
    ("IF", "final_IF.json"),
    ("OE", "final_OE.json"),
]


def configured_files():
    value = os.environ.get("HAPPYOYSTER_DATA_FILES", "").strip()
    if not value:
        return DEFAULT_FILES
    files = []
    for part in value.split(","):
        part = part.strip()
        if not part:
            continue
        match = re.match(r"^(GC|IF|OE)[:=](.+)$", part)
        if match:
            files.append((match.group(1), match.group(2).strip()))
        else:
            files.append((None, part))
    return files


FILES = configured_files()


KEY_MAP = {
    "w": "w",
    "a": "a",
    "s": "s",
    "d": "d",
    "q": "q",
    "e": "e",
    "u": "ArrowUp",
    "j": "ArrowDown",
    "left": "ArrowLeft",
    "right": "ArrowRight",
    "up": "ArrowUp",
    "down": "ArrowDown",
    "←": "ArrowLeft",
    "→": "ArrowRight",
    "space": "Space",
    "jump": "Space",
    "ascend": "Space",
}

CDP_KEY_DETAILS = {
    "w": ("w", "KeyW", 87),
    "a": ("a", "KeyA", 65),
    "s": ("s", "KeyS", 83),
    "d": ("d", "KeyD", 68),
    "q": ("q", "KeyQ", 81),
    "e": ("e", "KeyE", 69),
    "ArrowUp": ("ArrowUp", "ArrowUp", 38),
    "ArrowDown": ("ArrowDown", "ArrowDown", 40),
    "ArrowLeft": ("ArrowLeft", "ArrowLeft", 37),
    "ArrowRight": ("ArrowRight", "ArrowRight", 39),
    "Space": (" ", "Space", 32),
}

KEY_HOLD_MS = int(os.environ.get("HAPPYOYSTER_KEY_HOLD_MS", "650") or "650")
GC001_INITIAL_W_HOLD_MS = max(
    1, int(os.environ.get("HAPPYOYSTER_GC001_INITIAL_W_HOLD_MS", "1000") or "1000")
)
HOLD_SOURCE_STEP_MS = int(os.environ.get("HAPPYOYSTER_HOLD_SOURCE_STEP_MS", "450") or "450")
HOLD_TARGET_STEP_MS = int(os.environ.get("HAPPYOYSTER_HOLD_TARGET_STEP_MS", "650") or "650")
HOLD_SCALE = float(os.environ.get("HAPPYOYSTER_HOLD_SCALE", str(HOLD_TARGET_STEP_MS / HOLD_SOURCE_STEP_MS)) or "1")
ACTION_INTERVAL_S = 0
ACTION_START_DELAY_MS = int(os.environ.get("HAPPYOYSTER_ACTION_START_DELAY_MS", "0") or "0")
WAIT_OBSERVE_MS = int(os.environ.get("HAPPYOYSTER_WAIT_OBSERVE_MS", "60000") or "60000")
END_WAIT_TIMEOUT_S = int(os.environ.get("HAPPYOYSTER_END_WAIT_TIMEOUT_S", "150") or "150")
INTERACTIVE_TIMEOUT_S = int(os.environ.get("HAPPYOYSTER_INTERACTIVE_TIMEOUT_S", "180") or "180")
INTERACTIVE_STABLE_CHECKS = int(os.environ.get("HAPPYOYSTER_INTERACTIVE_STABLE_CHECKS", "2") or "2")
INTERACTIVE_VISUAL_STABLE_CHECKS = int(os.environ.get("HAPPYOYSTER_INTERACTIVE_VISUAL_STABLE_CHECKS", "2") or "2")
CREATE_WAIT_TIMEOUT_S = int(os.environ.get("CREATE_WAIT_TIMEOUT_S", "120") or "120")
CREATE_ATTEMPTS = int(os.environ.get("CREATE_ATTEMPTS", "4") or "4")
CREATE_STUCK_RETRY_S = int(os.environ.get("CREATE_STUCK_RETRY_S", "30") or "30")
CREATE_RETRY_DELAY_S = int(os.environ.get("CREATE_RETRY_DELAY_S", "20") or "20")
SUBMIT_READY_TIMEOUT_S = int(os.environ.get("SUBMIT_READY_TIMEOUT_S", "90") or "90")
DOWNLOAD_ATTEMPTS = int(os.environ.get("DOWNLOAD_ATTEMPTS", "3") or "3")
DOWNLOAD_MODAL_WAIT_S = int(os.environ.get("DOWNLOAD_MODAL_WAIT_S", "120") or "120")
DOWNLOAD_FILE_WAIT_S = int(os.environ.get("DOWNLOAD_FILE_WAIT_S", "90") or "90")
MIN_UPLOAD_ASPECT = 1.5
MAX_UPLOAD_ASPECT = 2.0
TARGET_UPLOAD_ASPECT = 16 / 9
MAX_UPLOAD_WIDTH = 1600


def env_flag(name, default=False):
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def env_action_sequence_overrides():
    raw = os.environ.get("HAPPYOYSTER_ACTION_SEQUENCE_OVERRIDES_JSON", "").strip()
    if not raw:
        return {}
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise ValueError("HAPPYOYSTER_ACTION_SEQUENCE_OVERRIDES_JSON must be a JSON object")
    overrides = {}
    for task_id, steps in parsed.items():
        if not isinstance(task_id, str) or not isinstance(steps, list) or not all(
            isinstance(step, str) and step.strip() for step in steps
        ):
            raise ValueError(f"Invalid action override for {task_id!r}")
        overrides[task_id] = [step.strip() for step in steps]
    return overrides


def env_create_prompt_overrides():
    raw = os.environ.get("HAPPYOYSTER_CREATE_PROMPT_OVERRIDES_JSON", "").strip()
    if not raw:
        return {}
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise ValueError("HAPPYOYSTER_CREATE_PROMPT_OVERRIDES_JSON must be a JSON object")
    overrides = {}
    for task_id, prompt in parsed.items():
        if not isinstance(task_id, str) or not isinstance(prompt, str) or not prompt.strip():
            raise ValueError(f"Invalid create prompt override for {task_id!r}")
        overrides[task_id] = prompt.strip()
    return overrides


ALL_TASKS = env_flag("HAPPYOYSTER_ALL_TASKS")
TASK_ACTION_SEQUENCE_OVERRIDES = env_action_sequence_overrides()
TASK_CREATE_PROMPT_OVERRIDES = env_create_prompt_overrides()
RUN_ID = os.environ.get(
    "HAPPYOYSTER_RUN_ID",
    datetime.now().strftime(
        ("all_entries_actionseq_" if ALL_TASKS else "first_entries_actionseq_") + "%Y%m%d_%H%M%S"
    ),
)
OUT_DIR = OUT_ROOT / RUN_ID
SCREEN_RECORD_DIR_VALUE = os.environ.get("HAPPYOYSTER_SCREEN_RECORD_DIR", "").strip()
SCREEN_RECORD_DIR = Path(SCREEN_RECORD_DIR_VALUE).expanduser() if SCREEN_RECORD_DIR_VALUE else None
SCREEN_RECORD_DEVICE = os.environ.get("HAPPYOYSTER_SCREEN_RECORD_DEVICE", "2").strip() or "2"
SCREEN_RECORD_FPS = int(os.environ.get("HAPPYOYSTER_SCREEN_RECORD_FPS", "15") or "15")
SCREEN_RECORD_APP = os.environ.get("HAPPYOYSTER_SCREEN_RECORD_APP", "Google Chrome Dev").strip()
SKIP_EXISTING_SUCCESS = env_flag("SKIP_EXISTING_SUCCESS", True)
SPLIT_BY_PERSPECTIVE = env_flag("SPLIT_BY_PERSPECTIVE", True)
REQUIRE_ACTION_STEPS = env_flag("REQUIRE_ACTION_STEPS", False)
FORCE_IMAGE_FALLBACK_TASK_IDS = {
    x.strip()
    for x in os.environ.get("HAPPYOYSTER_FORCE_IMAGE_FALLBACK_TASK_IDS", "GC020").split(",")
    if x.strip()
}
ADAPTIVE_CORRECTION = env_flag("HAPPYOYSTER_ADAPTIVE_CORRECTION", False)
ADAPTIVE_MAX_ACTIONS = int(os.environ.get("HAPPYOYSTER_ADAPTIVE_MAX_ACTIONS", "3") or "3")
ADAPTIVE_TIMEOUT_S = float(os.environ.get("HAPPYOYSTER_ADAPTIVE_TIMEOUT_S", "90") or "90")
ADAPTIVE_EXTEND_HOLD = env_flag("HAPPYOYSTER_ADAPTIVE_EXTEND_HOLD", ADAPTIVE_CORRECTION)
ADAPTIVE_EXTEND_HOLD_MIN_MS = int(os.environ.get("HAPPYOYSTER_ADAPTIVE_EXTEND_HOLD_MIN_MS", "2000") or "2000")
ADAPTIVE_EXTEND_HOLD_MAX_MS = int(os.environ.get("HAPPYOYSTER_ADAPTIVE_EXTEND_HOLD_MAX_MS", "2400") or "2400")
ADAPTIVE_EXTEND_HOLD_MAX_ROUNDS = int(os.environ.get("HAPPYOYSTER_ADAPTIVE_EXTEND_HOLD_MAX_ROUNDS", "1") or "1")
ADAPTIVE_PHASE_PROGRESS_CHECK = env_flag("HAPPYOYSTER_ADAPTIVE_PHASE_PROGRESS_CHECK", ADAPTIVE_CORRECTION)
ADAPTIVE_PHASE_CHECK_EVERY = max(
    1, int(os.environ.get("HAPPYOYSTER_ADAPTIVE_PHASE_CHECK_EVERY", "3") or "3")
)
ADAPTIVE_SCREENSHOT_QUALITY = int(os.environ.get("HAPPYOYSTER_ADAPTIVE_SCREENSHOT_QUALITY", "55") or "55")
ADAPTIVE_SCREENSHOT_MAX_WIDTH = int(os.environ.get("HAPPYOYSTER_ADAPTIVE_SCREENSHOT_MAX_WIDTH", "768") or "768")
ADAPTIVE_SCREENSHOT_MAX_HEIGHT = int(os.environ.get("HAPPYOYSTER_ADAPTIVE_SCREENSHOT_MAX_HEIGHT", "432") or "432")
LIVE_HOLD_STOP_CHECK = env_flag("HAPPYOYSTER_LIVE_HOLD_STOP_CHECK", False)
LIVE_HOLD_CHECK_INTERVAL_MS = int(os.environ.get("HAPPYOYSTER_LIVE_HOLD_CHECK_INTERVAL_MS", "50") or "50")
LIVE_HOLD_REQUEST_MIN_MS = int(os.environ.get("HAPPYOYSTER_LIVE_HOLD_REQUEST_MIN_MS", os.environ.get("GENIE3_LIVE_HOLD_MIN_MS", "0")) or "0")
LIVE_HOLD_STOP_MIN_MS = int(os.environ.get("HAPPYOYSTER_LIVE_HOLD_STOP_MIN_MS", os.environ.get("GENIE3_LIVE_HOLD_STOP_MIN_MS", "600")) or "600")
LIVE_HOLD_MIN_MS = LIVE_HOLD_STOP_MIN_MS
LIVE_HOLD_MIN_REMAINING_MS = int(os.environ.get("HAPPYOYSTER_LIVE_HOLD_MIN_REMAINING_MS", os.environ.get("GENIE3_LIVE_HOLD_MIN_REMAINING_MS", "600")) or "600")
LIVE_HOLD_MAX_CHECKS = int(os.environ.get("HAPPYOYSTER_LIVE_HOLD_MAX_CHECKS", "20") or "20")
LIVE_HOLD_TIMEOUT_S = float(os.environ.get("HAPPYOYSTER_LIVE_HOLD_TIMEOUT_S", "8") or "8")
LIVE_HOLD_SCREENSHOT_QUALITY = int(os.environ.get("HAPPYOYSTER_LIVE_HOLD_SCREENSHOT_QUALITY", "45") or "45")
LIVE_HOLD_SCREENSHOT_TIMEOUT_MS = int(os.environ.get("HAPPYOYSTER_LIVE_HOLD_SCREENSHOT_TIMEOUT_MS", "1200") or "1200")
LIVE_HOLD_SCREENSHOT_MAX_WIDTH = int(os.environ.get("HAPPYOYSTER_LIVE_HOLD_SCREENSHOT_MAX_WIDTH", "640") or "640")
LIVE_HOLD_SCREENSHOT_MAX_HEIGHT = int(os.environ.get("HAPPYOYSTER_LIVE_HOLD_SCREENSHOT_MAX_HEIGHT", "360") or "360")
LIVE_HOLD_MAX_TOKENS = int(os.environ.get("HAPPYOYSTER_LIVE_HOLD_MAX_TOKENS", "64") or "64")
LIVE_HOLD_MAX_ADAPTIVE_ACTIONS = int(os.environ.get("HAPPYOYSTER_LIVE_HOLD_MAX_ADAPTIVE_ACTIONS", "2") or "2")
LIVE_HOLD_ADAPTIVE_MIN_MS = int(os.environ.get("HAPPYOYSTER_LIVE_HOLD_ADAPTIVE_MIN_MS", "200") or "200")
LIVE_HOLD_ADAPTIVE_MAX_REPEAT = int(os.environ.get("HAPPYOYSTER_LIVE_HOLD_ADAPTIVE_MAX_REPEAT", "4") or "4")
LIVE_HOLD_ADAPTIVE_MAX_MS = int(
    os.environ.get("HAPPYOYSTER_LIVE_HOLD_ADAPTIVE_MAX_MS", str(KEY_HOLD_MS * LIVE_HOLD_ADAPTIVE_MAX_REPEAT))
    or str(KEY_HOLD_MS * LIVE_HOLD_ADAPTIVE_MAX_REPEAT)
)
REQUIRE_FULL_ACTION_SEQUENCE = env_flag("HAPPYOYSTER_REQUIRE_FULL_ACTION_SEQUENCE", False)
ROTATION_LOOP_CHECK = env_flag("HAPPYOYSTER_ROTATION_LOOP_CHECK", ADAPTIVE_CORRECTION)
ROTATION_LOOP_MAX_ACTIONS = int(os.environ.get("HAPPYOYSTER_ROTATION_LOOP_MAX_ACTIONS", "4") or "4")
ROTATION_LOOP_MAX_CHECKS = int(os.environ.get("HAPPYOYSTER_ROTATION_LOOP_MAX_CHECKS", "2") or "2")
ROTATION_LOOP_SKIP_MIN_ACTIONS = int(os.environ.get("HAPPYOYSTER_ROTATION_LOOP_SKIP_MIN_ACTIONS", "4") or "4")
ROTATION_LOOP_SKIP_CHECK_EVERY = int(os.environ.get("HAPPYOYSTER_ROTATION_LOOP_SKIP_CHECK_EVERY", "2") or "2")
ROTATION_EXTRA_TURN_UNITS = max(
    0, int(os.environ.get("HAPPYOYSTER_ROTATION_EXTRA_TURN_UNITS", "2") or "2")
)
ROTATION_EXTRA_TURN_MS = ROTATION_EXTRA_TURN_UNITS * KEY_HOLD_MS
GC007_FORWARD_EXTRA_UNITS = max(
    0, int(os.environ.get("HAPPYOYSTER_GC007_FORWARD_EXTRA_UNITS", "3") or "3")
)
GC007_RETURN_EXTRA_UNITS = max(
    0, int(os.environ.get("HAPPYOYSTER_GC007_RETURN_EXTRA_UNITS", str(GC007_FORWARD_EXTRA_UNITS)) or "0")
)
FINAL_ORIENTATION_CHECK = env_flag("HAPPYOYSTER_FINAL_ORIENTATION_CHECK", ADAPTIVE_CORRECTION)
FINAL_ORIENTATION_MAX_ACTIONS = int(os.environ.get("HAPPYOYSTER_FINAL_ORIENTATION_MAX_ACTIONS", "4") or "4")
FINAL_ORIENTATION_MAX_CHECKS = int(os.environ.get("HAPPYOYSTER_FINAL_ORIENTATION_MAX_CHECKS", "2") or "2")
KIGRESS_TRUST_ENV = env_flag("KIGRESS_TRUST_ENV", False)
KIGRESS_PREFLIGHT_ATTEMPTS = int(os.environ.get("KIGRESS_PREFLIGHT_ATTEMPTS", "3") or "3")
KIGRESS_PREFLIGHT_TIMEOUT_S = float(os.environ.get("KIGRESS_PREFLIGHT_TIMEOUT_S", "20") or "20")
AGENT_ABLATION_MODE = ablation_mode()
AGENT_ONLY_MAX_DECISIONS = max(1, int(os.environ.get("AGENT_ONLY_MAX_DECISIONS", "16") or "16"))
AGENT_ONLY_MAX_ACTIONS = max(1, int(os.environ.get("AGENT_ONLY_MAX_ACTIONS", "3") or "3"))
AGENT_ONLY_TOTAL_ACTION_BUDGET = max(1, int(os.environ.get("AGENT_ONLY_TOTAL_ACTION_BUDGET", "32") or "32"))
AGENT_ONLY_TIMEOUT_S = float(os.environ.get("AGENT_ONLY_TIMEOUT_S", "60") or "60")
AGENT_ONLY_MAX_TOKENS = max(32, int(os.environ.get("AGENT_ONLY_MAX_TOKENS", "160") or "160"))
AGENT_ONLY_WALLCLOCK_BUDGET_S = max(
    1.0, float(os.environ.get("AGENT_ONLY_WALLCLOCK_BUDGET_S", "42") or "42")
)

if AGENT_ABLATION_MODE in {"preset_only", "agent_only"}:
    ADAPTIVE_CORRECTION = False
    ADAPTIVE_EXTEND_HOLD = False
    ADAPTIVE_PHASE_PROGRESS_CHECK = False
    LIVE_HOLD_STOP_CHECK = False
    ROTATION_LOOP_CHECK = False
    FINAL_ORIENTATION_CHECK = False
    ROTATION_EXTRA_TURN_MS = 0
    GC007_FORWARD_EXTRA_UNITS = 0
    GC007_RETURN_EXTRA_UNITS = 0


def normalize_perspective(value):
    normalized = (value or "").strip().lower().replace("_", "-")
    if normalized in {"first", "first-person", "first person", "firstperson", "fp", "第一人称"}:
        return "first-person"
    if normalized in {"third", "third-person", "third person", "thirdperson", "tp", "第三人称"}:
        return "third-person"
    return "unknown"


def normalize_camera_label(value):
    label = (value or "").strip()
    if label in {"第一人称", "第三人称"}:
        return normalize_perspective(label)
    compact = re.sub(r"[\s_-]+", "", label.lower())
    if compact in {"firstperson", "firstpersonview"}:
        return "first-person"
    if compact in {"thirdperson", "thirdpersonview"}:
        return "third-person"
    return "unknown"


def perspective_dir_name(perspective):
    return normalize_perspective(perspective).replace("-", "_")


PERSPECTIVE_FILTER = {
    normalize_perspective(x)
    for x in os.environ.get("PERSPECTIVES", "").split(",")
    if x.strip()
}


def make_landscape_upload_image(src_path, dst_path):
    try:
        img = Image.open(src_path).convert("RGB")
    except Exception as exc:
        link_or_copy_file(src_path, dst_path)
        return {
            "source": str(src_path),
            "path": str(dst_path),
            "fallback": "original_image",
            "error": repr(exc),
        }
    original_w, original_h = img.size
    original_aspect = original_w / original_h
    crop_box = [0, 0, original_w, original_h]

    if original_aspect < 1.55 or original_aspect > 1.95:
        if original_aspect < TARGET_UPLOAD_ASPECT:
            target_h = min(original_h, int(round(original_w / TARGET_UPLOAD_ASPECT)))
            top = max(0, (original_h - target_h) // 2)
            crop_box = [0, top, original_w, top + target_h]
        else:
            target_w = min(original_w, int(round(original_h * TARGET_UPLOAD_ASPECT)))
            left = max(0, (original_w - target_w) // 2)
            crop_box = [left, 0, left + target_w, original_h]
        img = img.crop(crop_box)

    if img.width > MAX_UPLOAD_WIDTH:
        target_h = int(img.height * MAX_UPLOAD_WIDTH / img.width)
        img = img.resize((MAX_UPLOAD_WIDTH, target_h), Image.Resampling.LANCZOS)

    dst_path.parent.mkdir(parents=True, exist_ok=True)
    if dst_path.exists() or dst_path.is_symlink():
        dst_path.unlink()
    img.save(dst_path, format="JPEG", quality=95)
    upload_w, upload_h = img.size
    return {
        "source": str(src_path),
        "path": str(dst_path),
        "original_size": [original_w, original_h],
        "original_aspect": original_aspect,
        "upload_size": [upload_w, upload_h],
        "upload_aspect": upload_w / upload_h,
        "crop_box": crop_box,
    }


def load_tasks():
    tasks = []
    only_order = [x.strip() for x in os.environ.get("TASK_IDS", "").split(",") if x.strip()]
    only = set(only_order)
    task_offset = int(os.environ.get("TASK_OFFSET", "0") or "0")
    task_limit = int(os.environ.get("TASK_LIMIT", "0") or "0")
    task_sources = []
    if HAPPYOYSTER_TASK_FILE:
        task_path = Path(HAPPYOYSTER_TASK_FILE)
        if not task_path.is_absolute():
            task_path = DATA_ROOT / task_path
        task_sources.append((None, str(task_path), task_path))
    else:
        task_sources = [
            (group, filename, DATA_ROOT / filename)
            for group, filename in FILES
        ]

    for group, filename, path in task_sources:
        data = json.load(open(path, encoding="utf-8"))
        for source_item in data:
            if only and source_item.get("task_id") not in only:
                continue
            if not only and not ALL_TASKS and source_item is not data[0]:
                continue
            if REQUIRE_ACTION_STEPS and not source_item.get("action_sequence_steps"):
                continue
            item = dict(source_item)
            item["perspective_normalized"] = normalize_perspective(item.get("perspective"))
            if PERSPECTIVE_FILTER and item["perspective_normalized"] not in PERSPECTIVE_FILTER:
                continue
            item["group"] = group or item.get("category") or "combined"
            item["source_file"] = filename
            item["resolved_image_path"] = str(DATA_ROOT / item["image_path"])
            tasks.append(item)
        if only and only.issubset({task["task_id"] for task in tasks}):
            break
    if only:
        found = {task["task_id"] for task in tasks}
        missing = sorted(only - found)
        if missing:
            raise ValueError(f"TASK_IDS not found: {missing}")
        order = {task_id: i for i, task_id in enumerate(only_order)}
        tasks.sort(key=lambda task: order.get(task["task_id"], 999))
    if task_offset:
        tasks = tasks[task_offset:]
    if task_limit:
        tasks = tasks[:task_limit]
    return tasks


def task_output_dir(task):
    if SPLIT_BY_PERSPECTIVE:
        return OUT_DIR / perspective_dir_name(task.get("perspective")) / task["task_id"]
    return OUT_DIR / task["task_id"]


def readable_file(path):
    try:
        with Path(path).open("rb") as fp:
            fp.read(32)
        return True
    except Exception:
        return False


def forced_image_fallback(task, image_path):
    if task["task_id"] not in FORCE_IMAGE_FALLBACK_TASK_IDS:
        return image_path, None
    task_id = task["task_id"]
    perspective_dir = perspective_dir_name(task.get("perspective"))
    candidates = [
        OUT_ROOT / "happyoyster_cn_priority_all_rerun_20260708_232330" / perspective_dir / task_id / f"{task_id}_input.jpg",
        OUT_ROOT / "happyoyster_GC_IF_OE_20260703_213609" / perspective_dir / task_id / f"{task_id}_input.jpg",
        OUT_ROOT.parent / "genie3" / "genie3_GC_IF_OE_20260703_171826" / perspective_dir / task_id / f"{task_id}_input.jpg",
        OUT_ROOT.parent / "genie3" / "final-result" / task_id / f"{task_id}_input.jpg",
    ]
    for candidate in candidates:
        if candidate.exists() and readable_file(candidate):
            return candidate, {
                "original": str(image_path),
                "fallback": str(candidate),
                "reason": "forced_image_fallback",
            }
    return image_path, {
        "original": str(image_path),
        "fallback": None,
        "reason": "forced_image_fallback_not_found",
    }


def has_successful_result(task):
    result_path = task_output_dir(task) / "result.json"
    if not result_path.exists():
        return False
    try:
        result = json.loads(result_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return False
    download_path = result.get("download_path")
    condition_name = os.environ.get("HAPPYOYSTER_CONDITION_VIDEO_NAME", "").strip()
    condition_path = task_output_dir(task) / condition_name if condition_name else None
    perspective_confirmed = any(
        key.startswith("perspective_control")
        and isinstance(value, dict)
        and value.get("confirmed") is True
        for key, value in result.items()
    )
    return (
        result.get("status") == "actions_completed"
        and result.get("download_status") in {"downloaded", "downloaded_from_downloads"}
        and bool(download_path)
        and Path(download_path).exists()
        and (condition_path is None or condition_path.exists() and condition_path.stat().st_size > 0)
        and result.get("first_frame_upload_confirmed") is True
        and perspective_confirmed
    )


def box_state(page):
    return page.evaluate(
        """() => {
          const box = el => { const r = el.getBoundingClientRect(); return {x:r.x,y:r.y,w:r.width,h:r.height}; };
          const visible = el => {
            const r = el.getBoundingClientRect();
            const s = getComputedStyle(el);
            return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none';
          };
          return {
            url: location.href,
            text: (document.body.innerText || '').slice(0, 5000),
            canvases: Array.from(document.querySelectorAll('canvas')).filter(visible).map(box),
            videos: Array.from(document.querySelectorAll('video')).filter(visible).map(box),
            buttons: Array.from(document.querySelectorAll('button')).filter(visible).map((b,i)=>({
              i,
              text:(b.innerText||b.getAttribute('aria-label')||'').slice(0,120),
              disabled:!!b.disabled||b.getAttribute('aria-disabled')==='true',
              box:box(b)
            })),
          };
        }"""
    )


def safe_screenshot(page, path, result=None, key=None, **kwargs):
    try:
        page.screenshot(path=str(path), timeout=10000, **kwargs)
        return True
    except Exception as exc:
        if result is not None:
            result[key or "screenshot_error"] = str(exc)
        print(f"[screenshot] skipped {path}: {exc}", flush=True)
        return False


def upload_start_image(page, image_path):
    image_button = page.locator('[role="button"][aria-label="Image"], [role="button"][aria-label="图片"]').first
    try:
        image_button.wait_for(state="visible", timeout=30000)
        with page.expect_file_chooser(timeout=10000) as chooser_info:
            image_button.click()
        chooser_info.value.set_files(str(image_path), timeout=120000)
        return {"method": "file_chooser", "image": str(image_path)}
    except PlaywrightTimeoutError:
        page.locator("input[type=file]").first.set_input_files(str(image_path), timeout=120000)
        return {"method": "hidden_file_input_fallback", "image": str(image_path)}


def fill_prompt_until_present(page, prompt, result, timeout_s=75):
    start = time.perf_counter()
    last_error = None
    while time.perf_counter() - start < timeout_s:
        try:
            textarea = page.locator("textarea").first
            try:
                textarea.wait_for(state="visible", timeout=2500)
                textarea.fill(prompt, timeout=30000)
            except Exception as exc:
                last_error = str(exc)
            page.wait_for_timeout(500)
            state = page.evaluate(
                """(promptText) => {
                  const visible = el => {
                    const r = el.getBoundingClientRect();
                    const s = getComputedStyle(el);
                    return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none';
                  };
                  const allEditors = Array.from(document.querySelectorAll('textarea,[contenteditable="true"]'));
                  const visibleEditors = allEditors.filter(visible);
                  const editorText = allEditors.map(el => el.value || el.innerText || el.textContent || '').join('\\n');
                  if (editorText.includes(promptText.slice(0, 40))) {
                    return {hasPrompt: true, editorText: editorText.slice(0, 240), method: 'playwright'};
                  }
                  const textarea =
                    visibleEditors.find(el => el.tagName === 'TEXTAREA') ||
                    allEditors.find(el => el.tagName === 'TEXTAREA');
                  const editable = visibleEditors.find(el => el.isContentEditable) || allEditors.find(el => el.isContentEditable);
                  if (textarea) {
                    const nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value').set;
                    textarea.focus();
                    nativeSetter.call(textarea, promptText);
                    textarea.dispatchEvent(new InputEvent('input', {bubbles: true, inputType: 'insertText', data: promptText}));
                    textarea.dispatchEvent(new Event('change', {bubbles: true}));
                    const afterText = textarea.value || '';
                    return {
                      hasPrompt: afterText.includes(promptText.slice(0, 40)),
                      editorText: afterText.slice(0, 240),
                      method: visible(textarea) ? 'js_value_setter_visible' : 'js_value_setter_hidden'
                    };
                  }
                  if (editable) {
                    editable.focus();
                    editable.textContent = promptText;
                    editable.dispatchEvent(new InputEvent('input', {bubbles: true, inputType: 'insertText', data: promptText}));
                    editable.dispatchEvent(new Event('change', {bubbles: true}));
                    const afterText = editable.innerText || editable.textContent || '';
                    return {
                      hasPrompt: afterText.includes(promptText.slice(0, 40)),
                      editorText: afterText.slice(0, 240),
                      method: visible(editable) ? 'contenteditable_visible' : 'contenteditable_hidden'
                    };
                  }
                  return {hasPrompt: false, editorText: editorText.slice(0, 240), method: 'no_editor'};
                }""",
                prompt,
            )
            result.setdefault("prompt_fill_attempts", []).append({
                "elapsed_s": time.perf_counter() - start,
                **state,
            })
            print(
                f"[{result['task_id']}] prompt-fill {time.perf_counter()-start:.1f}s "
                f"present={state.get('hasPrompt')} method={state.get('method')}",
                flush=True,
            )
            if state.get("hasPrompt"):
                result["prompt_fill_state"] = state
                return True
        except Exception as exc:
            last_error = str(exc)
            result.setdefault("prompt_fill_attempts", []).append({
                "elapsed_s": time.perf_counter() - start,
                "error": last_error,
            })
            print(f"[{result['task_id']}] prompt-fill error {last_error}", flush=True)
        page.wait_for_timeout(2000)
    result["prompt_fill_error"] = last_error or "prompt_not_present"
    return False


def open_create_panel(page, result, suffix):
    if "happyoyster" in page.url and "/home" in page.url:
        exploration_url = page.url.split("/home", 1)[0] + "/create"
        page.goto(exploration_url, wait_until="domcontentloaded", timeout=60000)
        try:
            page.locator("textarea:visible,[contenteditable='true']:visible").first.wait_for(
                state="visible", timeout=30000
            )
            page.locator("input[type=file]").first.wait_for(state="attached", timeout=30000)
            return {
                "status": "clicked",
                "method": "home_world_exploration_route",
                "button": {"text": "世界探索", "href": "/create"},
                "url": page.url,
            }
        except PlaywrightTimeoutError:
            result[f"create_entry_state_after_exploration{suffix}"] = box_state(page)

    try:
        has_editor = page.locator("textarea:visible,[contenteditable='true']:visible").count() > 0
        has_file_input = page.locator("input[type=file]").count() > 0
        if has_editor and has_file_input:
            return {"status": "already_open", "method": "create_page_form"}
    except Exception:
        pass

    state = box_state(page)
    candidates = [
        b for b in state["buttons"]
        if "click to create your world" in b["text"].lower()
        or "create a new world" in b["text"].lower()
        or b["text"].strip().lower() in {"create", "explore now"}
    ]
    if not candidates:
        exploration_click = page.evaluate(
            """() => {
              const visible = el => {
                const r = el.getBoundingClientRect();
                const s = getComputedStyle(el);
                return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none';
              };
              const labels = new Set(['Adventure', '世界探索']);
              const target = Array.from(document.querySelectorAll('a,button,[role="button"],div,span'))
                .filter(visible)
                .filter(el => labels.has((el.innerText || el.textContent || '').trim()))
                .filter(el => el.getBoundingClientRect().y < 180)
                .sort((a, b) => {
                  const ar = a.getBoundingClientRect();
                  const br = b.getBoundingClientRect();
                  return (ar.width * ar.height) - (br.width * br.height);
                })[0];
              if (!target) return null;
              const r = target.getBoundingClientRect();
              target.click();
              return {text:(target.innerText || target.textContent || '').trim(), x:r.x, y:r.y, w:r.width, h:r.height};
            }"""
        )
        if exploration_click:
            try:
                page.locator("textarea,[contenteditable='true']").first.wait_for(state="attached", timeout=30000)
                page.locator("input[type=file]").first.wait_for(state="attached", timeout=30000)
                return {
                    "status": "clicked",
                    "method": "home_world_exploration_nav",
                    "button": exploration_click,
                    "url": page.url,
                }
            except PlaywrightTimeoutError:
                result[f"create_entry_state_after_exploration{suffix}"] = box_state(page)
        result[f"create_entry_state{suffix}"] = state
        return {"status": "entry_not_found", "url": state["url"], "exploration_click": exploration_click}

    button = sorted(candidates, key=lambda b: b["box"]["w"] * b["box"]["h"], reverse=True)[0]
    page.mouse.click(button["box"]["x"] + button["box"]["w"] / 2, button["box"]["y"] + button["box"]["h"] / 2)
    page.wait_for_timeout(1500)
    try:
        page.locator("textarea,[contenteditable='true']").first.wait_for(state="attached", timeout=30000)
        page.locator("input[type=file]").first.wait_for(state="attached", timeout=30000)
        return {"status": "clicked", "button": button}
    except PlaywrightTimeoutError:
        result[f"create_entry_state_after_click{suffix}"] = box_state(page)
        return {"status": "panel_not_ready_after_click", "button": button}


def create_media_state(page):
    return page.evaluate(
        """() => {
          const visible = el => {
            const r = el.getBoundingClientRect();
            const s = getComputedStyle(el);
            return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none';
          };
          const previewSources = Array.from(document.querySelectorAll('img'))
            .filter(visible)
            .map(img => img.currentSrc || img.src || '')
            .filter(Boolean);
          const imageButton = document.querySelector('[role="button"][aria-label="Image"], [role="button"][aria-label="图片"]');
          const imageButtonHasMedia = !!(imageButton && (
            imageButton.querySelectorAll('img').length > 0 ||
            Array.from(imageButton.querySelectorAll('*')).some(el => {
              const bg = getComputedStyle(el).backgroundImage || '';
              return bg && bg !== 'none' && !bg.includes('plus') && !bg.includes('add');
            })
          ));
          const fileInputs = Array.from(document.querySelectorAll('input[type="file"]'));
          return {
            previewSources,
            imageButtonHasMedia,
            fileCount: fileInputs.reduce((total, input) => total + (input.files ? input.files.length : 0), 0),
          };
        }"""
    )


def wait_create_input_ready(page, prompt, result, media_before=None):
    start = time.perf_counter()
    baseline_sources = set((media_before or {}).get("previewSources") or [])
    while time.perf_counter() - start < 60:
        state = page.evaluate(
            """(promptText) => {
              const box = el => {
                const r = el.getBoundingClientRect();
                return {x:r.x, y:r.y, w:r.width, h:r.height};
              };
              const visible = el => {
                const r = el.getBoundingClientRect();
                const s = getComputedStyle(el);
                return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none';
              };
              const editors = Array.from(document.querySelectorAll('textarea,[contenteditable="true"]'));
              const editorText = editors.map(el => el.value || el.innerText || el.textContent || '').join('\\n');
              const previewImgs = Array.from(document.querySelectorAll('img')).filter(visible).filter(img => {
                const r = img.getBoundingClientRect();
                const src = img.currentSrc || img.src || '';
                return r.width >= 30 && r.height >= 30 && (r.y > window.innerHeight * 0.25 || src.startsWith('blob:'));
              });
              const imageButton = document.querySelector('[role="button"][aria-label="Image"], [role="button"][aria-label="图片"]');
              const imageButtonHasMedia = !!(imageButton && (
                imageButton.querySelectorAll('img').length > 0 ||
                Array.from(imageButton.querySelectorAll('*')).some(el => {
                  const bg = getComputedStyle(el).backgroundImage || '';
                  return bg && bg !== 'none' && !bg.includes('plus') && !bg.includes('add');
                })
              ));
              const fileInputs = Array.from(document.querySelectorAll('input[type="file"]'));
              return {
                url: location.href,
                hasPrompt: editorText.includes(promptText.slice(0, 40)),
                hasPreview: previewImgs.length > 0 || imageButtonHasMedia,
                editorText: editorText.slice(0, 240),
                previewCount: previewImgs.length,
                previewSources: previewImgs.map(img => img.currentSrc || img.src || '').filter(Boolean),
                imageButtonHasMedia,
                fileCount: fileInputs.reduce((total, input) => total + (input.files ? input.files.length : 0), 0),
                imageButtonBox: imageButton ? box(imageButton) : null,
              };
            }""",
            prompt,
        )
        new_preview_sources = sorted(set(state.get("previewSources") or []) - baseline_sources)
        first_frame_confirmed = bool(
            state.get("fileCount")
            or state.get("imageButtonHasMedia")
            or new_preview_sources
        )
        state["newPreviewSources"] = new_preview_sources
        state["firstFrameConfirmed"] = first_frame_confirmed
        ready = state["hasPrompt"] and first_frame_confirmed
        result.setdefault("input_ready_wait", []).append({"elapsed_s": time.perf_counter() - start, **state, "ready": ready})
        print(
            f"[{result['task_id']}] input-ready {time.perf_counter()-start:.1f}s ready={ready} "
            f"prompt={state['hasPrompt']} first_frame={first_frame_confirmed} "
            f"new_preview={len(new_preview_sources)} files={state.get('fileCount')}",
            flush=True,
        )
        if ready:
            result["input_ready_state"] = state
            result["first_frame_upload_confirmed"] = True
            return True
        page.wait_for_timeout(1000)
    return False


def page_requires_login(page):
    try:
        text = page.locator("body").inner_text(timeout=3000).lower()
    except Exception:
        return False
    login_markers = [
        "sign in with google",
        "sign in with email",
        "your login constitutes",
        "log in now",
    ]
    return any(marker in text for marker in login_markers)


def wait_submit_ready(page):
    return page.wait_for_function(
        """() => {
          const visible = el => {
            const r = el.getBoundingClientRect();
            const s = getComputedStyle(el);
            return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none';
          };
          const editors = Array.from(document.querySelectorAll('textarea,[contenteditable="true"]'));
          const editorText = el => el.value || el.innerText || el.textContent || '';
          const textarea = editors.find(el => {
            const r = el.getBoundingClientRect();
            return visible(el) && editorText(el).trim().length > 0 && r.width > 100;
          }) || editors.find(el => editorText(el).trim().length > 0);
          if (textarea && editorText(textarea).trim().length > 0) {
            const tr = textarea.getBoundingClientRect();
            const buttons = Array.from(document.querySelectorAll('button'));
            if (buttons.some(b => {
              const autolog = b.getAttribute('data-autolog') || '';
              return visible(b)
                && autolog.includes('create_send')
                && !b.disabled
                && b.getAttribute('aria-disabled') !== 'true';
            })) return true;
            return buttons.some(b => {
              const r = b.getBoundingClientRect();
              const text = (b.innerText || b.getAttribute('aria-label') || '').trim().toLowerCase();
              return visible(b)
                && !b.disabled
                && b.getAttribute('aria-disabled') !== 'true'
                && r.width <= 96
                && r.height <= 96
                && r.x >= tr.right - 120
                && r.y >= tr.bottom - 100
                && r.y <= tr.bottom + 120
                && !text.includes('back to top')
                && !text.includes('image')
                && !text.includes('random')
                && !text.includes('next world');
            });
          }
          return false;
        }""",
        timeout=SUBMIT_READY_TIMEOUT_S * 1000,
    )


def click_submit(page):
    target = page.evaluate(
        """() => {
          const box = el => { const r = el.getBoundingClientRect(); return {x:r.x,y:r.y,w:r.width,h:r.height}; };
          const visible = el => {
            const r = el.getBoundingClientRect();
            const s = getComputedStyle(el);
            return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none';
          };
          const editors = Array.from(document.querySelectorAll('textarea,[contenteditable="true"]'));
          const textarea = editors.find(el => {
            const r = el.getBoundingClientRect();
            return visible(el) && r.width > 100;
          }) || editors.find(el => {
            const r = el.getBoundingClientRect();
            return r.width > 100;
          }) || editors[0];
          if (textarea) {
            const tr = textarea.getBoundingClientRect();
            const sendButtons = Array.from(document.querySelectorAll('button')).filter(visible)
              .map(b => ({
                b,
                r:b.getBoundingClientRect(),
                text:(b.innerText || b.getAttribute('aria-label') || '').trim().toLowerCase(),
                autolog:b.getAttribute('data-autolog') || '',
                disabled:!!b.disabled || b.getAttribute('aria-disabled') === 'true'
              }))
              .filter(({autolog, disabled}) => !disabled && autolog.includes('create_send'));
            if (sendButtons.length) {
              const c = sendButtons.sort((a,b) => {
                const da = Math.abs((a.r.y + a.r.height / 2) - (tr.bottom + 16));
                const db = Math.abs((b.r.y + b.r.height / 2) - (tr.bottom + 16));
                return da - db;
              })[0];
              return {found:true, box:box(c.b), method:'create_send'};
            }
            const allButtons = Array.from(document.querySelectorAll('button')).filter(visible)
              .map(b => ({b, r:b.getBoundingClientRect(), text:(b.innerText || b.getAttribute('aria-label') || '').trim().toLowerCase(), autolog:b.getAttribute('data-autolog') || '', disabled:!!b.disabled || b.getAttribute('aria-disabled') === 'true'}))
              .filter(({r, text, disabled}) => !disabled
                && r.width <= 96 && r.height <= 96
                && !text.includes('back to top')
                && !text.includes('image')
                && !text.includes('random')
                && !text.includes('next world'));
            const formButtons = allButtons
              .filter(({r, text, disabled}) => !disabled
                && !text
                && r.width <= 80 && r.height <= 80
                && r.x >= tr.right - 90
                && r.y >= tr.top - 120
                && r.y <= tr.bottom + 140
                && !text.includes('back to top'));
            if (formButtons.length) {
              const c = formButtons.sort((a,b) => {
                const targetX = tr.right - 16;
                const targetY = tr.bottom + 16;
                const da = Math.hypot((a.r.x + a.r.width / 2) - targetX, (a.r.y + a.r.height / 2) - targetY);
                const db = Math.hypot((b.r.x + b.r.width / 2) - targetX, (b.r.y + b.r.height / 2) - targetY);
                return da - db;
              })[0];
              return {found:true, box:box(c.b), method:'textarea_adjacent'};
            }
          }
          const looseButtons = Array.from(document.querySelectorAll('button')).filter(visible)
            .map(b => ({
              b,
              r:b.getBoundingClientRect(),
              text:(b.innerText || b.getAttribute('aria-label') || '').trim().toLowerCase(),
              disabled:!!b.disabled || b.getAttribute('aria-disabled') === 'true',
              pointerEvents:getComputedStyle(b).pointerEvents
            }))
            .filter(({r, text, disabled, pointerEvents}) => !disabled
              && pointerEvents !== 'none'
              && r.width <= 96 && r.height <= 96
              && r.x >= window.innerWidth * 0.55
              && r.y >= window.innerHeight * 0.25
              && r.y <= window.innerHeight * 0.75
              && !text
            );
          if (looseButtons.length) {
            const c = looseButtons.sort((a,b) => {
              const targetX = window.innerWidth * 0.76;
              const targetY = window.innerHeight * 0.52;
              const da = Math.hypot((a.r.x + a.r.width / 2) - targetX, (a.r.y + a.r.height / 2) - targetY);
              const db = Math.hypot((b.r.x + b.r.width / 2) - targetX, (b.r.y + b.r.height / 2) - targetY);
              return da - db;
            })[0];
            return {found:true, box:box(c.b), method:'loose_send_button'};
          }
          return {found:false};
        }"""
    )
    if target.get("found") and target.get("box"):
        b = target["box"]
        page.mouse.click(b["x"] + b["w"] / 2, b["y"] + b["h"] / 2)
        target["clicked"] = True
    else:
        viewport = page.viewport_size or {"width": 1200, "height": 738}
        x = min(viewport["width"] - 24, max(24, viewport["width"] * 0.756))
        y = min(viewport["height"] - 24, max(24, viewport["height"] * 0.60))
        page.mouse.click(x, y)
        target.update({
            "found": True,
            "clicked": True,
            "method": "fixed_create_send_fallback",
            "box": {"x": x - 16, "y": y - 16, "w": 32, "h": 32},
        })
    return target


def get_submit_block_reason(page):
    state = page.evaluate(
        """() => {
          const visible = el => {
            const r = el.getBoundingClientRect();
            const s = getComputedStyle(el);
            return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none';
          };
          let targetRect = null;
          let buttons = Array.from(document.querySelectorAll('button')).filter(visible)
            .map(b => ({
              b,
              r: b.getBoundingClientRect(),
              disabled: !!b.disabled || b.getAttribute('aria-disabled') === 'true',
              autolog: b.getAttribute('data-autolog') || '',
              text: (b.innerText || b.getAttribute('aria-label') || '').trim()
            }))
            .filter(({autolog}) => autolog.includes('create_send'));
          if (!buttons.length) {
            const textareas = Array.from(document.querySelectorAll('textarea'));
            const textarea = textareas.find(el => {
              const r = el.getBoundingClientRect();
              return visible(el) && r.width > 100;
            }) || textareas.find(el => {
              const r = el.getBoundingClientRect();
              return r.width > 100;
            }) || textareas[0];
            if (!textarea) return {found: false};
            const tr = textarea.getBoundingClientRect();
            targetRect = tr;
            buttons = Array.from(document.querySelectorAll('button')).filter(visible)
              .map(b => ({b, r: b.getBoundingClientRect(), disabled: !!b.disabled || b.getAttribute('aria-disabled') === 'true', text: (b.innerText || b.getAttribute('aria-label') || '').trim()}))
              .filter(({r}) => r.width <= 80 && r.height <= 80
                && r.x >= tr.right - 90
                && r.y >= tr.top - 90
                && r.y <= tr.bottom + 120);
            if (!buttons.length) {
              buttons = Array.from(document.querySelectorAll('button')).filter(visible)
                .map(b => ({b, r: b.getBoundingClientRect(), disabled: !!b.disabled || b.getAttribute('aria-disabled') === 'true', text: (b.innerText || b.getAttribute('aria-label') || '').trim()}))
                .filter(({r}) => r.width <= 96 && r.height <= 96);
            }
          }
          if (!buttons.length) return {found: false};
          const targetY = targetRect
            ? targetRect.y + targetRect.height / 2
            : window.innerHeight / 2;
          const c = buttons.sort((a, b) => {
            const da = Math.abs((a.r.y + a.r.height / 2) - targetY);
            const db = Math.abs((b.r.y + b.r.height / 2) - targetY);
            return da - db;
          })[0];
          return {found: true, disabled: c.disabled, text: c.text, box: {x: c.r.x, y: c.r.y, w: c.r.width, h: c.r.height}};
        }"""
    )
    if state.get("found") and state.get("box"):
        b = state["box"]
        page.mouse.move(b["x"] + b["w"] / 2, b["y"] + b["h"] / 2)
        page.wait_for_timeout(1200)
    text = ""
    try:
        text = page.locator("body").inner_text(timeout=3000)
    except Exception:
        pass
    lower = text.lower()
    if (
        ("needs" in lower and "credits" in lower)
        or ("积分" in text and ("不足" in text or "需要" in text or "无法" in text))
    ):
        state["reason"] = "insufficient_credits"
    elif "sign in" in lower or "log in" in lower or "login" in lower or "登录" in text:
        state["reason"] = "login_required"
    else:
        state["reason"] = "submit_disabled" if state.get("disabled") else "unknown"
    state["body_tail"] = text[-500:]
    return state


def set_perspective(page, desired_perspective):
    desired = normalize_perspective(desired_perspective)
    if desired not in {"first-person", "third-person"}:
        return {"desired": desired, "status": "unknown_perspective"}

    # HappyOyster current UI uses Adventure for first-person and Directing for third-person.
    oyster_label = "Adventure" if desired == "first-person" else "Directing"
    for _ in range(3):
        state = box_state(page)
        oyster_buttons = [
            b for b in state["buttons"]
            if b["text"] in {"Adventure", "Directing"}
        ]
        target = next((b for b in oyster_buttons if b["text"] == oyster_label), None)
        if target:
            page.mouse.click(target["box"]["x"] + target["box"]["w"] / 2, target["box"]["y"] + target["box"]["h"] / 2)
            page.wait_for_timeout(800)
            return {
                "desired": desired,
                "selected_label": oyster_label,
                "clicked": True,
                "status": "selected_happyoyster_mode",
            }
        page.wait_for_timeout(500)

    desired_label_cn = "第一人称" if desired == "first-person" else "第三人称"
    opposite_label_cn = "第三人称" if desired == "first-person" else "第一人称"
    for _ in range(3):
        state = box_state(page)
        cn_buttons = [
            b for b in state["buttons"]
            if b["text"] in {"第一人称", "第三人称"}
        ]
        current = cn_buttons[0] if cn_buttons else None
        if current and current["text"] == desired_label_cn:
            return {
                "desired": desired,
                "selected_label": current["text"],
                "clicked": False,
                "status": "already_selected_chinese",
            }
        if current and current["text"] == opposite_label_cn:
            page.mouse.click(current["box"]["x"] + current["box"]["w"] / 2, current["box"]["y"] + current["box"]["h"] / 2)
            page.wait_for_timeout(800)
            clicked = page.evaluate(
                """(desiredLabel) => {
                  const visible = el => {
                    const r = el.getBoundingClientRect();
                    const s = getComputedStyle(el);
                    return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none';
                  };
                  const options = Array.from(document.querySelectorAll('button,[role="option"],[role="menuitem"],div,span'))
                    .filter(visible)
                    .filter(el => (el.innerText || el.textContent || '').trim() === desiredLabel);
                  const target = options.sort((a, b) => {
                    const ar = a.getBoundingClientRect();
                    const br = b.getBoundingClientRect();
                    return (ar.width * ar.height) - (br.width * br.height);
                  })[0];
                  if (!target) return null;
                  const r = target.getBoundingClientRect();
                  target.click();
                  return {text: (target.innerText || target.textContent || '').trim(), x:r.x, y:r.y, w:r.width, h:r.height};
                }""",
                desired_label_cn,
            )
            page.wait_for_timeout(800)
            return {
                "desired": desired,
                "selected_label": desired_label_cn if clicked else current["text"],
                "clicked": True,
                "option_click": clicked,
                "status": "selected_chinese" if clicked else "not_confirmed_chinese",
            }
        page.wait_for_timeout(500)

    desired_label = "First person" if desired == "first-person" else "Third person"
    opposite_label = "Third person" if desired == "first-person" else "First person"

    for _ in range(3):
        state = box_state(page)
        perspective_buttons = [
            b for b in state["buttons"]
            if b["text"] in {"First person", "Third person"}
        ]
        if not perspective_buttons:
            page.wait_for_timeout(500)
            continue

        button = perspective_buttons[0]
        if button["text"] == desired_label:
            return {
                "desired": desired,
                "selected_label": button["text"],
                "clicked": False,
                "status": "already_selected",
            }
        if button["text"] == opposite_label:
            page.mouse.click(button["box"]["x"] + button["box"]["w"] / 2, button["box"]["y"] + button["box"]["h"] / 2)
            page.wait_for_timeout(800)
            continue

    state = box_state(page)
    labels = [
        b["text"] for b in state["buttons"]
        if b["text"] in {"First person", "Third person"}
    ]
    return {
        "desired": desired,
        "selected_label": labels[0] if labels else None,
        "clicked": True,
        "status": "selected" if labels and labels[0] == desired_label else "not_confirmed",
    }


def set_camera_view(page, desired_perspective):
    desired = normalize_perspective(desired_perspective)
    if desired not in {"first-person", "third-person"}:
        return {"desired": desired, "status": "unknown_perspective"}
    desired_label_en = "First person view" if desired == "first-person" else "Third person view"
    desired_label_cn = "第一人称" if desired == "first-person" else "第三人称"
    chinese_ui = "happyoyster.cn" in page.url
    desired_label = desired_label_cn if chinese_ui else desired_label_en
    desired_labels = (
        ["First person view", "First person", "Firstperson", "firstperson", "第一人称"]
        if desired == "first-person"
        else ["Third person view", "Third person", "Thirdperson", "thirdperson", "第三人称"]
    )

    def current_view_button():
        state = box_state(page)
        view_buttons = [
            b for b in state["buttons"]
            if normalize_camera_label(b["text"]) in {"first-person", "third-person"}
        ]
        return view_buttons[0] if view_buttons else None

    button = current_view_button()
    if not button:
        return {"desired": desired, "desired_label": desired_label, "status": "view_button_not_found"}
    if normalize_camera_label(button["text"]) == desired:
        return {
            "desired": desired,
            "desired_label": desired_label,
            "selected_label": button["text"],
            "selected_perspective": desired,
            "clicked": False,
            "status": "already_selected",
        }

    page.mouse.click(button["box"]["x"] + button["box"]["w"] / 2, button["box"]["y"] + button["box"]["h"] / 2)
    page.wait_for_timeout(800)
    clicked = page.evaluate(
        """(desiredLabels) => {
          const visible = el => {
            const r = el.getBoundingClientRect();
            const s = getComputedStyle(el);
            return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none';
          };
          const options = Array.from(document.querySelectorAll('button,[role="option"],[role="menuitem"],div,span'))
            .filter(visible)
            .filter(el => desiredLabels.includes((el.innerText || el.textContent || '').trim()));
          const target = options.sort((a, b) => {
            const ar = a.getBoundingClientRect();
            const br = b.getBoundingClientRect();
            return (ar.width * ar.height) - (br.width * br.height);
          })[0];
          if (!target) return null;
          const r = target.getBoundingClientRect();
          target.click();
          return {text: (target.innerText || target.textContent || '').trim(), x:r.x, y:r.y, w:r.width, h:r.height};
        }""",
        desired_labels,
    )
    page.wait_for_timeout(800)
    final_button = current_view_button()
    return {
        "desired": desired,
        "desired_label": desired_label,
        "initial_label": button["text"],
        "option_click": clicked,
        "selected_label": final_button["text"] if final_button else None,
        "selected_perspective": normalize_camera_label(final_button["text"]) if final_button else "unknown",
        "status": "selected" if final_button and normalize_camera_label(final_button["text"]) == desired else "not_confirmed",
    }


def wait_for_explore(page, result):
    start = time.perf_counter()
    while time.perf_counter() - start < CREATE_WAIT_TIMEOUT_S:
        state = box_state(page)
        result.setdefault("create_wait", []).append({
            "elapsed_s": time.perf_counter() - start,
            "url": state["url"],
            "canvas": len(state["canvases"]),
            "video": len(state["videos"]),
        })
        print(f"[{result['task_id']}] wait {time.perf_counter()-start:.1f}s url={state['url']} video={len(state['videos'])}", flush=True)
        if HAPPYOYSTER_HOST_FRAGMENT in state["url"] and "/explore/error" in state["url"]:
            result["create_error_page"] = {
                "elapsed_s": time.perf_counter() - start,
                "url": state["url"],
                "text": state["text"][:500],
            }
            return False
        if (HAPPYOYSTER_HOST_FRAGMENT in state["url"] and "/explore" in state["url"]) and (state["canvases"] or state["videos"]):
            return True
        if HAPPYOYSTER_HOST_FRAGMENT in state["url"] and "/explore" not in state["url"] and time.perf_counter() - start >= CREATE_STUCK_RETRY_S:
            if "/end/travel" in state["url"]:
                result["result_page_url"] = state["url"]
                result["direct_result_page_after_submit"] = True
                return True
            result.setdefault("create_stuck_retries", []).append({
                "elapsed_s": time.perf_counter() - start,
                "url": state["url"],
            })
            return False
        page.wait_for_timeout(2000)
    return False


def text_mentions_world_loading(text):
    lower = (text or "").lower()
    loading_markers = (
        "your world is coming to life",
        "bringing you into the scene",
        "gathering the first sparks",
        "shaping the scenario",
        "brewing imagination",
        "sculpting the atmosphere",
        "launching your world",
        "正在生成",
        "生成中",
        "加载中",
        "正在加载",
        "正在进入",
        "正在准备",
    )
    if any(marker in lower for marker in loading_markers):
        return True
    return bool(re.search(r"\b(?:[1-9]?\d|100)\s*%", text or ""))


def wait_for_interactive(page, result):
    start = time.perf_counter()
    stable_ready = 0
    stable_visual = 0
    while time.perf_counter() - start < INTERACTIVE_TIMEOUT_S:
        state = box_state(page)
        text = state["text"] or ""
        if "this scene can't be played right now" in text.lower():
            result["status"] = "scene_not_playable"
            result["scene_not_playable"] = {"url": state["url"], "text": text[:500]}
            return False
        if "/end/travel" in state["url"]:
            result["status"] = "ended_before_interactive"
            result["ended_before_interactive_url"] = state["url"]
            return False
        loading = text_mentions_world_loading(text)
        visual_ready = bool(state["videos"] or state["canvases"]) and not loading
        stable_visual = stable_visual + 1 if visual_ready else 0
        hud_ready = visual_ready and (
            "left for you" in text
            or "REC" in text
            or any(t in text.split() for t in ("W", "A", "S", "D"))
        )
        # The .com site briefly exposes a preview video before the real world starts
        # generating. Ablation runs require the control HUD so those preview frames
        # can never consume the action sequence.
        ready = hud_ready if AGENT_ABLATION_MODE else (
            hud_ready or stable_visual >= INTERACTIVE_VISUAL_STABLE_CHECKS
        )
        stable_ready = stable_ready + 1 if ready else 0
        result.setdefault("interactive_wait", []).append({
            "elapsed_s": time.perf_counter() - start,
            "ready": ready,
            "hud_ready": hud_ready,
            "visual_ready": visual_ready,
            "stable_visual": stable_visual,
            "loading": loading,
            "stable_ready": stable_ready,
            "url": state["url"],
            "video": len(state["videos"]),
            "canvas": len(state["canvases"]),
            "text": text[:300],
        })
        print(
            f"[{result['task_id']}] interactive {time.perf_counter()-start:.1f}s "
            f"ready={ready} hud={hud_ready} visual={visual_ready} "
            f"visual_stable={stable_visual}/{INTERACTIVE_VISUAL_STABLE_CHECKS} "
            f"loading={loading} stable={stable_ready}/{INTERACTIVE_STABLE_CHECKS}",
            flush=True,
        )
        if stable_ready >= INTERACTIVE_STABLE_CHECKS:
            result["interactive_ready"] = True
            return True
        page.wait_for_timeout(1000)
    result["interactive_ready"] = False
    return False


def files_snapshot(directory=DOWNLOADS_DIR):
    paths = []
    for suffix in ("*.mp4", "*.webm", "*.mov"):
        paths.extend(Path(directory).glob(suffix))
    return {str(p): (p.stat().st_mtime, p.stat().st_size) for p in paths if p.exists()}


def wait_for_download_file(watch_dirs, before_snapshots, timeout_s=180):
    start = time.perf_counter()
    last_sizes = {}
    while time.perf_counter() - start < timeout_s:
        for directory in watch_dirs:
            directory = Path(directory)
            before = before_snapshots.get(str(directory), {})
            for suffix in ("*.mp4", "*.webm", "*.mov"):
                for path in directory.glob(suffix):
                    if not path.exists() or path.name.endswith(".crdownload"):
                        continue
                    stat = path.stat()
                    old = before.get(str(path))
                    if old and old[1] == stat.st_size and old[0] == stat.st_mtime:
                        continue
                    if stat.st_size < 1000:
                        continue
                    key = str(path)
                    previous_size, previous_t = last_sizes.get(key, (None, None))
                    if previous_size == stat.st_size and time.perf_counter() - previous_t >= 2:
                        return path
                    last_sizes[key] = (stat.st_size, time.perf_counter())
        time.sleep(1)
    return None


def newest_new_video_file(watch_dirs, before_snapshots):
    candidates = []
    for directory in watch_dirs:
        directory = Path(directory)
        before = before_snapshots.get(str(directory), {})
        for suffix in ("*.mp4", "*.webm", "*.mov"):
            for path in directory.glob(suffix):
                if not path.exists() or path.name.endswith(".crdownload"):
                    continue
                stat = path.stat()
                if stat.st_size < 1000:
                    continue
                old = before.get(str(path))
                if old and old[1] == stat.st_size and old[0] == stat.st_mtime:
                    continue
                candidates.append((stat.st_mtime, path))
    if not candidates:
        return None
    return sorted(candidates, reverse=True)[0][1]


def stable_new_video_file_once(watch_dirs, before_snapshots, last_sizes, stable_s=2):
    now = time.perf_counter()
    for directory in watch_dirs:
        directory = Path(directory)
        before = before_snapshots.get(str(directory), {})
        for suffix in ("*.mp4", "*.webm", "*.mov"):
            for path in directory.glob(suffix):
                if not path.exists() or path.name.endswith(".crdownload"):
                    continue
                stat = path.stat()
                if stat.st_size < 1000:
                    continue
                old = before.get(str(path))
                if old and old[1] == stat.st_size and old[0] == stat.st_mtime:
                    continue
                key = str(path)
                previous_size, previous_t = last_sizes.get(key, (None, None))
                if previous_size == stat.st_size and now - previous_t >= stable_s:
                    return path
                last_sizes[key] = (stat.st_size, now)
    return None


def save_download_file(found, outdir, result):
    out = outdir / f"{result['task_id']}_native{found.suffix or '.mp4'}"
    if found.resolve() != out.resolve():
        if out.exists():
            out.unlink()
        shutil.move(str(found), str(out))
    result["download_status"] = "downloaded_from_downloads"
    result["download_path"] = str(out)
    result["download_bytes"] = out.stat().st_size
    condition_name = os.environ.get("HAPPYOYSTER_CONDITION_VIDEO_NAME", "").strip()
    if condition_name:
        condition_path = outdir / condition_name
        link_or_copy_file(out, condition_path)
        result["condition_video_path"] = str(condition_path)
        result["condition_video_bytes"] = condition_path.stat().st_size


def link_or_copy_file(src_path, dst_path):
    if dst_path.exists() or dst_path.is_symlink():
        dst_path.unlink()
    try:
        os.link(src_path, dst_path)
    except OSError:
        try:
            os.symlink(os.path.abspath(src_path), dst_path)
        except OSError:
            shutil.copyfile(src_path, dst_path)


def is_download_button(button):
    text = (button.get("text") or "").strip().lower()
    return text in {"download", "下载", "下载视频"} or "download" in text or "下载" in text


def text_mentions_preparing_video(text):
    lower = (text or "").lower()
    return (
        "preparing video" in lower
        or "正在准备" in lower
        or "准备视频" in lower
        or "生成视频" in lower
    )


def click_download_and_save(page, outdir, result):
    page.wait_for_timeout(5000)
    try:
        cdp = page.context.new_cdp_session(page)
        cdp.send("Browser.setDownloadBehavior", {
            "behavior": "allow",
            "downloadPath": str(outdir),
            "eventsEnabled": True,
        })
        result["download_behavior"] = {"downloadPath": str(outdir)}
    except Exception as exc:
        result["download_behavior_error"] = str(exc)
    watch_dirs = [outdir, DOWNLOADS_DIR]
    before_snapshots = {str(directory): files_snapshot(directory) for directory in watch_dirs}
    safe_screenshot(page, outdir / "result_page_before_download.jpg", result, "result_page_screenshot_error", type="jpeg", quality=85, full_page=True)
    state = box_state(page)
    result["result_page_url"] = state["url"]
    direct_download_sizes = {}
    for attempt in range(1, DOWNLOAD_ATTEMPTS + 1):
        page.bring_to_front()
        buttons = []
        state = None
        button_wait_start = time.perf_counter()
        while time.perf_counter() - button_wait_start < 30:
            state = box_state(page)
            buttons = [b for b in state["buttons"] if is_download_button(b)]
            result.setdefault("download_button_wait_states", []).append({
                "attempt": attempt,
                "elapsed_s": time.perf_counter() - button_wait_start,
                "url": state["url"],
                "text": state["text"][:500],
                "buttons": state["buttons"],
            })
            if buttons:
                break
            page.wait_for_timeout(1000)
        if not buttons:
            if (
                state
                and "/end/travel/" in state["url"]
                and not result.get("download_reloaded_result_page")
            ):
                result["download_reloaded_result_page"] = state["url"]
                page.goto(state["url"], wait_until="domcontentloaded", timeout=45000)
                page.wait_for_timeout(5000)
                continue
            result["download_status"] = "no_download_button"
            return
        # Management-page download is the medium circular button; modal download is the wide button.
        management_buttons = [b for b in buttons if b["box"]["w"] <= 100 and 300 <= b["box"]["y"] <= 650]
        b = sorted(management_buttons or buttons, key=lambda x: x["box"]["w"] * x["box"]["h"])[-1]["box"]
        result.setdefault("download_clicks", []).append({"attempt": attempt, "phase": "open_modal", "box": b})
        print(f"[{result['task_id']}] download attempt {attempt}: open modal {b}", flush=True)
        page.mouse.click(b["x"] + b["w"] / 2, b["y"] + b["h"] / 2)
        buttons2 = []
        state2 = None
        modal_wait_start = time.perf_counter()
        last_modal_open_click = modal_wait_start
        while time.perf_counter() - modal_wait_start < DOWNLOAD_MODAL_WAIT_S:
            page.wait_for_timeout(2500)
            direct_found = stable_new_video_file_once(watch_dirs, before_snapshots, direct_download_sizes)
            if direct_found:
                result.setdefault("download_direct_detected", []).append({
                    "attempt": attempt,
                    "path": str(direct_found),
                    "elapsed_s": time.perf_counter() - modal_wait_start,
                })
                save_download_file(direct_found, outdir, result)
                return
            state2 = box_state(page)
            result.setdefault("download_modal_states", []).append({
                "attempt": attempt,
                "elapsed_s": time.perf_counter() - modal_wait_start,
                "text": state2["text"][:500],
                "buttons": state2["buttons"],
            })
            buttons2 = [b for b in state2["buttons"] if is_download_button(b) and b["box"]["w"] > 150]
            if buttons2:
                break
            if text_mentions_preparing_video(state2["text"]):
                print(f"[{result['task_id']}] download attempt {attempt}: preparing video", flush=True)
                continue
            small_buttons = [
                b for b in state2["buttons"]
                if is_download_button(b) and b["box"]["w"] <= 120
            ]
            if small_buttons and time.perf_counter() - last_modal_open_click >= 10:
                b_retry = sorted(small_buttons, key=lambda x: x["box"]["w"] * x["box"]["h"])[-1]["box"]
                result.setdefault("download_clicks", []).append({
                    "attempt": attempt,
                    "phase": "reopen_modal",
                    "box": b_retry,
                })
                print(f"[{result['task_id']}] download attempt {attempt}: reopen modal {b_retry}", flush=True)
                page.mouse.click(b_retry["x"] + b_retry["w"] / 2, b_retry["y"] + b_retry["h"] / 2)
                last_modal_open_click = time.perf_counter()
                continue
            # Modal may have closed or click may not have registered.
            if not any(is_download_button(b) for b in state2["buttons"]):
                break
        if not buttons2:
            print(f"[{result['task_id']}] download attempt {attempt}: modal button not ready", flush=True)
            page.wait_for_timeout(1500)
            continue
        b2 = sorted(buttons2, key=lambda x: x["box"]["w"] * x["box"]["h"])[-1]["box"]
        result.setdefault("download_clicks", []).append({"attempt": attempt, "phase": "confirm_download", "box": b2})
        print(f"[{result['task_id']}] download attempt {attempt}: confirm {b2}", flush=True)
        page.mouse.click(b2["x"] + b2["w"] / 2, b2["y"] + b2["h"] / 2)

        found = wait_for_download_file(watch_dirs, before_snapshots, timeout_s=DOWNLOAD_FILE_WAIT_S)
        if found:
            save_download_file(found, outdir, result)
            return
        late_found = newest_new_video_file(watch_dirs, before_snapshots)
        if late_found:
            result.setdefault("download_late_detected", []).append({
                "attempt": attempt,
                "path": str(late_found),
            })
            save_download_file(late_found, outdir, result)
            return
        result.setdefault("download_attempt_timeouts", []).append({"attempt": attempt})

    found = wait_for_download_file(watch_dirs, before_snapshots, timeout_s=60)
    if not found:
        found = newest_new_video_file(watch_dirs, before_snapshots)
    if found:
        result["download_late_after_retries"] = str(found)
        save_download_file(found, outdir, result)
        return
    result["download_status"] = "download_timeout"


def parse_step(step):
    original_step = step.strip()
    step = original_step
    repeat = 1
    repeat_match = re.match(r"^(.*)\*(\d+)$", step)
    if repeat_match:
        step = repeat_match.group(1).strip()
        repeat = int(repeat_match.group(2))
    hold_match = re.match(r"^hold\(([^,]+),\s*([0-9.]+)\s*(ms|s)?\)$", step, re.I)
    if hold_match:
        key_part = hold_match.group(1).strip()
        value = float(hold_match.group(2))
        unit = (hold_match.group(3) or "ms").lower()
        source_hold_ms = int(value * 1000 if unit == "s" else value)
        hold_ms = max(1, int(round(source_hold_ms * HOLD_SCALE)))
        keys = [normalize_action_token(k) for k in re.split(r"[+&]", key_part) if k.strip()]
        total_source_hold_ms = source_hold_ms * repeat
        total_hold_ms = hold_ms * repeat
        return [{
            "type": "key",
            "keys": keys,
            "raw": original_step,
            "repeat": repeat,
            "source_hold_ms": total_source_hold_ms,
            "hold_ms": total_hold_ms,
            "hold_token": f"hold({'+'.join(display_key_token(k) for k in keys)},{total_hold_ms}ms)",
        }]
    wait_match = re.match(r"^wait\(\s*([0-9.]+)\s*(ms|s)?\s*\)$", step, re.I)
    if wait_match:
        value = float(wait_match.group(1))
        unit = (wait_match.group(2) or "ms").lower()
        seconds = value if unit == "s" else value / 1000
        return [{"type": "wait", "seconds": seconds * repeat, "repeat": repeat, "raw": original_step}]
    if step == "wait":
        return [{"type": "wait", "seconds": ACTION_INTERVAL_S * repeat, "repeat": repeat, "raw": original_step}]
    if step.startswith("wait:"):
        return [{
            "type": "wait",
            "seconds": float(step.split(":", 1)[1]) * repeat,
            "repeat": repeat,
            "raw": original_step,
        }]
    if step.startswith("interact("):
        return [{
            "type": "key",
            "keys": [normalize_action_token(step)],
            "raw": original_step,
            "repeat": repeat,
            "hold_ms": KEY_HOLD_MS * repeat,
        }]
    if step.startswith("(") and step.endswith(")"):
        keys = [normalize_action_token(k) for k in step[1:-1].split("+") if k.strip()]
        return [{"type": "key", "keys": keys, "raw": original_step, "repeat": repeat, "hold_ms": KEY_HOLD_MS * repeat}]
    if "+" in step:
        keys = [normalize_action_token(k) for k in step.split("+") if k.strip()]
        return [{"type": "key", "keys": keys, "raw": original_step, "repeat": repeat, "hold_ms": KEY_HOLD_MS * repeat}]
    return [{
        "type": "key",
        "keys": [normalize_action_token(step)],
        "raw": original_step,
        "repeat": repeat,
        "hold_ms": KEY_HOLD_MS * repeat,
    }]


def normalize_action_token(token):
    token = token.strip().lower()
    match = re.match(r"^interact\(([^,)]*)(?:,\s*\d+)?\)$", token)
    if not match:
        return token
    intent = match.group(1).strip().lower()
    if intent in {"jump", "climb", "ascend"}:
        return "jump"
    return "e"


def display_key_token(token):
    mapped = {
        "left": "LEFT",
        "right": "RIGHT",
        "up": "UP",
        "down": "DOWN",
        "←": "LEFT",
        "→": "RIGHT",
        "↑": "UP",
        "↓": "DOWN",
        "space": "SPACE",
    }
    return mapped.get(str(token).lower(), str(token).upper())


def expand_steps(steps):
    actions = []
    for step_index, step in enumerate(steps):
        for action in parse_step(step):
            action["step_index"] = step_index
            action["step"] = step
            actions.append(action)
    return actions


def extract_chat_text(data):
    choices = data.get("choices") or []
    if choices:
        message = choices[0].get("message") or {}
        content = message.get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts = []
            for item in content:
                if isinstance(item, dict):
                    parts.append(item.get("text") or item.get("content") or "")
                else:
                    parts.append(str(item))
            return "".join(parts)
    content = data.get("content")
    if isinstance(content, list) and content:
        return "".join(item.get("text", "") if isinstance(item, dict) else str(item) for item in content)
    candidates = data.get("candidates") or []
    if candidates:
        return "".join(
            part.get("text", "")
            for candidate in candidates
            for part in ((candidate.get("content") or {}).get("parts") or [])
            if isinstance(part, dict)
        )
    return json.dumps(data, ensure_ascii=False)


def extract_json_object(text):
    text = (text or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?", "", text).strip()
        text = re.sub(r"```$", "", text).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.S)
        if match:
            return json.loads(match.group(0))
        raise


def strict_adaptive_json_retry_prompt(original_prompt, bad_response, parse_error):
    return (
        "Your previous response was not valid JSON for this benchmark controller.\n"
        "Convert the decision into strict JSON only, with no markdown and no prose outside JSON.\n"
        "Schema: {\"skip_remaining_phase\":false,\"extend_current_hold_ms\":0,"
        "\"correction_steps\":[\"w\"],\"reason\":\"short reason\"}\n"
        "Allowed correction tokens: w, a, s, d, left, right, up, down, space, e, wait:1, wait:2.\n"
        f"Return at most {ADAPTIVE_MAX_ACTIONS} correction steps, or [] if no correction is needed.\n\n"
        f"Parse error: {parse_error}\n"
        f"Previous response:\n{bad_response or '<empty>'}\n\n"
        f"Original task context:\n{original_prompt}"
    )


def strict_rotation_json_retry_prompt(original_prompt, bad_response, parse_error):
    return (
        "Your previous response was not valid JSON for this benchmark controller.\n"
        "Convert the decision into strict JSON only, with no markdown and no prose outside JSON.\n"
        "Schema: {\"closed_loop_ok\":true,\"in_place_ok\":true,\"orientation_ok\":true,"
        "\"needs_more_turn\":false,\"correction_steps\":[],\"position_drift\":\"none\","
        "\"reason\":\"short reason\"}\n"
        "Allowed correction tokens: left, right, ←, →, wait:1.\n"
        f"Return at most {ROTATION_LOOP_MAX_ACTIONS} correction steps, or [].\n\n"
        f"Parse error: {parse_error}\nPrevious response:\n{bad_response or '<empty>'}\n\n"
        f"Original task context:\n{original_prompt}"
    )


def strict_final_orientation_json_retry_prompt(original_prompt, bad_response, parse_error):
    return (
        "Your previous response was not valid JSON for this benchmark controller.\n"
        "Convert the decision into strict JSON only, with no markdown and no prose outside JSON.\n"
        "Schema: {\"final_orientation_ok\":true,\"starting_side_ok\":true,\"anchor_visible\":true,"
        "\"needs_more_turn\":false,\"needs_position_correction\":false,\"correction_steps\":[],"
        "\"missing_anchor\":\"\",\"reason\":\"short reason\"}\n"
        "Use only the sequence-consistent correction tokens listed in the original context.\n\n"
        f"Parse error: {parse_error}\nPrevious response:\n{bad_response or '<empty>'}\n\n"
        f"Original task context:\n{original_prompt}"
    )


def clamp_correction_steps(steps):
    if not isinstance(steps, list):
        return []
    actions = []
    for step in steps[:ADAPTIVE_MAX_ACTIONS]:
        if not isinstance(step, str):
            continue
        parsed = parse_step(step)
        for action in parsed:
            if action["type"] == "wait" and action.get("seconds", 0) > 2:
                action["seconds"] = 2
                action["raw"] = "wait:2"
            if action["type"] == "key":
                action["keys"] = [k for k in action["keys"] if k in KEY_MAP]
                if not action["keys"]:
                    continue
            action["adaptive"] = True
            action["step_index"] = "adaptive"
            action["step"] = step
            actions.append(action)
            if len(actions) >= ADAPTIVE_MAX_ACTIONS:
                return actions
    return actions


def clamp_live_adaptive_actions(items):
    if not isinstance(items, list):
        return []
    allowed = {"w", "a", "s", "d", "left", "right", "up", "down", "space", "e"}
    actions = []
    for item in items[:LIVE_HOLD_MAX_ADAPTIVE_ACTIONS]:
        if isinstance(item, str):
            token = item.strip().lower()
            match = re.fullmatch(r"([a-z]+)(?:\*(\d+))?", token)
            if not match or match.group(1) not in allowed:
                continue
            repeat = max(1, min(int(match.group(2) or 1), LIVE_HOLD_ADAPTIVE_MAX_REPEAT))
            key = match.group(1)
            hold_ms = KEY_HOLD_MS * repeat
            raw = f"{key}*{repeat}" if repeat > 1 else key
        elif isinstance(item, list) and item:
            key = str(item[0]).strip().lower()
            if key not in allowed:
                continue
            try:
                hold_ms = int(float(item[1])) if len(item) > 1 else KEY_HOLD_MS
            except (TypeError, ValueError):
                hold_ms = KEY_HOLD_MS
            hold_ms = max(LIVE_HOLD_ADAPTIVE_MIN_MS, min(hold_ms, LIVE_HOLD_ADAPTIVE_MAX_MS))
            repeat = max(1, int(round(hold_ms / KEY_HOLD_MS)))
            raw = f"live_adaptive({key},{hold_ms}ms)"
        else:
            continue
        actions.append({
            "type": "key",
            "keys": [key],
            "raw": raw,
            "repeat": repeat,
            "hold_ms": hold_ms,
            "adaptive": True,
            "step_index": "live_adaptive",
            "step": key,
        })
    return actions


def clamp_turn_correction_steps(steps, max_actions, preferred_turn=None, marker="turn_correction"):
    if not isinstance(steps, list):
        return []
    allowed = {"left", "right", "←", "→", "wait:1"}
    if preferred_turn in {"left", "←"}:
        preferred = {"left", "←", "wait:1"}
    elif preferred_turn in {"right", "→"}:
        preferred = {"right", "→", "wait:1"}
    else:
        preferred = allowed
    actions = []
    for step in steps:
        if len(actions) >= max_actions:
            break
        if not isinstance(step, str):
            continue
        step = step.strip()
        if step not in allowed or step not in preferred:
            continue
        for action in parse_step(step):
            if action["type"] == "key":
                action["keys"] = [key for key in action["keys"] if key in {"left", "right", "←", "→"}]
                if not action["keys"]:
                    continue
            action["adaptive"] = True
            action[marker] = True
            action["step_index"] = marker
            action["step"] = step
            actions.append(action)
    return actions[:max_actions]


def sequence_correction_tokens(actions):
    present = {
        key
        for action in actions
        if action.get("type") == "key"
        for key in action.get("keys", [])
        if key in KEY_MAP
    }
    if present & {"left", "←"}:
        present.update({"left", "←"})
    if present & {"right", "→"}:
        present.update({"right", "→"})
    if present & {"space", "jump", "ascend"}:
        present.update({"space", "jump", "ascend"})
    return [
        token
        for token in (
            "w", "a", "s", "d", "q", "e", "u", "j", "up", "down",
            "left", "right", "←", "→", "space", "jump", "ascend", "wait:1",
        )
        if token == "wait:1" or token in present
    ]


def clamp_sequence_correction_steps(steps, max_actions, sequence_actions, marker="sequence_correction"):
    if not isinstance(steps, list):
        return []
    allowed = set(sequence_correction_tokens(sequence_actions))
    actions = []
    for step in steps:
        if len(actions) >= max_actions:
            break
        if not isinstance(step, str):
            continue
        step = step.strip()
        if step not in allowed:
            continue
        for action in parse_step(step):
            if action["type"] == "key":
                action["keys"] = [key for key in action["keys"] if key in allowed and key in KEY_MAP]
                if not action["keys"]:
                    continue
            action["adaptive"] = True
            action[marker] = True
            action["step_index"] = marker
            action["step"] = step
            actions.append(action)
    return actions[:max_actions]


def is_turn_action(action):
    return action.get("type") == "key" and action.get("keys") and all(
        key in {"left", "right", "←", "→"} for key in action.get("keys", [])
    )


def task_requests_360_rotation(task):
    text = f"{task.get('prompt') or ''} {' '.join(task.get('action_sequence_steps') or [])}".lower()
    return bool(
        "360" in text
        or "full circle" in text
        or "one full circle" in text
        or "rotate all the way around" in text
    )


def is_360_rotation_turn_action(task, action):
    return task_requests_360_rotation(task) and is_turn_action(action)


def gc007_fixed_extra(task, action):
    if task.get("task_id") != "GC007" or action.get("type") != "key":
        return None
    keys = [key.lower() for key in action.get("keys", [])]
    if keys == ["w"] and GC007_FORWARD_EXTRA_UNITS > 0:
        return {
            "phase": "gc007_forward_fixed_extra",
            "units": GC007_FORWARD_EXTRA_UNITS,
            "hold_ms": GC007_FORWARD_EXTRA_UNITS * KEY_HOLD_MS,
            "step": "continue forward until the overhead Primemall sign leaves view",
        }
    if keys == ["s"] and GC007_RETURN_EXTRA_UNITS > 0:
        return {
            "phase": "gc007_return_fixed_extra",
            "units": GC007_RETURN_EXTRA_UNITS,
            "hold_ms": GC007_RETURN_EXTRA_UNITS * KEY_HOLD_MS,
            "step": "match the extra forward distance while returning to the start",
        }
    return None


def apply_task_action_overrides(task, actions):
    overrides = []
    if task.get("task_id") == "GC001":
        for index, action in enumerate(actions):
            keys = [key.lower() for key in action.get("keys", [])]
            if action.get("type") == "key" and keys == ["w"]:
                original_hold_ms = action_hold_ms(action)
                action["hold_ms"] = GC001_INITIAL_W_HOLD_MS
                action["hold_token"] = f"hold(W,{GC001_INITIAL_W_HOLD_MS}ms)"
                action["task_override"] = "gc001_initial_w"
                overrides.append({
                    "action_index": index,
                    "name": "gc001_initial_w",
                    "original_hold_ms": original_hold_ms,
                    "hold_ms": GC001_INITIAL_W_HOLD_MS,
                })
                break
    return overrides


def is_rotation_loop_task(task, actions):
    text = f"{task.get('prompt') or ''} {' '.join(task.get('action_sequence_steps') or [])}".lower()
    has_loop_language = (
        "360" in text
        or "rotate" in text
        or "rotates" in text
        or "spin" in text
        or "turn around in place" in text
        or ("in place" in text and ("survey" in text or "look around" in text))
    )
    key_actions = [action for action in actions if action.get("type") == "key"]
    return bool(key_actions and has_loop_language and all(is_turn_action(action) for action in key_actions))


def final_turn_phase_actions(actions):
    key_actions = [action for action in actions if action.get("type") == "key"]
    if not key_actions or not is_turn_action(key_actions[-1]):
        return []
    final_step_index = key_actions[-1].get("step_index")
    phase = []
    for action in reversed(actions):
        if action.get("step_index") != final_step_index:
            break
        phase.append(action)
    phase.reverse()
    return phase if phase and all(is_turn_action(action) for action in phase) else []


def is_final_orientation_task(task, actions):
    prompt = (task.get("prompt") or "").lower()
    return bool(
        final_turn_phase_actions(actions)
        and any(
            phrase in prompt
            for phrase in (
                "original direction", "original orientation", "face the original",
                "look in the original", "look into the original",
            )
        )
    )


def is_wait_observe_task(task):
    prompt = re.sub(r"\s+", " ", (task.get("prompt") or "").strip()).lower()
    prompt = prompt.rstrip(".!?")
    return prompt == "wait and observe"


def dominant_turn_key(actions):
    counts = {"left": 0, "right": 0}
    for action in actions:
        for key in action.get("keys", []):
            if key in {"left", "←"}:
                counts["left"] += 1
            elif key in {"right", "→"}:
                counts["right"] += 1
    if counts["right"] >= counts["left"] and counts["right"]:
        return "→"
    return "←" if counts["left"] else None


_KIGRESS_CLIENT = None
_KIGRESS_CLIENT_LOCK = threading.Lock()
_LIVE_HOLD_REQUEST_LOCK = threading.Lock()
_CONTROLLER_RESPONSE_MODELS = []


def controller_config():
    config = configured_agent()
    validate_agent_config(config)
    return config


def controller_model():
    return controller_config().model


def controller_request_url():
    config = controller_config()
    return config.base_url if config.transport in {"anthropic", "gemini_generate_content"} else f"{config.base_url}/chat/completions"


def kigress_client():
    global _KIGRESS_CLIENT
    if _KIGRESS_CLIENT is None:
        with _KIGRESS_CLIENT_LOCK:
            if _KIGRESS_CLIENT is None:
                config = controller_config()
                _KIGRESS_CLIENT = httpx.Client(
                    trust_env=config.trust_env,
                    verify=config.verify_tls,
                    timeout=None,
                    limits=httpx.Limits(max_connections=8, max_keepalive_connections=4, keepalive_expiry=60),
                )
    return _KIGRESS_CLIENT


def close_kigress_client():
    global _KIGRESS_CLIENT
    if _KIGRESS_CLIENT is not None:
        _KIGRESS_CLIENT.close()
        _KIGRESS_CLIENT = None


atexit.register(close_kigress_client)


def agent_chat_post(payload, timeout_s):
    config = controller_config()
    response = post_chat_completion(kigress_client(), config, payload, timeout_s)
    try:
        data = response.json()
        response_model = data.get("model") or data.get("modelVersion")
    except Exception:
        response_model = None
    if response_model and response_model not in _CONTROLLER_RESPONSE_MODELS:
        _CONTROLLER_RESPONSE_MODELS.append(response_model)
    return response


def deployed_controller_model():
    return _CONTROLLER_RESPONSE_MODELS[-1] if _CONTROLLER_RESPONSE_MODELS else controller_model()


def require_agent_controller():
    missing = []
    if httpx is None:
        missing.append("httpx package")
    try:
        config = controller_config()
    except Exception as exc:
        config = None
        missing.append(str(exc))
    if not ADAPTIVE_CORRECTION:
        missing.append("HAPPYOYSTER_ADAPTIVE_CORRECTION=1")
    if not LIVE_HOLD_STOP_CHECK:
        missing.append("HAPPYOYSTER_LIVE_HOLD_STOP_CHECK=1")
    if not ROTATION_LOOP_CHECK:
        missing.append("HAPPYOYSTER_ROTATION_LOOP_CHECK=1")
    if not FINAL_ORIENTATION_CHECK:
        missing.append("HAPPYOYSTER_FINAL_ORIENTATION_CHECK=1")
    if missing:
        raise RuntimeError(
            "HappyOyster preset_agent requires a live Agent controller: "
            + ", ".join(missing)
        )
    payload = {
        "model": config.model,
        "max_completion_tokens": 8,
        "messages": [{"role": "user", "content": "Reply with exactly OK."}],
    }
    last_error = None
    for attempt in range(1, max(1, KIGRESS_PREFLIGHT_ATTEMPTS) + 1):
        try:
            response = agent_chat_post(payload, KIGRESS_PREFLIGHT_TIMEOUT_S)
            if response.status_code < 400:
                return {
                    "provider": config.provider,
                    "configured_model": config.model,
                    "response_model": deployed_controller_model(),
                    "transport": config.transport,
                    "http_status": response.status_code,
                    "attempt": attempt,
                }
            last_error = f"HTTP {response.status_code}: {response.text[:300]}"
        except Exception as exc:
            last_error = repr(exc)
        if attempt < KIGRESS_PREFLIGHT_ATTEMPTS:
            print(f"Agent preflight attempt {attempt} failed: {last_error}; retrying", flush=True)
            time.sleep(attempt)
    raise RuntimeError(
        f"Agent API preflight failed after {KIGRESS_PREFLIGHT_ATTEMPTS} attempts: {last_error}"
    )


def control_agent_policy(task):
    lines = [
        "Controller policy: follow the dataset action sequence as the primary source of truth. "
        "Use the task goal and current screenshot to judge whether the current phase needs more hold duration, "
        "a small alignment correction, or a safe trim of the current hold."
    ]
    if (task.get("group") or "").upper() == "IF":
        lines.append(
            "IF task obstacle policy: if the task explicitly says to walk, drive, jump, climb, push, enter, "
            "or move into/through a target area, do not stop merely because an obstacle, edge, water surface, "
            "doorway, fence, wall, furniture, grass, bushes, or other object is directly ahead. Treat those "
            "elements as part of the requested interaction unless going around is explicitly required."
        )
    return "\n".join(lines)


def action_hold_ms(action):
    if action.get("type") == "wait":
        return int(float(action.get("seconds", 0)) * 1000)
    if action.get("hold_ms") is not None:
        return int(action["hold_ms"])
    return KEY_HOLD_MS


def action_token(action):
    if action.get("type") == "wait":
        return f"wait:{action.get('seconds', 1)}"
    return action.get("raw") or "+".join(action.get("keys", [])) or action.get("type", "?")


def hold_token_for_actions(actions):
    if not actions:
        return ""
    first = actions[0]
    if first.get("type") == "wait":
        return f"wait({sum(action_hold_ms(action) for action in actions)}ms)"
    keys = "+".join(display_key_token(key) for key in first.get("keys", []))
    hold_ms = sum(action_hold_ms(action) for action in actions)
    return f"hold({keys},{hold_ms}ms)"


def actions_to_hold_tokens(actions):
    return [hold_token_for_actions([action]) if action.get("type") in {"key", "wait"} else action_token(action) for action in actions]


def phase_bounds(actions, index):
    start = index
    while start > 0 and actions[start - 1].get("step_index") == actions[index].get("step_index"):
        start -= 1
    end = index + 1
    while end < len(actions) and actions[end].get("step_index") == actions[index].get("step_index"):
        end += 1
    return start, end


def make_hold_extension_action(base_action, extend_ms):
    action = dict(base_action)
    action["raw"] = f"extend({'+'.join(display_key_token(k) for k in action.get('keys', []))},{extend_ms}ms)"
    action["hold_ms"] = int(extend_ms)
    action["hold_token"] = hold_token_for_actions([action])
    action["adaptive"] = True
    action["step_index"] = "adaptive_extend"
    action["step"] = action["raw"]
    return action


def build_live_hold_context(task, result, actions, index):
    if not actions or index >= len(actions):
        return None
    phase_start, phase_end = phase_bounds(actions, index)
    context = {
        "task": task,
        "result": result,
        "phase_index": actions[index].get("step_index"),
        "phase_step": actions[index].get("step"),
        "hold_token": hold_token_for_actions([actions[index]]),
        "remaining_phase_actions": actions_to_hold_tokens(actions[index + 1:phase_end]),
        "upcoming_dataset_actions": actions_to_hold_tokens(actions[phase_end:min(len(actions), phase_end + 24)]),
    }
    if is_360_rotation_turn_action(task, actions[index]) or gc007_fixed_extra(task, actions[index]):
        # Seeing the starting object again is not enough to prove a full 360-degree turn.
        # Protected task segments must complete their dataset hold before accepting keyup.
        context["minimum_stop_ms"] = action_hold_ms(actions[index])
        context["full_hold_required"] = True
    return context


def record_live_hold_skip(result, actions, current_index, reason_info):
    _, phase_end = phase_bounds(actions, current_index)
    skipped_actions = actions[current_index + 1:phase_end]
    if not skipped_actions:
        return current_index
    skip_record = {
        "phase_index": actions[current_index].get("step_index"),
        "phase_step": actions[current_index].get("step"),
        "after_action_index": len(result.get("executed_actions", [])),
        "skipped_count": len(skipped_actions),
        "skipped_hold_sequence": "; ".join(actions_to_hold_tokens(skipped_actions)),
        "skipped_actions": skipped_actions,
        "reason": reason_info.get("reason") if reason_info else None,
        "live_hold_stop": reason_info,
    }
    if REQUIRE_FULL_ACTION_SEQUENCE:
        result.setdefault("live_hold_skip_recommendations", []).append(skip_record)
        return current_index
    result.setdefault("live_hold_skipped_actions", []).append(skip_record)
    return phase_end - 1


def record_adaptive_phase_skip(result, actions, current_index, reason_info, record_key="adaptive_skipped_actions"):
    _, phase_end = phase_bounds(actions, current_index)
    skipped_actions = actions[current_index + 1:phase_end]
    if not skipped_actions:
        return current_index
    record = {
        "phase_index": actions[current_index].get("step_index"),
        "phase_step": actions[current_index].get("step"),
        "after_action_index": len(result.get("executed_actions", [])),
        "skipped_count": len(skipped_actions),
        "skipped_hold_sequence": "; ".join(actions_to_hold_tokens(skipped_actions)),
        "skipped_actions": skipped_actions,
        "reason": reason_info.get("reason") if reason_info else None,
    }
    if REQUIRE_FULL_ACTION_SEQUENCE:
        result.setdefault(f"{record_key}_recommendations", []).append(record)
        return current_index
    result.setdefault(record_key, []).append(record)
    return phase_end - 1


def request_live_hold_stop_check(task, result, context, image_bytes, request_slot_acquired=False):
    if not LIVE_HOLD_STOP_CHECK or not ADAPTIVE_CORRECTION:
        if request_slot_acquired:
            _LIVE_HOLD_REQUEST_LOCK.release()
        return {"enabled": False, "stop_current_hold": False}
    started_at = time.perf_counter()
    info = {
        "enabled": True,
        "phase_index": context.get("phase_index"),
        "phase_step": context.get("phase_step"),
        "hold_token": context.get("hold_token"),
        "elapsed_hold_ms": context.get("elapsed_hold_ms"),
        "planned_hold_ms": context.get("planned_hold_ms"),
        "model": controller_model(),
        "request_url": controller_request_url(),
        "transport": controller_config().transport,
        "stop_current_hold": False,
        "skip_remaining_phase": False,
        "screenshot": context.get("screenshot"),
    }
    if httpx is None:
        if request_slot_acquired:
            _LIVE_HOLD_REQUEST_LOCK.release()
        info["error"] = "httpx is not installed"
        return info
    b64 = base64.b64encode(image_bytes).decode("ascii")
    recent = [
        item.get("hold_token") or item.get("raw") or "+".join(item.get("keys", []))
        for item in result.get("executed_actions", [])[-6:]
    ]
    prompt = (
        "Control a held key in HappyOyster from the screenshot. Be conservative. "
        "Choose k=keep, s=stop, or e=extend this same key. ms is extra hold time for e. "
        "skip=1 skips remaining repeated actions in this phase. next contains at most two correction tokens, "
        "such as [\"a\",\"w*2\"], executed after release. One token holds its key for about 1 second; "
        "w*3 means one continuous 3-second W hold. Allowed keys: w,a,s,d,left,right,up,down,space,e.\n"
        f"Scene: {task_environmental_caption(task)[:400]}\n"
        f"Goal: {(task.get('prompt') or '')[:400]}\n"
        f"Perspective: {task.get('perspective')}\n"
        f"{control_agent_policy(task)}\n"
        f"Phase: {context.get('phase_step')}\n"
        f"Hold: {context.get('hold_token')}; elapsed={context.get('elapsed_hold_ms')}ms; "
        f"planned={context.get('planned_hold_ms')}ms; earliest_stop={LIVE_HOLD_STOP_MIN_MS}ms.\n"
        f"Same-phase remaining: {context.get('remaining_phase_actions')[:8]}\n"
        f"Upcoming: {context.get('upcoming_dataset_actions')[:8]}\n"
        f"Recent: {recent}\n"
        "Return JSON only: {\"a\":\"k\",\"ms\":0,\"skip\":0,\"next\":[]}"
    )
    payload = {
        "model": controller_model(),
        "max_completion_tokens": LIVE_HOLD_MAX_TOKENS,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                ],
            }
        ],
    }
    try:
        resp = agent_chat_post(payload, LIVE_HOLD_TIMEOUT_S)
        info["response_model"] = deployed_controller_model()
        info["http_status"] = resp.status_code
        info["elapsed_s"] = resp.elapsed.total_seconds()
        info["wall_elapsed_s"] = time.perf_counter() - started_at
        if resp.status_code >= 400:
            info["error"] = resp.text[:1000] or f"HTTP {resp.status_code}"
            return info
        raw = extract_chat_text(resp.json())
        info["raw_response"] = raw
        parsed = extract_json_object(raw)
        decision = str(parsed.get("a") or "").strip().lower()
        decision = {"keep": "k", "stop": "s", "extend": "e"}.get(decision, decision)
        if decision not in {"k", "s", "e"}:
            confidence = str(parsed.get("confidence") or "").strip().lower()
            decision = "s" if parsed.get("stop_current_hold") and confidence in {"medium", "high", "certain"} else "k"
        try:
            extend_ms = int(float(parsed.get("ms") or parsed.get("extend_current_hold_ms") or 0))
        except (TypeError, ValueError):
            extend_ms = 0
        extend_ms = max(0, min(extend_ms, ADAPTIVE_EXTEND_HOLD_MAX_MS)) if decision == "e" else 0
        info["decision"] = decision
        info["stop_current_hold"] = decision == "s"
        info["extend_current_hold_ms"] = extend_ms
        info["skip_remaining_phase"] = bool(parsed.get("skip") or parsed.get("skip_remaining_phase")) and decision == "s"
        info["actions"] = clamp_live_adaptive_actions(parsed.get("next") or [])
        return info
    except Exception as exc:
        info["error"] = repr(exc)
        info["wall_elapsed_s"] = time.perf_counter() - started_at
        return info
    finally:
        if request_slot_acquired:
            _LIVE_HOLD_REQUEST_LOCK.release()


def request_adaptive_correction(
    page,
    task,
    result,
    phase_index,
    phase_step,
    outdir,
    *,
    phase_done=True,
    remaining_in_phase=0,
    remaining_phase_actions=None,
    allow_hold_extension=False,
    current_hold_actions=None,
    upcoming_dataset_actions=None,
):
    if not ADAPTIVE_CORRECTION:
        return {"enabled": False, "actions": []}
    shot_path = outdir / f"adaptive_phase_{phase_index}.jpg"
    remaining_phase_actions = remaining_phase_actions or []
    upcoming_dataset_actions = upcoming_dataset_actions or []
    try:
        img_bytes, screenshot_meta = capture_agent_image(
            page,
            quality=ADAPTIVE_SCREENSHOT_QUALITY,
            max_width=ADAPTIVE_SCREENSHOT_MAX_WIDTH,
            max_height=ADAPTIVE_SCREENSHOT_MAX_HEIGHT,
            timeout=max(LIVE_HOLD_SCREENSHOT_TIMEOUT_MS, 3000),
            path=shot_path,
        )
    except Exception as exc:
        return {
            "enabled": True,
            "phase_index": phase_index,
            "phase_step": phase_step,
            "phase_done": phase_done,
            "remaining_in_phase": remaining_in_phase,
            "remaining_phase_actions": remaining_phase_actions,
            "allow_hold_extension": allow_hold_extension,
            "current_hold_action": hold_token_for_actions(current_hold_actions or []),
            "upcoming_dataset_actions": upcoming_dataset_actions,
            "skip_remaining_phase": False,
            "extend_current_hold_ms": 0,
            "screenshot": str(shot_path),
            "screenshot_error": repr(exc),
            "model": controller_model(),
            "actions": [],
        }
    info = {
        "enabled": True,
        "phase_index": phase_index,
        "phase_step": phase_step,
        "phase_done": phase_done,
        "remaining_in_phase": remaining_in_phase,
        "remaining_phase_actions": remaining_phase_actions,
        "allow_hold_extension": allow_hold_extension,
        "current_hold_action": hold_token_for_actions(current_hold_actions or []),
        "upcoming_dataset_actions": upcoming_dataset_actions,
        "skip_remaining_phase": False,
        "extend_current_hold_ms": 0,
        "screenshot": str(shot_path),
        "screenshot_meta": screenshot_meta,
        "model": controller_model(),
        "request_url": controller_request_url(),
        "transport": controller_config().transport,
        "actions": [],
    }
    if httpx is None:
        info["error"] = "httpx is not installed"
        return info
    b64 = base64.b64encode(img_bytes).decode("ascii")
    recent = [
        item.get("hold_token") or item.get("raw") or "+".join(item.get("keys", []))
        for item in result.get("executed_actions", [])[-12:]
    ]
    extension_instruction = ""
    if phase_done and allow_hold_extension and current_hold_actions:
        extension_instruction = (
            f"The just-executed hold was {hold_token_for_actions(current_hold_actions)}. "
            "If the current screenshot shows this hold was too short to reach the needed position for the task "
            "or for the next phase, return extend_current_hold_ms with the extra duration to keep holding the "
            f"SAME key(s), from 0 to {ADAPTIVE_EXTEND_HOLD_MAX_MS}ms. Use 0 if no extension is needed. "
            "Prefer extension for insufficient travel distance; use correction_steps only for small alignment "
            "or facing fixes after movement distance is sufficient.\n"
        )
    if phase_done:
        timing_instruction = (
            "The dataset action phase has just completed. Inspect the current screenshot and decide whether the "
            "same hold should be extended, or whether a very small correction is needed before continuing.\n"
            "Set skip_remaining_phase=false because this phase has no remaining actions.\n"
            f"{extension_instruction}"
        )
    else:
        timing_instruction = (
            "The dataset action phase is still in progress. Decide whether its remaining repeated actions should "
            "be skipped because continuing would overshoot, collide, drift away, or make the task worse.\n"
            f"There are {remaining_in_phase} logical actions remaining in this phase.\n"
            f"Remaining same-phase actions: {remaining_phase_actions}.\n"
            "Set skip_remaining_phase=true only when the current phase goal is visibly satisfied or continuing is harmful. "
            "Only return correction_steps with a true skip decision and only for a tiny alignment fix.\n"
        )
    prompt = (
        "You are a conservative action controller for a HappyOyster benchmark run.\n"
        f"{timing_instruction}"
        f"Environment caption: {task_environmental_caption(task)}\n"
        f"Task goal: {task['prompt']}\n"
        f"Perspective: {task.get('perspective')}\n"
        f"{control_agent_policy(task)}\n"
        f"Current dataset phase: {phase_step}\n"
        f"Recent executed actions: {recent}\n"
        f"Upcoming dataset actions after this phase: {upcoming_dataset_actions}\n\n"
        "Allowed correction tokens: w, a, s, d, left, right, up, down, space, e, wait:1, wait:2.\n"
        f"Return at most {ADAPTIVE_MAX_ACTIONS} correction steps. Use [] if no correction is needed. "
        "Do not invent a new plan, do not repeat the whole dataset sequence, and do not exceed small alignment fixes.\n"
        "Return only strict JSON in this shape:\n"
        '{"skip_remaining_phase":false,"extend_current_hold_ms":0,"correction_steps":["w"],"reason":"short reason"}'
    )
    payload = {
        "model": controller_model(),
        "max_completion_tokens": 220,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                ],
            }
        ],
    }
    try:
        resp = agent_chat_post(payload, ADAPTIVE_TIMEOUT_S)
        info["response_model"] = deployed_controller_model()
        info["http_status"] = resp.status_code
        info["elapsed_s"] = resp.elapsed.total_seconds()
        if resp.status_code >= 400:
            info["error"] = resp.text[:1000] or f"HTTP {resp.status_code}"
            return info
        raw = extract_chat_text(resp.json())
        info["raw_response"] = raw
        try:
            parsed = extract_json_object(raw)
        except json.JSONDecodeError as parse_exc:
            retry_payload = {
                "model": controller_model(),
                "max_completion_tokens": 160,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": strict_adaptive_json_retry_prompt(prompt, raw, repr(parse_exc))},
                            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                        ],
                    }
                ],
            }
            retry_resp = agent_chat_post(retry_payload, ADAPTIVE_TIMEOUT_S)
            info["retry_response_model"] = deployed_controller_model()
            info["retry_http_status"] = retry_resp.status_code
            info["retry_elapsed_s"] = retry_resp.elapsed.total_seconds()
            if retry_resp.status_code >= 400:
                info["retry_error"] = retry_resp.text[:1000] or f"HTTP {retry_resp.status_code}"
                return info
            retry_raw = extract_chat_text(retry_resp.json())
            info["retry_raw_response"] = retry_raw
            parsed = extract_json_object(retry_raw)
        try:
            extend_ms = int(float(parsed.get("extend_current_hold_ms") or 0))
        except (TypeError, ValueError):
            extend_ms = 0
        if not allow_hold_extension:
            extend_ms = 0
        info["skip_remaining_phase"] = bool(parsed.get("skip_remaining_phase")) and not phase_done
        info["extend_current_hold_ms"] = max(0, min(extend_ms, ADAPTIVE_EXTEND_HOLD_MAX_MS))
        info["reason"] = parsed.get("reason")
        info["correction_steps"] = parsed.get("correction_steps") or []
        if phase_done or info["skip_remaining_phase"]:
            info["actions"] = clamp_correction_steps(info["correction_steps"])
        return info
    except Exception as exc:
        info["error"] = repr(exc)
        return info


def request_two_image_json(prompt, before_b64, after_b64, max_tokens, retry_prompt_builder):
    payload = {
        "model": controller_model(),
        "max_completion_tokens": max_tokens,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{before_b64}"}},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{after_b64}"}},
            ],
        }],
    }
    info = {}
    try:
        response = agent_chat_post(payload, ADAPTIVE_TIMEOUT_S)
        info["response_model"] = deployed_controller_model()
        info["http_status"] = response.status_code
        info["elapsed_s"] = response.elapsed.total_seconds()
        if response.status_code >= 400:
            info["error"] = response.text[:1000] or f"HTTP {response.status_code}"
            return info
        raw = extract_chat_text(response.json())
        info["raw_response"] = raw
        try:
            info["parsed"] = extract_json_object(raw)
            return info
        except json.JSONDecodeError as parse_exc:
            info["parse_error"] = repr(parse_exc)
            retry_payload = {
                "model": controller_model(),
                "max_completion_tokens": 180,
                "messages": [{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": retry_prompt_builder(prompt, raw, repr(parse_exc))},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{before_b64}"}},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{after_b64}"}},
                    ],
                }],
            }
            retry = agent_chat_post(retry_payload, ADAPTIVE_TIMEOUT_S)
            info["retry_response_model"] = deployed_controller_model()
            info["retry_http_status"] = retry.status_code
            info["retry_elapsed_s"] = retry.elapsed.total_seconds()
            if retry.status_code >= 400:
                info["retry_error"] = retry.text[:1000] or f"HTTP {retry.status_code}"
                return info
            retry_raw = extract_chat_text(retry.json())
            info["retry_raw_response"] = retry_raw
            info["parsed"] = extract_json_object(retry_raw)
            return info
    except Exception as exc:
        info["error"] = repr(exc)
        return info


def request_rotation_loop_check(
    page,
    task,
    result,
    outdir,
    before_path,
    attempt_index=0,
    *,
    purpose="final",
    completed_in_phase=None,
    remaining_in_phase=None,
):
    after_prefix = "rotation_loop_mid" if purpose == "mid_phase" else "rotation_loop_after"
    after_path = outdir / f"{after_prefix}_{attempt_index:02d}.jpg"
    after_bytes = page.screenshot(path=str(after_path), type="jpeg", quality=80, full_page=True)
    before_b64 = base64.b64encode(Path(before_path).read_bytes()).decode("ascii")
    after_b64 = base64.b64encode(after_bytes).decode("ascii")
    preferred_turn = dominant_turn_key(result.get("expanded_actions", [])) or "→"
    recent = [
        item.get("raw") or "+".join(item.get("keys", []))
        for item in result.get("executed_actions", [])[-20:]
    ]
    if purpose == "mid_phase":
        timing = (
            "This is a mid-phase check before all repeated turn actions have been consumed. If image 2 has already "
            "returned to the starting position and orientation in image 1, set closed_loop_ok, in_place_ok, and "
            "orientation_ok to true so the runner can skip the remaining repeats. Otherwise return no correction; "
            "the dataset turns will continue.\n"
            f"Completed turn actions: {completed_in_phase}; remaining: {remaining_in_phase}.\n"
        )
    else:
        timing = (
            "This is the final check. If the loop or original orientation is slightly incomplete, set "
            "needs_more_turn=true and return a few extra turns in the preferred direction.\n"
        )
    prompt = (
        "You are checking a closed-loop 360-degree in-place rotation in a HappyOyster benchmark run.\n"
        "Compare image 1 before controls with image 2 after the executed turns. The character/camera should complete "
        "one full circle, remain near the starting position, and face the original view. Small animation and camera "
        "jitter are acceptable.\n\n"
        f"Environment caption: {task_environmental_caption(task)}\n"
        f"Task goal: {task.get('prompt')}\n"
        f"Perspective: {task.get('perspective')}\n"
        f"Dataset action sequence: {task.get('action_sequence')}\n"
        f"Recent executed actions: {recent}\n"
        f"Preferred extra turn direction: {preferred_turn}\n\n"
        f"{timing}"
        "If continuing the same dataset turn direction can complete the intended circle despite some drift, return "
        f"1-{ROTATION_LOOP_MAX_ACTIONS} turn tokens in that direction. Do not invent translation or reverse turns.\n"
        "Return only strict JSON:\n"
        '{"closed_loop_ok":true,"in_place_ok":true,"orientation_ok":true,'
        '"needs_more_turn":false,"correction_steps":[],"position_drift":"none","reason":"short reason"}'
    )
    info = {
        "enabled": True,
        "attempt_index": attempt_index,
        "purpose": purpose,
        "completed_in_phase": completed_in_phase,
        "remaining_in_phase": remaining_in_phase,
        "before_screenshot": str(before_path),
        "after_screenshot": str(after_path),
        "preferred_turn": preferred_turn,
        "model": controller_model(),
        "request_url": controller_request_url(),
        "transport": controller_config().transport,
        "actions": [],
    }
    response_info = request_two_image_json(
        prompt, before_b64, after_b64, 260, strict_rotation_json_retry_prompt
    )
    info.update(response_info)
    parsed = response_info.get("parsed")
    if not parsed:
        return info
    steps = parsed.get("correction_steps") or []
    info.update({
        "closed_loop_ok": bool(parsed.get("closed_loop_ok")),
        "in_place_ok": bool(parsed.get("in_place_ok")),
        "orientation_ok": bool(parsed.get("orientation_ok")),
        "needs_more_turn": bool(parsed.get("needs_more_turn")),
        "position_drift": parsed.get("position_drift"),
        "reason": parsed.get("reason"),
        "correction_steps": steps,
    })
    if (
        purpose != "mid_phase"
        and info["needs_more_turn"]
        and (not info["closed_loop_ok"] or not info["in_place_ok"] or not info["orientation_ok"])
    ):
        info["actions"] = clamp_turn_correction_steps(
            steps, ROTATION_LOOP_MAX_ACTIONS, preferred_turn, marker="closed_loop_rotation"
        )
    return info


def request_final_orientation_check(page, task, result, outdir, before_path, attempt_index=0):
    after_path = outdir / f"final_orientation_after_{attempt_index:02d}.jpg"
    after_bytes = page.screenshot(path=str(after_path), type="jpeg", quality=80, full_page=True)
    before_b64 = base64.b64encode(Path(before_path).read_bytes()).decode("ascii")
    after_b64 = base64.b64encode(after_bytes).decode("ascii")
    final_phase = final_turn_phase_actions(result.get("expanded_actions", []))
    preferred_turn = dominant_turn_key(final_phase) or dominant_turn_key(result.get("expanded_actions", [])) or "→"
    sequence_tokens = sequence_correction_tokens(result.get("expanded_actions", []))
    recent = [
        item.get("raw") or "+".join(item.get("keys", []))
        for item in result.get("executed_actions", [])[-20:]
    ]
    prompt = (
        "You are checking the final orientation and position of a HappyOyster benchmark run.\n"
        "Compare image 1 immediately before controls with image 2 after the dataset actions and corrections. The "
        "final view should face the same general direction and show the same distinctive forward anchors. Natural "
        "animation and small perspective differences are acceptable when the character is in the intended side/area.\n\n"
        "Bridge rule: crossing or circling bridge tasks should still show the bridge or its distinctive structure; "
        "otherwise anchor_visible must be false.\n\n"
        f"Environment caption: {task_environmental_caption(task)}\n"
        f"Task goal: {task.get('prompt')}\n"
        f"Perspective: {task.get('perspective')}\n"
        f"Dataset action sequence: {task.get('action_sequence')}\n"
        f"Recent executed actions: {recent}\n"
        f"Preferred extra turn direction: {preferred_turn}\n"
        f"Allowed sequence-consistent correction tokens: {sequence_tokens}\n\n"
        "If position is correct but the camera has not turned far enough, set needs_more_turn=true and return only "
        f"1-{FINAL_ORIENTATION_MAX_ACTIONS} preferred-direction turns. If the character is on the wrong side/area "
        "but a short continuation of the existing dataset trajectory can repair it, set starting_side_ok=false, "
        "needs_position_correction=true, and return only tokens from the sequence-consistent list. Do not invent "
        "a route or reverse the dataset trajectory. If repair is unclear, return no correction.\n"
        "Return only strict JSON:\n"
        '{"final_orientation_ok":true,"starting_side_ok":true,"anchor_visible":true,'
        '"needs_more_turn":false,"needs_position_correction":false,"correction_steps":[],'
        '"missing_anchor":"","reason":"short reason"}'
    )
    info = {
        "enabled": True,
        "attempt_index": attempt_index,
        "before_screenshot": str(before_path),
        "after_screenshot": str(after_path),
        "preferred_turn": preferred_turn,
        "allowed_sequence_tokens": sequence_tokens,
        "model": controller_model(),
        "request_url": controller_request_url(),
        "transport": controller_config().transport,
        "actions": [],
    }
    response_info = request_two_image_json(
        prompt, before_b64, after_b64, 260, strict_final_orientation_json_retry_prompt
    )
    info.update(response_info)
    parsed = response_info.get("parsed")
    if not parsed:
        return info
    steps = parsed.get("correction_steps") or []
    info.update({
        "final_orientation_ok": bool(parsed.get("final_orientation_ok")),
        "starting_side_ok": bool(parsed.get("starting_side_ok")),
        "anchor_visible": bool(parsed.get("anchor_visible")),
        "needs_more_turn": bool(parsed.get("needs_more_turn")),
        "needs_position_correction": bool(parsed.get("needs_position_correction")),
        "missing_anchor": parsed.get("missing_anchor"),
        "reason": parsed.get("reason"),
        "correction_steps": steps,
    })
    if (
        info["needs_more_turn"]
        and info["starting_side_ok"]
        and (not info["final_orientation_ok"] or not info["anchor_visible"])
    ):
        info["actions"] = clamp_turn_correction_steps(
            steps, FINAL_ORIENTATION_MAX_ACTIONS, preferred_turn, marker="final_orientation"
        )
    elif info["needs_position_correction"] and not info["starting_side_ok"]:
        info["actions"] = clamp_sequence_correction_steps(
            steps, FINAL_ORIENTATION_MAX_ACTIONS, result.get("expanded_actions", []), marker="final_position"
        )
    return info


def live_hold_check_enabled(action, hold_ms, context):
    return (
        LIVE_HOLD_STOP_CHECK
        and ADAPTIVE_CORRECTION
        and context
        and action.get("type") == "key"
        and not action.get("adaptive")
        and hold_ms >= LIVE_HOLD_REQUEST_MIN_MS + LIVE_HOLD_MIN_REMAINING_MS
        and LIVE_HOLD_CHECK_INTERVAL_MS > 0
        and KIGRESS_BASE_URL
        and KIGRESS_API_KEY
    )


def find_world_element(page):
    for selector in ("canvas", "video"):
        elem = page.query_selector(selector)
        if elem and elem.is_visible():
            box = elem.bounding_box()
            if box and box["width"] > 100 and box["height"] > 100:
                return elem, box
    return None, None


def capture_agent_image(
    page,
    *,
    quality=LIVE_HOLD_SCREENSHOT_QUALITY,
    max_width=LIVE_HOLD_SCREENSHOT_MAX_WIDTH,
    max_height=LIVE_HOLD_SCREENSHOT_MAX_HEIGHT,
    timeout=LIVE_HOLD_SCREENSHOT_TIMEOUT_MS,
    path=None,
):
    def capture_viewport():
        try:
            return (
                page.screenshot(
                    type="jpeg", quality=quality, full_page=False, timeout=max(timeout, 5000)
                ),
                "viewport_fallback",
            )
        except PlaywrightTimeoutError:
            data_url = page.evaluate(
                """quality => {
                    const media = [...document.querySelectorAll('canvas, video')].find((node) => {
                        const rect = node.getBoundingClientRect();
                        const style = getComputedStyle(node);
                        return rect.width > 100 && rect.height > 100 &&
                            style.visibility !== 'hidden' && style.display !== 'none';
                    });
                    if (!media) return null;
                    const width = media.videoWidth || media.width || media.clientWidth;
                    const height = media.videoHeight || media.height || media.clientHeight;
                    if (!width || !height) return null;
                    const output = document.createElement('canvas');
                    output.width = width;
                    output.height = height;
                    output.getContext('2d').drawImage(media, 0, 0, width, height);
                    return output.toDataURL('image/jpeg', quality);
                }""",
                quality / 100,
            )
            if not data_url or "," not in data_url:
                raise RuntimeError("No readable canvas/video frame for Agent observation")
            return base64.b64decode(data_url.split(",", 1)[1]), "dom_media_fallback"

    started_at = time.perf_counter()
    element, _ = find_world_element(page)
    if element:
        try:
            raw = element.screenshot(type="jpeg", quality=quality, timeout=timeout)
            source = "world_element"
        except PlaywrightTimeoutError:
            raw, source = capture_viewport()
    else:
        try:
            raw = page.screenshot(type="jpeg", quality=quality, full_page=False, timeout=timeout)
            source = "viewport"
        except PlaywrightTimeoutError:
            raw, source = capture_viewport()

    with Image.open(io.BytesIO(raw)) as image:
        image = image.convert("RGB")
        original_size = image.size
        image.thumbnail((max_width, max_height), Image.Resampling.LANCZOS)
        output = io.BytesIO()
        image.save(output, format="JPEG", quality=quality, optimize=True)
        encoded = output.getvalue()
        final_size = image.size
    if path:
        Path(path).write_bytes(encoded)
    return encoded, {
        "source": source,
        "original_size": list(original_size),
        "size": list(final_size),
        "bytes": len(encoded),
        "elapsed_ms": int((time.perf_counter() - started_at) * 1000),
    }


def run_agent_only_actions(page, objective, outdir, result):
    """Plan from observations only; this function deliberately has no base-action argument."""
    config = configured_agent()
    validate_agent_config(config)
    client = httpx.Client(
        trust_env=config.trust_env,
        verify=config.verify_tls,
        timeout=None,
        limits=httpx.Limits(max_connections=4, max_keepalive_connections=2, keepalive_expiry=60),
    )
    initial_path = outdir / "agent_observation_000.jpg"
    _, initial_meta = capture_agent_image(
        page,
        quality=ADAPTIVE_SCREENSHOT_QUALITY,
        max_width=ADAPTIVE_SCREENSHOT_MAX_WIDTH,
        max_height=ADAPTIVE_SCREENSHOT_MAX_HEIGHT,
        timeout=max(LIVE_HOLD_SCREENSHOT_TIMEOUT_MS, 3000),
        path=initial_path,
    )
    latest_path = initial_path
    result["observation_path"] = str(initial_path)
    result["initial_observation"] = {"path": str(initial_path), **initial_meta}
    result["agent_decisions"] = []
    executed_dsl = []
    started = time.perf_counter()
    try:
        for decision_index in range(1, AGENT_ONLY_MAX_DECISIONS + 1):
            if time.perf_counter() - started >= AGENT_ONLY_WALLCLOCK_BUDGET_S:
                result["agent_stop_reason"] = "wallclock_budget"
                break
            if len(executed_dsl) >= AGENT_ONLY_TOTAL_ACTION_BUDGET:
                result["agent_stop_reason"] = "total_action_budget"
                break
            package = observation_package(objective, initial_path, latest_path, executed_dsl)
            decision, messages = request_agent_decision(
                client,
                config,
                package,
                max_actions=min(AGENT_ONLY_MAX_ACTIONS, AGENT_ONLY_TOTAL_ACTION_BUDGET - len(executed_dsl)),
                max_tokens=AGENT_ONLY_MAX_TOKENS,
                timeout_s=AGENT_ONLY_TIMEOUT_S,
            )
            audit_text = json.dumps(messages, ensure_ascii=False)
            audit = {
                "decision_index": decision_index,
                "observation_path": str(latest_path),
                "decision_latency_ms": decision["decision_latency_ms"],
                "response_model": decision["response_model"],
                "status": decision["status"],
                "actions": [item["raw"] for item in decision["actions"]],
                "reason": decision["reason"],
                "raw_response": decision["raw_response"],
                "observation_package_fields": sorted(package),
                "base_sequence_exposed": False,
                "request_text_sha256": __import__("hashlib").sha256(audit_text.encode("utf-8")).hexdigest(),
            }
            result["agent_decisions"].append(audit)
            result.setdefault("agent_response_models", [])
            if decision["response_model"] not in result["agent_response_models"]:
                result["agent_response_models"].append(decision["response_model"])
            result["agent_model"] = decision["response_model"]
            print(
                f"[{result['task_id']}] agent-only decision={decision_index} status={decision['status']} "
                f"actions={audit['actions']} latency={decision['decision_latency_ms']}ms",
                flush=True,
            )
            if decision["status"] == "done" and not decision["actions"]:
                result["agent_stop_reason"] = "agent_done"
                break
            wallclock_exhausted = False
            for action in decision["actions"]:
                elapsed = time.perf_counter() - started
                hold_ms = action_hold_ms(action)
                if elapsed + hold_ms / 1000.0 > AGENT_ONLY_WALLCLOCK_BUDGET_S:
                    result["agent_stop_reason"] = "wallclock_budget"
                    wallclock_exhausted = True
                    break
                press_info = press_action(page, action, hold_ms=hold_ms if action["type"] != "wait" else None)
                executed_dsl.append(action["raw"])
                result["executed_actions"].append({
                    "index": len(result["executed_actions"]) + 1,
                    "elapsed_s": elapsed,
                    "source": "inserted",
                    "base_index": None,
                    "executed_action": action["raw"],
                    "observation_path": str(latest_path),
                    "decision_model": decision["response_model"],
                    "decision_latency_ms": decision["decision_latency_ms"],
                    "reason": decision["reason"],
                    "hold_token": hold_token_for_actions([action]),
                    "actual_hold_ms": press_info.get("actual_hold_ms"),
                    "input_dispatch": press_info.get("input_dispatch"),
                    **action,
                })
            if wallclock_exhausted:
                break
            next_path = outdir / f"agent_observation_{decision_index:03d}.jpg"
            _, next_meta = capture_agent_image(
                page,
                quality=ADAPTIVE_SCREENSHOT_QUALITY,
                max_width=ADAPTIVE_SCREENSHOT_MAX_WIDTH,
                max_height=ADAPTIVE_SCREENSHOT_MAX_HEIGHT,
                timeout=max(LIVE_HOLD_SCREENSHOT_TIMEOUT_MS, 3000),
                path=next_path,
            )
            latest_path = next_path
            audit["next_observation"] = {"path": str(next_path), **next_meta}
            if decision["status"] == "done":
                result["agent_stop_reason"] = "agent_done_after_actions"
                break
        else:
            result["agent_stop_reason"] = "max_decisions"
    finally:
        client.close()
    result["executed_action_sequence"] = executed_dsl
    latencies = [item["decision_latency_ms"] for item in result["agent_decisions"]]
    result["decision_latency_ms"] = latencies
    result["decision_latency_total_ms"] = sum(latencies)
    return time.perf_counter() - started


def focus_world(page):
    page.bring_to_front()
    try:
        page.evaluate("() => window.focus()")
    except Exception:
        pass
    _, box = find_world_element(page)
    if box:
        page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
        page.wait_for_timeout(80)
        return {"focused": True, "box": box}
    try:
        page.mouse.click(20, 20)
        page.wait_for_timeout(80)
    except Exception:
        pass
    return {"focused": False}


def dispatch_js_key_event(page, event_type, key):
    key_value, code, key_code = CDP_KEY_DETAILS.get(key, (key, key, 0))
    try:
        page.evaluate(
            """({eventType, keyValue, code, keyCode}) => {
              const event = new KeyboardEvent(eventType, {
                key: keyValue,
                code,
                keyCode,
                which: keyCode,
                bubbles: true,
                cancelable: true,
                composed: true,
              });
              for (const target of [window, document, document.body, document.activeElement]) {
                try { target && target.dispatchEvent(event); } catch (_) {}
              }
            }""",
            {
                "eventType": event_type,
                "keyValue": key_value,
                "code": code,
                "keyCode": key_code,
            },
        )
        return True
    except Exception:
        return False


def dispatch_cdp_key_event(page, event_type, key):
    key_value, code, key_code = CDP_KEY_DETAILS.get(key, (key, key, 0))
    try:
        cdp = page.context.new_cdp_session(page)
        cdp.send("Input.dispatchKeyEvent", {
            "type": event_type,
            "key": key_value,
            "code": code,
            "windowsVirtualKeyCode": key_code,
            "nativeVirtualKeyCode": key_code,
            "unmodifiedText": key_value if len(key_value) == 1 else "",
            "text": key_value if event_type == "char" and len(key_value) == 1 else "",
        })
        return True
    except Exception:
        return False


def press_keys_down(page, keys):
    methods = []
    focus_info = focus_world(page)
    for key in keys:
        try:
            page.keyboard.down(key)
            methods.append({"key": key, "method": "playwright_down", "ok": True})
        except Exception as exc:
            methods.append({"key": key, "method": "playwright_down", "ok": False, "error": str(exc)})
        methods.append({"key": key, "method": "cdp_raw_key_down", "ok": dispatch_cdp_key_event(page, "rawKeyDown", key)})
        methods.append({"key": key, "method": "js_keydown", "ok": dispatch_js_key_event(page, "keydown", key)})
    return {"focus": focus_info, "methods": methods}


def press_keys_up(page, keys):
    methods = []
    for key in reversed(keys):
        methods.append({"key": key, "method": "js_keyup", "ok": dispatch_js_key_event(page, "keyup", key)})
        methods.append({"key": key, "method": "cdp_key_up", "ok": dispatch_cdp_key_event(page, "keyUp", key)})
        try:
            page.keyboard.up(key)
            methods.append({"key": key, "method": "playwright_up", "ok": True})
        except Exception as exc:
            methods.append({"key": key, "method": "playwright_up", "ok": False, "error": str(exc)})
    return methods


def press_action(page, action, hold_ms=None, live_hold_context=None):
    if action["type"] == "wait":
        time.sleep(action["seconds"])
        actual_ms = int(action.get("seconds", 0) * 1000)
        return {"planned_hold_ms": actual_ms, "actual_hold_ms": actual_ms}
    mapped = [KEY_MAP.get(k, k) for k in action["keys"]]
    effective_hold_ms = hold_ms if hold_ms is not None else action.get("hold_ms", KEY_HOLD_MS)
    if not live_hold_check_enabled(action, effective_hold_ms, live_hold_context):
        down_info = press_keys_down(page, mapped)
        page.wait_for_timeout(effective_hold_ms)
        up_info = press_keys_up(page, mapped)
        return {
            "planned_hold_ms": effective_hold_ms,
            "actual_hold_ms": effective_hold_ms,
            "input_dispatch": {"down": down_info, "up": up_info},
        }

    context = dict(live_hold_context)
    original_hold_ms = effective_hold_ms
    minimum_stop_ms = max(LIVE_HOLD_STOP_MIN_MS, int(context.get("minimum_stop_ms") or 0))
    context["planned_hold_ms"] = original_hold_ms
    context["minimum_stop_ms"] = minimum_stop_ms
    stop_info = None
    decision_info = None
    deferred_stop_info = None
    adaptive_actions = []
    checks = []
    pending = None
    request_sent = False
    executor = ThreadPoolExecutor(max_workers=1)
    down_info = press_keys_down(page, mapped)
    hold_started = time.perf_counter()
    hold_deadline = hold_started + effective_hold_ms / 1000.0
    try:
        def maybe_request_check(elapsed_ms, remaining_ms):
            nonlocal pending, request_sent
            if (
                pending is not None
                or request_sent
                or deferred_stop_info is not None
                or len(checks) >= LIVE_HOLD_MAX_CHECKS
                or elapsed_ms < LIVE_HOLD_REQUEST_MIN_MS
                or remaining_ms < LIVE_HOLD_MIN_REMAINING_MS
            ):
                return
            check_context = dict(context)
            check_context["elapsed_hold_ms"] = elapsed_ms
            if not _LIVE_HOLD_REQUEST_LOCK.acquire(blocking=False):
                checks.append({
                    "enabled": True,
                    "elapsed_hold_ms": elapsed_ms,
                    "skipped": "live_hold_request_in_flight",
                })
                request_sent = True
                return
            try:
                shot, screenshot_meta = capture_agent_image(
                    page,
                    quality=LIVE_HOLD_SCREENSHOT_QUALITY,
                    timeout=LIVE_HOLD_SCREENSHOT_TIMEOUT_MS,
                )
                check_context["screenshot"] = screenshot_meta
                pending = executor.submit(
                    request_live_hold_stop_check,
                    context["task"],
                    context["result"],
                    check_context,
                    shot,
                    True,
                )
                request_sent = True
            except Exception as exc:
                _LIVE_HOLD_REQUEST_LOCK.release()
                checks.append({
                    "enabled": True,
                    "elapsed_hold_ms": elapsed_ms,
                    "error": repr(exc),
                })
                pending = None

        maybe_request_check(0, effective_hold_ms)
        while True:
            now = time.perf_counter()
            elapsed_ms = int((now - hold_started) * 1000)
            remaining_ms = max(0, int((hold_deadline - now) * 1000))

            if pending and pending.done():
                try:
                    check = pending.result(timeout=0)
                except Exception as exc:
                    check = {"enabled": True, "error": repr(exc)}
                checks.append(check)
                pending = None
                remaining_at_response_ms = remaining_ms
                if remaining_at_response_ms >= LIVE_HOLD_MIN_REMAINING_MS:
                    decision_info = check
                    adaptive_actions = check.get("actions") or []
                    extend_ms = int(check.get("extend_current_hold_ms") or 0)
                    if extend_ms > 0:
                        effective_hold_ms += extend_ms
                        hold_deadline += extend_ms / 1000.0
                        check["applied_extend_ms"] = extend_ms
                if check.get("stop_current_hold"):
                    if elapsed_ms >= minimum_stop_ms and remaining_at_response_ms >= LIVE_HOLD_MIN_REMAINING_MS:
                        stop_info = check
                        break
                    if remaining_at_response_ms >= LIVE_HOLD_MIN_REMAINING_MS:
                        deferred_stop_info = check

            if (
                deferred_stop_info
                and elapsed_ms >= minimum_stop_ms
                and remaining_ms >= LIVE_HOLD_MIN_REMAINING_MS
            ):
                stop_info = deferred_stop_info
                break

            if remaining_ms <= 0:
                break

            maybe_request_check(elapsed_ms, remaining_ms)

            wait_ms = min(LIVE_HOLD_CHECK_INTERVAL_MS, remaining_ms)
            page.wait_for_timeout(wait_ms)

        if pending and pending.done() and not stop_info:
            try:
                check = pending.result(timeout=0)
            except Exception as exc:
                check = {"enabled": True, "error": repr(exc)}
            checks.append(check)
            final_elapsed_ms = int((time.perf_counter() - hold_started) * 1000)
            final_remaining_ms = max(0, int((hold_deadline - time.perf_counter()) * 1000))
            if (
                check.get("stop_current_hold")
                and final_elapsed_ms < effective_hold_ms
                and final_elapsed_ms >= minimum_stop_ms
                and final_remaining_ms >= LIVE_HOLD_MIN_REMAINING_MS
            ):
                stop_info = check
    finally:
        up_info = press_keys_up(page, mapped)
        try:
            executor.shutdown(wait=False, cancel_futures=True)
        except TypeError:
            executor.shutdown(wait=False)

    actual_hold_ms = int((time.perf_counter() - hold_started) * 1000)
    result = context.get("result")
    if result is not None:
        result.setdefault("live_hold_stop_checks", []).extend(checks)
        if stop_info:
            result.setdefault("live_hold_stops", []).append(stop_info)
    return {
        "planned_hold_ms": original_hold_ms,
        "effective_hold_ms": effective_hold_ms,
        "actual_hold_ms": actual_hold_ms,
        "input_dispatch": {"down": down_info, "up": up_info},
        "live_hold_checks": checks,
        "live_hold_stop": stop_info,
        "live_hold_decision": decision_info,
        "adaptive_actions": (
            adaptive_actions
            if not decision_info or not decision_info.get("stop_current_hold") or stop_info
            else []
        ),
        "stop_current_hold": bool(stop_info),
        "skip_remaining_phase": bool(stop_info and stop_info.get("skip_remaining_phase")),
    }


def task_environmental_caption(task):
    return (
        task.get("image_caption")
        or task.get("environmental_caption")
        or task.get("scene_context")
        or task.get("prompt")
        or ""
    )


def central_character_from_prompt(prompt):
    text = re.sub(r"\s+", " ", (prompt or "").strip())
    if not text:
        return "the central character"
    verb_pattern = (
        r"walks?|runs?|moves?|drives?|rides?|turns?|climbs?|jumps?|rows?|pushes?|"
        r"gallops?|rush(?:es)?|knocks?|charges?|enters?|goes?|crosses?|follows?|"
        r"tilts?|pans?|rotates?|circles?|watches?|observes?"
    )
    match = re.match(rf"^((?:the|a|an)\s+.+?)\s+({verb_pattern})\b", text, flags=re.I)
    if match:
        return match.group(1).strip()
    match = re.match(rf"^([A-Z][A-Za-z0-9_-]*(?:\s+[A-Z][A-Za-z0-9_-]*)?)\s+({verb_pattern})\b", text)
    if match:
        return match.group(1).strip()
    match = re.search(
        r"\b((?:the|a|an)\s+(?:man|woman|boy|girl|child|person|character|waiter|warrior|archer|fisherman|bellhop|robot dog|horse|car|tram|boat|wagon|deer)[^,.;]*)",
        text,
        flags=re.I,
    )
    if match:
        return match.group(1).strip()
    return text.split(",")[0].strip()[:160] or "the central character"


def sanitize_happyoyster_prompt_text(text):
    text = text or ""
    # HappyOyster can silently refuse prompts with certain storefront sign words.
    text = re.sub(r"\bDRUGS?\.?\b", "GENERAL STORE", text, flags=re.I)
    return text


def build_happyoyster_prompt(task):
    environment = sanitize_happyoyster_prompt_text(task_environmental_caption(task))
    perspective = normalize_perspective(task.get("perspective"))
    lines = [environment]
    if perspective == "third-person":
        lines.append(f"Character: {central_character_from_prompt(task.get('prompt'))}.")
        lines.append("Perspective: Third-person view with the character visible.")
    elif perspective == "first-person":
        lines.append("Perspective: First-person view through the character's eyes.")
    lines.append(f"Task: {sanitize_happyoyster_prompt_text(task['prompt'])}")
    return "\n".join(line for line in lines if line)


def submit_create_attempt(page, task, prompt, upload_path, outdir, result, attempt):
    suffix = "" if attempt == 1 else f"_attempt_{attempt}"
    result["create_attempt"] = attempt
    for nav_try in range(1, 4):
        try:
            page.goto("about:blank", wait_until="domcontentloaded", timeout=15000)
            page.goto(HAPPYOYSTER_CREATE_URL, wait_until="domcontentloaded", timeout=60000)
            result[f"create_goto{suffix}"] = {"status": "ok", "try": nav_try}
            break
        except Exception as exc:
            result.setdefault(f"create_goto_errors{suffix}", []).append({
                "try": nav_try,
                "error": repr(exc),
            })
            if nav_try >= 3:
                result["status"] = "create_goto_failed"
                return False
            page.wait_for_timeout(3000)
    page.wait_for_timeout(5000)
    result[f"create_entry{suffix}"] = open_create_panel(page, result, suffix)
    if result[f"create_entry{suffix}"]["status"] not in {"already_open", "clicked"}:
        safe_screenshot(page, outdir / f"create_entry_not_ready{suffix}.jpg", result, f"create_entry_screenshot_error{suffix}", type="jpeg", quality=85, full_page=True)
        result["status"] = "create_entry_not_ready"
        return False
    if page_requires_login(page):
        safe_screenshot(page, outdir / f"login_required{suffix}.jpg", result, f"login_required_screenshot_error{suffix}", type="jpeg", quality=85, full_page=True)
        result["status"] = "login_required"
        return False
    result[f"perspective_select{suffix}"] = set_perspective(page, task.get("perspective"))
    if not fill_prompt_until_present(page, prompt, result):
        safe_screenshot(page, outdir / f"prompt_not_ready{suffix}.jpg", result, f"prompt_screenshot_error{suffix}", type="jpeg", quality=85, full_page=True)
        result["status"] = "prompt_not_ready"
        return False
    if not readable_file(upload_path):
        result["status"] = "first_frame_not_readable"
        result[f"first_frame_path{suffix}"] = str(upload_path)
        return False
    media_before = create_media_state(page)
    result[f"first_frame_before{suffix}"] = media_before
    try:
        result[f"upload{suffix}"] = upload_start_image(page, upload_path)
    except Exception as exc:
        result[f"upload_error{suffix}"] = repr(exc)
        safe_screenshot(page, outdir / f"upload_failed{suffix}.jpg", result, f"upload_screenshot_error{suffix}", type="jpeg", quality=85, full_page=True)
        result["status"] = "image_upload_failed"
        return False
    page.wait_for_timeout(2500)
    page.wait_for_timeout(1200)
    if not wait_create_input_ready(page, prompt, result, media_before):
        safe_screenshot(page, outdir / f"create_input_not_ready{suffix}.jpg", result, f"create_input_screenshot_error{suffix}", type="jpeg", quality=85, full_page=True)
        result["status"] = "first_frame_not_confirmed"
        return False
    result[f"first_frame_upload{suffix}"] = {
        "required": True,
        "confirmed": True,
        "path": str(upload_path),
        "upload_method": result[f"upload{suffix}"].get("method"),
    }
    camera_info = set_camera_view(page, task.get("perspective"))
    result[f"camera_view_select{suffix}"] = camera_info
    expected_camera_label = camera_info.get("desired_label")
    camera_confirmed = (
        camera_info.get("status") in {"selected", "already_selected"}
        and camera_info.get("selected_perspective") == normalize_perspective(task.get("perspective"))
    )
    result[f"perspective_control{suffix}"] = {
        "required": True,
        "desired": normalize_perspective(task.get("perspective")),
        "expected_camera_label": expected_camera_label,
        "confirmed": camera_confirmed,
    }
    if not camera_confirmed:
        safe_screenshot(
            page,
            outdir / f"perspective_not_confirmed{suffix}.jpg",
            result,
            f"perspective_screenshot_error{suffix}",
            type="jpeg",
            quality=85,
            full_page=True,
        )
        result["status"] = "perspective_not_confirmed"
        return False
    if page_requires_login(page):
        safe_screenshot(page, outdir / f"login_required{suffix}.jpg", result, f"login_required_screenshot_error{suffix}", type="jpeg", quality=85, full_page=True)
        result["status"] = "login_required"
        return False

    try:
        wait_submit_ready(page)
    except PlaywrightTimeoutError as exc:
        safe_screenshot(page, outdir / f"submit_not_ready{suffix}.jpg", result, f"submit_screenshot_error{suffix}", type="jpeg", quality=85, full_page=True)
        result[f"submit_ready_error{suffix}"] = str(exc)
        result[f"submit_block{suffix}"] = get_submit_block_reason(page)
        if result[f"submit_block{suffix}"].get("reason") in {"insufficient_credits", "login_required"}:
            result["status"] = result[f"submit_block{suffix}"]["reason"]
            return False
    safe_screenshot(page, outdir / f"create_ready{suffix}.jpg", result, f"create_ready_screenshot_error{suffix}", type="jpeg", quality=85, full_page=True)
    submit_result = {"method": "button_first", "pressed": False}
    submit_result["button"] = click_submit(page)
    page.wait_for_timeout(1500)
    if not submit_result["button"].get("clicked") and HAPPYOYSTER_HOST_FRAGMENT in page.url and ("/home" in page.url or "/create" in page.url):
        try:
            textarea = page.locator("textarea").first
            textarea.click()
            textarea.press("Enter")
            submit_result["pressed"] = True
        except Exception as exc:
            submit_result["enter_error"] = str(exc)
        page.wait_for_timeout(1500)
    result[f"submit{suffix}"] = submit_result
    if not submit_result.get("pressed") and not submit_result.get("button", {}).get("clicked"):
        result[f"submit_block_after_click{suffix}"] = get_submit_block_reason(page)
        if result[f"submit_block_after_click{suffix}"].get("reason") in {"insufficient_credits", "login_required"}:
            result["status"] = result[f"submit_block_after_click{suffix}"]["reason"]
            return False
        result["status"] = "submit_not_clicked"
        return False
    print(f"[{task['task_id']}] submit attempt={attempt} {result[f'submit{suffix}']}", flush=True)
    page.wait_for_timeout(3000)
    if not wait_for_explore(page, result):
        safe_screenshot(page, outdir / f"explore_not_ready{suffix}.jpg", result, f"explore_screenshot_error{suffix}", type="jpeg", quality=85, full_page=True)
        result["status"] = "explore_not_ready"
        return False
    return True


def start_screen_recording(task_id):
    if SCREEN_RECORD_DIR is None:
        return None
    SCREEN_RECORD_DIR.mkdir(parents=True, exist_ok=True)
    output_path = SCREEN_RECORD_DIR / f"{task_id}_operation.mp4"
    log_path = SCREEN_RECORD_DIR / f"{task_id}_ffmpeg.log"
    output_path.unlink(missing_ok=True)
    log_path.unlink(missing_ok=True)
    log_handle = log_path.open("wb")
    command = [
        shutil.which("ffmpeg") or "/opt/homebrew/bin/ffmpeg",
        "-y",
        "-f", "avfoundation",
        "-framerate", str(SCREEN_RECORD_FPS),
        "-capture_cursor", "1",
        "-i", f"{SCREEN_RECORD_DEVICE}:none",
        "-vf", "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2",
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-crf", "23",
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        str(output_path),
    ]
    process = subprocess.Popen(
        command,
        stdin=subprocess.DEVNULL,
        stdout=log_handle,
        stderr=subprocess.STDOUT,
    )
    time.sleep(1)
    if process.poll() is not None:
        log_handle.close()
        error_tail = log_path.read_text(encoding="utf-8", errors="replace")[-2000:]
        print(f"[{task_id}] screen recording failed to start: {error_tail}", flush=True)
        return {
            "process": None,
            "log_handle": None,
            "path": str(output_path),
            "log_path": str(log_path),
            "status": "start_failed",
            "returncode": process.returncode,
            "error": error_tail,
        }
    print(f"[{task_id}] screen recording started: {output_path}", flush=True)
    return {
        "process": process,
        "log_handle": log_handle,
        "path": str(output_path),
        "log_path": str(log_path),
        "status": "recording",
        "started_at": time.time(),
    }


def stop_screen_recording(recording, task_id):
    if not recording:
        return None
    process = recording.get("process")
    if process is not None and process.poll() is None:
        process.send_signal(signal.SIGINT)
        try:
            process.wait(timeout=20)
        except subprocess.TimeoutExpired:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
    log_handle = recording.get("log_handle")
    if log_handle is not None and not log_handle.closed:
        log_handle.close()
    output_path = Path(recording["path"])
    status = "completed" if output_path.exists() and output_path.stat().st_size > 0 else "failed"
    metadata = {
        "path": str(output_path),
        "log_path": recording["log_path"],
        "status": status if recording.get("status") != "start_failed" else "start_failed",
        "returncode": process.returncode if process is not None else recording.get("returncode"),
        "size_bytes": output_path.stat().st_size if output_path.exists() else 0,
        "elapsed_s": round(time.time() - recording["started_at"], 3) if recording.get("started_at") else 0,
    }
    if recording.get("error"):
        metadata["error"] = recording["error"]
    print(f"[{task_id}] screen recording {metadata['status']}: {output_path}", flush=True)
    return metadata


def run_task(ctx, task):
    outdir = task_output_dir(task)
    outdir.mkdir(parents=True, exist_ok=True)
    result_path = outdir / "result.json"
    previous_success_result = None
    if result_path.is_file():
        try:
            candidate = json.loads(result_path.read_text(encoding="utf-8"))
            candidate_download = candidate.get("download_path")
            if (
                candidate.get("status") == "actions_completed"
                and candidate.get("download_status") in {"downloaded", "downloaded_from_downloads"}
                and candidate_download
                and Path(candidate_download).is_file()
                and Path(candidate_download).stat().st_size > 0
            ):
                previous_success_result = candidate
        except (OSError, json.JSONDecodeError):
            pass
    original_image_path = Path(task["resolved_image_path"])
    image_path, image_fallback = forced_image_fallback(task, original_image_path)
    link_or_copy_file(image_path, outdir / f"{task['task_id']}_input.jpg")
    upload_info = make_landscape_upload_image(image_path, outdir / f"{task['task_id']}_upload_landscape.jpg")
    prompt = TASK_CREATE_PROMPT_OVERRIDES.get(task["task_id"], build_happyoyster_prompt(task))
    original_action_sequence_steps = task["action_sequence_steps"]
    if AGENT_ABLATION_MODE == "preset_only":
        effective_action_sequence_steps = original_action_sequence_steps
        has_action_sequence_override = False
    else:
        effective_action_sequence_steps = TASK_ACTION_SEQUENCE_OVERRIDES.get(
            task["task_id"], original_action_sequence_steps
        )
        has_action_sequence_override = task["task_id"] in TASK_ACTION_SEQUENCE_OVERRIDES
    actions = expand_steps(effective_action_sequence_steps)
    task_action_overrides = [] if AGENT_ABLATION_MODE == "preset_only" else apply_task_action_overrides(task, actions)
    agent_config = configured_agent() if AGENT_ABLATION_MODE in {"agent_only", "preset_agent"} else None
    wait_observe_task = is_wait_observe_task(task)
    rotation_loop_task = not has_action_sequence_override and is_rotation_loop_task(task, actions)
    final_orientation_task = not has_action_sequence_override and is_final_orientation_task(task, actions)
    result = {
        "run_id": RUN_ID,
        "task_id": task["task_id"],
        "group": task["group"],
        "source_file": task["source_file"],
        "prompt": task["prompt"],
        "ablation_mode": AGENT_ABLATION_MODE or "legacy",
        "agent_provider": agent_config.provider if agent_config else None,
        "agent_model": deployed_controller_model() if agent_config else None,
        "original_action_sequence": task["action_sequence"],
        "create_prompt": prompt,
        "create_prompt_override": TASK_CREATE_PROMPT_OVERRIDES.get(task["task_id"]),
        "environmental_caption": task_environmental_caption(task),
        "character": central_character_from_prompt(task.get("prompt")) if normalize_perspective(task.get("perspective")) == "third-person" else "",
        "image_path": str(image_path),
        "original_image_path": str(original_image_path),
        "image_fallback": image_fallback,
        "upload_image": upload_info,
        "first_frame_required": True,
        "perspective": task.get("perspective"),
        "perspective_normalized": normalize_perspective(task.get("perspective")),
        "perspective_control_required": True,
        "perspective_output_dir": perspective_dir_name(task.get("perspective")),
        "action_sequence": task["action_sequence"],
        "action_sequence_steps": effective_action_sequence_steps,
        "original_action_sequence_steps": original_action_sequence_steps,
        "action_sequence_override": (
            effective_action_sequence_steps if has_action_sequence_override else None
        ),
        "expanded_actions": actions,
        "task_action_overrides": task_action_overrides,
        "key_hold_ms": KEY_HOLD_MS,
        "hold_source_step_ms": HOLD_SOURCE_STEP_MS,
        "hold_target_step_ms": HOLD_TARGET_STEP_MS,
        "hold_scale": HOLD_SCALE,
        "executed_actions": [],
        "executed_action_sequence": [],
        "deleted_actions": [],
        "observation_path": None,
        "decision_latency_ms": [],
        "agent_only_wallclock_budget_s": AGENT_ONLY_WALLCLOCK_BUDGET_S,
        "adaptive_corrections": [],
        "adaptive_correction_enabled": ADAPTIVE_CORRECTION,
        "adaptive_phase_progress_check_enabled": ADAPTIVE_PHASE_PROGRESS_CHECK,
        "adaptive_phase_check_every": ADAPTIVE_PHASE_CHECK_EVERY,
        "adaptive_screenshot": {
            "quality": ADAPTIVE_SCREENSHOT_QUALITY,
            "max_width": ADAPTIVE_SCREENSHOT_MAX_WIDTH,
            "max_height": ADAPTIVE_SCREENSHOT_MAX_HEIGHT,
        },
        "adaptive_skipped_actions": [],
        "adaptive_extend_hold_enabled": ADAPTIVE_EXTEND_HOLD,
        "adaptive_extend_hold_min_ms": ADAPTIVE_EXTEND_HOLD_MIN_MS,
        "adaptive_extend_hold_max_ms": ADAPTIVE_EXTEND_HOLD_MAX_MS,
        "adaptive_extend_hold_max_rounds": ADAPTIVE_EXTEND_HOLD_MAX_ROUNDS,
        "live_hold_stop_check_enabled": LIVE_HOLD_STOP_CHECK,
        "live_hold_check_interval_ms": LIVE_HOLD_CHECK_INTERVAL_MS,
        "live_hold_min_ms": LIVE_HOLD_MIN_MS,
        "live_hold_request_min_ms": LIVE_HOLD_REQUEST_MIN_MS,
        "live_hold_stop_min_ms": LIVE_HOLD_STOP_MIN_MS,
        "live_hold_min_remaining_ms": LIVE_HOLD_MIN_REMAINING_MS,
        "live_hold_timeout_s": LIVE_HOLD_TIMEOUT_S,
        "live_hold_max_tokens": LIVE_HOLD_MAX_TOKENS,
        "live_hold_screenshot": {
            "quality": LIVE_HOLD_SCREENSHOT_QUALITY,
            "max_width": LIVE_HOLD_SCREENSHOT_MAX_WIDTH,
            "max_height": LIVE_HOLD_SCREENSHOT_MAX_HEIGHT,
        },
        "live_hold_stop_checks": [],
        "live_hold_stops": [],
        "live_hold_skipped_actions": [],
        "require_full_action_sequence": REQUIRE_FULL_ACTION_SEQUENCE,
        "adaptive_model": deployed_controller_model() if ADAPTIVE_CORRECTION else None,
        "wait_observe_task": wait_observe_task,
        "wait_observe_ms": WAIT_OBSERVE_MS if wait_observe_task else 0,
        "rotation_loop_task": rotation_loop_task,
        "rotation_loop_check_enabled": ROTATION_LOOP_CHECK,
        "rotation_extra_turn_units": ROTATION_EXTRA_TURN_UNITS,
        "rotation_extra_turn_ms": ROTATION_EXTRA_TURN_MS,
        "gc007_forward_extra_units": GC007_FORWARD_EXTRA_UNITS if task["task_id"] == "GC007" else 0,
        "gc007_return_extra_units": GC007_RETURN_EXTRA_UNITS if task["task_id"] == "GC007" else 0,
        "rotation_loop_checks": [],
        "rotation_loop_skipped_actions": [],
        "final_orientation_task": final_orientation_task,
        "final_orientation_check_enabled": FINAL_ORIENTATION_CHECK,
        "final_orientation_checks": [],
        "status": "started",
    }

    page = ctx.new_page()
    screen_recording = None
    try:
        # Start immediately before the first create attempt, covering automatic form filling onward.
        if SCREEN_RECORD_DIR is not None:
            page.bring_to_front()
            if SCREEN_RECORD_APP:
                subprocess.run(
                    ["open", "-a", SCREEN_RECORD_APP],
                    check=False,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            time.sleep(1)
        screen_recording = start_screen_recording(task["task_id"])
        if screen_recording:
            result["screen_recording"] = {
                key: value
                for key, value in screen_recording.items()
                if key not in {"process", "log_handle", "started_at"}
            }
        explore_ready = False
        for attempt in range(1, CREATE_ATTEMPTS + 1):
            explore_ready = submit_create_attempt(
                page, task, prompt, Path(upload_info["path"]), outdir, result, attempt
            )
            if explore_ready:
                break
            if result.get("status") in {"insufficient_credits", "login_required", "image_upload_failed"}:
                break
            if attempt < CREATE_ATTEMPTS:
                print(f"[{task['task_id']}] retry create after status={result.get('status')}", flush=True)
                page.wait_for_timeout(CREATE_RETRY_DELAY_S * 1000)
        if not explore_ready:
            return result
        result["explore_url"] = page.url
        if not wait_for_interactive(page, result):
            if result.get("status") == "started":
                result["status"] = "interactive_not_ready"
            safe_screenshot(
                page,
                outdir / "interactive_not_ready.jpg",
                result,
                "interactive_not_ready_screenshot_error",
                type="jpeg",
                quality=85,
                full_page=True,
            )
            return result
        result["action_start_delay_ms"] = ACTION_START_DELAY_MS
        if ACTION_START_DELAY_MS > 0:
            print(f"[{task['task_id']}] action start delay {ACTION_START_DELAY_MS}ms", flush=True)
            page.wait_for_timeout(ACTION_START_DELAY_MS)
        result["initial_focus"] = focus_world(page)

        if AGENT_ABLATION_MODE == "agent_only":
            result["action_elapsed_s"] = run_agent_only_actions(page, task["prompt"], outdir, result)
            page.wait_for_timeout(8000)
            result["url_after_actions"] = page.url
            result["status"] = "actions_completed"
            safe_screenshot(
                page, outdir / "after_actions.jpg", result, "after_actions_screenshot_error",
                type="jpeg", quality=85, full_page=True,
            )
            wait_start = time.perf_counter()
            while not (HAPPYOYSTER_HOST_FRAGMENT in page.url and "/end/travel" in page.url) and time.perf_counter() - wait_start < END_WAIT_TIMEOUT_S:
                page.wait_for_timeout(3000)
            click_download_and_save(page, outdir, result)
            return result

        if wait_observe_task:
            print(f"[{task['task_id']}] wait-and-observe: no actions, observe {WAIT_OBSERVE_MS}ms", flush=True)
            start = time.perf_counter()
            page.wait_for_timeout(WAIT_OBSERVE_MS)
            result["action_elapsed_s"] = time.perf_counter() - start
            result["url_after_actions"] = page.url
            result["status"] = "actions_completed"
            safe_screenshot(
                page,
                outdir / "after_actions.jpg",
                result,
                "after_actions_screenshot_error",
                type="jpeg",
                quality=85,
                full_page=True,
            )
            wait_start = time.perf_counter()
            while not (HAPPYOYSTER_HOST_FRAGMENT in page.url and "/end/travel" in page.url) and time.perf_counter() - wait_start < END_WAIT_TIMEOUT_S:
                page.wait_for_timeout(3000)
            click_download_and_save(page, outdir, result)
            return result

        rotation_loop_before_path = None
        if rotation_loop_task and ROTATION_LOOP_CHECK:
            rotation_loop_before_path = outdir / "rotation_loop_before.jpg"
            page.screenshot(path=str(rotation_loop_before_path), type="jpeg", quality=85, full_page=True)
        final_orientation_before_path = None
        if final_orientation_task and FINAL_ORIENTATION_CHECK:
            final_orientation_before_path = outdir / "final_orientation_before.jpg"
            page.screenshot(path=str(final_orientation_before_path), type="jpeg", quality=85, full_page=True)

        start = time.perf_counter()

        def execute_correction_actions(correction_actions, adaptive_phase):
            for correction_action in correction_actions:
                adaptive_elapsed = time.perf_counter() - start
                correction_hold_ms = action_hold_ms(correction_action)
                correction_token = hold_token_for_actions([correction_action])
                print(
                    f"[{task['task_id']}] {adaptive_phase} correction t={adaptive_elapsed:.1f}s {correction_token}",
                    flush=True,
                )
                correction_press = press_action(
                    page,
                    correction_action,
                    hold_ms=correction_hold_ms if correction_action["type"] != "wait" else None,
                )
                result["executed_actions"].append({
                    "index": len(result["executed_actions"]) + 1,
                    "elapsed_s": adaptive_elapsed,
                    "adaptive_phase": adaptive_phase,
                    "hold_token": correction_token,
                    "hold_ms": correction_hold_ms,
                    "actual_hold_ms": correction_press.get("actual_hold_ms"),
                    "input_dispatch": correction_press.get("input_dispatch"),
                    **correction_action,
                })
                if correction_action["type"] != "wait":
                    time.sleep(max(0, ACTION_INTERVAL_S - correction_hold_ms / 1000.0))

        i = 0
        while i < len(actions):
            action = actions[i]
            elapsed = time.perf_counter() - start
            hold_ms = action_hold_ms(action)
            hold_token = hold_token_for_actions([action])
            print(f"[{task['task_id']}] action {i + 1}/{len(actions)} t={elapsed:.1f}s {hold_token}", flush=True)
            press_info = press_action(
                page,
                action,
                hold_ms=hold_ms if action["type"] != "wait" else None,
                live_hold_context=build_live_hold_context(task, result, actions, i),
            )
            action_record = dict(action)
            action_record["hold_token"] = hold_token
            action_record["hold_ms"] = hold_ms
            action_record["actual_hold_ms"] = press_info.get("actual_hold_ms")
            action_record["effective_hold_ms"] = press_info.get("effective_hold_ms")
            action_record["input_dispatch"] = press_info.get("input_dispatch")
            action_record["live_hold_stop"] = press_info.get("live_hold_stop")
            action_record["live_hold_decision"] = press_info.get("live_hold_decision")
            result["executed_actions"].append({
                "index": len(result["executed_actions"]) + 1,
                "elapsed_s": elapsed,
                **action_record,
            })
            if action["type"] != "wait":
                actual_hold_s = (press_info.get("actual_hold_ms") or hold_ms) / 1000.0
                hold_s = min(hold_ms / 1000.0, actual_hold_s)
                time.sleep(max(0, ACTION_INTERVAL_S - hold_s))
            live_skipped_phase_tail = False
            if press_info.get("skip_remaining_phase"):
                i = record_live_hold_skip(result, actions, i, press_info.get("live_hold_stop"))
                action = actions[i]
                live_skipped_phase_tail = True

            if is_360_rotation_turn_action(task, action) and ROTATION_EXTRA_TURN_MS > 0:
                bonus_action = make_hold_extension_action(action, ROTATION_EXTRA_TURN_MS)
                bonus_action["rotation_fixed_extra"] = True
                bonus_action["step_index"] = "rotation_fixed_extra"
                bonus_action["step"] = f"fixed extra 360 turn ({ROTATION_EXTRA_TURN_UNITS} units)"
                bonus_elapsed = time.perf_counter() - start
                bonus_token = hold_token_for_actions([bonus_action])
                print(
                    f"[{task['task_id']}] rotation fixed extra t={bonus_elapsed:.1f}s {bonus_token}",
                    flush=True,
                )
                bonus_press = press_action(page, bonus_action, hold_ms=ROTATION_EXTRA_TURN_MS)
                result["executed_actions"].append({
                    "index": len(result["executed_actions"]) + 1,
                    "elapsed_s": bonus_elapsed,
                    "adaptive_phase": "rotation_fixed_extra",
                    "hold_token": bonus_token,
                    "hold_ms": ROTATION_EXTRA_TURN_MS,
                    "actual_hold_ms": bonus_press.get("actual_hold_ms"),
                    "input_dispatch": bonus_press.get("input_dispatch"),
                    **bonus_action,
                })

            task_extra = gc007_fixed_extra(task, action)
            if task_extra:
                extra_action = make_hold_extension_action(action, task_extra["hold_ms"])
                extra_action["task_fixed_extra"] = True
                extra_action["step_index"] = task_extra["phase"]
                extra_action["step"] = task_extra["step"]
                extra_elapsed = time.perf_counter() - start
                extra_token = hold_token_for_actions([extra_action])
                print(
                    f"[{task['task_id']}] {task_extra['phase']} t={extra_elapsed:.1f}s {extra_token}",
                    flush=True,
                )
                extra_press = press_action(page, extra_action, hold_ms=task_extra["hold_ms"])
                result["executed_actions"].append({
                    "index": len(result["executed_actions"]) + 1,
                    "elapsed_s": extra_elapsed,
                    "adaptive_phase": task_extra["phase"],
                    "hold_token": extra_token,
                    "hold_ms": task_extra["hold_ms"],
                    "actual_hold_ms": extra_press.get("actual_hold_ms"),
                    "input_dispatch": extra_press.get("input_dispatch"),
                    **extra_action,
                })
            execute_correction_actions(press_info.get("adaptive_actions", []), "live_hold")

            next_index = i + 1
            next_action = actions[next_index] if next_index < len(actions) else None
            phase_done = next_action is None or next_action.get("step_index") != action.get("step_index")
            phase_tail_skipped = live_skipped_phase_tail

            if not phase_done and not live_skipped_phase_tail:
                phase_start, phase_end = phase_bounds(actions, i)
                completed_in_phase = i - phase_start + 1
                remaining_in_phase = phase_end - i - 1
                if (
                    rotation_loop_task
                    and rotation_loop_before_path
                    and completed_in_phase >= ROTATION_LOOP_SKIP_MIN_ACTIONS
                    and completed_in_phase % max(1, ROTATION_LOOP_SKIP_CHECK_EVERY) == 0
                ):
                    rotation_check = request_rotation_loop_check(
                        page,
                        task,
                        result,
                        outdir,
                        rotation_loop_before_path,
                        attempt_index=completed_in_phase,
                        purpose="mid_phase",
                        completed_in_phase=completed_in_phase,
                        remaining_in_phase=remaining_in_phase,
                    )
                    result["rotation_loop_checks"].append(rotation_check)
                    if (
                        rotation_check.get("closed_loop_ok")
                        and rotation_check.get("in_place_ok")
                        and rotation_check.get("orientation_ok")
                    ):
                        new_index = record_adaptive_phase_skip(
                            result,
                            actions,
                            i,
                            rotation_check,
                            record_key="rotation_loop_skipped_actions",
                        )
                        phase_tail_skipped = new_index != i
                        i = new_index
                elif ADAPTIVE_PHASE_PROGRESS_CHECK and (
                    completed_in_phase % ADAPTIVE_PHASE_CHECK_EVERY == 0
                    or remaining_in_phase == 1
                ):
                    progress_check = request_adaptive_correction(
                        page,
                        task,
                        result,
                        action.get("step_index"),
                        action.get("step"),
                        outdir,
                        phase_done=False,
                        remaining_in_phase=remaining_in_phase,
                        remaining_phase_actions=actions_to_hold_tokens(actions[i + 1:phase_end]),
                        upcoming_dataset_actions=actions_to_hold_tokens(
                            actions[phase_end:min(len(actions), phase_end + 24)]
                        ),
                    )
                    result["adaptive_corrections"].append(progress_check)
                    print(
                        f"[{task['task_id']}] phase-progress phase={action.get('step')} "
                        f"remaining={remaining_in_phase} skip={progress_check.get('skip_remaining_phase')} "
                        f"steps={progress_check.get('correction_steps')} error={progress_check.get('error')}",
                        flush=True,
                    )
                    if progress_check.get("skip_remaining_phase"):
                        new_index = record_adaptive_phase_skip(result, actions, i, progress_check)
                        phase_tail_skipped = new_index != i
                        i = new_index
                    execute_correction_actions(progress_check.get("actions", []), "phase_progress")

                action = actions[i]
                next_index = i + 1
                next_action = actions[next_index] if next_index < len(actions) else None
                phase_done = next_action is None or next_action.get("step_index") != action.get("step_index")

            if (
                ADAPTIVE_EXTEND_HOLD
                and ADAPTIVE_CORRECTION
                and phase_done
                and not phase_tail_skipped
                and not rotation_loop_task
                and action.get("type") == "key"
                and not bool(press_info.get("stop_current_hold"))
                and hold_ms >= ADAPTIVE_EXTEND_HOLD_MIN_MS
            ):
                extension_check = None
                for extension_round in range(ADAPTIVE_EXTEND_HOLD_MAX_ROUNDS):
                    extension_elapsed = time.perf_counter() - start
                    extension_check = request_adaptive_correction(
                        page,
                        task,
                        result,
                        action.get("step_index"),
                        action.get("step"),
                        outdir,
                        allow_hold_extension=True,
                        current_hold_actions=[action],
                        upcoming_dataset_actions=actions_to_hold_tokens(actions[next_index:min(len(actions), next_index + 24)]),
                    )
                    extension_check["extension_round"] = extension_round + 1
                    extension_check["after_hold_ms"] = hold_ms
                    result.setdefault("adaptive_hold_extension_checks", []).append(extension_check)
                    result["adaptive_corrections"].append(extension_check)
                    extend_ms = int(extension_check.get("extend_current_hold_ms") or 0)
                    print(
                        f"[{task['task_id']}] hold extension phase={action.get('step')} "
                        f"round={extension_round + 1} extend_ms={extend_ms} "
                        f"steps={extension_check.get('correction_steps')} error={extension_check.get('error')}",
                        flush=True,
                    )
                    if extend_ms <= 0:
                        break
                    extension_action = make_hold_extension_action(action, extend_ms)
                    extension_token = hold_token_for_actions([extension_action])
                    extension_press = press_action(page, extension_action, hold_ms=extend_ms)
                    result["executed_actions"].append({
                        "index": len(result["executed_actions"]) + 1,
                        "elapsed_s": extension_elapsed,
                        "adaptive_phase": action.get("step"),
                        "adaptive_extension": True,
                        "extension_round": extension_round + 1,
                        "hold_token": extension_token,
                        "hold_ms": extend_ms,
                        "actual_hold_ms": extension_press.get("actual_hold_ms"),
                        "input_dispatch": extension_press.get("input_dispatch"),
                        "reason": extension_check.get("reason"),
                        **extension_action,
                    })
                    time.sleep(max(0, ACTION_INTERVAL_S - extend_ms / 1000.0))

                execute_correction_actions(
                    extension_check.get("actions", []) if extension_check else [],
                    action.get("step"),
                )
            i += 1

        if rotation_loop_task and rotation_loop_before_path:
            for check_index in range(ROTATION_LOOP_MAX_CHECKS):
                rotation_check = request_rotation_loop_check(
                    page,
                    task,
                    result,
                    outdir,
                    rotation_loop_before_path,
                    attempt_index=check_index,
                )
                result["rotation_loop_checks"].append(rotation_check)
                print(
                    f"[{task['task_id']}] rotation-loop check={check_index} "
                    f"closed={rotation_check.get('closed_loop_ok')} in_place={rotation_check.get('in_place_ok')} "
                    f"orient={rotation_check.get('orientation_ok')} steps={rotation_check.get('correction_steps')}",
                    flush=True,
                )
                if not rotation_check.get("actions"):
                    break
                execute_correction_actions(rotation_check["actions"], "closed_loop_rotation")

        if final_orientation_task and final_orientation_before_path:
            for check_index in range(FINAL_ORIENTATION_MAX_CHECKS):
                orientation_check = request_final_orientation_check(
                    page,
                    task,
                    result,
                    outdir,
                    final_orientation_before_path,
                    attempt_index=check_index,
                )
                result["final_orientation_checks"].append(orientation_check)
                print(
                    f"[{task['task_id']}] final-orientation check={check_index} "
                    f"ok={orientation_check.get('final_orientation_ok')} side={orientation_check.get('starting_side_ok')} "
                    f"anchor={orientation_check.get('anchor_visible')} "
                    f"position_fix={orientation_check.get('needs_position_correction')} "
                    f"steps={orientation_check.get('correction_steps')}",
                    flush=True,
                )
                if not orientation_check.get("actions"):
                    break
                execute_correction_actions(orientation_check["actions"], "final_orientation")

        if AGENT_ABLATION_MODE == "preset_agent":
            decision_groups = (
                result.get("agent_decisions", []),
                result.get("live_hold_stop_checks", []),
                result.get("adaptive_corrections", []),
                result.get("rotation_loop_checks", []),
                result.get("final_orientation_checks", []),
            )
            has_agent_attempt = any(
                isinstance(record, dict)
                and ("http_status" in record or "decision_latency_ms" in record)
                for records in decision_groups
                for record in (records or [])
            )
            if not has_agent_attempt:
                final_audit = request_adaptive_correction(
                    page,
                    task,
                    result,
                    "final",
                    "final_agent_audit",
                    outdir,
                    phase_done=True,
                    upcoming_dataset_actions=[],
                )
                final_audit["final_agent_audit"] = True
                result["adaptive_corrections"].append(final_audit)
                print(
                    f"[{task['task_id']}] final-agent-audit "
                    f"steps={final_audit.get('correction_steps')} error={final_audit.get('error')}",
                    flush=True,
                )
                execute_correction_actions(final_audit.get("actions", []), "final_agent_audit")

        result["action_elapsed_s"] = time.perf_counter() - start
        page.wait_for_timeout(8000)
        result["url_after_actions"] = page.url
        result["status"] = "actions_completed"
        safe_screenshot(page, outdir / "after_actions.jpg", result, "after_actions_screenshot_error", type="jpeg", quality=85, full_page=True)

        wait_start = time.perf_counter()
        while not (HAPPYOYSTER_HOST_FRAGMENT in page.url and "/end/travel" in page.url) and time.perf_counter() - wait_start < END_WAIT_TIMEOUT_S:
            page.wait_for_timeout(3000)
        click_download_and_save(page, outdir, result)
        return result
    finally:
        screen_recording_result = stop_screen_recording(screen_recording, task["task_id"])
        if screen_recording_result:
            result["screen_recording"] = screen_recording_result
        base_actions = expand_steps(original_action_sequence_steps)
        provenance, deleted = align_action_sources(base_actions, result.get("executed_actions", []), AGENT_ABLATION_MODE or "preset_agent")
        for action, source in zip(result.get("executed_actions", []), provenance):
            action.setdefault("source", source["source"])
            action.setdefault("base_index", source.get("base_index"))
            action.setdefault("observation_path", None)
            action.setdefault("decision_latency_ms", 0)
            action.setdefault("executed_action", action.get("hold_token") or action.get("raw"))
        detailed_provenance = []
        for source in provenance:
            executed = result.get("executed_actions", [])[source["index"] - 1]
            base_index = source.get("base_index")
            detailed_provenance.append({
                **source,
                "base_action": (
                    hold_token_for_actions([base_actions[base_index - 1]])
                    if base_index and base_index <= len(base_actions) else None
                ),
                "executed_action": executed.get("hold_token") or executed.get("raw"),
                "observation_path": executed.get("observation_path"),
                "decision_latency_ms": executed.get("decision_latency_ms", 0),
                "reason": executed.get("reason"),
            })
        detailed_deleted = []
        for source in deleted:
            base_index = source.get("base_index")
            detailed_deleted.append({
                **source,
                "base_action": (
                    hold_token_for_actions([base_actions[base_index - 1]])
                    if base_index and base_index <= len(base_actions) else None
                ),
            })
        result["action_provenance"] = detailed_provenance
        result["deleted_actions"] = detailed_deleted
        if not result.get("executed_action_sequence"):
            result["executed_action_sequence"] = [
                action.get("hold_token") or action.get("raw") for action in result.get("executed_actions", [])
            ]
        if agent_config:
            result["agent_model"] = deployed_controller_model()
            result["agent_response_models"] = list(_CONTROLLER_RESPONSE_MODELS)
            if ADAPTIVE_CORRECTION:
                result["adaptive_model"] = deployed_controller_model()
        agent_call_records = []
        for record_type, records in (
            ("agent_only", result.get("agent_decisions", [])),
            ("live_hold", result.get("live_hold_stop_checks", [])),
            ("adaptive_phase", result.get("adaptive_corrections", [])),
            ("rotation", result.get("rotation_loop_checks", [])),
            ("final_orientation", result.get("final_orientation_checks", [])),
        ):
            for record in records or []:
                if not isinstance(record, dict):
                    continue
                if "http_status" not in record and "decision_latency_ms" not in record:
                    continue
                agent_call_records.append({
                    "type": record_type,
                    "http_status": record.get("http_status", 200 if record_type == "agent_only" else None),
                    "model": record.get("response_model") or record.get("model") or result.get("agent_model"),
                    "decision_latency_ms": record.get("decision_latency_ms") or int(
                        1000 * float(record.get("wall_elapsed_s") or record.get("elapsed_s") or 0)
                    ),
                    "observation_path": record.get("screenshot") or record.get("latest_observation"),
                    "raw_response": record.get("raw_response"),
                })
                if record.get("retry_http_status") is not None:
                    agent_call_records.append({
                        "type": f"{record_type}_retry",
                        "http_status": record.get("retry_http_status"),
                        "model": record.get("retry_response_model") or result.get("agent_model"),
                        "decision_latency_ms": int(1000 * float(record.get("retry_elapsed_s") or 0)),
                        "observation_path": record.get("screenshot"),
                        "raw_response": record.get("retry_raw_response"),
                    })
        result["agent_call_records"] = agent_call_records
        result["agent_call_count"] = len(agent_call_records)
        new_download = result.get("download_path")
        new_result_succeeded = (
            result.get("status") == "actions_completed"
            and result.get("download_status") in {"downloaded", "downloaded_from_downloads"}
            and new_download
            and Path(new_download).is_file()
            and Path(new_download).stat().st_size > 0
        )
        if previous_success_result is not None and not new_result_succeeded:
            failed_path = outdir / f"result_attempt_failed_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            failed_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            result_path.write_text(
                json.dumps(previous_success_result, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            print(f"[{task['task_id']}] preserved previous successful result; failed attempt={failed_path}", flush=True)
        else:
            result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        page.close()


def main():
    if AGENT_ABLATION_MODE == "preset_only":
        controller_preflight = {"skipped": True, "reason": "preset_only_never_calls_agent"}
    elif AGENT_ABLATION_MODE == "agent_only":
        config = configured_agent()
        validate_agent_config(config)
        controller_preflight = {
            "provider": config.provider,
            "model": config.model,
            "transport": config.transport,
            "configured": True,
        }
    else:
        controller_preflight = require_agent_controller()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    tasks = load_tasks()
    print(json.dumps({
        "run_id": RUN_ID,
        "out_dir": str(OUT_DIR),
        "all_tasks": ALL_TASKS,
        "task_count": len(tasks),
        "skip_existing_success": SKIP_EXISTING_SUCCESS,
        "split_by_perspective": SPLIT_BY_PERSPECTIVE,
        "perspective_filter": sorted(PERSPECTIVE_FILTER),
        "ablation_mode": AGENT_ABLATION_MODE or "legacy",
        "agent_controller_preflight": controller_preflight,
    }, ensure_ascii=False), flush=True)
    p = sync_playwright().start()
    all_results = []
    try:
        browser = p.chromium.connect_over_cdp(HAPPYOYSTER_CDP_URL)
        ctx = browser.contexts[0] if browser.contexts else browser.new_context(accept_downloads=True)
        for task in tasks:
            if SKIP_EXISTING_SUCCESS and has_successful_result(task):
                result_path = task_output_dir(task) / "result.json"
                result = json.loads(result_path.read_text(encoding="utf-8"))
                result["status"] = "skipped_existing_success"
                all_results.append(result)
                print(f"\n=== SKIP {task['task_id']} {task.get('perspective')} existing successful result ===", flush=True)
                continue
            print(f"\n=== RUN {task['task_id']} {task.get('perspective')} {task['source_file']} ===", flush=True)
            result = run_task(ctx, task)
            all_results.append(result)
            print(json.dumps({
                "task_id": result["task_id"],
                "status": result.get("status"),
                "result_url": result.get("result_page_url"),
                "download_status": result.get("download_status"),
                "download_path": result.get("download_path"),
                "actions": len(result.get("executed_actions", [])),
            }, ensure_ascii=False, indent=2), flush=True)
            if result.get("status") in {"insufficient_credits", "login_required"}:
                print(
                    f"STOP_AFTER_BLOCKING_STATUS={result.get('status')} task_id={result.get('task_id')}",
                    flush=True,
                )
                break
    finally:
        summary_path = OUT_DIR / "summary.json"
        summary_path.write_text(json.dumps(all_results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        p.stop()
        print(f"SUMMARY={summary_path}", flush=True)


if __name__ == "__main__":
    main()
