#!/usr/bin/env python3
"""Complete Genie3 player migrated from the worldplay_0622 Playwright runner."""

import json
import math
import os
import re
import shutil
import subprocess
import time
import base64
from io import BytesIO
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from datetime import datetime
from pathlib import Path

import httpx
from PIL import Image
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError


REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = Path(os.environ.get("GENIE3_DATA_ROOT", REPO_ROOT / "data"))
OUT_ROOT = Path(os.environ.get("GENIE3_OUT_ROOT", REPO_ROOT / "outputs"))
DOWNLOADS_DIR = Path(os.environ.get("GENIE3_DOWNLOADS_DIR", Path.home() / "Downloads"))
FULL_PROCESS_RECORDING = os.environ.get("GENIE3_FULL_PROCESS_RECORDING", "0") == "1"
FULL_PROCESS_RECORDING_FPS = max(1, int(os.environ.get("GENIE3_FULL_PROCESS_RECORDING_FPS", "5")))
FULL_PROCESS_RECORDING_WIDTH = max(320, int(os.environ.get("GENIE3_FULL_PROCESS_RECORDING_WIDTH", "1280")))
FULL_PROCESS_RECORDING_HEIGHT = max(240, int(os.environ.get("GENIE3_FULL_PROCESS_RECORDING_HEIGHT", "720")))
CHARACTER_OVERRIDES = dict(
    item.split("=", 1)
    for item in os.environ.get("GENIE3_CHARACTER_OVERRIDES", "").split(",")
    if "=" in item
)
GENIE3_CREATE_URL = os.environ.get(
    "GENIE3_CREATE_URL",
    "https://labs.google/fx/projectgenie/zh/tools/projectgenie/creation",
)
GENIE3_HOST_FRAGMENT = os.environ.get("GENIE3_HOST_FRAGMENT", "labs.google")
GENIE3_CDP_URL = os.environ.get("GENIE3_CDP_URL", "http://127.0.0.1:9222")

KIGRESS_BASE_URL = os.environ.get(
    "KIGRESS_BASE_URL",
    "",
).rstrip("/")
KIGRESS_API_KEY = os.environ.get("KIGRESS_API_KEY", "")
KIGRESS_USER_KEY = os.environ.get("KIGRESS_USER_KEY", "")
KIGRESS_MODEL = os.environ.get("KIGRESS_MODEL", "claude-haiku-4-5-20251001")
KIGRESS_BIZ_SCENE = os.environ.get("KIGRESS_BIZ_SCENE", "offline")
AGENT_GUIDANCE = os.environ.get("GENIE3_AGENT_GUIDANCE", "").strip()

DEFAULT_FILES = [
    ("GC", "final_GC.json"),
    ("IF", "final_IF.json"),
    ("OE", "final_OE.json"),
]


def configured_files():
    value = os.environ.get("GENIE3_DATA_FILES", "").strip()
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
    "up": "ArrowUp",
    "down": "ArrowDown",
    "left": "ArrowLeft",
    "right": "ArrowRight",
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

KEY_HOLD_MS = 350
ACTION_INTERVAL_S = 0.85
CREATE_WAIT_TIMEOUT_S = int(os.environ.get("CREATE_WAIT_TIMEOUT_S", "120") or "120")
CREATE_ATTEMPTS = int(os.environ.get("CREATE_ATTEMPTS", "4") or "4")
CREATE_STUCK_RETRY_S = int(os.environ.get("CREATE_STUCK_RETRY_S", "30") or "30")
CREATE_RETRY_DELAY_S = int(os.environ.get("CREATE_RETRY_DELAY_S", "20") or "20")
POST_ACTION_WAIT_S = int(os.environ.get("POST_ACTION_WAIT_S", "240") or "240")
DOWNLOAD_EXPECT_TIMEOUT_MS = int(os.environ.get("DOWNLOAD_EXPECT_TIMEOUT_MS", "45000") or "45000")
DOWNLOAD_JS_FALLBACK_TIMEOUT_MS = int(os.environ.get("DOWNLOAD_JS_FALLBACK_TIMEOUT_MS", "15000") or "15000")
DOWNLOAD_SETTLE_MS = int(os.environ.get("DOWNLOAD_SETTLE_MS", "15000") or "15000")
DOWNLOAD_CLICK_RETRIES = int(os.environ.get("DOWNLOAD_CLICK_RETRIES", "4") or "4")
GENIE3_ERROR_RETRIES = int(os.environ.get("GENIE3_ERROR_RETRIES", "3") or "3")
MIN_UPLOAD_ASPECT = 1.5
MAX_UPLOAD_ASPECT = 2.0
TARGET_UPLOAD_ASPECT = 16 / 9
MAX_UPLOAD_WIDTH = 1600
MIN_UPLOAD_WIDTH = 1280
MIN_UPLOAD_HEIGHT = 720

WORLD_LOADING_TEXTS = (
    "正在创建您的世界",
    "正在创建你的世界",
    "创建您的世界",
    "创建你的世界",
    "Creating your world",
    "creating your world",
    "Loading your world",
    "每次会话都可以保存为视频并分享",
)

DOWNLOAD_TERMS = ("download", "下载", "save", "保存", "export", "导出")
DOWNLOAD_PATTERNS = ("*.mp4", "*.webm", "*.mov")

GENIE3_ERROR_TEXTS = (
    "糟糕，出了点问题",
    "出了点问题",
    "请重试或发送反馈",
    "Oops, something went wrong",
    "Something went wrong",
    "Please try again",
)

AUTH_REQUIRED_TEXTS = (
    "Sign in with Google",
    "使用 Google 账号登录",
    "使用 Google 帐号登录",
    "登录 Google",
)


def env_flag(name, default=False):
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


FAST_REPEAT_PRESS = env_flag("GENIE3_FAST_REPEAT_PRESS", True)
FAST_REPEAT_MIN_COUNT = int(os.environ.get("GENIE3_FAST_REPEAT_MIN_COUNT", "2") or "2")
FAST_REPEAT_CHECK_FRACTION = float(os.environ.get("GENIE3_FAST_REPEAT_CHECK_FRACTION", "0.6") or "0.6")
FAST_REPEAT_SETTLE_S = float(os.environ.get("GENIE3_FAST_REPEAT_SETTLE_S", "0") or "0")
HOLD_SEQUENCE_MODE = env_flag("GENIE3_HOLD_SEQUENCE_MODE", True)
HOLD_MS_PER_ACTION = int(os.environ.get("GENIE3_HOLD_MS_PER_ACTION", "450") or "450")
GUARANTEE_PHASE_COMPLETION = env_flag("GENIE3_GUARANTEE_PHASE_COMPLETION", True)
ACTION_PHASE_BUDGET_S = float(os.environ.get("GENIE3_ACTION_PHASE_BUDGET_S", "55") or "55")
ACTION_PHASE_RESERVE_S = float(os.environ.get("GENIE3_ACTION_PHASE_RESERVE_S", "5") or "5")
INITIAL_ACTION_DELAY_S = float(os.environ.get("GENIE3_INITIAL_ACTION_DELAY_S", "1") or "1")
AUTO_EXIT_AFTER_ACTIONS = env_flag("GENIE3_AUTO_EXIT_AFTER_ACTIONS", False)
WAIT_AND_OBSERVE_S = float(os.environ.get("GENIE3_WAIT_AND_OBSERVE_S", "60") or "60")
ADAPTIVE_CORRECTION = env_flag("GENIE3_ADAPTIVE_CORRECTION", False)
ADAPTIVE_MAX_ACTIONS = int(os.environ.get("GENIE3_ADAPTIVE_MAX_ACTIONS", "3") or "3")
ADAPTIVE_SKIP_REMAINING = env_flag("GENIE3_ADAPTIVE_SKIP_REMAINING", True)
REQUIRE_FULL_ACTION_SEQUENCE = env_flag("GENIE3_REQUIRE_FULL_ACTION_SEQUENCE", False)
ADAPTIVE_PRETHINK = env_flag("GENIE3_ADAPTIVE_PRETHINK", False)
ADAPTIVE_PRETHINK_TIMEOUT_S = float(os.environ.get("GENIE3_ADAPTIVE_PRETHINK_TIMEOUT_S", "20") or "20")
ADAPTIVE_PRE_PHASE_PLAN_MIN_MS = int(os.environ.get("GENIE3_ADAPTIVE_PRE_PHASE_PLAN_MIN_MS", "0") or "0")
ADAPTIVE_PHASE_DONE_CHECK = env_flag("GENIE3_ADAPTIVE_PHASE_DONE_CHECK", ADAPTIVE_CORRECTION)
ADAPTIVE_PHASE_PROGRESS_CHECK = env_flag("GENIE3_ADAPTIVE_PHASE_PROGRESS_CHECK", ADAPTIVE_CORRECTION)
ADAPTIVE_PHASE_CHECK_EVERY = max(1, int(os.environ.get("GENIE3_ADAPTIVE_PHASE_CHECK_EVERY", "3") or "3"))
ADAPTIVE_EXTEND_HOLD = env_flag("GENIE3_ADAPTIVE_EXTEND_HOLD", ADAPTIVE_CORRECTION)
ADAPTIVE_EXTEND_HOLD_MIN_MS = int(os.environ.get("GENIE3_ADAPTIVE_EXTEND_HOLD_MIN_MS", "2000") or "2000")
ADAPTIVE_EXTEND_HOLD_MAX_MS = int(os.environ.get("GENIE3_ADAPTIVE_EXTEND_HOLD_MAX_MS", "2400") or "2400")
ADAPTIVE_EXTEND_HOLD_MAX_ROUNDS = int(os.environ.get("GENIE3_ADAPTIVE_EXTEND_HOLD_MAX_ROUNDS", "1") or "1")
ADAPTIVE_SKIP_MIN_PHASE_FRACTION = float(
    os.environ.get("GENIE3_ADAPTIVE_SKIP_MIN_PHASE_FRACTION", "0.6") or "0.6"
)
ADAPTIVE_TIMEOUT_S = float(os.environ.get("GENIE3_ADAPTIVE_TIMEOUT_S", "90") or "90")
ADAPTIVE_INTER_KEY_TIMEOUT_S = float(os.environ.get("GENIE3_ADAPTIVE_INTER_KEY_TIMEOUT_S", "5") or "5")
ADAPTIVE_SCREENSHOT_MAX_WIDTH = int(os.environ.get("GENIE3_ADAPTIVE_SCREENSHOT_MAX_WIDTH", "640") or "640")
ADAPTIVE_SCREENSHOT_MAX_HEIGHT = int(os.environ.get("GENIE3_ADAPTIVE_SCREENSHOT_MAX_HEIGHT", "360") or "360")
ADAPTIVE_SCREENSHOT_QUALITY = int(os.environ.get("GENIE3_ADAPTIVE_SCREENSHOT_QUALITY", "40") or "40")
ADAPTIVE_CONTEXT_ACTIONS = int(os.environ.get("GENIE3_ADAPTIVE_CONTEXT_ACTIONS", "5") or "5")
ADAPTIVE_MAX_COMPLETION_TOKENS = int(os.environ.get("GENIE3_ADAPTIVE_MAX_COMPLETION_TOKENS", "100") or "100")
LIVE_HOLD_MAX_COMPLETION_TOKENS = int(os.environ.get("GENIE3_LIVE_HOLD_MAX_COMPLETION_TOKENS", "64") or "64")
LIVE_HOLD_STOP_CHECK = env_flag("GENIE3_LIVE_HOLD_STOP_CHECK", False)
LIVE_HOLD_CHECK_INTERVAL_MS = int(os.environ.get("GENIE3_LIVE_HOLD_CHECK_INTERVAL_MS", "50") or "50")
LIVE_HOLD_MIN_MS = int(os.environ.get("GENIE3_LIVE_HOLD_MIN_MS", "0") or "0")
LIVE_HOLD_MIN_APPLY_MS = int(os.environ.get("GENIE3_LIVE_HOLD_MIN_APPLY_MS", "600") or "600")
LIVE_HOLD_MIN_REMAINING_MS = int(os.environ.get("GENIE3_LIVE_HOLD_MIN_REMAINING_MS", "0") or "0")
LIVE_HOLD_MAX_CHECKS = int(os.environ.get("GENIE3_LIVE_HOLD_MAX_CHECKS", "20") or "20")
LIVE_HOLD_TIMEOUT_S = float(os.environ.get("GENIE3_LIVE_HOLD_TIMEOUT_S", "8") or "8")
LIVE_HOLD_SCREENSHOT_QUALITY = int(os.environ.get("GENIE3_LIVE_HOLD_SCREENSHOT_QUALITY", "45") or "45")
LIVE_HOLD_SCREENSHOT_TIMEOUT_MS = int(os.environ.get("GENIE3_LIVE_HOLD_SCREENSHOT_TIMEOUT_MS", "1200") or "1200")
LIVE_HOLD_MAX_ADAPTIVE_ACTIONS = int(os.environ.get("GENIE3_LIVE_HOLD_MAX_ADAPTIVE_ACTIONS", "2") or "2")
LIVE_HOLD_ADAPTIVE_MIN_MS = int(os.environ.get("GENIE3_LIVE_HOLD_ADAPTIVE_MIN_MS", "200") or "200")
LIVE_HOLD_ADAPTIVE_MAX_REPEAT = int(os.environ.get("GENIE3_LIVE_HOLD_ADAPTIVE_MAX_REPEAT", "4") or "4")
LIVE_HOLD_ADAPTIVE_MAX_MS = int(
    os.environ.get("GENIE3_LIVE_HOLD_ADAPTIVE_MAX_MS", str(HOLD_MS_PER_ACTION * LIVE_HOLD_ADAPTIVE_MAX_REPEAT))
    or str(HOLD_MS_PER_ACTION * LIVE_HOLD_ADAPTIVE_MAX_REPEAT)
)
ROTATION_LOOP_CHECK = env_flag("GENIE3_ROTATION_LOOP_CHECK", ADAPTIVE_CORRECTION)
ROTATION_LOOP_MAX_ACTIONS = int(os.environ.get("GENIE3_ROTATION_LOOP_MAX_ACTIONS", "4") or "4")
ROTATION_LOOP_MAX_CHECKS = int(os.environ.get("GENIE3_ROTATION_LOOP_MAX_CHECKS", "2") or "2")
ROTATION_LOOP_SKIP_REMAINING = env_flag("GENIE3_ROTATION_LOOP_SKIP_REMAINING", ROTATION_LOOP_CHECK)
ROTATION_LOOP_SKIP_MIN_ACTIONS = int(os.environ.get("GENIE3_ROTATION_LOOP_SKIP_MIN_ACTIONS", "8") or "8")
ROTATION_LOOP_SKIP_CHECK_EVERY = int(os.environ.get("GENIE3_ROTATION_LOOP_SKIP_CHECK_EVERY", "2") or "2")
FINAL_ORIENTATION_CHECK = env_flag("GENIE3_FINAL_ORIENTATION_CHECK", ADAPTIVE_CORRECTION)
FINAL_ORIENTATION_MAX_ACTIONS = int(os.environ.get("GENIE3_FINAL_ORIENTATION_MAX_ACTIONS", "4") or "4")
FINAL_ORIENTATION_MAX_CHECKS = int(os.environ.get("GENIE3_FINAL_ORIENTATION_MAX_CHECKS", "2") or "2")
ROTATION_BASE_EXTRA_UNITS = max(0, int(os.environ.get("GENIE3_ROTATION_BASE_EXTRA_UNITS", "0") or "0"))
FORCE_CIRCLE_RETURN_PROMPT = env_flag("GENIE3_FORCE_CIRCLE_RETURN_PROMPT", True)
KIGRESS_TRUST_ENV = env_flag("KIGRESS_TRUST_ENV", False)
ALL_TASKS = env_flag("GENIE3_ALL_TASKS")
RUN_STARTED_AT = datetime.now()
RUN_ID = os.environ.get(
    "GENIE3_RUN_ID",
    RUN_STARTED_AT.strftime(
        ("all_entries_actionseq_genie3_" if ALL_TASKS else "first_entries_actionseq_genie3_") + "%Y%m%d_%H%M%S"
    ),
)


def run_timestamp_from_id(run_id):
    six_digit = re.findall(r"(20\d{6})_(\d{6})(?!\d)", run_id)
    if six_digit:
        return "_".join(six_digit[-1])
    four_digit = re.findall(r"(20\d{6})_(\d{4})(?!\d)", run_id)
    if four_digit:
        day, time_value = four_digit[-1]
        return f"{day}_{time_value}00"
    return RUN_STARTED_AT.strftime("%Y%m%d_%H%M%S")


RUN_TIMESTAMP = run_timestamp_from_id(RUN_ID)
RUN_LOG_ROOT = Path(os.environ.get("GENIE3_RUN_LOG_ROOT", OUT_ROOT.parent / f"{OUT_ROOT.name}-logs"))
RUN_META_DIR = RUN_LOG_ROOT / RUN_ID
SKIP_EXISTING_SUCCESS = env_flag("SKIP_EXISTING_SUCCESS", True)
SKIP_EXISTING_TERMINAL_FAILURE = env_flag("SKIP_EXISTING_TERMINAL_FAILURE", True)


def normalize_perspective(value):
    normalized = (value or "").strip().lower().replace("_", "-")
    if normalized in {"first", "first-person", "first person", "fp"}:
        return "first-person"
    if normalized in {"third", "third-person", "third person", "tp"}:
        return "third-person"
    return "unknown"


def perspective_dir_name(perspective):
    return normalize_perspective(perspective).replace("-", "_")


def infer_group(item, fallback=None):
    if fallback:
        return fallback
    value = item.get("group") or item.get("category") or item.get("task_id") or item.get("id") or ""
    match = re.match(r"^([A-Z]+)", str(value))
    return match.group(1) if match else "CUSTOM"


def genie3_error_text(text):
    text = text or ""
    for token in GENIE3_ERROR_TEXTS:
        if token in text:
            return token
    return None


def auth_required_text(text):
    text = text or ""
    for token in AUTH_REQUIRED_TEXTS:
        if token in text:
            return token
    return None


def record_auth_required(result, phase, state, matched_text=None):
    matched_text = matched_text or auth_required_text(state.get("text"))
    event = {
        "phase": phase,
        "matched_text": matched_text,
        "url": state.get("url"),
        "buttons": [b.get("text") for b in state.get("buttons", [])[:20]],
        "text": (state.get("text") or "")[:500],
    }
    result.setdefault("auth_required_events", []).append(event)
    result["status"] = "auth_required"
    result["auth_required_phase"] = phase
    result["auth_required_text"] = matched_text
    return event


def record_genie3_error(result, phase, state, matched_text):
    event = {
        "phase": phase,
        "matched_text": matched_text,
        "url": state.get("url"),
        "buttons": [b.get("text") for b in state.get("buttons", [])[:20]],
        "text": (state.get("text") or "")[:500],
    }
    result.setdefault("genie3_error_events", []).append(event)
    result["status"] = "genie3_retryable_error"
    result["genie3_error_phase"] = phase
    result["genie3_error_text"] = matched_text
    return event


PERSPECTIVE_FILTER = {
    normalize_perspective(x)
    for x in os.environ.get("PERSPECTIVES", "").split(",")
    if x.strip()
}


