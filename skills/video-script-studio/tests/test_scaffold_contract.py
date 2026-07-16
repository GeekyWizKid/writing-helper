from __future__ import annotations

import json
import re
import tempfile
import unittest
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

    def test_write_json_is_stable_atomic_and_utf8(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "nested" / "data.json"
            self.common.write_json(path, {"z": True, "a": "中文"})
            expected = '{\n  "a": "中文",\n  "z": true\n}\n'
            self.assertEqual(expected, path.read_text(encoding="utf-8"))
            self.assertEqual({"a": "中文", "z": True}, json.loads(expected))

    def test_state_yaml_round_trips_supported_subset_deterministically(self) -> None:
        state = {
            "title": "你好: video",
            "ready": True,
            "missing": None,
            "nested": {"enabled": False, "quote": 'a "value"'},
        }
        dumped = self.common.dump_state_yaml(state)
        self.assertEqual(dumped, self.common.dump_state_yaml(state))
        self.assertEqual(state, self.common.load_state_yaml(dumped))
        self.assertLess(dumped.index("missing:"), dumped.index("nested:"))
        self.assertLess(dumped.index("nested:"), dumped.index("ready:"))

    def test_state_yaml_rejects_unsupported_values_and_invalid_schema(self) -> None:
        with self.assertRaises(self.common.StudioError):
            self.common.dump_state_yaml({"count": 1})
        with self.assertRaises(self.common.StudioError):
            self.common.dump_state_yaml({"valid": "value", 1: "invalid key"})
        for invalid in ("- item\n", "name: 12\n", "child:\n   key: true\n"):
            with self.subTest(invalid=invalid):
                with self.assertRaises(self.common.StudioError):
                    self.common.load_state_yaml(invalid)


if __name__ == "__main__":
    unittest.main()
