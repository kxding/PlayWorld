# PlayWorldBench: Gemini Metrics + Agent Control

This repository contains two complete, independent parts:

- Gemini video scoring and aggregation for:

> **Gemini score averages · Fail = 1 · OE split**

- `PlayWorldEngine` browser control for HappyOyster and Genie3, including task
  execution, screenshots, durable result recording, retries, Agent decisions,
  and `keep_action`, `stop_action`, `extend_action`, `correct_action`.

The Hugging Face `datasuite` remains a separate repository/folder. Task IDs and
assets retain their original `GC*`, `IF*`, and `OE*` names; the Agent code does
not rename IF/OE records to GC IDs.

## Verified reference table

The aggregator was tested against the cached Gemini results and exact video
manifest embedded in `final-result/index.html`. It reproduces every displayed
value and every `n=` count:

| Method | GC | IF | In-sight Evolution | Out-of-sight Evolution | Overall |
| --- | ---: | ---: | ---: | ---: | ---: |
| Genie3 | 2.74 (n=37/48) | 2.40 (n=43/46) | 1.51 (n=30/30) | 1.81 (n=39/43) | 2.12 |
| LingBot-World | 2.11 (n=28/48) | 2.23 (n=38/50) | 1.33 (n=30/30) | 1.43 (n=36/43) | 1.78 |
| LingBot-World-Infinity | 2.04 (n=28/48) | 2.13 (n=40/47) | 1.95 (n=30/30) | 1.16 (n=40/43) | 1.82 |
| HYWorld2 | 2.14 (n=23/48) | 2.06 (n=35/50) | 1.13 (n=18/30) | 1.09 (n=16/43) | 1.61 |
| HappyOyster | 2.54 (n=30/47) | 2.15 (n=43/46) | 1.47 (n=30/30) | 1.54 (n=35/43) | 1.92 |
| SANA_WM | 1.72 (n=30/48) | 1.89 (n=44/50) | 1.13 (n=30/30) | 1.16 (n=39/43) | 1.48 |
| gamecraft2 | 1.62 (n=12/48) | 1.52 (n=39/50) | 1.21 (n=30/30) | 1.31 (n=35/43) | 1.42 |
| hy_worldplay | 1.12 (n=7/48) | 1.63 (n=40/50) | 1.01 (n=22/30) | 1.08 (n=13/43) | 1.21 |
| matrixgame3_native | 1.30 (n=18/48) | 1.25 (n=44/50) | 1.00 (n=30/30) | 1.00 (n=34/43) | 1.14 |

This equality is an exact aggregation check using the existing cached Gemini
responses. A new Gemini call is not guaranteed to return byte-identical scores
because model versions and multimodal inference may vary.

## Exact table policy

- GC: use the raw 1–5 Gemini score when the trajectory gate is Pass/Partial;
  otherwise use 1.
- IF: first-person cases retain the raw score. Third-person cases retain the raw
  score for Pass/Partial and use 1 for Fail.
- In-sight Evolution: retain the raw score without an instruction gate.
- Out-of-sight Evolution: retain the raw score for Pass/Partial and use 1 for
  Fail.
- Missing videos contribute 1.
- GC `identity_id` has weight 2 when recomputing cached category averages.
- Overall is the equal-weight mean of GC, IF, In-sight, and Out-of-sight means.
- OE is split using the fixed 30-task In-sight and 43-task Out-of-sight lists in
  `oe_split_averages.py`.

## Sampling sent to Gemini

| Stream | FPS | Cell | Grid | Sheet | Use |
| --- | ---: | ---: | ---: | ---: | --- |
| Primary | 10 | 384×216 | 5×5 | 1920×1080 | trajectory, motion, continuity |
| Detail | 0.5 | 800×450 | 2×2 | 1600×900 | identity, texture, material, small defects |

Both streams cover the complete video and are included in the generated context.
Contact sheets use JPEG quality 70 with 4:2:0 subsampling; this changes only the
transport encoding, not the FPS, cell resolution, grid, ordering, or coverage.

## Repository layout

```text
playworld_code/
├── playworldbench/
│   ├── agent/
│   │   ├── base.py              # PlayWorldEngine public browser API
│   │   ├── happyoyster.py       # HappyOyster page adapter
│   │   ├── genie3.py            # Genie3 page adapter
│   │   ├── harness.py           # retries, execution, screenshots, results
│   │   ├── policies.py          # keep/scripted/Gemini Agent policies
│   │   └── recording.py
│   ├── agent_cli.py
│   ├── metrics/
│   │   ├── dual_sampling.py
│   │   ├── gemini_metrics.py
│   │   ├── instruction_gate.py
│   │   └── oe_split_averages.py
│   └── cli/
│       ├── evaluate.py
│       └── aggregate.py
├── configs/decisions.example.json
├── scripts/
│   ├── launch_chrome_cdp.sh
│   └── run_agent.sh
├── tests/
│   ├── test_agent_harness.py
│   └── test_metrics.py
├── pyproject.toml
└── requirements.txt
```