def make_landscape_upload_image(src_path, dst_path):
    img = Image.open(src_path).convert("RGB")
    original_w, original_h = img.size
    original_aspect = original_w / original_h
    crop_box = [0, 0, original_w, original_h]
    upscaled_to_minimum = False

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

    if img.width < MIN_UPLOAD_WIDTH or img.height < MIN_UPLOAD_HEIGHT:
        scale = max(MIN_UPLOAD_WIDTH / img.width, MIN_UPLOAD_HEIGHT / img.height)
        resized_w = max(MIN_UPLOAD_WIDTH, int(round(img.width * scale)))
        resized_h = max(MIN_UPLOAD_HEIGHT, int(round(img.height * scale)))
        img = img.resize((resized_w, resized_h), Image.Resampling.LANCZOS)
        left = max(0, (img.width - MIN_UPLOAD_WIDTH) // 2)
        top = max(0, (img.height - MIN_UPLOAD_HEIGHT) // 2)
        img = img.crop((left, top, left + MIN_UPLOAD_WIDTH, top + MIN_UPLOAD_HEIGHT))
        upscaled_to_minimum = True

    dst_path.parent.mkdir(parents=True, exist_ok=True)
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
        "minimum_upload_size": [MIN_UPLOAD_WIDTH, MIN_UPLOAD_HEIGHT],
        "upscaled_to_minimum": upscaled_to_minimum,
    }


def load_tasks():
    tasks = []
    only_order = [x.strip() for x in os.environ.get("TASK_IDS", "").split(",") if x.strip()]
    only = set(only_order)
    task_offset = int(os.environ.get("TASK_OFFSET", "0") or "0")
    task_limit = int(os.environ.get("TASK_LIMIT", "0") or "0")
    for group, filename in FILES:
        data_path = Path(filename)
        if not data_path.is_absolute():
            data_path = DATA_ROOT / data_path
        data = json.load(open(data_path, encoding="utf-8"))
        for source_item in data:
            if only and source_item.get("task_id") not in only:
                continue
            if not only and not ALL_TASKS and source_item is not data[0]:
                continue
            item = dict(source_item)
            item["perspective_normalized"] = normalize_perspective(item.get("perspective"))
            if PERSPECTIVE_FILTER and item["perspective_normalized"] not in PERSPECTIVE_FILTER:
                continue
            item["group"] = infer_group(item, group)
            item["source_file"] = str(data_path)
            item["resolved_image_path"] = str(DATA_ROOT / item["image_path"])
            tasks.append(item)
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
    return OUT_ROOT / f"{task['task_id']}_{RUN_TIMESTAMP}"


def current_native_video(task):
    outdir = task_output_dir(task)
    for path in sorted(outdir.glob(f"{task['task_id']}_native.*")):
        if path.is_file() and path.stat().st_size > 1000:
            return path
    return None


def has_successful_result(task):
    result_path = task_output_dir(task) / "result.json"
    if not result_path.exists():
        return False
    try:
        result = json.loads(result_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return False
    download_path = result.get("download_path")
    download_exists = bool(download_path) and Path(download_path).exists()
    native_video = current_native_video(task)
    return (
        result.get("status") in {"downloaded", "completed"}
        and result.get("download_status") in {"downloaded", "downloaded_from_downloads"}
        and (download_exists or native_video is not None)
    )


def has_terminal_failure_result(task):
    result_path = task_output_dir(task) / "result.json"
    if not result_path.exists():
        return False
    try:
        result = json.loads(result_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return False
    if result.get("status") in {
        "auth_required",
        "explore_not_ready",
        "interactive_not_ready",
        "skipped_genie3_error_retries_exceeded",
    }:
        return True
    return (
        result.get("status") == "completed_without_download"
        and result.get("download_status") in {"no_modal_download_button", "no_download_button"}
    )


def box_state(page):
    last_error = None
    for _ in range(5):
        try:
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
        except Exception as exc:
            last_error = exc
            page.wait_for_timeout(500)
    raise last_error


def upload_start_image(page, image_path):
    try:
        page.wait_for_function(
            """() => {
              const visible = el => {
                const r = el.getBoundingClientRect();
                const s = getComputedStyle(el);
                return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none';
              };
              const hasUploadButton = Array.from(document.querySelectorAll('button,[role="button"]')).filter(visible).some(el => {
                const text = (el.innerText || el.getAttribute('aria-label') || '').toLowerCase();
                return text.includes('image') || text.includes('upload') || text.includes('photo')
                  || text.includes('图片') || text.includes('上传') || text.includes('媒体');
              });
              return !!document.querySelector('input[type=file]') || hasUploadButton;
            }""",
            timeout=30000,
        )
    except PlaywrightTimeoutError:
        pass
    has_upload_control = page.evaluate(
        """() => {
          const visible = el => {
            const r = el.getBoundingClientRect();
            const s = getComputedStyle(el);
            return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none';
          };
          const uploadText = el => (el.innerText || el.getAttribute('aria-label') || '').toLowerCase();
          return !!document.querySelector('input[type=file]')
            || Array.from(document.querySelectorAll('button,[role="button"]')).filter(visible).some(el => {
              const text = uploadText(el);
              return text.includes('image') || text.includes('upload') || text.includes('photo')
                || text.includes('图片') || text.includes('上传') || text.includes('媒体');
            });
        }"""
    )
    if not has_upload_control:
        return {"method": "text_only_no_upload_control", "image": str(image_path), "skipped": True}

    if env_flag("GENIE3_UPLOAD_VISIBLE_FIRST", False):
        image_button = page.locator(
            '[role="button"][aria-label*="Image" i], '
            '[role="button"][aria-label*="Upload" i], '
            'button:has-text("Image"), '
            'button:has-text("Upload"), '
            'button:has-text("Reference"), '
            'button:has-text("photo"), '
            'button:has-text("图片"), '
            'button:has-text("上传"), '
            'button:has-text("媒体")'
        ).first
        try:
            image_button.wait_for(state="visible", timeout=8000)
            with page.expect_file_chooser(timeout=10000) as chooser_info:
                image_button.click()
            chooser_info.value.set_files(str(image_path), timeout=120000)
            return {"method": "file_chooser_preferred", "image": str(image_path)}
        except PlaywrightTimeoutError:
            pass

    try:
        page.locator("input[type=file]").first.wait_for(state="attached", timeout=30000)
        inputs = page.locator("input[type=file]")
        count = inputs.count()
        errors = []
        for index in range(count - 1, -1, -1):
            try:
                inputs.nth(index).set_input_files(str(image_path), timeout=15000)
                return {"method": "hidden_file_input_preferred", "image": str(image_path), "input_index": index}
            except Exception as exc:
                errors.append({"input_index": index, "error": repr(exc)})
        if errors:
            print(f"hidden file input upload failed: {errors}", flush=True)
    except PlaywrightTimeoutError:
        pass

    image_button = page.locator(
        '[role="button"][aria-label*="Image" i], '
        '[role="button"][aria-label*="Upload" i], '
        'button:has-text("Image"), '
        'button:has-text("Upload"), '
        'button:has-text("Reference"), '
        'button:has-text("photo"), '
        'button:has-text("图片"), '
        'button:has-text("上传"), '
        'button:has-text("媒体")'
    ).first
    try:
        image_button.wait_for(state="visible", timeout=30000)
        with page.expect_file_chooser(timeout=10000) as chooser_info:
            image_button.click()
        chooser_info.value.set_files(str(image_path), timeout=120000)
        return {"method": "file_chooser", "image": str(image_path)}
    except PlaywrightTimeoutError:
        try:
            page.locator("input[type=file]").first.wait_for(state="attached", timeout=30000)
        except PlaywrightTimeoutError:
            pass
        inputs = page.locator("input[type=file]")
        count = inputs.count()
        errors = []
        for index in range(count - 1, -1, -1):
            try:
                inputs.nth(index).set_input_files(str(image_path), timeout=15000)
                return {"method": "hidden_file_input_fallback", "image": str(image_path), "input_index": index}
            except Exception as exc:
                errors.append({"input_index": index, "error": repr(exc)})
        raise RuntimeError(f"Could not upload image through {count} file inputs: {errors}")


def open_create_panel(page, result, suffix):
    if "/creation" in page.url:
        return {"status": "already_open", "url": page.url}

    try:
        page.locator(
            '[role="button"][aria-label*="Image" i], '
            '[role="button"][aria-label*="Upload" i], '
            'button:has-text("Image"), '
            'button:has-text("Upload"), '
            'button:has-text("photo"), '
            'button:has-text("图片"), '
            'button:has-text("上传"), '
            'input[type=file]'
        ).first.wait_for(state="visible", timeout=5000)
        return {"status": "already_open"}
    except PlaywrightTimeoutError:
        pass

    for label in ("创建新项目", "Create new project", "New project"):
        try:
            locator = page.locator("button").filter(has_text=label).first
            locator.scroll_into_view_if_needed(timeout=3000)
            locator.evaluate("el => el.click()", timeout=5000)
            try:
                page.wait_for_url("**/creation**", timeout=30000)
            except PlaywrightTimeoutError:
                pass
            page.wait_for_timeout(1500)
            if "/creation" in page.url:
                return {"status": "clicked", "button": {"text": label, "method": "locator"}, "url": page.url}
        except Exception:
            pass

    state = box_state(page)
    candidates = [
        b for b in state["buttons"]
        if "create with project genie" in b["text"].lower()
        or "create your world" in b["text"].lower()
        or "create your own" in b["text"].lower()
        or "create a world" in b["text"].lower()
        or "制作自己的作品" in b["text"]
        or "创建" in b["text"]
        or "制作" in b["text"]
        or "click to create your world" in b["text"].lower()
        or b["text"].strip().lower() in {"create", "explore now"}
        or b["text"].strip().lower() in {"get started", "start creating"}
    ]
    if not candidates:
        if "projectgenie" in state["url"] and "creation" not in state["url"]:
            viewport = page.viewport_size or page.evaluate("() => ({width: window.innerWidth, height: window.innerHeight})")
            page.mouse.click(viewport["width"] / 2, viewport["height"] / 2)
            page.wait_for_timeout(2500)
            if "/creation" in page.url:
                return {"status": "clicked_orb_fallback", "url": page.url}
        result[f"create_entry_state{suffix}"] = state
        return {"status": "entry_not_found", "url": state["url"]}

    button = sorted(candidates, key=lambda b: b["box"]["w"] * b["box"]["h"], reverse=True)[0]
    page.mouse.click(button["box"]["x"] + button["box"]["w"] / 2, button["box"]["y"] + button["box"]["h"] / 2)
    try:
        page.wait_for_url("**/creation**", timeout=30000)
    except PlaywrightTimeoutError:
        pass
    page.wait_for_timeout(1500)
    try:
        if "/creation" in page.url:
            return {"status": "clicked", "button": button, "url": page.url}
        page.locator(
            '[role="button"][aria-label*="Image" i], '
            '[role="button"][aria-label*="Upload" i], '
            'button:has-text("Image"), '
            'button:has-text("Upload"), '
            'button:has-text("photo"), '
            'button:has-text("图片"), '
            'button:has-text("上传"), '
            'input[type=file]'
        ).first.wait_for(state="visible", timeout=30000)
        return {"status": "clicked", "button": button}
    except PlaywrightTimeoutError:
        result[f"create_entry_state_after_click{suffix}"] = box_state(page)
        return {"status": "panel_not_ready_after_click", "button": button}


def wait_create_input_ready(page, fields, result):
    start = time.perf_counter()
    while time.perf_counter() - start < 60:
        state = page.evaluate(
            """(fields) => {
              const box = el => {
                const r = el.getBoundingClientRect();
                return {x:r.x, y:r.y, w:r.width, h:r.height};
              };
              const visible = el => {
                const r = el.getBoundingClientRect();
                const s = getComputedStyle(el);
                return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none';
              };
              const editors = Array.from(document.querySelectorAll('textarea,[contenteditable="true"]')).filter(visible);
              const editorValues = editors.map(el => el.value || el.innerText || el.textContent || '');
              const editorText = editorValues.join('\\n');
              const hasEnvironment = editorValues.some(text => text.includes(fields.environment.slice(0, 40)));
              const hasCharacter = !fields.character || editorValues.some(text => text.includes(fields.character.slice(0, 40)));
              const previewImgs = Array.from(document.querySelectorAll('img')).filter(visible).filter(img => {
                const r = img.getBoundingClientRect();
                return r.width >= 30 && r.height >= 30 && r.y > window.innerHeight * 0.45;
              });
              const imageButton = document.querySelector(
                '[role="button"][aria-label*="Image" i], [role="button"][aria-label*="Upload" i], button'
              );
              const imageButtonHasMedia = !!(imageButton && (
                imageButton.querySelectorAll('img').length > 0 ||
                Array.from(imageButton.querySelectorAll('*')).some(el => {
                  const bg = getComputedStyle(el).backgroundImage || '';
                  return bg && bg !== 'none' && !bg.includes('plus') && !bg.includes('add');
                })
              ));
              const hasUploadControl = !!document.querySelector('input[type=file]') ||
                Array.from(document.querySelectorAll('button,[role="button"]')).filter(visible).some(el => {
                  const text = (el.innerText || el.getAttribute('aria-label') || '').toLowerCase();
                  return text.includes('image') || text.includes('upload') || text.includes('photo')
                    || text.includes('图片') || text.includes('上传') || text.includes('媒体');
              });
              const pageText = (document.body.innerText || '').slice(0, 5000);
              return {
                url: location.href,
                text: pageText,
                hasPrompt: hasEnvironment && hasCharacter,
                hasEnvironment,
                hasCharacter,
                hasPreview: previewImgs.length > 0 || imageButtonHasMedia,
                hasUploadControl,
                editorText: editorText.slice(0, 240),
                previewCount: previewImgs.length,
                imageButtonBox: imageButton ? box(imageButton) : null,
              };
            }""",
            fields,
        )
        auth_text = auth_required_text(state.get("text"))
        if auth_text:
            record_auth_required(result, "input_ready_wait", state, auth_text)
            return False
        ready = state["hasPrompt"] and (
            fields.get("_allow_text_only") or state["hasPreview"] or not state["hasUploadControl"]
        )
        result.setdefault("input_ready_wait", []).append({"elapsed_s": time.perf_counter() - start, **state, "ready": ready})
        print(
            f"[{result['task_id']}] input-ready {time.perf_counter()-start:.1f}s ready={ready} "
            f"prompt={state['hasPrompt']} preview={state['hasPreview']}",
            flush=True,
        )
        if ready:
            result["input_ready_state"] = state
            return True
        page.wait_for_timeout(1000)
    return False


def wait_submit_ready(page):
    return page.wait_for_function(
        """() => {
          const visible = el => {
            const r = el.getBoundingClientRect();
            const s = getComputedStyle(el);
            return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none';
          };
          return Array.from(document.querySelectorAll('button')).some(b => {
            const r = b.getBoundingClientRect();
            const text = (b.innerText || b.getAttribute('aria-label') || '').trim().toLowerCase();
            return visible(b)
              && !b.disabled
              && b.getAttribute('aria-disabled') !== 'true'
              && (
                (r.width <= 80 && r.height <= 80 && r.x > window.innerWidth * 0.60 && r.y > window.innerHeight * 0.45) ||
                ['create', 'generate', 'enter world', 'explore', 'start', 'preview', '创建', '生成', '制作', '进入', '探索', '开始', '预览'].some(t => text.includes(t))
              );
          });
        }""",
        timeout=90000,
    )


def click_submit(page):
    return page.evaluate(
        """() => {
          const box = el => { const r = el.getBoundingClientRect(); return {x:r.x,y:r.y,w:r.width,h:r.height}; };
          const visible = el => {
            const r = el.getBoundingClientRect();
            const s = getComputedStyle(el);
            return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none';
          };
          const buttons = Array.from(document.querySelectorAll('button')).filter(visible)
            .map(b => ({
              b,
              r:b.getBoundingClientRect(),
              text:(b.innerText || b.getAttribute('aria-label') || '').trim().toLowerCase(),
              disabled:!!b.disabled || b.getAttribute('aria-disabled') === 'true'
            }))
            .filter(({r, text, disabled}) => !disabled && (
              (r.width <= 80 && r.height <= 80 && r.x > window.innerWidth * 0.60 && r.y > window.innerHeight * 0.45) ||
              ['create', 'generate', 'enter world', 'explore', 'start', 'preview', '创建', '生成', '制作', '进入', '探索', '开始', '预览'].some(t => text.includes(t))
            ))
            .sort((a,b) => {
              const score = x => {
                if (x.text.includes('enter world') || x.text.includes('explore') || x.text.includes('进入') || x.text.includes('探索')) return 4;
                if (x.text.includes('create') || x.text.includes('generate') || x.text.includes('创建') || x.text.includes('生成') || x.text.includes('制作')) return 3;
                return x.r.x / window.innerWidth;
              };
              return score(b) - score(a);
            });
          if (buttons.length) {
            const c = buttons[0];
            c.b.click();
            return {clicked:true, box:box(c.b)};
          }
          return {clicked:false};
        }"""
    )


def set_perspective(page, desired_perspective):
    desired = normalize_perspective(desired_perspective)
    if desired not in {"first-person", "third-person"}:
        return {"desired": desired, "status": "unknown_perspective"}

    desired_labels = {"First person", "第一人称"} if desired == "first-person" else {"Third person", "第三人称"}
    opposite_labels = {"Third person", "第三人称"} if desired == "first-person" else {"First person", "第一人称"}

    for _ in range(3):
        state = box_state(page)
        perspective_buttons = [
            b for b in state["buttons"]
            if any(label in b["text"] for label in {"First person", "Third person", "第一人称", "第三人称"})
        ]
        if not perspective_buttons:
            page.wait_for_timeout(500)
            continue

        button = perspective_buttons[0]
        if any(label in button["text"] for label in desired_labels):
            return {
                "desired": desired,
                "selected_label": button["text"],
                "clicked": False,
                "status": "already_selected",
            }
        if any(label in button["text"] for label in opposite_labels):
            page.mouse.click(button["box"]["x"] + button["box"]["w"] / 2, button["box"]["y"] + button["box"]["h"] / 2)
            page.wait_for_timeout(800)
            continue

    state = box_state(page)
    labels = [
        b["text"] for b in state["buttons"]
        if any(label in b["text"] for label in {"First person", "Third person", "第一人称", "第三人称"})
    ]
    return {
        "desired": desired,
        "selected_label": labels[0] if labels else None,
        "clicked": True,
        "status": "selected" if labels and any(label in labels[0] for label in desired_labels) else "not_confirmed",
    }


def wait_for_explore(page, result):
    start = time.perf_counter()
    while time.perf_counter() - start < CREATE_WAIT_TIMEOUT_S:
        state = box_state(page)
        text = state["text"] or ""
        auth_text = auth_required_text(text)
        error_text = genie3_error_text(text)
        lower_url = state["url"].lower()
        host_ready = GENIE3_HOST_FRAGMENT in lower_url
        route_ready = any(fragment in lower_url for fragment in ("/explore", "/world", "/play", "/view", "/w"))
        interactive_text = any(token in text for token in ("REC", "left for you", "W", "A", "S", "D", "60s"))
        visual_ready = bool(state["canvases"] or state["videos"])
        world_loading = any(token in text for token in WORLD_LOADING_TEXTS)
        result.setdefault("create_wait", []).append({
            "elapsed_s": time.perf_counter() - start,
            "url": state["url"],
            "canvas": len(state["canvases"]),
            "video": len(state["videos"]),
            "interactive_text": interactive_text,
            "world_loading": world_loading,
            "auth_required": auth_text,
            "genie3_error": error_text,
        })
        print(
            f"[{result['task_id']}] wait {time.perf_counter()-start:.1f}s "
            f"url={state['url']} video={len(state['videos'])} loading={world_loading}",
            flush=True,
        )
        if auth_text:
            record_auth_required(result, "create_wait", state, auth_text)
            return False
        if error_text:
            record_genie3_error(result, "create_wait", state, error_text)
            return False
        if host_ready and visual_ready and not world_loading and (route_ready or interactive_text):
            return True
        if host_ready and not route_ready and not visual_ready and time.perf_counter() - start >= CREATE_STUCK_RETRY_S:
            result.setdefault("create_stuck_retries", []).append({
                "elapsed_s": time.perf_counter() - start,
                "url": state["url"],
            })
            return False
        page.wait_for_timeout(2000)
    return False


def wait_for_interactive(page, result):
    start = time.perf_counter()
    while time.perf_counter() - start < max(90, CREATE_WAIT_TIMEOUT_S):
        state = box_state(page)
        text = state["text"] or ""
        auth_text = auth_required_text(text)
        error_text = genie3_error_text(text)
        world_loading = any(token in text for token in WORLD_LOADING_TEXTS)
        ready = bool(state["videos"] or state["canvases"]) and (
            "left for you" in text
            or "REC" in text
            or "60s" in text
            or any(t in text.split() for t in ("W", "A", "S", "D"))
        ) and not world_loading
        result.setdefault("interactive_wait", []).append({
            "elapsed_s": time.perf_counter() - start,
            "ready": ready,
            "url": state["url"],
            "video": len(state["videos"]),
            "canvas": len(state["canvases"]),
            "world_loading": world_loading,
            "auth_required": auth_text,
            "genie3_error": error_text,
            "text": text[:300],
        })
        print(f"[{result['task_id']}] interactive {time.perf_counter()-start:.1f}s ready={ready}", flush=True)
        if auth_text:
            record_auth_required(result, "interactive_wait", state, auth_text)
            return False
        if error_text:
            record_genie3_error(result, "interactive_wait", state, error_text)
            return False
        if ready:
            return True
        page.wait_for_timeout(1000)
    return False


def files_snapshot():
    paths = []
    for suffix in DOWNLOAD_PATTERNS:
        paths.extend(DOWNLOADS_DIR.glob(suffix))
    return {str(p): (p.stat().st_mtime, p.stat().st_size) for p in paths if p.exists()}


def find_new_download(before, min_bytes=1000):
    after = files_snapshot()
    new_paths = [Path(p) for p in after if p not in before and after[p][1] > min_bytes]
    if new_paths:
        return max(new_paths, key=lambda p: p.stat().st_mtime)
    return None


def find_recent_download(before, started_at, min_bytes=1000):
    found = find_new_download(before, min_bytes=min_bytes)
    if found:
        return found

    recent = []
    cutoff = started_at - 15
    for pattern in DOWNLOAD_PATTERNS:
        for path in DOWNLOADS_DIR.glob(pattern):
            if not path.exists() or path.stat().st_size <= min_bytes:
                continue
            mtime = path.stat().st_mtime
            if mtime >= cutoff:
                recent.append(path)
    if recent:
        return max(recent, key=lambda p: p.stat().st_mtime)
    return None


def find_recent_genie_download(started_at, min_bytes=1000, lookback_s=180):
    recent = []
    cutoff = started_at - lookback_s
    for suffix in (".mp4", ".webm", ".mov"):
        for path in DOWNLOADS_DIR.glob(f"Genie*{suffix}"):
            if path.exists() and path.stat().st_size > min_bytes and path.stat().st_mtime >= cutoff:
                recent.append(path)
    if recent:
        return max(recent, key=lambda p: p.stat().st_mtime)
    return None


def find_download_buttons(state):
    return [
        b for b in state["buttons"]
        if not b.get("disabled")
        and any(term in (b["text"] or "").lower() for term in DOWNLOAD_TERMS)
    ]


def same_button_box(left, right, tolerance=3):
    return all(abs(left.get(key, 0) - right.get(key, 0)) <= tolerance for key in ("x", "y", "w", "h"))


def save_download_object(download, outdir, result):
    suffix = Path(download.suggested_filename).suffix or ".mp4"
    out = outdir / f"{result['task_id']}_native{suffix}"
    download.save_as(str(out))
    result["download_bytes"] = out.stat().st_size
    if result["download_bytes"] > 1000:
        result["download_status"] = "downloaded"
    else:
        result["download_status"] = "download_empty"
    result["download_path"] = str(out)


def save_found_download(found, outdir, result):
    out = outdir / f"{result['task_id']}_native{found.suffix or '.mp4'}"
    shutil.move(str(found), str(out))
    result["download_status"] = "downloaded_from_downloads"
    result["download_path"] = str(out)
    result["download_bytes"] = out.stat().st_size


def recover_empty_download(before, started_at, outdir, result):
    if result.get("download_bytes", 0) > 1000:
        return False
    found = None
    for _ in range(30):
        found = find_recent_download(before, started_at)
        if found:
            break
        time.sleep(2)
    if not found:
        found = find_recent_genie_download(started_at)
    if found:
        save_found_download(found, outdir, result)
        return True
    return False


def wait_for_download_file(before, started_at, timeout_s=45):
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        found = find_recent_download(before, started_at)
        if found:
            return found
        time.sleep(2)
    return find_recent_genie_download(started_at)


def configure_browser_downloads(browser):
    try:
        session = browser.new_browser_cdp_session()
        session.send(
            "Browser.setDownloadBehavior",
            {
                "behavior": "allow",
                "downloadPath": str(DOWNLOADS_DIR),
                "eventsEnabled": True,
            },
        )
        return {"configured": True, "download_path": str(DOWNLOADS_DIR)}
    except Exception as exc:
        return {"configured": False, "error": repr(exc)}


class FullProcessRecorder:
    def __init__(self, page, outdir, task_id):
        self.page = page
        self.outdir = Path(outdir)
        self.task_id = task_id
        self.frames_dir = self.outdir / ".full_process_frames"
        self.output_path = self.outdir / f"{task_id}_full_process.mp4"
        self.cdp = None
        self.frame_count = 0
        self.started_at = None
        self.last_frame_timestamp = None
        self.error = None
        self.active = False

    def start(self):
        if not FULL_PROCESS_RECORDING:
            return
        shutil.rmtree(self.frames_dir, ignore_errors=True)
        self.frames_dir.mkdir(parents=True, exist_ok=True)
        self.output_path.unlink(missing_ok=True)
        self.cdp = self.page.context.new_cdp_session(self.page)
        frame_interval = 1.0 / FULL_PROCESS_RECORDING_FPS

        def on_frame(event):
            try:
                timestamp = float(event.get("metadata", {}).get("timestamp") or time.time())
                if (
                    self.last_frame_timestamp is None
                    or timestamp - self.last_frame_timestamp >= frame_interval * 0.9
                ):
                    frame_path = self.frames_dir / f"frame_{self.frame_count:06d}.jpg"
                    frame_path.write_bytes(base64.b64decode(event["data"]))
                    self.frame_count += 1
                    self.last_frame_timestamp = timestamp
            except Exception as exc:
                self.error = self.error or repr(exc)
            finally:
                if self.active:
                    try:
                        self.cdp.send("Page.screencastFrameAck", {"sessionId": event["sessionId"]})
                    except Exception:
                        pass

        self.cdp.on("Page.screencastFrame", on_frame)
        self.active = True
        self.cdp.send(
            "Page.startScreencast",
            {
                "format": "jpeg",
                "quality": 72,
                "maxWidth": FULL_PROCESS_RECORDING_WIDTH,
                "maxHeight": FULL_PROCESS_RECORDING_HEIGHT,
                "everyNthFrame": 1,
            },
        )
        self.started_at = time.time()

    def stop(self):
        if not self.started_at:
            return {"enabled": FULL_PROCESS_RECORDING, "status": "disabled"}
        try:
            self.page.wait_for_timeout(250)
        except Exception:
            pass
        try:
            self.cdp.send("Page.stopScreencast")
        except Exception as exc:
            self.error = self.error or repr(exc)
        self.active = False
        try:
            self.cdp.detach()
        except Exception:
            pass
        duration_s = max(0.0, time.time() - self.started_at)
        info = {
            "enabled": True,
            "fps": FULL_PROCESS_RECORDING_FPS,
            "frame_count": self.frame_count,
            "duration_s": duration_s,
            "path": str(self.output_path),
        }
        try:
            if self.frame_count < 2:
                raise RuntimeError(f"insufficient screencast frames: {self.frame_count}")
            subprocess.run(
                [
                    "ffmpeg",
                    "-loglevel",
                    "error",
                    "-y",
                    "-framerate",
                    str(FULL_PROCESS_RECORDING_FPS),
                    "-i",
                    str(self.frames_dir / "frame_%06d.jpg"),
                    "-c:v",
                    "libx264",
                    "-preset",
                    "veryfast",
                    "-crf",
                    "23",
                    "-vf",
                    (
                        f"scale={FULL_PROCESS_RECORDING_WIDTH}:{FULL_PROCESS_RECORDING_HEIGHT}:"
                        "force_original_aspect_ratio=decrease,"
                        f"pad={FULL_PROCESS_RECORDING_WIDTH}:{FULL_PROCESS_RECORDING_HEIGHT}:"
                        "(ow-iw)/2:(oh-ih)/2"
                    ),
                    "-pix_fmt",
                    "yuv420p",
                    "-movflags",
                    "+faststart",
                    str(self.output_path),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            info["status"] = "recorded"
            info["size_bytes"] = self.output_path.stat().st_size
        except Exception as exc:
            info["status"] = "recording_failed"
            info["error"] = self.error or repr(exc)
            if isinstance(exc, subprocess.CalledProcessError):
                info["ffmpeg_stderr"] = (exc.stderr or "")[-2000:]
        finally:
            shutil.rmtree(self.frames_dir, ignore_errors=True)
        return info


def click_visible_button_by_filtered_index(page, index):
    return page.evaluate(
        """index => {
          const visible = el => {
            const r = el.getBoundingClientRect();
            const s = getComputedStyle(el);
            return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none';
          };
          const buttons = Array.from(document.querySelectorAll('button')).filter(visible);
          const button = buttons[index];
          if (!button) return false;
          button.click();
          return true;
        }""",
        index,
    )


def click_download_button(page, selected_button=None):
    attempts = []

    for label in (re.compile(r"(下载视频|下载|download)", re.I),):
        for kind in ("role", "text"):
            try:
                if kind == "role":
                    locator = page.get_by_role("button", name=label)
                else:
                    locator = page.locator("button").filter(has_text=label)
                count = locator.count()
                if count:
                    locator.nth(count - 1).click(timeout=3000, force=True)
                    return {"method": kind, "count": count}
            except Exception as exc:
                attempts.append({"method": kind, "error": repr(exc)})

    state = box_state(page)
    buttons = find_download_buttons(state)
    if buttons:
        # The Genie result page also exposes other icon buttons. Prefer the bottom,
        # center-left download icon over menu/history/share controls.
        button = sorted(
            buttons,
            key=lambda item: (
                item["box"]["y"],
                -abs((item["box"]["x"] + item["box"]["w"] / 2) - page.viewport_size["width"] / 2)
                if page.viewport_size
                else 0,
            ),
            reverse=True,
        )[0]
        box = button["box"]
        page.mouse.click(box["x"] + box["w"] / 2, box["y"] + box["h"] / 2)
        return {"method": "fresh_box", "button": button}

    if selected_button:
        box = selected_button["box"]
        page.mouse.click(box["x"] + box["w"] / 2, box["y"] + box["h"] / 2)
        return {"method": "saved_box", "button": selected_button}

    return {"method": "none", "attempts": attempts}


def wait_for_session_end_or_download(page, result):
    start = time.perf_counter()
    final_state = None
    while time.perf_counter() - start < POST_ACTION_WAIT_S:
        state = box_state(page)
        final_state = state
        text = state["text"] or ""
        auth_text = auth_required_text(text)
        error_text = genie3_error_text(text)
        lower_url = state["url"].lower()
        world_loading = any(token in text for token in WORLD_LOADING_TEXTS)
        recording = (
            "REC" in text
            or "left for you" in text
            or "剩余" in text
            or bool(re.search(r"\b\d{1,3}s\b", text))
        )
        download_ready = bool(find_download_buttons(state))
        result_ready_url = any(fragment in lower_url for fragment in ("/end", "/result", "/share"))
        elapsed = time.perf_counter() - start
        result.setdefault("post_action_wait", []).append({
            "elapsed_s": elapsed,
            "url": state["url"],
            "download_ready": download_ready,
            "recording": recording,
            "world_loading": world_loading,
            "auth_required": auth_text,
            "genie3_error": error_text,
            "buttons": [b["text"] for b in state["buttons"][:20]],
            "text": text[:300],
        })
        print(
            f"[{result['task_id']}] post-action {elapsed:.1f}s "
            f"download={download_ready} recording={recording} loading={world_loading}",
            flush=True,
        )
        if auth_text:
            record_auth_required(result, "post_action_wait", state, auth_text)
            return {"status": "auth_required", "elapsed_s": elapsed, "url": state["url"], "auth_required": auth_text}
        if error_text:
            record_genie3_error(result, "post_action_wait", state, error_text)
            return {"status": "genie3_retryable_error", "elapsed_s": elapsed, "url": state["url"], "error": error_text}
        if download_ready:
            return {"status": "download_ready", "elapsed_s": elapsed, "url": state["url"]}
        if result_ready_url and not world_loading:
            return {"status": "result_url_ready", "elapsed_s": elapsed, "url": state["url"]}
        if elapsed >= 45 and not result.get("download_menu_opened"):
            menu_buttons = [
                b for b in state["buttons"]
                if (
                    not (b["text"] or "").strip()
                    or "more_vert" in (b["text"] or "")
                    or "更多" in (b["text"] or "")
                    or "More" in (b["text"] or "")
                )
            ]
            if menu_buttons:
                box = sorted(menu_buttons, key=lambda x: x["box"]["x"], reverse=True)[0]["box"]
                page.mouse.click(box["x"] + box["w"] / 2, box["y"] + box["h"] / 2)
                result["download_menu_opened"] = True
        page.wait_for_timeout(3000)
    return {
        "status": "post_action_wait_timeout",
        "elapsed_s": time.perf_counter() - start,
        "url": final_state["url"] if final_state else page.url,
    }


def click_download_and_save(page, outdir, result):
    started_at = time.time()
    page.wait_for_timeout(DOWNLOAD_SETTLE_MS)
    before = files_snapshot()
    page.screenshot(path=str(outdir / "result_page_before_download.jpg"), type="jpeg", quality=85, full_page=True)
    state = box_state(page)
    result["result_page_url"] = state["url"]
    buttons = find_download_buttons(state)
    if not buttons:
        menu_buttons = [
            b for b in state["buttons"]
            if (
                not (b["text"] or "").strip()
                or "more_vert" in (b["text"] or "")
                or "更多" in (b["text"] or "")
                or "More" in (b["text"] or "")
            )
        ]
        for menu_button in sorted(menu_buttons, key=lambda x: x["box"]["x"], reverse=True):
            box = menu_button["box"]
            page.mouse.click(box["x"] + box["w"] / 2, box["y"] + box["h"] / 2)
            page.wait_for_timeout(1000)
            state = box_state(page)
            buttons = find_download_buttons(state)
            if buttons:
                break
    if not buttons:
        result["download_status"] = "no_download_button"
        return
    selected_button = sorted(buttons, key=lambda x: x["box"]["w"] * x["box"]["h"])[-1]
    result["download_click_attempts"] = []

    for attempt in range(1, DOWNLOAD_CLICK_RETRIES + 1):
        attempt_started_at = time.time()
        try:
            with page.expect_download(timeout=DOWNLOAD_EXPECT_TIMEOUT_MS) as info:
                click_result = click_download_button(page, selected_button)
                result["download_click_attempts"].append({"attempt": attempt, "click": click_result})
            save_download_object(info.value, outdir, result)
            recover_empty_download(before, started_at, outdir, result)
            return
        except PlaywrightTimeoutError as exc:
            result["download_click_attempts"].append({"attempt": attempt, "error": str(exc)})
            found = wait_for_download_file(before, attempt_started_at, timeout_s=15)
            if found:
                save_found_download(found, outdir, result)
                return
            page.wait_for_timeout(3000)

    found = wait_for_download_file(before, started_at, timeout_s=30)
    if found:
        save_found_download(found, outdir, result)
    else:
        result["download_status"] = "no_modal_download_button"
        result["download_error"] = result["download_click_attempts"][-1].get("error", "download click did not produce a file")


def parse_wait_seconds(value, default_unit="s"):
    match = re.match(r"^\s*([0-9.]+)\s*(ms|s)?\s*$", value, re.I)
    if not match:
        return float(value)
    amount = float(match.group(1))
    unit = (match.group(2) or default_unit).lower()
    return amount / 1000 if unit == "ms" else amount


def parse_step(step):
    original_step = step.strip()
    step = original_step
    repeat = 1
    repeat_match = re.match(r"^(.*)\*(\d+)$", step)
    if repeat_match:
        step = repeat_match.group(1).strip()
        repeat = int(repeat_match.group(2))
    wait_colon_match = re.match(r"^wait\s*:\s*(.+)$", step, re.I)
    wait_call_match = re.match(r"^wait\(\s*([0-9.]+)\s*(ms|s)?\s*\)$", step, re.I)
    if wait_colon_match:
        seconds = parse_wait_seconds(wait_colon_match.group(1), default_unit="s")
        return [{"type": "wait", "seconds": seconds, "raw": original_step} for _ in range(repeat)]
    if wait_call_match:
        value = wait_call_match.group(1)
        unit = wait_call_match.group(2) or "ms"
        seconds = parse_wait_seconds(f"{value}{unit}", default_unit="ms")
        return [{"type": "wait", "seconds": seconds, "raw": original_step} for _ in range(repeat)]
    if step.lower() == "wait":
        return [{"type": "wait", "seconds": ACTION_INTERVAL_S, "raw": original_step} for _ in range(repeat)]
    hold_match = re.match(r"^hold\(([^,]+),\s*([0-9.]+)\s*(ms|s)?\)$", step, re.I)
    if hold_match:
        key_part = hold_match.group(1).strip()
        value = float(hold_match.group(2))
        unit = (hold_match.group(3) or "ms").lower()
        hold_ms = int(value * 1000 if unit == "s" else value)
        keys = [normalize_action_token(k) for k in re.split(r"[+&]", key_part) if k.strip()]
        return [
            {
                "type": "key",
                "keys": keys,
                "raw": original_step,
                "hold_ms": hold_ms,
                "hold_token": f"hold({'+'.join(display_key_token(k) for k in keys)},{hold_ms}ms)",
            }
            for _ in range(repeat)
        ]
    if step.startswith("interact("):
        return [{"type": "key", "keys": [normalize_action_token(step)], "raw": step} for _ in range(repeat)]
    if step.startswith("(") and step.endswith(")"):
        step = step[1:-1].strip()
    if "+" in step:
        keys = [normalize_action_token(k) for k in step.split("+") if k.strip()]
        return [{"type": "key", "keys": keys, "raw": step} for _ in range(repeat)]
    return [{"type": "key", "keys": [normalize_action_token(step)], "raw": step} for _ in range(repeat)]


def normalize_action_token(token):
    token = token.strip().lower()
    match = re.match(r"^interact\(([^)]*)\)$", token)
    if not match:
        return token
    intent = match.group(1).strip().lower()
    if intent in {"jump", "climb", "ascend"}:
        return "jump"
    return "e"


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


def strict_json_retry_prompt(original_prompt, bad_response, parse_error):
    return (
        "Your previous response was not valid JSON for this benchmark controller.\n"
        "Convert the decision into strict JSON only, with no markdown and no prose outside JSON.\n"
        "Schema: {\"skip_remaining_phase\":false,\"correction_steps\":[\"w\"],\"reason\":\"short reason\"}\n"
        "If the attempted/current hold is too short, include \"extend_current_hold_ms\": an integer number of milliseconds.\n"
        f"Allowed correction tokens remain: w, a, s, d, left, right, ←, →, space, e, wait:1, wait:2.\n"
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
        f"Allowed correction tokens remain: left, right, ←, →, wait:1. "
        f"Return at most {ROTATION_LOOP_MAX_ACTIONS} correction steps, or [] if no correction is useful.\n\n"
        f"Parse error: {parse_error}\n"
        f"Previous response:\n{bad_response or '<empty>'}\n\n"
        f"Original task context:\n{original_prompt}"
    )


def strict_final_orientation_json_retry_prompt(original_prompt, bad_response, parse_error):
    return (
        "Your previous response was not valid JSON for this benchmark controller.\n"
        "Convert the decision into strict JSON only, with no markdown and no prose outside JSON.\n"
        "Schema: {\"final_orientation_ok\":true,\"starting_side_ok\":true,\"anchor_visible\":true,"
        "\"needs_more_turn\":false,\"needs_position_correction\":false,\"correction_steps\":[],\"missing_anchor\":\"\","
        "\"reason\":\"short reason\"}\n"
        "Allowed correction tokens remain the sequence-consistent tokens listed in the original task context. "
        f"Return at most {FINAL_ORIENTATION_MAX_ACTIONS} correction steps, or [] if no correction is useful.\n\n"
        f"Parse error: {parse_error}\n"
        f"Previous response:\n{bad_response or '<empty>'}\n\n"
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
    for step in steps[:max_actions]:
        if not isinstance(step, str):
            continue
        step = step.strip()
        hold_match = re.fullmatch(
            r"hold\(\s*(left|right|←|→)\s*,\s*([0-9.]+)\s*ms\s*\)",
            step,
            flags=re.I,
        )
        if hold_match:
            direction = hold_match.group(1)
            if direction.lower() in {"left", "right"}:
                direction = direction.lower()
            if direction not in allowed or direction not in preferred:
                continue
            try:
                duration_ms = int(float(hold_match.group(2)))
            except (TypeError, ValueError):
                continue
            duration_ms = max(100, min(duration_ms, max_actions * HOLD_MS_PER_ACTION))
            step = f"hold({direction},{duration_ms}ms)"
        elif step not in allowed or step not in preferred:
            continue
        parsed = parse_step(step)
        for action in parsed:
            if action["type"] == "key":
                action["keys"] = [k for k in action["keys"] if k in KEY_MAP and k in {"left", "right", "←", "→"}]
                if not action["keys"]:
                    continue
            action["adaptive"] = True
            action[marker] = True
            action["step_index"] = marker
            action["step"] = step
            actions.append(action)
            if len(actions) >= max_actions:
                return actions
    return actions


def clamp_rotation_correction_steps(steps, preferred_turn=None):
    return clamp_turn_correction_steps(
        steps,
        ROTATION_LOOP_MAX_ACTIONS,
        preferred_turn,
        marker="closed_loop_rotation",
    )


def clamp_camera_correction_steps(steps, max_actions, marker="camera_correction"):
    if not isinstance(steps, list):
        return []
    allowed = {"left", "right", "up", "down", "←", "→", "↑", "↓", "wait:1"}
    actions = []
    for step in steps[:max_actions]:
        if not isinstance(step, str):
            continue
        step = step.strip()
        hold_match = re.fullmatch(
            r"hold\(\s*(left|right|up|down|←|→|↑|↓)\s*,\s*([0-9.]+)\s*ms\s*\)",
            step,
            flags=re.I,
        )
        if hold_match:
            direction = hold_match.group(1)
            if direction.lower() in {"left", "right", "up", "down"}:
                direction = direction.lower()
            duration_ms = max(100, min(int(float(hold_match.group(2))), max_actions * HOLD_MS_PER_ACTION))
            step = f"hold({direction},{duration_ms}ms)"
        elif step not in allowed:
            continue
        for action in parse_step(step):
            if action["type"] == "key":
                action["keys"] = [key for key in action["keys"] if key in KEY_MAP and key in allowed]
                if not action["keys"]:
                    continue
                if action.get("hold_ms") is None:
                    action["hold_ms"] = max(HOLD_MS_PER_ACTION, LIVE_HOLD_MIN_APPLY_MS)
                    action["hold_token"] = hold_token_for_actions([action])
            action["adaptive"] = True
            action[marker] = True
            action["step_index"] = marker
            action["step"] = step
            actions.append(action)
            if len(actions) >= max_actions:
                return actions
    return actions


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
            "w", "a", "s", "d", "q", "e", "u", "j",
            "left", "right", "←", "→", "space", "jump", "ascend", "wait:1",
        )
        if token == "wait:1" or token in present
    ]


def clamp_sequence_correction_steps(steps, max_actions, sequence_actions, marker="sequence_correction"):
    if not isinstance(steps, list):
        return []
    allowed = set(sequence_correction_tokens(sequence_actions))
    actions = []
    for step in steps[:max_actions]:
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
                if action.get("hold_ms") is None:
                    action["hold_ms"] = max(HOLD_MS_PER_ACTION, LIVE_HOLD_MIN_APPLY_MS)
                    action["hold_token"] = hold_token_for_actions([action])
            action["adaptive"] = True
            action[marker] = True
            action["step_index"] = marker
            action["step"] = step
            actions.append(action)
            if len(actions) >= max_actions:
                return actions
    return actions


def is_rotation_loop_task(task, actions):
    prompt = (task.get("prompt") or "").lower()
    sequence = " ".join(task.get("action_sequence_steps") or []).lower()
    text = f"{prompt} {sequence}"
    has_loop_language = (
        "360" in text
        or "rotate" in text
        or "rotates" in text
        or "spin" in text
        or "turn around in place" in text
        or ("in place" in text and ("survey" in text or "look around" in text))
    )
    key_actions = [action for action in actions if action.get("type") == "key"]
    if not key_actions:
        return False
    turn_only = all(
        all(key in {"left", "right", "←", "→"} for key in action.get("keys", []))
        for action in key_actions
    )
    return bool(has_loop_language and turn_only)


def is_turn_action(action):
    return action.get("type") == "key" and action.get("keys") and all(
        key in {"left", "right", "←", "→"} for key in action.get("keys", [])
    )


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
    if phase and all(is_turn_action(action) for action in phase):
        return phase
    return []


def is_final_orientation_task(task, actions):
    prompt = (task.get("prompt") or "").lower()
    has_original_direction = (
        "original direction" in prompt
        or "original orientation" in prompt
        or "original view" in prompt
        or "face the original" in prompt
        or "look in the original" in prompt
        or "look into the original" in prompt
        or "starting view" in prompt
        or "starting position" in prompt
    )
    return bool(has_original_direction and actions)


def circle_task_text(task):
    parts = [
        task.get("prompt") or "",
        task.get("action") or "",
        task.get("action_sequence") or "",
        json.dumps(task.get("questions") or [], ensure_ascii=False),
    ]
    return " ".join(parts).lower()


def is_circle_return_task(task):
    text = circle_task_text(task)
    has_circle = (
        "360" in text
        or "full circle" in text
        or "one full circle" in text
        or "turn a circle" in text
        or "rotate in a circle" in text
        or "转一圈" in text
        or "一圈" in text
    )
    has_return = (
        "return to the original" in text
        or "return to original" in text
        or "original view" in text
        or "original direction" in text
        or "original viewing direction" in text
        or "starting position" in text
        or "starting point" in text
        or "starting view" in text
        or "原本" in text
        or "原始" in text
    )
    return bool(has_circle and has_return)


def is_in_place_circle_task(task):
    text = circle_task_text(task)
    explicit_in_place = "in place" in text or "原地" in text
    orbit_path = bool(re.search(r"\b(?:around|orbit(?:ing|ed)?|circle around)\b", text))
    return bool(
        is_circle_return_task(task)
        and (
            explicit_in_place
            or (
                not orbit_path
                and (
                    "rotate the camera 360" in text
                    or "rotate the viewpoint 360" in text
                    or "rotate the view 360" in text
                    or "rotate 360" in text
                )
            )
        )
    )


def circle_return_policy(task):
    if not FORCE_CIRCLE_RETURN_PROMPT or not is_circle_return_task(task):
        return ""
    if is_in_place_circle_task(task):
        return (
            "Circle-return hard constraint: this is a 360-degree in-place rotation task. "
            "The agent/camera must rotate on the spot without walking, strafing, orbiting, or drifting. "
            "End at the same world position and face the same original view; only yaw/pan rotation is allowed."
        )
    return (
        "Circle-return hard constraint: this 360-degree task must end at the original world position and "
        "original viewing direction. If the path orbits around an object, close the loop precisely and return "
        "to the starting coordinates before the video ends; do not leave the agent displaced from the start."
    )


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
    if counts["left"]:
        return "←"
    return None


def kigress_headers():
    return {
        "Content-Type": "application/json",
        "x-api-key": KIGRESS_API_KEY,
        "x-ks-user-key": KIGRESS_USER_KEY,
        "x-ks-llm-model": KIGRESS_MODEL,
        "x-ks-biz-scene": KIGRESS_BIZ_SCENE,
    }


_KIGRESS_CLIENT = None


def kigress_client():
    global _KIGRESS_CLIENT
    if _KIGRESS_CLIENT is None:
        _KIGRESS_CLIENT = httpx.Client(trust_env=KIGRESS_TRUST_ENV)
    return _KIGRESS_CLIENT


def post_kigress(payload, timeout_s):
    return kigress_client().post(
        f"{KIGRESS_BASE_URL}/chat/completions",
        headers=kigress_headers(),
        json=payload,
        timeout=timeout_s,
    )


def require_claude_haiku_controller():
    missing = []
    if not KIGRESS_BASE_URL:
        missing.append("KIGRESS_BASE_URL")
    if not KIGRESS_API_KEY:
        missing.append("KIGRESS_API_KEY")
    if not KIGRESS_USER_KEY:
        missing.append("KIGRESS_USER_KEY")
    if "haiku" not in KIGRESS_MODEL.lower():
        missing.append("a Claude Haiku KIGRESS_MODEL")
    if not ADAPTIVE_CORRECTION:
        missing.append("GENIE3_ADAPTIVE_CORRECTION=1")
    if not LIVE_HOLD_STOP_CHECK:
        missing.append("GENIE3_LIVE_HOLD_STOP_CHECK=1")
    if ADAPTIVE_PRETHINK:
        missing.append("GENIE3_ADAPTIVE_PRETHINK=0")
    if missing:
        raise RuntimeError(
            "Genie3 requires the live Claude Haiku controller and cannot run scripted-only: "
            + ", ".join(missing)
        )
    payload = {
        "model": KIGRESS_MODEL,
        "max_completion_tokens": 8,
        "messages": [{"role": "user", "content": "Reply with exactly OK."}],
    }
    try:
        response = post_kigress(payload, 15)
    except Exception as exc:
        raise RuntimeError(f"Claude Haiku API preflight failed: {exc!r}") from exc
    if response.status_code >= 400:
        raise RuntimeError(
            f"Claude Haiku API preflight returned HTTP {response.status_code}: {response.text[:300]}"
        )
    return {"model": KIGRESS_MODEL, "http_status": response.status_code}


def request_adaptive_prethink(task, actions, upload_image_path):
    if not ADAPTIVE_CORRECTION or not ADAPTIVE_PRETHINK:
        return {"enabled": False}
    started_at = time.perf_counter()
    try:
        image_b64 = base64.b64encode(Path(upload_image_path).read_bytes()).decode("ascii")
        compact_phases = " -> ".join(task.get("action_sequence_steps") or [])
        expanded_preview = actions_to_hold_tokens(actions[:40])
        prompt = (
            "You are pre-planning a Genie 3 benchmark controller before live execution starts.\n"
            "You only see the initial/reference image, the task goal, and the dataset action sequence. "
            "Do not make final skip decisions because the live screenshot will override this pre-analysis. "
            "Instead, identify likely overshoot-prone phases, useful visual anchors, and conservative correction "
            "directions that may help a later live controller decide faster.\n\n"
            f"Environment caption: {task_environmental_caption(task)}\n"
            f"Task goal: {task['prompt']}\n"
            f"Perspective: {task.get('perspective')}\n"
            f"{control_agent_policy(task)}\n"
            f"Dataset action sequence: {task.get('action_sequence')}\n"
            f"Dataset phases: {compact_phases}\n"
            f"Expanded action preview: {expanded_preview}\n\n"
            "Return only strict JSON in this shape:\n"
            '{"global_strategy":"short",'
            '"phase_notes":[{"phase":"w*3","watch_for":"short","overshoot_risk":"short","likely_fix":"d"}],'
            '"final_anchor":"short"}'
        )
        payload = {
            "model": KIGRESS_MODEL,
            "max_completion_tokens": 360,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}},
                    ],
                }
            ],
        }
        info = {
            "enabled": True,
            "model": KIGRESS_MODEL,
            "request_url": f"{KIGRESS_BASE_URL}/chat/completions",
            "trust_env": KIGRESS_TRUST_ENV,
            "image_path": str(upload_image_path),
        }
        resp = post_kigress(payload, ADAPTIVE_PRETHINK_TIMEOUT_S)
        info["http_status"] = resp.status_code
        info["elapsed_s"] = resp.elapsed.total_seconds()
        info["wall_elapsed_s"] = time.perf_counter() - started_at
        if resp.status_code >= 400:
            info["error"] = resp.text[:1000] or f"HTTP {resp.status_code}"
            return info
        raw = extract_chat_text(resp.json())
        info["raw_response"] = raw
        try:
            info["parsed"] = extract_json_object(raw)
        except json.JSONDecodeError as parse_exc:
            info["parse_error"] = repr(parse_exc)
        return info
    except Exception as exc:
        return {
            "enabled": True,
            "error": repr(exc),
            "wall_elapsed_s": time.perf_counter() - started_at,
        }


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
    if not ROTATION_LOOP_CHECK:
        return {"enabled": False, "actions": []}
    shot_prefix = "rotation_loop_mid" if purpose == "mid_phase" else "rotation_loop_after"
    after_path = outdir / f"{shot_prefix}_{attempt_index:02d}.jpg"
    after_bytes = adaptive_screenshot(page, after_path)
    before_b64 = base64.b64encode(Path(before_path).read_bytes()).decode("ascii")
    after_b64 = base64.b64encode(after_bytes).decode("ascii")
    preferred_turn = dominant_turn_key(result.get("expanded_actions", [])) or "→"
    recent = [
        item.get("raw") or "+".join(item.get("keys", []))
        for item in result.get("executed_actions", [])[-20:]
    ]
    if purpose == "mid_phase":
        timing_instruction = (
            "This is a mid-phase check during a repeated turn sequence, before all dataset turn repeats "
            "have been consumed. Decide whether image 2 has already returned to the starting place and "
            "starting orientation shown in image 1. If it has, set closed_loop_ok, in_place_ok, and "
            "orientation_ok to true so the controller can skip the remaining turn repeats. If it has not, "
            "set closed_loop_ok to false and return correction_steps as an empty list; the controller will "
            "continue the remaining dataset turn steps.\n"
            f"Completed turn actions in this phase: {completed_in_phase}. "
            f"Remaining turn actions in this phase: {remaining_in_phase}.\n"
        )
    else:
        timing_instruction = (
            "This is the final check after the dataset action sequence. If the final frame is still in place "
            "but slightly short of the original orientation, set needs_more_turn to true and return a few "
            "extra turn tokens in the preferred direction.\n"
        )
    prompt = (
        "You are checking a closed-loop 360-degree in-place rotation in a Genie 3 benchmark run.\n"
        "Compare image 1 (before the action sequence) with image 2 (after the action sequence).\n"
        "The task should rotate the visible character/camera one full circle in place to survey the arena, "
        "then end near the starting position and facing the original view again. Natural animation, small camera "
        "jitter, and minor perspective differences are acceptable. A failure includes the character walking away, "
        "ending at a different location, stopping before completing the circle, overshooting far past the original "
        "view, or losing the distinctive target/arena layout.\n\n"
        f"Environment caption: {task_environmental_caption(task)}\n"
        f"Task goal: {task['prompt']}\n"
        f"Perspective: {task.get('perspective')}\n"
        f"{control_agent_policy(task)}\n"
        f"Dataset action sequence: {task.get('action_sequence')}\n"
        f"Recent executed actions: {recent}\n"
        f"Preferred extra turn direction, if only orientation is short: {preferred_turn}\n\n"
        f"{timing_instruction}\n"
        "For the final check only, if the final frame is still in place but slightly short of the original "
        "orientation, set needs_more_turn to true and return "
        f"1-{ROTATION_LOOP_MAX_ACTIONS} extra turn tokens in the preferred direction. "
        "If the loop is visibly incomplete or there is some position drift but continuing the same dataset turn "
        "direction can still advance the intended circle, set needs_more_turn to true and return a few extra turn "
        "tokens in that direction. Do not invent translation keys or reverse the dataset turn direction. "
        "Return only strict JSON in this shape:\n"
        '{"closed_loop_ok":true,"in_place_ok":true,"orientation_ok":true,'
        '"needs_more_turn":false,"correction_steps":[],"position_drift":"none","reason":"short reason"}'
    )
    payload = {
        "model": KIGRESS_MODEL,
        "max_completion_tokens": 320,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{before_b64}"}},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{after_b64}"}},
                ],
            }
        ],
    }
    info = {
        "enabled": True,
        "attempt_index": attempt_index,
        "purpose": purpose,
        "completed_in_phase": completed_in_phase,
        "remaining_in_phase": remaining_in_phase,
        "before_screenshot": str(before_path),
        "after_screenshot": str(after_path),
        "preferred_turn": preferred_turn,
        "model": KIGRESS_MODEL,
        "request_url": f"{KIGRESS_BASE_URL}/chat/completions",
        "trust_env": KIGRESS_TRUST_ENV,
        "actions": [],
    }
    try:
        resp = post_kigress(payload, ADAPTIVE_TIMEOUT_S)
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
            info["parse_error"] = repr(parse_exc)
            retry_payload = {
                "model": KIGRESS_MODEL,
                "max_completion_tokens": 320,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": strict_rotation_json_retry_prompt(prompt, raw, repr(parse_exc))},
                            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{before_b64}"}},
                            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{after_b64}"}},
                        ],
                    }
                ],
            }
            retry_resp = post_kigress(retry_payload, ADAPTIVE_TIMEOUT_S)
            info["retry_http_status"] = retry_resp.status_code
            info["retry_elapsed_s"] = retry_resp.elapsed.total_seconds()
            if retry_resp.status_code >= 400:
                info["retry_error"] = retry_resp.text[:1000] or f"HTTP {retry_resp.status_code}"
                return info
            retry_raw = extract_chat_text(retry_resp.json())
            info["retry_raw_response"] = retry_raw
            parsed = extract_json_object(retry_raw)
        steps = parsed.get("correction_steps") or []
        info["closed_loop_ok"] = bool(parsed.get("closed_loop_ok"))
        info["in_place_ok"] = bool(parsed.get("in_place_ok"))
        info["orientation_ok"] = bool(parsed.get("orientation_ok"))
        info["needs_more_turn"] = bool(parsed.get("needs_more_turn"))
        info["position_drift"] = parsed.get("position_drift")
        info["reason"] = parsed.get("reason")
        info["correction_steps"] = steps
        if (
            purpose != "mid_phase"
            and info["needs_more_turn"]
            and (
                not info["closed_loop_ok"]
                or not info["in_place_ok"]
                or not info["orientation_ok"]
            )
        ):
            info["actions"] = clamp_rotation_correction_steps(steps, preferred_turn)
        return info
    except Exception as exc:
        info["error"] = repr(exc)
        return info


