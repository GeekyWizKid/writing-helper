"""Enforce ordered approval gates for Video Script Studio projects."""

from __future__ import annotations

import argparse
import copy
import ctypes
import errno
import json
import os
import re
import stat
import sys
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

try:
    import fcntl
except ImportError:  # pragma: no cover - importability is platform dependent
    fcntl = None  # type: ignore[assignment]

_SCRIPT_DIRECTORY = Path(__file__).resolve().parent
if str(_SCRIPT_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIRECTORY))

from common import StudioError, _parse_state_yaml, dump_state_yaml


STAGES = ("brief", "research", "concept", "outline", "script")
STAGE_FILES = {
    "brief": "brief.md",
    "research": "research.md",
    "concept": "concepts.md",
    "outline": "outline.md",
    "script": "script.md",
}
MAX_STATE_BYTES = 1024 * 1024
MAX_ARTIFACT_BYTES = 10 * 1024 * 1024
MAX_REASON_CHARS = 4096

_APPROVAL_VALUES = frozenset(("pending", "approved", "invalidated"))
_ROOT_KEYS = frozenset(
    ("approvals", "artifacts", "project", "research", "schema_version", "sources", "stage")
)
_ARTIFACTS = {
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
_PROJECT_KEYS = frozenset(
    ("date", "platform", "primary_type", "profile_id", "project_id", "secondary_type", "title")
)
_LOCK_NAME = ".video-script-studio-state.lock"
JOURNAL_NAME = ".video-script-studio-reopen.json"
_STAGING_PATTERN = re.compile(r"^\.reopen-txn-[0-9a-f]{32}$")
_RESERVED_TEMP_PATTERN = re.compile(
    r"^(?:\.project\.yaml|\.\.video-script-studio-reopen\.json)\.[0-9a-f]{32}\.tmp$"
)
_SNAPSHOT_PATTERN = re.compile(
    r"^[A-Za-z0-9_-]{1,200}-(?:brief|research|concept|outline|script)$"
)
_UNSUPPORTED = "State management requires a trusted POSIX filesystem."
_PROCESS_LOCK = threading.RLock()


class _StateCommittedError(StudioError):
    """The state rename committed, but its directory durability sync failed."""


def _bounded_text(value: Any, field: str, *, nullable: bool = False) -> None:
    if nullable and value is None:
        return
    if not isinstance(value, str) or len(value) > MAX_STATE_BYTES:
        raise StudioError(f"The {field} field is invalid.")


def _expected_stage(approvals: dict[str, str]) -> str:
    for stage in STAGES:
        if approvals[stage] != "approved":
            return f"{stage}_pending"
    return "script_approved"


def _validate_state(state: Any) -> dict[str, Any]:
    if not isinstance(state, dict) or frozenset(state) != _ROOT_KEYS:
        raise StudioError("The project state schema is invalid.")

    approvals = state.get("approvals")
    if not isinstance(approvals, dict) or frozenset(approvals) != frozenset(STAGES):
        raise StudioError("The project approvals schema is invalid.")
    if any(
        not isinstance(value, str) or value not in _APPROVAL_VALUES
        for value in approvals.values()
    ):
        raise StudioError("The project approval status is invalid.")

    found_open = False
    for stage in STAGES:
        value = approvals[stage]
        if found_open and value == "approved":
            raise StudioError("The project approvals are out of order.")
        if value != "approved":
            found_open = True
    first_open = next((stage for stage in STAGES if approvals[stage] != "approved"), None)
    if first_open is not None and approvals[first_open] != "pending":
        raise StudioError("The next project approval must be pending.")
    if state.get("stage") != _expected_stage(approvals):
        raise StudioError("The project stage does not match its approvals.")

    if state.get("schema_version") != "1" or state.get("artifacts") != _ARTIFACTS:
        raise StudioError("The project state schema is invalid.")
    project = state.get("project")
    if not isinstance(project, dict) or frozenset(project) != _PROJECT_KEYS:
        raise StudioError("The project metadata schema is invalid.")
    for key, value in project.items():
        _bounded_text(value, f"project.{key}", nullable=key in {"profile_id", "secondary_type"})
    for section_name in ("research", "sources"):
        section = state.get(section_name)
        if not isinstance(section, dict) or frozenset(section) != {"disposition"}:
            raise StudioError(f"The {section_name} state schema is invalid.")
        _bounded_text(section["disposition"], f"{section_name}.disposition")
    return state


@contextmanager
def _trusted_project(project: Path) -> Iterator[tuple[Path, int]]:
    if not isinstance(project, Path) or fcntl is None or not callable(getattr(os, "getuid", None)):
        raise StudioError(_UNSUPPORTED)
    descriptor: int | None = None
    try:
        before = project.stat(follow_symlinks=False)
        if stat.S_ISLNK(before.st_mode) or not stat.S_ISDIR(before.st_mode):
            raise StudioError("The project path must be a real directory.")
        descriptor = os.open(
            project,
            os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0),
        )
        after = os.fstat(descriptor)
        if (before.st_dev, before.st_ino) != (after.st_dev, after.st_ino):
            raise StudioError("The project directory changed while opening it.")
        if after.st_uid != os.getuid() or stat.S_IMODE(after.st_mode) & 0o022:
            raise StudioError("The project directory has unsafe ownership or permissions.")
        yield project.resolve(strict=True), descriptor
    except StudioError:
        raise
    except OSError as exc:
        raise StudioError("Could not open the project safely.") from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)


