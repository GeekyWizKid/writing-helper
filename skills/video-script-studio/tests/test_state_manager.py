from __future__ import annotations

import io
import json
import os
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

from helpers import load_script_module


STAGES = ("brief", "research", "concept", "outline", "script")
STAGE_FILES = {
    "brief": "brief.md",
    "research": "research.md",
    "concept": "concepts.md",
    "outline": "outline.md",
    "script": "script.md",
}


class StateManagerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.module = load_script_module("state_manager")
        cls.initializer = load_script_module("init_project")

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        result = self.initializer.init_project(
            Path(self.temporary.name),
            "State Test",
            "short-form",
            date="2026-07-17",
        )
        self.project = Path(result["path"])

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def approve_through(self, final_stage: str) -> None:
        for stage in STAGES[: STAGES.index(final_stage) + 1]:
            self.module.approve(self.project, stage)

    def test_exports_exact_stage_contract(self) -> None:
        self.assertEqual(STAGES, self.module.STAGES)
        for name in ("load_state", "save_state", "approve", "reopen", "status"):
            self.assertTrue(callable(getattr(self.module, name)))

    def test_approves_all_stages_in_order(self) -> None:
        for index, stage in enumerate(STAGES):
            result = self.module.approve(self.project, stage)
            self.assertEqual("approved", result["status"])
            state = self.module.load_state(self.project)
            self.assertEqual("approved", state["approvals"][stage])
            expected_stage = (
                "script_approved" if index == len(STAGES) - 1 else f"{STAGES[index + 1]}_pending"
            )
            self.assertEqual(expected_stage, state["stage"])

    def test_rejects_skipped_stage_without_mutating_state(self) -> None:
        before = (self.project / "project.yaml").read_bytes()
        with self.assertRaises(self.module.StudioError):
            self.module.approve(self.project, "research")
        self.assertEqual(before, (self.project / "project.yaml").read_bytes())

    def test_approval_is_idempotent_and_does_not_regress_stage(self) -> None:
        self.module.approve(self.project, "brief")
        self.module.approve(self.project, "research")
        result = self.module.approve(self.project, "brief")
        self.assertEqual("already_approved", result["status"])
        self.assertEqual("concept_pending", self.module.load_state(self.project)["stage"])

    def test_reopen_snapshots_affected_nonempty_files_and_invalidates_downstream(self) -> None:
        self.approve_through("script")
        expected = {}
        for stage in ("concept", "outline", "script"):
            content = f"approved {stage}\n"
            (self.project / STAGE_FILES[stage]).write_text(content, encoding="utf-8")
            expected[STAGE_FILES[stage]] = content

        result = self.module.reopen(self.project, "concept", reason="核心命题改变")
        state = self.module.load_state(self.project)
        self.assertEqual("pending", state["approvals"]["concept"])
        self.assertEqual("invalidated", state["approvals"]["outline"])
        self.assertEqual("invalidated", state["approvals"]["script"])
        self.assertEqual("concept_pending", state["stage"])

        snapshot = Path(result["history_path"])
        self.assertEqual(self.project / "history", snapshot.parent)
        self.assertEqual(expected.keys(), {p.name for p in snapshot.glob("*.md")})
        for filename, content in expected.items():
            self.assertEqual(content, (snapshot / filename).read_text(encoding="utf-8"))
        manifest = json.loads((snapshot / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual("核心命题改变", manifest["reason"])
        self.assertEqual("concept", manifest["stage"])
        self.assertEqual(sorted(expected), manifest["affected_artifacts"])

    def test_reopen_does_not_snapshot_empty_affected_artifact(self) -> None:
        self.approve_through("research")
        (self.project / "research.md").write_text("", encoding="utf-8")
        result = self.module.reopen(self.project, "research", reason="new evidence")
        snapshot = Path(result["history_path"])
        self.assertFalse((snapshot / "research.md").exists())
        manifest = json.loads((snapshot / "manifest.json").read_text(encoding="utf-8"))
        self.assertNotIn("research.md", manifest["affected_artifacts"])

    def test_reopen_requires_an_approved_stage_and_nonblank_bounded_reason(self) -> None:
        for reason in ("", "   ", "x" * 4097):
            with self.subTest(reason_length=len(reason)):
                with self.assertRaises(self.module.StudioError):
                    self.module.reopen(self.project, "brief", reason=reason)
        self.module.approve(self.project, "brief")
        self.module.reopen(self.project, "brief", reason="rewrite")
        with self.assertRaises(self.module.StudioError):
            self.module.reopen(self.project, "brief", reason="again")

    def test_reapproval_after_reopen_can_progress_through_invalidated_stages(self) -> None:
        self.approve_through("script")
        self.module.reopen(self.project, "concept", reason="rewrite")
        for stage in ("concept", "outline", "script"):
            self.module.approve(self.project, stage)
        state = self.module.load_state(self.project)
        self.assertEqual({stage: "approved" for stage in STAGES}, state["approvals"])
        self.assertEqual("script_approved", state["stage"])

    def test_public_save_validates_schema_and_is_atomic_on_replace_failure(self) -> None:
        original = (self.project / "project.yaml").read_bytes()
        state = self.module.load_state(self.project)
        state["approvals"]["unknown"] = "approved"
        with self.assertRaises(self.module.StudioError):
            self.module.save_state(self.project, state)
        self.assertEqual(original, (self.project / "project.yaml").read_bytes())

        valid = self.module.load_state(self.project)
        with mock.patch.object(self.module.os, "rename", side_effect=OSError("boom")):
            with self.assertRaises(self.module.StudioError):
                self.module.save_state(self.project, valid)
        self.assertEqual(original, (self.project / "project.yaml").read_bytes())
        self.assertFalse(any(p.name.startswith(".project.yaml") for p in self.project.iterdir()))

    def test_reopen_rolls_back_snapshot_when_state_publication_fails(self) -> None:
        self.module.approve(self.project, "brief")
        history = self.project / "history"
        original = (self.project / "project.yaml").read_bytes()
        real_rename = self.module.os.rename

        def fail_state_only(source, destination, *args, **kwargs):
            if destination == "project.yaml":
                raise OSError("state publish failed")
            return real_rename(source, destination, *args, **kwargs)

        with mock.patch.object(self.module.os, "rename", side_effect=fail_state_only):
            with self.assertRaises(self.module.StudioError):
                self.module.reopen(self.project, "brief", reason="rewrite")
        self.assertEqual(original, (self.project / "project.yaml").read_bytes())
        self.assertEqual([], list(history.iterdir()))

    def test_existing_snapshot_name_is_never_overwritten(self) -> None:
        self.module.approve(self.project, "brief")
        with mock.patch.object(self.module, "_history_timestamp", return_value="fixed"):
            existing = self.project / "history" / "fixed-brief"
            existing.mkdir()
            marker = existing / "keep.txt"
            marker.write_text("keep", encoding="utf-8")
            with self.assertRaises(self.module.StudioError):
                self.module.reopen(self.project, "brief", reason="rewrite")
            self.assertEqual("keep", marker.read_text(encoding="utf-8"))

    def test_rejects_symlink_project_state_history_and_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as outside:
            outside_path = Path(outside)
            project_link = outside_path / "project-link"
            project_link.symlink_to(self.project, target_is_directory=True)
            with self.assertRaises(self.module.StudioError):
                self.module.load_state(project_link)

            state_path = self.project / "project.yaml"
            state_data = state_path.read_bytes()
            state_path.unlink()
            target = outside_path / "state.yaml"
            target.write_bytes(state_data)
            state_path.symlink_to(target)
            with self.assertRaises(self.module.StudioError):
                self.module.load_state(self.project)
            state_path.unlink()
            state_path.write_bytes(state_data)

            history = self.project / "history"
            history.rmdir()
            history.symlink_to(outside_path, target_is_directory=True)
            self.module.approve(self.project, "brief")
            with self.assertRaises(self.module.StudioError):
                self.module.reopen(self.project, "brief", reason="rewrite")

            history.unlink()
            history.mkdir()

            artifact = self.project / "brief.md"
            artifact.unlink()
            artifact.symlink_to(outside_path / "artifact.md")
            with self.assertRaises(self.module.StudioError):
                self.module.reopen(self.project, "brief", reason="rewrite")

    def test_rejects_fifo_state_and_artifact_without_blocking_or_mutation(self) -> None:
        state_path = self.project / "project.yaml"
        state_data = state_path.read_bytes()
        state_path.unlink()
        os.mkfifo(state_path)
        with self.assertRaises(self.module.StudioError):
            self.module.load_state(self.project)
        state_path.unlink()
        state_path.write_bytes(state_data)

        self.module.approve(self.project, "brief")
        approved_state = state_path.read_bytes()
        artifact = self.project / "brief.md"
        artifact.unlink()
        os.mkfifo(artifact)
        with self.assertRaises(self.module.StudioError):
            self.module.reopen(self.project, "brief", reason="rewrite")
        self.assertEqual(approved_state, state_path.read_bytes())
        self.assertEqual([], list((self.project / "history").iterdir()))

    def test_rejects_malformed_and_oversized_state(self) -> None:
        state_path = self.project / "project.yaml"
        state_path.write_text("not: [supported]\n", encoding="utf-8")
        with self.assertRaises(self.module.StudioError):
            self.module.load_state(self.project)
        state_path.write_bytes(b"x" * (self.module.MAX_STATE_BYTES + 1))
        with self.assertRaises(self.module.StudioError):
            self.module.load_state(self.project)

    def test_concurrent_same_stage_approval_is_serialized_and_idempotent(self) -> None:
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(lambda _: self.module.approve(self.project, "brief"), range(2)))
        self.assertEqual(["already_approved", "approved"], sorted(r["status"] for r in results))
        self.assertEqual("approved", self.module.load_state(self.project)["approvals"]["brief"])

    def test_status_returns_detached_state_and_safe_summary(self) -> None:
        result = self.module.status(self.project)
        self.assertEqual("brief_pending", result["stage"])
        self.assertEqual({stage: "pending" for stage in STAGES}, result["approvals"])
        result["approvals"]["brief"] = "tampered"
        self.assertEqual("pending", self.module.load_state(self.project)["approvals"]["brief"])

    def test_cli_prints_one_json_object_for_success_and_sanitized_failure(self) -> None:
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            code = self.module.main(["status", "--project", str(self.project)])
        self.assertEqual(0, code)
        self.assertEqual(1, len(stdout.getvalue().splitlines()))
        self.assertEqual("brief_pending", json.loads(stdout.getvalue())["stage"])

        secret = "DO-NOT-LEAK"
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            code = self.module.main(["reopen", "--project", str(self.project), "--stage", secret, "--reason", secret])
        self.assertEqual(2, code)
        payload = json.loads(stdout.getvalue())
        self.assertEqual("error", payload["status"])
        self.assertNotIn(secret, stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
