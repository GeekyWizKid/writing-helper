"""Initialize a resumable Video Script Studio project."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import date as calendar_date
from pathlib import Path
from typing import Any

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


def _validate_root(root: Path) -> Path:
    if not isinstance(root, Path):
        raise StudioError("root must be a filesystem path.")
    try:
        root.mkdir(parents=True, exist_ok=True)
        resolved = root.resolve(strict=True)
    except OSError as exc:
        raise StudioError("Could not prepare the project root.") from exc
    if not resolved.is_dir():
        raise StudioError("The project root must be a directory.")
    return resolved


def _reserve_project_directory(root: Path, base_name: str) -> Path:
    sequence = 1
    while True:
        suffix = "" if sequence == 1 else f"-{sequence:02d}"
        candidate = root / f"{base_name}{suffix}"
        if candidate.parent != root:
            raise StudioError("The project path is invalid.")
        try:
            candidate.mkdir()
            return candidate
        except FileExistsError:
            sequence += 1
        except OSError as exc:
            raise StudioError("Could not create the project directory.") from exc


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
    root = _validate_root(root)
    base_name = f"{project_date}-{safe_slug(title)}"
    state = load_state_yaml(_TEMPLATE_PATH)
    state["project"] = {
        "date": project_date,
        "platform": platform,
        "primary_type": primary_type,
        "profile_id": profile_id,
        "secondary_type": secondary_type,
        "title": title,
    }

    project = _reserve_project_directory(root, base_name)
    try:
        (project / "history").mkdir()
        for filename in REQUIRED_ARTIFACTS:
            atomic_write_text(project / filename, _artifact_content(filename))
        atomic_write_text(project / "project.yaml", dump_state_yaml(state))
    except (OSError, StudioError) as exc:
        shutil.rmtree(project, ignore_errors=True)
        if isinstance(exc, StudioError):
            raise
        raise StudioError("Could not initialize the project files.") from exc

    return {
        "path": str(project),
        "project_file": str(project / "project.yaml"),
        "status": "ok",
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
    parser.add_argument("--date")
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
            date=arguments.date,
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
