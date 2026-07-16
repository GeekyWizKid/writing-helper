from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from helpers import SKILL_ROOT, load_script_module


class ProfileManagerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.common = load_script_module("common")
        module_path = SKILL_ROOT / "scripts" / "profile_manager.py"
        cls.manager = load_script_module("profile_manager") if module_path.is_file() else None

    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.root = Path(self.temporary_directory.name) / "profiles"

    def require_manager(self):
        self.assertIsNotNone(
            self.manager, "profile_manager.py must implement creator profile persistence"
        )
        return self.manager

    def test_create_accepts_safe_ids_and_builds_complete_profile_layout(self) -> None:
        manager = self.require_manager()
        for profile_id in ("main", "creator-02", "studio_account"):
            with self.subTest(profile_id=profile_id):
                result = manager.create_profile(self.root, profile_id, "主账号")
                profile_path = self.root / profile_id
                self.assertEqual(profile_id, result["profile_id"])
                self.assertEqual("主账号", result["display_name"])
                self.assertEqual(
                    {
                        "constraints.md",
                        "profile.md",
                        "samples",
                        "style-analysis.md",
                        "versions",
                    },
                    {path.name for path in profile_path.iterdir()},
                )
                self.assertTrue((profile_path / "samples").is_dir())
                self.assertEqual(
                    {"manifest.json"},
                    {path.name for path in (profile_path / "versions").iterdir()},
                )
                manifest = json.loads(
                    (profile_path / "versions" / "manifest.json").read_text(
                        encoding="utf-8"
                    )
                )
                self.assertEqual(profile_id, manifest["profile_id"])
                self.assertEqual([], manifest["versions"])

    def test_rejects_empty_reserved_traversal_absolute_and_separator_ids(self) -> None:
        manager = self.require_manager()
        invalid_ids = (
            "",
            ".",
            "..",
            "../outside",
            "nested/profile",
            "nested\\profile",
            "/absolute",
            "C:\\absolute",
            " space ",
        )
        for profile_id in invalid_ids:
            with self.subTest(profile_id=profile_id):
                with self.assertRaises(self.common.StudioError):
                    manager.create_profile(self.root, profile_id, "账号")
        self.assertFalse((self.root.parent / "outside").exists())

    def test_profiles_are_isolated_and_cannot_cross_read(self) -> None:
        manager = self.require_manager()
        manager.create_profile(self.root, "alpha", "Alpha")
        manager.create_profile(self.root, "beta", "Beta")
        manager.update_profile(
            self.root,
            "alpha",
            "alpha-only-content",
            confirmed=True,
            change_note="alpha change",
        )

        alpha = manager.read_profile(self.root, "alpha")
        beta = manager.read_profile(self.root, "beta")
        self.assertEqual("alpha-only-content", alpha["content"])
        self.assertNotIn("alpha-only-content", beta["content"])
        with self.assertRaises(self.common.StudioError):
            manager.read_profile(self.root, "../alpha")

    def test_duplicate_create_is_rejected_without_overwriting_files(self) -> None:
        manager = self.require_manager()
        manager.create_profile(self.root, "main", "First Name")
        profile_path = self.root / "main" / "profile.md"
        original = profile_path.read_bytes()

        with self.assertRaises(self.common.StudioError):
            manager.create_profile(self.root, "main", "Replacement Name")

        self.assertEqual(original, profile_path.read_bytes())

    def test_update_requires_explicit_confirmation_without_mutation(self) -> None:
        manager = self.require_manager()
        manager.create_profile(self.root, "main", "主账号")
        profile_path = self.root / "main"
        before = {
            path.relative_to(profile_path): path.read_bytes()
            for path in profile_path.rglob("*")
            if path.is_file()
        }

        with self.assertRaises(self.common.StudioError):
            manager.update_profile(
                self.root,
                "main",
                "new content",
                confirmed=False,
                change_note="test",
            )

        after = {
            path.relative_to(profile_path): path.read_bytes()
            for path in profile_path.rglob("*")
            if path.is_file()
        }
        self.assertEqual(before, after)

    def test_confirmed_updates_snapshot_all_prior_documents_monotonically(self) -> None:
        manager = self.require_manager()
        manager.create_profile(self.root, "main", "主账号")
        profile_path = self.root / "main"
        original_documents = {
            name: (profile_path / name).read_text(encoding="utf-8")
            for name in ("profile.md", "style-analysis.md", "constraints.md")
        }

        first = manager.update_profile(
            self.root,
            "main",
            "first profile content",
            confirmed=True,
            change_note="clarify audience",
        )
        second = manager.update_profile(
            self.root,
            "main",
            "second profile content",
            confirmed=True,
            change_note="add production boundary",
        )

        self.assertEqual(1, first["version"])
        self.assertEqual(2, second["version"])
        self.assertEqual("second profile content", (profile_path / "profile.md").read_text(encoding="utf-8"))
        self.assertEqual(
            original_documents,
            {
                name: (profile_path / "versions" / "v001" / name).read_text(
                    encoding="utf-8"
                )
                for name in original_documents
            },
        )
        self.assertEqual(
            "first profile content",
            (profile_path / "versions" / "v002" / "profile.md").read_text(
                encoding="utf-8"
            ),
        )
        for version in ("v001", "v002"):
            self.assertEqual(
                set(original_documents),
                {path.name for path in (profile_path / "versions" / version).iterdir()},
            )

        manifest = json.loads(
            (profile_path / "versions" / "manifest.json").read_text(encoding="utf-8")
        )
        self.assertEqual([1, 2], [entry["version"] for entry in manifest["versions"]])
        self.assertEqual(
            ["clarify audience", "add production boundary"],
            [entry["change_note"] for entry in manifest["versions"]],
        )
        for entry in manifest["versions"]:
            self.assertRegex(
                entry["timestamp"], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$"
            )

    def test_read_and_list_are_deterministic_and_missing_is_safe_error(self) -> None:
        manager = self.require_manager()
        manager.create_profile(self.root, "zeta", "Zeta")
        manager.create_profile(self.root, "alpha", "Alpha")

        first_read = manager.read_profile(self.root, "alpha")
        second_read = manager.read_profile(self.root, "alpha")
        self.assertEqual(first_read, second_read)
        self.assertEqual(
            ["alpha", "zeta"],
            [item["profile_id"] for item in manager.list_profiles(self.root)],
        )
        self.assertEqual(manager.list_profiles(self.root), manager.list_profiles(self.root))
        with self.assertRaises(self.common.StudioError):
            manager.read_profile(self.root, "missing")
        self.assertEqual([], manager.list_profiles(self.root / "not-created"))

    def test_cli_create_read_update_and_list_emit_json(self) -> None:
        manager = self.require_manager()
        script = Path(manager.__file__)

        def run(*arguments: str, expect_success: bool = True) -> subprocess.CompletedProcess[str]:
            completed = subprocess.run(
                [sys.executable, str(script), "--root", str(self.root), *arguments],
                capture_output=True,
                check=False,
                text=True,
            )
            self.assertEqual(0 if expect_success else 2, completed.returncode, completed.stderr)
            return completed

        created = json.loads(run("create", "main", "主账号").stdout)
        self.assertEqual("main", created["profile_id"])
        rejected = run(
            "update", "main", "unconfirmed", "--change-note", "blocked", expect_success=False
        )
        self.assertEqual("", rejected.stdout)
        updated = json.loads(
            run(
                "update",
                "main",
                "confirmed content",
                "--change-note",
                "approved",
                "--confirmed",
            ).stdout
        )
        self.assertEqual(1, updated["version"])
        self.assertEqual("confirmed content", json.loads(run("read", "main").stdout)["content"])
        self.assertEqual(["main"], [item["profile_id"] for item in json.loads(run("list").stdout)])


class ProfileTemplateTests(unittest.TestCase):
    def test_template_covers_creator_identity_and_style_layers_without_placeholders(self) -> None:
        template_path = SKILL_ROOT / "assets" / "profile-template.md"
        self.assertTrue(template_path.is_file(), "profile-template.md must exist")
        content = template_path.read_text(encoding="utf-8") if template_path.is_file() else ""
        for expected in (
            "创作者身份",
            "目标受众",
            "可信边界",
            "核心价值",
            "长期主题",
            "平台与内容格式",
            "制作约束",
            "稳定风格",
            "可变表达",
            "实验方向",
        ):
            with self.subTest(expected=expected):
                self.assertIn(expected, content)
        self.assertNotRegex(content.lower(), r"\b(?:todo|tbd|fixme)\b")


if __name__ == "__main__":
    unittest.main()
