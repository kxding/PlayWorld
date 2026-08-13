# HappyOyster Agent 控制说明

这份文档说明目前 HappyOyster runner 如何用 agent 控制生成后的交互世界，并对齐 Genie3 的控制方式。

核心结论：HappyOyster 和 Genie3 在“世界已经生成并可交互”之后使用同一套控制契约。差别只在站点自动化部分，例如登录、上传起始图、填写 prompt、提交生成、下载视频；这些步骤不属于 agent 的 embodied control。

整体流程：

1. 通过 Playwright CDP 连接一个已经登录 HappyOyster 的浏览器。
2. 用 image + prompt 创建世界。
3. 等待生成结果进入可交互页面。
4. 聚焦可见的世界视口，也就是 `canvas` 或 `video`。
5. 按 `action_sequence_steps` 发送真实键盘事件：`keyboard.down` -> 等待 `hold_ms` -> `keyboard.up`。
6. 保存 `result.json`、截图和 HappyOyster 原生下载的视频。

runner 不调用 HappyOyster 私有 API，也不模拟高级游戏状态。它和 Genie3 一样，是在真实浏览器页面里控制一个已经生成出来的 interactive world。

## Browser/CDP 设置

HappyOyster 使用已登录的 Chrome Dev session。当前约定端口是 `9225`，避免和 Genie3 常用的 `9223` 冲突。

```bash
PROFILE="/tmp/happyoyster_chrome_dev_open_profile_9225"
mkdir -p "$PROFILE"
open -na "Google Chrome Dev" --args \
  --user-data-dir="$PROFILE" \
  --remote-debugging-address=127.0.0.1 \
  --remote-debugging-port=9225 \
  --no-first-run \
  --no-default-browser-check \
  --disable-sync \
  --disable-blink-features=AutomationControlled \
  "https://www.happyoyster.com/create"
```

检查端口：

```bash
curl http://127.0.0.1:9225/json/version
```

如果页面显示登录态丢失，需要先在这个 Chrome Dev 窗口里手动登录 HappyOyster。runner 默认浏览器已经有有效 cookie，并且账号有可用 credits。

## 运行命令

runner 文件：

```text
$PLAYWORLD_CODE/Agent_player/happyoyster/../player_happyoyster.py
```

典型运行环境：

```bash
WORLDPLAY_DIR="/Users/kaixinding/Documents/research/0316_worldmodelbenchmark/WorldModelBenchMark_latest/worldplay_0622"
OUT_ROOT="/Users/kaixinding/Documents/research/0316_worldmodelbenchmark/WorldModelBenchMark_latest/result/happyoyster"
TASK_FILE="/Users/kaixinding/Documents/Codex/2026-07-03/users-kaixinding-documents-research-0316-worldmodelbenchmark-2/work/happyoyster_GC_IF_OE_combined.json"

HAPPYOYSTER_CDP_URL="http://127.0.0.1:9225" \
HAPPYOYSTER_DATA_ROOT="$WORLDPLAY_DIR" \
HAPPYOYSTER_OUT_ROOT="$OUT_ROOT" \
HAPPYOYSTER_TASK_FILE="$TASK_FILE" \
HAPPYOYSTER_RUN_ID="happyoyster_GC_IF_OE_20260703_213609" \
HAPPYOYSTER_ALL_TASKS="1" \
SKIP_EXISTING_SUCCESS="1" \
CREATE_WAIT_TIMEOUT_S="600" \
DOWNLOAD_FILE_WAIT_S="180" \
python3 "$WORLDPLAY_DIR/code/playwright_happyoyster/../player_happyoyster.py"
```

`SKIP_EXISTING_SUCCESS=1` 用于断点续跑。只有满足下面条件的任务才会被跳过：

- `result.json` 中 `status` 是 `actions_completed`。
- `download_status` 是 `downloaded` 或 `downloaded_from_downloads`。
- `download_path` 指向的视频文件真实存在。

## 输入数据