def request_final_orientation_check(page, task, result, outdir, before_path, attempt_index=0):
    if not FINAL_ORIENTATION_CHECK:
        return {"enabled": False, "actions": []}
    after_path = outdir / f"final_orientation_after_{attempt_index:02d}.jpg"
    after_bytes = adaptive_screenshot(page, after_path)
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
        "You are checking the final orientation of a Genie 3 benchmark run.\n"
        "Compare image 1 (the starting view immediately after the world became interactive) with image 2 "
        "(the current final view after the action sequence and any corrections).\n"
        "The task ends by turning to look in the original direction. The final view should face the same "
        "general direction as image 1 and should show the same distinctive forward anchor objects from the "
        "environment caption. Natural perspective differences are acceptable if the character returned to the "
        "correct side/area and is looking back toward the original scene.\n\n"
        "Important bridge rule: if the task involves crossing or circling a bridge, the final view should still "
        "show the bridge or its distinctive bridge structure. If the bridge is not visible, anchor_visible must "
        "be false. If the character appears to be on the correct side/area but simply has not turned far enough, "
        "set needs_more_turn to true and return extra turn tokens in the preferred direction.\n\n"
        f"Environment caption: {task_environmental_caption(task)}\n"
        f"Task goal: {task['prompt']}\n"
        f"Perspective: {task.get('perspective')}\n"
        f"{control_agent_policy(task)}\n"
        f"Dataset action sequence: {task.get('action_sequence')}\n"
        f"Recent executed actions: {recent}\n"
        f"Preferred extra turn direction: {preferred_turn}\n\n"
        f"Allowed sequence-consistent correction tokens: {sequence_tokens}\n"
        "Allowed camera-only alignment tokens: left, right, up, down, ←, →, ↑, ↓, "
        "or hold(Direction,Nms). Use these only to repair final viewing direction or pitch.\n\n"
        "If the final view already shows the original-direction anchors, set final_orientation_ok=true and "
        "correction_steps=[]. If the final view is missing the key anchor because the camera has not turned far "
        f"enough, set needs_more_turn=true and return 1-{FINAL_ORIENTATION_MAX_ACTIONS} tokens using the preferred "
        "turn direction. If the character is not back at the intended side/area but a short continuation of the "
        "existing dataset trajectory can repair it, set starting_side_ok=false, needs_position_correction=true, "
        f"and return 1-{FINAL_ORIENTATION_MAX_ACTIONS} correction tokens from the allowed sequence-consistent list. "
        "Follow the original action direction: only repeat actions already present in the dataset sequence; do not "
        "invent a new route or reverse the trajectory. If the required position repair is unclear, set "
        "needs_position_correction=false and correction_steps=[].\n"
        "Return only strict JSON in this shape:\n"
        '{"final_orientation_ok":true,"starting_side_ok":true,"anchor_visible":true,'
        '"needs_more_turn":false,"needs_position_correction":false,"correction_steps":[],'
        '"missing_anchor":"","reason":"short reason"}'
    )
    payload = {
        "model": KIGRESS_MODEL,
        "max_completion_tokens": 320,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{before_b64}"}},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{after_b64}"}},
                ],
            }
        ],
    }
    info = {
        "enabled": True,
        "attempt_index": attempt_index,
        "before_screenshot": str(before_path),
        "after_screenshot": str(after_path),
        "preferred_turn": preferred_turn,
        "model": KIGRESS_MODEL,
        "request_url": f"{KIGRESS_BASE_URL}/chat/completions",
        "trust_env": KIGRESS_TRUST_ENV,
        "actions": [],
    }
    try:
        resp = post_kigress(payload, ADAPTIVE_TIMEOUT_S)
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
            info["parse_error"] = repr(parse_exc)
            retry_payload = {
                "model": KIGRESS_MODEL,
                "max_completion_tokens": 320,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": strict_final_orientation_json_retry_prompt(prompt, raw, repr(parse_exc)),
                            },
                            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{before_b64}"}},
                            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{after_b64}"}},
                        ],
                    }
                ],
            }
            retry_resp = post_kigress(retry_payload, ADAPTIVE_TIMEOUT_S)
            info["retry_http_status"] = retry_resp.status_code
            info["retry_elapsed_s"] = retry_resp.elapsed.total_seconds()
            if retry_resp.status_code >= 400:
                info["retry_error"] = retry_resp.text[:1000] or f"HTTP {retry_resp.status_code}"
                return info
            retry_raw = extract_chat_text(retry_resp.json())
            info["retry_raw_response"] = retry_raw
            parsed = extract_json_object(retry_raw)
        steps = parsed.get("correction_steps") or []
        info["final_orientation_ok"] = bool(parsed.get("final_orientation_ok"))
        info["starting_side_ok"] = bool(parsed.get("starting_side_ok"))
        info["anchor_visible"] = bool(parsed.get("anchor_visible"))
        info["needs_more_turn"] = bool(parsed.get("needs_more_turn"))
        info["needs_position_correction"] = bool(parsed.get("needs_position_correction"))
        info["missing_anchor"] = parsed.get("missing_anchor")
        info["reason"] = parsed.get("reason")
        info["correction_steps"] = steps
        if info["starting_side_ok"] and not info["final_orientation_ok"] and steps:
            if is_circle_return_task(task) and not is_in_place_circle_task(task):
                info["actions"] = clamp_sequence_correction_steps(
                    steps,
                    FINAL_ORIENTATION_MAX_ACTIONS,
                    result.get("expanded_actions", []),
                    marker="final_orientation_path",
                )
            else:
                info["actions"] = clamp_camera_correction_steps(
                    steps,
                    1,
                    marker="final_orientation",
                )
        elif info["needs_position_correction"] and not info["starting_side_ok"]:
            info["actions"] = clamp_sequence_correction_steps(
                steps,
                FINAL_ORIENTATION_MAX_ACTIONS,
                result.get("expanded_actions", []),
                marker="final_position",
            )
        return info
    except Exception as exc:
        info["error"] = repr(exc)
        return info


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
    upcoming_dataset_actions=None,
    min_required_phase_fraction=None,
    allow_hold_extension=False,
    current_hold_actions=None,
    timeout_s=None,
):
    if not ADAPTIVE_CORRECTION:
        return {"enabled": False, "actions": []}
    shot_path = outdir / f"adaptive_phase_{phase_index:02d}.jpg"
    img_bytes = adaptive_screenshot(page, shot_path)
    b64 = base64.b64encode(img_bytes).decode("ascii")
    recent_hold_actions = result.get("executed_hold_actions") or []
    if recent_hold_actions:
        recent = [item.get("token") for item in recent_hold_actions[-4:]]
    else:
        recent = [
            item.get("hold_token") or item.get("raw") or "+".join(item.get("keys", []))
            for item in result.get("executed_actions", [])[-6:]
        ]
    remaining_phase_actions = remaining_phase_actions or []
    upcoming_dataset_actions = upcoming_dataset_actions or []
    current_hold_actions = current_hold_actions or []
    current_hold_token = hold_token_for_actions(current_hold_actions) if current_hold_actions else ""
    if phase_done:
        extension_instruction = ""
        if allow_hold_extension and current_hold_token:
            extension_instruction = (
                f"The just-executed hold was {current_hold_token}. If the current screenshot shows this hold was "
                "too short to reach the needed position for the task or for the next phase, return "
                "\"extend_current_hold_ms\" with the extra duration to keep holding the SAME key(s). "
                f"Use 0 if no extension is needed. The maximum allowed extension is {ADAPTIVE_EXTEND_HOLD_MAX_MS}ms. "
                "For circle-around-object tasks, distance holds are only complete when there is clear visual evidence "
                "that the controller has passed the relevant side/far edge of the object and is ready for the next "
                "side of the loop. Do not infer success merely because the planned hold finished. If the target object "
                "is still beside/in front of the camera, the far edge/rear has not clearly been passed, or you are "
                "uncertain whether the loop progressed far enough, choose a positive extension (usually 900-1800ms) "
                "instead of 0. Use extension when the path or loop is incomplete; use correction_steps only for small "
                "lateral or facing alignment fixes after movement distance is sufficient.\n"
            )
        timing_instruction = (
            "The dataset action phase has just completed. Inspect the current screenshot and decide whether "
            "a very small correction is needed before continuing.\n"
            "Set skip_remaining_phase to false because there are no remaining actions in this phase.\n"
            f"{extension_instruction}"
        )
    else:
        minimum_execution_note = ""
        if min_required_phase_fraction is not None:
            minimum_execution_note = (
                f"The controller will execute at least {min_required_phase_fraction:.0%} of this phase before "
                "trimming its tail, even when skip_remaining_phase is true.\n"
            )
        timing_instruction = (
            "The dataset action phase is still in progress. Inspect the current screenshot and decide whether "
            "the remaining hold actions in this same phase should be skipped because continuing would overshoot, drift, "
            "or make the task worse.\n"
            f"There are {remaining_in_phase} remaining logical repeats in this phase. If the current position already "
            "satisfies this phase or further repeats are harmful, set skip_remaining_phase to true. Otherwise false.\n"
            f"Remaining hold actions in this phase if not skipped: {remaining_phase_actions}.\n"
            f"Upcoming dataset hold actions after the current point if no skip/correction is applied: {upcoming_dataset_actions}.\n"
            "Mentally project the effect of those hold actions from the current screenshot, including the duration in ms. "
            "Use that projection to decide whether the current phase should stop early. "
            "You may only skip remaining actions in the current phase; later phases are shown only for context.\n"
            f"{minimum_execution_note}"
            "Only provide correction_steps when skip_remaining_phase is true and a tiny alignment fix is needed.\n"
        )
    prethink = result.get("adaptive_prethink") or {}
    prethink_note = ""
    if prethink.get("parsed"):
        prethink_note = (
            "Prior pre-analysis from the initial image only. Treat it as guidance; the current screenshot overrides it:\n"
            f"{json.dumps(prethink['parsed'], ensure_ascii=False)[:1400]}\n\n"
        )
    elif prethink.get("raw_response"):
        prethink_note = (
            "Prior pre-analysis from the initial image only. Treat it as guidance; the current screenshot overrides it:\n"
            f"{prethink['raw_response'][:1400]}\n\n"
        )
    prompt = (
        "You are a conservative action controller for a Genie 3 benchmark run.\n"
        f"{timing_instruction}\n"
        f"{prethink_note}"
        f"Environment caption: {task_environmental_caption(task)}\n"
        f"Task goal: {task['prompt']}\n"
        f"Perspective: {task.get('perspective')}\n"
        f"{control_agent_policy(task)}\n"
        f"Current dataset phase: {phase_step}\n"
        f"Recent executed actions: {recent}\n\n"
        "Allowed correction tokens: w, a, s, d, left, right, ←, →, space, e, wait:1, wait:2.\n"
        f"Return at most {ADAPTIVE_MAX_ACTIONS} correction steps. Use [] if no correction is needed. "
        f"If allowed and the just-executed hold is too short, return extend_current_hold_ms from 0 to {ADAPTIVE_EXTEND_HOLD_MAX_MS}. "
        "When both extension and correction might help, prefer extension for insufficient travel distance and reserve "
        "correction_steps for small alignment/facing fixes. "
        "Do not invent a new plan, do not repeat the whole dataset sequence, and do not exceed small alignment fixes. "
        "Skipping remaining phase actions is allowed only for the current phase and may skip any number of remaining repeats.\n"
        "Return only strict JSON in this shape:\n"
        '{"skip_remaining_phase":false,"extend_current_hold_ms":0,"correction_steps":["w"],"reason":"short reason"}'
    )
    payload = {
        "model": KIGRESS_MODEL,
        "max_completion_tokens": ADAPTIVE_MAX_COMPLETION_TOKENS,
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
    info = {
        "enabled": True,
        "phase_index": phase_index,
        "phase_step": phase_step,
        "phase_done": phase_done,
        "remaining_in_phase": remaining_in_phase,
        "min_required_phase_fraction": min_required_phase_fraction,
        "remaining_phase_actions": remaining_phase_actions,
        "upcoming_dataset_actions": upcoming_dataset_actions,
        "allow_hold_extension": allow_hold_extension,
        "current_hold_action": current_hold_token,
        "skip_remaining_phase": False,
        "extend_current_hold_ms": 0,
        "screenshot": str(shot_path),
        "model": KIGRESS_MODEL,
        "request_url": f"{KIGRESS_BASE_URL}/chat/completions",
        "trust_env": KIGRESS_TRUST_ENV,
        "actions": [],
    }
    request_timeout_s = ADAPTIVE_TIMEOUT_S if timeout_s is None else timeout_s
    try:
        resp = post_kigress(payload, request_timeout_s)
        info["http_status"] = resp.status_code
        info["elapsed_s"] = resp.elapsed.total_seconds()
        if resp.status_code >= 400:
            info["error"] = resp.text[:1000] or f"HTTP {resp.status_code}"
            return info
        data = resp.json()
        raw = extract_chat_text(data)
        info["raw_response"] = raw
        try:
            parsed = extract_json_object(raw)
        except json.JSONDecodeError as parse_exc:
            info["parse_error"] = repr(parse_exc)
            retry_payload = {
                "model": KIGRESS_MODEL,
                "max_completion_tokens": ADAPTIVE_MAX_COMPLETION_TOKENS,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": strict_json_retry_prompt(prompt, raw, repr(parse_exc)),
                            },
                            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                        ],
                    }
                ],
            }
            retry_resp = post_kigress(retry_payload, request_timeout_s)
            info["retry_http_status"] = retry_resp.status_code
            info["retry_elapsed_s"] = retry_resp.elapsed.total_seconds()
            if retry_resp.status_code >= 400:
                info["retry_error"] = retry_resp.text[:1000] or f"HTTP {retry_resp.status_code}"
                return info
            retry_data = retry_resp.json()
            retry_raw = extract_chat_text(retry_data)
            info["retry_raw_response"] = retry_raw
            parsed = extract_json_object(retry_raw)
        steps = parsed.get("correction_steps") or []
        info["skip_remaining_phase"] = bool(parsed.get("skip_remaining_phase")) and not phase_done
        try:
            extend_ms = int(float(parsed.get("extend_current_hold_ms") or 0))
        except (TypeError, ValueError):
            extend_ms = 0
        if not allow_hold_extension:
            extend_ms = 0
        info["extend_current_hold_ms"] = max(0, min(extend_ms, ADAPTIVE_EXTEND_HOLD_MAX_MS))
        info["reason"] = parsed.get("reason")
        info["correction_steps"] = steps
        info["actions"] = clamp_correction_steps(steps)
        return info
    except Exception as exc:
        info["error"] = repr(exc)
        return info