@contextmanager
def _locked_project(project: Path) -> Iterator[tuple[Path, int]]:
    # flock coordinates processes.  A process lock also gives deterministic
    # thread semantics on platforms whose flock implementation is process-wide.
    with _PROCESS_LOCK:
        with _trusted_project(project) as opened:
            resolved, project_fd = opened
            lock_fd: int | None = None
            try:
                created = False
                try:
                    lock_fd = os.open(
                        _LOCK_NAME,
                        os.O_RDWR
                        | os.O_CREAT
                        | os.O_EXCL
                        | getattr(os, "O_NOFOLLOW", 0),
                        0o600,
                        dir_fd=project_fd,
                    )
                    created = True
                except FileExistsError:
                    lock_fd = os.open(
                        _LOCK_NAME,
                        os.O_RDWR | getattr(os, "O_NOFOLLOW", 0),
                        dir_fd=project_fd,
                    )
                lock_stat = os.fstat(lock_fd)
                if (
                    not stat.S_ISREG(lock_stat.st_mode)
                    or lock_stat.st_uid != os.getuid()
                    or lock_stat.st_nlink != 1
                    or (not created and stat.S_IMODE(lock_stat.st_mode) != 0o600)
                ):
                    raise StudioError("The project lock file is unsafe.")
                if created:
                    os.fchmod(lock_fd, 0o600)
                fcntl.flock(lock_fd, fcntl.LOCK_EX)
                _recover_transaction_at(project_fd)
                yield resolved, project_fd
            except StudioError:
                raise
            except OSError as exc:
                raise StudioError("Could not lock the project.") from exc
            finally:
                if lock_fd is not None:
                    try:
                        fcntl.flock(lock_fd, fcntl.LOCK_UN)
                    finally:
                        os.close(lock_fd)


def _read_regular_at(directory_fd: int, name: str, limit: int, label: str) -> bytes:
    descriptor: int | None = None
    try:
        descriptor = os.open(
            name,
            os.O_RDONLY
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_NONBLOCK", 0),
            dir_fd=directory_fd,
        )
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid != os.getuid()
            or metadata.st_nlink != 1
            or stat.S_IMODE(metadata.st_mode) & 0o022
            or metadata.st_size > limit
        ):
            raise StudioError(f"The {label} file is unsafe or too large.")
        chunks: list[bytes] = []
        remaining = limit + 1
        while remaining:
            chunk = os.read(descriptor, min(65536, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        data = b"".join(chunks)
        if len(data) > limit:
            raise StudioError(f"The {label} file is unsafe or too large.")
        return data
    except StudioError:
        raise
    except OSError as exc:
        raise StudioError(f"Could not read the {label} file safely.") from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _load_state_at(project_fd: int) -> dict[str, Any]:
    raw = _read_regular_at(project_fd, "project.yaml", MAX_STATE_BYTES, "project state")
    try:
        state = _parse_state_yaml(raw.decode("utf-8"))
    except (UnicodeError, StudioError) as exc:
        raise StudioError("The project state file is invalid.") from exc
    return _validate_state(state)


def _write_all(descriptor: int, data: bytes) -> None:
    view = memoryview(data)
    while view:
        written = os.write(descriptor, view)
        if written <= 0:
            raise OSError("short write")
        view = view[written:]


def _save_state_at(project_fd: int, state: dict[str, Any]) -> None:
    _validate_state(state)
    committed = False
    try:
        payload = dump_state_yaml(state).encode("utf-8")
    except (UnicodeError, StudioError) as exc:
        raise StudioError("Could not serialize the project state.") from exc
    if len(payload) > MAX_STATE_BYTES:
        raise StudioError("The project state is too large.")
    temporary = f".project.yaml.{uuid.uuid4().hex}.tmp"
    descriptor: int | None = None
    try:
        descriptor = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            0o600,
            dir_fd=project_fd,
        )
        _write_all(descriptor, payload)
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = None
        os.rename(temporary, "project.yaml", src_dir_fd=project_fd, dst_dir_fd=project_fd)
        committed = True
        os.fsync(project_fd)
    except OSError as exc:
        if committed:
            raise _StateCommittedError(
                "The project state was committed, but its durability sync failed."
            ) from exc
        raise StudioError("Could not publish the project state.") from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)
        try:
            os.unlink(temporary, dir_fd=project_fd)
        except FileNotFoundError:
            pass
        except OSError:
            pass


