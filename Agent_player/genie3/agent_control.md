# Genie3 Agent Control Notes

This note records how the agent currently controls Genie3 for the
`worldplay_0622/code/playwright_genie3` runner.

## Current Runner

Main files:

- `../player_genie3.py`: Playwright runner that opens Genie3, uploads the reference image, submits the prompt, performs keyboard actions, and downloads the video.
- `run_task.sh`: wrapper for running one or more `TASK_IDS`.
- `launch_chrome_cdp.sh`: starts Chrome/Chrome Dev with a CDP port.
- `api_keys.sh`: optional KIGRESS configuration for visual checks and adaptive correction.

The runner controls an already logged-in Chrome session through Chrome DevTools Protocol:

```bash
GENIE3_CDP_URL=http://127.0.0.1:9223
```

The browser must already be logged in to Genie3. If not logged in, the task result becomes:

```json
{"status": "auth_required"}
```

## Start Or Reattach Browser

Preferred start command:

```bash
cd $PLAYWORLD_CODE/Agent_player/genie3
./launch_chrome_cdp.sh
```

Check whether the port is alive:

```bash
curl http://127.0.0.1:9223/json/version
lsof -nP -iTCP:9223 -sTCP:LISTEN
```

If Chrome Dev is already running and a normal launch gets redirected or exits, force a new app instance:

```bash
rm -f "$HOME/.genie3_chrome_profile/SingletonLock" \
      "$HOME/.genie3_chrome_profile/SingletonCookie" \
      "$HOME/.genie3_chrome_profile/SingletonSocket"

open -na "Google Chrome Dev" --args \
  --user-data-dir="$HOME/.genie3_chrome_profile" \
  --remote-debugging-address=127.0.0.1 \
  --remote-debugging-port=9223 \
  --no-first-run \
  --no-default-browser-check \
  --disable-blink-features=AutomationControlled \
  "https://labs.google/fx/projectgenie/zh/tools/projectgenie/creation"
```

Only delete `Singleton*` files when the PID in `SingletonLock` is stale and Chrome for that profile is not running.

## Batch Run Command Used For GC/IF/OE

The completed run used:

```bash
RUN_ID="genie3_GC_IF_OE_20260703_171826"
WORLDPLAY_DIR="/Users/kaixinding/Documents/research/0316_worldmodelbenchmark/WorldModelBenchMark_latest/worldplay_0622"
SCRIPT_DIR="$WORLDPLAY_DIR/code/playwright_genie3"
OUT_ROOT="/Users/kaixinding/Documents/research/0316_worldmodelbenchmark/WorldModelBenchMark_latest/result/genie3"

cd "$SCRIPT_DIR"
source ../api_keys.sh 2>/dev/null || true

export GENIE3_CDP_URL="http://127.0.0.1:9223"
export GENIE3_RUN_ID="$RUN_ID"
export GENIE3_DATA_ROOT="$WORLDPLAY_DIR"
export GENIE3_OUT_ROOT="$OUT_ROOT"
export GENIE3_DATA_FILES="GC:GC.json,IF:IF.json,OE:OE.json"
export GENIE3_ALL_TASKS=1
unset TASK_IDS

export SKIP_EXISTING_SUCCESS=1
export SKIP_EXISTING_TERMINAL_FAILURE=0
export CREATE_WAIT_TIMEOUT_S=600
export POST_ACTION_WAIT_S=300
export GENIE3_ERROR_RETRIES=3

python3 "$SCRIPT_DIR/../player_genie3.py"
```

Output directory:

```text
/Users/kaixinding/Documents/research/0316_worldmodelbenchmark/WorldModelBenchMark_latest/result/genie3/genie3_GC_IF_OE_20260703_171826
```

Current verified status for `GC.json`, `IF.json`, and `OE.json`:

- GC: 48 downloaded
- IF: 42 downloaded
- OE: 52 downloaded
- Total: 142 non-empty mp4 files

`final_combined.json` has 131 tasks. Its `OE012` is not included in the completed `GC/IF/OE` run and still needs a logged-in Genie3 browser if that combined file must be fully covered.

