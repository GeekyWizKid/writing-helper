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

    def public_history(self, project: Path | None = None) -> list[Path]:
        history = (project or self.project) / "history"
        return sorted(path for path in history.iterdir() if not path.name.startswith("."))

    def assert_hidden_history_is_safe_tombstones(self, project: Path | None = None) -> None:
        history = (project or self.project) / "history"
        for path in history.iterdir():
            if not path.name.startswith("."):
                continue
            self.assertRegex(path.name, self.module._QUARANTINE_PATTERN)
            self.assertTrue(path.is_dir())
            self.assertEqual([], list(path.iterdir()))

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
        self.assertEqual([], self.public_history())
        self.assert_hidden_history_is_safe_tombstones()

    def test_post_commit_directory_fsync_failure_never_deletes_snapshot(self) -> None:
        self.module.approve(self.project, "brief")
        (self.project / "brief.md").write_text("approved brief\n", encoding="utf-8")
        renamed_state = False
        real_rename = self.module.os.rename
        real_fsync = self.module.os.fsync

        def track_state_rename(source, destination, *args, **kwargs):
            nonlocal renamed_state
            result = real_rename(source, destination, *args, **kwargs)
            if destination == "project.yaml":
                renamed_state = True
            return result

        def fail_post_commit_sync(descriptor):
            if renamed_state:
                raise OSError("directory sync failed")
            return real_fsync(descriptor)

        with (
            mock.patch.object(self.module.os, "rename", side_effect=track_state_rename),
            mock.patch.object(self.module.os, "fsync", side_effect=fail_post_commit_sync),
        ):
            with self.assertRaises(self.module.StudioError) as raised:
                self.module.reopen(self.project, "brief", reason="rewrite")
        self.assertIn("committed", str(raised.exception).lower())
        self.assertEqual("brief_pending", self.module.load_state(self.project)["stage"])
        public = [p for p in (self.project / "history").iterdir() if not p.name.startswith(".")]
        self.assertEqual(1, len(public))
        self.assertTrue((public[0] / "manifest.json").is_file())

    def test_reopen_recovers_keyboard_interrupt_at_every_transaction_boundary(self) -> None:
        for boundary in ("staged", "journaled", "snapshot-published", "state-committed"):
            with self.subTest(boundary=boundary), tempfile.TemporaryDirectory() as directory:
                result = self.initializer.init_project(
                    Path(directory), "Crash Test", "short-form", date="2026-07-17"
                )
                project = Path(result["path"])
                self.module.approve(project, "brief")
                (project / "brief.md").write_text("approved\n", encoding="utf-8")

                def interrupt(name):
                    if name == boundary:
                        raise KeyboardInterrupt(name)

                with mock.patch.object(self.module, "_transaction_boundary", side_effect=interrupt):
                    with self.assertRaises(KeyboardInterrupt):
                        self.module.reopen(project, "brief", reason="rewrite")

                state = self.module.status(project)
                history_entries = self.public_history(project)
                self.assert_hidden_history_is_safe_tombstones(project)
                self.assertFalse((project / self.module.JOURNAL_NAME).exists())
                if boundary == "state-committed":
                    self.assertEqual("brief_pending", state["stage"])
                    self.assertEqual(1, len(history_entries))
                    self.assertTrue((history_entries[0] / "manifest.json").is_file())
                else:
                    self.assertEqual("research_pending", state["stage"])
                    self.assertEqual([], history_entries)

    def test_next_operation_recovers_persisted_pre_and_post_commit_journals(self) -> None:
        for boundary in ("snapshot-published", "state-committed"):
            with self.subTest(boundary=boundary), tempfile.TemporaryDirectory() as directory:
                result = self.initializer.init_project(
                    Path(directory), "Journal Test", "short-form", date="2026-07-17"
                )
                project = Path(result["path"])
                self.module.approve(project, "brief")
                real_recover = self.module._recover_transaction_at

                def interrupt(name):
                    if name == boundary:
                        raise KeyboardInterrupt(name)

                def leave_journal_for_next_operation(project_fd, *, scan_orphans=False):
                    if scan_orphans and (project / self.module.JOURNAL_NAME).exists():
                        raise self.module.StudioError("simulated recovery interruption")
                    return real_recover(project_fd, scan_orphans=scan_orphans)

                with (
                    mock.patch.object(self.module, "_transaction_boundary", side_effect=interrupt),
                    mock.patch.object(
                        self.module,
                        "_recover_transaction_at",
                        side_effect=leave_journal_for_next_operation,
                    ),
                ):
                    with self.assertRaises(self.module.StudioError):
                        self.module.reopen(project, "brief", reason="rewrite")
                self.assertTrue((project / self.module.JOURNAL_NAME).is_file())

                state = self.module.status(project)
                self.assertFalse((project / self.module.JOURNAL_NAME).exists())
                history = self.public_history(project)
                self.assert_hidden_history_is_safe_tombstones(project)
                if boundary == "state-committed":
                    self.assertEqual("brief_pending", state["stage"])
                    self.assertEqual(1, len(history))
                else:
                    self.assertEqual("research_pending", state["stage"])
                    self.assertEqual([], history)

    def test_recovery_never_deletes_competing_snapshot_inode(self) -> None:
        self.module.approve(self.project, "brief")
        history = self.project / "history"
        replacement: Path | None = None

        def replace_published_snapshot(name):
            nonlocal replacement
            if name != "snapshot-published":
                return
            published = next(path for path in history.iterdir() if not path.name.startswith("."))
            for child in published.iterdir():
                child.unlink()
            published.rmdir()
            published.mkdir()
            (published / "competitor.txt").write_text("keep", encoding="utf-8")
            replacement = published
            raise KeyboardInterrupt("replacement race")

        with mock.patch.object(
            self.module, "_transaction_boundary", side_effect=replace_published_snapshot
        ):
            with self.assertRaises(self.module.StudioError):
                self.module.reopen(self.project, "brief", reason="rewrite")
        self.assertIsNotNone(replacement)
        self.assertEqual("keep", (replacement / "competitor.txt").read_text(encoding="utf-8"))
        self.assertTrue((self.project / self.module.JOURNAL_NAME).is_file())

    def test_recovery_fsync_failure_keeps_journal_until_next_operation(self) -> None:
        self.module.approve(self.project, "brief")
        real_fsync = self.module.os.fsync
        fail_cleanup_sync = False

        def interrupt_after_publish(name):
            nonlocal fail_cleanup_sync
            if name == "snapshot-published":
                fail_cleanup_sync = True
                raise KeyboardInterrupt(name)

        def fail_first_cleanup_sync(descriptor):
            nonlocal fail_cleanup_sync
            if fail_cleanup_sync:
                fail_cleanup_sync = False
                raise OSError("cleanup directory sync failed")
            return real_fsync(descriptor)

        with (
            mock.patch.object(
                self.module, "_transaction_boundary", side_effect=interrupt_after_publish
            ),
            mock.patch.object(self.module.os, "fsync", side_effect=fail_first_cleanup_sync),
        ):
            with self.assertRaises(self.module.StudioError):
                self.module.reopen(self.project, "brief", reason="rewrite")
        self.assertTrue((self.project / self.module.JOURNAL_NAME).is_file())
        self.assertEqual("research_pending", self.module.status(self.project)["stage"])
        self.assertFalse((self.project / self.module.JOURNAL_NAME).exists())
        self.assertEqual([], self.public_history())
        self.assert_hidden_history_is_safe_tombstones()

    def test_recovery_resumes_partially_removed_bound_snapshot(self) -> None:
        self.module.approve(self.project, "brief")
        history = self.project / "history"

        def interrupt_during_bound_snapshot_cleanup(name):
            if name != "snapshot-published":
                return
            snapshot = next(path for path in history.iterdir() if not path.name.startswith("."))
            next(snapshot.iterdir()).unlink()
            raise KeyboardInterrupt(name)

        with mock.patch.object(
            self.module,
            "_transaction_boundary",
            side_effect=interrupt_during_bound_snapshot_cleanup,
        ):
            with self.assertRaises(KeyboardInterrupt):
                self.module.reopen(self.project, "brief", reason="rewrite")
        self.assertFalse((self.project / self.module.JOURNAL_NAME).exists())
        self.assertEqual([], self.public_history())
        self.assert_hidden_history_is_safe_tombstones()

    def test_recovery_remover_rejects_final_and_staging_live_swaps(self) -> None:
        for boundary, journal_key in (
            ("snapshot-published", "snapshot_name"),
            ("journaled", "staging_name"),
        ):
            with self.subTest(boundary=boundary), tempfile.TemporaryDirectory() as directory:
                result = self.initializer.init_project(
                    Path(directory), "Swap Test", "short-form", date="2026-07-17"
                )
                project = Path(result["path"])
                history = project / "history"
                self.module.approve(project, "brief")
                real_recover = self.module._recover_transaction_at

                def interrupt(name):
                    if name == boundary:
                        raise KeyboardInterrupt(name)

                def persist_transaction(project_fd, *, scan_orphans=False):
                    if scan_orphans and (project / self.module.JOURNAL_NAME).exists():
                        raise self.module.StudioError("leave transaction persisted")
                    return real_recover(project_fd, scan_orphans=scan_orphans)

                with (
                    mock.patch.object(self.module, "_transaction_boundary", side_effect=interrupt),
                    mock.patch.object(
                        self.module,
                        "_recover_transaction_at",
                        side_effect=persist_transaction,
                    ),
                ):
                    with self.assertRaises(self.module.StudioError):
                        self.module.reopen(project, "brief", reason="rewrite")

                journal = json.loads(
                    (project / self.module.JOURNAL_NAME).read_text(encoding="utf-8")
                )
                target_name = journal[journal_key]
                target = history / target_name
                displaced = history / f".displaced-{boundary}"
                real_open = self.module.os.open
                swapped = False
                competitor_identity: tuple[int, int] | None = None

                def swap_after_open(path, flags, *args, **kwargs):
                    nonlocal swapped, competitor_identity
                    descriptor = real_open(path, flags, *args, **kwargs)
                    if (
                        isinstance(path, str)
                        and self.module._QUARANTINE_PATTERN.fullmatch(path)
                        and not swapped
                    ):
                        swapped = True
                        (history / path).rename(displaced)
                        target.mkdir()
                        metadata = target.stat()
                        competitor_identity = (metadata.st_dev, metadata.st_ino)
                    return descriptor

                with mock.patch.object(self.module.os, "open", side_effect=swap_after_open):
                    with self.assertRaises(self.module.StudioError):
                        self.module.status(project)
                self.assertTrue(swapped)
                self.assertTrue(target.is_dir())
                metadata = target.stat()
                self.assertEqual(competitor_identity, (metadata.st_dev, metadata.st_ino))
                self.assertTrue((project / self.module.JOURNAL_NAME).is_file())

    def test_atomic_quarantine_never_rmdirs_a_swapped_public_competitor(self) -> None:
        self.assertFalse(hasattr(self.module, "_native_rmdir_at"))
        self.module.approve(self.project, "brief")
        project = self.project
        history = project / "history"
        real_recover = self.module._recover_transaction_at

        def interrupt(name):
            if name == "snapshot-published":
                raise KeyboardInterrupt(name)

        def persist_transaction(project_fd, *, scan_orphans=False):
            if scan_orphans and (project / self.module.JOURNAL_NAME).exists():
                raise self.module.StudioError("leave transaction persisted")
            return real_recover(project_fd, scan_orphans=scan_orphans)

        with (
            mock.patch.object(self.module, "_transaction_boundary", side_effect=interrupt),
            mock.patch.object(
                self.module, "_recover_transaction_at", side_effect=persist_transaction
            ),
        ):
            with self.assertRaises(self.module.StudioError):
                self.module.reopen(project, "brief", reason="rewrite")

        journal = json.loads(
            (project / self.module.JOURNAL_NAME).read_text(encoding="utf-8")
        )
        public_name = journal["snapshot_name"]
        public = history / public_name
        expected_identity = (journal["snapshot_dev"], journal["snapshot_ino"])
        displaced = history / ".expected-displaced"
        competitor_identity: tuple[int, int] | None = None
        real_quarantine = self.module._native_rename_noreplace

        def swap_during_quarantine(directory_fd, source, destination):
            nonlocal competitor_identity
            result = real_quarantine(directory_fd, source, destination)
            if source == public_name:
                quarantine = history / destination
                quarantine.rename(displaced)
                public.mkdir()
                metadata = public.stat()
                competitor_identity = (metadata.st_dev, metadata.st_ino)
            return result

        with (
            mock.patch.object(
                self.module,
                "_native_rename_noreplace",
                side_effect=swap_during_quarantine,
            ),
            mock.patch.object(
                self.module.os,
                "rmdir",
                side_effect=AssertionError("public os.rmdir must not be used"),
            ),
        ):
            with self.assertRaises(self.module.StudioError):
                self.module.status(project)

        self.assertTrue(public.is_dir())
        metadata = public.stat()
        self.assertEqual(competitor_identity, (metadata.st_dev, metadata.st_ino))
        displaced_metadata = displaced.stat()
        self.assertEqual(
            expected_identity,
            (displaced_metadata.st_dev, displaced_metadata.st_ino),
        )
        self.assertTrue((project / self.module.JOURNAL_NAME).is_file())

    def test_no_journal_recovery_ignores_empty_tombstone_but_rejects_nonempty(self) -> None:
        history = self.project / "history"
        empty = history / (".reopen-delete-" + "a" * 32)
        empty.mkdir()
        self.module.status(self.project)
        self.assertTrue(empty.is_dir())
        empty.chmod(0o777)
        with self.assertRaises(self.module.StudioError):
            self.module.status(self.project)
        empty.chmod(0o700)

        nonempty = history / (".reopen-delete-" + "b" * 32)
        nonempty.mkdir()
        marker = nonempty / "keep"
        marker.write_text("keep", encoding="utf-8")
        with self.assertRaises(self.module.StudioError):
            self.module.status(self.project)
        self.assertEqual("keep", marker.read_text(encoding="utf-8"))

    def test_old_empty_tombstone_does_not_block_new_journal_recovery(self) -> None:
        for boundary in ("snapshot-published", "state-committed"):
            with self.subTest(boundary=boundary), tempfile.TemporaryDirectory() as directory:
                result = self.initializer.init_project(
                    Path(directory), "Old Tombstone", "short-form", date="2026-07-17"
                )
                project = Path(result["path"])
                history = project / "history"
                old_tombstone = history / (".reopen-delete-" + "c" * 32)
                old_tombstone.mkdir()
                self.module.approve(project, "brief")
                real_recover = self.module._recover_transaction_at

                def interrupt(name):
                    if name == boundary:
                        raise KeyboardInterrupt(name)

                def persist_journal(project_fd, *, scan_orphans=False):
                    if scan_orphans and (project / self.module.JOURNAL_NAME).exists():
                        raise self.module.StudioError("persist for next operation")
                    return real_recover(project_fd, scan_orphans=scan_orphans)

                with (
                    mock.patch.object(self.module, "_transaction_boundary", side_effect=interrupt),
                    mock.patch.object(
                        self.module, "_recover_transaction_at", side_effect=persist_journal
                    ),
                ):
                    with self.assertRaises(self.module.StudioError):
                        self.module.reopen(project, "brief", reason="rewrite")
                self.assertTrue((project / self.module.JOURNAL_NAME).is_file())

                state = self.module.status(project)
                self.assertTrue(old_tombstone.is_dir())
                self.assertEqual([], list(old_tombstone.iterdir()))
                self.assertFalse((project / self.module.JOURNAL_NAME).exists())
                public = self.public_history(project)
                if boundary == "state-committed":
                    self.assertEqual("brief_pending", state["stage"])
                    self.assertEqual(1, len(public))
                else:
                    self.assertEqual("research_pending", state["stage"])
                    self.assertEqual([], public)
                self.assert_hidden_history_is_safe_tombstones(project)

    def test_recovery_removes_only_strict_reserved_root_temp_names(self) -> None:
        stale_state = self.project / (".project.yaml." + "a" * 32 + ".tmp")
        stale_journal = self.project / (
            "..video-script-studio-reopen.json." + "b" * 32 + ".tmp"
        )
        unrelated = self.project / (".project.yaml." + "g" * 32 + ".tmp")
        for path in (stale_state, stale_journal, unrelated):
            path.write_text("stale", encoding="utf-8")

        self.module.status(self.project)

        self.assertFalse(stale_state.exists())
        self.assertFalse(stale_journal.exists())
        self.assertEqual("stale", unrelated.read_text(encoding="utf-8"))

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
        self.assertEqual([], self.public_history())

    def test_rejects_untrusted_state_artifact_and_history_metadata_without_mutation(self) -> None:
        state_path = self.project / "project.yaml"
        original = state_path.read_bytes()
        state_path.chmod(0o666)
        with self.assertRaises(self.module.StudioError):
            self.module.load_state(self.project)
        state_path.chmod(0o600)
        state_hardlink = self.project / "project-copy.yaml"
        os.link(state_path, state_hardlink)
        with self.assertRaises(self.module.StudioError):
            self.module.load_state(self.project)
        state_hardlink.unlink()

        self.module.approve(self.project, "brief")
        approved = state_path.read_bytes()
        artifact = self.project / "brief.md"
        artifact.chmod(0o666)
        with self.assertRaises(self.module.StudioError):
            self.module.reopen(self.project, "brief", reason="rewrite")
        self.assertEqual(approved, state_path.read_bytes())
        artifact.chmod(0o600)

        history = self.project / "history"
        history.chmod(0o777)
        with self.assertRaises(self.module.StudioError):
            self.module.reopen(self.project, "brief", reason="rewrite")
        self.assertEqual(approved, state_path.read_bytes())
        history.chmod(0o755)

        hardlink = self.project / "brief-copy.md"
        os.link(artifact, hardlink)
        with self.assertRaises(self.module.StudioError):
            self.module.reopen(self.project, "brief", reason="rewrite")
        self.assertEqual(approved, state_path.read_bytes())
        hardlink.unlink()
        self.assertEqual([], self.public_history())

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
