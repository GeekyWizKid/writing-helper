"""Create, read, list, and explicitly version creator profiles.

``update_profile`` replaces only ``profile.md``. Before that replacement, a
confirmed update snapshots all three current Markdown documents so style and
constraint history remains coupled to the profile version.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import shutil
import sys
from pathlib import Path
from types import ModuleType
from typing import Any


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


def _profile_path(root: Path, profile_id: str) -> Path:
    safe_id = _validate_profile_id(profile_id)
    try:
        root_path = Path(root)
        resolved_root = root_path.resolve()
        candidate = root_path / safe_id
        if candidate.is_symlink():
            raise StudioError("Profile path must not be a symbolic link.")
        if candidate.exists() and candidate.resolve().parent != resolved_root:
            raise StudioError("Profile path is outside the profile root.")
        if candidate.parent.resolve() != resolved_root:
            raise StudioError("Profile path is outside the profile root.")
        return candidate
    except (OSError, RuntimeError) as exc:
        raise StudioError("Could not resolve the profile path safely.") from exc


def _validate_text(value: str, label: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str) or (not allow_empty and not value.strip()):
        raise StudioError(f"{label} must be non-empty text.")
    return value


def _template_content(display_name: str) -> str:
    template_path = Path(__file__).resolve().parents[1] / "assets" / "profile-template.md"
    try:
        template = template_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise StudioError("Could not read the creator profile template.") from exc
    return template.replace("{{display_name}}", display_name)


def _load_manifest(profile_path: Path) -> dict[str, Any]:
    versions_path = _require_direct_directory(profile_path, "versions")
    manifest_path = _require_direct_file(versions_path, "manifest.json")
    manifest = read_json(manifest_path)
    versions = manifest.get("versions")
    if not isinstance(versions, list) or any(
        not isinstance(item, dict) or not isinstance(item.get("version"), int)
        for item in versions
    ):
        raise StudioError("Profile version manifest has an invalid schema.")
    return manifest


def _has_expected_parent(path: Path, parent: Path) -> bool:
    try:
        return path.resolve().parent == parent.resolve()
    except (OSError, RuntimeError) as exc:
        raise StudioError("Could not resolve the creator profile safely.") from exc


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
    if (
        profile_path.is_symlink()
        or not profile_path.is_dir()
        or not _has_expected_parent(profile_path, Path(root))
    ):
        raise StudioError("Creator profile does not exist.")
    for name in PROFILE_DOCUMENTS:
        _require_direct_file(profile_path, name)
    _require_direct_directory(profile_path, "samples")
    _require_direct_directory(profile_path, "versions")
    return profile_path


def create_profile(root: Path, profile_id: str, display_name: str) -> dict:
    """Create a new isolated profile without overwriting an existing profile."""
    _validate_text(display_name, "Display name")
    profile_path = _profile_path(root, profile_id)
    created_at = utc_now_iso()
    try:
        profile_path.mkdir(parents=True, exist_ok=False)
    except FileExistsError as exc:
        raise StudioError("Creator profile already exists.") from exc
    except OSError as exc:
        raise StudioError("Could not create the creator profile.") from exc

    try:
        (profile_path / "samples").mkdir()
        (profile_path / "versions").mkdir()
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
    except Exception:
        shutil.rmtree(profile_path, ignore_errors=True)
        raise
    return read_profile(root, profile_id)


def read_profile(root: Path, profile_id: str) -> dict:
    """Read one profile and all three current Markdown documents."""
    profile_path = _require_profile(root, profile_id)
    manifest = _load_manifest(profile_path)
    if manifest.get("profile_id") != profile_id:
        raise StudioError("Profile manifest does not match its directory.")
    try:
        documents = {
            name: (profile_path / name).read_text(encoding="utf-8")
            for name in PROFILE_DOCUMENTS
        }
    except (OSError, UnicodeError) as exc:
        raise StudioError("Could not read the creator profile.") from exc
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


def update_profile(
    root: Path,
    profile_id: str,
    content: str,
    confirmed: bool,
    change_note: str,
) -> dict:
    """Replace ``profile.md`` after approval and snapshot all prior documents."""
    if confirmed is not True:
        raise StudioError("Profile updates require explicit confirmation.")
    _validate_text(content, "Profile content", allow_empty=True)
    _validate_text(change_note, "Change note")
    profile_path = _require_profile(root, profile_id)
    manifest = _load_manifest(profile_path)
    existing_versions = [entry["version"] for entry in manifest["versions"]]
    version = max(existing_versions, default=0) + 1
    version_name = f"v{version:03d}"
    snapshot_path = profile_path / "versions" / version_name
    try:
        snapshot_path.mkdir(exist_ok=False)
        for name in PROFILE_DOCUMENTS:
            current = (profile_path / name).read_text(encoding="utf-8")
            atomic_write_text(snapshot_path / name, current)
    except FileExistsError as exc:
        raise StudioError("The next profile version already exists.") from exc
    except (OSError, UnicodeError) as exc:
        shutil.rmtree(snapshot_path, ignore_errors=True)
        raise StudioError("Could not snapshot the creator profile.") from exc
    except Exception:
        shutil.rmtree(snapshot_path, ignore_errors=True)
        raise

    timestamp = utc_now_iso()
    atomic_write_text(profile_path / "profile.md", content)
    manifest["updated_at"] = timestamp
    manifest["versions"].append(
        {
            "change_note": change_note,
            "directory": version_name,
            "timestamp": timestamp,
            "version": version,
        }
    )
    write_json(profile_path / "versions" / "manifest.json", manifest)
    result = read_profile(root, profile_id)
    result["change_note"] = change_note
    result["timestamp"] = timestamp
    result["version"] = version
    return result


def list_profiles(root: Path) -> list[dict]:
    """List valid profiles in deterministic profile-ID order."""
    root_path = Path(root)
    if not root_path.exists():
        return []
    if not root_path.is_dir():
        raise StudioError("Profile root is not a directory.")
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


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
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