The external Hugging Face `datasuite` remains outside this repository.

## Installation

```bash
brew install ffmpeg
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
export DATA_SUITE=/absolute/path/to/datasuite
```

The supplied macOS launcher attaches to Google Chrome over CDP. If Chrome is in
a different location, set `CHROME_BIN` before running it.

## Credential input

```bash
export GEMINI_API_KEY="your_api_key"
export GEMINI_MODEL="gemini-3.1-pro-preview"
```

For an authorized Gemini-compatible gateway, keep secrets in environment
variables rather than source code:

```bash
export GEMINI_API_KEY="dummy-or-provider-api-key"
export GEMINI_BASE_URL="https://gateway.example.com/path"
export GEMINI_HEADERS_JSON='{"x-api-key":"...","x-user-key":"..."}'
```

`GEMINI_BASE_URL` must be the base URL expected by the Google GenAI SDK, not a
shell `curl` command. Credentials and headers are not accepted in task JSON,
prompts, contexts, or output artifacts. `.env` is ignored by Git, and the code
does not load it automatically.

## Agent Control

`PlayWorldEngine` is the public control interface used by PlayWorldBench. It is
not a fork of the Playwright package: Playwright remains the internal browser
driver, while `PlayWorldEngine` provides world-model operations such as image
upload, world generation, observation, keyboard control, recovery, and safe key
release. `HappyOysterEngine` is the HappyOyster page adapter for that interface.

The following uses HappyOyster as the concrete example. Other cases, including
HYWorld2, Genie3, and additional world-model systems, follow the same control
workflow; only the corresponding `PlayWorldEngine` adapter and model-specific
page selectors or readiness checks need to be supplied.

For every planned benchmark action, the harness takes a screenshot, asks the
selected Agent policy for a decision, executes the resolved action, takes an
after-action screenshot, and immediately records the event. The same harness can
therefore run a fixed action trace or close the loop with a visual Agent.

```text
task JSON + reference image
          |
          v
HappyOysterEngine: upload image -> submit prompt -> wait for world
          |
          v
observe screenshot -> Agent decision -> execute/release keys -> record result
          ^                                                      |
          +--------------------- next planned action -------------+
```

### 1. Prepare one HappyOyster task

The dataset file is a JSON array. A minimal task record is:

```json
[
  {
    "task_id": "GC001",
    "prompt": "Move forward and turn left to inspect the scene.",
    "image_path": "gc/images/GC001.jpg",
    "action_sequence_steps": [
      "hold(W,1000ms)",
      "wait(500ms)",
      "hold(A,750ms)"
    ],
    "image_caption": "A navigable outdoor scene",
    "perspective": "first-person"
  }
]
```

Required fields are `task_id`, `prompt`, `image_path`, and
`action_sequence_steps`. An action sequence may be a JSON list as above or one
semicolon-separated string. Supported expressions are `hold(KEY,Nms)` and
`wait(Nms)`. The controller accepts `W/A/S/D`, arrow keys, and `WAIT` for Agent
corrections. `image_path` is resolved relative to `--datasuite-root`.

Use the original suite IDs and filenames: for example, an IF record remains
`IF001` and an OE record remains `OE001`; Agent Control does not convert them to
GC IDs.

### 2. Start Chrome and sign in to HappyOyster

```bash
chmod +x scripts/*.sh
scripts/launch_chrome_cdp.sh
```

This starts a separate Chrome profile with the DevTools endpoint at
`http://127.0.0.1:9222`. In that Chrome window:

1. Open the HappyOyster web application.
2. Complete login or any human verification.
3. Leave the HappyOyster tab open.

The harness attaches to this browser session. It does not launch an anonymous
session and deliberately does not close the user's Chrome window when a run
finishes. A different Chrome path, profile, or port can be supplied with
`CHROME_BIN`, `PLAYWORLD_PROFILE_DIR`, and `CDP_PORT`.

### 3. Verify browser control with the fixed benchmark plan

Start with the `keep` policy. It uses every action from the dataset unchanged
and does not call an Agent model:

