# VQA video scoring

This folder contains the complete, inspectable VQA scoring path:

| File | Responsibility |
| --- | --- |
| `sampling.py` | Decode the complete video into synchronized 10 FPS primary and 0.5 FPS detail contact sheets. |
| `rubric.py` | Build the task-aware 1–5 physical/visual-quality questions, scoring policy, output schema, and VQA prompt. |
| `instruction_gate.py` | Build the separate Pass/Partial/Fail trajectory gate used for GC and applicable IF/OE cases. |
| `score.py` | Load one task, assemble visual evidence, call Gemini, parse JSON, and save the result/cache. |

## What the VQA judge receives

For `--mode score`, Gemini receives the task-derived rubric, an optional
reference image, and both chronological contact-sheet streams. The primary
stream is used for motion and temporal continuity; the detail stream is used
for identity, texture, material, color, and small artifacts. The judge returns
per-question evidence and scores plus a normalized final score from 1 to 5.

For `--mode gate`, the same video evidence is used without the reference image.
The result is only the instruction-following verdict. The benchmark aggregation
later converts an applicable Fail to a contribution of 1.

## Run

Edit the configuration block at the top of `run_vqa_score.sh`, especially:

```bash
api_key="xxx"
dataset="/absolute/path/to/data.json"
task_id="GC001"
video="/absolute/path/to/recording.mp4"
reference_image="/absolute/path/to/GC001.jpg"
```

Then run:

```bash
chmod +x run_vqa_score.sh
./run_vqa_score.sh
```

To validate sampling and prompt generation without an API call:

```bash
DRY_RUN=1 ./run_vqa_score.sh
```

All settings may instead be supplied as uppercase environment variables. For
advanced use, arguments are forwarded directly:

```bash
GEMINI_API_KEY="xxx" ./run_vqa_score.sh --mode score --dataset /path/data.json \
  --task-id GC001 --video /path/video.mp4 --output outputs/GC001.json
```

The key is read only from the process environment by the Python client and is
never written to the result or context JSON.
