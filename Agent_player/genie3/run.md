# Genie3 新窗口 / 新机器运行手册

本文档记录当前 Genie3 runner 的可迁移运行上下文。以
`../player_genie3.py`、`run_oe_all_loop.sh` 和
`run_landscape_gc_loop.sh` 的当前代码为准；旧 `README.md` 和
`agent_control.md` 中的 `9223`、旧输出层级及生成后 Claude 验收说明可能已过期。

## 1. 当前运行约定

- Chrome CDP 主端口使用 `9228`；如需第二个独立 Profile，可使用 `9229`。
- 每个任务必须上传 JSON 指定的首帧图片，看到首帧预览后才提交创建。
- `first-person` 的人物框必须留空。
- `third-person` 的人物框由 runner 从 prompt 开头的主体中提取并填写。
- 世界进入可按键状态后等待 `1s`，再执行第一个 action。
- `wait and observe` 任务不发送任何按键，等待 `60s` 后结束。
- action sequence 以 JSON 为唯一初始来源。不要人工或用 ChatGPT 改 action；只允许 Claude 根据运行截图做 adaptive 更新。
- hold 期间可持续截图问 Claude，检查间隔目标为 `200ms`。Claude 可以在 hold 刚开始时接收请求，但只有 hold 总年龄达到 `600ms` 后才能应用提前 keyup；剩余时长不足 `600ms` 也可以停。
- 长按使用单调时钟的绝对截止时间。截图和 Claude 状态检测耗时包含在原定 hold 时长内，不会反复累加；截止点到达立即松键，未完成的检测不会阻塞下一个按键。
- 普通按键之间 settle 为 `0ms`，并且不在每个 action 前重复点击游戏画面。phase 结束后的同步 Claude 延长与 phase-done 请求默认关闭，避免在两个原始按键之间产生等待；只保留 hold 期间的异步 Claude 截图判断。
- 原始 phase 完成后即可询问 Claude 是否延长，不要求该 phase 已执行满 `2000ms`。若需要延长，实际继续按住的始终是刚执行的原始 phase 按键；Claude 同次返回的其他 phase/correction 按键不会替换延长按键。单轮最多延长 `2400ms`。
- Claude 低延迟模式默认优先截取游戏 `canvas/video`，压缩到最大 `640x360`、JPEG quality `40`；进程内复用同一个 HTTP 连接，只携带最多 5 个后续 action。普通 adaptive 最多返回 100 tokens，live hold 最多 60 tokens，每个 hold 最多发起 3 次 live 判断。
- 不再做视频生成完成后的 Claude 校验。Claude 只参与 action 执行期间的 adaptive 判断。
- 所有 action 完成后不按 `Escape`，保持无输入并等待 Genie3 会话自然结束、出现下载按钮。
- 成功标准为 `result.json` 状态是 `downloaded`/`completed`，且存在大于 1000 字节的 `*_native.*` 视频。
- 输出目录扁平放置：`<OUT_ROOT>/GC001_YYYYMMDD_HHMMSS/`，不要再增加 run-id 上层目录。

## 2. 新机器准备

建议保持项目在同一路径，因为当前两个批量脚本内含绝对 `ROOT`：

```bash
ROOT=/Users/kaixinding/Documents/research/0316_worldmodelbenchmark/WorldModelBenchMark_latest
CODE="${PLAYWORLD_CODE:-$ROOT/opensource/playworld_code}/Agent_player/genie3"
cd "$CODE"
```

若新机器路径不同，先修改以下脚本顶部的 `ROOT`：

- `run_oe_all_loop.sh`
- `run_landscape_gc_loop.sh`
- `run_full_latest_context_loop.sh`（仅在需要 GC/IF/OE 全量时使用）

安装 Python 运行环境：

```bash
python3 -m venv /tmp/genie3_pw161_runtime
/tmp/genie3_pw161_runtime/bin/pip install -r "$CODE/requirements.txt"
/tmp/genie3_pw161_runtime/bin/python -m playwright install chromium
```

如果使用持久环境，也可以创建 `$HOME/.genie3_runtime_venv`，并在运行时设置：

```bash
export GENIE3_PYTHON_BIN="$HOME/.genie3_runtime_venv/bin/python"
```

## 3. Claude / KIGRESS 配置

运行前加载仓库中的配置：

```bash
cd "$CODE"
source ../api_keys.sh
```

当前默认模型为 `claude-haiku-4-5-20251001`，另有
`claude-opus-4-5` 可用。内网默认地址由 `api_keys.sh` 提供；办公网访问时覆盖为：

完整配置如下：

```bash
export KIGRESS_BASE_URL=https://kigress-gateway.corp.kuaishou.com/mmu-dingkaixin03-68368/v1
export KIGRESS_API_KEY="${KIGRESS_API_KEY:?Load the managed gateway key from a secure environment}"
export KIGRESS_USER_KEY=mmu-dingkaixin03-68368
export KIGRESS_MODEL=claude-haiku-4-5-20251001
export KIGRESS_OPUS_MODEL=claude-opus-4-5
export KIGRESS_BIZ_SCENE=offline
export KIGRESS_TRUST_ENV=0
```

