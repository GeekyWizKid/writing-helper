"""Create, read, list, and transactionally version creator profiles.

Profile mutations are bound to trusted, open directory descriptors. Once a
profile and its versions directory are opened with ``O_NOFOLLOW``, transaction
staging, publication, rollback, and cleanup use only ``dir_fd`` operations.
"""

from __future__ import annotations

import argparse
import fcntl
import importlib.util
import json
import os
import re
import stat
import sys
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from types import ModuleType
from typing import Any, Iterator


def _load_common() -> ModuleType:
    loaded = sys.modules.get("video_script_studio_common")
    if loaded is not None:
        return loaded
    try:
        import common

        return common
    except ImportError:
        common_path = Path(__file__).with_name("common.py")
        spec = importlib.util.spec_from_file_location(
            "video_script_studio_common", common_path
        )
        if spec is None or spec.loader is None:
            raise ImportError(f"Cannot load common helpers from {common_path}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        return module


_common = _load_common()
StudioError = _common.StudioError
utc_now_iso = _common.utc_now_iso

PROFILE_DOCUMENTS = ("profile.md", "style-analysis.md", "constraints.md")
PROFILE_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
VERSION_DIRECTORY_PATTERN = re.compile(r"^v[0-9]{3,}$")
TRANSACTION_DIRECTORY_PATTERN = re.compile(r"^\.profile-txn-[0-9a-f]{32}$")
TIMESTAMP_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
LOCK_NAME = ".profile.lock"
JOURNAL_NAME = ".transaction.json"
DIRECTORY_FLAGS = os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0)
FILE_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)

STYLE_ANALYSIS = """# 风格分析

## 开头与观点

记录常见开场动作、观点出现的时机，以及观点直陈或隐含的选择依据。

## 语言与节奏

记录句子长度、停顿、信息与情绪比例、幽默强度和惯用修辞。

## 画面与声音

记录画面承担的信息、视觉母题、环境声、音乐、静默和旁白的分工。

## 结尾方式

记录适合账号的收束方式，以及需要避免的固定句式和机械号召。
"""

CONSTRAINTS = """# 创作约束

## 表达边界

记录禁用词、厌恶表达、禁止话题和不采用的叙事手法。

## 事实与营销边界

记录证据要求、不能越过的专业边界、商业披露规则和营销尺度。

## 资源与平台规则

记录制作资源上限，以及必须遵循的平台、品牌、版权和安全规则。
"""


@dataclass(frozen=True)
class LockedProfile:
    root_path: Path
    profile_id: str
    root_fd: int
    profile_fd: int
    versions_fd: int


def _validate_profile_id(profile_id: str) -> str:
    if not isinstance(profile_id, str) or not PROFILE_ID_PATTERN.fullmatch(profile_id):
        raise StudioError(
            "Profile ID must use 1-64 ASCII letters, digits, underscores, or hyphens."
        )
    return profile_id


