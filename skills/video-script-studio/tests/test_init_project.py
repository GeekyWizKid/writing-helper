from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from helpers import SKILL_ROOT, load_script_module


ARTIFACTS = {
    "assets": "assets.md",
    "brief": "brief.md",
    "concepts": "concepts.md",
    "outline": "outline.md",
    "publish": "publish.md",
    "research": "research.md",
    "review": "review.md",
    "script": "script.md",
    "sources": "sources.md",
    "storyboard": "storyboard.md",
}


class InitProjectTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.module = load_script_module("init_project")
        cls.common = load_script_module("common")

    def test_creates_safe_chinese_and_english_slug(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            result = self.module.init_project(
                Path(directory), "你好 Video_2026!", "short-form", date="2026-07-17"
            )
            self.assertEqual("2026-07-17-你好-Video-2026", Path(result["path"]).name)

    def test_uses_untitled_video_for_title_without_safe_characters(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            result = self.module.init_project(
                Path(directory), "?!", "visual-essay", date="2026-07-17"
            )
            self.assertEqual("2026-07-17-untitled-video", Path(result["path"]).name)

    def test_collision_suffixes_are_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = [
                Path(
                    self.module.init_project(
                        root, "Same title", "narrative", date="2026-07-17"
                    )["path"]
                ).name
                for _ in range(3)
            ]
            self.assertEqual(
                [
                    "2026-07-17-Same-title",
                    "2026-07-17-Same-title-02",
                    "2026-07-17-Same-title-03",
                ],
                paths,
            )

    def test_creates_complete_exact_artifact_skeleton_and_initial_state(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            result = self.module.init_project(
                Path(directory),
                "Launch",
                "commercial",
                secondary_type="short-form",
                platform="douyin",
                profile_id="brand-a",
                date="2026-07-17",
            )
            project = Path(result["path"])
            self.assertEqual(
                {"project.yaml", "history", *ARTIFACTS.values()},
                {item.name for item in project.iterdir()},
            )
            self.assertTrue((project / "history").is_dir())
            self.assertTrue(all((project / name).is_file() for name in ARTIFACTS.values()))
            for name in ("research.md", "sources.md"):
                self.assertIn(
                    "disposition: undecided",
                    (project / name).read_text(encoding="utf-8"),
                )

            state = self.common.load_state_yaml(project / "project.yaml")
            self.assertEqual("brief_pending", state["stage"])
            self.assertEqual(ARTIFACTS, state["artifacts"])
            self.assertEqual(
                {name: "pending" for name in ARTIFACTS}, state["approvals"]
            )
            self.assertEqual("undecided", state["research"]["disposition"])
            self.assertEqual("undecided", state["sources"]["disposition"])
            self.assertEqual(
                {
                    "title": "Launch",
                    "primary_type": "commercial",
                    "secondary_type": "short-form",
                    "platform": "douyin",
                    "profile_id": "brand-a",
                    "date": "2026-07-17",
                },
                state["project"],
            )

    def test_rejects_invalid_primary_type(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(self.module.StudioError):
                self.module.init_project(Path(directory), "Title", "podcast")

    def test_existing_directory_is_never_overwritten(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            existing = root / "2026-07-17-Title"
            existing.mkdir()
            sentinel = existing / "keep.txt"
            sentinel.write_text("user data", encoding="utf-8")

            result = self.module.init_project(
                root, "Title", "long-form", date="2026-07-17"
            )

            self.assertEqual("user data", sentinel.read_text(encoding="utf-8"))
            self.assertEqual("2026-07-17-Title-02", Path(result["path"]).name)


class InitProjectCliTests(unittest.TestCase):
    SCRIPT = SKILL_ROOT / "scripts" / "init_project.py"

    def test_cli_prints_one_json_success_object(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            completed = subprocess.run(
                [
                    sys.executable,
                    str(self.SCRIPT),
                    "--root",
                    directory,
                    "--title",
                    "CLI 视频",
                    "--primary-type",
                    "short-form",
                    "--date",
                    "2026-07-17",
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(0, completed.returncode, completed.stderr)
            self.assertEqual("", completed.stderr)
            lines = completed.stdout.splitlines()
            self.assertEqual(1, len(lines))
            payload = json.loads(lines[0])
            self.assertEqual("ok", payload["status"])
            self.assertTrue(Path(payload["path"]).is_dir())

    def test_cli_invalid_input_is_sanitized_json_with_exit_two(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            completed = subprocess.run(
                [
                    sys.executable,
                    str(self.SCRIPT),
                    "--root",
                    directory,
                    "--title",
                    "Secret title",
                    "--primary-type",
                    "invalid-type",
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(2, completed.returncode)
            self.assertEqual("", completed.stderr)
            lines = completed.stdout.splitlines()
            self.assertEqual(1, len(lines))
            payload = json.loads(lines[0])
            self.assertEqual("error", payload["status"])
            self.assertEqual({"status", "error"}, set(payload))
            self.assertNotIn(directory, payload["error"])
            self.assertNotIn("Secret title", payload["error"])


if __name__ == "__main__":
    unittest.main()
