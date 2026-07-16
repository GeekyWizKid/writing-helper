from __future__ import annotations

import builtins
import importlib.util
import io
import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

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

    def test_module_imports_when_fcntl_is_unavailable(self) -> None:
        module_path = SKILL_ROOT / "scripts" / "init_project.py"
        spec = importlib.util.spec_from_file_location(
            "video_script_studio_init_project_without_fcntl", module_path
        )
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader if spec is not None else None)
        module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
        original_import = builtins.__import__

        def import_without_fcntl(
            name: str,
            globals: dict | None = None,
            locals: dict | None = None,
            fromlist: tuple = (),
            level: int = 0,
        ):
            if name == "fcntl":
                raise ImportError("fcntl unavailable")
            return original_import(name, globals, locals, fromlist, level)

        with mock.patch.object(
            builtins, "__import__", side_effect=import_without_fcntl
        ):
            spec.loader.exec_module(module)  # type: ignore[union-attr]

        self.assertIsNone(module.fcntl)

    def test_unsupported_platform_capabilities_fail_before_root_creation(self) -> None:
        expected = (
            "Project initialization requires POSIX Darwin or Linux with fcntl "
            "and getuid support."
        )
        scenarios = (
            ("missing fcntl", mock.patch.object(self.module, "fcntl", None)),
            ("missing getuid", mock.patch.object(self.module.os, "getuid", None)),
            (
                "unsupported platform",
                mock.patch.object(self.module.sys, "platform", "win32"),
            ),
        )
        for scenario, patcher in scenarios:
            with self.subTest(scenario=scenario):
                with tempfile.TemporaryDirectory() as directory:
                    root = Path(directory) / "must-not-exist"
                    with patcher:
                        with self.assertRaises(self.module.StudioError) as raised:
                            self.module.init_project(
                                root, "Unsupported", "short-form", date="2026-07-17"
                            )
                    self.assertEqual(expected, str(raised.exception))
                    self.assertFalse(root.exists())

    def test_main_reports_unsupported_platform_as_safe_json_before_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "must-not-exist"
            stdout = io.StringIO()
            with mock.patch.object(self.module, "fcntl", None), redirect_stdout(stdout):
                exit_code = self.module.main(
                    [
                        "--root",
                        str(root),
                        "--title",
                        "Unsupported",
                        "--primary-type",
                        "short-form",
                    ]
                )

            self.assertEqual(2, exit_code)
            self.assertEqual(
                {
                    "error": (
                        "Project initialization requires POSIX Darwin or Linux "
                        "with fcntl and getuid support."
                    ),
                    "status": "error",
                },
                json.loads(stdout.getvalue()),
            )
            self.assertFalse(root.exists())

    def test_missing_native_rename_symbol_fails_before_root_creation(self) -> None:
        expected = (
            "Project initialization requires POSIX Darwin or Linux with fcntl "
            "and getuid support."
        )
        for platform in ("darwin", "linux"):
            with self.subTest(platform=platform):
                with tempfile.TemporaryDirectory() as directory:
                    root = Path(directory) / "must-not-exist"
                    with (
                        mock.patch.object(self.module.sys, "platform", platform),
                        mock.patch.object(
                            self.module.ctypes, "CDLL", return_value=object()
                        ),
                    ):
                        with self.assertRaises(self.module.StudioError) as raised:
                            self.module.init_project(
                                root, "Unsupported", "short-form", date="2026-07-17"
                            )

                    self.assertEqual(expected, str(raised.exception))
                    self.assertFalse(root.exists())

    def test_main_reports_missing_native_rename_symbol_before_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "must-not-exist"
            stdout = io.StringIO()
            with (
                mock.patch.object(self.module.ctypes, "CDLL", return_value=object()),
                redirect_stdout(stdout),
            ):
                exit_code = self.module.main(
                    [
                        "--root",
                        str(root),
                        "--title",
                        "Unsupported",
                        "--primary-type",
                        "short-form",
                    ]
                )

            self.assertEqual(2, exit_code)
            self.assertEqual(
                {
                    "error": (
                        "Project initialization requires POSIX Darwin or Linux "
                        "with fcntl and getuid support."
                    ),
                    "status": "error",
                },
                json.loads(stdout.getvalue()),
            )
            self.assertFalse(root.exists())

    def test_returns_exact_public_creation_result(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            result = self.module.init_project(
                Path(directory), "Public Result", "short-form", date="2026-07-17"
            )
            self.assertEqual(
                {
                    "status": "created",
                    "project_id": "2026-07-17-Public-Result",
                    "path": str(
                        Path(directory).resolve() / "2026-07-17-Public-Result"
                    ),
                },
                result,
            )

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
                {
                    name: "pending"
                    for name in ("brief", "research", "concept", "outline", "script")
                },
                state["approvals"],
            )
            self.assertEqual("undecided", state["research"]["disposition"])
            self.assertEqual("undecided", state["sources"]["disposition"])
            self.assertEqual(
                {
                    "project_id": "2026-07-17-Launch",
                    "title": "Launch",
                    "primary_type": "commercial",
                    "secondary_type": "short-form",
                    "platform": "douyin",
                    "profile_id": "brand-a",
                    "date": "2026-07-17",
                },
                state["project"],
            )

    def test_collision_resolved_project_id_is_saved_in_state(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.module.init_project(root, "Same title", "short-form", date="2026-07-17")
            result = self.module.init_project(
                root, "Same title", "short-form", date="2026-07-17"
            )

            state = self.common.load_state_yaml(Path(result["path"]) / "project.yaml")
            self.assertEqual("2026-07-17-Same-title-02", state["project"]["project_id"])

    def test_write_exception_leaves_no_project_or_staging_and_retry_uses_base_name(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            real_write = self.module.atomic_write_text
            writes = 0

            def fail_on_third_write(path: Path, content: str) -> None:
                nonlocal writes
                writes += 1
                if writes == 3:
                    raise RuntimeError("injected write failure")
                real_write(path, content)

            with mock.patch.object(
                self.module, "atomic_write_text", side_effect=fail_on_third_write
            ):
                with self.assertRaisesRegex(RuntimeError, "injected write failure"):
                    self.module.init_project(
                        root, "Atomic", "short-form", date="2026-07-17"
                    )

            residue = [
                entry.name
                for entry in root.iterdir()
                if not entry.name.endswith(".lock")
            ]
            self.assertEqual([], residue)

            result = self.module.init_project(
                root, "Atomic", "short-form", date="2026-07-17"
            )
            self.assertEqual("2026-07-17-Atomic", Path(result["path"]).name)

    def test_staging_setup_exception_is_cleaned_up(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            real_chmod = self.module.os.chmod

            def fail_for_staging(path: Path, mode: int) -> None:
                if Path(path).name.startswith(".video-script-studio-staging-"):
                    raise RuntimeError("injected staging setup failure")
                real_chmod(path, mode)

            with mock.patch.object(
                self.module.os, "chmod", side_effect=fail_for_staging
            ):
                with self.assertRaisesRegex(
                    RuntimeError, "injected staging setup failure"
                ):
                    self.module.init_project(
                        root, "Atomic", "short-form", date="2026-07-17"
                    )

            residue = [
                entry.name
                for entry in root.iterdir()
                if not entry.name.endswith(".lock")
            ]
            self.assertEqual([], residue)

    def test_absent_root_is_created_private(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "new-root"
            self.module.init_project(root, "Private", "short-form", date="2026-07-17")
            self.assertEqual(0o700, stat.S_IMODE(root.stat().st_mode))

    def test_rejects_symlink_root(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory)
            real_root = parent / "real-root"
            real_root.mkdir()
            symlink_root = parent / "linked-root"
            symlink_root.symlink_to(real_root, target_is_directory=True)

            with self.assertRaises(self.module.StudioError):
                self.module.init_project(
                    symlink_root, "Unsafe", "short-form", date="2026-07-17"
                )
            self.assertEqual([], list(real_root.iterdir()))

    def test_rejects_group_or_world_writable_root(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "unsafe-root"
            root.mkdir(mode=0o700)
            os.chmod(root, 0o777)

            with self.assertRaises(self.module.StudioError):
                self.module.init_project(
                    root, "Unsafe", "short-form", date="2026-07-17"
                )
            self.assertEqual([], list(root.iterdir()))

    def test_concurrent_initialization_uses_unique_deterministic_suffixes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)

            def create(_: int) -> str:
                return Path(
                    self.module.init_project(
                        root, "Concurrent", "short-form", date="2026-07-17"
                    )["path"]
                ).name

            with ThreadPoolExecutor(max_workers=6) as executor:
                names = sorted(executor.map(create, range(6)))

            self.assertEqual(
                [
                    "2026-07-17-Concurrent",
                    "2026-07-17-Concurrent-02",
                    "2026-07-17-Concurrent-03",
                    "2026-07-17-Concurrent-04",
                    "2026-07-17-Concurrent-05",
                    "2026-07-17-Concurrent-06",
                ],
                names,
            )

    def test_publish_collision_never_replaces_competing_destination(self) -> None:
        for competitor_kind in ("directory", "file", "symlink"):
            with self.subTest(competitor_kind=competitor_kind):
                with tempfile.TemporaryDirectory() as directory:
                    root = Path(directory)
                    real_rename = self.module._rename_directory_noreplace
                    first_publish = True

                    def inject_competitor(
                        source: Path, destination: Path, native_rename
                    ) -> None:
                        nonlocal first_publish
                        if first_publish:
                            first_publish = False
                            if competitor_kind == "directory":
                                destination.mkdir()
                            elif competitor_kind == "file":
                                destination.write_text("competitor", encoding="utf-8")
                            else:
                                destination.symlink_to(root / "competitor-target")
                        real_rename(source, destination, native_rename)

                    with mock.patch.object(
                        self.module,
                        "_rename_directory_noreplace",
                        side_effect=inject_competitor,
                    ):
                        result = self.module.init_project(
                            root, "Race", "short-form", date="2026-07-17"
                        )

                    competitor = root / "2026-07-17-Race"
                    project = Path(result["path"])
                    self.assertEqual("2026-07-17-Race-02", project.name)
                    state = self.common.load_state_yaml(project / "project.yaml")
                    self.assertEqual(project.name, state["project"]["project_id"])
                    if competitor_kind == "directory":
                        self.assertTrue(competitor.is_dir())
                        self.assertEqual([], list(competitor.iterdir()))
                    elif competitor_kind == "file":
                        self.assertEqual(
                            "competitor", competitor.read_text(encoding="utf-8")
                        )
                    else:
                        self.assertTrue(competitor.is_symlink())
                        self.assertEqual(
                            root / "competitor-target", competitor.readlink()
                        )

    def test_rejects_invalid_primary_type(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(self.module.StudioError):
                self.module.init_project(Path(directory), "Title", "podcast")

    def test_secondary_type_accepts_natural_expression_label_and_persists_exactly(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            label = "剧情/个人叙事 · experiment-log（第一季）"
            result = self.module.init_project(
                Path(directory),
                "Expression",
                "narrative",
                secondary_type=label,
                date="2026-07-17",
            )

            state = self.common.load_state_yaml(Path(result["path"]) / "project.yaml")
            self.assertEqual(label, state["project"]["secondary_type"])

    def test_secondary_type_accepts_none_and_two_hundred_unicode_code_points(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            none_result = self.module.init_project(
                root,
                "No expression",
                "short-form",
                secondary_type=None,
                date="2026-07-17",
            )
            boundary_label = "叙" * 200
            boundary_result = self.module.init_project(
                root,
                "Bounded expression",
                "long-form",
                secondary_type=boundary_label,
                date="2026-07-17",
            )

            none_state = self.common.load_state_yaml(
                Path(none_result["path"]) / "project.yaml"
            )
            boundary_state = self.common.load_state_yaml(
                Path(boundary_result["path"]) / "project.yaml"
            )
            self.assertIsNone(none_state["project"]["secondary_type"])
            self.assertEqual(
                boundary_label, boundary_state["project"]["secondary_type"]
            )

    def test_secondary_type_rejects_invalid_metadata_before_filesystem_mutation(
        self,
    ) -> None:
        invalid_values = (
            "",
            " \t ",
            "line\nbreak",
            "delete\x7fcontrol",
            "unsafe\u2028separator",
            "unsafe\u2029separator",
            "bad\ud800label",
            "叙" * 201,
            7,
            ["个人叙事"],
        )
        for value in invalid_values:
            with self.subTest(value=repr(value)):
                with tempfile.TemporaryDirectory() as directory:
                    root = Path(directory) / "must-not-exist"
                    with self.assertRaises(self.module.StudioError):
                        self.module.init_project(
                            root,
                            "Invalid expression",
                            "narrative",
                            secondary_type=value,
                            date="2026-07-17",
                        )
                    self.assertFalse(root.exists())

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

    def test_existing_dangling_symlink_is_never_replaced(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            existing = root / "2026-07-17-Title"
            existing.symlink_to(root / "missing-target", target_is_directory=True)

            result = self.module.init_project(
                root, "Title", "long-form", date="2026-07-17"
            )

            self.assertTrue(existing.is_symlink())
            self.assertEqual(root / "missing-target", existing.readlink())
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
            self.assertEqual({"status", "project_id", "path"}, set(payload))
            self.assertEqual("created", payload["status"])
            self.assertEqual(Path(payload["path"]).name, payload["project_id"])
            self.assertTrue(Path(payload["path"]).is_absolute())
            self.assertTrue(Path(payload["path"]).is_dir())

    def test_cli_rejects_private_date_override(self) -> None:
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
            self.assertEqual(2, completed.returncode)
            self.assertEqual("", completed.stderr)
            self.assertEqual(
                {"error": "Invalid command-line arguments.", "status": "error"},
                json.loads(completed.stdout),
            )

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
