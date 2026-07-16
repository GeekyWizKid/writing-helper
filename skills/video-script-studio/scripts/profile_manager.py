"""Create, read, list, and transactionally version creator profiles.

``update_profile`` replaces only ``profile.md``. A confirmed update stages the
old and new profile state plus a snapshot of all three current Markdown files.
It then publishes under a per-profile filesystem lock. A small journal lets the
next operation finish rollback or cleanup if an ordinary filesystem failure
interrupts the transaction.
"""

from __future__ import annotations

import argparse
import fcntl
import importlib.util
import json
import os
import re
import shutil
import stat
import sys
import uuid
from contextlib import contextmanager
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
atomic_write_text = _common.atomic_write_text
read_json = _common.read_json
utc_now_iso = _common.utc_now_iso
write_json = _common.write_json

PROFILE_DOCUMENTS = ("profile.md", "style-analysis.md", "constraints.md")
PROFILE_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
VERSION_DIRECTORY_PATTERN = re.compile(r"^v[0-9]{3,}$")
TRANSACTION_DIRECTORY_PATTERN = re.compile(r"^\.profile-txn-[0-9a-f]{32}$")
LOCK_NAME = ".profile.lock"
JOURNAL_NAME = ".transaction.json"

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


def _has_expected_parent(path: Path, parent: Path) -> bool:
    try:
        return path.resolve().parent == parent.resolve()
    except (OSError, RuntimeError) as exc:
        raise StudioError("Could not resolve the creator profile safely.") from exc


def _trusted_directory(path: Path, parent: Path | None = None) -> Path:
    try:
        metadata = path.lstat()
    except OSError as exc:
        raise StudioError("Creator profile directory is unavailable.") from exc
    current_uid = os.getuid() if hasattr(os, "getuid") else metadata.st_uid
    if (
        stat.S_ISLNK(metadata.st_mode)
        or not stat.S_ISDIR(metadata.st_mode)
        or metadata.st_uid != current_uid
        or metadata.st_mode & (stat.S_IWGRP | stat.S_IWOTH)
        or (parent is not None and not _has_expected_parent(path, parent))
    ):
        raise StudioError("Creator profile directory is not trusted.")
    return path


def _prepare_root(root: Path, *, create: bool) -> Path:
    root_path = Path(root)
    if root_path.is_symlink():
        raise StudioError("Profile root must not be a symbolic link.")
    if create:
        try:
            root_path.mkdir(parents=True, mode=0o700, exist_ok=True)
        except OSError as exc:
            raise StudioError("Could not create the profile root.") from exc
    return _trusted_directory(root_path)


def _profile_path(root: Path, profile_id: str) -> Path:
    safe_id = _validate_profile_id(profile_id)
    candidate = root / safe_id
    if candidate.is_symlink():
        raise StudioError("Profile path must not be a symbolic link.")
    if candidate.parent != root:
        raise StudioError("Profile path is outside the profile root.")
    return candidate


def _require_direct_directory(parent: Path, name: str) -> Path:
    path = parent / name
    if path.is_symlink() or not path.is_dir() or not _has_expected_parent(path, parent):
        raise StudioError("Creator profile contains an unsafe directory.")
    return path


def _require_direct_file(parent: Path, name: str) -> Path:
    path = parent / name
    if path.is_symlink() or not path.is_file() or not _has_expected_parent(path, parent):
        raise StudioError("Creator profile contains an unsafe document.")
    return path


def _require_profile(root: Path, profile_id: str) -> Path:
    profile_path = _profile_path(root, profile_id)
    _trusted_directory(profile_path, root)
    for name in PROFILE_DOCUMENTS:
        _require_direct_file(profile_path, name)
    _require_direct_directory(profile_path, "samples")
    _require_direct_directory(profile_path, "versions")
    return profile_path


@contextmanager
def _profile_lock(root: Path, profile_path: Path) -> Iterator[None]:
    _trusted_directory(root)
    _trusted_directory(profile_path, root)
    lock_path = profile_path / LOCK_NAME
    flags = os.O_RDWR | os.O_CREAT
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor: int | None = None
    try:
        descriptor = os.open(lock_path, flags, 0o600)
        opened = os.fstat(descriptor)
        current_uid = os.getuid() if hasattr(os, "getuid") else opened.st_uid
        if (
            not stat.S_ISREG(opened.st_mode)
            or opened.st_uid != current_uid
            or opened.st_mode & (stat.S_IWGRP | stat.S_IWOTH)
        ):
            raise StudioError("Creator profile lock is not trusted.")
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        _trusted_directory(root)
        _trusted_directory(profile_path, root)
        if lock_path.is_symlink() or not _has_expected_parent(lock_path, profile_path):
            raise StudioError("Creator profile lock is not trusted.")
        current = lock_path.lstat()
        if (current.st_dev, current.st_ino) != (opened.st_dev, opened.st_ino):
            raise StudioError("Creator profile lock changed while opening it.")
        yield
    except StudioError:
        raise
    except OSError as exc:
        raise StudioError("Could not lock the creator profile safely.") from exc
    finally:
        if descriptor is not None:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_UN)
            except OSError:
                pass
            os.close(descriptor)