HappyOyster runner 接受和 Genie3 相同的 task contract：

- `task_id`
- `prompt`
- `image_path`
- `image_caption`
- `perspective`
- `action_sequence`
- `action_sequence_steps`

当前 GC/IF/OE 任务是把下面三个文件拼接成 combined task file：

```text
worldplay_0622/GC.json
worldplay_0622/IF.json
worldplay_0622/OE.json
```

图片路径相对 `HAPPYOYSTER_DATA_ROOT` 解析。

## 和 Genie3 的控制等价性

HappyOyster 与 Genie3 的等价点在于：一旦世界可交互，两者都只执行同一种低层控制动作。

- 都先聚焦 interactive viewport。
- 都把 `action_sequence_steps` 解析成原子动作。
- 都用真实键盘事件控制世界。
- 都尊重每个 action step 自己的 `hold_ms`。
- 都把 `wait(...)` 当作纯等待，不发送键盘事件。
- 都在任务结果里记录实际执行过的动作。

因此 HappyOyster 没有单独的 agent policy。它只是多了一层 HappyOyster 站点 UI glue，用来进入和离开交互世界。

## 什么时候调用外部 Agent

当前 HappyOyster runner 正常 benchmark 运行时不会调用 Claude 或其他 LLM agent。它是 deterministic action-sequence runner：读取 `action_sequence_steps`，等世界可交互，然后严格执行这些步骤。

如果后续要加入 Claude 这样的外部 agent，调用窗口必须和 Genie3 一样，只能放在 interactive world control 阶段：

```text
create world -> wait for interactive world -> focus viewport -> optional agent observe/decide -> execute keyboard action -> optional agent observe/decide -> ... -> wait result/download
```

不要在这些阶段调用 agent：

- 登录。
- 上传起始图。
- 填写 create prompt。
- 等待 submit/generation。
- 下载视频。
- 归一化 `result.json` 或文件名。

这些是网页自动化，不是世界控制。agent 只应该在 `wait_for_interactive(...)` 已经 ready，并且 `focus_world(...)` 能够点击到可见 `canvas` 或 `video` 后介入。

推荐介入点：

- 第一条动作之前：agent 先观察生成世界，再选择第一个原子动作。
- 两个原子动作之间：用于 adaptive control。
- recovery 时：例如焦点丢失、页面离开 `/explore`、世界疑似卡住、目标物没有出现。
- 不要在单个 hold 动作中间介入。例如 `hold(W,1350ms)` 必须保持一次完整、不中断的 key down/up。

为了 benchmark 可复现，默认优先使用固定 `action_sequence_steps`。Claude/LLM agent 只建议用于明确的 adaptive run 或 debug run。

## Agent 怎么干涉

外部 agent 不应该直接控制浏览器。它只返回受限 DSL，runner 仍然是唯一执行动作的组件。

允许的动作形式示例：

```text
hold(W,1350ms)
hold(W+D,900ms)
hold(Right,1800ms)
wait(450ms)
interact(door,1)
```

推荐循环：

1. 用 `focus_world(page)` 聚焦世界视口。
2. 截取 observation，通常包括 screenshot 和 task metadata：
   - `task_id`
   - original `prompt`
   - `image_caption`
   - `perspective`
   - remaining goal
   - previous executed actions
3. 向 agent 请求一个 next atomic DSL step，或一个很短的 bounded step list。
4. 用和 `action_sequence_steps` 相同的 parser 校验返回内容。
5. 用 `press_action(page, action)` 执行。
6. 在 `result.json` 中记录干涉信息，例如：

```json
{
  "agent_interventions": [
    {
      "index": 1,
      "observation_path": "agent_obs_001.jpg",
      "agent": "claude",
      "decision": "hold(Right,1800ms)",
      "executed_action": {
        "type": "key",
        "keys": ["right"],
        "hold_ms": 1800
      }
    }
  ]
}
```