对应请求 header：

```text
x-api-key: $KIGRESS_API_KEY
x-ks-user-key: mmu-dingkaixin03-68368
x-ks-llm-model: claude-haiku-4-5-20251001
x-ks-biz-scene: offline
```

办公网只替换 host，后面的路径和其他配置保持不变：

```bash
export KIGRESS_BASE_URL=https://kigress-gateway.corp.kuaishou.com/mmu-dingkaixin03-68368/v1
```

确认 Claude 可用后再跑任务：

```bash
curl -sS -X POST "$KIGRESS_BASE_URL/chat/completions" \
  -H 'Content-Type: application/json' \
  -H "x-api-key: $KIGRESS_API_KEY" \
  -H "x-ks-user-key: $KIGRESS_USER_KEY" \
  -H "x-ks-llm-model: $KIGRESS_MODEL" \
  -H "x-ks-biz-scene: $KIGRESS_BIZ_SCENE" \
  -d "{\"messages\":[{\"role\":\"user\",\"content\":\"reply OK\"}],\"max_completion_tokens\":20,\"model\":\"$KIGRESS_MODEL\"}"
```

正常应返回 HTTP 200 和非空 assistant content。runner 启动时也会打印
`claude_controller_preflight.http_status: 200`；不是 200 时不要继续批量生成。

## 4. 启动并登录 Chrome Profile

首次在新机器启动 9228：

```bash
cd "$CODE"
GENIE3_CDP_PORT=9228 \
GENIE3_CHROME_PROFILE="$HOME/.genie3_chrome_profile_9228" \
./launch_chrome_cdp.sh
```

在打开的 Chrome 中手动登录 Genie3，并进入创建页。登录会保存在该 Profile，之后复用。

验证 CDP：

```bash
curl -sS http://127.0.0.1:9228/json/version
lsof -nP -iTCP:9228 -sTCP:LISTEN
```

需要全新 Profile 时，先停止使用该 Profile 的 Chrome，再删除目录并重启：

```bash
rm -rf "$HOME/.genie3_chrome_profile_9228"
GENIE3_CDP_PORT=9228 \
GENIE3_CHROME_PROFILE="$HOME/.genie3_chrome_profile_9228" \
./launch_chrome_cdp.sh
```

不要在 Chrome 仍运行时删除 Profile。第二个窗口使用不同目录和端口，例如
`$HOME/.genie3_chrome_profile_9229` 与 `9229`，并分别完成登录。

## 5. 单任务或指定任务重跑

下面是当前推荐的直接命令，避免 `run_task.sh` 中仍存在的旧数据/输出默认值：

```bash
ROOT=/Users/kaixinding/Documents/research/0316_worldmodelbenchmark/WorldModelBenchMark_latest
CODE="${PLAYWORLD_CODE:-$ROOT/opensource/playworld_code}/Agent_player/genie3"
RUN_ID="gc004_gc005_adaptive_$(date +%Y%m%d_%H%M%S)"

cd "$CODE"
source ../api_keys.sh
export GENIE3_CDP_URL=http://127.0.0.1:9228
export GENIE3_RUN_ID="$RUN_ID"
export GENIE3_DATA_ROOT="$ROOT/worldplay_0622"
export GENIE3_DATA_FILES="GC:$ROOT/worldplay_0622/GC.json"
export GENIE3_OUT_ROOT="$ROOT/result/genie3"
export GENIE3_RUN_LOG_ROOT="$ROOT/result/genie3-logs"
export TASK_IDS=GC004,GC005
export SKIP_EXISTING_SUCCESS=0
export SKIP_EXISTING_TERMINAL_FAILURE=0
export CREATE_WAIT_TIMEOUT_S=600
export POST_ACTION_WAIT_S=300
export GENIE3_INITIAL_ACTION_DELAY_S=1
export GENIE3_WAIT_AND_OBSERVE_S=60
export GENIE3_AUTO_EXIT_AFTER_ACTIONS=0
export GENIE3_ADAPTIVE_CORRECTION=1
export GENIE3_ADAPTIVE_PRETHINK=0
export GENIE3_ADAPTIVE_PHASE_DONE_CHECK=1
export GENIE3_ADAPTIVE_PHASE_PROGRESS_CHECK=1
export GENIE3_ADAPTIVE_PHASE_CHECK_EVERY=3
export GENIE3_ADAPTIVE_EXTEND_HOLD=1
export GENIE3_ADAPTIVE_EXTEND_HOLD_MIN_MS=2000
export GENIE3_LIVE_HOLD_STOP_CHECK=1
export GENIE3_LIVE_HOLD_CHECK_INTERVAL_MS=50
export GENIE3_LIVE_HOLD_MIN_APPLY_MS=600
export GENIE3_LIVE_HOLD_MAX_CHECKS=20
export GENIE3_LIVE_HOLD_SCREENSHOT_QUALITY=45
export GENIE3_ADAPTIVE_SCREENSHOT_MAX_WIDTH=640
export GENIE3_ADAPTIVE_SCREENSHOT_MAX_HEIGHT=360
export GENIE3_ADAPTIVE_SCREENSHOT_QUALITY=40
export GENIE3_ADAPTIVE_CONTEXT_ACTIONS=5
export GENIE3_ADAPTIVE_MAX_COMPLETION_TOKENS=100
export GENIE3_LIVE_HOLD_MAX_COMPLETION_TOKENS=64
export GENIE3_FAST_REPEAT_SETTLE_S=0
export GENIE3_ADAPTIVE_INTER_KEY_TIMEOUT_S=5
export GENIE3_ROTATION_LOOP_CHECK=1
export GENIE3_FINAL_ORIENTATION_CHECK=1
export GENIE3_ERROR_RETRIES=3
export PYTHONUNBUFFERED=1

/tmp/genie3_pw161_runtime/bin/python "$CODE/../player_genie3.py"
```

