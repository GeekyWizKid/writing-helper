"""Contract tests for research claim and source provenance validation."""

from __future__ import annotations

import json
import math
import subprocess
import sys
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

from helpers import SKILL_ROOT, load_script_module


validate_sources = load_script_module("validate_sources")
validate = validate_sources.validate


def valid_manifest() -> dict:
    """Return the exact supported manifest schema with one factual claim."""
    return {
        "schema_version": 1,
        "research_required": True,
        "decision_reason": "The script makes a current factual claim.",
        "sources": [
            {
                "id": "S01",
                "title": "Official product documentation",
                "provenance": {"url": "https://example.com/product"},
                "level": "primary",
                "capture_status": "complete",
                "body_status": "full-text",
                "accessed_at": "2026-07-17",
            }
        ],
        "claims": [
            {
                "claim_id": "C01",
                "text": "The product supports streaming.",
                "claim_type": "factual",
                "source_ids": ["S01"],
                "confidence": "high",
            }
        ],
    }


class ValidateSourcesTests(unittest.TestCase):
    def test_accepts_exact_manifest_schema_and_reports_counts(self):
        result = validate(valid_manifest(), "The product supports streaming [C01].")

        self.assertEqual(
            result,
            {
                "valid": True,
                "errors": [],
                "warnings": [],
                "error_codes": [],
                "claim_count": 1,
                "source_count": 1,
            },
        )
        self.assertEqual(
            validate_sources.SOURCE_LEVELS,
            ("primary", "authoritative-secondary", "expert", "community"),
        )
        self.assertEqual(validate_sources.CONFIDENCE_LEVELS, ("high", "medium", "low"))

    def test_rejects_non_object_manifest_and_wrong_top_level_shapes(self):
        for manifest in (None, [], "manifest", {"schema_version": 1}):
            with self.subTest(manifest=manifest):
                result = validate(manifest, "")
                self.assertFalse(result["valid"])
                self.assertIn("invalid_manifest_schema", result["error_codes"])

    def test_rejects_boolean_and_nonfinite_schema_version(self):
        for value in (True, False, math.nan, math.inf, -math.inf, 1.5, 10**1000):
            manifest = valid_manifest()
            manifest["schema_version"] = value
            with self.subTest(value=value):
                result = validate(manifest, "[C01]")
                self.assertIn("invalid_schema_version", result["error_codes"])

    def test_rejects_duplicate_or_malformed_claim_ids(self):
        duplicate = deepcopy(valid_manifest()["claims"][0])
        duplicate["text"] = "Another claim"
        manifest = valid_manifest()
        manifest["claims"].append(duplicate)
        self.assertIn("duplicate_claim_id", validate(manifest, "[C01]")["error_codes"])

        for claim_id in ("C1", "c01", "C001", " C01", 1, True):
            manifest = valid_manifest()
            manifest["claims"][0]["claim_id"] = claim_id
            with self.subTest(claim_id=claim_id):
                self.assertIn(
                    "invalid_claim_id", validate(manifest, "")["error_codes"]
                )

    def test_requires_complete_source_fields_and_valid_enums(self):
        required = (
            "id",
            "title",
            "provenance",
            "level",
            "capture_status",
            "body_status",
            "accessed_at",
        )
        for field in required:
            manifest = valid_manifest()
            del manifest["sources"][0][field]
            with self.subTest(field=field):
                self.assertIn(
                    "missing_source_field", validate(manifest, "[C01]")["error_codes"]
                )

        manifest = valid_manifest()
        manifest["sources"][0]["level"] = "blog"
        self.assertIn("invalid_source_level", validate(manifest, "[C01]")["error_codes"])

        manifest = valid_manifest()
        manifest["claims"][0]["confidence"] = "certain"
        self.assertIn("invalid_confidence", validate(manifest, "[C01]")["error_codes"])

    def test_requires_exactly_one_nonempty_url_or_file_provenance(self):
        invalid_values = (
            {},
            {"url": ""},
            {"file": ""},
            {"url": "https://example.com", "file": "notes.pdf"},
            {"url": "ftp://example.com/data"},
            {"url": "http://["},
            {"url": True},
            "https://example.com",
        )
        for provenance in invalid_values:
            manifest = valid_manifest()
            manifest["sources"][0]["provenance"] = provenance
            with self.subTest(provenance=provenance):
                self.assertIn(
                    "invalid_source_provenance",
                    validate(manifest, "[C01]")["error_codes"],
                )

        manifest = valid_manifest()
        manifest["sources"][0]["provenance"] = {"file": "research/report.pdf"}
        self.assertTrue(validate(manifest, "[C01]")["valid"])

    def test_requires_real_iso_calendar_date(self):
        for date in ("2026-02-30", "2026/07/17", "", True, 20260717):
            manifest = valid_manifest()
            manifest["sources"][0]["accessed_at"] = date
            with self.subTest(date=date):
                self.assertIn("invalid_accessed_at", validate(manifest, "[C01]")["error_codes"])

    def test_claims_must_reference_existing_unique_sources(self):
        manifest = valid_manifest()
        manifest["claims"][0]["source_ids"] = ["S01", "S99"]
        self.assertIn("unknown_source_reference", validate(manifest, "[C01]")["error_codes"])

        manifest = valid_manifest()
        manifest["claims"][0]["source_ids"] = ["S01", "S01"]
        self.assertIn("duplicate_source_reference", validate(manifest, "[C01]")["error_codes"])

        manifest = valid_manifest()
        manifest["sources"].append(deepcopy(manifest["sources"][0]))
        self.assertIn("duplicate_source_id", validate(manifest, "[C01]")["error_codes"])

    def test_factual_claim_requires_at_least_one_complete_source(self):
        for capture_status, body_status in (
            ("partial", "full-text"),
            ("complete", "metadata-only"),
            ("unavailable", "unavailable"),
        ):
            manifest = valid_manifest()
            manifest["sources"][0]["capture_status"] = capture_status
            manifest["sources"][0]["body_status"] = body_status
            with self.subTest(capture_status=capture_status, body_status=body_status):
                self.assertIn(
                    "incomplete_claim_support",
                    validate(manifest, "[C01]")["error_codes"],
                )

    def test_rejects_search_snippet_as_complete_source(self):
        manifest = valid_manifest()
        manifest["sources"][0]["body_status"] = "search-snippet"
        manifest["sources"][0]["capture_status"] = "complete"

        result = validate(manifest, script_text="事实 [C01]")

        self.assertIn("snippet_cannot_be_complete", result["error_codes"])

    def test_rejects_community_only_factual_claim_support(self):
        manifest = valid_manifest()
        manifest["sources"][0]["level"] = "community"
        self.assertIn("community_only_factual_claim", validate(manifest, "[C01]")["error_codes"])

    def test_rejects_community_only_support_for_every_non_exempt_claim_type(self):
        for claim_type in ("analysis", "opinion", "unknown"):
            manifest = valid_manifest()
            manifest["sources"][0]["level"] = "community"
            manifest["claims"][0]["claim_type"] = claim_type
            with self.subTest(claim_type=claim_type):
                self.assertIn(
                    "community_only_factual_claim",
                    validate(manifest, "[C01]")["error_codes"],
                )

    def test_allows_community_only_support_only_for_exempt_claim_types(self):
        for allowed_type in ("audience-language", "anecdote"):
            manifest = valid_manifest()
            manifest["sources"][0]["level"] = "community"
            manifest["claims"][0]["claim_type"] = allowed_type
            with self.subTest(claim_type=allowed_type):
                self.assertTrue(validate(manifest, "[C01]")["valid"])

    def test_script_and_manifest_claim_markers_must_match_both_directions(self):
        result = validate(valid_manifest(), "A missing claim [C02].")
        self.assertIn("unresolved_script_marker", result["error_codes"])
        self.assertIn("claim_missing_from_script", result["error_codes"])

    def test_rejects_duplicate_script_claim_references(self):
        result = validate(valid_manifest(), "First [C01], repeated [C01].")
        self.assertIn("duplicate_script_marker", result["error_codes"])

    def test_no_research_requires_reason_and_zero_factual_markers(self):
        manifest = {
            "schema_version": 1,
            "research_required": False,
            "decision_reason": "This is a fictional mood piece with no factual claims.",
            "sources": [],
            "claims": [],
        }
        self.assertTrue(validate(manifest, "A purely fictional scene.")["valid"])

        manifest["decision_reason"] = "  "
        self.assertIn("missing_decision_reason", validate(manifest, "")["error_codes"])

        manifest["decision_reason"] = "No external research needed."
        self.assertIn(
            "factual_marker_without_research",
            validate(manifest, "Unsupported fact [C01]")["error_codes"],
        )

    def test_errors_are_deterministic_and_do_not_echo_unsafe_values(self):
        manifest = valid_manifest()
        manifest["sources"][0]["level"] = "SECRET-VALUE"
        manifest["sources"][0]["accessed_at"] = "bad"
        first = validate(manifest, "[C99]")
        second = validate(manifest, "[C99]")
        self.assertEqual(first, second)
        self.assertNotIn("SECRET-VALUE", json.dumps(first))