def load_state(project: Path) -> dict[str, Any]:
    """Load and validate a project's bounded state document."""
    with _locked_project(project) as (_, project_fd):
        return copy.deepcopy(_load_state_at(project_fd))


def save_state(project: Path, state: dict[str, Any]) -> None:
    """Validate and atomically replace a project's state document."""
    # Reject an unknown or oversized shape before recursively copying caller
    # input; validated state contains only the bounded scalar schema above.
    _validate_state(state)
    with _locked_project(project) as (_, project_fd):
        _save_state_at(project_fd, copy.deepcopy(state))


def approve(project: Path, stage: str) -> dict[str, Any]:
    """Approve exactly the next gate, or return an idempotent result."""
    if stage not in STAGES:
        raise StudioError("The approval stage is invalid.")
    with _locked_project(project) as (_, project_fd):
        state = _load_state_at(project_fd)
        approvals = state["approvals"]
        if approvals[stage] == "approved":
            return {"stage": state["stage"], "status": "already_approved"}
        next_stage = next(item for item in STAGES if approvals[item] != "approved")
        if stage != next_stage:
            raise StudioError("Approval gates must be completed in order.")
        approvals[stage] = "approved"
        index = STAGES.index(stage)
        if index + 1 < len(STAGES) and approvals[STAGES[index + 1]] == "invalidated":
            approvals[STAGES[index + 1]] = "pending"
        state["stage"] = _expected_stage(approvals)
        _save_state_at(project_fd, state)
        return {"stage": state["stage"], "status": "approved"}


def _history_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def _open_history(project_fd: int) -> int:
    descriptor: int | None = None
    try:
        descriptor = os.open(
            "history",
            os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0),
            dir_fd=project_fd,
        )
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISDIR(metadata.st_mode)
            or metadata.st_uid != os.getuid()
            or stat.S_IMODE(metadata.st_mode) & 0o022
        ):
            raise StudioError("The project history path is unsafe.")
        return descriptor
    except StudioError:
        if descriptor is not None:
            os.close(descriptor)
        raise
    except OSError as exc:
        if descriptor is not None:
            os.close(descriptor)
        raise StudioError("Could not open project history safely.") from exc


def _write_exclusive_at(directory_fd: int, name: str, data: bytes) -> None:
    descriptor: int | None = None
    try:
        descriptor = os.open(
            name,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            0o600,
            dir_fd=directory_fd,
        )
        _write_all(descriptor, data)
        os.fsync(descriptor)
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _entry_exists_at(directory_fd: int, name: str) -> bool:
    try:
        os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
        return True
    except FileNotFoundError:
        return False
    except OSError as exc:
        raise StudioError("Could not inspect transaction data safely.") from exc