```bash
playworld-agent \
  --engine happyoyster \
  --url 'https://your-happyoyster-page.example' \
  --cdp-url http://127.0.0.1:9222 \
  --dataset "$DATA_SUITE/gc/data.json" \
  --datasuite-root "$DATA_SUITE" \
  --task-id GC001 \
  --policy keep \
  --output-root runs/happyoyster
```

The HappyOyster adapter performs four page-level operations:

1. Find the file input and upload the task image.
2. Fill the prompt field and click **Generate**.
3. Wait up to five minutes for the interactive canvas.
4. Focus the page and send timed keyboard actions.

The built-in adapter recognizes common English/Chinese Generate buttons and
standard file, textarea, content-editable, and canvas elements. If a deployed
HappyOyster page uses different controls, update only the selector tuples in
`playworldbench/agent/happyoyster.py`; the harness and policies do not need to
change.

### 4. Enable screenshot-based Agent decisions

Set Gemini credentials through environment variables, then select the `gemini`
policy:

```bash
export GEMINI_API_KEY="your_api_key"
export GEMINI_MODEL="gemini-3.1-pro-preview"

playworld-agent \
  --engine happyoyster \
  --url 'https://your-happyoyster-page.example' \
  --cdp-url http://127.0.0.1:9222 \
  --dataset "$DATA_SUITE/gc/data.json" \
  --datasuite-root "$DATA_SUITE" \
  --task-id GC001 \
  --policy gemini \
  --gemini-model "$GEMINI_MODEL" \
  --max-extension-ms 5000 \
  --output-root runs/happyoyster
```

Before each action, Gemini receives the current JPEG screenshot together with
the task objective, scene metadata when present, planned action, and remaining
base actions. It must return exactly one control operation:

| Operation | Effect | Required fields |
| --- | --- | --- |
| `keep_action` | Execute the planned key and duration unchanged. | `operation`, optional `reason` |
| `stop_action` | Release every pressed key and end the action sequence. | `operation`, optional `reason` |
| `extend_action` | Add time to the planned action without changing its key. | Positive `extension_ms` |
| `correct_action` | Replace the planned action with a validated action. | `corrected_action.key`, positive `corrected_action.duration_ms` |

Example Agent response:

```json
{
  "operation": "correct_action",
  "reason": "The target is now to the left of the camera.",
  "extension_ms": 0,
  "corrected_action": {"key": "A", "duration_ms": 750}
}
```

To test all four operations without making Gemini calls, use the supplied
decision file:

```bash
playworld-agent \
  --engine happyoyster \
  --url 'https://your-happyoyster-page.example' \
  --dataset "$DATA_SUITE/gc/data.json" \
  --datasuite-root "$DATA_SUITE" \
  --task-id GC001 \
  --policy scripted \
  --decisions-file configs/decisions.example.json \
  --output-root runs/happyoyster-scripted
```

Unspecified indexes in a scripted decision file default to `keep_action`.

### 5. Batch execution

Repeat `--task-id` to select several tasks, or use `--all` for every record in
the JSON file:

```bash
playworld-agent \
  --engine happyoyster \
  --url 'https://your-happyoyster-page.example' \
  --dataset "$DATA_SUITE/oe/data.json" \
  --datasuite-root "$DATA_SUITE" \
  --all \
  --policy gemini \
  --continue-on-error \
  --output-root runs/happyoyster-oe
```

`--continue-on-error` applies between tasks. A failed task is still fully
recorded before the batch moves to the next one.

### Fault tolerance and result artifacts

Connection, generation, observation, and policy calls have independently
configurable retry counts (`--connect-attempts`, `--generation-attempts`,
`--observation-attempts`, and `--policy-attempts`). Browser recovery reconnects
through CDP. An action that may have partially executed is never blindly
repeated: pressed keys are released, the failure is recorded, and that task
stops. If an Agent call fails, the default safe decision is `stop_action`; use
`--policy-failure-fallback keep` or `fail` only when that behavior is intended.

Every task creates a timestamped folder under `--output-root`:

```text
GC001_YYYYMMDD_HHMMSS_microseconds/
├── task.json
├── run_config.json
├── events.jsonl
├── result.json
└── screenshots/
    ├── probe.jpg
    ├── after_upload.jpg
    ├── before_actions.jpg
    ├── action_NNN_before.jpg
    ├── action_NNN_after.jpg
    ├── after_actions.jpg
    └── natural_end.jpg
```

`events.jsonl` is flushed after each event, so partial runs remain diagnosable.
`result.json` contains task status, planned/resolved actions, Agent decisions,
timestamps, errors, and screenshot paths. Gemini policy traces include the
decision prompt, raw response, and latency, but API credentials are never
written to task or result artifacts. The batch CLI additionally writes
`batch_YYYYMMDD_HHMMSS.json`.