def _validate_text(value: str, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise StudioError(f"{label} must be non-empty text.")
    return value


def _trusted_metadata(metadata: os.stat_result, *, regular: bool = False) -> None:
    current_uid = os.getuid() if hasattr(os, "getuid") else metadata.st_uid
    expected_type = stat.S_ISREG if regular else stat.S_ISDIR
    if (
        not expected_type(metadata.st_mode)
        or metadata.st_uid != current_uid
        or metadata.st_mode & (stat.S_IWGRP | stat.S_IWOTH)
    ):
        raise StudioError("Creator profile filesystem entry is not trusted.")


def _same_inode(left: os.stat_result, right: os.stat_result) -> bool:
    return (left.st_dev, left.st_ino) == (right.st_dev, right.st_ino)


def _prepare_root(root: Path, *, create: bool) -> Path:
    root_path = Path(root)
    if root_path.is_symlink():
        raise StudioError("Profile root must not be a symbolic link.")
    if create:
        try:
            root_path.mkdir(parents=True, mode=0o700, exist_ok=True)
        except OSError as exc:
            raise StudioError("Could not create the profile root.") from exc
    try:
        metadata = root_path.lstat()
    except OSError as exc:
        raise StudioError("Creator profile directory is unavailable.") from exc
    _trusted_metadata(metadata)
    return root_path


def _open_path_directory(path: Path) -> int:
    try:
        descriptor = os.open(path, DIRECTORY_FLAGS)
        metadata = os.fstat(descriptor)
        _trusted_metadata(metadata)
        path_metadata = path.lstat()
        if stat.S_ISLNK(path_metadata.st_mode) or not _same_inode(metadata, path_metadata):
            raise StudioError("Creator profile directory changed while opening it.")
        return descriptor
    except StudioError:
        if "descriptor" in locals():
            os.close(descriptor)
        raise
    except OSError as exc:
        if "descriptor" in locals():
            os.close(descriptor)
        raise StudioError("Could not open the creator profile directory safely.") from exc


def _open_directory_at(parent_fd: int, name: str, *, trusted: bool = True) -> int:
    try:
        descriptor = os.open(name, DIRECTORY_FLAGS, dir_fd=parent_fd)
        metadata = os.fstat(descriptor)
        if trusted:
            _trusted_metadata(metadata)
        elif not stat.S_ISDIR(metadata.st_mode):
            raise StudioError("Profile entry is not a directory.")
        linked = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        if stat.S_ISLNK(linked.st_mode) or not _same_inode(metadata, linked):
            raise StudioError("Profile directory changed while opening it.")
        return descriptor
    except StudioError:
        if "descriptor" in locals():
            os.close(descriptor)
        raise
    except OSError as exc:
        if "descriptor" in locals():
            os.close(descriptor)
        raise StudioError("Could not open a profile directory safely.") from exc


def _read_bytes_at(dir_fd: int, name: str) -> bytes:
    descriptor: int | None = None
    try:
        descriptor = os.open(name, os.O_RDONLY | FILE_NOFOLLOW, dir_fd=dir_fd)
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise StudioError("Profile document is not a regular file.")
        chunks: list[bytes] = []
        while True:
            chunk = os.read(descriptor, 64 * 1024)
            if not chunk:
                return b"".join(chunks)
            chunks.append(chunk)
    except StudioError:
        raise
    except OSError as exc:
        raise StudioError("Could not read a profile document safely.") from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _read_text_at(dir_fd: int, name: str) -> str:
    try:
        return _read_bytes_at(dir_fd, name).decode("utf-8")
    except UnicodeError as exc:
        raise StudioError("Profile document is not valid UTF-8.") from exc


def _json_text(value: dict[str, Any]) -> str:
    try:
        return json.dumps(
            value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False
        ) + "\n"
    except (TypeError, ValueError) as exc:
        raise StudioError("Profile JSON contains unsupported data.") from exc


def _read_json_at(dir_fd: int, name: str) -> dict[str, Any]:
    def reject_non_finite(constant: str) -> None:
        raise ValueError(f"non-finite JSON constant: {constant}")

    try:
        value = json.loads(
            _read_text_at(dir_fd, name), parse_constant=reject_non_finite
        )
    except (ValueError, TypeError) as exc:
        raise StudioError("Could not read valid profile JSON.") from exc
    if not isinstance(value, dict):
        raise StudioError("Profile JSON must contain an object.")
    return value


def _atomic_write_at(dir_fd: int, name: str, content: str) -> None:
    """Atomically write one direct child without following any symlink."""
    if Path(name).name != name or not isinstance(content, str):
        raise StudioError("Unsafe atomic profile write request.")
    temporary = f".{name}.{uuid.uuid4().hex}.tmp"
    descriptor: int | None = None
    try:
        data = content.encode("utf-8")
        descriptor = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | FILE_NOFOLLOW,
            0o600,
            dir_fd=dir_fd,
        )
        view = memoryview(data)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise OSError("atomic profile write made no progress")
            view = view[written:]
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = None
        os.rename(temporary, name, src_dir_fd=dir_fd, dst_dir_fd=dir_fd)
        os.fsync(dir_fd)
    except BaseException as exc:
        if descriptor is not None:
            try:
                os.close(descriptor)
            except OSError:
                pass
        try:
            os.unlink(temporary, dir_fd=dir_fd)
        except OSError:
            pass
        if isinstance(exc, (OSError, UnicodeError)):
            raise StudioError("Could not save the profile file safely.") from exc
        raise


def _entry_exists_at(dir_fd: int, name: str) -> bool:
    try:
        os.stat(name, dir_fd=dir_fd, follow_symlinks=False)
        return True
    except FileNotFoundError:
        return False
    except OSError as exc:
        raise StudioError("Could not inspect the profile entry safely.") from exc


