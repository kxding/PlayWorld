# Metrics

Metric implementations are organized by evaluator:

- `vqa/`: Gemini VQA judge, including video sampling, rubric/prompt, instruction
  gate, API call, and JSON output.
- The legacy import path `playworldbench.metrics` remains available for Python
  callers.

Run the VQA judge from the repository root with `./run_vqa_score.sh`.