### Python interface

The same HappyOyster control path can be embedded without the CLI:

```python
from pathlib import Path

from playworldbench.agent import (
    AgentHarness,
    HappyOysterEngine,
    HarnessConfig,
    KeepAllPolicy,
)

task = {
    "task_id": "GC001",
    "prompt": "Move forward and turn left to inspect the scene.",
    "image_path": "gc/images/GC001.jpg",
    "action_sequence_steps": ["hold(W,1000ms)", "hold(A,750ms)"],
}

engine = HappyOysterEngine(
    target_url="https://your-happyoyster-page.example",
    cdp_url="http://127.0.0.1:9222",
)
harness = AgentHarness(
    engine=engine,
    policy=KeepAllPolicy(),
    output_root=Path("runs/happyoyster"),
    config=HarnessConfig(policy_failure_fallback="stop"),
)
result = harness.run_task(task, Path("/absolute/path/to/gc/images/GC001.jpg"))
print(result["status"], result["run_dir"])
```

Use `GeminiPolicy(task["prompt"], task_context=task)` in place of
`KeepAllPolicy()` for visual closed-loop control. `PlayWorldEngine` is also
exported as the canonical base-class name for implementing another world-model
page adapter.

## Metrics evaluation

### Automatic metrics included in this release

The public evaluator is an automatic Gemini VLM-as-a-judge pipeline. Given a
task record, its reference image when applicable, and a generated video, the
code automatically produces the following measurements and final table:

| Stage | Automatic measurement | Output |
| --- | --- | --- |
| Video quality | Applicable 1–5 categories such as identity, background consistency, motion/trajectory, contact/support, collision/boundary, causal response, spatial consistency, and evolution quality | Raw category scores and `final_score_1_to_5` |
| Instruction following | Trajectory-only Pass/Partial/Fail gate for GC, third-person IF, and out-of-sight OE | Verdict and binary instruction-following score |
| Failure normalization | Preserve the raw quality score for Pass/Partial and replace Fail with 1 where the gate applies; missing videos also contribute 1 | Normalized per-video score |
| Benchmark aggregation | Split OE into the fixed 30 In-sight and 43 Out-of-sight tasks, then average GC, IF, In-sight, and Out-of-sight with equal group weight | `Gemini score averages · Fail = 1 · OE split` Markdown/JSON table |

All scripts used to compute these metrics are included in this repository:

| Metric component | Script |
| --- | --- |
| Per-video score/gate CLI and Gemini request | [`playworldbench/cli/evaluate.py`](playworldbench/cli/evaluate.py) |
| Primary/detail frame extraction and contact sheets | [`playworldbench/metrics/dual_sampling.py`](playworldbench/metrics/dual_sampling.py) |
| Automatic 1–5 scoring context, prompt, and schema | [`playworldbench/metrics/gemini_metrics.py`](playworldbench/metrics/gemini_metrics.py) |
| Trajectory-only instruction gate | [`playworldbench/metrics/instruction_gate.py`](playworldbench/metrics/instruction_gate.py) |
| Fail=1 normalization and fixed OE split | [`playworldbench/metrics/oe_split_averages.py`](playworldbench/metrics/oe_split_averages.py) |
| Table aggregation CLI | [`playworldbench/cli/aggregate.py`](playworldbench/cli/aggregate.py) |
| Metric regression tests | [`tests/test_metrics.py`](tests/test_metrics.py) |

Installing the package registers `playworld-eval` and
`playworld-aggregate` as the two executable metric commands. The Python files
above are the complete implementations behind those commands, not placeholders.