agent 不允许发明浏览器 selector，不允许点击 HappyOyster UI，不允许下载文件。它只选择世界内控制动作；Playwright runner 负责执行。

## Agent 干涉延时

延时规则保持和 Genie3 一致。关键点是：模型调用耗时不应该改变 world action 的语义，DSL 里的 `hold_ms` 永远是准确信号。

代码里已经支持和 Genie3 同风格的可选动态控制。默认关闭，固定 benchmark 仍然只执行 `action_sequence_steps`。需要 Claude/KIGRESS 介入时启用：

```bash
export KIGRESS_BASE_URL="https://..."
export KIGRESS_API_KEY="..."
export KIGRESS_USER_KEY="..."
export KIGRESS_MODEL="claude-haiku-4-5-20251001"

export HAPPYOYSTER_ADAPTIVE_CORRECTION=1
export HAPPYOYSTER_LIVE_HOLD_STOP_CHECK=1
export HAPPYOYSTER_ADAPTIVE_EXTEND_HOLD=1
export HAPPYOYSTER_LIVE_HOLD_REQUEST_MIN_MS=0
export HAPPYOYSTER_LIVE_HOLD_STOP_MIN_MS=600
export HAPPYOYSTER_LIVE_HOLD_MIN_REMAINING_MS=0
```

对应 Genie3 语义：

- 延时调用 agent：长按一开始就可以问 agent，因为 agent 判断本身有网络和模型延迟。默认 `HAPPYOYSTER_LIVE_HOLD_REQUEST_MIN_MS=0`，也兼容用 `GENIE3_LIVE_HOLD_MIN_MS=0` 表达同一件事。runner 在 keydown 后立刻截图并异步请求 agent。
- 动态缩短：长按过程中每 `HAPPYOYSTER_LIVE_HOLD_CHECK_INTERVAL_MS=200` 检查一次 pending agent 结果。若返回 `stop_current_hold=true` 且 confidence 为 `medium/high/certain`，runner 会缓存这个 stop 建议，但只有当 hold 总年龄满足 `HAPPYOYSTER_LIVE_HOLD_STOP_MIN_MS=600` 时才真正 `keyboard.up`。也就是说 agent 可以早判断，keyup 不会早于 600ms。
- 剩余时间不再限制 stop：默认 `HAPPYOYSTER_LIVE_HOLD_MIN_REMAINING_MS=0`，也兼容 `GENIE3_LIVE_HOLD_MIN_REMAINING_MS=0`。即使 hold 剩余不到 600ms，只要 agent 已经判断需要停，也可以在满足 stop 最小年龄后停。
- 动态增长：一个 dataset phase 结束后，如果该 hold 时长不少于 `HAPPYOYSTER_ADAPTIVE_EXTEND_HOLD_MIN_MS=2000`，runner 截图请求 agent 判断是否需要继续按同一组 key。agent 通过 `extend_current_hold_ms` 返回额外时长，上限 `HAPPYOYSTER_ADAPTIVE_EXTEND_HOLD_MAX_MS=2400`，轮数由 `HAPPYOYSTER_ADAPTIVE_EXTEND_HOLD_MAX_ROUNDS=1` 控制。
- agent 仍不直接操作浏览器；它只返回 JSON。Playwright runner 负责执行 key down/up。

推荐 timing：

- 世界变为 interactive 后：等待 `1500ms` 再做第一次控制。当前 HappyOyster runner 已经在 `wait_for_interactive(...)` 后这样做。
- 每次 observation screenshot 前：聚焦 viewport 后等待 `300-800ms`，让画面稳定。
- 每个非 wait 动作后：保持现有动作节奏。当前 HappyOyster 使用 `ACTION_INTERVAL_S = 0.85`，key hold 后额外 sleep 为 `max(0, 0.85s - hold_duration_s)`。
- 对显式等待：严格遵守 DSL，例如 `wait(450ms)` 就 sleep `450ms`。
- agent 返回 decision 后：校验通过即可执行，不额外加固定延时。
- 全部 action 完成后：等待 `8000ms`，再查找结果页或下载入口。

