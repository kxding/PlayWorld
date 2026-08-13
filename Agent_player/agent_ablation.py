"""Provider-neutral action agent support for HappyOyster ablations."""

import base64
import json
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path


VALID_MODES = {"preset_only", "agent_only", "preset_agent"}
VALID_PROVIDERS = {"claude", "gemini"}
ALLOWED_KEYS = {"w", "a", "s", "d", "left", "right", "up", "down", "space", "e"}
ACTION_RE = re.compile(r"^hold\((w|a|s|d|left|right|up|down|space|e),([1-9]\d{1,4})ms\)$", re.I)
WAIT_RE = re.compile(r"^wait\(([1-9]\d{1,4})ms\)$", re.I)


@dataclass(frozen=True)
class AgentConfig:
    provider: str
    model: str
    base_url: str
    headers: dict
    transport: str = "openai"
    verify_tls: bool = True
    trust_env: bool = False


def ablation_mode():
    mode = os.environ.get("AGENT_ABLATION_MODE", "").strip().lower()
    if mode and mode not in VALID_MODES:
        raise ValueError(f"AGENT_ABLATION_MODE must be one of {sorted(VALID_MODES)}, got {mode!r}")
    return mode


def configured_agent():
    provider = os.environ.get("AGENT_PROVIDER", "claude").strip().lower()
    if provider not in VALID_PROVIDERS:
        raise ValueError(f"AGENT_PROVIDER must be one of {sorted(VALID_PROVIDERS)}, got {provider!r}")

    if provider == "claude":
        requested_transport = os.environ.get("AGENT_TRANSPORT", "openai").strip().lower()
        if requested_transport == "anthropic":
            model = os.environ.get("AGENT_MODEL") or os.environ.get("WQ_MODEL", "ep-hizen2-1786024970943139465")
            base_url = os.environ.get("AGENT_BASE_URL") or os.environ.get(
                "WQ_MESSAGES_URL", "https://wanqing-api.corp.kuaishou.com/api/gateway/v1/messages"
            )
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {os.environ['WQ_API_KEY']}",
            }
            verify_tls, trust_env, transport = True, False, "anthropic"
        else:
            model = os.environ.get("AGENT_MODEL") or os.environ.get("KIGRESS_MODEL", "claude-haiku-4-5-20251001")
            base_url = (os.environ.get("AGENT_BASE_URL") or os.environ.get("KIGRESS_BASE_URL", "")).rstrip("/")
            headers = {
                "Content-Type": "application/json",
                "x-api-key": os.environ.get("KIGRESS_API_KEY", ""),
                "x-ks-user-key": os.environ.get("KIGRESS_USER_KEY", ""),
                "x-ks-llm-model": model,
                "x-ks-biz-scene": os.environ.get("KIGRESS_BIZ_SCENE", "offline"),
            }
            host = os.environ.get("KIGRESS_HOST_HEADER", "").strip()
            if host:
                headers["Host"] = host
            verify_tls = os.environ.get("KIGRESS_VERIFY_TLS", "1").lower() not in {"0", "false", "no", "off"}
            trust_env = os.environ.get("KIGRESS_TRUST_ENV", "0").lower() in {"1", "true", "yes", "on"}
            transport = "openai"
    else:
        model = os.environ.get("AGENT_MODEL") or os.environ.get("GEMINI_MODEL", "gemini-3.1-pro-preview")
        requested_transport = os.environ.get("AGENT_TRANSPORT", "openai").strip().lower()
        if requested_transport == "gemini_generate_content":
            base_url = os.environ.get("AGENT_BASE_URL") or os.environ.get("GEMINI_GENERATE_CONTENT_URL", "")
            headers = {
                "Content-Type": "application/json",
                "x-api-key": os.environ.get("GEMINI_GATEWAY_API_KEY", ""),
                "x-ks-user-key": os.environ.get("GEMINI_GATEWAY_USER_KEY", ""),
                "x-ks-llm-model": model,
                "x-ks-biz-scene": os.environ.get("GEMINI_GATEWAY_BIZ_SCENE", "offline"),
            }
            verify_tls, trust_env, transport = True, False, "gemini_generate_content"
        else:
            base_url = (
                os.environ.get("AGENT_BASE_URL")
                or os.environ.get("GEMINI_BASE_URL")
                or "https://generativelanguage.googleapis.com/v1beta/openai"
            ).rstrip("/")
            key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY", "")
            headers = {"Content-Type": "application/json", "Authorization": f"Bearer {key}"}
            verify_tls, trust_env, transport = True, False, "openai"

    return AgentConfig(provider, model, base_url, headers, transport, verify_tls, trust_env)