def _remove_tree_at(parent_fd: int, name: str) -> None:
    descriptor = _open_directory_at(parent_fd, name, trusted=False)
    try:
        for child in os.listdir(descriptor):
            metadata = os.stat(child, dir_fd=descriptor, follow_symlinks=False)
            if stat.S_ISDIR(metadata.st_mode) and not stat.S_ISLNK(metadata.st_mode):
                _remove_tree_at(descriptor, child)
            else:
                os.unlink(child, dir_fd=descriptor)
    except OSError as exc:
        raise StudioError("Could not clean profile transaction data.") from exc
    finally:
        os.close(descriptor)
    try:
        os.rmdir(name, dir_fd=parent_fd)
    except OSError as exc:
        raise StudioError("Could not remove profile transaction directory.") from exc


def _unlink_at(dir_fd: int, name: str) -> None:
    try:
        os.unlink(name, dir_fd=dir_fd)
    except FileNotFoundError:
        return
    except OSError as exc:
        raise StudioError("Could not remove profile transaction file.") from exc


def _template_content(display_name: str) -> str:
    template_path = Path(__file__).resolve().parents[1] / "assets" / "profile-template.md"
    try:
        template = template_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise StudioError("Could not read the creator profile template.") from exc
    return template.replace("{{display_name}}", display_name)


def _parse_timestamp(value: Any) -> datetime:
    if not isinstance(value, str) or not TIMESTAMP_PATTERN.fullmatch(value):
        raise StudioError("Profile manifest timestamp is invalid.")
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError as exc:
        raise StudioError("Profile manifest timestamp is invalid.") from exc


def _load_manifest_at(
    profile_fd: int, versions_fd: int, expected_profile_id: str
) -> dict[str, Any]:
    manifest = _read_json_at(versions_fd, "manifest.json")
    if manifest.get("profile_id") != expected_profile_id:
        raise StudioError("Profile manifest does not match its directory.")
    display_name = manifest.get("display_name")
    if not isinstance(display_name, str) or not display_name.strip():
        raise StudioError("Profile manifest display name is invalid.")
    created_at = _parse_timestamp(manifest.get("created_at"))
    updated_at = _parse_timestamp(manifest.get("updated_at"))
    if created_at > updated_at:
        raise StudioError("Profile manifest timestamps are out of order.")

    versions = manifest.get("versions")
    if not isinstance(versions, list):
        raise StudioError("Profile version manifest has an invalid schema.")
    previous = 0
    expected_directories: set[str] = set()
    for entry in versions:
        if not isinstance(entry, dict):
            raise StudioError("Profile version manifest has an invalid schema.")
        version = entry.get("version")
        directory = entry.get("directory")
        change_note = entry.get("change_note")
        timestamp = entry.get("timestamp")
        if (
            type(version) is not int
            or version <= previous
            or version <= 0
            or directory != f"v{version:03d}"
            or not isinstance(change_note, str)
            or not change_note.strip()
        ):
            raise StudioError("Profile version manifest has an invalid entry.")
        _parse_timestamp(timestamp)
        snapshot_fd = _open_directory_at(versions_fd, directory, trusted=False)
        try:
            for document in PROFILE_DOCUMENTS:
                _read_bytes_at(snapshot_fd, document)
        finally:
            os.close(snapshot_fd)
        expected_directories.add(directory)
        previous = version
    try:
        actual_directories = {
            name
            for name in os.listdir(versions_fd)
            if VERSION_DIRECTORY_PATTERN.fullmatch(name)
        }
    except OSError as exc:
        raise StudioError("Could not inspect profile version history.") from exc
    if actual_directories != expected_directories:
        raise StudioError("Profile version history contains an orphan snapshot.")
    for document in PROFILE_DOCUMENTS:
        _read_bytes_at(profile_fd, document)
    samples_fd = _open_directory_at(profile_fd, "samples", trusted=False)
    os.close(samples_fd)
    return manifest


