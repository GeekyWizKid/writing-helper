"""Initialize a resumable Video Script Studio project."""

from __future__ import annotations

import argparse
import ctypes
import errno
import json
import os
import shutil
import stat
import sys
import tempfile
from contextlib import contextmanager
from datetime import date as calendar_date
from pathlib import Path
from typing import Any

try:
    import fcntl
except ImportError:  # pragma: no cover - exercised through import simulation
    fcntl = None  # type: ignore[assignment]

_SCRIPT_DIRECTORY = Path(__file__).resolve().parent
if str(_SCRIPT_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIRECTORY))

from common import (
    StudioError,
    atomic_write_text,
    dump_state_yaml,
    load_state_yaml,
    safe_slug,
)


PRIMARY_TYPES = (
    "short-form",
    "long-form",
    "narrative",
    "commercial",
    "visual-essay",
)

REQUIRED_ARTIFACTS = (
    "brief.md",
    "research.md",
    "concepts.md",
    "outline.md",
    "script.md",
    "storyboard.md",
    "assets.md",
    "publish.md",
    "sources.md",
    "review.md",
)

_TEMPLATE_PATH = Path(__file__).resolve().parents[1] / "assets" / "project-state-template.yaml"
_TYPE_SET = frozenset(PRIMARY_TYPES)
_UNSUPPORTED_PLATFORM_MESSAGE = (
    "Project initialization requires POSIX Darwin or Linux with fcntl and getuid "
    "support."
)


def _text(value: Any, field: str, *, optional: bool = False) -> str | None:
    if optional and value is None:
        return None
    if not isinstance(value, str):
        raise StudioError(f"{field} must be text.")
    return value


def _project_date(value: str | None) -> str:
    if value is None:
        return calendar_date.today().isoformat()
    if not isinstance(value, str):
        raise StudioError("date must use YYYY-MM-DD format.")
    try:
        parsed = calendar_date.fromisoformat(value)
    except ValueError as exc:
        raise StudioError("date must use YYYY-MM-DD format.") from exc
    if parsed.isoformat() != value:
        raise StudioError("date must use YYYY-MM-DD format.")
    return value


def _require_supported_platform() -> None:
    """Reject unsupported project platforms before any filesystem mutation."""
    getuid = getattr(os, "getuid", None)
    supported_os = sys.platform == "darwin" or sys.platform.startswith("linux")
    if not supported_os or fcntl is None or not callable(getuid):
        raise StudioError(_UNSUPPORTED_PLATFORM_MESSAGE)


def _validate_root(root: Path) -> Path:
    if not isinstance(root, Path):
        raise StudioError("root must be a filesystem path.")
    try:
        if root.is_symlink():
            raise StudioError("The project root must not be a symbolic link.")
        root.mkdir(mode=0o700, parents=True, exist_ok=True)
        root_stat = root.stat(follow_symlinks=False)
        if stat.S_ISLNK(root_stat.st_mode):
            raise StudioError("The project root must not be a symbolic link.")
        if not stat.S_ISDIR(root_stat.st_mode):
            raise StudioError("The project root must be a directory.")
        getuid = getattr(os, "getuid", None)
        if not callable(getuid):
            raise StudioError(_UNSUPPORTED_PLATFORM_MESSAGE)
        if root_stat.st_uid != getuid() or stat.S_IMODE(root_stat.st_mode) & 0o022:
            raise StudioError("The project root has unsafe ownership or permissions.")
        resolved = root.resolve(strict=True)
    except OSError as exc:
        raise StudioError("Could not prepare the project root.") from exc
    return resolved


def _available_project_directory(root: Path, base_name: str) -> Path:
    sequence = 1
    while True:
        suffix = "" if sequence == 1 else f"-{sequence:02d}"
        candidate = root / f"{base_name}{suffix}"
        if candidate.parent != root:
            raise StudioError("The project path is invalid.")
        if not os.path.lexists(candidate):
            return candidate
        sequence += 1


def _rename_directory_noreplace(source: Path, destination: Path) -> None:
    """Atomically rename a directory only when the destination is absent."""
    try:
        libc = ctypes.CDLL(None, use_errno=True)
        source_bytes = os.fsencode(source)
        destination_bytes = os.fsencode(destination)
        if sys.platform == "darwin":
            # RENAME_EXCL is 0x00000004 in the Darwin SDK's <sys/stdio.h>.
            rename = libc.renamex_np
            rename.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint]
            rename.restype = ctypes.c_int
            result = rename(source_bytes, destination_bytes, 0x00000004)
        elif sys.platform.startswith("linux"):
            # RENAME_NOREPLACE is 1 in the Linux UAPI <linux/fs.h>.
            rename = libc.renameat2
            rename.argtypes = [
                ctypes.c_int,
                ctypes.c_char_p,
                ctypes.c_int,
                ctypes.c_char_p,
                ctypes.c_uint,
            ]
            rename.restype = ctypes.c_int
            result = rename(-100, source_bytes, -100, destination_bytes, 1)
        else:
            raise StudioError(
                "Atomic no-replace publication is not supported on this platform."
            )
    except AttributeError as exc:
        raise StudioError(
            "Atomic no-replace publication is not supported on this platform."
        ) from exc

    if result == 0:
        return
    error_number = ctypes.get_errno()
    if error_number in (errno.EEXIST, errno.ENOTEMPTY):
        raise FileExistsError(
            error_number, os.strerror(error_number), str(destination)
        )
    raise OSError(error_number, os.strerror(error_number), str(destination))