def _remove_flat_directory_at(parent_fd: int, name: str) -> None:
    descriptor: int | None = None
    try:
        descriptor = os.open(
            name,
            os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0),
            dir_fd=parent_fd,
        )
        for child in os.listdir(descriptor):
            metadata = os.stat(child, dir_fd=descriptor, follow_symlinks=False)
            if stat.S_ISDIR(metadata.st_mode) and not stat.S_ISLNK(metadata.st_mode):
                raise StudioError("Transaction data contains an unexpected directory.")
            os.unlink(child, dir_fd=descriptor)
        os.close(descriptor)
        descriptor = None
        os.rmdir(name, dir_fd=parent_fd)
        os.fsync(parent_fd)
    except StudioError:
        raise
    except OSError as exc:
        raise StudioError("Could not clean transaction data safely.") from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _unlink_if_present(directory_fd: int, name: str) -> None:
    try:
        os.unlink(name, dir_fd=directory_fd)
        os.fsync(directory_fd)
    except FileNotFoundError:
        pass
    except OSError as exc:
        raise StudioError("Could not clean the transaction journal.") from exc


def _atomic_write_json_at(directory_fd: int, name: str, value: dict[str, Any]) -> None:
    try:
        payload = (
            json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
            + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise StudioError("Could not serialize the transaction journal.") from exc
    temporary = f".{name}.{uuid.uuid4().hex}.tmp"
    descriptor: int | None = None
    renamed = False
    try:
        descriptor = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            0o600,
            dir_fd=directory_fd,
        )
        _write_all(descriptor, payload)
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = None
        os.rename(temporary, name, src_dir_fd=directory_fd, dst_dir_fd=directory_fd)
        renamed = True
        os.fsync(directory_fd)
    except OSError as exc:
        if renamed:
            raise StudioError("The transaction journal was committed but not synced.") from exc
        raise StudioError("Could not save the transaction journal.") from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)
        try:
            os.unlink(temporary, dir_fd=directory_fd)
        except OSError:
            pass


def _read_journal_at(project_fd: int) -> dict[str, Any]:
    raw = _read_regular_at(project_fd, JOURNAL_NAME, MAX_STATE_BYTES, "transaction journal")
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeError, ValueError) as exc:
        raise StudioError("The transaction journal is invalid.") from exc
    if not isinstance(value, dict):
        raise StudioError("The transaction journal is invalid.")
    required = {
        "artifacts",
        "old_approvals",
        "old_stage",
        "reason",
        "snapshot_name",
        "snapshot_dev",
        "snapshot_ino",
        "stage",
        "staging_name",
        "target_approvals",
        "target_stage",
        "version",
    }
    if set(value) != required or value.get("version") != "1":
        raise StudioError("The transaction journal schema is invalid.")
    if (
        value.get("stage") not in STAGES
        or not isinstance(value.get("reason"), str)
        or not value["reason"].strip()
        or len(value["reason"]) > MAX_REASON_CHARS
        or not isinstance(value.get("staging_name"), str)
        or not _STAGING_PATTERN.fullmatch(value["staging_name"])
        or not isinstance(value.get("snapshot_name"), str)
        or not _SNAPSHOT_PATTERN.fullmatch(value["snapshot_name"])
        or type(value.get("snapshot_dev")) is not int
        or value["snapshot_dev"] < 0
        or type(value.get("snapshot_ino")) is not int
        or value["snapshot_ino"] <= 0
        or not isinstance(value.get("artifacts"), list)
        or any(item not in STAGE_FILES.values() for item in value["artifacts"])
        or len(set(value["artifacts"])) != len(value["artifacts"])
    ):
        raise StudioError("The transaction journal schema is invalid.")
    for prefix in ("old", "target"):
        approvals = value.get(f"{prefix}_approvals")
        stage_value = value.get(f"{prefix}_stage")
        if (
            not isinstance(approvals, dict)
            or frozenset(approvals) != frozenset(STAGES)
            or any(
                not isinstance(status, str) or status not in _APPROVAL_VALUES
                for status in approvals.values()
            )
            or not isinstance(stage_value, str)
        ):
            raise StudioError("The transaction journal schema is invalid.")
        found_open = False
        for approval_stage in STAGES:
            status_value = approvals[approval_stage]
            if found_open and status_value == "approved":
                raise StudioError("The transaction journal approvals are invalid.")
            if status_value != "approved":
                found_open = True
        first_open = next(
            (approval_stage for approval_stage in STAGES if approvals[approval_stage] != "approved"),
            None,
        )
        if first_open is not None and approvals[first_open] != "pending":
            raise StudioError("The transaction journal approvals are invalid.")
        if stage_value != _expected_stage(approvals):
            raise StudioError("The transaction journal stage is invalid.")
    transaction_stage = value["stage"]
    if value["old_approvals"][transaction_stage] != "approved":
        raise StudioError("The transaction journal transition is invalid.")
    expected_target = copy.deepcopy(value["old_approvals"])
    transaction_index = STAGES.index(transaction_stage)
    expected_target[transaction_stage] = "pending"
    for later in STAGES[transaction_index + 1 :]:
        expected_target[later] = "invalidated"
    if (
        value["target_approvals"] != expected_target
        or value["target_stage"] != f"{transaction_stage}_pending"
    ):
        raise StudioError("The transaction journal transition is invalid.")
    return value