class ValidateSourcesCliTests(unittest.TestCase):
    script = SKILL_ROOT / "scripts" / "validate_sources.py"

    def run_cli(self, manifest_text: str, script_text: str | None = None):
        with tempfile.TemporaryDirectory() as directory:
            manifest_path = Path(directory) / "manifest.json"
            manifest_path.write_text(manifest_text, encoding="utf-8")
            command = [sys.executable, str(self.script), "--manifest", str(manifest_path)]
            if script_text is not None:
                script_path = Path(directory) / "script.md"
                script_path.write_text(script_text, encoding="utf-8")
                command.extend(("--script", str(script_path)))
            return subprocess.run(command, capture_output=True, text=True, check=False)

    def test_cli_outputs_invalid_validation_as_json_with_exit_zero(self):
        manifest = valid_manifest()
        manifest["claims"][0]["source_ids"] = ["S99"]
        completed = self.run_cli(json.dumps(manifest), "Claim [C01]")

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertFalse(json.loads(completed.stdout)["valid"])
        self.assertEqual(completed.stderr, "")

    def test_cli_malformed_input_is_safe_json_with_exit_two(self):
        for manifest_text in ("not json", "[]", '{"schema_version": NaN}'):
            with self.subTest(manifest_text=manifest_text):
                completed = self.run_cli(manifest_text)
                self.assertEqual(completed.returncode, 2)
                payload = json.loads(completed.stdout)
                self.assertEqual(payload, {"valid": False, "error": "invalid_input"})
                self.assertEqual(completed.stderr, "")


if __name__ == "__main__":
    unittest.main()