def clamp_live_adaptive_actions(items):
    if not isinstance(items, list):
        return []
    allowed = {"w", "a", "s", "d", "left", "right", "up", "down", "space", "e"}
    actions = []
    for item in items[:LIVE_HOLD_MAX_ADAPTIVE_ACTIONS]:
        if isinstance(item, str):
            match = re.fullmatch(r"([a-z]+)(?:\*(\d+))?", item.strip().lower())
            if not match or match.group(1) not in allowed:
                continue
            key = match.group(1)
            repeat = max(1, min(int(match.group(2) or 1), LIVE_HOLD_ADAPTIVE_MAX_REPEAT))
            hold_ms = HOLD_MS_PER_ACTION * repeat
            raw = f"{key}*{repeat}" if repeat > 1 else key
        elif isinstance(item, list) and item:
            key = str(item[0]).strip().lower()
            if key not in allowed:
                continue
            try:
                hold_ms = int(float(item[1])) if len(item) > 1 else HOLD_MS_PER_ACTION
            except (TypeError, ValueError):
                hold_ms = HOLD_MS_PER_ACTION
            hold_ms = max(LIVE_HOLD_ADAPTIVE_MIN_MS, min(hold_ms, LIVE_HOLD_ADAPTIVE_MAX_MS))
            repeat = max(1, int(round(hold_ms / HOLD_MS_PER_ACTION)))
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