## Single Task Or Resume

Use `run_task.sh` for ordinary single-task reruns:

```bash
cd $PLAYWORLD_CODE/Agent_player/genie3
GENIE3_CDP_URL=http://127.0.0.1:9223 ./run_task.sh GC001
```

Run multiple IDs:

```bash
./run_task.sh GC001,IF040,OE053
```

Resume a previous run id and skip existing successful outputs:

```bash
GENIE3_RUN_ID="genie3_GC_IF_OE_20260703_171826" \
GENIE3_OUT_ROOT="/Users/kaixinding/Documents/research/0316_worldmodelbenchmark/WorldModelBenchMark_latest/result/genie3" \
GENIE3_DATA_ROOT="/Users/kaixinding/Documents/research/0316_worldmodelbenchmark/WorldModelBenchMark_latest/worldplay_0622" \
GENIE3_DATA_FILES="GC:GC.json,IF:IF.json,OE:OE.json" \
SKIP_EXISTING_SUCCESS=1 \
GENIE3_ALL_TASKS=1 \
python3 ./../player_genie3.py
```

For `final_combined.json`, do not use `ALL:final_combined.json`; the parser only treats `GC:`, `IF:`, and `OE:` as labels. Use the plain filename:

```bash
GENIE3_DATA_FILES="final_combined.json" TASK_IDS="OE012" python3 ./../player_genie3.py
```

## Action Strategy

Each task has `action_sequence_steps`, usually atomic strings such as:

```text
hold(W,1350ms)
hold(W+D,900ms)
wait(450ms)
hold(RIGHT,1800ms)
interact(vase,1)
```

The runner parses:

- `hold(KEY,1350ms)`: keydown, hold for duration, keyup.
- `hold(KEY1+KEY2,900ms)`: press multiple keys together.
- `wait(450ms)`: no key action, just wait.
- `wait(0.45s)`: same, seconds unit.
- `wait:450ms` or `wait:2`: alternate wait syntax.
- `interact(object,1)`: interaction-style action if the task uses it.

Keyboard names are normalized through `KEY_MAP`. Common keys:

- `W/A/S/D`
- `LEFT/RIGHT/UP/DOWN`
- `U/D` for up/down camera style actions where the data uses those names

The agent does not continuously steer by default. It executes the scripted sequence, waits for Genie3 to expose the download button, then downloads the native mp4.

## Timing And Download Waits

Important waits:

- `CREATE_WAIT_TIMEOUT_S=600`: maximum time to wait for world creation/loading.
- `GENIE3_INITIAL_ACTION_DELAY_S=1`: after the world is interactive and focused, wait 1 second before the first action of each case.
- `POST_ACTION_WAIT_S=300`: maximum time after actions for the download button.
- `DOWNLOAD_EXPECT_TIMEOUT_MS=25000`: Playwright download event wait.
- `DOWNLOAD_JS_FALLBACK_TIMEOUT_MS=15000`: JS fallback wait.
- `DOWNLOAD_SETTLE_MS=15000`: wait for the file to finish settling.
- `DOWNLOAD_CLICK_RETRIES=3`: retry download click.

Observed normal pattern:

- World creation often takes 30-40 seconds.
- Download button often appears 66-75 seconds after actions.
- Some slow tasks can take 150+ seconds after actions and still succeed.

Do not interrupt just because there is no log for 30-90 seconds during download settle.

## Long Hold Early Stop

The runner has live hold early-stop support:

```bash
GENIE3_LIVE_HOLD_STOP_CHECK=1
GENIE3_LIVE_HOLD_CHECK_INTERVAL_MS=50
GENIE3_LIVE_HOLD_MIN_MS=0
GENIE3_LIVE_HOLD_MIN_APPLY_MS=600
GENIE3_LIVE_HOLD_MIN_REMAINING_MS=0
GENIE3_LIVE_HOLD_MAX_CHECKS=20
GENIE3_ADAPTIVE_PHASE_PROGRESS_CHECK=1
GENIE3_ADAPTIVE_PHASE_CHECK_EVERY=3
GENIE3_ADAPTIVE_EXTEND_HOLD=1
GENIE3_ADAPTIVE_EXTEND_HOLD_MIN_MS=2000
GENIE3_ROTATION_LOOP_CHECK=1
GENIE3_FINAL_ORIENTATION_CHECK=1
```