def _revalidate_open_directories(handles: LockedProfile) -> None:
    """Verify pathname entries still name the already-open trusted inodes."""
    root_metadata = handles.root_path.lstat()
    if stat.S_ISLNK(root_metadata.st_mode) or not _same_inode(
        root_metadata, os.fstat(handles.root_fd)
    ):
        raise StudioError("Profile root changed during the operation.")
    profile_metadata = os.stat(
        handles.profile_id, dir_fd=handles.root_fd, follow_symlinks=False
    )
    if stat.S_ISLNK(profile_metadata.st_mode) or not _same_inode(
        profile_metadata, os.fstat(handles.profile_fd)
    ):
        raise StudioError("Profile directory changed during the operation.")
    versions_metadata = os.stat(
        "versions", dir_fd=handles.profile_fd, follow_symlinks=False
    )
    if stat.S_ISLNK(versions_metadata.st_mode) or not _same_inode(
        versions_metadata, os.fstat(handles.versions_fd)
    ):
        raise StudioError("Versions directory changed during the operation.")


@contextmanager
def _locked_profile_from_root_fd(
    root_path: Path, root_fd: int, profile_id: str
) -> Iterator[LockedProfile]:
    profile_id = _validate_profile_id(profile_id)
    profile_fd: int | None = None
    versions_fd: int | None = None
    lock_fd: int | None = None
    try:
        profile_fd = _open_directory_at(root_fd, profile_id)
        lock_fd = os.open(
            LOCK_NAME,
            os.O_RDWR | os.O_CREAT | FILE_NOFOLLOW,
            0o600,
            dir_fd=profile_fd,
        )
        opened_lock = os.fstat(lock_fd)
        _trusted_metadata(opened_lock, regular=True)
        fcntl.flock(lock_fd, fcntl.LOCK_EX)
        linked_lock = os.stat(LOCK_NAME, dir_fd=profile_fd, follow_symlinks=False)
        if stat.S_ISLNK(linked_lock.st_mode) or not _same_inode(
            opened_lock, linked_lock
        ):
            raise StudioError("Creator profile lock changed while opening it.")
        versions_fd = _open_directory_at(profile_fd, "versions")
        handles = LockedProfile(
            root_path, profile_id, root_fd, profile_fd, versions_fd
        )
        _revalidate_open_directories(handles)
        yield handles
    except StudioError:
        raise
    except OSError as exc:
        raise StudioError("Could not lock the creator profile safely.") from exc
    finally:
        if lock_fd is not None:
            try:
                fcntl.flock(lock_fd, fcntl.LOCK_UN)
            except OSError:
                pass
            os.close(lock_fd)
        if versions_fd is not None:
            os.close(versions_fd)
        if profile_fd is not None:
            os.close(profile_fd)


@contextmanager
def _locked_profile(root: Path, profile_id: str) -> Iterator[LockedProfile]:
    root_path = _prepare_root(root, create=False)
    root_fd = _open_path_directory(root_path)
    try:
        with _locked_profile_from_root_fd(root_path, root_fd, profile_id) as handles:
            yield handles
    finally:
        os.close(root_fd)


def _transaction_names(profile_fd: int) -> list[str]:
    try:
        return sorted(
            name
            for name in os.listdir(profile_fd)
            if TRANSACTION_DIRECTORY_PATTERN.fullmatch(name)
        )
    except OSError as exc:
        raise StudioError("Could not inspect profile transaction staging.") from exc


def _validate_journal(
    journal: dict[str, Any], profile_id: str
) -> tuple[str, str, str, str]:
    staging_name = journal.get("staging_directory")
    version_name = journal.get("version_directory")
    state = journal.get("state")
    phase = journal.get("phase")
    if (
        journal.get("profile_id") != profile_id
        or not isinstance(staging_name, str)
        or not TRANSACTION_DIRECTORY_PATTERN.fullmatch(staging_name)
        or not isinstance(version_name, str)
        or not VERSION_DIRECTORY_PATTERN.fullmatch(version_name)
        or state not in {"pending", "rolled_back", "committed"}
        or phase not in {"intent", "staged"}
    ):
        raise StudioError("Profile recovery journal is invalid.")
    return staging_name, version_name, state, phase


def _remove_snapshot_at(versions_fd: int, version_name: str) -> None:
    if _entry_exists_at(versions_fd, version_name):
        _remove_tree_at(versions_fd, version_name)


def _cleanup_transaction_at(
    profile_fd: int, staging_name: str, *, remove_journal: bool = True
) -> None:
    if _entry_exists_at(profile_fd, staging_name):
        _remove_tree_at(profile_fd, staging_name)
    if remove_journal:
        _unlink_at(profile_fd, JOURNAL_NAME)