Only categories marked applicable in each task record enter its weighted quality
average. `task_specific`, `applicable=false`, and zero-weight questions are
excluded. For GC aggregation, `identity_id` has weight 2. The exact group and
failure policies are listed in [Exact table policy](#exact-table-policy).

In this release, **automatic metrics** means the reproducible Gemini evaluation
implemented in `playworldbench/metrics/`. VBench, FVD, LPIPS, SSIM, and other
separate metric suites are not silently computed and are not included in the
reported table.

### Automatic evaluation pipeline

1. Read the task metadata and generated-video path.
2. Decode the complete video into the Primary and Detail evidence streams
   specified in [Sampling sent to Gemini](#sampling-sent-to-gemini).
3. Send the reference image (score mode only), both chronological evidence
   streams, the structured task context, and the canonical scoring prompt to
   Gemini.
4. Save the raw JSON response and update the score cache.
5. Run the applicable instruction-following gate. GC gate mode intentionally
   excludes the reference image and judges only the observed action trajectory.
6. Aggregate all cached results with the Fail=1 and fixed OE-split policy.

The commands below can evaluate one video at a time and then reproduce the full
benchmark table.

### Benchmark data and media are not included

This GitHub repository is code-only. Benchmark reference images, task JSON, and
other datasuite assets remain in the separate Hugging Face datasuite. Generated
benchmark videos remain in local or external storage. They are supplied to the
CLI using `--reference-image`, `--video`, `--dataset`, and
`--datasuite-root`; the evaluator does not require media to be copied into this
repository.

The repository contains no tracked benchmark images or videos. `.gitignore`
also excludes datasuite/data/result directories, GC/IF/OE benchmark-image
filenames, and common video formats to prevent accidental media uploads.

### Gemini automatic video score

#### 1. Generate a raw 1–5 score

Run a dry-run first to verify video decoding, both sampling streams, the exact
prompt, and the serialized context without calling Gemini:

```bash
playworld-eval --dry-run --mode score \
  --dataset "$DATA_SUITE/gc/data.json" \
  --task-id GC001 \
  --video /absolute/path/to/recording.mp4 \
  --reference-image "$DATA_SUITE/gc/images/GC001.jpg" \
  --world-model HYWorld2 \
  --context-output outputs/GC001_context.json \
  --output outputs/GC001_dry_run.json
```

Call Gemini and update the shared score cache:

```bash
playworld-eval --mode score \
  --dataset "$DATA_SUITE/gc/data.json" \
  --task-id GC001 \
  --video /absolute/path/to/recording.mp4 \
  --reference-image "$DATA_SUITE/gc/images/GC001.jpg" \
  --world-model HYWorld2 \
  --model gemini-3.1-pro-preview \
  --cache-key 'HYWorld2::HYWorld2/GC001/recording.mp4' \
  --scores-cache outputs/gemini_scores.json \
  --context-output outputs/GC001_context.json \
  --output outputs/GC001_result.json
```

The score prompt itself emits the third-person IF and out-of-sight OE
instruction-following checks used by the table. First-person IF and In-sight OE
are marked not applicable for that gate.

#### 2. Generate the GC trajectory gate

GC uses a separate action-trajectory-only judgment. It must not compare scene
identity, background appearance, or returned visual content.

```bash
playworld-eval --mode gate \
  --dataset "$DATA_SUITE/gc/data.json" \
  --task-id GC001 \
  --video /absolute/path/to/recording.mp4 \
  --world-model HYWorld2 \
  --model gemini-3.1-pro-preview \
  --cache-key 'HYWorld2::HYWorld2/GC001/recording.mp4' \
  --gc-completion-cache outputs/gemini_task_completion.json \
  --context-output outputs/GC001_gate_context.json \
  --output outputs/GC001_gate_result.json
```

`gate` mode intentionally does not send the reference image. Pass and Partial
map to 1; Fail maps to 0 before the table converts Fail to a final contribution
of 1.

#### 3. Aggregate the OE-split table

The video manifest is a JSON array. Each record must provide at least:

```json
{
  "model": "HYWorld2",
  "task": "GC001",
  "group": "GC",
  "view": "first-person",
  "path": "HYWorld2/GC001/recording.mp4",
  "isPlaceholder": false,
  "isFullProcess": false
}
```

The cache key is always `model::path`.

```bash
playworld-aggregate \
  --videos-manifest outputs/videos_manifest.json \
  --scores outputs/gemini_scores.json \
  --gc-task-completion outputs/gemini_task_completion.json \
  --output-json outputs/oe_split_averages.json \
  --output-markdown outputs/oe_split_averages.md
```

The command prints the same Markdown table to stdout.

## Existing-video verification performed

The current code successfully dry-ran these real videos from `final-result`:

- `HYWorld2/GC001/recording.mp4`: 597 primary frames and 30 detail frames.
- `HYWorld2/IF001/recording.mp4`: 604 primary frames and 31 detail frames.
- `HYWorld2/OE001/recording.mp4`: 609 primary frames and 31 detail frames.
- `LingbotVA/OE014/OE014_lingbot.mp4`: 160 primary frames and 8 detail frames.

GC gate context was also generated from the real GC001 video. No paid Gemini API
call was made during this verification because `GEMINI_API_KEY` was not set in
the execution environment.

## Tests

```bash
python -m unittest discover -s tests -v
```

Tests cover Agent decision semantics, retries, safe-stop fallback, screenshot and
result artifacts, non-retried ambiguous actions, exact sampling settings, gate
applicability, GC identity weight 2, Fail=1 behavior, missing-video=1 behavior,
and the fixed 30/43 OE split.