Intended behavior:

1. Start holding the requested key.
2. Immediately send the first screenshot after keydown and poll the in-flight decision every 50 ms, with at most 20 checks per hold.
3. Claude may keep, stop, or extend the same held key by at most 2400 ms total, and may return up to two correction actions for execution after keyup.
4. If enough, send keyup early and optionally skip the remaining repeated actions in the phase.
5. Check phase progress every three logical actions, and run phase-end extension only after the original phase has executed for at least 2000 ms.
6. Enable rotation-loop and final-orientation checks so Claude can append turn corrections when needed.
7. Dispatch every key through Playwright, CDP, and JavaScript key events.

This solves the problem: if the agent has already reached the desired position but the scripted hold duration is too long, it can release early.

Minimum timing guard:

- Screenshots may be sent to the agent immediately, even when the current hold has lasted less than `600ms`, because the agent-side judgment has latency.
- Do not apply an early-stop decision before the current hold total age has reached `600ms`; if the agent says stop earlier, defer the keyup until `GENIE3_LIVE_HOLD_MIN_APPLY_MS` measured from keydown.
- Remaining hold time does not need a `600ms` guard. If the hold total age is old enough, it is fine to stop even when the scripted hold has less than `600ms` left.
- The main guard is against pausing immediately at the beginning of a hold; after the hold has lasted `600ms`, agent-approved stop can be applied.

Current caveat:

- Basic scripted actions work without KIGRESS.
- Early-stop visual judgment requires valid `KIGRESS_BASE_URL`, `KIGRESS_API_KEY`, and `KIGRESS_USER_KEY`.
- In the latest run, KIGRESS was not effectively active because the configured URL was empty or missing `http://` / `https://`.
- Logs showed errors like:

```text
UnsupportedProtocol("Request URL is missing an 'http://' or 'https://' protocol.")
```

So the latest GC/IF/OE run used fixed hold durations, not real visual early release.

## Adaptive Correction

Adaptive correction is controlled by:

```bash
GENIE3_ADAPTIVE_CORRECTION=1
GENIE3_ADAPTIVE_MAX_ACTIONS=3
```

It can ask KIGRESS to inspect screenshots for final orientation or rotation-loop checks. Like live hold early-stop, it requires working KIGRESS configuration. If KIGRESS is not configured, the runner logs the error and continues with normal scripted actions.

## Perspective Fields

When Genie3 shows separate environment and character/person fields:

- `first-person`: fill the environment field from the task image caption/prompt context, and leave the character/person field empty.
- `third-person`: fill the environment field the same way, and fill the character/person field with the leading subject from the task prompt, such as `the man`, `a horse`, or the first prompt clause when no simpler subject is detected.
- Every case must upload its prepared first-frame/reference image before prompt submission, including third-person cases. A text-only third-person submission is not allowed.

This is handled in `build_genie3_fields()` by setting an empty `character` for first-person and using `central_character_from_prompt(task["prompt"])` for third-person.

## Wait And Observe

When the task prompt contains `wait and observe` (case-insensitive), the runner uses a dedicated no-input path:

- Do not focus/click the world canvas.
- Do not execute any dataset keyboard or wait action.
- Leave the interactive world untouched for `GENIE3_WAIT_AND_OBSERVE_S` seconds, defaulting to 60 seconds.
- Do not press Escape. Keep the world untouched until the Genie3 session ends naturally, then download the video.

The task `result.json` records `wait_and_observe_task`, `wait_and_observe_s`, `wait_and_observe_actual_s`, and an empty `executed_actions` list.

## Output Structure

Task outputs are written directly under `GENIE3_OUT_ROOT`. The run timestamp is taken from the final `YYYYMMDD_HHMMSS` component of `GENIE3_RUN_ID`; a four-digit time such as `20260710_1740` is normalized to `20260710_174000`.

