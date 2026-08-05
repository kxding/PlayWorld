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

## HappyOyster / Agent control

### 1. Start a CDP-enabled browser

```bash
chmod +x scripts/*.sh
scripts/launch_chrome_cdp.sh
```

In that Chrome window, open HappyOyster and finish any required login. The
harness attaches to this existing browser and deliberately does not close it.

### 2. Run one task

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

Use the corresponding IF/OE JSON file and original ID for those suites, for
example `--dataset "$DATA_SUITE/if/data.json" --task-id IF001`. Each record must
provide `task_id`, `prompt`, `image_path`, and `action_sequence_steps` (a list
such as `hold(W,1000ms)` and `wait(500ms)`). The image path is resolved relative
to `--datasuite-root`.

Run several selected tasks by repeating `--task-id`, or run the entire JSON with
`--all`. Add `--continue-on-error` for batch execution that should continue
after a failed task.

### 3. Choose the Agent decision interface

- `--policy keep`: execute the benchmark action sequence unchanged.
- `--policy scripted --decisions-file configs/decisions.example.json`: exercise
  all four operations deterministically.
- `--policy gemini --gemini-model gemini-3.1-pro-preview`: let Gemini inspect
  the current screenshot before every action and return one of the four control
  operations.

The four decisions have stable semantics: `keep_action` keeps the planned key
and duration, `stop_action` releases pressed keys and ends the sequence,
`extend_action` adds milliseconds to the planned action, and `correct_action`
replaces it with a validated key/duration pair.

### Fault tolerance and result artifacts

Connection, generation, observation, and policy calls have independently
configurable retry counts. A browser recovery reconnects through CDP. An action
that may have partially executed is never blindly retried; keys are released and
the failure is recorded. If an Agent call fails, the default safe behavior is
`stop_action`, configurable with `--policy-failure-fallback`.

Every task creates a timestamped folder under `--output-root` containing:

```text
task.json
run_config.json
events.jsonl
result.json
screenshots/
  probe.jpg
  after_upload.jpg
  before_actions.jpg
  action_NNN_before.jpg
  action_NNN_after.jpg
  after_actions.jpg
  natural_end.jpg
```

The batch CLI also writes `batch_YYYYMMDD_HHMMSS.json`. This preserves task
execution status, decisions, executed actions, timestamps, errors, screenshots,
and policy traces without storing API credentials.

## Gemini video metrics

### 1. Generate a raw 1–5 score

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

### 2. Generate the GC trajectory gate

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

### 3. Aggregate the OE-split table

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
