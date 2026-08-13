# Agent Player

This directory separates the reusable player contract from concrete world-model
website automation.

```text
Agent_player/
├── player.py                  # template/base class for another model
├── player_genie3.py           # complete migrated Genie3 runner
├── player_happyoyster.py      # complete migrated HappyOyster runner
├── agent_ablation.py          # shared HappyOyster agent-controller support
├── api_keys.example.sh        # credential placeholders only
├── example/                   # seven numbered image/task pairs
├── genie3/                    # Genie3 launch/batch/validation support
└── happyoyster/               # HappyOyster launch/ablation/validation support
```

`player.py` is intentionally a template. To add another model, subclass
`Player` and implement page selection, image/prompt submission, readiness, and
optionally native-video download. Shared action parsing supports
`hold(W,1000ms)`, chords such as `hold(W+D,900ms)`, and `wait(500ms)`.

The two concrete players retain the complete implementations migrated from
`worldplay_0622/code/playwright_genie3` and
`worldplay_0622/code/playwright_happyoyster`.

## Install

```bash
python3 -m pip install -r Agent_player/genie3/requirements.txt
python3 -m playwright install chromium
```

## Credentials

No source credential was copied. For adaptive Agent control only:

```bash
cp Agent_player/api_keys.example.sh Agent_player/api_keys.sh
# edit xxx values; Agent_player/api_keys.sh is ignored by git
```

HappyOyster `AGENT_ABLATION_MODE=preset_only` does not need an LLM key. The
migrated Genie3 workflow requires its live adaptive controller, matching the
source runner's behavior.

## Genie3

Launch a dedicated signed-in Chrome session, then run one or more task IDs:

```bash
Agent_player/genie3/launch_chrome_cdp.sh
GENIE3_DATA_ROOT=/path/to/datasuite Agent_player/genie3/run_task.sh GC079
```

The complete runner can also be invoked directly. Its inputs are configured by
the existing `GENIE3_*` and `TASK_IDS` environment variables:

```bash
GENIE3_DATA_ROOT=/path/to/datasuite \
GENIE3_DATA_FILES=GC:final_combined.json \
GENIE3_OUT_ROOT=/path/to/output \
TASK_IDS=GC079 \
python3 Agent_player/player_genie3.py
```

After `python3 -m pip install -e .`, the equivalent installed command is
`playworld-player-genie3`.

## HappyOyster

```bash
Agent_player/happyoyster/launch_chrome_cdp.sh
HAPPYOYSTER_DATA_ROOT=/path/to/datasuite Agent_player/happyoyster/run_task.sh GC079
```

Or call it directly:

```bash
HAPPYOYSTER_DATA_ROOT=/path/to/datasuite \
HAPPYOYSTER_DATA_FILES=GC:GC.json,IF:IF.json,OE:OE.json \
HAPPYOYSTER_OUT_ROOT=/path/to/output \
TASK_IDS=GC079 \
python3 Agent_player/player_happyoyster.py
```

After editable installation, the equivalent command is
`playworld-player-happyoyster`.

Both players attach through CDP to an already signed-in Chrome profile and do
not contain account credentials.