def _scan_unjournaled_staging(profile_fd: int, keep: str | None = None) -> None:
    for name in _transaction_names(profile_fd):
        if name != keep:
            _remove_tree_at(profile_fd, name)


def _recover_transaction_at(handles: LockedProfile) -> None:
    if not _entry_exists_at(handles.profile_fd, JOURNAL_NAME):
        _scan_unjournaled_staging(handles.profile_fd)
        return
    journal = _read_json_at(handles.profile_fd, JOURNAL_NAME)
    staging_name, version_name, state, phase = _validate_journal(
        journal, handles.profile_id
    )
    if state in {"rolled_back", "committed"}:
        _cleanup_transaction_at(handles.profile_fd, staging_name)
        _scan_unjournaled_staging(handles.profile_fd)
        return

    if phase == "staged":
        if not _entry_exists_at(handles.profile_fd, staging_name):
            raise StudioError("Profile recovery staging is unavailable.")
        staging_fd = _open_directory_at(handles.profile_fd, staging_name)
        try:
            old_fd = _open_directory_at(staging_fd, "old", trusted=False)
            try:
                old_profile = _read_text_at(old_fd, "profile.md")
                old_manifest = _read_text_at(old_fd, "manifest.json")
            finally:
                os.close(old_fd)
        finally:
            os.close(staging_fd)
        _atomic_write_at(handles.profile_fd, "profile.md", old_profile)
        _atomic_write_at(handles.versions_fd, "manifest.json", old_manifest)
    _remove_snapshot_at(handles.versions_fd, version_name)
    journal["state"] = "rolled_back"
    _atomic_write_at(handles.profile_fd, JOURNAL_NAME, _json_text(journal))
    _cleanup_transaction_at(handles.profile_fd, staging_name)
    _scan_unjournaled_staging(handles.profile_fd)


def _read_profile_at(
    handles: LockedProfile, manifest: dict[str, Any] | None = None
) -> dict:
    if manifest is None:
        manifest = _load_manifest_at(
            handles.profile_fd, handles.versions_fd, handles.profile_id
        )
    return {
        "content": _read_text_at(handles.profile_fd, "profile.md"),
        "created_at": manifest["created_at"],
        "display_name": manifest["display_name"],
        "profile_id": handles.profile_id,
        "style_analysis": _read_text_at(handles.profile_fd, "style-analysis.md"),
        "constraints": _read_text_at(handles.profile_fd, "constraints.md"),
        "updated_at": manifest["updated_at"],
        "version_count": len(manifest["versions"]),
    }


def create_profile(root: Path, profile_id: str, display_name: str) -> dict:
    """Create a new isolated profile without overwriting an existing profile."""
    profile_id = _validate_profile_id(profile_id)
    _validate_text(display_name, "Display name")
    root_path = _prepare_root(root, create=True)
    root_fd = _open_path_directory(root_path)
    try:
        try:
            os.mkdir(profile_id, mode=0o700, dir_fd=root_fd)
        except FileExistsError as exc:
            raise StudioError("Creator profile already exists.") from exc
        try:
            profile_fd = _open_directory_at(root_fd, profile_id)
            try:
                lock_fd = os.open(
                    LOCK_NAME,
                    os.O_RDWR | os.O_CREAT | FILE_NOFOLLOW,
                    0o600,
                    dir_fd=profile_fd,
                )
                fcntl.flock(lock_fd, fcntl.LOCK_EX)
                try:
                    os.mkdir("samples", mode=0o700, dir_fd=profile_fd)
                    os.mkdir("versions", mode=0o700, dir_fd=profile_fd)
                    versions_fd = _open_directory_at(profile_fd, "versions")
                    try:
                        created_at = utc_now_iso()
                        _atomic_write_at(
                            profile_fd, "profile.md", _template_content(display_name)
                        )
                        _atomic_write_at(
                            profile_fd, "style-analysis.md", STYLE_ANALYSIS
                        )
                        _atomic_write_at(profile_fd, "constraints.md", CONSTRAINTS)
                        _atomic_write_at(
                            versions_fd,
                            "manifest.json",
                            _json_text(
                                {
                                    "created_at": created_at,
                                    "display_name": display_name,
                                    "profile_id": profile_id,
                                    "updated_at": created_at,
                                    "versions": [],
                                }
                            ),
                        )
                    finally:
                        os.close(versions_fd)
                finally:
                    fcntl.flock(lock_fd, fcntl.LOCK_UN)
                    os.close(lock_fd)
            finally:
                os.close(profile_fd)
        except BaseException as exc:
            if _entry_exists_at(root_fd, profile_id):
                try:
                    _remove_tree_at(root_fd, profile_id)
                except StudioError:
                    pass
            if isinstance(exc, Exception):
                if isinstance(exc, StudioError):
                    raise
                raise StudioError("Could not create the creator profile safely.") from exc
            raise
    finally:
        os.close(root_fd)
    return read_profile(root_path, profile_id)