def _transaction_state_matches(state: dict[str, Any], journal: dict[str, Any], prefix: str) -> bool:
    return (
        state["stage"] == journal[f"{prefix}_stage"]
        and state["approvals"] == journal[f"{prefix}_approvals"]
    )


def _snapshot_identity_at(history_fd: int, name: str) -> tuple[int, int] | None:
    try:
        metadata = os.stat(name, dir_fd=history_fd, follow_symlinks=False)
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise StudioError("Could not inspect the history snapshot identity.") from exc
    return metadata.st_dev, metadata.st_ino


def _journal_snapshot_identity(journal: dict[str, Any]) -> tuple[int, int]:
    return journal["snapshot_dev"], journal["snapshot_ino"]


def _validate_snapshot_at(history_fd: int, journal: dict[str, Any]) -> None:
    descriptor: int | None = None
    try:
        descriptor = os.open(
            journal["snapshot_name"],
            os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0),
            dir_fd=history_fd,
        )
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISDIR(metadata.st_mode)
            or metadata.st_uid != os.getuid()
            or stat.S_IMODE(metadata.st_mode) & 0o022
        ):
            raise StudioError("The history snapshot directory is unsafe.")
        expected = {*journal["artifacts"], "manifest.json"}
        if set(os.listdir(descriptor)) != expected:
            raise StudioError("The history snapshot contents are incomplete.")
        for filename in journal["artifacts"]:
            _read_regular_at(descriptor, filename, MAX_ARTIFACT_BYTES, "history artifact")
        raw_manifest = _read_regular_at(
            descriptor, "manifest.json", MAX_STATE_BYTES, "history manifest"
        )
        try:
            manifest = json.loads(raw_manifest.decode("utf-8"))
        except (UnicodeError, ValueError) as exc:
            raise StudioError("The history snapshot manifest is invalid.") from exc
        if manifest != {
            "affected_artifacts": sorted(journal["artifacts"]),
            "reason": journal["reason"],
            "stage": journal["stage"],
        }:
            raise StudioError("The history snapshot manifest is invalid.")
    except StudioError:
        raise
    except OSError as exc:
        raise StudioError("Could not validate the history snapshot safely.") from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _cleanup_reserved_temps_at(project_fd: int) -> None:
    removed = False
    try:
        for name in os.listdir(project_fd):
            if not _RESERVED_TEMP_PATTERN.fullmatch(name):
                continue
            metadata = os.stat(name, dir_fd=project_fd, follow_symlinks=False)
            if stat.S_ISDIR(metadata.st_mode) and not stat.S_ISLNK(metadata.st_mode):
                raise StudioError("A reserved project temporary path is unsafe.")
            os.unlink(name, dir_fd=project_fd)
            removed = True
        if removed:
            os.fsync(project_fd)
    except StudioError:
        raise
    except OSError as exc:
        raise StudioError("Could not clean reserved project temporary files.") from exc


