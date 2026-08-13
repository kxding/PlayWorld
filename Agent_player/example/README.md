# Player examples

Each numbered JSON is a one-task dataset and references the JPEG with the same
number. Original task IDs are preserved.

| Example | Source task |
| --- | --- |
| `001` | `GC002` |
| `002` | `GC004` |
| `003` | `GC005` |
| `004` | `GC006` |
| `005` | `IF046` |
| `006` | `IF032` |
| `007` | `IF017` |

For example, run `001.json` by using this directory as the data root:

```bash
GENIE3_DATA_ROOT=/absolute/path/to/playworld_code/Agent_player/example \
GENIE3_DATA_FILES=GC:001.json \
TASK_IDS=GC002 \
python3 /absolute/path/to/playworld_code/Agent_player/player_genie3.py
```
