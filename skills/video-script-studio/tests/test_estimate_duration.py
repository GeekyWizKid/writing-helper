from __future__ import annotations

import json
import math
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from helpers import SKILL_ROOT, load_script_module


class EstimateDurationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.duration = load_script_module("estimate_duration")

    def test_short_form_counts_chinese_characters_and_explicit_pauses(self) -> None:
        result = self.duration.estimate(
            {
                "primary_type": "short-form",
                "chinese_chars_per_minute": 120,
                "segments": [{"text": "你好，世界！", "pause_seconds": 2}],
            }
        )
        self.assertEqual(4, result["estimated_seconds"])
        self.assertEqual(1, result["segment_count"])

    def test_long_form_counts_english_words_with_configurable_rate(self) -> None:
        result = self.duration.estimate(
            {
                "primary_type": "long-form",
                "english_words_per_minute": 120,
                "segments": [{"text": "One well-paced sentence, here."}],
            }
        )
        self.assertEqual(2, result["estimated_seconds"])
        self.assertEqual(2 / 60, result["estimated_minutes"])

    def test_mixed_spoken_text_counts_han_characters_and_ascii_words_once(self) -> None:
        result = self.duration.estimate(
            {
                "primary_type": "short-form",
                "chinese_chars_per_minute": 60,
                "english_words_per_minute": 60,
                "segments": [{"text": "你好 AI writing 2.0！"}],
            }
        )
        # Two Han characters plus three ASCII tokens: AI, writing, and 2.0.
        self.assertEqual(5, result["estimated_seconds"])

    def test_spoken_text_counts_han_zero_and_supplementary_ideographs(self) -> None:
        result = self.duration.estimate(
            {
                "primary_type": "short-form",
                "chinese_chars_per_minute": 60,
                "segments": [{"text": "〇𠮷"}],
            }
        )
        self.assertEqual(2, result["estimated_seconds"])

    def test_english_period_separates_words_but_decimal_remains_one_token(self) -> None:
        result = self.duration.estimate(
            {
                "primary_type": "long-form",
                "english_words_per_minute": 60,
                "segments": [{"text": "Hello.World 3.14"}],
            }
        )
        self.assertEqual(3, result["estimated_seconds"])

    def test_spoken_routes_require_positive_finite_rates(self) -> None:
        base = {"primary_type": "short-form", "segments": [{"text": "你好"}]}
        for field, value in (
            ("chinese_chars_per_minute", 0),
            ("english_words_per_minute", -1),
            ("chinese_chars_per_minute", math.inf),
            ("english_words_per_minute", True),
        ):
            with self.subTest(field=field, value=value):
                with self.assertRaisesRegex(self.duration.StudioError, field):
                    self.duration.estimate({**base, field: value})

    def test_subnormal_positive_rate_raises_safe_error(self) -> None:
        with self.assertRaisesRegex(self.duration.StudioError, "english_words_per_minute"):
            self.duration.estimate(
                {
                    "primary_type": "short-form",
                    "english_words_per_minute": 5e-324,
                    "segments": [{"text": "word"}],
                }
            )

    def test_narrative_sums_declared_dialogue_action_response_and_pause(self) -> None:
        result = self.duration.estimate(
            {
                "primary_type": "narrative",
                "segments": [
                    {
                        "dialogue_seconds": 3,
                        "action_seconds": 4.5,
                        "response_seconds": 1.5,
                        "pause_seconds": 1,
                    },
                    {"dialogue_seconds": 2, "action_seconds": 0, "response_seconds": 1},
                ],
            }
        )
        self.assertEqual(13, result["estimated_seconds"])

    def test_visual_essay_uses_scene_duration_not_sparse_voiceover(self) -> None:
        result = self.duration.estimate(
            {
                "primary_type": "visual-essay",
                "segments": [
                    {"id": "S1", "duration_seconds": 12, "voiceover": "开始"},
                    {"id": "S2", "duration_seconds": 18, "voiceover": ""},
                ],
            }
        )
        self.assertEqual(30, result["estimated_seconds"])

    def test_commercial_spoken_duration_emits_target_diagnostics(self) -> None:
        base = {
            "primary_type": "commercial",
            "duration_method": "spoken",
            "english_words_per_minute": 60,
            "target_seconds": 10,
            "target_tolerance_seconds": 1,
        }
        cases = (("one two three four five", "under_target"),
                 ("one two three four five six seven eight nine ten", "within_target"),
                 ("one two three four five six seven eight nine ten eleven twelve", "over_target"))
        for text, diagnostic in cases:
            with self.subTest(diagnostic=diagnostic):
                result = self.duration.estimate({**base, "segments": [{"text": text}]})
                self.assertEqual([diagnostic], result["diagnostics"])

    def test_commercial_declared_duration_uses_segment_duration(self) -> None:
        result = self.duration.estimate(
            {
                "primary_type": "commercial",
                "duration_method": "declared",
                "target_seconds": 15,
                "segments": [{"duration_seconds": 6}, {"duration_seconds": 9}],
            }
        )
        self.assertEqual(15, result["estimated_seconds"])
        self.assertEqual(["within_target"], result["diagnostics"])

    def test_commercial_inclusive_tolerance_boundaries_are_stable(self) -> None:
        base = {
            "primary_type": "commercial",
            "duration_method": "declared",
            "target_seconds": 2,
            "target_tolerance_seconds": 1,
        }
        for duration in (0.1, 0.3):
            with self.subTest(duration=duration):
                result = self.duration.estimate(
                    {**base, "segments": [{"duration_seconds": duration}] * 10}
                )
                self.assertEqual(["within_target"], result["diagnostics"])

    def test_empty_segments_returns_stable_zero_result(self) -> None:
        result = self.duration.estimate({"primary_type": "visual-essay", "segments": []})
        self.assertEqual(
            {
                "primary_type": "visual-essay",
                "estimated_seconds": 0,
                "estimated_minutes": 0,
                "diagnostics": [],
                "segment_count": 0,
            },
            result,
        )

    def test_malformed_segments_have_field_specific_safe_errors(self) -> None:
        cases = (
            ({"primary_type": "short-form"}, "segments"),
            ({"primary_type": "short-form", "segments": {}}, "segments"),
            ({"primary_type": "short-form", "segments": ["bad"]}, r"segments\[0\]"),
            ({"primary_type": "short-form", "segments": [{}]}, r"segments\[0\]\.text"),
            ({"primary_type": "visual-essay", "segments": [{}]}, r"segments\[0\]\.duration_seconds"),
        )
        for payload, field in cases:
            with self.subTest(field=field):
                with self.assertRaisesRegex(self.duration.StudioError, field):
                    self.duration.estimate(payload)

    def test_numeric_fields_reject_booleans_nonfinite_and_negative_values(self) -> None:
        for value in (True, math.nan, math.inf, -0.1):
            payload = {
                "primary_type": "visual-essay",
                "segments": [{"duration_seconds": value}],
            }
            with self.subTest(value=value):
                with self.assertRaisesRegex(
                    self.duration.StudioError, r"segments\[0\]\.duration_seconds"
                ):
                    self.duration.estimate(payload)

    def test_huge_integer_raises_safe_field_error(self) -> None:
        with self.assertRaisesRegex(
            self.duration.StudioError, r"segments\[0\]\.duration_seconds"
        ):
            self.duration.estimate(
                {
                    "primary_type": "visual-essay",
                    "segments": [{"duration_seconds": 10**400}],
                }
            )

    def test_finite_segment_values_with_nonfinite_sum_raise_safe_error(self) -> None:
        with self.assertRaisesRegex(self.duration.StudioError, "estimated_seconds"):
            self.duration.estimate(
                {
                    "primary_type": "visual-essay",
                    "segments": [
                        {"duration_seconds": 1e308},
                        {"duration_seconds": 1e308},
                    ],
                }
            )

    def test_invalid_payload_and_primary_type_are_rejected(self) -> None:
        for payload, field in (([], "payload"), ({"segments": []}, "primary_type"),
                               ({"primary_type": "podcast", "segments": []}, "primary_type")):
            with self.subTest(payload=payload):
                with self.assertRaisesRegex(self.duration.StudioError, field):
                    self.duration.estimate(payload)