def _template_content(display_name: str) -> str:
    template_path = Path(__file__).resolve().parents[1] / "assets" / "profile-template.md"
    try:
        template = template_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise StudioError("Could not read the creator profile template.") from exc
    return template.replace("{{display_name}}", display_name)


def _read_text(path: Path, error: str) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise StudioError(error) from exc


def _json_text(value: dict[str, Any]) -> str:
    try:
        return json.dumps(
            value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False
        ) + "\n"
    except (TypeError, ValueError) as exc:
        raise StudioError("Profile manifest contains unsupported data.") from exc


def _load_manifest(profile_path: Path, expected_profile_id: str) -> dict[str, Any]:
    versions_path = _require_direct_directory(profile_path, "versions")
    manifest_path = _require_direct_file(versions_path, "manifest.json")
    manifest = read_json(manifest_path)
    if manifest.get("profile_id") != expected_profile_id:
        raise StudioError("Profile manifest does not match its directory.")
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
            or not isinstance(timestamp, str)
            or not timestamp.strip()
        ):
            raise StudioError("Profile version manifest has an invalid entry.")
        snapshot_path = _require_direct_directory(versions_path, directory)
        for name in PROFILE_DOCUMENTS:
            _require_direct_file(snapshot_path, name)
        expected_directories.add(directory)
        previous = version

    try:
        actual_directories = {
            entry.name
            for entry in versions_path.iterdir()
            if VERSION_DIRECTORY_PATTERN.fullmatch(entry.name)
        }
    except OSError as exc:
        raise StudioError("Could not inspect the profile version history.") from exc
    if actual_directories != expected_directories:
        raise StudioError("Profile version history contains an orphan snapshot.")
    return manifest


def _transaction_paths(profile_path: Path, journal: dict[str, Any]) -> tuple[Path, Path]:
    staging_name = journal.get("staging_directory")
    version_name = journal.get("version_directory")
    if (
        journal.get("profile_id") != profile_path.name
        or not isinstance(staging_name, str)
        or not TRANSACTION_DIRECTORY_PATTERN.fullmatch(staging_name)
        or not isinstance(version_name, str)
        or not VERSION_DIRECTORY_PATTERN.fullmatch(version_name)
    ):
        raise StudioError("Profile recovery journal is invalid.")
    return profile_path / staging_name, profile_path / "versions" / version_name


def _remove_snapshot(version_path: Path, versions_path: Path) -> None:
    if version_path.is_symlink():
        raise StudioError("Profile recovery found an unsafe snapshot.")
    if version_path.exists():
        if not version_path.is_dir() or not _has_expected_parent(version_path, versions_path):
            raise StudioError("Profile recovery found an unsafe snapshot.")
        try:
            shutil.rmtree(version_path)
        except OSError as exc:
            raise StudioError("Could not remove an unpublished profile snapshot.") from exc


def _cleanup_finished_transaction(
    profile_path: Path, journal_path: Path, staging_path: Path
) -> None:
    if staging_path.is_symlink():
        raise StudioError("Profile recovery found unsafe staging data.")
    if staging_path.exists():
        if not staging_path.is_dir() or not _has_expected_parent(staging_path, profile_path):
            raise StudioError("Profile recovery found unsafe staging data.")
        try:
            shutil.rmtree(staging_path)
        except OSError as exc:
            raise StudioError("Could not remove profile transaction staging.") from exc
    try:
        journal_path.unlink(missing_ok=True)
    except OSError as exc:
        raise StudioError("Could not finish profile transaction cleanup.") from exc