def _recover_transaction_at(project_fd: int, *, scan_orphans: bool = False) -> None:
    """Reconcile a prior reopen using project.yaml as the commit record."""
    _cleanup_reserved_temps_at(project_fd)
    has_journal = _entry_exists_at(project_fd, JOURNAL_NAME)
    if not has_journal and not scan_orphans:
        try:
            history_metadata = os.stat(
                "history", dir_fd=project_fd, follow_symlinks=False
            )
        except OSError:
            return
        if (
            not stat.S_ISDIR(history_metadata.st_mode)
            or stat.S_ISLNK(history_metadata.st_mode)
            or history_metadata.st_uid != os.getuid()
            or stat.S_IMODE(history_metadata.st_mode) & 0o022
        ):
            return
    history_fd = _open_history(project_fd)
    try:
        if not has_journal:
            for name in os.listdir(history_fd):
                if _STAGING_PATTERN.fullmatch(name):
                    _remove_flat_directory_at(history_fd, name)
            return

        journal = _read_journal_at(project_fd)
        state = _load_state_at(project_fd)
        staging_name = journal["staging_name"]
        snapshot_name = journal["snapshot_name"]
        staging_exists = _entry_exists_at(history_fd, staging_name)
        final_identity = _snapshot_identity_at(history_fd, snapshot_name)
        expected_identity = _journal_snapshot_identity(journal)
        if _transaction_state_matches(state, journal, "target"):
            if final_identity is None:
                raise StudioError("Committed project state is missing its history snapshot.")
            if final_identity != expected_identity:
                raise StudioError("The history snapshot was replaced during recovery.")
            _validate_snapshot_at(history_fd, journal)
        elif _transaction_state_matches(state, journal, "old"):
            # A remaining staging directory proves this transaction did not
            # publish; an identically named final entry therefore predates it.
            if not staging_exists and final_identity is not None:
                if final_identity != expected_identity:
                    raise StudioError(
                        "A competing history snapshot prevents automatic recovery."
                    )
                _validate_snapshot_at(history_fd, journal)
                _remove_flat_directory_at(history_fd, snapshot_name)
        else:
            raise StudioError("Project state conflicts with its recovery journal.")
        if staging_exists:
            _remove_flat_directory_at(history_fd, staging_name)
        _unlink_if_present(project_fd, JOURNAL_NAME)
        for name in os.listdir(history_fd):
            if _STAGING_PATTERN.fullmatch(name):
                _remove_flat_directory_at(history_fd, name)
    finally:
        os.close(history_fd)


def _native_rename_noreplace(directory_fd: int, source: str, destination: str) -> None:
    """Atomically publish a same-directory snapshot without replacement."""
    try:
        libc = ctypes.CDLL(None, use_errno=True)
        if sys.platform == "darwin":
            rename = libc.renameatx_np
            rename.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
            rename.restype = ctypes.c_int
            result = rename(directory_fd, os.fsencode(source), directory_fd, os.fsencode(destination), 0x4)
        elif sys.platform.startswith("linux"):
            rename = libc.renameat2
            rename.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
            rename.restype = ctypes.c_int
            result = rename(directory_fd, os.fsencode(source), directory_fd, os.fsencode(destination), 1)
        else:
            raise AttributeError("unsupported platform")
    except (AttributeError, OSError) as exc:
        raise StudioError(_UNSUPPORTED) from exc
    if result == 0:
        return
    error_number = ctypes.get_errno()
    if error_number in (errno.EEXIST, errno.ENOTEMPTY):
        raise StudioError("The history snapshot already exists.")
    raise StudioError("Could not publish the history snapshot safely.")


def _transaction_boundary(name: str) -> None:
    """Test seam for simulating abrupt termination at durable boundaries."""


def _build_target_state(state: dict[str, Any], stage: str) -> dict[str, Any]:
    target = copy.deepcopy(state)
    index = STAGES.index(stage)
    target["approvals"][stage] = "pending"
    for later in STAGES[index + 1 :]:
        target["approvals"][later] = "invalidated"
    target["stage"] = f"{stage}_pending"
    return target


