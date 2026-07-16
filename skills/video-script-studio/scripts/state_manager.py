"""Enforce ordered approval gates for Video Script Studio projects."""

from __future__ import annotations

import argparse
import copy
import json
import os
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
_UNSUPPORTED = "State management requires a trusted POSIX filesystem."
_PROCESS_LOCK = threading.RLock()


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
        descriptor = os.open(name, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0), dir_fd=directory_fd)
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > limit:
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
        os.fsync(project_fd)
    except OSError as exc:
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
    try:
        descriptor = os.open(
            "history",
            os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0),
            dir_fd=project_fd,
        )
        metadata = os.fstat(descriptor)
        if not stat.S_ISDIR(metadata.st_mode):
            raise StudioError("The project history path is unsafe.")
        return descriptor
    except StudioError:
        raise
    except OSError as exc:
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


def _remove_snapshot(history_fd: int, name: str, filenames: list[str]) -> None:
    snapshot_fd: int | None = None
    try:
        snapshot_fd = os.open(
            name,
            os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0),
            dir_fd=history_fd,
        )
        for filename in [*filenames, "manifest.json"]:
            try:
                os.unlink(filename, dir_fd=snapshot_fd)
            except FileNotFoundError:
                pass
        os.close(snapshot_fd)
        snapshot_fd = None
        os.rmdir(name, dir_fd=history_fd)
    except OSError:
        pass
    finally:
        if snapshot_fd is not None:
            os.close(snapshot_fd)


def reopen(project: Path, stage: str, reason: str) -> dict[str, Any]:
    """Reopen an approved stage, preserving affected non-empty artifacts."""
    if stage not in STAGES:
        raise StudioError("The reopen stage is invalid.")
    if not isinstance(reason, str) or not reason.strip() or len(reason) > MAX_REASON_CHARS:
        raise StudioError("The reopen reason must be nonblank and at most 4096 characters.")

    with _locked_project(project) as (resolved, project_fd):
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
        created = False
        try:
            try:
                os.mkdir(snapshot_name, 0o700, dir_fd=history_fd)
            except FileExistsError as exc:
                raise StudioError("The history snapshot already exists.") from exc
            created = True
            snapshot_fd = os.open(
                snapshot_name,
                os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0),
                dir_fd=history_fd,
            )
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

            index = STAGES.index(stage)
            state["approvals"][stage] = "pending"
            for later in STAGES[index + 1 :]:
                state["approvals"][later] = "invalidated"
            state["stage"] = f"{stage}_pending"
            try:
                _save_state_at(project_fd, state)
            except Exception:
                _remove_snapshot(history_fd, snapshot_name, list(artifacts))
                raise
        except Exception:
            if created:
                _remove_snapshot(history_fd, snapshot_name, list(artifacts))
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