def read_profile(root: Path, profile_id: str) -> dict:
    """Read and recover one profile using inode-bound directory descriptors."""
    with _locked_profile(root, profile_id) as handles:
        _recover_transaction_at(handles)
        manifest = _load_manifest_at(
            handles.profile_fd, handles.versions_fd, handles.profile_id
        )
        return _read_profile_at(handles, manifest)


def _stage_update_at(
    handles: LockedProfile,
    manifest: dict[str, Any],
    content: str,
    change_note: str,
) -> tuple[str, str, dict[str, Any], int, str]:
    version = manifest["versions"][-1]["version"] + 1 if manifest["versions"] else 1
    version_name = f"v{version:03d}"
    if _entry_exists_at(handles.versions_fd, version_name):
        raise StudioError("The next profile version already exists.")
    staging_name = f".profile-txn-{uuid.uuid4().hex}"
    timestamp = utc_now_iso()
    new_manifest = dict(manifest)
    new_manifest["updated_at"] = timestamp
    new_manifest["versions"] = [
        *manifest["versions"],
        {
            "change_note": change_note,
            "directory": version_name,
            "timestamp": timestamp,
            "version": version,
        },
    ]
    journal = {
        "phase": "intent",
        "profile_id": handles.profile_id,
        "staging_directory": staging_name,
        "state": "pending",
        "version_directory": version_name,
    }
    os.mkdir(staging_name, mode=0o700, dir_fd=handles.profile_fd)
    _atomic_write_at(handles.profile_fd, JOURNAL_NAME, _json_text(journal))
    staging_fd = _open_directory_at(handles.profile_fd, staging_name)
    try:
        for name in ("old", "new", "snapshot"):
            os.mkdir(name, mode=0o700, dir_fd=staging_fd)
        old_fd = _open_directory_at(staging_fd, "old", trusted=False)
        new_fd = _open_directory_at(staging_fd, "new", trusted=False)
        snapshot_fd = _open_directory_at(staging_fd, "snapshot", trusted=False)
        try:
            _atomic_write_at(
                old_fd, "profile.md", _read_text_at(handles.profile_fd, "profile.md")
            )
            _atomic_write_at(
                old_fd,
                "manifest.json",
                _read_text_at(handles.versions_fd, "manifest.json"),
            )
            _atomic_write_at(new_fd, "profile.md", content)
            _atomic_write_at(new_fd, "manifest.json", _json_text(new_manifest))
            for document in PROFILE_DOCUMENTS:
                _atomic_write_at(
                    snapshot_fd,
                    document,
                    _read_text_at(handles.profile_fd, document),
                )
        finally:
            os.close(snapshot_fd)
            os.close(new_fd)
            os.close(old_fd)
    finally:
        os.close(staging_fd)
    journal["phase"] = "staged"
    _atomic_write_at(handles.profile_fd, JOURNAL_NAME, _json_text(journal))
    return staging_name, version_name, new_manifest, version, timestamp


