from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

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
                        ".profile.lock",
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

    def test_read_rejects_cross_profile_document_symlink_without_leaking(self) -> None:
        manager = self.require_manager()
        manager.create_profile(self.root, "alpha", "Alpha")
        manager.create_profile(self.root, "beta", "Beta")
        secret = "alpha-private-content"
        manager.update_profile(
            self.root,
            "alpha",
            secret,
            confirmed=True,
            change_note="private alpha update",
        )
        beta_document = self.root / "beta" / "profile.md"
        beta_document.unlink()
        beta_document.symlink_to(self.root / "alpha" / "profile.md")

        with self.assertRaises(self.common.StudioError) as raised:
            manager.read_profile(self.root, "beta")

        self.assertNotIn(secret, str(raised.exception))

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

    def test_confirmed_update_rejects_whitespace_content_without_mutation(self) -> None:
        manager = self.require_manager()
        manager.create_profile(self.root, "main", "主账号")
        before = self._file_tree(self.root / "main")

        with self.assertRaises(self.common.StudioError):
            manager.update_profile(
                self.root,
                "main",
                "  \n\t ",
                confirmed=True,
                change_note="must not clear profile",
            )

        self.assertEqual(before, self._file_tree(self.root / "main"))

    def test_manifest_identity_mismatch_is_rejected_before_any_mutation(self) -> None:
        manager = self.require_manager()
        manager.create_profile(self.root, "main", "主账号")
        manifest_path = self.root / "main" / "versions" / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["profile_id"] = "different-profile"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        before = self._file_tree(self.root / "main")

        with self.assertRaises(self.common.StudioError):
            manager.update_profile(
                self.root,
                "main",
                "must not publish",
                confirmed=True,
                change_note="identity mismatch",
            )

        self.assertEqual(before, self._file_tree(self.root / "main"))

    def test_update_publish_failures_roll_back_and_allow_retry(self) -> None:
        manager = self.require_manager()
        for publish_name in ("profile.md", "manifest.json"):
            with self.subTest(publish_name=publish_name):
                case_root = self.root / publish_name.replace(".", "-")
                manager.create_profile(case_root, "main", "主账号")
                profile_path = case_root / "main"
                before = self._file_tree(profile_path)
                target = (
                    profile_path / "profile.md"
                    if publish_name == "profile.md"
                    else profile_path / "versions" / "manifest.json"
                )
                original_atomic_write = manager.atomic_write_text
                failed = False

                def fail_publish_once(path, content):
                    nonlocal failed
                    if Path(path) == target and not failed:
                        failed = True
                        raise self.common.StudioError("injected publish failure")
                    return original_atomic_write(path, content)

                with patch.object(manager, "atomic_write_text", fail_publish_once):
                    with self.assertRaises(self.common.StudioError):
                        manager.update_profile(
                            case_root,
                            "main",
                            "new transactional content",
                            confirmed=True,
                            change_note="transaction test",
                        )

                self.assertTrue(failed, f"{publish_name} publish was not exercised")
                self.assertEqual(before, self._file_tree(profile_path))
                self.assertFalse((profile_path / "versions" / "v001").exists())
                self.assertEqual([], list(profile_path.glob(".profile-txn-*")))
                self.assertFalse((profile_path / ".transaction.json").exists())

                retried = manager.update_profile(
                    case_root,
                    "main",
                    "new transactional content",
                    confirmed=True,
                    change_note="transaction retry",
                )
                self.assertEqual(1, retried["version"])

    def test_incomplete_rollback_is_recovered_by_next_operation(self) -> None:
        manager = self.require_manager()
        manager.create_profile(self.root, "main", "主账号")
        profile_path = self.root / "main"
        before = self._file_tree(profile_path)
        target = profile_path / "profile.md"
        original_atomic_write = manager.atomic_write_text
        target_failures = 0

        def fail_publish_and_first_rollback(path, content):
            nonlocal target_failures
            if Path(path) == target and target_failures < 2:
                target_failures += 1
                raise self.common.StudioError("injected repeated failure")
            return original_atomic_write(path, content)

        with patch.object(manager, "atomic_write_text", fail_publish_and_first_rollback):
            with self.assertRaises(self.common.StudioError):
                manager.update_profile(
                    self.root,
                    "main",
                    "interrupted content",
                    confirmed=True,
                    change_note="recovery test",
                )

        self.assertEqual(2, target_failures)
        self.assertTrue((profile_path / ".transaction.json").is_file())
        recovered = manager.read_profile(self.root, "main")
        self.assertNotEqual("interrupted content", recovered["content"])
        self.assertEqual(before, self._file_tree(profile_path))
        self.assertFalse((profile_path / ".transaction.json").exists())
        self.assertEqual([], list(profile_path.glob(".profile-txn-*")))

        retried = manager.update_profile(
            self.root,
            "main",
            "recovered content",
            confirmed=True,
            change_note="retry after recovery",
        )
        self.assertEqual(1, retried["version"])

    def test_rejects_untrusted_or_symlinked_profile_roots(self) -> None:
        manager = self.require_manager()
        unsafe_root = Path(self.temporary_directory.name) / "unsafe"
        unsafe_root.mkdir(mode=0o700)
        unsafe_root.chmod(0o777)
        with self.assertRaises(self.common.StudioError):
            manager.create_profile(unsafe_root, "main", "Unsafe")

        actual_root = Path(self.temporary_directory.name) / "actual"
        actual_root.mkdir(mode=0o700)
        symlink_root = Path(self.temporary_directory.name) / "linked"
        symlink_root.symlink_to(actual_root, target_is_directory=True)
        with self.assertRaises(self.common.StudioError):
            manager.create_profile(symlink_root, "main", "Linked")

    def test_symlinked_profile_lock_is_rejected_without_touching_target(self) -> None:
        manager = self.require_manager()
        manager.create_profile(self.root, "main", "主账号")
        lock_path = self.root / "main" / ".profile.lock"
        lock_path.unlink(missing_ok=True)
        outside = Path(self.temporary_directory.name) / "outside-lock"
        outside.write_text("outside-safe", encoding="utf-8")
        lock_path.symlink_to(outside)

        with self.assertRaises(self.common.StudioError):
            manager.read_profile(self.root, "main")

        self.assertEqual("outside-safe", outside.read_text(encoding="utf-8"))

    def test_group_writable_profile_directory_is_rejected(self) -> None:
        manager = self.require_manager()
        manager.create_profile(self.root, "main", "主账号")
        profile_path = self.root / "main"
        profile_path.chmod(0o770)
        self.addCleanup(profile_path.chmod, 0o700)

        with self.assertRaises(self.common.StudioError):
            manager.read_profile(self.root, "main")

    def test_manifest_versions_require_canonical_complete_strict_history(self) -> None:
        manager = self.require_manager()

        def valid_entry(version: int = 1) -> dict:
            return {
                "change_note": "approved change",
                "directory": f"v{version:03d}",
                "timestamp": "2026-07-17T10:00:00Z",
                "version": version,
            }

        variants = {
            "boolean-version": [dict(valid_entry(), version=True)],
            "zero-version": [dict(valid_entry(), version=0, directory="v000")],
            "duplicate-version": [valid_entry(), valid_entry()],
            "decreasing-version": [valid_entry(2), valid_entry(1)],
            "wrong-directory": [dict(valid_entry(), directory="v999")],
            "empty-note": [dict(valid_entry(), change_note=" ")],
            "empty-timestamp": [dict(valid_entry(), timestamp="")],
            "missing-snapshot": [valid_entry()],
        }
        for name, versions in variants.items():
            with self.subTest(name=name):
                case_root = self.root / name
                manager.create_profile(case_root, "main", "主账号")
                profile_path = case_root / "main"
                if name != "missing-snapshot":
                    for entry in versions:
                        version = entry["version"]
                        if type(version) is int and version > 0:
                            snapshot = profile_path / "versions" / f"v{version:03d}"
                            snapshot.mkdir(exist_ok=True)
                            for document in ("profile.md", "style-analysis.md", "constraints.md"):
                                (snapshot / document).write_text("snapshot", encoding="utf-8")
                manifest_path = profile_path / "versions" / "manifest.json"
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                manifest["versions"] = versions
                manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

                with self.assertRaises(self.common.StudioError):
                    manager.read_profile(case_root, "main")

    def test_manifest_rejects_symlinked_snapshot_directory_or_document(self) -> None:
        manager = self.require_manager()
        for symlink_kind in ("directory", "document"):
            with self.subTest(symlink_kind=symlink_kind):
                case_root = self.root / symlink_kind
                manager.create_profile(case_root, "main", "主账号")
                manager.update_profile(
                    case_root,
                    "main",
                    "version one",
                    confirmed=True,
                    change_note="create snapshot",
                )
                profile_path = case_root / "main"
                snapshot_path = profile_path / "versions" / "v001"
                if symlink_kind == "directory":
                    outside_snapshot = case_root / "outside-snapshot"
                    snapshot_path.rename(outside_snapshot)
                    snapshot_path.symlink_to(outside_snapshot, target_is_directory=True)
                else:
                    snapshot_document = snapshot_path / "profile.md"
                    snapshot_document.unlink()
                    snapshot_document.symlink_to(profile_path / "profile.md")

                with self.assertRaises(self.common.StudioError):
                    manager.read_profile(case_root, "main")

    @staticmethod
    def _file_tree(root: Path) -> dict[Path, bytes]:
        return {
            path.relative_to(root): path.read_bytes()
            for path in root.rglob("*")
            if path.is_file() and not path.is_symlink()
        }

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
        self.assertEqual("", rejected.stderr)
        self.assertEqual(
            ["error"], sorted(json.loads(rejected.stdout)), rejected.stdout
        )
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

    def test_cli_parser_errors_are_single_json_objects_on_stdout(self) -> None:
        manager = self.require_manager()
        completed = subprocess.run(
            [
                sys.executable,
                str(Path(manager.__file__)),
                "--root",
                str(self.root),
                "update",
                "main",
                "content",
                "--change-note",
                "missing confirmation",
            ],
            capture_output=True,
            check=False,
            text=True,
        )

        self.assertEqual(2, completed.returncode)
        self.assertEqual("", completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertEqual(["error"], sorted(payload))
        self.assertNotIn("usage:", completed.stdout.lower())


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
