from __future__ import annotations

import json
import re
import tempfile
import unittest
from collections import UserDict
from pathlib import Path

from helpers import SKILL_ROOT, load_script_module


REQUIRED_FILES = (
    "SKILL.md",
    "agents/openai.yaml",
    "scripts/__init__.py",
    "scripts/common.py",
    "tests/__init__.py",
    "tests/helpers.py",
)


class ScaffoldContractTests(unittest.TestCase):
    def test_required_scaffold_files_exist(self) -> None:
        missing = [path for path in REQUIRED_FILES if not (SKILL_ROOT / path).is_file()]
        self.assertEqual([], missing, f"missing scaffold files: {missing}")

    def test_skill_frontmatter_has_expected_name(self) -> None:
        content = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        self.assertRegex(content, r"(?m)^name: video-script-studio$")

    def test_scaffold_contains_no_placeholders(self) -> None:
        for relative_path in REQUIRED_FILES:
            path = SKILL_ROOT / relative_path
            if not path.is_file():
                continue
            content = path.read_text(encoding="utf-8")
            self.assertIsNone(
                re.search(r"\b(?:TBD|TODO|FIXME)\b", content, re.IGNORECASE),
                f"placeholder found in {relative_path}",
            )

    def test_skill_frontmatter_is_trigger_only_and_skill_is_compact(self) -> None:
        content = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        self.assertLessEqual(len(content.splitlines()), 350)
        match = re.match(r"^---\n(.*?)\n---\n", content, re.DOTALL)
        self.assertIsNotNone(match)
        frontmatter = match.group(1) if match else ""
        description = re.search(r"(?m)^description: (.+)$", frontmatter)
        self.assertIsNotNone(description)
        value = description.group(1) if description else ""
        self.assertTrue(value.startswith("Use when"))
        for literal in (
            "create/新建",
            "resume/继续",
            "revise/修改",
            "quality-check/质检",
            "video-script projects",
        ):
            self.assertIn(literal, value)
        for forbidden in ("workflow", "staged", "through", "first", "then"):
            self.assertNotIn(forbidden, value.lower())

    def test_router_has_exact_order_and_explicit_gates(self) -> None:
        content = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        ordered = (
            "detect new/resume",
            "initialize/load project",
            "load profile",
            "diagnose route",
            "confirm brief",
            "decide/research",
            "confirm research",
            "propose 3 concepts",
            "confirm concept",
            "build experience-node outline",
            "confirm outline",
            "write clean+execution script",
            "estimate duration",
            "confirm script",
            "storyboard/assets/publish",
            "independent review",
            "max two revisions",
            "deterministic validation",
            "complete",
        )
        positions = [content.find(item) for item in ordered]
        self.assertTrue(all(position >= 0 for position in positions), positions)
        self.assertEqual(positions, sorted(positions))
        for literal in (
            "Ask exactly one diagnosis question per turn",
            "Silence is never approval",
            "brief, research, concept, outline, and script",
            "explicit approval",
        ):
            self.assertIn(literal, content)

    def test_resume_and_revision_are_state_first_and_invalidate_downstream(self) -> None:
        content = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        for literal in (
            "On resume, run status before reading or generating artifacts",
            "Treat `project.yaml` and command output as authoritative",
            "read needed current artifacts and relevant `history/` entries",
            "even when the user asks to skip dependency verification",
            "reopen the earliest affected approved stage",
            "invalidates downstream approvals",
            "history/",
            "Never overwrite an approved upstream decision in place",
        ):
            self.assertIn(literal, content)
        self.assertNotIn("`.project.yaml`", content)

    def test_progressive_loading_names_every_reference_and_exactly_one_route(self) -> None:
        content = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        references = (
            "references/discovery.md",
            "references/tool-routing.md",
            "references/research.md",
            "references/short-form.md",
            "references/long-form.md",
            "references/narrative.md",
            "references/commercial.md",
            "references/visual-essay.md",
            "references/storyboard.md",
            "references/publishing.md",
            "references/quality-rubric.md",
        )
        for relative_path in references:
            self.assertIn(relative_path, content)
            self.assertTrue((SKILL_ROOT / relative_path).is_file(), relative_path)
        for literal in (
            "Load exactly one route reference",
            "Do not load the other four route references",
            "Progressive loading",
        ):
            self.assertIn(literal, content)

    def test_external_capabilities_have_explicit_failure_contracts(self) -> None:
        content = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        for literal in (
            "POSIX Darwin or Linux",
            "Detect external capability availability before calling it",
            "Never fabricate a tool result, source, transcript, or successful fallback",
            "Search snippets are incomplete evidence",
            "Report a missing transcript explicitly",
            "stop and ask whether to continue with existing material",
            "No silent degradation",
            "Do not update a profile implicitly",
            "以后都这样",
            "explicit confirmation",
        ):
            self.assertIn(literal, content)

    def test_skill_documents_exact_deterministic_commands(self) -> None:
        content = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        commands = (
            "python3 scripts/init_project.py --root",
            "python3 scripts/state_manager.py status --project",
            "python3 scripts/state_manager.py approve --project",
            "python3 scripts/state_manager.py reopen --project",
            "python3 scripts/state_manager.py complete --project",
            "python3 scripts/profile_manager.py --root",
            "python3 scripts/estimate_duration.py --input",
            "python3 scripts/validate_pack.py --project",
        )
        for command in commands:
            self.assertIn(command, content)
        self.assertIn("validate_sources.py accepts an extracted JSON manifest", content)
        self.assertIn("does not read sources.md frontmatter", content)

    def test_completion_response_contract_is_explicit(self) -> None:
        content = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        for literal in (
            "Completion response",
            "project path",
            "final stage",
            "validation result",
            "saved artifact inventory",
            "unresolved warnings",
            "next permitted action",
        ):
            self.assertIn(literal, content)

    def test_openai_metadata_has_exact_approved_interface(self) -> None:
        content = (SKILL_ROOT / "agents/openai.yaml").read_text(encoding="utf-8")
        self.assertEqual(
            'interface:\n'
            '  display_name: "Video Script Studio"\n'
            '  short_description: "分阶段创作可拍摄的视频脚本与完整制作包"\n'
            '  default_prompt: "使用 $video-script-studio 从需求诊断开始创建一个可恢复的视频脚本项目。"\n',
            content,
        )


class CommonContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.common = load_script_module("common")

    def test_utc_now_iso_is_second_precision_utc(self) -> None:
        value = self.common.utc_now_iso()
        self.assertRegex(value, r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")

    def test_safe_slug_keeps_safe_chinese_english_digits_and_hyphens(self) -> None:
        self.assertEqual("你好-Video-2026", self.common.safe_slug(" 你好 Video_2026! "))
        self.assertEqual("already-safe", self.common.safe_slug("already-safe"))
        self.assertEqual("untitled-video", self.common.safe_slug("?!"))

    def test_safe_slug_respects_utf8_byte_limit_without_splitting_characters(self) -> None:
        ascii_slug = self.common.safe_slug("a" * (self.common.MAX_SLUG_BYTES + 10))
        self.assertEqual(self.common.MAX_SLUG_BYTES, len(ascii_slug.encode("utf-8")))

        multibyte_slug = self.common.safe_slug("你" * 100)
        self.assertEqual("你" * 66, multibyte_slug)
        self.assertLessEqual(
            len(multibyte_slug.encode("utf-8")), self.common.MAX_SLUG_BYTES
        )

        trailing_hyphen = self.common.safe_slug("a" * 199 + "-suffix")
        self.assertEqual("a" * 199, trailing_hyphen)

    def test_atomic_write_text_creates_parents_and_replaces_content(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "nested" / "state.txt"
            self.common.atomic_write_text(path, "first")
            self.common.atomic_write_text(path, "第二版")
            self.assertEqual("第二版", path.read_text(encoding="utf-8"))
            self.assertEqual([], list(path.parent.glob(f".{path.name}.*.tmp")))

    def test_atomic_write_text_wraps_filesystem_failures(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            blocked_parent = Path(directory) / "not-a-directory"
            blocked_parent.write_text("file", encoding="utf-8")
            with self.assertRaises(self.common.StudioError):
                self.common.atomic_write_text(blocked_parent / "state.txt", "content")

    def test_read_json_accepts_only_object_roots(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "data.json"
            path.write_text('{"name": "脚本"}', encoding="utf-8")
            self.assertEqual({"name": "脚本"}, self.common.read_json(path))
            path.write_text("[]", encoding="utf-8")
            with self.assertRaises(self.common.StudioError):
                self.common.read_json(path)
            path.write_text("{broken", encoding="utf-8")
            with self.assertRaises(self.common.StudioError):
                self.common.read_json(path)

    def test_read_json_rejects_non_finite_constants(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "data.json"
            for constant in ("NaN", "Infinity", "-Infinity"):
                path.write_text(f'{{"value": {constant}}}', encoding="utf-8")
                with self.subTest(constant=constant):
                    with self.assertRaises(self.common.StudioError):
                        self.common.read_json(path)

    def test_write_json_is_stable_atomic_and_utf8(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "nested" / "data.json"
            self.common.write_json(path, {"z": True, "a": "中文"})
            expected = '{\n  "a": "中文",\n  "z": true\n}\n'
            self.assertEqual(expected, path.read_text(encoding="utf-8"))
            self.assertEqual({"a": "中文", "z": True}, json.loads(expected))

    def test_write_json_rejects_non_dict_mappings(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "data.json"
            with self.assertRaises(self.common.StudioError):
                self.common.write_json(path, UserDict({"title": "video"}))

    def test_state_yaml_round_trips_supported_subset_deterministically(self) -> None:
        state = {
            "title": "你好: video",
            "ready": True,
            "missing": None,
            "nested": {"enabled": False, "quote": 'a "value"'},
        }
        dumped = self.common.dump_state_yaml(state)
        self.assertEqual(dumped, self.common.dump_state_yaml(state))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.yaml"
            path.write_text(dumped, encoding="utf-8")
            self.assertEqual(state, self.common.load_state_yaml(path))
        self.assertLess(dumped.index("missing:"), dumped.index("nested:"))
        self.assertLess(dumped.index("nested:"), dumped.index("ready:"))

    def test_state_yaml_round_trips_unicode_line_separators_in_values_and_keys(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.yaml"
            for separator in ("\u0085", "\u2028", "\u2029"):
                state = {f"key{separator}part": f"value{separator}part"}
                path.write_text(self.common.dump_state_yaml(state), encoding="utf-8")
                with self.subTest(codepoint=f"U+{ord(separator):04X}"):
                    self.assertEqual(state, self.common.load_state_yaml(path))

    def test_state_yaml_rejects_cyclic_mappings(self) -> None:
        cyclic: dict[str, object] = {}
        cyclic["self"] = cyclic
        with self.assertRaises(self.common.StudioError):
            self.common.dump_state_yaml(cyclic)

    def test_state_yaml_rejects_excessive_dump_depth(self) -> None:
        deep: dict[str, object] = {}
        cursor = deep
        for _ in range(self.common.MAX_STATE_DEPTH + 1):
            child: dict[str, object] = {}
            cursor["child"] = child
            cursor = child
        cursor["value"] = "end"
        with self.assertRaises(self.common.StudioError):
            self.common.dump_state_yaml(deep)

    def test_state_yaml_rejects_excessive_load_depth(self) -> None:
        lines = []
        for depth in range(self.common.MAX_STATE_DEPTH + 2):
            suffix = ' "end"' if depth == self.common.MAX_STATE_DEPTH + 1 else ""
            lines.append("  " * depth + f"level{depth}:" + suffix)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "deep.yaml"
            path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            with self.assertRaises(self.common.StudioError):
                self.common.load_state_yaml(path)

    def test_state_yaml_rejects_unsupported_values_and_invalid_schema(self) -> None:
        with self.assertRaises(self.common.StudioError):
            self.common.dump_state_yaml({"count": 1})
        with self.assertRaises(self.common.StudioError):
            self.common.dump_state_yaml({"valid": "value", 1: "invalid key"})
        with self.assertRaises(self.common.StudioError):
            self.common.dump_state_yaml(UserDict({"title": "video"}))
        with tempfile.TemporaryDirectory() as directory:
            for index, invalid in enumerate(("- item\n", "name: 12\n", "child:\n   key: true\n")):
                path = Path(directory) / f"invalid-{index}.yaml"
                path.write_text(invalid, encoding="utf-8")
                with self.subTest(invalid=invalid):
                    with self.assertRaises(self.common.StudioError):
                        self.common.load_state_yaml(path)

    def test_load_state_yaml_wraps_file_errors(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            missing = Path(directory) / "missing.yaml"
            with self.assertRaises(self.common.StudioError):
                self.common.load_state_yaml(missing)


if __name__ == "__main__":
    unittest.main()
