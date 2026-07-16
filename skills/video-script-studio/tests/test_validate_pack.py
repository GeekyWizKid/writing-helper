from __future__ import annotations

import json
import os
import re
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest import mock

from helpers import load_script_module


COMMON_SCRIPT_HEADINGS = (
    "最终命题", "目标", "预计时长", "干净表演稿", "制作执行稿",
    "待人工确认事项", "可删段落", "短版本切点",
)

ROUTE_ANCHORS = {
    "short-form": {"brief.md": ("观看理由",), "outline.md": ("中段推进", "结尾兑现")},
    "long-form": {"brief.md": ("核心问题",), "outline.md": ("子问题链", "章节回报")},
    "narrative": {"brief.md": ("人物目标",), "outline.md": ("阻力",), "script.md": ("潜台词",)},
    "commercial": {"brief.md": ("唯一核心承诺",), "research.md": ("证据",), "review.md": ("合规",)},
    "visual-essay": {"storyboard.md": ("可见行动", "视觉母题", "环境声"), "script.md": ("旁白克制",)},
}
EXPECTED_DIMENSIONS = {
    "short-form": ("viewing_reason", "pace_progression", "information_density", "natural_delivery", "ending_payoff"),
    "long-form": ("research_depth", "question_chain", "chapter_value", "evidence_opinion_separation", "long_range_retention"),
    "narrative": ("character_desire", "conflict_escalation", "scene_function", "subtext", "emotional_payoff"),
    "commercial": ("audience_insight", "single_promise", "proof_strength", "product_integration", "action_drive", "compliance"),
    "visual-essay": ("visible_action", "visual_storytelling", "inner_outer_change", "sound_design", "voiceover_restraint", "aesthetic_consistency"),
}
EXPECTED_GATES = (
    "factual_integrity", "logical_consistency", "brief_alignment", "profile_constraints",
    "duration_feasible", "production_feasible", "risk_disclosure",
)
EXPECTED_WEIGHTS = {
    "short-form": dict(zip(EXPECTED_DIMENSIONS["short-form"], (25, 20, 20, 15, 20))),
    "long-form": dict(zip(EXPECTED_DIMENSIONS["long-form"], (20, 25, 20, 20, 15))),
    "narrative": dict(zip(EXPECTED_DIMENSIONS["narrative"], (20, 25, 20, 15, 20))),
    "commercial": dict(zip(EXPECTED_DIMENSIONS["commercial"], (15, 20, 20, 15, 15, 15))),
    "visual-essay": dict(zip(EXPECTED_DIMENSIONS["visual-essay"], (20, 20, 15, 15, 15, 15))),
}


class ValidatePackTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.initializer = load_script_module("init_project")
        cls.state = load_script_module("state_manager")
        cls.validator = load_script_module("validate_pack")

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        result = self.initializer.init_project(
            Path(self.temporary.name), "Pack Test", "short-form", date="2026-07-17"
        )
        self.project = Path(result["path"])
        self.make_valid()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def write(self, name: str, text: str) -> None:
        (self.project / name).write_text(text, encoding="utf-8")

    def make_valid(self) -> None:
        for stage in self.state.STAGES:
            self.state.approve(self.project, stage)
        for name in (
            "brief.md", "research.md", "concepts.md", "outline.md",
            "storyboard.md", "assets.md", "publish.md",
        ):
            self.write(name, f"# {name}\n\n这是经过人工确认的完整制作内容。\n")
        self.write("brief.md", "# Brief\n\n## 观看理由\n观众马上获得明确价值。\n")
        self.write(
            "outline.md",
            "# Outline\n\n## 中段推进\n信息逐层升级。\n\n## 结尾兑现\n结尾回答开头承诺。\n",
        )
        script = "# Script\n\n" + "\n\n".join(
            f"## {heading}\n这是{heading}的完整可执行内容。" for heading in COMMON_SCRIPT_HEADINGS
        )
        self.write("script.md", script + "\n")
        manifest = {
            "schema_version": 1,
            "research_required": False,
            "decision_reason": "该创作不依赖外部事实研究。",
            "sources": [],
            "claims": [],
        }
        self.write(
            "sources.md",
            "---\n" + json.dumps(manifest, ensure_ascii=False) + "\n---\n\n# Sources\n\n无需外部事实来源。\n",
        )
        dimensions = {
            name: {"score": 8, "weight": weight}
            for name, weight in zip(
                EXPECTED_DIMENSIONS["short-form"], EXPECTED_WEIGHTS["short-form"].values()
            )
        }
        review = {
            "schema_version": 1,
            "passed": True,
            "total_score": 80,
            "core_dimensions": dimensions,
            "base_gates": {name: True for name in self.validator.BASE_GATES},
            "revision_count": 0,
        }
        self.write(
            "review.md",
            "---\n" + json.dumps(review, ensure_ascii=False) + "\n---\n\n# Review\n\n全部质量门槛已经通过。\n",
        )

    def set_route(self, route: str) -> None:
        state = self.state.load_state(self.project)
        state["project"]["primary_type"] = route
        self.state.save_state(self.project, state)
        for filename, headings in ROUTE_ANCHORS[route].items():
            with (self.project / filename).open("a", encoding="utf-8") as artifact:
                for heading in headings:
                    artifact.write(f"\n## {heading}\n{heading}已经形成可执行且经过确认的内容。\n")
        review_path = self.project / "review.md"
        review = json.loads(review_path.read_text(encoding="utf-8").split("---")[1])
        review["core_dimensions"] = {
            name: {"score": 8, "weight": weight}
            for name, weight in EXPECTED_WEIGHTS[route].items()
        }
        review_path.write_text(
            "---\n" + json.dumps(review, ensure_ascii=False) + "\n---\n\n# Review\n\n质量复核完整。\n"
            + "\n".join(f"\n## {h}\n{h}合规说明完整。" for h in ROUTE_ANCHORS[route].get("review.md", ()))
            + "\n",
            encoding="utf-8",
        )

    def test_valid_pack_has_exact_deterministic_result(self) -> None:
        self.assertEqual(EXPECTED_DIMENSIONS, self.validator.ROUTE_DIMENSIONS)
        self.assertEqual(EXPECTED_GATES, self.validator.BASE_GATES)
        self.assertEqual(EXPECTED_WEIGHTS, self.validator.ROUTE_WEIGHTS)
        expected = {
            "valid": True,
            "errors": [],
            "warnings": [],
            "error_codes": [],
            "checked_file_count": 11,
            "source_count": 0,
            "claim_count": 0,
        }
        self.assertEqual(expected, self.validator.validate_pack(self.project))
        self.assertEqual(expected, self.validator.validate_pack(self.project))

    def test_all_five_routes_validate_with_exact_dimensions_and_anchors(self) -> None:
        for route in ROUTE_ANCHORS:
            with self.subTest(route=route), tempfile.TemporaryDirectory() as directory:
                result = self.initializer.init_project(
                    Path(directory), f"Route {route}", route, date="2026-07-17"
                )
                old_project = self.project
                self.project = Path(result["path"])
                try:
                    self.make_valid()
                    self.set_route(route)
                    self.assertTrue(self.validator.validate_pack(self.project)["valid"])
                finally:
                    self.project = old_project

    def test_each_route_anchor_is_required_in_its_assigned_artifact(self) -> None:
        for route, files in ROUTE_ANCHORS.items():
            for filename, headings in files.items():
                for heading in headings:
                    with self.subTest(route=route, file=filename, heading=heading), tempfile.TemporaryDirectory() as directory:
                        result = self.initializer.init_project(
                            Path(directory), "Anchor", route, date="2026-07-17"
                        )
                        old_project = self.project
                        self.project = Path(result["path"])
                        try:
                            self.make_valid()
                            self.set_route(route)
                            path = self.project / filename
                            text = path.read_text(encoding="utf-8")
                            text = re.sub(
                                rf"(?ms)^## {re.escape(heading)}[ \t]*\n.*?(?=^## |\Z)",
                                "",
                                text,
                            )
                            path.write_text(text, encoding="utf-8")
                            self.assertIn(
                                "missing_route_anchor",
                                self.validator.validate_pack(self.project)["error_codes"],
                            )
                        finally:
                            self.project = old_project

    def test_missing_file_placeholder_and_empty_required_heading_fail(self) -> None:
        (self.project / "assets.md").unlink()
        self.write("publish.md", "# Publish\n\nTODO\n")
        script = (self.project / "script.md").read_text(encoding="utf-8")
        self.write("script.md", script.replace("这是目标的完整可执行内容。", ""))
        result = self.validator.validate_pack(self.project)
        self.assertFalse(result["valid"])
        self.assertIn("missing_file", result["error_codes"])
        self.assertIn("unresolved_placeholder", result["error_codes"])
        self.assertIn("empty_required_heading", result["error_codes"])

    def test_placeholders_and_headings_in_comments_or_fences_do_not_count(self) -> None:
        self.write("publish.md", "# Publish\n\n真实内容。\n<!-- TODO -->\n```text\nFIXME\n```\n")
        self.assertTrue(self.validator.validate_pack(self.project)["valid"])
        self.write("outline.md", "# Outline\n\n<!-- ## 中段推进\n伪内容 -->\n```\n## 结尾兑现\n伪内容\n```\n")
        self.assertIn("missing_route_anchor", self.validator.validate_pack(self.project)["error_codes"])

    def test_unclosed_and_long_closed_fences_hide_fake_content_through_eof(self) -> None:
        for closing in ("", "````"):
            with self.subTest(closing=closing or "unclosed"):
                self.make_valid()
                self.write(
                    "outline.md",
                    "# Outline\n\n```text\n## 中段推进\n伪造推进。\n"
                    "## 结尾兑现\n伪造兑现。\nTODO\n" + closing + "\n",
                )
                result = self.validator.validate_pack(self.project)
                self.assertIn("missing_route_anchor", result["error_codes"])
                self.assertNotIn("unresolved_placeholder", result["error_codes"])

    def test_unclosed_multiline_html_comment_hides_fake_heading_and_placeholder(self) -> None:
        self.write(
            "outline.md",
            "# Outline\n\n真实说明。\n<!-- 尚未闭合\n## 中段推进\n伪造。\n"
            "## 结尾兑现\n伪造。\nFIXME\n",
        )
        result = self.validator.validate_pack(self.project)
        self.assertIn("missing_route_anchor", result["error_codes"])
        self.assertNotIn("unresolved_placeholder", result["error_codes"])

    def test_cr_only_fence_lines_preserve_line_boundaries(self) -> None:
        visible = self.validator._visible_markdown(
            "before\r```text\rTODO\r````\rafter\r"
        )
        self.assertNotIn("TODO", visible)
        self.assertEqual(5, visible.count("\r"))

    def test_bad_sources_and_review_contracts_propagate_stable_codes(self) -> None:
        self.write("script.md", (self.project / "script.md").read_text() + "\n[C01]\n")
        result = self.validator.validate_pack(self.project)
        self.assertIn("factual_marker_without_research", result["error_codes"])

        review_path = self.project / "review.md"
        review = json.loads(review_path.read_text().split("---")[1])
        review["total_score"] = 79
        review["core_dimensions"][next(iter(review["core_dimensions"]))]["score"] = 6
        review["base_gates"][next(iter(review["base_gates"]))] = False
        self.write("review.md", "---\n" + json.dumps(review) + "\n---\n# Review\n通过说明。\n")
        codes = self.validator.validate_pack(self.project)["error_codes"]
        self.assertIn("review_total_below_80", codes)
        self.assertIn("review_core_dimension_below_7", codes)
        self.assertIn("review_base_gate_failed", codes)

    def test_frontmatter_rejects_duplicate_keys_nonfinite_and_extra_review_fields(self) -> None:
        sources = self.project / "sources.md"
        sources.write_text(
            '---\n{"schema_version":1,"schema_version":1,"research_required":false,'
            '"decision_reason":"完整理由","sources":[],"claims":[]}\n---\n# Sources\n内容。\n',
            encoding="utf-8",
        )
        self.assertIn("invalid_sources_frontmatter", self.validator.validate_pack(self.project)["error_codes"])
        self.make_valid()
        review = self.project / "review.md"
        raw = review.read_text(encoding="utf-8").replace('"total_score": 80', '"total_score": NaN')
        review.write_text(raw, encoding="utf-8")
        self.assertIn("invalid_review_frontmatter", self.validator.validate_pack(self.project)["error_codes"])
        self.make_valid()
        raw = review.read_text(encoding="utf-8").replace('"revision_count": 0', '"revision_count": 0, "extra": true')
        review.write_text(raw, encoding="utf-8")
        self.assertIn("invalid_review_schema", self.validator.validate_pack(self.project)["error_codes"])

    def test_review_requires_exact_dimensions_weights_and_boundary_scores(self) -> None:
        path = self.project / "review.md"
        review = json.loads(path.read_text(encoding="utf-8").split("---")[1])
        dimension = next(iter(review["core_dimensions"]))
        review["core_dimensions"][dimension]["score"] = 7
        for name in review["core_dimensions"]:
            if name != dimension:
                review["core_dimensions"][name]["score"] = 25 / 3
        review["total_score"] = 80
        path.write_text("---\n" + json.dumps(review) + "\n---\n# Review\n完整复核。\n", encoding="utf-8")
        self.assertTrue(self.validator.validate_pack(self.project)["valid"])
        review["core_dimensions"]["错误维度"] = review["core_dimensions"].pop(dimension)
        review["core_dimensions"][next(iter(review["core_dimensions"]))]["weight"] = 19
        path.write_text("---\n" + json.dumps(review) + "\n---\n# Review\n完整复核。\n", encoding="utf-8")
        codes = self.validator.validate_pack(self.project)["error_codes"]
        self.assertIn("invalid_review_dimensions", codes)
        self.assertIn("invalid_review_weights", codes)

    def test_review_total_must_equal_recomputed_weighted_score(self) -> None:
        path = self.project / "review.md"
        review = json.loads(path.read_text(encoding="utf-8").split("---")[1])
        review["total_score"] = 81
        path.write_text("---\n" + json.dumps(review) + "\n---\n# Review\n完整复核。\n", encoding="utf-8")
        self.assertIn("review_total_mismatch", self.validator.validate_pack(self.project)["error_codes"])

    def test_route_weights_are_canonical_and_cannot_be_manipulated(self) -> None:
        path = self.project / "review.md"
        review = json.loads(path.read_text(encoding="utf-8").split("---")[1])
        scores = (7, 10, 7, 7, 7)
        manipulated_weights = (1, 96, 1, 1, 1)
        for dimension, score, weight in zip(
            EXPECTED_DIMENSIONS["short-form"], scores, manipulated_weights
        ):
            review["core_dimensions"][dimension] = {"score": score, "weight": weight}
        review["total_score"] = 98.8
        path.write_text("---\n" + json.dumps(review) + "\n---\n# Review\n完整复核。\n", encoding="utf-8")
        result = self.validator.validate_pack(self.project)
        self.assertFalse(result["valid"])
        self.assertIn("invalid_review_weights", result["error_codes"])

    def test_boolean_canonical_looking_weight_is_invalid(self) -> None:
        path = self.project / "review.md"
        review = json.loads(path.read_text(encoding="utf-8").split("---")[1])
        dimension = next(iter(review["core_dimensions"]))
        review["core_dimensions"][dimension]["weight"] = True
        path.write_text("---\n" + json.dumps(review) + "\n---\n# Review\n完整复核。\n", encoding="utf-8")
        self.assertIn("invalid_review_weights", self.validator.validate_pack(self.project)["error_codes"])

    def test_huge_json_integers_are_deterministic_content_errors(self) -> None:
        huge = 10**1000
        cases = (
            ("total", "invalid_review_schema"),
            ("score", "invalid_review_schema"),
            ("weight", "invalid_review_weights"),
        )
        for field, expected_code in cases:
            with self.subTest(field=field):
                self.make_valid()
                path = self.project / "review.md"
                review = json.loads(path.read_text(encoding="utf-8").split("---")[1])
                dimension = next(iter(review["core_dimensions"]))
                if field == "total":
                    review["total_score"] = huge
                else:
                    review["core_dimensions"][dimension][field] = huge
                path.write_text(
                    "---\n" + json.dumps(review) + "\n---\n# Review\n完整复核。\n",
                    encoding="utf-8",
                )
                result = self.validator.validate_pack(self.project)
                self.assertFalse(result["valid"])
                self.assertIn(expected_code, result["error_codes"])

    def test_review_object_order_is_irrelevant_but_zero_weight_is_invalid(self) -> None:
        path = self.project / "review.md"
        review = json.loads(path.read_text(encoding="utf-8").split("---")[1])
        review["core_dimensions"] = dict(reversed(list(review["core_dimensions"].items())))
        review["base_gates"] = dict(reversed(list(review["base_gates"].items())))
        path.write_text("---\n" + json.dumps(review) + "\n---\n# Review\n完整复核。\n", encoding="utf-8")
        self.assertTrue(self.validator.validate_pack(self.project)["valid"])
        first = next(iter(review["core_dimensions"]))
        second = next(iter(key for key in review["core_dimensions"] if key != first))
        review["core_dimensions"][first]["weight"] = 0
        review["core_dimensions"][second]["weight"] += 20
        path.write_text("---\n" + json.dumps(review) + "\n---\n# Review\n完整复核。\n", encoding="utf-8")
        self.assertIn("invalid_review_weights", self.validator.validate_pack(self.project)["error_codes"])

    def test_every_base_gate_is_a_veto_and_passed_must_be_true(self) -> None:
        for gate in self.validator.BASE_GATES:
            with self.subTest(gate=gate):
                self.make_valid()
                path = self.project / "review.md"
                review = json.loads(path.read_text(encoding="utf-8").split("---")[1])
                review["base_gates"][gate] = False
                path.write_text("---\n" + json.dumps(review) + "\n---\n# Review\n完整复核。\n", encoding="utf-8")
                self.assertIn("review_base_gate_failed", self.validator.validate_pack(self.project)["error_codes"])
        self.make_valid()
        path = self.project / "review.md"
        review = json.loads(path.read_text(encoding="utf-8").split("---")[1])
        review["passed"] = False
        path.write_text("---\n" + json.dumps(review) + "\n---\n# Review\n完整复核。\n", encoding="utf-8")
        self.assertIn("review_not_passed", self.validator.validate_pack(self.project)["error_codes"])

    def test_all_approvals_are_required(self) -> None:
        self.state.reopen(self.project, "script", "继续修改")
        result = self.validator.validate_pack(self.project)
        self.assertIn("script_not_approved", result["error_codes"])

    def test_each_approval_gate_is_reported_when_reopened(self) -> None:
        for stage in self.state.STAGES:
            with self.subTest(stage=stage), tempfile.TemporaryDirectory() as directory:
                result = self.initializer.init_project(
                    Path(directory), "Approval", "short-form", date="2026-07-17"
                )
                old_project = self.project
                self.project = Path(result["path"])
                try:
                    self.make_valid()
                    self.state.reopen(self.project, stage, "重新检查这个阶段")
                    self.assertIn(
                        f"{stage}_not_approved",
                        self.validator.validate_pack(self.project)["error_codes"],
                    )
                finally:
                    self.project = old_project

    def test_exact_topology_and_safe_filesystem_are_enforced(self) -> None:
        self.write("extra.md", "# Extra\n\n内容。\n")
        self.assertIn("unexpected_project_entry", self.validator.validate_pack(self.project)["error_codes"])
        (self.project / "extra.md").unlink()
        target = self.project / "assets.md"
        target.unlink()
        target.symlink_to(self.project / "brief.md")
        with self.assertRaises(self.validator.StudioError):
            self.validator.validate_pack(self.project)

    def test_untrusted_entry_name_is_never_reflected_in_result(self) -> None:
        secret = "SECRET-token-extra.md"
        self.write(secret, "content")
        result = self.validator.validate_pack(self.project)
        self.assertNotIn(secret, json.dumps(result, ensure_ascii=False))

    def test_non_utf8_and_oversized_files_raise_safe_error(self) -> None:
        (self.project / "assets.md").write_bytes(b"\xff")
        with self.assertRaises(self.validator.StudioError):
            self.validator.validate_pack(self.project)

    def test_per_file_and_aggregate_limits_are_enforced(self) -> None:
        self.write("assets.md", "x" * (self.validator.MAX_FILE_BYTES + 1))
        with self.assertRaises(self.validator.StudioError):
            self.validator.validate_pack(self.project)

    def test_completion_counts_preloaded_project_state_in_aggregate_limit(self) -> None:
        targets = ["assets.md", "publish.md", "storyboard.md", "concepts.md"]
        other_size = sum(
            path.stat().st_size
            for path in self.project.glob("*.md")
            if path.name not in targets
        )
        remaining = self.validator.MAX_PACK_BYTES - other_size
        for name in targets:
            size = min(self.validator.MAX_FILE_BYTES, remaining)
            self.write(name, "x" * size)
            remaining -= size
        self.assertEqual(0, remaining)
        with self.assertRaises(self.state.StudioError):
            self.state.complete(self.project)
        self.make_valid()
        chunk = "x" * (9 * 1024 * 1024)
        for name in ("assets.md", "publish.md", "storyboard.md", "concepts.md"):
            self.write(name, chunk)
        with self.assertRaises(self.validator.StudioError):
            self.validator.validate_pack(self.project)

    def test_history_accepts_safe_empty_tombstone_and_rejects_bad_entries(self) -> None:
        tombstone = self.project / "history" / (".reopen-delete-" + "a" * 32)
        tombstone.mkdir(mode=0o700)
        self.assertTrue(self.validator.validate_pack(self.project)["valid"])
        (tombstone / "payload").write_text("unsafe", encoding="utf-8")
        with self.assertRaises(self.validator.StudioError):
            self.validator.validate_pack(self.project)
        (tombstone / "payload").unlink()
        (self.project / "history" / "unknown").mkdir()
        self.assertIn("invalid_history_entry", self.validator.validate_pack(self.project)["error_codes"])

    def test_history_error_never_echoes_untrusted_entry_name(self) -> None:
        secret = "SECRET-history-entry"
        (self.project / "history" / secret).mkdir()
        result = self.validator.validate_pack(self.project)
        self.assertIn("invalid_history_entry", result["error_codes"])
        self.assertNotIn(secret, json.dumps(result, ensure_ascii=False))

    def test_history_entry_count_and_aggregate_bytes_are_bounded(self) -> None:
        history = self.project / "history"
        for index in range(self.validator.MAX_HISTORY_ENTRIES + 1):
            (history / f"unknown-{index:04d}").mkdir()
        with self.assertRaises(self.validator.StudioError):
            self.validator.validate_pack(self.project)

        for entry in history.iterdir():
            entry.rmdir()
        self.write("script.md", (self.project / "script.md").read_text() + "x" * (9 * 1024 * 1024))
        for index in range(4):
            self.state.reopen(self.project, "script", f"归档大型脚本 {index}")
            self.state.approve(self.project, "script")
        with self.assertRaises(self.validator.StudioError):
            self.validator.validate_pack(self.project)

    def test_history_manifest_artifacts_must_match_stage_and_downstream_only(self) -> None:
        self.state.reopen(self.project, "outline", "重写大纲")
        self.state.approve(self.project, "outline")
        self.state.approve(self.project, "script")
        snapshot = next(path for path in (self.project / "history").iterdir() if not path.name.startswith("."))
        manifest_path = snapshot / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        (snapshot / "brief.md").write_bytes((self.project / "brief.md").read_bytes())
        manifest["affected_artifacts"] = sorted([*manifest["affected_artifacts"], "brief.md"])
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        self.assertIn("invalid_history_snapshot", self.validator.validate_pack(self.project)["error_codes"])

    def test_history_manifest_reason_surrogate_is_invalid_content(self) -> None:
        self.state.reopen(self.project, "script", "正常归档原因")
        self.state.approve(self.project, "script")
        snapshot = next(
            path for path in (self.project / "history").iterdir() if not path.name.startswith(".")
        )
        manifest_path = snapshot / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["reason"] = "\ud800"
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=True), encoding="utf-8"
        )
        result = self.validator.validate_pack(self.project)
        self.assertFalse(result["valid"])
        self.assertIn("invalid_history_snapshot", result["error_codes"])

    def test_valid_reopen_snapshot_is_accepted_and_tampering_is_detected(self) -> None:
        self.state.reopen(self.project, "script", "发现需修改的脚本")
        self.state.approve(self.project, "script")
        snapshot = next(path for path in (self.project / "history").iterdir() if not path.name.startswith("."))
        self.assertTrue(self.validator.validate_pack(self.project)["valid"])
        (snapshot / "manifest.json").write_text("{}", encoding="utf-8")
        self.assertIn("invalid_history_snapshot", self.validator.validate_pack(self.project)["error_codes"])

    def test_completion_is_atomic_idempotent_and_reopenable(self) -> None:
        before = (self.project / "project.yaml").read_bytes()
        result = self.state.complete(self.project)
        self.assertEqual("completed", result["status"])
        self.assertEqual("complete", self.state.status(self.project)["stage"])
        completed_state = self.state.load_state(self.project)
        self.assertRegex(completed_state["completion_digest"], r"^[0-9a-f]{64}$")
        self.assertTrue(self.validator.validate_pack(self.project)["valid"])
        self.assertEqual("already_complete", self.state.complete(self.project)["status"])
        self.state.reopen(self.project, "script", "完成后发现问题")
        self.assertEqual("script_pending", self.state.status(self.project)["stage"])
        self.assertIsNone(self.state.load_state(self.project)["completion_digest"])
        self.assertNotEqual(before, (self.project / "project.yaml").read_bytes())

    def test_completed_pack_detects_later_artifact_edit_by_semantic_digest(self) -> None:
        self.state.complete(self.project)
        self.write("publish.md", "# Publish\n\n完成后被修改的有效内容。\n")
        result = self.validator.validate_pack(self.project)
        self.assertFalse(result["valid"])
        self.assertIn("completion_digest_mismatch", result["error_codes"])
        completion = self.state.complete(self.project)
        self.assertEqual("blocked", completion["status"])
        self.assertIn(
            "completion_digest_mismatch", completion["validation"]["error_codes"]
        )

    def test_completed_pack_digest_binds_project_metadata_and_dispositions(self) -> None:
        self.state.complete(self.project)
        original = self.state.load_state(self.project)
        mutations = (
            ("title", lambda state: state["project"].__setitem__("title", "新标题")),
            ("platform", lambda state: state["project"].__setitem__("platform", "新平台")),
            ("profile", lambda state: state["project"].__setitem__("profile_id", "new-profile")),
            ("date", lambda state: state["project"].__setitem__("date", "2026-07-18")),
            ("secondary", lambda state: state["project"].__setitem__("secondary_type", "long-form")),
            ("research", lambda state: state["research"].__setitem__("disposition", "required")),
            ("sources", lambda state: state["sources"].__setitem__("disposition", "captured")),
        )
        for label, mutate in mutations:
            with self.subTest(field=label):
                changed = json.loads(json.dumps(original))
                mutate(changed)
                self.state.save_state(self.project, changed)
                validation = self.validator.validate_pack(self.project)
                self.assertIn("completion_digest_mismatch", validation["error_codes"])
                completion = self.state.complete(self.project)
                self.assertEqual("blocked", completion["status"])
                self.assertIn(
                    "completion_digest_mismatch",
                    completion["validation"]["error_codes"],
                )
                self.state.save_state(self.project, original)

    def test_precomplete_and_postcomplete_semantic_digest_are_identical(self) -> None:
        with self.state._locked_project(self.project) as (_, project_fd):
            state, state_bytes, state_digest = self.state._load_state_with_size_at(project_fd)
            result, _, precomplete_digest = self.validator._validate_pack_at(
                project_fd,
                state=state,
                state_byte_count=state_bytes,
                state_digest=state_digest,
                capture_fingerprint=True,
            )
        self.assertTrue(result["valid"])
        self.state.complete(self.project)
        completed = self.state.load_state(self.project)
        self.assertEqual(precomplete_digest, completed["completion_digest"])
        self.assertTrue(self.validator.validate_pack(self.project)["valid"])

    def test_missing_ordinary_artifact_blocks_completion_without_raising(self) -> None:
        (self.project / "assets.md").unlink()
        before = (self.project / "project.yaml").read_bytes()
        result = self.state.complete(self.project)
        self.assertEqual("blocked", result["status"])
        self.assertIn("missing_file", result["validation"]["error_codes"])
        self.assertEqual(before, (self.project / "project.yaml").read_bytes())

    def test_concurrent_completion_serializes_to_one_transition(self) -> None:
        with ThreadPoolExecutor(max_workers=8) as executor:
            results = list(executor.map(lambda _: self.state.complete(self.project), range(16)))
        self.assertEqual(1, sum(result["status"] == "completed" for result in results))
        self.assertEqual(15, sum(result["status"] == "already_complete" for result in results))

    def test_validation_and_completion_share_a_consistent_locked_snapshot(self) -> None:
        with ThreadPoolExecutor(max_workers=8) as executor:
            futures = [executor.submit(self.validator.validate_pack, self.project) for _ in range(8)]
            futures += [executor.submit(self.state.complete, self.project) for _ in range(8)]
            results = [future.result() for future in futures]
        self.assertTrue(all(result.get("valid", True) for result in results))
        self.assertEqual("complete", self.state.status(self.project)["stage"])

    def test_unknown_primary_route_is_a_state_error(self) -> None:
        state = self.state.load_state(self.project)
        state["project"]["primary_type"] = "unknown-route"
        self.state.save_state(self.project, state)
        self.assertIn("invalid_state", self.validator.validate_pack(self.project)["error_codes"])

    def test_escaped_unpaired_surrogate_state_is_deterministic_invalid_state(self) -> None:
        state_path = self.project / "project.yaml"
        original = state_path.read_bytes()
        replacements = (
            (b'title: "Pack Test"', b'title: "\\ud800"'),
            (b'disposition: "undecided"', b'disposition: "\\ud800"'),
        )
        for old, new in replacements:
            with self.subTest(field=old.split(b":", 1)[0]):
                self.assertIn(old, original)
                state_path.write_bytes(original.replace(old, new, 1))
                result = self.validator.validate_pack(self.project)
                self.assertFalse(result["valid"])
                self.assertIn("invalid_state", result["error_codes"])
                state_path.write_bytes(original)

    def test_validator_and_completion_cli_emit_sanitized_json(self) -> None:
        stream = StringIO()
        with redirect_stdout(stream):
            exit_code = self.validator.main(["--project", str(self.project)])
        self.assertEqual(0, exit_code)
        self.assertTrue(json.loads(stream.getvalue())["valid"])
        stream = StringIO()
        with redirect_stdout(stream):
            exit_code = self.state.main(["complete", "--project", str(self.project)])
        self.assertEqual(0, exit_code)
        self.assertEqual("completed", json.loads(stream.getvalue())["status"])

    def test_completion_publication_failure_preserves_original_bytes(self) -> None:
        before = (self.project / "project.yaml").read_bytes()
        real_rename = self.state.os.rename

        def fail_state(source, destination, *args, **kwargs):
            if destination == "project.yaml":
                raise OSError("publication failed")
            return real_rename(source, destination, *args, **kwargs)

        with mock.patch.object(self.state.os, "rename", side_effect=fail_state):
            with self.assertRaises(self.state.StudioError):
                self.state.complete(self.project)
        self.assertEqual(before, (self.project / "project.yaml").read_bytes())

    def test_completion_reverifies_pack_after_validation_before_publication(self) -> None:
        before = (self.project / "project.yaml").read_bytes()

        def mutate_after_validation(name: str) -> None:
            if name == "validated":
                self.write("publish.md", "# Publish\n\n验证后被替换的内容。\n")

        with mock.patch.object(self.state, "_completion_boundary", side_effect=mutate_after_validation):
            result = self.state.complete(self.project)
        self.assertEqual("blocked", result["status"])
        self.assertIn("pack_changed_during_completion", result["validation"]["error_codes"])
        self.assertEqual(before, (self.project / "project.yaml").read_bytes())

    def test_completion_accepts_content_stable_from_validation_onward(self) -> None:
        real_load = self.state._load_state_with_size_at

        def mutate_during_state_load(project_fd: int):
            loaded = real_load(project_fd)
            self.write("publish.md", "# Publish\n\n状态读取期间被替换但仍属有效的内容。\n")
            return loaded

        with mock.patch.object(
            self.state, "_load_state_with_size_at", side_effect=mutate_during_state_load
        ):
            result = self.state.complete(self.project)
        self.assertEqual("completed", result["status"])

    def test_completion_rejects_aba_restore_of_prevalidation_invalid_content(self) -> None:
        invalid_a = "# Publish\n\nTODO\n"
        valid_b = "# Publish\n\n验证期间临时出现的完整有效发布内容。\n"
        self.write("publish.md", invalid_a)
        state_before = (self.project / "project.yaml").read_bytes()
        real_load = self.state._load_state_with_size_at

        def swap_to_valid_during_state_load(project_fd: int):
            loaded = real_load(project_fd)
            self.write("publish.md", valid_b)
            return loaded

        def restore_invalid_at_boundary(name: str) -> None:
            if name == "validated":
                self.write("publish.md", invalid_a)

        with (
            mock.patch.object(
                self.state,
                "_load_state_with_size_at",
                side_effect=swap_to_valid_during_state_load,
            ),
            mock.patch.object(
                self.state,
                "_completion_boundary",
                side_effect=restore_invalid_at_boundary,
            ),
        ):
            result = self.state.complete(self.project)
        self.assertEqual("blocked", result["status"])
        self.assertIn("pack_changed_during_completion", result["validation"]["error_codes"])
        self.assertEqual(state_before, (self.project / "project.yaml").read_bytes())

    def test_save_entry_mutation_cannot_publish_complete_state(self) -> None:
        before = (self.project / "project.yaml").read_bytes()
        real_save = self.state._save_state_at

        def mutate_before_save(project_fd: int, state: dict, *args, **kwargs):
            self.write("publish.md", "# Publish\n\n保存入口发生的合法内容替换。\n")
            return real_save(project_fd, state, *args, **kwargs)

        with mock.patch.object(self.state, "_save_state_at", side_effect=mutate_before_save):
            with self.assertRaises(self.state.StudioError):
                self.state.complete(self.project)
        self.assertEqual(before, (self.project / "project.yaml").read_bytes())

    def test_failed_completion_does_not_change_published_state_bytes(self) -> None:
        self.write("publish.md", "# Publish\n\nTBD\n")
        before = (self.project / "project.yaml").read_bytes()
        result = self.state.complete(self.project)
        self.assertEqual("blocked", result["status"])
        self.assertEqual(before, (self.project / "project.yaml").read_bytes())


if __name__ == "__main__":
    unittest.main()