def reopen(project: Path, stage: str, reason: str) -> dict[str, Any]:
    """Reopen an approved stage, preserving affected non-empty artifacts."""
    if stage not in STAGES:
        raise StudioError("The reopen stage is invalid.")
    if not isinstance(reason, str) or not reason.strip() or len(reason) > MAX_REASON_CHARS:
        raise StudioError("The reopen reason must be nonblank and at most 4096 characters.")

    with _locked_project(project) as (resolved, project_fd):
        _recover_transaction_at(project_fd, scan_orphans=True)
        state = _load_state_at(project_fd)
        if state["approvals"][stage] != "approved":
            raise StudioError("Only an approved stage can be reopened.")
        affected_stages = STAGES[STAGES.index(stage) :]
        artifacts: dict[str, bytes] = {}
        for affected_stage in affected_stages:
            filename = STAGE_FILES[affected_stage]
            content = _read_regular_at(project_fd, filename, MAX_ARTIFACT_BYTES, filename)
            if content:
                artifacts[filename] = content

        history_fd = _open_history(project_fd)
        snapshot_name = f"{_history_timestamp()}-{stage}"
        if not _SNAPSHOT_PATTERN.fullmatch(snapshot_name):
            os.close(history_fd)
            raise StudioError("The history snapshot name is invalid.")
        staging_name = f".reopen-txn-{uuid.uuid4().hex}"
        target = _build_target_state(state, stage)
        journal = {
            "artifacts": sorted(artifacts),
            "old_approvals": copy.deepcopy(state["approvals"]),
            "old_stage": state["stage"],
            "reason": reason,
            "snapshot_name": snapshot_name,
            "stage": stage,
            "staging_name": staging_name,
            "target_approvals": copy.deepcopy(target["approvals"]),
            "target_stage": target["stage"],
            "version": "1",
        }
        try:
            os.mkdir(staging_name, 0o700, dir_fd=history_fd)
            snapshot_fd = os.open(
                staging_name,
                os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0),
                dir_fd=history_fd,
            )
            snapshot_metadata = os.fstat(snapshot_fd)
            journal["snapshot_dev"] = snapshot_metadata.st_dev
            journal["snapshot_ino"] = snapshot_metadata.st_ino
            try:
                for filename, content in artifacts.items():
                    _write_exclusive_at(snapshot_fd, filename, content)
                manifest = {
                    "affected_artifacts": sorted(artifacts),
                    "reason": reason,
                    "stage": stage,
                }
                manifest_data = (
                    json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
                    + "\n"
                ).encode("utf-8")
                _write_exclusive_at(snapshot_fd, "manifest.json", manifest_data)
                os.fsync(snapshot_fd)
            finally:
                os.close(snapshot_fd)
            os.fsync(history_fd)
            _transaction_boundary("staged")
            _atomic_write_json_at(project_fd, JOURNAL_NAME, journal)
            _transaction_boundary("journaled")
            _native_rename_noreplace(history_fd, staging_name, snapshot_name)
            os.fsync(history_fd)
            _transaction_boundary("snapshot-published")
            _save_state_at(project_fd, target)
            _transaction_boundary("state-committed")
            _unlink_if_present(project_fd, JOURNAL_NAME)
            state = target
        except BaseException as original_exc:
            try:
                _recover_transaction_at(project_fd, scan_orphans=True)
            except Exception as recovery_exc:
                if isinstance(original_exc, _StateCommittedError):
                    raise original_exc from recovery_exc
                raise StudioError(
                    "The reopen transaction requires recovery before continuing."
                ) from recovery_exc
            raise
        finally:
            os.close(history_fd)

        return {
            "history_path": str(resolved / "history" / snapshot_name),
            "stage": state["stage"],
            "status": "reopened",
        }


def status(project: Path) -> dict[str, Any]:
    """Return a detached, minimal project approval summary."""
    state = load_state(project)
    return {"approvals": copy.deepcopy(state["approvals"]), "stage": state["stage"]}


class _JsonArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise StudioError("Invalid command-line arguments.")


def _parser() -> argparse.ArgumentParser:
    parser = _JsonArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True, parser_class=_JsonArgumentParser)
    approve_parser = subparsers.add_parser("approve")
    approve_parser.add_argument("--project", required=True)
    approve_parser.add_argument("--stage", required=True)
    reopen_parser = subparsers.add_parser("reopen")
    reopen_parser.add_argument("--project", required=True)
    reopen_parser.add_argument("--stage", required=True)
    reopen_parser.add_argument("--reason", required=True)
    status_parser = subparsers.add_parser("status")
    status_parser.add_argument("--project", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    try:
        arguments = _parser().parse_args(argv)
        project = Path(arguments.project)
        if arguments.command == "approve":
            payload = approve(project, arguments.stage)
        elif arguments.command == "reopen":
            payload = reopen(project, arguments.stage, arguments.reason)
        else:
            payload = status(project)
        exit_code = 0
    except StudioError as exc:
        payload = {"error": str(exc), "status": "error"}
        exit_code = 2
    except Exception:
        payload = {"error": "Could not manage the project state.", "status": "error"}
        exit_code = 2
    print(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