class EstimateDurationCliTests(unittest.TestCase):
    SCRIPT = SKILL_ROOT / "scripts" / "estimate_duration.py"

    def run_cli(self, content: str) -> subprocess.CompletedProcess[str]:
        with tempfile.TemporaryDirectory() as directory:
            input_path = Path(directory) / "input.json"
            input_path.write_text(content, encoding="utf-8")
            return subprocess.run(
                [sys.executable, str(self.SCRIPT), "--input", str(input_path)],
                capture_output=True,
                text=True,
                check=False,
            )

    def test_cli_emits_success_json_and_exit_zero(self) -> None:
        completed = self.run_cli(
            json.dumps({"primary_type": "visual-essay", "segments": [{"duration_seconds": 5}]})
        )
        self.assertEqual(0, completed.returncode)
        self.assertEqual(5, json.loads(completed.stdout)["estimated_seconds"])
        self.assertEqual("", completed.stderr)

    def test_cli_emits_sanitized_error_json_and_exit_two(self) -> None:
        completed = self.run_cli("{malformed")
        self.assertEqual(2, completed.returncode)
        self.assertEqual({"error": "Could not read valid JSON data."}, json.loads(completed.stdout))
        self.assertNotIn("Traceback", completed.stdout + completed.stderr)

    def test_cli_sanitizes_valid_json_huge_integer(self) -> None:
        completed = self.run_cli(
            json.dumps(
                {
                    "primary_type": "visual-essay",
                    "segments": [{"duration_seconds": 10**400}],
                }
            )
        )
        self.assertEqual(2, completed.returncode)
        self.assertRegex(json.loads(completed.stdout)["error"], r"segments\[0\]\.duration_seconds")
        self.assertNotIn("Traceback", completed.stdout + completed.stderr)

    def test_cli_sanitizes_nonfinite_duration_sum(self) -> None:
        completed = self.run_cli(
            json.dumps(
                {
                    "primary_type": "visual-essay",
                    "segments": [
                        {"duration_seconds": 1e308},
                        {"duration_seconds": 1e308},
                    ],
                }
            )
        )
        self.assertEqual(2, completed.returncode)
        self.assertEqual({"error": "estimated_seconds must be finite."}, json.loads(completed.stdout))
        self.assertNotIn("Traceback", completed.stdout + completed.stderr)

    def test_cli_sanitizes_subnormal_positive_rate(self) -> None:
        completed = self.run_cli(
            json.dumps(
                {
                    "primary_type": "short-form",
                    "english_words_per_minute": 5e-324,
                    "segments": [{"text": "word"}],
                }
            )
        )
        self.assertEqual(2, completed.returncode)
        self.assertEqual(
            {"error": "english_words_per_minute produces a non-finite duration."},
            json.loads(completed.stdout),
        )
        self.assertNotIn("Traceback", completed.stdout + completed.stderr)


if __name__ == "__main__":
    unittest.main()