推荐 adaptive-agent loop：

```text
wait_for_interactive
sleep 1500ms
for each agent step:
  focus_world
  sleep 300-800ms
  screenshot
  call agent
  validate DSL step
  press_action
  sleep max(0, 850ms - hold_ms)
after final action:
  sleep 8000ms
  wait/download result
```

recovery 场景可以使用更长 settle delay：

- 页面导航或关闭 modal 后：`1000-2000ms`。
- 疑似 world reload 后：`2000-3000ms`。
- 如果页面已经不在 `/explore`，或者出现 credits/login 错误，应停止该任务并标记失败，不要反复调用 agent。

## Action Parsing

两套 runner 都读取机器可解析的 `action_sequence_steps`，例如：

```json
[
  "hold(W,1350ms)",
  "hold(D,1350ms)",
  "wait(450ms)",
  "hold(Right,1800ms)"
]
```

HappyOyster runner 会把这些 step 展开成内部 action：

- `type: "key"` 表示键盘 hold。
- `type: "wait"` 表示纯等待。
- `keys` 使用和 Genie3 同风格的 key map：`w/a/s/d`、arrow keys、`space/jump`、interaction aliases。
- `hold_ms` 来自每个 step，不使用固定全局时长。

## Focus

每次发送 key action 前，runner 都会先点击可见的 `canvas` 或 `video` 中心点：

```text
focus_world(page) -> find_world_element(page) -> click center of canvas/video
```

这和 Genie3 一样：agent 先把键盘焦点交给生成出来的交互世界，再发送键盘事件。

## Keyboard Events

每个 key action 都使用 Playwright 的低层键盘事件：

```text
page.keyboard.down(key)
wait hold_ms
page.keyboard.up(key)
```

多键组合按顺序 key down，反序 key up。runner 会在 `result["executed_actions"]` 记录 index、elapsed time、keys、raw step 和 hold duration。

## Timing

执行固定 action sequence 时，HappyOyster 保持和 Genie3 相同的 timing 语义：

- hold duration 来自当前 step。
- 非 wait 动作之间保留短间隔。
- `wait(...)` 只 sleep，不发送任何 key。

这意味着 HappyOyster 不使用不同的控制策略。差异只在进入世界前和下载结果后的站点 UI 处理。

## 360 度旋转保护

对于目标中明确包含 `360`、`full circle` 或同义描述的原地旋转段，不能因为起始物体再次出现在画面中就立即停止。同一物体可能提前重现，但它在画面中的位置、比例和相机朝向仍与起始帧明显不同，此时不代表已经完成 360 度闭环。

当前执行规则：

- `Left/Right` 旋转段必须先完整执行数据集给出的计划长按时间；Claude 可以从 keydown 开始观察和思考，但计划时长结束前返回的 `stop` 不会触发 `keyup`。
- 完成数据集旋转段后，runner 固定沿相同方向补按 `HAPPYOYSTER_ROTATION_EXTRA_TURN_UNITS=2` 个按键单位。
- 当前单按键单位是 `650ms`，因此默认固定补按总时长是 `1300ms`。
- 固定补按之后再运行闭环和最终朝向检查。只有起始参照物的位置、构图和观看方向都接近起始帧，才认为旋转完成。
- 该保护同样作用于“先移动、再原地旋转、再继续移动”的混合任务；普通左右查看、180 度转向和使用 `W/A/S/D` 绕物体移动不会自动补按。

可配置补按数量：

```bash
export HAPPYOYSTER_ROTATION_EXTRA_TURN_UNITS=2
```

设为 `0` 可关闭固定补按，但仍会保留“原始旋转长按不得被 Claude 提前终止”的保护。

## GC007 商场入口距离

GC007 需要走到 Primemall 入口，并让入口上方的标牌离开当前视野。HappyOyster 中原始 `W` 距离不足，因此采用任务级固定补偿：