def validate_agent_config(config):
    missing = []
    if not config.base_url:
        missing.append("agent base URL")
    if config.provider == "claude":
        if config.transport == "anthropic":
            if not config.headers.get("Authorization", "").removeprefix("Bearer "):
                missing.append("WQ_API_KEY")
        else:
            if not config.headers.get("x-api-key"):
                missing.append("KIGRESS_API_KEY")
            if not config.headers.get("x-ks-user-key"):
                missing.append("KIGRESS_USER_KEY")
    elif config.transport == "gemini_generate_content":
        if not config.headers.get("x-api-key"):
            missing.append("GEMINI_GATEWAY_API_KEY")
        if not config.headers.get("x-ks-user-key"):
            missing.append("GEMINI_GATEWAY_USER_KEY")
    elif not config.headers.get("Authorization", "").removeprefix("Bearer "):
        missing.append("GEMINI_API_KEY or GOOGLE_API_KEY")
    if missing:
        raise RuntimeError("Missing agent configuration: " + ", ".join(missing))


def observation_package(objective, initial_observation_path, latest_observation_path, executed_actions):
    """The only semantic context visible to an Agent Only model."""
    return {
        "objective": objective,
        "initial_observation": str(initial_observation_path),
        "latest_observation": str(latest_observation_path),
        "executed_actions": list(executed_actions),
    }


def _image_part(path, label):
    data = base64.b64encode(Path(path).read_bytes()).decode("ascii")
    return [
        {"type": "text", "text": label},
        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{data}"}},
    ]


def build_agent_only_messages(package, max_actions):
    """Build identical message content for every provider, independent of base actions."""
    system = (
        "You control a first- or third-person interactive world from visual observations. "
        "Choose the next small action from scratch to achieve the objective. "
        "You have no preset plan. Use only the objective, the initial observation, the latest observation, "
        "and the actions already executed below. Return strict JSON only. "
        f"Schema: {{\"status\":\"continue|done\",\"actions\":[\"hold(w,650ms)\"],\"reason\":\"short reason\"}}. "
        f"Return at most {max_actions} actions. Allowed DSL: hold(w|a|s|d|left|right|up|down|space|e,100..10000ms) "
        "or wait(100..10000ms). Use status=done and actions=[] when the objective is complete."
    )
    content = [{
        "type": "text",
        "text": json.dumps(
            {"objective": package["objective"], "executed_actions": package["executed_actions"]},
            ensure_ascii=False,
            separators=(",", ":"),
        ),
    }]
    content.extend(_image_part(package["initial_observation"], "Initial observation:"))
    content.extend(_image_part(package["latest_observation"], "Latest observation:"))
    return [{"role": "system", "content": system}, {"role": "user", "content": content}]


def transport_request(config, payload):
    """Translate one OpenAI-style multimodal request without changing semantic content."""
    if config.transport == "openai":
        return f"{config.base_url}/chat/completions", payload
    if config.transport == "gemini_generate_content":
        system_parts = []
        contents = []
        for message in payload.get("messages") or []:
            content = message.get("content")
            if message.get("role") == "system":
                system_parts.append(content if isinstance(content, str) else json.dumps(content, ensure_ascii=False))
                continue
            parts = []
            for part in ([{"type": "text", "text": content}] if isinstance(content, str) else content or []):
                if part.get("type") == "text":
                    parts.append({"text": part.get("text", "")})
                elif part.get("type") == "image_url":
                    url = part["image_url"]["url"]
                    media_type, data = url.removeprefix("data:").split(";base64,", 1)
                    parts.append({"inlineData": {"mimeType": media_type, "data": data}})
            contents.append({"role": "model" if message.get("role") == "assistant" else "user", "parts": parts})
        translated = {
            "contents": contents,
            "generationConfig": {
                "maxOutputTokens": payload.get("max_completion_tokens") or payload.get("max_tokens") or 256,
                "responseMimeType": "application/json",
            },
        }
        if system_parts:
            translated["systemInstruction"] = {"parts": [{"text": "\n".join(system_parts)}]}
        return config.base_url, translated
    messages = []
    system_parts = []
    for message in payload.get("messages") or []:
        if message.get("role") == "system":
            content = message.get("content") or ""
            system_parts.append(content if isinstance(content, str) else json.dumps(content, ensure_ascii=False))
            continue
        content = message.get("content")
        if isinstance(content, str):
            converted = content
        else:
            converted = []
            for part in content or []:
                if part.get("type") == "text":
                    converted.append(part)
                elif part.get("type") == "image_url":
                    url = part["image_url"]["url"]
                    media_type, data = url.removeprefix("data:").split(";base64,", 1)
                    converted.append({
                        "type": "image",
                        "source": {"type": "base64", "media_type": media_type, "data": data},
                    })

        messages.append({"role": message.get("role", "user"), "content": converted})
    translated = {
        "model": payload["model"],
        "max_tokens": payload.get("max_completion_tokens") or payload.get("max_tokens") or 256,
        "messages": messages,
    }
    if system_parts:
        translated["system"] = "\n".join(system_parts)
    return config.base_url, translated