@contextmanager
def _locked_root(root: Path):
    """Serialize candidate selection and publication for a trusted root."""
    lock_api = fcntl
    if lock_api is None:
        raise StudioError(_UNSUPPORTED_PLATFORM_MESSAGE)
    lock_path = root / ".video-script-studio.lock"
    descriptor: int | None = None
    try:
        flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(lock_path, flags, 0o600)
        os.fchmod(descriptor, 0o600)
        lock_api.flock(descriptor, lock_api.LOCK_EX)
        yield
    except OSError as exc:
        raise StudioError("Could not lock the project root.") from exc
    finally:
        if descriptor is not None:
            try:
                lock_api.flock(descriptor, lock_api.LOCK_UN)
            finally:
                os.close(descriptor)


def _artifact_content(filename: str) -> str:
    title = filename.removesuffix(".md").replace("-", " ").title()
    if filename in {"research.md", "sources.md"}:
        return f"# {title}\n\ndisposition: undecided\n"
    return f"# {title}\n"


def init_project(
    root: Path,
    title: str,
    primary_type: str,
    secondary_type: str | None = None,
    platform: str = "unspecified",
    profile_id: str | None = None,
    date: str | None = None,
) -> dict:
    """Create a new project without altering any existing directory."""
    title = _text(title, "title")  # type: ignore[assignment]
    primary_type = _text(primary_type, "primary_type")  # type: ignore[assignment]
    secondary_type = _text(secondary_type, "secondary_type", optional=True)
    platform = _text(platform, "platform")  # type: ignore[assignment]
    profile_id = _text(profile_id, "profile_id", optional=True)
    if primary_type not in _TYPE_SET:
        raise StudioError("primary_type is not supported.")
    if secondary_type is not None and secondary_type not in _TYPE_SET:
        raise StudioError("secondary_type is not supported.")

    project_date = _project_date(date)
    _require_supported_platform()
    root = _validate_root(root)
    base_name = f"{project_date}-{safe_slug(title)}"
    with _locked_root(root):
        project = _available_project_directory(root, base_name)
        state = load_state_yaml(_TEMPLATE_PATH)
        state["project"] = {
            "date": project_date,
            "platform": platform,
            "primary_type": primary_type,
            "profile_id": profile_id,
            "project_id": project.name,
            "secondary_type": secondary_type,
            "title": title,
        }

        staging: Path | None = None
        try:
            staging = Path(
                tempfile.mkdtemp(prefix=".video-script-studio-staging-", dir=root)
            )
            os.chmod(staging, 0o700)
            (staging / "history").mkdir()
            for filename in REQUIRED_ARTIFACTS:
                atomic_write_text(staging / filename, _artifact_content(filename))
            atomic_write_text(staging / "project.yaml", dump_state_yaml(state))
            while True:
                try:
                    _rename_directory_noreplace(staging, project)
                    break
                except FileExistsError:
                    project = _available_project_directory(root, base_name)
                    state["project"]["project_id"] = project.name
                    atomic_write_text(
                        staging / "project.yaml", dump_state_yaml(state)
                    )
        except Exception as exc:
            if staging is not None:
                shutil.rmtree(staging, ignore_errors=True)
            if isinstance(exc, StudioError):
                raise
            if isinstance(exc, OSError):
                raise StudioError("Could not initialize the project files.") from exc
            raise

    return {
        "path": str(project),
        "project_id": project.name,
        "status": "created",
    }


class _JsonArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise StudioError("Invalid command-line arguments.")


def _parser() -> argparse.ArgumentParser:
    parser = _JsonArgumentParser(description=__doc__, add_help=True)
    parser.add_argument("--root", required=True)
    parser.add_argument("--title", required=True)
    parser.add_argument("--primary-type", required=True)
    parser.add_argument("--secondary-type")
    parser.add_argument("--platform", default="unspecified")
    parser.add_argument("--profile-id")
    return parser


def main(argv: list[str] | None = None) -> int:
    try:
        arguments = _parser().parse_args(argv)
        result = init_project(
            root=Path(arguments.root),
            title=arguments.title,
            primary_type=arguments.primary_type,
            secondary_type=arguments.secondary_type,
            platform=arguments.platform,
            profile_id=arguments.profile_id,
        )
        payload = result
        exit_code = 0
    except StudioError as exc:
        payload = {"error": str(exc), "status": "error"}
        exit_code = 2
    except Exception:
        payload = {"error": "Could not initialize the project.", "status": "error"}
        exit_code = 2
    print(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