```text
<GENIE3_OUT_ROOT>/
  GC001_20260710_174000/
    result.json
    GC001_native.mp4
    GC001_input.jpg
    GC001_upload_landscape.jpg
  IF001_20260710_174000/
  OE001_20260710_174000/
```

There are no run-ID or perspective parent directories under the output root. Run-level files such as `summary.json`, `runner.log`, and loop status are stored under `<GENIE3_RUN_LOG_ROOT>/<run_id>/`, where `GENIE3_RUN_LOG_ROOT` defaults to a sibling directory named `<output-root>-logs`.

`result.json` contains the task status, result URL, download status, download path, and action count.

Successful download status is usually:

```json
{
  "status": "downloaded",
  "download_status": "downloaded_from_downloads"
}
```

## Verification Commands

Count successful mp4 files:

```bash
find /Users/kaixinding/Documents/research/0316_worldmodelbenchmark/WorldModelBenchMark_latest/result/genie3/genie3_GC_IF_OE_20260703_171826 \
  -name "*.mp4" -type f -size +0c | wc -l
```

Check source coverage:

```bash
python3 - <<'PY'
import json
from pathlib import Path

base = Path("/Users/kaixinding/Documents/research/0316_worldmodelbenchmark/WorldModelBenchMark_latest/worldplay_0622")
run = Path("/Users/kaixinding/Documents/research/0316_worldmodelbenchmark/WorldModelBenchMark_latest/result/genie3/genie3_GC_IF_OE_20260703_171826")
existing = {p.parent.name for p in run.rglob("result.json")}

for name in ["GC.json", "IF.json", "OE.json", "final_combined.json"]:
    data = json.loads((base / name).read_text())
    tasks = data if isinstance(data, list) else next((v for v in data.values() if isinstance(v, list)), [])
    ids = [str(t.get("task_id") or t.get("id") or t.get("task") or i) for i, t in enumerate(tasks, 1)]
    missing = [task_id for task_id in ids if task_id not in existing]
    print(name, "count", len(ids), "missing", len(missing), " ".join(missing[:20]))
PY
```

Check disk:

```bash
df -h /Users/kaixinding/Documents/research/0316_worldmodelbenchmark/WorldModelBenchMark_latest/result/genie3
du -sh /Users/kaixinding/Documents/research/0316_worldmodelbenchmark/WorldModelBenchMark_latest/result/genie3/genie3_GC_IF_OE_20260703_171826
```

## Known Failure Modes

### `auth_required`

Cause: CDP browser is not logged into Genie3.

Fix: open the CDP browser manually, log in to Genie3, then rerun the task.

### `connect ECONNREFUSED 127.0.0.1:9223`

Cause: no Chrome process is listening on that CDP port.

Fix: restart Chrome CDP and verify `/json/version`.

### `socket hang up` during `connect_over_cdp`

Cause: Chrome started but exited/crashed while Playwright connected.

Fixes to try:

- remove stale `Singleton*` files if the referenced PID is gone
- use `open -na "Google Chrome Dev" --args ...` to force a new instance
- use a different profile only if it is known to be logged in

### KIGRESS `UnsupportedProtocol`

Cause: `KIGRESS_BASE_URL` is empty or lacks `http://` / `https://`.

Impact: adaptive checks and live hold early-stop are disabled in practice. Scripted keyboard actions and downloads can still work.

### Slow `result.json` reads

Some macOS filesystem reads under the result directory can be unexpectedly slow. Use direct `find` counts for mp4 verification, and use per-file timeouts when rebuilding summaries.

## Practical Agent Loop

1. Verify CDP browser is alive and logged in.
2. Set run id and output root.
3. Run a batch with `SKIP_EXISTING_SUCCESS=1`.
4. Watch logs every 30 seconds.
5. Do not interrupt during normal post-action download waits unless the page errors or disk is full.
6. After exit, verify non-empty mp4 count and missing task IDs.
7. Clean only failed artifacts created by the current attempt; do not delete successful outputs.