def post_chat_completion(client, config, payload, timeout_s):
    request_url, request_payload = transport_request(config, payload)
    return client.post(
        request_url,
        headers=config.headers,
        json=request_payload,
        timeout=timeout_s,
    )


def extract_response_text(data):
    choices = data.get("choices") or []
    if choices:
        content = (choices[0].get("message") or {}).get("content") or ""
    elif data.get("candidates"):
        content = [
            part
            for candidate in data.get("candidates") or []
            for part in ((candidate.get("content") or {}).get("parts") or [])
        ]
    else:
        content = data.get("content") or ""
    if isinstance(content, list):
        return "".join(item.get("text", "") if isinstance(item, dict) else str(item) for item in content)
    return str(content)


def parse_agent_decision(raw_text, max_actions=3):
    text = (raw_text or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?", "", text).strip()
        text = re.sub(r"```$", "", text).strip()
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.S)
        if not match:
            raise
        parsed = json.loads(match.group(0))
    status = str(parsed.get("status", "continue")).strip().lower()
    if status not in {"continue", "done"}:
        raise ValueError(f"Invalid agent status: {status!r}")
    actions = []
    for token in parsed.get("actions") or []:
        token = re.sub(r"\s+", "", str(token)).lower()
        key_match = ACTION_RE.fullmatch(token)
        wait_match = WAIT_RE.fullmatch(token)
        if key_match:
            duration = max(100, min(10000, int(key_match.group(2))))
            actions.append({"type": "key", "keys": [key_match.group(1).lower()], "hold_ms": duration, "raw": token})
        elif wait_match:
            duration = max(100, min(10000, int(wait_match.group(1))))
            actions.append({"type": "wait", "seconds": duration / 1000, "hold_ms": duration, "raw": token})
        else:
            raise ValueError(f"Invalid action DSL: {token!r}")
        if len(actions) >= max_actions:
            break
    if status == "continue" and not actions:
        raise ValueError("Agent returned continue without an action")
    return {"status": status, "actions": actions, "reason": str(parsed.get("reason") or "")[:500]}


def request_agent_decision(client, config, package, max_actions=3, max_tokens=160, timeout_s=60):
    messages = build_agent_only_messages(package, max_actions)
    payload = {"model": config.model, "max_completion_tokens": max_tokens, "messages": messages}
    if config.transport == "openai":
        payload["response_format"] = {"type": "json_object"}
    started = time.perf_counter()
    response = post_chat_completion(client, config, payload, timeout_s)
    latency_ms = int((time.perf_counter() - started) * 1000)
    response.raise_for_status()
    data = response.json()
    content = extract_response_text(data)
    decision = parse_agent_decision(content, max_actions=max_actions)
    decision.update({
        "raw_response": content,
        "decision_latency_ms": latency_ms,
        "response_model": data.get("model") or data.get("modelVersion") or config.model,
    })
    return decision, messages


def action_signature(action):
    if action.get("type") == "wait":
        duration = int(action.get("hold_ms") or float(action.get("seconds", 0)) * 1000)
        return ("wait", (), round(duration / 250))
    duration = int(action.get("actual_hold_ms") or action.get("hold_ms") or 0)
    return ("key", tuple(sorted(str(k).lower() for k in action.get("keys", []))), round(duration / 250))


def align_action_sources(base_actions, executed_actions, mode):
    """Action-aware Levenshtein alignment with provenance records."""
    if mode == "preset_only":
        records = []
        for index, action in enumerate(executed_actions):
            records.append({"index": index + 1, "source": "retained", "base_index": index + 1})
        return records, []
    if mode == "agent_only":
        records = [{"index": i + 1, "source": "inserted", "base_index": None} for i in range(len(executed_actions))]
        deleted = [{"base_index": i + 1, "source": "deleted"} for i in range(len(base_actions))]
        return records, deleted

    n, m = len(base_actions), len(executed_actions)
    dp = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n + 1):
        dp[i][0] = i
    for j in range(m + 1):
        dp[0][j] = j
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            same = action_signature(base_actions[i - 1]) == action_signature(executed_actions[j - 1])
            dp[i][j] = min(dp[i - 1][j] + 1, dp[i][j - 1] + 1, dp[i - 1][j - 1] + (0 if same else 1))
    records, deleted = [], []
    i, j = n, m
    while i or j:
        if i and j:
            same = action_signature(base_actions[i - 1]) == action_signature(executed_actions[j - 1])
            cost = 0 if same else 1
            if dp[i][j] == dp[i - 1][j - 1] + cost:
                records.append({"index": j, "source": "retained" if same else "replaced", "base_index": i})
                i -= 1
                j -= 1
                continue
        if j and dp[i][j] == dp[i][j - 1] + 1:
            records.append({"index": j, "source": "inserted", "base_index": None})
            j -= 1
        else:
            deleted.append({"base_index": i, "source": "deleted"})
            i -= 1
    return list(reversed(records)), list(reversed(deleted))