def _recover_transaction(profile_path: Path) -> None:
    journal_path = profile_path / JOURNAL_NAME
    if journal_path.is_symlink():
        raise StudioError("Profile recovery journal is unsafe.")
    if not journal_path.exists():
        return
    _require_direct_file(profile_path, JOURNAL_NAME)
    journal = read_json(journal_path)
    state = journal.get("state")
    if state not in {"pending", "rolled_back", "committed"}:
        raise StudioError("Profile recovery journal is invalid.")
    staging_path, version_path = _transaction_paths(profile_path, journal)
    versions_path = _require_direct_directory(profile_path, "versions")

    if state in {"rolled_back", "committed"}:
        _cleanup_finished_transaction(profile_path, journal_path, staging_path)
        return

    if not staging_path.exists():
        _remove_snapshot(version_path, versions_path)
        journal["state"] = "rolled_back"
        write_json(journal_path, journal)
        _cleanup_finished_transaction(profile_path, journal_path, staging_path)
        return

    staging_path = _require_direct_directory(profile_path, staging_path.name)
    old_path = _require_direct_directory(staging_path, "old")
    old_profile_path = _require_direct_file(old_path, "profile.md")
    old_manifest_path = _require_direct_file(old_path, "manifest.json")
    old_profile = _read_text(old_profile_path, "Could not read profile recovery data.")
    old_manifest = _read_text(old_manifest_path, "Could not read profile recovery data.")
    try:
        atomic_write_text(profile_path / "profile.md", old_profile)
        atomic_write_text(versions_path / "manifest.json", old_manifest)
        _remove_snapshot(version_path, versions_path)
        journal["state"] = "rolled_back"
        write_json(journal_path, journal)
        _cleanup_finished_transaction(profile_path, journal_path, staging_path)
    except StudioError:
        raise
    except OSError as exc:
        raise StudioError("Could not recover the interrupted profile update.") from exc


def _read_profile_locked(
    profile_path: Path, profile_id: str, manifest: dict[str, Any] | None = None
) -> dict:
    if manifest is None:
        manifest = _load_manifest(profile_path, profile_id)
    documents = {
        name: _read_text(
            _require_direct_file(profile_path, name),
            "Could not read the creator profile.",
        )
        for name in PROFILE_DOCUMENTS
    }
    return {
        "content": documents["profile.md"],
        "created_at": manifest.get("created_at"),
        "display_name": manifest.get("display_name"),
        "profile_id": profile_id,
        "style_analysis": documents["style-analysis.md"],
        "constraints": documents["constraints.md"],
        "updated_at": manifest.get("updated_at"),
        "version_count": len(manifest["versions"]),
    }


def create_profile(root: Path, profile_id: str, display_name: str) -> dict:
    """Create a new isolated profile without overwriting an existing profile."""
    _validate_text(display_name, "Display name")
    root_path = _prepare_root(root, create=True)
    profile_path = _profile_path(root_path, profile_id)
    created_at = utc_now_iso()
    try:
        profile_path.mkdir(mode=0o700, exist_ok=False)
    except FileExistsError as exc:
        raise StudioError("Creator profile already exists.") from exc
    except OSError as exc:
        raise StudioError("Could not create the creator profile.") from exc

    try:
        (profile_path / "samples").mkdir(mode=0o700)
        (profile_path / "versions").mkdir(mode=0o700)
        atomic_write_text(profile_path / "profile.md", _template_content(display_name))
        atomic_write_text(profile_path / "style-analysis.md", STYLE_ANALYSIS)
        atomic_write_text(profile_path / "constraints.md", CONSTRAINTS)
        write_json(
            profile_path / "versions" / "manifest.json",
            {
                "created_at": created_at,
                "display_name": display_name,
                "profile_id": profile_id,
                "updated_at": created_at,
                "versions": [],
            },
        )
        with _profile_lock(root_path, profile_path):
            _require_profile(root_path, profile_id)
            _load_manifest(profile_path, profile_id)
    except Exception as exc:
        shutil.rmtree(profile_path, ignore_errors=True)
        if isinstance(exc, StudioError):
            raise
        raise StudioError("Could not initialize the creator profile safely.") from exc
    return read_profile(root_path, profile_id)


def read_profile(root: Path, profile_id: str) -> dict:
    """Read one validated profile while holding its trusted filesystem lock."""
    root_path = _prepare_root(root, create=False)
    profile_path = _profile_path(root_path, profile_id)
    _trusted_directory(profile_path, root_path)
    with _profile_lock(root_path, profile_path):
        _recover_transaction(profile_path)
        _require_profile(root_path, profile_id)
        manifest = _load_manifest(profile_path, profile_id)
        return _read_profile_locked(profile_path, profile_id, manifest)