def request_live_hold_stop_check(task, result, context, image_bytes):
    if not LIVE_HOLD_STOP_CHECK or not ADAPTIVE_CORRECTION:
        return {"enabled": False, "stop_current_hold": False}
    started_at = time.perf_counter()
    b64 = base64.b64encode(image_bytes).decode("ascii")
    recent = [
        item.get("token") or item.get("hold_token") or item.get("raw") or "+".join(item.get("keys", []))
        for item in (result.get("executed_hold_actions") or [])[-4:]
    ]
    prompt = (
        "Control a held key in Genie 3 from the screenshot. Be conservative. "
        "Choose k=keep, s=stop, or e=extend this same key. ms is extra hold time for e. "
        "skip=1 skips remaining repeated actions in this phase. next contains at most two correction tokens, "
        "such as [\"a\",\"w*2\"], executed after release. Allowed keys: "
        "w,a,s,d,left,right,up,down,space,e.\n"
        f"Environment caption: {task_environmental_caption(task)}\n"
        f"Task goal: {task['prompt']}\n"
        f"Perspective: {task.get('perspective')}\n"
        f"{control_agent_policy(task)}\n"
        f"Current dataset phase: {context.get('phase_step')}\n"
        f"Current hold command: {context.get('hold_token')}\n"
        f"Elapsed in this hold: {context.get('elapsed_hold_ms')}ms of planned {context.get('planned_hold_ms')}ms.\n"
        f"Remaining same-phase dataset actions after this hold group: {context.get('remaining_phase_actions')}\n"
        f"Upcoming dataset actions after this phase: {context.get('upcoming_dataset_actions')}\n"
        f"Recent executed holds: {recent}\n\n"
        "Return JSON only: {\"a\":\"k\",\"ms\":0,\"skip\":0,\"next\":[]}"
    )
    payload = {
        "model": KIGRESS_MODEL,
        "max_completion_tokens": LIVE_HOLD_MAX_COMPLETION_TOKENS,
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
    info = {
        "enabled": True,
        "phase_index": context.get("phase_index"),
        "phase_step": context.get("phase_step"),
        "hold_token": context.get("hold_token"),
        "elapsed_hold_ms": context.get("elapsed_hold_ms"),
        "planned_hold_ms": context.get("planned_hold_ms"),
        "model": KIGRESS_MODEL,
        "request_url": f"{KIGRESS_BASE_URL}/chat/completions",
        "trust_env": KIGRESS_TRUST_ENV,
        "stop_current_hold": False,
        "skip_remaining_phase": False,
    }
    try:
        resp = post_kigress(payload, LIVE_HOLD_TIMEOUT_S)
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
        info["reason"] = parsed.get("reason")
        info["stop_current_hold"] = decision == "s"
        info["extend_current_hold_ms"] = extend_ms
        info["skip_remaining_phase"] = bool(parsed.get("skip") or parsed.get("skip_remaining_phase")) and decision == "s"
        info["actions"] = clamp_live_adaptive_actions(parsed.get("next") or [])
        return info
    except Exception as exc:
        info["error"] = repr(exc)
        info["wall_elapsed_s"] = time.perf_counter() - started_at
        return info


def find_world_element(page):
    for selector in ("canvas", "video"):
        elem = page.query_selector(selector)
        if elem and elem.is_visible():
            box = elem.bounding_box()
            if box and box["width"] > 100 and box["height"] > 100:
                return elem, box
    return None, None


def adaptive_screenshot(page, path=None, timeout_ms=1500, quality=None):
    element, _ = find_world_element(page)
    try:
        if element:
            raw = element.screenshot(type="jpeg", quality=60, timeout=timeout_ms)
        else:
            raw = page.screenshot(type="jpeg", quality=60, full_page=False, timeout=timeout_ms)
    except Exception:
        raw = page.screenshot(type="jpeg", quality=60, full_page=False, timeout=timeout_ms)

    with Image.open(BytesIO(raw)) as image:
        image = image.convert("RGB")
        image.thumbnail(
            (ADAPTIVE_SCREENSHOT_MAX_WIDTH, ADAPTIVE_SCREENSHOT_MAX_HEIGHT),
            Image.Resampling.LANCZOS,
        )
        output = BytesIO()
        image.save(
            output,
            format="JPEG",
            quality=quality if quality is not None else ADAPTIVE_SCREENSHOT_QUALITY,
            optimize=True,
        )
        compressed = output.getvalue()
    if path:
        Path(path).write_bytes(compressed)
    return compressed


def focus_world(page):
    _, box = find_world_element(page)
    if box:
        page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
        return {"focused": True, "box": box}
    return {"focused": False}


def dismiss_consent_dialog(page):
    labels = ["我同意", "I agree", "同意", "Agree", "知道了", "Got it", "OK"]
    clicked = []
    for label in labels:
        # Exact matching is important here: Playwright's `text=OK` also matches
        # the "book_5" icon in the History button and navigates away from the
        # creation form after an upload.
        for locator in (
            page.get_by_role("button", name=label, exact=True).last,
            page.get_by_text(label, exact=True).last,
        ):
            try:
                if not locator.count():
                    continue
                box = locator.bounding_box(timeout=1000)
                if box:
                    page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
                else:
                    locator.click(timeout=1000)
                page.wait_for_timeout(700)
                clicked.append(label)
                break
            except Exception:
                continue
    if clicked:
        page.wait_for_timeout(2000)
    return {"clicked": bool(clicked), "labels": clicked}


def fill_text_editor(page, locator, text):
    def current_text():
        try:
            return locator.input_value(timeout=1000)
        except Exception:
            try:
                return locator.inner_text(timeout=1000)
            except Exception:
                return ""

    try:
        locator.fill(text, timeout=10000)
    except Exception:
        locator.click(timeout=10000)
        page.keyboard.press("Meta+A")
        page.keyboard.insert_text(text)
        return
    page.wait_for_timeout(300)
    if text and text[:40] not in current_text():
        locator.click(timeout=10000)
        page.keyboard.press("Meta+A")
        page.keyboard.insert_text(text)
        page.wait_for_timeout(300)


def fill_create_fields(page, fields):
    dismiss_consent_dialog(page)
    editors = page.locator(
        "textarea:not(.g-recaptcha-response):not([name='g-recaptcha-response']),"
        "[contenteditable='true'],"
        "input[type='text']:not([name='g-recaptcha-response']),"
        "[role='textbox']"
    )
    last_error = None
    try:
        editors.first.wait_for(state="visible", timeout=5000)
        count = editors.count()
        if count >= 2:
            environment_editor = editors.nth(0)
            character_editor = editors.nth(1)
            environment_editor.scroll_into_view_if_needed(timeout=3000)
            fill_text_editor(page, environment_editor, fields["environment"])
            if fields.get("character"):
                character_editor.scroll_into_view_if_needed(timeout=3000)
                fill_text_editor(page, character_editor, fields["character"])
            else:
                try:
                    character_editor.fill("", timeout=3000)
                except Exception:
                    pass
            return {
                "method": "two_field_form",
                "environment": fields["environment"],
                "character": fields.get("character", ""),
            }
        if count == 1:
            combined = fields["environment"]
            if fields.get("character"):
                combined = f"{combined}\n\n{fields['character']}"
            editor = editors.first
            editor.scroll_into_view_if_needed(timeout=3000)
            fill_text_editor(page, editor, combined)
            return {"method": "single_field_fallback", "combined": combined}
    except Exception as exc:
        last_error = exc

    state = box_state(page)
    editable = [b for b in state["buttons"] if b["text"] in {"环境", "人物"}]
    if editable:
        b = editable[0]["box"]
        page.mouse.click(b["x"] + b["w"] / 2, b["y"] + b["h"] / 2)
        page.keyboard.type(fields["environment"], delay=0)
        return {"method": "button_label_fallback", "label": editable[0]["text"], "environment": fields["environment"]}

    raise last_error or RuntimeError("No prompt input found")


def wait_create_form_controls(page, timeout_ms=30000):
    deadline = time.perf_counter() + timeout_ms / 1000.0
    while time.perf_counter() < deadline:
        try:
            ready = page.evaluate(
                """() => {
                  const visible = el => {
                    const r = el.getBoundingClientRect();
                    const s = getComputedStyle(el);
                    return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none';
                  };
                  const editors = Array.from(document.querySelectorAll(
                    "textarea:not(.g-recaptcha-response):not([name='g-recaptcha-response'])," +
                    "[contenteditable='true'],input[type='text']:not([name='g-recaptcha-response']),[role='textbox']"
                  )).filter(visible);
                  const upload = !!document.querySelector('input[type=file]') ||
                    Array.from(document.querySelectorAll('button,[role="button"]')).filter(visible).some(el => {
                      const text = (el.innerText || el.getAttribute('aria-label') || '').toLowerCase();
                      return text.includes('image') || text.includes('upload') || text.includes('photo')
                        || text.includes('图片') || text.includes('上传') || text.includes('媒体');
                    });
                  return location.href.includes('/creation') && editors.length >= 2 && upload;
                }"""
            )
            if ready:
                return True
        except Exception:
            pass
        try:
            if "/history" in page.url:
                locator = page.locator("button").filter(has_text="创建新项目").first
                locator.scroll_into_view_if_needed(timeout=2000)
                locator.evaluate("el => el.click()", timeout=4000)
                try:
                    page.wait_for_url("**/creation**", timeout=10000)
                except PlaywrightTimeoutError:
                    pass
            elif "/creation" not in page.url:
                try:
                    page.goto(GENIE3_CREATE_URL, wait_until="commit", timeout=15000)
                except Exception:
                    pass
        except Exception:
            pass
        page.wait_for_timeout(3000)
    return False


def task_environmental_caption(task):
    return (
        task.get("image_caption")
        or task.get("environmental_caption")
        or task.get("scene_context")
        or task.get("prompt")
        or ""
    )


def is_wait_and_observe_task(task):
    prompt = re.sub(r"\s+", " ", task.get("prompt") or "").strip().lower()
    return bool(re.search(r"\bwait\s*(?:and|&)\s*observe\b", prompt))


def control_agent_policy(task):
    lines = [
        "Controller policy: follow the dataset action sequence as the primary source of truth. "
        "Use the task goal and current screenshot to judge whether the current phase needs more hold duration, "
        "a small alignment correction, or a safe trim of the current phase tail."
    ]
    policy = circle_return_policy(task)
    if policy:
        lines.append(policy)
    if infer_group(task) == "IF":
        lines.append(
            "IF task obstacle policy: if the task explicitly says to walk, drive, jump, climb, push, enter, "
            "or move into/through a target area, do not stop merely because an obstacle, edge, water surface, "
            "doorway, fence, wall, furniture, grass, bushes, or other object is directly ahead. Treat those "
            "elements as part of the requested interaction. Continue according to the prompt and action sequence; "
            "only choose to go around when the prompt says to go around, or when going around is required to reach "
            "the same requested target without clipping through solid geometry."
        )
    if AGENT_GUIDANCE:
        lines.append(f"User-provided agent guidance: {AGENT_GUIDANCE}")
    return "\n".join(lines)


def central_character_from_prompt(prompt):
    text = re.sub(r"\s+", " ", (prompt or "").strip())
    if not text:
        return "the central character"
    leading_subject = re.match(
        r"^((?:the|a|an)\s+"
        r"(?:(?:elderly|little|young|old|small|large|main|central|male|female|"
        r"blonde|brown|black|white|grey|gray|red|blue|green|robot|scruffy|fluffy|"
        r"armored|mounted|standing|sitting)\s+)*"
        r"(?:man|woman|boy|girl|child|person|character|waiter|warrior|archer|"
        r"fisherman|bellhop|dog|cat|horse|deer|rider|driver|cyclist|skier|"
        r"surfer|swimmer|car|tram|boat|wagon))\b",
        text,
        flags=re.I,
    )
    if leading_subject:
        return leading_subject.group(1).strip()
    verb_pattern = (
        r"walks?|runs?|moves?|drives?|rides?|turns?|climbs?|jumps?|rows?|pushes?|"
        r"gallops?|rush(?:es)?|knocks?|charges?|enters?|goes?|crosses?|follows?|"
        r"keeps?|continues?|tilts?|pans?|rotates?|circles?|watches?|observes?"
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


def task_character(task):
    return CHARACTER_OVERRIDES.get(task.get("task_id")) or central_character_from_prompt(task.get("prompt"))


def build_genie3_fields(task):
    perspective = normalize_perspective(task.get("perspective"))
    environment = task_environmental_caption(task)[:900]
    if perspective == "first-person":
        character = ""
    elif perspective == "third-person":
        character = task_character(task)
    else:
        character = (
            "Controllable game-like explorer. "
            f"Goal: {task['prompt']} "
            "Controls: responsive movement, camera turning, and interaction when relevant."
        )
    return {"environment": environment, "character": character[:900]}


def build_genie3_prompt(task):
    perspective = normalize_perspective(task.get("perspective"))
    environmental_caption = task_environmental_caption(task)
    if perspective == "first-person":
        camera = "Use a first-person camera so the player sees through the controllable character."
        character = ""
    elif perspective == "third-person":
        camera = "Use a third-person camera with the controllable character centered in frame."
        character = f"Character: {task_character(task)}."
    else:
        camera = "Use a controllable game-like camera suitable for real-time exploration."
        character = "Character: a controllable explorer with responsive movement."

    lines = [
        "Create an interactive Genie 3 world from the uploaded reference image.\n"
        f"Environment: {environmental_caption}\n"
        f"Task: {task['prompt']}\n"
    ]
    if character:
        lines.append(f"{character}\n")
    lines.append(
        f"Movement: support WASD movement, arrow-key camera turns, and action/interact controls when relevant. Execute the task action above. {camera}\n"
    )
    policy = circle_return_policy(task)
    if policy:
        lines.append(f"{policy}\n")
    lines.append("Keep the language direct and action-oriented. Make the world photorealistic, stable, and navigable in real time.")
    return "".join(lines)


def live_hold_check_enabled(action, hold_ms, context):
    return (
        LIVE_HOLD_STOP_CHECK
        and ADAPTIVE_CORRECTION
        and context
        and action.get("type") == "key"
        and not action.get("adaptive")
        and hold_ms >= LIVE_HOLD_MIN_MS
        and LIVE_HOLD_CHECK_INTERVAL_MS > 0
        and KIGRESS_BASE_URL
        and KIGRESS_API_KEY
    )


def dispatch_js_key_event(page, event_type, key):
    key_value, code, key_code = CDP_KEY_DETAILS.get(key, (key, key, 0))
    try:
        page.evaluate(
            """({eventType, keyValue, code, keyCode}) => {
              const event = new KeyboardEvent(eventType, {
                key: keyValue, code, keyCode, which: keyCode,
                bubbles: true, cancelable: true, composed: true,
              });
              for (const target of [window, document, document.body, document.activeElement]) {
                try { target && target.dispatchEvent(event); } catch (_) {}
              }
            }""",
            {"eventType": event_type, "keyValue": key_value, "code": code, "keyCode": key_code},
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
        cdp.detach()
        return True
    except Exception:
        return False


def press_keys_down(page, keys):
    methods = []
    for key in keys:
        try:
            page.keyboard.down(key)
            methods.append({"key": key, "method": "playwright_down", "ok": True})
        except Exception as exc:
            methods.append({"key": key, "method": "playwright_down", "ok": False, "error": str(exc)})
        methods.append({"key": key, "method": "cdp_raw_key_down", "ok": dispatch_cdp_key_event(page, "rawKeyDown", key)})
        methods.append({"key": key, "method": "js_keydown", "ok": dispatch_js_key_event(page, "keydown", key)})
    return methods


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
    context["planned_hold_ms"] = original_hold_ms
    stop_info = None
    decision_info = None
    deferred_stop_info = None
    adaptive_actions = []
    extension_applied_ms = 0
    checks = []
    pending = None
    executor = ThreadPoolExecutor(max_workers=1)
    hold_started = time.perf_counter()
    hold_deadline = hold_started + effective_hold_ms / 1000.0
    down_info = press_keys_down(page, mapped)
    try:
        if LIVE_HOLD_MIN_MS <= 0 and LIVE_HOLD_MIN_REMAINING_MS <= effective_hold_ms:
            check_context = dict(context)
            check_context["elapsed_hold_ms"] = 0
            try:
                shot = adaptive_screenshot(
                    page,
                    timeout_ms=LIVE_HOLD_SCREENSHOT_TIMEOUT_MS,
                    quality=LIVE_HOLD_SCREENSHOT_QUALITY,
                )
                pending = executor.submit(
                    request_live_hold_stop_check,
                    context["task"],
                    context["result"],
                    check_context,
                    shot,
                )
            except Exception as exc:
                checks.append({
                    "enabled": True,
                    "elapsed_hold_ms": 0,
                    "error": repr(exc),
                })
                pending = None
        while True:
            now = time.perf_counter()
            elapsed_ms = int((now - hold_started) * 1000)
            remaining_ms = max(0, int((hold_deadline - now) * 1000))
            if remaining_ms <= 0:
                break

            wait_ms = min(LIVE_HOLD_CHECK_INTERVAL_MS, remaining_ms)
            page.wait_for_timeout(wait_ms)
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
                decision_info = check
                adaptive_actions = (adaptive_actions + (check.get("actions") or []))[:LIVE_HOLD_MAX_ADAPTIVE_ACTIONS]
                extend_ms = min(
                    int(check.get("extend_current_hold_ms") or 0),
                    max(0, ADAPTIVE_EXTEND_HOLD_MAX_MS - extension_applied_ms),
                )
                if extend_ms > 0:
                    effective_hold_ms += extend_ms
                    hold_deadline += extend_ms / 1000.0
                    extension_applied_ms += extend_ms
                    check["applied_extend_ms"] = extend_ms
                if check.get("stop_current_hold"):
                    if elapsed_ms >= LIVE_HOLD_MIN_APPLY_MS:
                        stop_info = check
                        break
                    deferred_stop_info = dict(check)
                    deferred_stop_info["deferred_until_min_apply_ms"] = LIVE_HOLD_MIN_APPLY_MS
                    deferred_stop_info["deferred_at_elapsed_ms"] = elapsed_ms

            if deferred_stop_info and elapsed_ms >= LIVE_HOLD_MIN_APPLY_MS:
                stop_info = dict(deferred_stop_info)
                stop_info["applied_at_elapsed_ms"] = elapsed_ms
                break

            if (
                pending is None
                and deferred_stop_info is None
                and len(checks) < LIVE_HOLD_MAX_CHECKS
                and elapsed_ms >= LIVE_HOLD_MIN_MS
                and remaining_ms >= LIVE_HOLD_MIN_REMAINING_MS
            ):
                check_context = dict(context)
                check_context["elapsed_hold_ms"] = elapsed_ms
                try:
                    shot = adaptive_screenshot(
                        page,
                        timeout_ms=LIVE_HOLD_SCREENSHOT_TIMEOUT_MS,
                        quality=LIVE_HOLD_SCREENSHOT_QUALITY,
                    )
                    pending = executor.submit(
                        request_live_hold_stop_check,
                        context["task"],
                        context["result"],
                        check_context,
                        shot,
                    )
                except Exception as exc:
                    checks.append({
                        "enabled": True,
                        "elapsed_hold_ms": elapsed_ms,
                        "error": repr(exc),
                    })
                    pending = None

        if pending and pending.done() and not stop_info:
            try:
                check = pending.result(timeout=0)
            except Exception as exc:
                check = {"enabled": True, "error": repr(exc)}
            checks.append(check)
            if check.get("stop_current_hold"):
                actual_elapsed_ms = int((time.perf_counter() - hold_started) * 1000)
                if actual_elapsed_ms >= LIVE_HOLD_MIN_APPLY_MS:
                    stop_info = check
    finally:
        up_info = press_keys_up(page, mapped)
        hold_released_at = time.perf_counter()

    if pending:
        if pending.done():
            try:
                check = pending.result(timeout=0)
            except Exception as exc:
                check = {"enabled": True, "error": repr(exc)}
            check["arrived_after_hold"] = True
            checks.append(check)
        else:
            checks.append({
                "enabled": True,
                "abandoned_after_hold": True,
                "cancelled": pending.cancel(),
                "reason": "hold absolute deadline reached; do not delay the next action",
            })
        pending = None
    try:
        executor.shutdown(wait=False, cancel_futures=True)
    except TypeError:
        executor.shutdown(wait=False)

    actual_hold_ms = int((hold_released_at - hold_started) * 1000)
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
        "adaptive_actions": adaptive_actions,
        "stop_current_hold": bool(stop_info),
        "skip_remaining_phase": bool(stop_info and stop_info.get("skip_remaining_phase")),
    }


def key_action_signature(action):
    if action.get("type") != "key" or action.get("adaptive"):
        return None
    keys = tuple(action.get("keys") or [])
    if not keys:
        return None
    return keys, action.get("raw")


def fast_repeat_batch_size(actions, index, rotation_loop_task=False):
    if not FAST_REPEAT_PRESS or rotation_loop_task:
        return 1
    action = actions[index]
    signature = key_action_signature(action)
    if not signature:
        return 1
    phase_end = index + 1
    while (
        phase_end < len(actions)
        and actions[phase_end].get("step_index") == action.get("step_index")
        and key_action_signature(actions[phase_end]) == signature
    ):
        phase_end += 1
    total = phase_end - index
    if total < FAST_REPEAT_MIN_COUNT:
        return 1
    if ADAPTIVE_PHASE_PROGRESS_CHECK:
        return min(total, ADAPTIVE_PHASE_CHECK_EVERY)
    target = max(1, math.ceil(total * FAST_REPEAT_CHECK_FRACTION))
    return min(total, max(FAST_REPEAT_MIN_COUNT, target))


def fast_repeat_hold_ms(batch_size):
    if batch_size <= 1:
        return HOLD_MS_PER_ACTION if HOLD_SEQUENCE_MODE else KEY_HOLD_MS
    if HOLD_SEQUENCE_MODE:
        return int(batch_size * HOLD_MS_PER_ACTION)
    return KEY_HOLD_MS + int((batch_size - 1) * ACTION_INTERVAL_S * 1000)


def action_hold_ms(action):
    if action.get("type") == "wait":
        return int(float(action.get("seconds", 0)) * 1000)
    if action.get("hold_ms") is not None:
        return int(action["hold_ms"])
    return fast_repeat_hold_ms(1)


def hold_ms_for_actions(actions):
    if not actions:
        return 0
    explicit_or_wait = any(action.get("hold_ms") is not None or action.get("type") == "wait" for action in actions)
    if explicit_or_wait:
        return sum(action_hold_ms(action) for action in actions)
    return fast_repeat_hold_ms(len(actions))


def action_token(action):
    if action.get("type") == "wait":
        return f"wait:{action.get('seconds', 1)}"
    return action.get("raw") or "+".join(action.get("keys", [])) or action.get("type", "?")


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


def hold_token_for_actions(actions):
    if not actions:
        return ""
    first = actions[0]
    if first.get("type") == "wait":
        total_ms = hold_ms_for_actions(actions)
        return f"wait({total_ms}ms)"
    keys = "+".join(display_key_token(key) for key in first.get("keys", []))
    hold_ms = hold_ms_for_actions(actions)
    return f"hold({keys},{hold_ms}ms)"


def actions_to_hold_tokens(actions):
    tokens = []
    i = 0
    while i < len(actions):
        action = actions[i]
        if action.get("type") == "wait":
            j = i + 1
            while j < len(actions) and actions[j].get("type") == "wait":
                j += 1
            tokens.append(hold_token_for_actions(actions[i:j]))
            i = j
            continue
        signature = key_action_signature(action)
        if not signature:
            tokens.append(action_token(action))
            i += 1
            continue
        j = i + 1
        while j < len(actions) and key_action_signature(actions[j]) == signature:
            j += 1
        tokens.append(hold_token_for_actions(actions[i:j]))
        i = j
    return tokens


def hold_sequence_text(actions):
    return "; ".join(actions_to_hold_tokens(actions))


def remaining_hold_ms(actions, start_index):
    return sum(hold_ms_for_actions([action]) for action in actions[start_index:])


def make_hold_extension_action(base_action, extend_ms):
    action = dict(base_action)
    action["raw"] = f"extend({'+'.join(display_key_token(k) for k in action.get('keys', []))},{extend_ms}ms)"
    action["hold_ms"] = int(extend_ms)
    action["hold_token"] = hold_token_for_actions([action])
    action["adaptive"] = True
    action["step_index"] = "adaptive_extend"
    action["step"] = action["raw"]
    return action


def phase_bounds(actions, index):
    start = index
    while start > 0 and actions[start - 1].get("step_index") == actions[index].get("step_index"):
        start -= 1
    end = index + 1
    while end < len(actions) and actions[end].get("step_index") == actions[index].get("step_index"):
        end += 1
    return start, end


def build_live_hold_context(task, result, actions, hold_start, hold_end):
    if not actions or hold_start >= len(actions):
        return None
    phase_start, phase_end = phase_bounds(actions, hold_start)
    return {
        "task": task,
        "result": result,
        "phase_index": actions[hold_start].get("step_index"),
        "phase_step": actions[hold_start].get("step"),
        "hold_token": hold_token_for_actions(actions[hold_start:hold_end]),
        "remaining_phase_actions": actions_to_hold_tokens(actions[hold_end:phase_end]),
        "upcoming_dataset_actions": actions_to_hold_tokens(
            actions[phase_end:min(len(actions), phase_end + ADAPTIVE_CONTEXT_ACTIONS)]
        ),
    }


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
        "skipped_hold_sequence": hold_sequence_text(skipped_actions),
        "skipped_actions": skipped_actions,
        "reason": reason_info.get("reason") if reason_info else None,
        "live_hold_stop": reason_info,
    }
    if REQUIRE_FULL_ACTION_SEQUENCE:
        result.setdefault("live_hold_skip_recommendations", []).append(skip_record)
        return current_index
    result.setdefault("live_hold_skipped_actions", []).append(skip_record)
    return phase_end - 1


def can_hold_phase(actions, start, end):
    if start >= end:
        return False
    first = actions[start]
    if first.get("type") == "wait":
        return all(action.get("type") == "wait" for action in actions[start:end])
    signature = key_action_signature(first)
    if not signature:
        return False
    return all(key_action_signature(action) == signature for action in actions[start:end])


def submit_create_attempt(page, task, prompt, upload_path, outdir, result, attempt):
    suffix = "" if attempt == 1 else f"_attempt_{attempt}"
    result["create_attempt"] = attempt
    already_ready = False
    if "/creation" in page.url:
        try:
            already_ready = page.locator("textarea").count() >= 2 and page.locator("input[type=file]").count() > 0
        except Exception:
            already_ready = False
    if not already_ready:
        page.goto(GENIE3_CREATE_URL, wait_until="commit", timeout=30000)
        page.wait_for_timeout(5000)
    result[f"initial_consent{suffix}"] = dismiss_consent_dialog(page)
    entry_state = box_state(page)
    auth_text = auth_required_text(entry_state.get("text"))
    if auth_text:
        result[f"auth_required_state{suffix}"] = entry_state
        record_auth_required(result, "create_entry", entry_state, auth_text)
        return False
    result[f"create_entry{suffix}"] = open_create_panel(page, result, suffix)
    if result[f"create_entry{suffix}"]["status"] not in {"already_open", "clicked"}:
        state = box_state(page)
        auth_text = auth_required_text(state.get("text"))
        if auth_text:
            result[f"auth_required_state{suffix}"] = state
            record_auth_required(result, "create_entry_not_ready", state, auth_text)
            return False
        page.screenshot(path=str(outdir / f"create_entry_not_ready{suffix}.jpg"), type="jpeg", quality=85, full_page=True)
        result["status"] = "create_entry_not_ready"
        return False
    result[f"consent{suffix}"] = dismiss_consent_dialog(page)
    page.wait_for_timeout(10000)
    if not wait_create_form_controls(page, timeout_ms=120000):
        page.screenshot(path=str(outdir / f"create_controls_not_ready{suffix}.jpg"), type="jpeg", quality=85, full_page=True)
        result["status"] = "create_input_not_ready"
        return False
    result[f"perspective_select{suffix}"] = set_perspective(page, task.get("perspective"))
    page.wait_for_timeout(1000)
    result[f"upload{suffix}"] = upload_start_image(page, upload_path)
    if result[f"upload{suffix}"].get("skipped"):
        result["status"] = "required_start_image_not_uploaded"
        return False
    page.wait_for_timeout(2500)
    result[f"post_upload_consent{suffix}"] = dismiss_consent_dialog(page)
    page.wait_for_timeout(1000)
    try:
        result[f"prompt_fill{suffix}"] = fill_create_fields(page, result["create_fields"])
    except Exception as exc:
        state = box_state(page)
        auth_text = auth_required_text(state.get("text"))
        if auth_text:
            result[f"auth_required_state{suffix}"] = state
            result[f"prompt_fill_error{suffix}"] = repr(exc)
            record_auth_required(result, "prompt_fill", state, auth_text)
            return False
        page.screenshot(path=str(outdir / f"create_input_fill_failed{suffix}.jpg"), type="jpeg", quality=85, full_page=True)
        result[f"prompt_fill_error{suffix}"] = repr(exc)
        result["status"] = "create_input_not_ready"
        return False
    if normalize_perspective(task.get("perspective")) == "third-person":
        result["create_fields"]["_allow_text_only"] = True
    page.wait_for_timeout(1200)
    if not wait_create_input_ready(page, result["create_fields"], result):
        if result.get("status") == "auth_required":
            return False
        page.screenshot(path=str(outdir / f"create_input_not_ready{suffix}.jpg"), type="jpeg", quality=85, full_page=True)
        result["status"] = "create_input_not_ready"
        return False
    try:
        wait_submit_ready(page)
    except PlaywrightTimeoutError as exc:
        page.screenshot(path=str(outdir / f"submit_not_ready{suffix}.jpg"), type="jpeg", quality=85, full_page=True)
        result[f"submit_ready_error{suffix}"] = str(exc)
    page.screenshot(path=str(outdir / f"create_ready{suffix}.jpg"), type="jpeg", quality=85, full_page=True)
    result[f"submit{suffix}"] = click_submit(page)
    if not result[f"submit{suffix}"].get("clicked"):
        result["status"] = "submit_not_clicked"
        return False
    print(f"[{task['task_id']}] submit attempt={attempt} {result[f'submit{suffix}']}", flush=True)
    page.wait_for_timeout(3000)
    if not wait_for_explore(page, result):
        page.screenshot(path=str(outdir / f"explore_not_ready{suffix}.jpg"), type="jpeg", quality=85, full_page=True)
        result["status"] = "explore_not_ready"
        return False
    return True


def run_task_once(ctx, task, genie3_retry_index=0):
    outdir = task_output_dir(task)
    outdir.mkdir(parents=True, exist_ok=True)
    image_path = Path(task["resolved_image_path"])
    shutil.copyfile(image_path, outdir / f"{task['task_id']}_input.jpg")
    upload_info = make_landscape_upload_image(image_path, outdir / f"{task['task_id']}_upload_landscape.jpg")
    prompt = build_genie3_prompt(task)
    fields = build_genie3_fields(task)
    dataset_actions = expand_steps(task["action_sequence_steps"])
    wait_and_observe_task = is_wait_and_observe_task(task)
    actions = [] if wait_and_observe_task else [dict(action) for action in dataset_actions]
    rotation_loop_task = is_rotation_loop_task(task, actions)
    rotation_base_extra_ms = 0
    if rotation_loop_task and ROTATION_BASE_EXTRA_UNITS > 0:
        rotation_base_extra_ms = ROTATION_BASE_EXTRA_UNITS * HOLD_MS_PER_ACTION
        for action in reversed(actions):
            if is_turn_action(action):
                action["hold_ms"] = action_hold_ms(action) + rotation_base_extra_ms
                action["hold_token"] = hold_token_for_actions([action])
                action["rotation_base_extra_ms"] = rotation_base_extra_ms
                break
    final_orientation_task = is_final_orientation_task(task, actions)
    result = {
        "run_id": RUN_ID,
        "run_timestamp": RUN_TIMESTAMP,
        "task_id": task["task_id"],
        "group": task["group"],
        "source_file": task["source_file"],
        "prompt": task["prompt"],
        "create_prompt": prompt,
        "create_fields": fields,
        "image_path": str(image_path),
        "upload_image": upload_info,
        "perspective": task.get("perspective"),
        "perspective_normalized": normalize_perspective(task.get("perspective")),
        "output_dir_name": outdir.name,
        "action_sequence": task["action_sequence"],
        "action_sequence_steps": task["action_sequence_steps"],
        "dataset_expanded_actions": dataset_actions,
        "expanded_actions": actions,
        "wait_and_observe_task": wait_and_observe_task,
        "wait_and_observe_s": WAIT_AND_OBSERVE_S if wait_and_observe_task else 0,
        "hold_sequence_mode": HOLD_SEQUENCE_MODE,
        "hold_uses_absolute_deadline": True,
        "hold_ms_per_action": HOLD_MS_PER_ACTION,
        "rotation_base_extra_units": ROTATION_BASE_EXTRA_UNITS,
        "rotation_base_extra_ms": rotation_base_extra_ms,
        "guarantee_phase_completion": GUARANTEE_PHASE_COMPLETION,
        "action_phase_budget_s": ACTION_PHASE_BUDGET_S,
        "action_phase_reserve_s": ACTION_PHASE_RESERVE_S,
        "initial_action_delay_s": INITIAL_ACTION_DELAY_S,
        "auto_exit_after_actions": AUTO_EXIT_AFTER_ACTIONS,
        "planned_hold_sequence": hold_sequence_text(actions),
        "executed_actions": [],
        "executed_hold_actions": [],
        "adaptive_corrections": [],
        "adaptive_correction_enabled": ADAPTIVE_CORRECTION,
        "agent_guidance": AGENT_GUIDANCE,
        "adaptive_skip_remaining_enabled": ADAPTIVE_SKIP_REMAINING,
        "adaptive_prethink_enabled": ADAPTIVE_PRETHINK,
        "adaptive_pre_phase_plan_min_ms": ADAPTIVE_PRE_PHASE_PLAN_MIN_MS,
        "adaptive_phase_done_check_enabled": ADAPTIVE_PHASE_DONE_CHECK,
        "adaptive_phase_progress_check_enabled": ADAPTIVE_PHASE_PROGRESS_CHECK,
        "adaptive_phase_check_every": ADAPTIVE_PHASE_CHECK_EVERY,
        "adaptive_extend_hold_enabled": ADAPTIVE_EXTEND_HOLD,
        "adaptive_extend_hold_min_ms": ADAPTIVE_EXTEND_HOLD_MIN_MS,
        "adaptive_extend_hold_min_ms": 0,
        "adaptive_extend_hold_max_ms": ADAPTIVE_EXTEND_HOLD_MAX_MS,
        "adaptive_extend_hold_max_rounds": ADAPTIVE_EXTEND_HOLD_MAX_ROUNDS,
        "live_hold_stop_check_enabled": LIVE_HOLD_STOP_CHECK,
        "live_hold_check_interval_ms": LIVE_HOLD_CHECK_INTERVAL_MS,
        "live_hold_min_ms": LIVE_HOLD_MIN_MS,
        "live_hold_min_apply_ms": LIVE_HOLD_MIN_APPLY_MS,
        "live_hold_min_remaining_ms": LIVE_HOLD_MIN_REMAINING_MS,
        "live_hold_timeout_s": LIVE_HOLD_TIMEOUT_S,
        "live_hold_stop_checks": [],
        "live_hold_stops": [],
        "live_hold_skipped_actions": [],
        "require_full_action_sequence": REQUIRE_FULL_ACTION_SEQUENCE,
        "adaptive_skipped_actions": [],
        "adaptive_skip_recommendations": [],
        "adaptive_model": KIGRESS_MODEL if ADAPTIVE_CORRECTION else None,
        "adaptive_screenshot_max_width": ADAPTIVE_SCREENSHOT_MAX_WIDTH,
        "adaptive_screenshot_max_height": ADAPTIVE_SCREENSHOT_MAX_HEIGHT,
        "adaptive_screenshot_quality": ADAPTIVE_SCREENSHOT_QUALITY,
        "adaptive_context_actions": ADAPTIVE_CONTEXT_ACTIONS,
        "adaptive_max_completion_tokens": ADAPTIVE_MAX_COMPLETION_TOKENS,
        "adaptive_inter_key_timeout_s": ADAPTIVE_INTER_KEY_TIMEOUT_S,
        "live_hold_max_checks": LIVE_HOLD_MAX_CHECKS,
        "live_hold_max_completion_tokens": LIVE_HOLD_MAX_COMPLETION_TOKENS,
        "live_hold_max_adaptive_actions": LIVE_HOLD_MAX_ADAPTIVE_ACTIONS,
        "input_dispatch_methods": ["playwright", "cdp", "javascript"],
        "kigress_connection_reuse": True,
        "fast_repeat_press_enabled": FAST_REPEAT_PRESS,
        "fast_repeat_min_count": FAST_REPEAT_MIN_COUNT,
        "fast_repeat_check_fraction": FAST_REPEAT_CHECK_FRACTION,
        "fast_repeat_settle_s": FAST_REPEAT_SETTLE_S,
        "rotation_loop_task": rotation_loop_task,
        "circle_return_task": is_circle_return_task(task),
        "in_place_circle_task": is_in_place_circle_task(task),
        "force_circle_return_prompt": FORCE_CIRCLE_RETURN_PROMPT,
        "rotation_loop_check_enabled": ROTATION_LOOP_CHECK,
        "rotation_loop_skip_remaining_enabled": ROTATION_LOOP_SKIP_REMAINING,
        "rotation_loop_checks": [],
        "rotation_loop_skipped_actions": [],
        "rotation_loop_verified": None,
        "final_orientation_task": final_orientation_task,
        "final_orientation_check_enabled": FINAL_ORIENTATION_CHECK,
        "final_orientation_checks": [],
        "genie3_retry_index": genie3_retry_index,
        "genie3_error_retries_allowed": GENIE3_ERROR_RETRIES,
        "status": "started",
    }

    prethink_executor = None
    prethink_future = None
    if ADAPTIVE_CORRECTION and ADAPTIVE_PRETHINK:
        prethink_executor = ThreadPoolExecutor(max_workers=1)
        prethink_future = prethink_executor.submit(
            request_adaptive_prethink,
            task,
            actions,
            upload_info["path"],
        )
        result["adaptive_prethink_status"] = "started"

    def collect_prethink(timeout=0):
        if not prethink_future or result.get("adaptive_prethink"):
            return
        try:
            result["adaptive_prethink"] = prethink_future.result(timeout=timeout)
            result["adaptive_prethink_status"] = "done"
        except FutureTimeoutError:
            result["adaptive_prethink_status"] = "pending"
        except Exception as exc:
            result["adaptive_prethink"] = {"enabled": True, "error": repr(exc)}
            result["adaptive_prethink_status"] = "error"

    page = None
    for existing_page in list(ctx.pages):
        try:
            if page is None and (existing_page.url == "about:blank" or GENIE3_HOST_FRAGMENT in existing_page.url):
                page = existing_page
                continue
            if existing_page.url == "about:blank" or GENIE3_HOST_FRAGMENT in existing_page.url:
                existing_page.close()
        except Exception:
            pass
    if page is None:
        page = ctx.new_page()
    page.bring_to_front()
    recorder = None
    if FULL_PROCESS_RECORDING:
        recorder = FullProcessRecorder(page, outdir, task["task_id"])
        try:
            recorder.start()
            result["full_process_recording"] = {
                "enabled": True,
                "status": "recording",
                "path": str(recorder.output_path),
            }
            print(f"[{task['task_id']}] full-process recording started", flush=True)
        except Exception as exc:
            result["full_process_recording"] = {
                "enabled": True,
                "status": "recording_start_failed",
                "error": repr(exc),
            }
    try:
        explore_ready = False
        for attempt in range(1, CREATE_ATTEMPTS + 1):
            explore_ready = submit_create_attempt(
                page, task, prompt, Path(upload_info["path"]), outdir, result, attempt
            )
            if explore_ready:
                break
            if result.get("status") in {"genie3_retryable_error", "auth_required"}:
                break
            if attempt < CREATE_ATTEMPTS:
                print(f"[{task['task_id']}] retry create after status={result.get('status')}", flush=True)
                page.wait_for_timeout(CREATE_RETRY_DELAY_S * 1000)
        if not explore_ready:
            return result
        result["explore_url"] = page.url
        if not wait_for_interactive(page, result):
            page.screenshot(path=str(outdir / f"interactive_not_ready_retry_{genie3_retry_index}.jpg"), type="jpeg", quality=85, full_page=True)
            if result.get("status") != "genie3_retryable_error":
                result["status"] = "interactive_not_ready"
            return result
        collect_prethink(timeout=0)
        if wait_and_observe_task:
            result["initial_focus"] = {
                "focused": False,
                "reason": "wait_and_observe_no_world_input",
            }
        else:
            result["initial_focus"] = focus_world(page)
        if INITIAL_ACTION_DELAY_S > 0 and not wait_and_observe_task:
            print(f"[{task['task_id']}] initial action delay {INITIAL_ACTION_DELAY_S:.1f}s", flush=True)
            page.wait_for_timeout(INITIAL_ACTION_DELAY_S * 1000)
        rotation_loop_before_path = None
        final_orientation_before_path = None
        if rotation_loop_task:
            rotation_loop_before_path = outdir / "rotation_loop_before.jpg"
            page.screenshot(path=str(rotation_loop_before_path), type="jpeg", quality=85, full_page=True)
            result["rotation_loop_before_screenshot"] = str(rotation_loop_before_path)
        if final_orientation_task:
            final_orientation_before_path = outdir / "final_orientation_before.jpg"
            page.screenshot(path=str(final_orientation_before_path), type="jpeg", quality=85, full_page=True)
            result["final_orientation_before_screenshot"] = str(final_orientation_before_path)

        start = time.perf_counter()

        def can_spend_time_on_adaptive(next_original_index, estimated_check_s=None):
            if not GUARANTEE_PHASE_COMPLETION:
                return True
            elapsed_now = time.perf_counter() - start
            remaining_s = remaining_hold_ms(actions, next_original_index) / 1000.0
            check_s = ADAPTIVE_TIMEOUT_S if estimated_check_s is None else estimated_check_s
            projected_s = elapsed_now + remaining_s + ACTION_PHASE_RESERVE_S + check_s
            allowed = projected_s < ACTION_PHASE_BUDGET_S
            if not allowed:
                result.setdefault("adaptive_checks_skipped_for_phase_completion", []).append({
                    "after_original_index": next_original_index,
                    "elapsed_s": elapsed_now,
                    "remaining_original_hold_s": remaining_s,
                    "reserve_s": ACTION_PHASE_RESERVE_S,
                    "estimated_check_s": check_s,
                    "budget_s": ACTION_PHASE_BUDGET_S,
                    "reason": "preserve time to execute all original action phases",
                })
            return allowed

        def execute_pre_phase_corrections(correction_actions, phase_step):
            for correction_action in correction_actions:
                adaptive_elapsed = time.perf_counter() - start
                correction_hold_ms = hold_ms_for_actions([correction_action])
                correction_hold_token = hold_token_for_actions([correction_action])
                print(
                    f"[{task['task_id']}] pre-phase correction t={adaptive_elapsed:.1f}s {correction_hold_token}",
                    flush=True,
                )
                press_action(
                    page,
                    correction_action,
                    hold_ms=correction_hold_ms if correction_action["type"] != "wait" else None,
                )
                result["executed_hold_actions"].append({
                    "index": len(result["executed_hold_actions"]) + 1,
                    "elapsed_s": adaptive_elapsed,
                    "token": correction_hold_token,
                    "hold_ms": correction_hold_ms,
                    "logical_count": 1,
                    "phase_index": "adaptive",
                    "phase_step": correction_action.get("step"),
                    "adaptive": True,
                    "actions": [correction_action],
                })
                result["executed_actions"].append({
                    "index": len(result["executed_actions"]) + 1,
                    "elapsed_s": adaptive_elapsed,
                    "adaptive_phase": phase_step,
                    "hold_token": correction_hold_token,
                    "hold_ms": correction_hold_ms,
                    **correction_action,
                })
                if correction_action["type"] != "wait":
                    time.sleep(FAST_REPEAT_SETTLE_S)

        pre_phase_plan = None
        i = 0
        if wait_and_observe_task:
            observe_started_at = time.perf_counter()
            print(
                f"[{task['task_id']}] wait-and-observe no actions for {WAIT_AND_OBSERVE_S:.1f}s",
                flush=True,
            )
            page.wait_for_timeout(WAIT_AND_OBSERVE_S * 1000)
            result["wait_and_observe_actual_s"] = time.perf_counter() - observe_started_at
        while i < len(actions):
            action = actions[i]
            elapsed = time.perf_counter() - start
            phase_start_index, phase_end_index = phase_bounds(actions, i)
            if pre_phase_plan and pre_phase_plan["step_index"] != action.get("step_index"):
                pre_phase_plan = None
            if (
                pre_phase_plan is None
                and HOLD_SEQUENCE_MODE
                and not GUARANTEE_PHASE_COMPLETION
                and ADAPTIVE_SKIP_REMAINING
                and not rotation_loop_task
                and i == phase_start_index
                and can_hold_phase(actions, phase_start_index, phase_end_index)
                and hold_ms_for_actions(actions[phase_start_index:phase_end_index]) >= ADAPTIVE_PRE_PHASE_PLAN_MIN_MS
            ):
                total_in_phase = phase_end_index - phase_start_index
                min_keep = max(
                    1,
                    min(total_in_phase, math.ceil(total_in_phase * ADAPTIVE_SKIP_MIN_PHASE_FRACTION)),
                )
                correction = request_adaptive_correction(
                    page,
                    task,
                    result,
                    int(action["step_index"]),
                    action["step"],
                    outdir,
                    phase_done=False,
                    remaining_in_phase=total_in_phase,
                    remaining_phase_actions=actions_to_hold_tokens(actions[phase_start_index:phase_end_index]),
                    upcoming_dataset_actions=actions_to_hold_tokens(
                        actions[i:min(len(actions), i + ADAPTIVE_CONTEXT_ACTIONS)]
                    ),
                    min_required_phase_fraction=ADAPTIVE_SKIP_MIN_PHASE_FRACTION,
                )
                correction["completed_in_phase"] = 0
                correction["total_in_phase"] = total_in_phase
                correction["completed_fraction"] = 0
                correction["min_skip_fraction"] = ADAPTIVE_SKIP_MIN_PHASE_FRACTION
                result["adaptive_corrections"].append(correction)
                keep_count = (
                    min_keep
                    if correction.get("skip_remaining_phase") and not REQUIRE_FULL_ACTION_SEQUENCE
                    else total_in_phase
                )
                if correction.get("error"):
                    pre_phase_plan = None
                else:
                    pre_phase_plan = {
                        "step_index": action.get("step_index"),
                        "phase_start": phase_start_index,
                        "phase_end": phase_end_index,
                        "execute_end": phase_start_index + keep_count,
                        "keep_count": keep_count,
                        "total_in_phase": total_in_phase,
                        "correction": correction,
                    }
                print(
                    f"[{task['task_id']}] pre-phase trim phase={action['step']} keep={keep_count}/{total_in_phase} "
                    f"skip={correction.get('skip_remaining_phase')} steps={correction.get('correction_steps')} "
                    f"error={correction.get('error')}",
                    flush=True,
                )

            pre_phase_planned = bool(
                pre_phase_plan and pre_phase_plan["step_index"] == action.get("step_index")
            )
            live_hold_stopped_current_phase = False
            batch_size = fast_repeat_batch_size(actions, i, rotation_loop_task=rotation_loop_task)
            if pre_phase_planned:
                batch_size = min(batch_size, max(1, pre_phase_plan["execute_end"] - i))
            if batch_size > 1:
                hold_start_index = i
                hold_end_index = i + batch_size
                hold_ms = hold_ms_for_actions(actions[hold_start_index:hold_end_index])
                hold_token = hold_token_for_actions(actions[hold_start_index:hold_end_index])
                print(
                    f"[{task['task_id']}] hold action {i + 1}-{i + batch_size}/{len(actions)} "
                    f"t={elapsed:.1f}s {hold_token}",
                    flush=True,
                )
                fast_action = dict(action)
                fast_action["fast_repeat_count"] = batch_size
                fast_action["fast_repeat_hold_ms"] = hold_ms
                press_info = press_action(
                    page,
                    fast_action,
                    hold_ms=hold_ms,
                    live_hold_context=build_live_hold_context(task, result, actions, hold_start_index, hold_end_index),
                )
                live_hold_stopped_current_phase = bool(press_info.get("stop_current_hold"))
                result["executed_hold_actions"].append({
                    "index": len(result["executed_hold_actions"]) + 1,
                    "elapsed_s": elapsed,
                    "token": hold_token,
                    "hold_ms": hold_ms,
                    "actual_hold_ms": press_info.get("actual_hold_ms"),
                    "effective_hold_ms": press_info.get("effective_hold_ms"),
                    "input_dispatch": press_info.get("input_dispatch"),
                    "live_hold_stop": press_info.get("live_hold_stop"),
                    "live_hold_decision": press_info.get("live_hold_decision"),
                    "logical_count": batch_size,
                    "phase_index": action.get("step_index"),
                    "phase_step": action.get("step"),
                    "pre_phase_planned": pre_phase_planned,
                    "actions": actions[hold_start_index:hold_end_index],
                })
                group_id = len(result["executed_actions"]) + 1
                for offset in range(batch_size):
                    logical_action = dict(actions[i + offset])
                    logical_action["fast_repeat"] = True
                    logical_action["fast_repeat_group"] = group_id
                    logical_action["fast_repeat_count"] = batch_size
                    logical_action["fast_repeat_hold_ms"] = hold_ms
                    logical_action["hold_token"] = hold_token
                    logical_action["hold_ms"] = hold_ms
                    logical_action["actual_hold_ms"] = press_info.get("actual_hold_ms")
                    logical_action["live_hold_stop"] = press_info.get("live_hold_stop")
                    logical_action["pre_phase_planned"] = pre_phase_planned
                    result["executed_actions"].append({
                        "index": len(result["executed_actions"]) + 1,
                        "elapsed_s": elapsed + offset * ACTION_INTERVAL_S,
                        **logical_action,
                    })
                time.sleep(FAST_REPEAT_SETTLE_S)
                i += batch_size - 1
                if press_info.get("skip_remaining_phase"):
                    i = record_live_hold_skip(result, actions, i, press_info.get("live_hold_stop"))
                action = actions[i]
            else:
                hold_ms = hold_ms_for_actions([action])
                hold_token = hold_token_for_actions([action])
                print(f"[{task['task_id']}] hold action {i + 1}/{len(actions)} t={elapsed:.1f}s {hold_token}", flush=True)
                press_info = press_action(
                    page,
                    action,
                    hold_ms=hold_ms if action["type"] != "wait" else None,
                    live_hold_context=build_live_hold_context(task, result, actions, i, i + 1),
                )
                live_hold_stopped_current_phase = bool(press_info.get("stop_current_hold"))
                result["executed_hold_actions"].append({
                    "index": len(result["executed_hold_actions"]) + 1,
                    "elapsed_s": elapsed,
                    "token": hold_token,
                    "hold_ms": hold_ms if action["type"] != "wait" else int(action.get("seconds", 0) * 1000),
                    "actual_hold_ms": press_info.get("actual_hold_ms"),
                    "effective_hold_ms": press_info.get("effective_hold_ms"),
                    "input_dispatch": press_info.get("input_dispatch"),
                    "live_hold_stop": press_info.get("live_hold_stop"),
                    "live_hold_decision": press_info.get("live_hold_decision"),
                    "logical_count": 1,
                    "phase_index": action.get("step_index"),
                    "phase_step": action.get("step"),
                    "pre_phase_planned": pre_phase_planned,
                    "actions": [action],
                })
                action_record = dict(action)
                action_record["hold_token"] = hold_token
                action_record["hold_ms"] = hold_ms if action["type"] != "wait" else int(action.get("seconds", 0) * 1000)
                action_record["actual_hold_ms"] = press_info.get("actual_hold_ms")
                action_record["effective_hold_ms"] = press_info.get("effective_hold_ms")
                action_record["input_dispatch"] = press_info.get("input_dispatch")
                action_record["live_hold_stop"] = press_info.get("live_hold_stop")
                action_record["live_hold_decision"] = press_info.get("live_hold_decision")
                action_record["pre_phase_planned"] = pre_phase_planned
                result["executed_actions"].append({"index": len(result["executed_actions"]) + 1, "elapsed_s": elapsed, **action_record})
                if action["type"] != "wait":
                    if HOLD_SEQUENCE_MODE:
                        time.sleep(FAST_REPEAT_SETTLE_S)
                    else:
                        time.sleep(max(0, ACTION_INTERVAL_S - KEY_HOLD_MS / 1000.0))
                if press_info.get("skip_remaining_phase"):
                    i = record_live_hold_skip(result, actions, i, press_info.get("live_hold_stop"))
                    action = actions[i]

            execute_pre_phase_corrections(
                press_info.get("adaptive_actions", []),
                f"live_hold:{action.get('step')}",
            )

            pre_phase_tail_trimmed = False
            if press_info.get("skip_remaining_phase"):
                pre_phase_plan = None
            elif pre_phase_planned and i + 1 >= pre_phase_plan["execute_end"]:
                correction = pre_phase_plan["correction"]
                if correction.get("skip_remaining_phase") and pre_phase_plan["execute_end"] < pre_phase_plan["phase_end"]:
                    skipped_actions = actions[pre_phase_plan["execute_end"]:pre_phase_plan["phase_end"]]
                    skip_record = {
                        "phase_index": action.get("step_index"),
                        "phase_step": action.get("step"),
                        "after_action_index": len(result["executed_actions"]),
                        "completed_in_phase": pre_phase_plan["keep_count"],
                        "total_in_phase": pre_phase_plan["total_in_phase"],
                        "completed_fraction": pre_phase_plan["keep_count"] / pre_phase_plan["total_in_phase"],
                        "skipped_count": len(skipped_actions),
                        "skipped_hold_sequence": hold_sequence_text(skipped_actions),
                        "skipped_actions": skipped_actions,
                        "reason": correction.get("reason"),
                        "pre_phase_planned": True,
                    }
                    result["adaptive_skipped_actions"].append(skip_record)
                    i = pre_phase_plan["phase_end"] - 1
                    action = actions[i]
                    pre_phase_tail_trimmed = True
                execute_pre_phase_corrections(correction.get("actions", []), action.get("step"))
                pre_phase_plan = None

            next_index = i + 1
            next_action = actions[next_index] if next_index < len(actions) else None
            phase_done = next_action is None or next_action.get("step_index") != action.get("step_index")
            post_phase_extension_checked = False
            if (
                HOLD_SEQUENCE_MODE
                and ADAPTIVE_EXTEND_HOLD
                and phase_done
                and not rotation_loop_task
                and not live_hold_stopped_current_phase
                and not pre_phase_tail_trimmed
                and action.get("type") != "wait"
            ):
                executed_phase_start, _ = phase_bounds(actions, i)
                executed_phase_actions = actions[executed_phase_start:next_index]
                executed_phase_hold_ms = hold_ms_for_actions(executed_phase_actions)
                if (
                    executed_phase_hold_ms >= ADAPTIVE_EXTEND_HOLD_MIN_MS
                    and can_spend_time_on_adaptive(next_index)
                ):
                    # An extension always continues the original dataset phase. Claude may
                    # suggest other correction steps, but those never select the held key.
                    extension_source_action = executed_phase_actions[-1]
                    for extension_round in range(ADAPTIVE_EXTEND_HOLD_MAX_ROUNDS):
                        extension_elapsed = time.perf_counter() - start
                        extension_check = request_adaptive_correction(
                            page,
                            task,
                            result,
                            int(action["step_index"]),
                            action["step"],
                            outdir,
                            phase_done=True,
                            remaining_in_phase=0,
                            remaining_phase_actions=[],
                            upcoming_dataset_actions=actions_to_hold_tokens(
                                actions[next_index:min(len(actions), next_index + ADAPTIVE_CONTEXT_ACTIONS)]
                            ),
                            allow_hold_extension=True,
                            current_hold_actions=executed_phase_actions,
                            timeout_s=ADAPTIVE_INTER_KEY_TIMEOUT_S,
                        )
                        post_phase_extension_checked = True
                        extension_check["extension_round"] = extension_round + 1
                        extension_check["after_hold_ms"] = executed_phase_hold_ms
                        extension_check["post_original_phase"] = True
                        result.setdefault("adaptive_hold_extension_checks", []).append(extension_check)
                        extend_ms = int(extension_check.get("extend_current_hold_ms") or 0)
                        print(
                            f"[{task['task_id']}] post-phase hold extension phase={action['step']} "
                            f"round={extension_round + 1} extend_ms={extend_ms} "
                            f"steps={extension_check.get('correction_steps')} error={extension_check.get('error')}",
                            flush=True,
                        )
                        if extend_ms <= 0:
                            break
                        extension_action = make_hold_extension_action(extension_source_action, extend_ms)
                        extension_token = hold_token_for_actions([extension_action])
                        press_action(page, extension_action, hold_ms=extend_ms)
                        result["executed_hold_actions"].append({
                            "index": len(result["executed_hold_actions"]) + 1,
                            "elapsed_s": extension_elapsed,
                            "token": extension_token,
                            "hold_ms": extend_ms,
                            "logical_count": 1,
                            "phase_index": action.get("step_index"),
                            "phase_step": action.get("step"),
                            "adaptive_extension": True,
                            "post_original_phase": True,
                            "extension_round": extension_round + 1,
                            "actions": [extension_action],
                            "reason": extension_check.get("reason"),
                        })
                        result["executed_actions"].append({
                            "index": len(result["executed_actions"]) + 1,
                            "elapsed_s": extension_elapsed,
                            "adaptive_phase": action["step"],
                            "adaptive_extension": True,
                            "post_original_phase": True,
                            "hold_token": extension_token,
                            "hold_ms": extend_ms,
                            **extension_action,
                        })
                        time.sleep(FAST_REPEAT_SETTLE_S)
                        if not can_spend_time_on_adaptive(next_index):
                            break
            if (
                rotation_loop_task
                and ROTATION_LOOP_SKIP_REMAINING
                and not GUARANTEE_PHASE_COMPLETION
                and rotation_loop_before_path
                and not phase_done
            ):
                phase_start_index = i
                while (
                    phase_start_index > 0
                    and actions[phase_start_index - 1].get("step_index") == action.get("step_index")
                ):
                    phase_start_index -= 1
                phase_end_index = next_index
                while (
                    phase_end_index < len(actions)
                    and actions[phase_end_index].get("step_index") == action.get("step_index")
                ):
                    phase_end_index += 1
                completed_in_phase = i - phase_start_index + 1
                remaining_in_phase = phase_end_index - next_index
                should_check_rotation_loop = (
                    completed_in_phase >= ROTATION_LOOP_SKIP_MIN_ACTIONS
                    and remaining_in_phase > 0
                    and completed_in_phase % max(1, ROTATION_LOOP_SKIP_CHECK_EVERY) == 0
                )
                if should_check_rotation_loop:
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
                    if rotation_check.get("enabled"):
                        print(
                            f"[{task['task_id']}] rotation-loop mid completed={completed_in_phase} "
                            f"remaining={remaining_in_phase} closed={rotation_check.get('closed_loop_ok')} "
                            f"in_place={rotation_check.get('in_place_ok')} "
                            f"orient={rotation_check.get('orientation_ok')} "
                            f"error={rotation_check.get('error')}",
                            flush=True,
                        )
                    if (
                        rotation_check.get("enabled")
                        and rotation_check.get("closed_loop_ok")
                        and rotation_check.get("in_place_ok")
                        and rotation_check.get("orientation_ok")
                    ):
                        skipped_actions = actions[next_index:phase_end_index]
                        skip_record = {
                            "phase_index": action["step_index"],
                            "phase_step": action["step"],
                            "after_action_index": len(result["executed_actions"]),
                            "completed_in_phase": completed_in_phase,
                            "skipped_count": len(skipped_actions),
                            "skipped_actions": skipped_actions,
                            "reason": rotation_check.get("reason"),
                        }
                        if REQUIRE_FULL_ACTION_SEQUENCE:
                            result.setdefault("rotation_loop_skip_recommendations", []).append(skip_record)
                            print(
                                f"[{task['task_id']}] rotation-loop skip recommended but ignored "
                                f"because require_full_action_sequence=1",
                                flush=True,
                            )
                        else:
                            result["rotation_loop_skipped_actions"].append(skip_record)
                            i = phase_end_index
                            continue
            if (
                ADAPTIVE_SKIP_REMAINING
                and ADAPTIVE_PHASE_PROGRESS_CHECK
                and not phase_done
                and not rotation_loop_task
                and pre_phase_plan is None
            ):
                phase_start_index = i
                while (
                    phase_start_index > 0
                    and actions[phase_start_index - 1].get("step_index") == action.get("step_index")
                ):
                    phase_start_index -= 1
                phase_end_index = next_index
                while (
                    phase_end_index < len(actions)
                    and actions[phase_end_index].get("step_index") == action.get("step_index")
                ):
                    phase_end_index += 1
                completed_in_phase = i - phase_start_index + 1
                remaining_in_phase = phase_end_index - next_index
                total_in_phase = completed_in_phase + remaining_in_phase
                completed_fraction = completed_in_phase / total_in_phase if total_in_phase else 1.0
                should_check_progress = (
                    completed_in_phase % ADAPTIVE_PHASE_CHECK_EVERY == 0
                    or remaining_in_phase == 1
                )
                if not should_check_progress:
                    i += 1
                    continue
                if not can_spend_time_on_adaptive(next_index, ADAPTIVE_INTER_KEY_TIMEOUT_S):
                    i += 1
                    continue
                collect_prethink(timeout=0)
                remaining_phase_tokens = actions_to_hold_tokens(actions[next_index:phase_end_index])
                upcoming_tokens = actions_to_hold_tokens(
                    actions[next_index:min(len(actions), next_index + ADAPTIVE_CONTEXT_ACTIONS)]
                )
                correction = request_adaptive_correction(
                    page,
                    task,
                    result,
                    int(action["step_index"]),
                    action["step"],
                    outdir,
                    phase_done=False,
                    remaining_in_phase=remaining_in_phase,
                    remaining_phase_actions=remaining_phase_tokens,
                    upcoming_dataset_actions=upcoming_tokens,
                )
                correction["completed_in_phase"] = completed_in_phase
                correction["total_in_phase"] = total_in_phase
                correction["completed_fraction"] = completed_fraction
                correction["phase_check_every"] = ADAPTIVE_PHASE_CHECK_EVERY
                result["adaptive_corrections"].append(correction)
                if correction.get("enabled"):
                    print(
                        f"[{task['task_id']}] adaptive phase={action['step']} remaining={remaining_in_phase} "
                        f"completed={completed_in_phase}/{total_in_phase} "
                        f"skip={correction.get('skip_remaining_phase')} "
                        f"steps={correction.get('correction_steps')} error={correction.get('error')}",
                        flush=True,
                    )
                if correction.get("skip_remaining_phase"):
                    skipped_actions = actions[next_index:phase_end_index]
                    skip_record = {
                        "phase_index": action["step_index"],
                        "phase_step": action["step"],
                        "after_action_index": len(result["executed_actions"]),
                        "skipped_count": len(skipped_actions),
                        "skipped_actions": skipped_actions,
                        "reason": correction.get("reason"),
                    }
                    if REQUIRE_FULL_ACTION_SEQUENCE:
                        result["adaptive_skip_recommendations"].append(skip_record)
                        print(
                            f"[{task['task_id']}] adaptive skip recommended but ignored "
                            f"because require_full_action_sequence=1",
                            flush=True,
                        )
                    else:
                        result["adaptive_skipped_actions"].append(skip_record)
                    for correction_action in correction.get("actions", []):
                        adaptive_elapsed = time.perf_counter() - start
                        print(
                            f"[{task['task_id']}] adaptive action t={adaptive_elapsed:.1f}s {correction_action}",
                            flush=True,
                        )
                        press_action(page, correction_action)
                        result["executed_actions"].append({
                            "index": len(result["executed_actions"]) + 1,
                            "elapsed_s": adaptive_elapsed,
                            "adaptive_phase": action["step"],
                            **correction_action,
                        })
                        if correction_action["type"] != "wait":
                            time.sleep(max(0, ACTION_INTERVAL_S - KEY_HOLD_MS / 1000.0))
                    if not REQUIRE_FULL_ACTION_SEQUENCE:
                        i = phase_end_index
                        continue
            elif (
                ADAPTIVE_PHASE_DONE_CHECK
                and phase_done
                and not rotation_loop_task
                and not post_phase_extension_checked
            ):
                collect_prethink(timeout=0)
                correction = request_adaptive_correction(
                    page,
                    task,
                    result,
                    int(action["step_index"]),
                    action["step"],
                    outdir,
                    phase_done=True,
                    remaining_in_phase=0,
                    remaining_phase_actions=[],
                    upcoming_dataset_actions=actions_to_hold_tokens(
                        actions[next_index:min(len(actions), next_index + ADAPTIVE_CONTEXT_ACTIONS)]
                    ),
                    timeout_s=ADAPTIVE_INTER_KEY_TIMEOUT_S,
                )
                result["adaptive_corrections"].append(correction)
                if correction.get("enabled"):
                    print(
                        f"[{task['task_id']}] adaptive phase={action['step']} "
                        f"steps={correction.get('correction_steps')} error={correction.get('error')}",
                        flush=True,
                    )
                for correction_action in correction.get("actions", []):
                    adaptive_elapsed = time.perf_counter() - start
                    print(
                        f"[{task['task_id']}] adaptive action t={adaptive_elapsed:.1f}s {correction_action}",
                        flush=True,
                    )
                    press_action(page, correction_action)
                    result["executed_actions"].append({
                        "index": len(result["executed_actions"]) + 1,
                        "elapsed_s": adaptive_elapsed,
                        "adaptive_phase": action["step"],
                        **correction_action,
                    })
                    if correction_action["type"] != "wait":
                        time.sleep(FAST_REPEAT_SETTLE_S)
            elif phase_done and not rotation_loop_task and ADAPTIVE_CORRECTION:
                result.setdefault("adaptive_phase_done_checks_skipped", []).append({
                    "phase_index": action.get("step_index"),
                    "phase_step": action.get("step"),
                    "after_action_index": len(result["executed_actions"]),
                    "reason": "disabled by GENIE3_ADAPTIVE_PHASE_DONE_CHECK=0",
                })
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
                if rotation_check.get("enabled"):
                    print(
                        f"[{task['task_id']}] rotation-loop check={check_index} "
                        f"closed={rotation_check.get('closed_loop_ok')} "
                        f"in_place={rotation_check.get('in_place_ok')} "
                        f"orient={rotation_check.get('orientation_ok')} "
                        f"steps={rotation_check.get('correction_steps')} "
                        f"error={rotation_check.get('error')}",
                        flush=True,
                    )
                if not rotation_check.get("actions"):
                    break
                for correction_action in rotation_check["actions"]:
                    adaptive_elapsed = time.perf_counter() - start
                    print(
                        f"[{task['task_id']}] rotation-loop action t={adaptive_elapsed:.1f}s {correction_action}",
                        flush=True,
                    )
                    press_action(page, correction_action)
                    result["executed_actions"].append({
                        "index": len(result["executed_actions"]) + 1,
                        "elapsed_s": adaptive_elapsed,
                        "adaptive_phase": "closed_loop_rotation",
                        **correction_action,
                    })
                    if correction_action["type"] != "wait":
                        time.sleep(max(0, ACTION_INTERVAL_S - KEY_HOLD_MS / 1000.0))
            # A correction from the last allowed round still needs one observation.
            # This check is judgment-only: it cannot trigger another action.
            if (
                result["rotation_loop_checks"]
                and result["rotation_loop_checks"][-1].get("actions")
            ):
                final_check_index = len(result["rotation_loop_checks"])
                rotation_check = request_rotation_loop_check(
                    page,
                    task,
                    result,
                    outdir,
                    rotation_loop_before_path,
                    attempt_index=final_check_index,
                )
                rotation_check["judgment_only"] = True
                result["rotation_loop_checks"].append(rotation_check)
                if rotation_check.get("enabled"):
                    print(
                        f"[{task['task_id']}] rotation-loop final-check={final_check_index} "
                        f"closed={rotation_check.get('closed_loop_ok')} "
                        f"in_place={rotation_check.get('in_place_ok')} "
                        f"orient={rotation_check.get('orientation_ok')} "
                        f"steps={rotation_check.get('correction_steps')} "
                        f"error={rotation_check.get('error')}",
                        flush=True,
                    )
            if result["rotation_loop_checks"]:
                final_rotation_check = result["rotation_loop_checks"][-1]
                result["rotation_loop_verified"] = bool(
                    final_rotation_check.get("closed_loop_ok")
                    and final_rotation_check.get("in_place_ok")
                    and final_rotation_check.get("orientation_ok")
                )
                result["rotation_loop_verification_reason"] = final_rotation_check.get("reason")

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
                if orientation_check.get("enabled"):
                    print(
                        f"[{task['task_id']}] final-orientation check={check_index} "
                        f"ok={orientation_check.get('final_orientation_ok')} "
                        f"side={orientation_check.get('starting_side_ok')} "
                        f"anchor={orientation_check.get('anchor_visible')} "
                        f"missing={orientation_check.get('missing_anchor')} "
                        f"steps={orientation_check.get('correction_steps')} "
                        f"error={orientation_check.get('error')}",
                        flush=True,
                    )
                if not orientation_check.get("actions"):
                    break
                for correction_action in orientation_check["actions"]:
                    adaptive_elapsed = time.perf_counter() - start
                    print(
                        f"[{task['task_id']}] final-orientation action t={adaptive_elapsed:.1f}s {correction_action}",
                        flush=True,
                    )
                    press_action(page, correction_action)
                    result["executed_actions"].append({
                        "index": len(result["executed_actions"]) + 1,
                        "elapsed_s": adaptive_elapsed,
                        "adaptive_phase": "final_orientation",
                        **correction_action,
                    })
                    if correction_action["type"] != "wait":
                        time.sleep(max(0, ACTION_INTERVAL_S - KEY_HOLD_MS / 1000.0))
            if (
                result["final_orientation_checks"]
                and result["final_orientation_checks"][-1].get("actions")
            ):
                final_check_index = len(result["final_orientation_checks"])
                orientation_check = request_final_orientation_check(
                    page,
                    task,
                    result,
                    outdir,
                    final_orientation_before_path,
                    attempt_index=final_check_index,
                )
                orientation_check["judgment_only"] = True
                result["final_orientation_checks"].append(orientation_check)
                if orientation_check.get("enabled"):
                    print(
                        f"[{task['task_id']}] final-orientation final-check={final_check_index} "
                        f"ok={orientation_check.get('final_orientation_ok')} "
                        f"side={orientation_check.get('starting_side_ok')} "
                        f"anchor={orientation_check.get('anchor_visible')} "
                        f"steps={orientation_check.get('correction_steps')} "
                        f"error={orientation_check.get('error')}",
                        flush=True,
                    )

        result["action_elapsed_s"] = time.perf_counter() - start
        if not wait_and_observe_task:
            page.wait_for_timeout(2000)
        result["url_after_actions"] = page.url
        result["action_sequence_status"] = (
            "wait_and_observe_completed" if wait_and_observe_task else "completed"
        )
        result["status"] = "actions_completed_waiting_for_session"
        page.screenshot(path=str(outdir / "after_actions.jpg"), type="jpeg", quality=85, full_page=True)

        if AUTO_EXIT_AFTER_ACTIONS:
            exit_started_at = time.perf_counter()
            page.keyboard.press("Escape")
            page.wait_for_timeout(2500)
            result["exit_after_actions"] = {
                "pressed": True,
                "elapsed_s": time.perf_counter() - exit_started_at,
                "url": page.url,
            }
        else:
            result["exit_after_actions"] = {
                "pressed": False,
                "natural_session_end": True,
                "url": page.url,
            }

        result["post_action_result"] = wait_for_session_end_or_download(page, result)
        if result["post_action_result"].get("status") == "genie3_retryable_error":
            page.screenshot(path=str(outdir / f"post_action_genie3_error_retry_{genie3_retry_index}.jpg"), type="jpeg", quality=85, full_page=True)
            return result
        if result["post_action_result"].get("status") == "auth_required":
            return result
        result["status"] = "post_action_wait_completed"
        click_download_and_save(page, outdir, result)
        if result.get("download_status") in {"downloaded", "downloaded_from_downloads"}:
            result["status"] = "downloaded"
        else:
            result["status"] = "completed_without_download"
        return result
    finally:
        collect_prethink(timeout=0)
        if prethink_executor:
            prethink_executor.shutdown(wait=False, cancel_futures=True)
        if recorder and recorder.started_at:
            result["full_process_recording"] = recorder.stop()
            print(
                f"[{task['task_id']}] full-process recording "
                f"status={result['full_process_recording'].get('status')} "
                f"frames={result['full_process_recording'].get('frame_count')} "
                f"path={result['full_process_recording'].get('path')}",
                flush=True,
            )
        (outdir / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def run_task(ctx, task):
    last_result = None
    outdir = task_output_dir(task)
    outdir.mkdir(parents=True, exist_ok=True)
    for retry_index in range(GENIE3_ERROR_RETRIES + 1):
        try:
            result = run_task_once(ctx, task, retry_index)
        except Exception as exc:
            result_path = outdir / "result.json"
            if result_path.exists():
                try:
                    result = json.loads(result_path.read_text(encoding="utf-8"))
                except json.JSONDecodeError:
                    result = {}
            else:
                result = {}
            result.update({
                "run_id": RUN_ID,
                "run_timestamp": RUN_TIMESTAMP,
                "task_id": task["task_id"],
                "group": task["group"],
                "source_file": task["source_file"],
                "prompt": task["prompt"],
                "perspective": task.get("perspective"),
                "status": "task_retryable_exception",
                "task_exception": repr(exc),
                "genie3_retry_index": retry_index,
            })
            (outdir / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        last_result = result
        if result.get("status") not in {"genie3_retryable_error", "task_retryable_exception"}:
            return result
        result.setdefault("genie3_task_retries", []).append({
            "retry_index": retry_index,
            "phase": result.get("genie3_error_phase"),
            "error": result.get("genie3_error_text") or result.get("task_exception"),
        })
        if retry_index < GENIE3_ERROR_RETRIES:
            print(
                f"[{task['task_id']}] Genie3 error retry {retry_index + 1}/{GENIE3_ERROR_RETRIES} "
                f"phase={result.get('genie3_error_phase')} "
                f"error={result.get('genie3_error_text') or result.get('task_exception')}",
                flush=True,
            )
            time.sleep(CREATE_RETRY_DELAY_S)
    last_result["status"] = "skipped_genie3_error_retries_exceeded"
    last_result["download_status"] = last_result.get("download_status") or "skipped"
    last_result["genie3_error_retries_exceeded"] = GENIE3_ERROR_RETRIES
    (outdir / "result.json").write_text(json.dumps(last_result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return last_result


def main():
    controller_preflight = require_claude_haiku_controller()
    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    RUN_META_DIR.mkdir(parents=True, exist_ok=True)
    tasks = load_tasks()
    print(json.dumps({
        "run_id": RUN_ID,
        "run_timestamp": RUN_TIMESTAMP,
        "out_dir": str(OUT_ROOT),
        "run_meta_dir": str(RUN_META_DIR),
        "flat_task_directories": True,
        "all_tasks": ALL_TASKS,
        "task_count": len(tasks),
        "skip_existing_success": SKIP_EXISTING_SUCCESS,
        "skip_existing_terminal_failure": SKIP_EXISTING_TERMINAL_FAILURE,
        "split_by_perspective": False,
        "perspective_filter": sorted(PERSPECTIVE_FILTER),
        "claude_controller_preflight": controller_preflight,
    }, ensure_ascii=False), flush=True)
    p = sync_playwright().start()
    all_results = []
    try:
        browser = p.chromium.connect_over_cdp(GENIE3_CDP_URL)
        print(f"DOWNLOAD_BEHAVIOR={configure_browser_downloads(browser)}", flush=True)
        ctx = browser.contexts[0] if browser.contexts else browser.new_context(accept_downloads=True)
        for task in tasks:
            if SKIP_EXISTING_SUCCESS and has_successful_result(task):
                result_path = task_output_dir(task) / "result.json"
                result = json.loads(result_path.read_text(encoding="utf-8"))
                result["status"] = "skipped_existing_success"
                all_results.append(result)
                print(f"\n=== SKIP {task['task_id']} {task.get('perspective')} existing successful result ===", flush=True)
                continue
            if SKIP_EXISTING_TERMINAL_FAILURE and has_terminal_failure_result(task):
                result_path = task_output_dir(task) / "result.json"
                result = json.loads(result_path.read_text(encoding="utf-8"))
                result["status"] = f"skipped_existing_{result.get('status')}"
                all_results.append(result)
                print(f"\n=== SKIP {task['task_id']} {task.get('perspective')} existing terminal failure ===", flush=True)
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
    finally:
        summary_path = RUN_META_DIR / "summary.json"
        summary_path.write_text(json.dumps(all_results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        p.stop()
        print(f"SUMMARY={summary_path}", flush=True)


if __name__ == "__main__":
    main()
