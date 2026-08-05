import json
import sys
import tempfile
import types
import unittest
from pathlib import Path

from playworldbench.cli.automatic import main as automatic_main
from playworldbench.metrics.memory_metrics import (
    aggregate_geo3d_similarities,
    fixed_window_indices,
)
from playworldbench.metrics.vbench_adapter import (
    VBENCH_CUSTOM_DIMENSIONS,
    evaluate_with_vbench,
    validate_vbench_dimensions,
)


class AutomaticMetricsTest(unittest.TestCase):
    def test_fixed_window_indices(self):
        self.assertEqual(
            fixed_window_indices(101),
            (2, 9, 16, 23, 77, 84, 91, 98),
        )
        with self.assertRaises(ValueError):
            fixed_window_indices(1)

    def test_geo3d_aggregation(self):
        result = aggregate_geo3d_similarities(
            (0.9, 0.8, 0.7), (1.0, 0.9, 0.8)
        )
        self.assertAlmostEqual(result["score"], 0.805)
        self.assertTrue(result["higher_is_better"])

    def test_vbench_custom_dimensions_are_strict(self):
        self.assertEqual(
            validate_vbench_dimensions(
                ["subject_consistency", "subject_consistency", "imaging_quality"]
            ),
            ("subject_consistency", "imaging_quality"),
        )
        self.assertIn("dynamic_degree", VBENCH_CUSTOM_DIMENSIONS)
        with self.assertRaisesRegex(ValueError, "temporal_flickering"):
            validate_vbench_dimensions(["temporal_flickering"])

    def test_vbench_adapter_calls_official_api(self):
        calls = {}

        class FakeVBench:
            def __init__(self, device, full_info, output_dir):
                calls["init"] = (device, full_info, output_dir)

            def evaluate(self, **kwargs):
                calls["evaluate"] = kwargs
                return {"subject_consistency": 0.75}

        fake_module = types.ModuleType("vbench")
        fake_module.VBench = FakeVBench
        previous = sys.modules.get("vbench")
        sys.modules["vbench"] = fake_module
        try:
            with tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                video = root / "sample.mp4"
                video.write_bytes(b"not decoded by adapter")
                full_info = root / "VBench_full_info.json"
                full_info.write_text("{}", encoding="utf-8")
                output_dir = root / "results"
                result = evaluate_with_vbench(
                    video,
                    full_info_path=full_info,
                    output_dir=output_dir,
                    dimensions=["subject_consistency"],
                    device="cpu",
                )
        finally:
            if previous is None:
                sys.modules.pop("vbench", None)
            else:
                sys.modules["vbench"] = previous

        self.assertEqual(result["result"]["subject_consistency"], 0.75)
        self.assertEqual(calls["evaluate"]["mode"], "custom_input")
        self.assertEqual(
            calls["evaluate"]["dimension_list"], ["subject_consistency"]
        )

    def test_cli_dry_run_does_not_load_models_or_decode_video(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "plan.json"
            automatic_main(
                [
                    "memory",
                    "--video",
                    "/external/video.mp4",
                    "--metrics",
                    "geo3d",
                    "--device",
                    "cpu",
                    "--dry-run",
                    "--output",
                    str(output),
                ]
            )
            result = json.loads(output.read_text(encoding="utf-8"))
        self.assertTrue(result["dry_run"])
        self.assertEqual(result["metrics"], ["geo3d"])


if __name__ == "__main__":
    unittest.main()