def _stage_update(
    profile_path: Path,
    profile_id: str,
    manifest: dict[str, Any],
    content: str,
    change_note: str,
) -> tuple[Path, Path, dict[str, Any], int, str]:
    version = manifest["versions"][-1]["version"] + 1 if manifest["versions"] else 1
    version_name = f"v{version:03d}"
    versions_path = _require_direct_directory(profile_path, "versions")
    version_path = versions_path / version_name
    if version_path.exists() or version_path.is_symlink():
        raise StudioError("The next profile version already exists.")

    staging_path = profile_path / f".profile-txn-{uuid.uuid4().hex}"
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
        "profile_id": profile_id,
        "staging_directory": staging_path.name,
        "state": "pending",
        "version_directory": version_name,
    }

    try:
        staging_path.mkdir(mode=0o700)
        old_path = staging_path / "old"
        new_path = staging_path / "new"
        snapshot_path = staging_path / "snapshot"
        for path in (old_path, new_path, snapshot_path):
            path.mkdir(mode=0o700)
        old_profile = _read_text(
            _require_direct_file(profile_path, "profile.md"),
            "Could not stage the creator profile.",
        )
        old_manifest = _read_text(
            _require_direct_file(versions_path, "manifest.json"),
            "Could not stage the profile manifest.",
        )
        atomic_write_text(old_path / "profile.md", old_profile)
        atomic_write_text(old_path / "manifest.json", old_manifest)
        atomic_write_text(new_path / "profile.md", content)
        atomic_write_text(new_path / "manifest.json", _json_text(new_manifest))
        for name in PROFILE_DOCUMENTS:
            current = _read_text(
                _require_direct_file(profile_path, name),
                "Could not stage the profile snapshot.",
            )
            atomic_write_text(snapshot_path / name, current)
        write_json(profile_path / JOURNAL_NAME, journal)
    except Exception as exc:
        shutil.rmtree(staging_path, ignore_errors=True)
        try:
            (profile_path / JOURNAL_NAME).unlink(missing_ok=True)
        except OSError:
            pass
        if isinstance(exc, StudioError):
            raise
        raise StudioError("Could not stage the creator profile update.") from exc
    return staging_path, version_path, new_manifest, version, timestamp


def update_profile(
    root: Path,
    profile_id: str,
    content: str,
    confirmed: bool,
    change_note: str,
) -> dict:
    """Replace ``profile.md`` transactionally after explicit confirmation."""
    if confirmed is not True:
        raise StudioError("Profile updates require explicit confirmation.")
    _validate_text(content, "Profile content")
    _validate_text(change_note, "Change note")
    root_path = _prepare_root(root, create=False)
    profile_path = _profile_path(root_path, profile_id)
    _trusted_directory(profile_path, root_path)

    with _profile_lock(root_path, profile_path):
        _recover_transaction(profile_path)
        _require_profile(root_path, profile_id)
        manifest = _load_manifest(profile_path, profile_id)
        staging_path, version_path, new_manifest, version, timestamp = _stage_update(
            profile_path, profile_id, manifest, content, change_note
        )
        journal_path = profile_path / JOURNAL_NAME
        versions_path = _require_direct_directory(profile_path, "versions")
        journal = read_json(journal_path)
        try:
            (staging_path / "snapshot").rename(version_path)
            new_profile = _read_text(
                _require_direct_file(staging_path / "new", "profile.md"),
                "Could not read staged profile content.",
            )
            new_manifest_text = _read_text(
                _require_direct_file(staging_path / "new", "manifest.json"),
                "Could not read staged profile manifest.",
            )
            atomic_write_text(profile_path / "profile.md", new_profile)
            atomic_write_text(versions_path / "manifest.json", new_manifest_text)
            journal["state"] = "committed"
            write_json(journal_path, journal)
        except Exception as exc:
            try:
                _recover_transaction(profile_path)
            except Exception as recovery_exc:
                raise StudioError(
                    "Profile update failed; recovery will retry on the next operation."
                ) from recovery_exc
            if isinstance(exc, StudioError):
                raise
            raise StudioError("Could not publish the creator profile update.") from exc

        try:
            _cleanup_finished_transaction(profile_path, journal_path, staging_path)
        except StudioError:
            # The committed journal makes this cleanup safely retryable.
            pass
        result = _read_profile_locked(profile_path, profile_id, new_manifest)
        result["change_note"] = change_note
        result["timestamp"] = timestamp
        result["version"] = version
        return result


def list_profiles(root: Path) -> list[dict]:
    """List valid profiles in deterministic profile-ID order."""
    root_path = Path(root)
    if not root_path.exists() and not root_path.is_symlink():
        return []
    root_path = _prepare_root(root_path, create=False)
    try:
        profile_ids = sorted(
            entry.name
            for entry in root_path.iterdir()
            if not entry.is_symlink()
            and entry.is_dir()
            and PROFILE_ID_PATTERN.fullmatch(entry.name)
        )
    except OSError as exc:
        raise StudioError("Could not list creator profiles.") from exc
    profiles = []
    for profile_id in profile_ids:
        profile = read_profile(root_path, profile_id)
        profiles.append(
            {
                "display_name": profile["display_name"],
                "profile_id": profile_id,
                "updated_at": profile["updated_at"],
                "version_count": profile["version_count"],
            }
        )
    return profiles


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