运行 IF/OE 时只替换 `GENIE3_DATA_FILES` 和 `TASK_IDS`，例如：

```bash
export GENIE3_DATA_FILES="IF:$ROOT/worldplay_0622/IF.json"
export TASK_IDS=IF003
```

每次明确重跑应使用新的 `GENIE3_RUN_ID`，从而得到新的时间戳目录。

## 6. OE 全量，然后 Landscape 42 条

业务顺序是先生成 OE 全条目，OE 完成后再生成 Landscape 42 条。不要并行占用同一个 Profile。

OE（默认端口 `9228`）：

```bash
cd "$CODE"
source ../api_keys.sh
GENIE3_CDP_URL=http://127.0.0.1:9228 \
GENIE3_RUN_ID="oe_all_$(date +%Y%m%d_%H%M%S)" \
./run_oe_all_loop.sh
```

OE 输出：

```text
$ROOT/result/genie3/OE001_YYYYMMDD_HHMMSS/
```

确认 OE 的 `COMPLETE` 后，再运行 Landscape。脚本默认使用已登录的 `9229`；若只使用
9228，可显式覆盖：

```bash
GENIE3_CDP_URL=http://127.0.0.1:9228 \
GENIE3_RUN_ID="landscape_gc_$(date +%Y%m%d_%H%M%S)" \
./run_landscape_gc_loop.sh
```

Landscape 数据与输出：

```text
$ROOT/worldplay_0622/GC_landscape.json
$ROOT/final-result/Landscape-GC/LS001_YYYYMMDD_HHMMSS/
```

批量脚本会跳过同一 run timestamp 下已有的成功视频，并最多重试 20 轮。日志分别在：

```text
$ROOT/result/genie3-logs/<run_id>/runner.log
$ROOT/final-result/Landscape-GC-logs/<run_id>/runner.log
```

## 7. 检查结果

检查某次单任务运行：

```bash
find "$ROOT/result/genie3" -maxdepth 2 -type f \
  \( -name 'GC004_native.*' -o -name 'GC005_native.*' \) -size +1000c -print
```

检查结果 JSON 的关键字段：

```bash
jq '{task_id,status,download_status,download_path,upload_image,create_fields,adaptive_corrections,rotation_loop_check_enabled,final_orientation_check_enabled}' \
  "$ROOT/result/genie3/GC004_YYYYMMDD_HHMMSS/result.json"
```

必须确认：

- `upload_image.source` 指向任务首帧图片。
- first-person 的 `create_fields.character` 是空字符串。
- Claude adaptive 请求无错误，HTTP 状态正常。
- `rotation_loop_check_enabled` 和 `final_orientation_check_enabled` 为 `false`。
- `*_native.mp4` 存在且非空。

## 8. 常见故障与恢复

- `auth_required`：在对应 CDP Profile 中重新登录 Genie3，再用新 run id 重跑失败项。
- `ready=False` 持续较久：创建有时接近 120 秒才可交互；在 runner 超时前不要手动中断。
- Claude preflight 非 200：检查办公网/内网地址、VPN/网络和 `api_keys.sh`，先恢复 Claude 再启动下一个任务。
- 未上传首帧或预览不对：停止该任务并重跑，不能接受无首帧结果。
- 下载阶段 30 到 90 秒无日志：可能仍在等待下载事件或文件 settle，不要过早终止。
- runner 意外退出：保持 Chrome Profile，使用相同批量 run id 可跳过该 run 中已有成功视频；明确重生成某个 case 时使用新 run id 且 `SKIP_EXISTING_SUCCESS=0`。
- 同一端口只运行一个任务进程。先测试一个任务且确认 Claude 响应正常，再启动下一个或批量队列。

## 9. 迁移检查清单

1. 项目与所有 JSON/首帧图片已同步到新机器。
2. Python 依赖和 Playwright Chromium 已安装。
3. `api_keys.sh` 已加载，Claude curl 与 preflight 均为 HTTP 200。
4. 9228 Profile 已启动并登录 Genie3，CDP `/json/version` 可访问。
5. 用一个 case 测试首帧上传、人物框规则、1 秒初始等待、adaptive 响应和视频下载。
6. 单 case 成功后再启动 OE 全量。
7. OE 完成后再启动 Landscape 42 条。