def update_profile(
    root: Path,
    profile_id: str,
    content: str,
    confirmed: bool,
    change_note: str,
) -> dict:
    """Replace ``profile.md`` in an inode-bound recoverable transaction."""
    if confirmed is not True:
        raise StudioError("Profile updates require explicit confirmation.")
    _validate_text(content, "Profile content")
    _validate_text(change_note, "Change note")
    with _locked_profile(root, profile_id) as handles:
        _recover_transaction_at(handles)
        manifest = _load_manifest_at(
            handles.profile_fd, handles.versions_fd, handles.profile_id
        )
        try:
            staging_name, version_name, new_manifest, version, timestamp = (
                _stage_update_at(handles, manifest, content, change_note)
            )
            _revalidate_open_directories(handles)
            staging_fd = _open_directory_at(handles.profile_fd, staging_name)
            try:
                new_fd = _open_directory_at(staging_fd, "new", trusted=False)
                try:
                    new_profile = _read_text_at(new_fd, "profile.md")
                    new_manifest_text = _read_text_at(new_fd, "manifest.json")
                finally:
                    os.close(new_fd)
                os.rename(
                    "snapshot",
                    version_name,
                    src_dir_fd=staging_fd,
                    dst_dir_fd=handles.versions_fd,
                )
            finally:
                os.close(staging_fd)
            _atomic_write_at(handles.profile_fd, "profile.md", new_profile)
            _atomic_write_at(
                handles.versions_fd, "manifest.json", new_manifest_text
            )
            journal = _read_json_at(handles.profile_fd, JOURNAL_NAME)
            journal["state"] = "committed"
            _atomic_write_at(handles.profile_fd, JOURNAL_NAME, _json_text(journal))
        except BaseException as exc:
            try:
                _recover_transaction_at(handles)
            except Exception as recovery_exc:
                if isinstance(exc, Exception):
                    raise StudioError(
                        "Profile update failed; recovery will retry later."
                    ) from recovery_exc
            if isinstance(exc, Exception):
                if isinstance(exc, StudioError):
                    raise
                raise StudioError("Could not publish the creator profile update.") from exc
            raise
        try:
            _cleanup_transaction_at(handles.profile_fd, staging_name)
        except StudioError:
            pass
        result = _read_profile_at(handles, new_manifest)
        result.update(
            {"change_note": change_note, "timestamp": timestamp, "version": version}
        )
        return result


def list_profiles(root: Path) -> list[dict]:
    """List valid profiles in deterministic profile-ID order."""
    root_path = Path(root)
    if not root_path.exists() and not root_path.is_symlink():
        return []
    root_path = _prepare_root(root_path, create=False)
    root_fd = _open_path_directory(root_path)
    try:
        try:
            profile_ids = []
            for name in os.listdir(root_fd):
                if not PROFILE_ID_PATTERN.fullmatch(name):
                    continue
                metadata = os.stat(name, dir_fd=root_fd, follow_symlinks=False)
                if stat.S_ISDIR(metadata.st_mode) and not stat.S_ISLNK(metadata.st_mode):
                    profile_ids.append(name)
        except OSError as exc:
            raise StudioError("Could not list creator profiles.") from exc
        profiles = []
        for profile_id in sorted(profile_ids):
            with _locked_profile_from_root_fd(
                root_path, root_fd, profile_id
            ) as handles:
                _recover_transaction_at(handles)
                manifest = _load_manifest_at(
                    handles.profile_fd, handles.versions_fd, profile_id
                )
                profiles.append(
                    {
                        "display_name": manifest["display_name"],
                        "profile_id": profile_id,
                        "updated_at": manifest["updated_at"],
                        "version_count": len(manifest["versions"]),
                    }
                )
        return profiles
    finally:
        os.close(root_fd)


class JsonArgumentParser(argparse.ArgumentParser):
    """Argument parser whose failures are safe machine-readable JSON."""

    def error(self, message: str) -> None:
        del message
        print(
            json.dumps({"error": "Invalid command arguments."}, ensure_ascii=False),
            file=sys.stdout,
        )
        raise SystemExit(2)


def _build_parser() -> argparse.ArgumentParser:
    parser = JsonArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    commands = parser.add_subparsers(dest="command", required=True)
    create_parser = commands.add_parser("create")
    create_parser.add_argument("profile_id")
    create_parser.add_argument("display_name")
    read_parser = commands.add_parser("read")
    read_parser.add_argument("profile_id")
    update_parser = commands.add_parser("update")
    update_parser.add_argument("profile_id")
    update_parser.add_argument("content")
    update_parser.add_argument("--change-note", required=True)
    update_parser.add_argument("--confirmed", action="store_true", required=True)
    commands.add_parser("list")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        if args.command == "create":
            result = create_profile(args.root, args.profile_id, args.display_name)
        elif args.command == "read":
            result = read_profile(args.root, args.profile_id)
        elif args.command == "update":
            result = update_profile(
                args.root,
                args.profile_id,
                args.content,
                confirmed=args.confirmed,
                change_note=args.change_note,
            )
        else:
            result = list_profiles(args.root)
    except StudioError as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