- 原始 `W` 必须完整执行，然后继续按 `W` 三个单位，即额外前进 `1950ms`。
- 原始 `S` 必须完整执行，然后继续按 `S` 三个单位，以抵消额外前进距离并返回起点。
- 两段固定补偿分别以 `gc007_forward_fixed_extra` 和 `gc007_return_fixed_extra` 写入 `executed_actions`。

可分别配置前进和返回补偿：

```bash
export HAPPYOYSTER_GC007_FORWARD_EXTRA_UNITS=3
export HAPPYOYSTER_GC007_RETURN_EXTRA_UNITS=3
```

## HappyOyster 特殊 UI 处理

下面这些是 HappyOyster-specific，但都发生在共享的 agent-control phase 之前或之后。

- 模式选择：
  - `first-person` 映射到 HappyOyster `Adventure`。
  - `third-person` 映射到 HappyOyster `Directing`。
- Camera view：
  - runner 从 HappyOyster UI 选择 `First person view` 或 `Third person view`。
- Start frame upload：
  - runner 通过 `Start frame` file chooser 上传源图，必要时使用隐藏 file input fallback。
- Prompt fill：
  - runner 等待可见 textarea，填写 create prompt；如果前端状态没有被普通 typing 更新，则用 JS value-setter fallback。
- Submit：
  - runner 优先点击 textarea 旁边的圆形 submit button，再 fallback 到 Enter。
- Prompt sanitization：
  - 某些 storefront 词可能触发 HappyOyster 静默拒绝生成。runner 只清洗 HappyOyster 的 `create_prompt` 文本，原始 task 字段仍保存在 `result.json`。
- Download：
  - HappyOyster 有时点击圆形 Download button 后会直接开始浏览器下载，不一定出现 modal confirm。runner 会同时监控 output folder 和 `~/Downloads`，等待稳定的新视频文件，并改名为 `<task_id>_native.mp4`。

这些 UI glue 不改变动作控制语义，只负责把 agent 带进和带出 interactive world。

## 输出目录

当前 run id：

```text
happyoyster_GC_IF_OE_20260703_213609
```

输出目录：

```text
/Users/kaixinding/Documents/research/0316_worldmodelbenchmark/WorldModelBenchMark_latest/result/happyoyster/happyoyster_GC_IF_OE_20260703_213609/
```

每个任务按视角分目录：

```text
first_person/<task_id>/
third_person/<task_id>/
```

成功任务的典型文件：

- `<task_id>_input.jpg`
- `<task_id>_upload_landscape.jpg`
- `create_ready.jpg`
- `after_actions.jpg`
- `result_page_before_download.jpg`
- `<task_id>_native.mp4`
- `result.json`

## 续跑与失败处理

runner 支持安全重启。续跑时使用同一个 `HAPPYOYSTER_RUN_ID`，并保留 `SKIP_EXISTING_SUCCESS=1`。已经成功并有下载视频的任务会跳过，失败或未完成任务会重试。

常见失败状态：

- `insufficient_credits`：HappyOyster credits 不足。应停止运行，补充 credits 后再续跑。
- `login_required`：浏览器 profile 登录态丢失。需要手动登录后再续跑。
- `explore_not_ready`：提交后没有进入世界。可以重试；如果同一任务反复失败，检查 `create_ready*.jpg` 和 prompt sanitization。
- `download_timeout`：世界完成但没有检测到稳定视频文件。检查 task output folder 和 `~/Downloads`，可能有站点原始命名的 mp4 需要归一化。

## 当前运行状态

当前主 run：

```text
happyoyster_GC_IF_OE_20260703_213609
```

这个 run 已经多次用同一 run id 续跑，已有成功任务会正确跳过。上次检查时，GC 前段到后段已有一批原生视频成功生成，后续任务因为 HappyOyster 再次返回 `insufficient_credits` 而停止。

credits 可用后，用同一个 run id 和上面的命令继续即可。
