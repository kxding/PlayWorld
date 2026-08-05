# Automatic metrics

PlayWorldBench exposes non-Gemini automatic metrics through:

```bash
playworld-auto-metrics {vbench,memory} ...
```

These results are auxiliary diagnostics. They are saved separately and do not
change the canonical `Gemini score averages · Fail = 1 · OE split` table.

## Official VBench backend

The adapter calls the installed official
[Vchitect/VBench](https://github.com/Vchitect/VBench) package in
`custom_input` mode. PlayWorldBench does not copy or modify VBench source code.
It exposes only the dimensions documented by VBench for arbitrary custom
videos:

- `subject_consistency`
- `background_consistency`
- `motion_smoothness`
- `dynamic_degree`
- `aesthetic_quality`
- `imaging_quality`

Prompt-suite-only dimensions are rejected instead of being assigned misleading
custom-video scores. VBench downloads/loads its own pretrained models and writes
dimension artifacts to the requested external output directory.

## No-GT memory backend

This backend extracts the reusable protocol from the local WorldPlay metrics.
It samples four early frames at 2%, 9%, 16%, and 23% of the video and four late
frames at 77%, 84%, 91%, and 98%.

### Geo3D

Depth Anything V2 estimates one depth map per sampled frame. Each depth map is
min-max normalized and L2 normalized. Adjacent cosine similarities are computed
within the early and late windows; the cross-window pair is excluded.

```text
Geo3D = 0.7 * (mean_early + mean_late) / 2
      + 0.3 * min(min_early, min_late)
```

Higher is better. This no-GT protocol measures local depth-structure stability;
it cannot prove prompt correctness and a frozen video can score highly.

### DSC_ctx

YOLO detects plausible dynamic COCO subjects. A class must appear in at least
two early and two late frames. The strongest confidence/area instance is
cropped per frame and embedded using CLIP; the score is the mean pairwise cosine
similarity between early and late subject embeddings.

If no comparable dynamic subject exists, the result is `null` with an explicit
status. N/A must not be converted to zero when reporting model averages.

## Media policy

Videos are read from the path supplied on the command line. Neither backend
copies source videos or benchmark images into the repository. Model weights,
VBench metadata, output JSON, and caches also remain external or in ignored
output directories.
