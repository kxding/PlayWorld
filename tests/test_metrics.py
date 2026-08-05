from __future__ import annotations

import unittest

from playworldbench.metrics import (
    CONTACT_SHEET_JPEG_QUALITY,
    CONTACT_SHEET_JPEG_SUBSAMPLING,
    DETAIL_SPEC,
    PRIMARY_SPEC,
)
from playworldbench.metrics.instruction_gate import build_gate_context, gate_kind
from playworldbench.metrics.oe_split_averages import aggregate_fail_one_oe_split, normalized_score


class MetricTest(unittest.TestCase):
    def test_contact_sheet_transport_encoding(self):
        self.assertEqual(CONTACT_SHEET_JPEG_QUALITY, 70)
        self.assertEqual(CONTACT_SHEET_JPEG_SUBSAMPLING, 2)

    def test_exact_dual_sampling_specs(self):
        self.assertEqual((PRIMARY_SPEC.fps, PRIMARY_SPEC.cell_width, PRIMARY_SPEC.cell_height), (10.0, 384, 216))
        self.assertEqual((PRIMARY_SPEC.grid_columns, PRIMARY_SPEC.grid_rows), (5, 5))
        self.assertEqual((DETAIL_SPEC.fps, DETAIL_SPEC.cell_width, DETAIL_SPEC.cell_height), (0.5, 800, 450))
        self.assertEqual((DETAIL_SPEC.grid_columns, DETAIL_SPEC.grid_rows), (2, 2))

    def test_gate_scope(self):
        self.assertEqual(gate_kind({"task_id": "GC001"}), "gc")
        self.assertEqual(gate_kind({"task_id": "IF001", "perspective": "third-person"}), "if_third_person")
        self.assertIsNone(gate_kind({"task_id": "IF002", "perspective": "first-person"}))
        self.assertEqual(gate_kind({"task_id": "OE014", "sub_category": "outofsight evolution"}), "oe_out_of_sight")
        self.assertIsNone(gate_kind({"task_id": "OE001", "sub_category": "insight evolution"}))
        context = build_gate_context({}, {"task_id": "GC001", "prompt": "Turn back to the original view."}, {"primary": {"fps": 10}})
        self.assertTrue(context["revisit_required"])

    def test_gc_identity_weight_is_two(self):
        result = {"categories": {"identity_id": {"score": 5, "weight": 3}, "color": {"score": 1, "weight": 1}}}
        self.assertEqual(normalized_score("M::x/GC001/video.mp4", result), 3.67)

    def test_fail_one_and_missing_are_one(self):
        videos = [
            {"model": "M", "task": "GC001", "group": "GC", "view": "first-person", "path": "M/GC001.mp4"},
            {"model": "M", "task": "IF001", "group": "IF", "view": "first-person", "path": "M/IF001.mp4"},
            {"model": "M", "task": "OE001", "group": "OE", "view": "first-person", "path": "M/OE001.mp4"},
            {"model": "M", "task": "OE014", "group": "OE", "view": "first-person", "path": "M/OE014.mp4"},
        ]
        scores = {
            "M::M/GC001.mp4": {"score": 5},
            "M::M/IF001.mp4": {"score": 4},
            "M::M/OE001.mp4": {"score": 3},
            "M::M/OE014.mp4": {"score": 5, "oe_instruction_following_check": {"verdict": "fail", "instruction_following_score": 0}},
        }
        completion = {"results": {"M::M/GC001.mp4": {"verdict": "fail", "instruction_following_score": 0}}}
        row = aggregate_fail_one_oe_split(videos, scores, completion, models=(("M", "M"),))[0]
        self.assertEqual(row["gc"]["average"], 1)
        self.assertEqual(row["if"]["average"], 4)
        self.assertEqual(row["insight"]["denominator"], 30)
        self.assertEqual(row["out_of_sight"]["denominator"], 43)
        self.assertEqual(row["out_of_sight"]["average"], 1)


if __name__ == "__main__":
    unittest.main()
