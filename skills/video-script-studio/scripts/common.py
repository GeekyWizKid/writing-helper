"""Dependency-free persistence helpers for Video Script Studio."""

from __future__ import annotations

import json
import os
import re
import tempfile
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class StudioError(Exception):
    """A safe, user-facing error raised by studio domain operations."""


def utc_now_iso() -> str:
    """Return the current UTC time at second precision with a ``Z`` suffix."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def safe_slug(value: str) -> str:
    """Return a filesystem-safe slug containing Chinese, ASCII, digits, or hyphens."""
    if not isinstance(value, str):
        raise StudioError("The video title must be text.")
    slug = re.sub(r"[^A-Za-z0-9\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff-]+", "-", value)
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug or "untitled-video"


def atomic_write_text(path: str | os.PathLike[str], content: str) -> None:
    """Write UTF-8 text atomically using a temporary file beside the target."""
    if not isinstance(content, str):
        raise StudioError("Text content must be a string.")
    target = Path(path)
    temporary_name: str | None = None
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="",
            dir=target.parent,
            prefix=f".{target.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary_name = temporary.name
            temporary.write(content)
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temporary_name, target)
    except (OSError, UnicodeError) as exc:
        if temporary_name is not None:
            try:
                Path(temporary_name).unlink(missing_ok=True)
            except OSError:
                pass
        raise StudioError("Could not save the project file.") from exc


def read_json(path: str | os.PathLike[str]) -> dict[str, Any]:
    """Read a UTF-8 JSON object and reject malformed or non-object roots."""
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise StudioError("Could not read valid JSON data.") from exc
    if not isinstance(value, dict):
        raise StudioError("JSON data must contain an object at its root.")
    return value


def write_json(path: str | os.PathLike[str], value: Mapping[str, Any]) -> None:
    """Serialize a mapping as stable UTF-8 JSON and write it atomically."""
    if not isinstance(value, Mapping):
        raise StudioError("JSON data must be a mapping.")
    try:
        content = json.dumps(
            dict(value), ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False
        ) + "\n"
    except (TypeError, ValueError) as exc:
        raise StudioError("JSON data contains an unsupported value.") from exc
    atomic_write_text(path, content)


_PLAIN_KEY = re.compile(r"^[A-Za-z_][A-Za-z0-9_-]*$")


def _yaml_key(key: str) -> str:
    return key if _PLAIN_KEY.fullmatch(key) else json.dumps(key, ensure_ascii=False)


def _dump_mapping(value: Mapping[str, Any], indent: int) -> list[str]:
    lines: list[str] = []
    if any(not isinstance(key, str) for key in value):
        raise StudioError("State mapping keys must be strings.")
    for key in sorted(value):
        item = value[key]
        prefix = " " * indent + _yaml_key(key) + ":"
        if isinstance(item, Mapping):
            if item:
                lines.append(prefix)
                lines.extend(_dump_mapping(item, indent + 2))
            else:
                lines.append(prefix + " {}")
        elif isinstance(item, str):
            lines.append(prefix + " " + json.dumps(item, ensure_ascii=False))
        elif item is True:
            lines.append(prefix + " true")
        elif item is False:
            lines.append(prefix + " false")
        elif item is None:
            lines.append(prefix + " null")
        else:
            raise StudioError("State contains an unsupported value type.")
    return lines


def dump_state_yaml(state: Mapping[str, Any]) -> str:
    """Dump the supported deterministic YAML subset without dependencies."""
    if not isinstance(state, Mapping):
        raise StudioError("State must be a mapping.")
    lines = _dump_mapping(state, 0)
    return "\n".join(lines) + "\n" if lines else "{}\n"


def _split_yaml_entry(entry: str) -> tuple[str, str]:
    if entry.startswith('"'):
        try:
            key, end = json.JSONDecoder().raw_decode(entry)
        except json.JSONDecodeError as exc:
            raise StudioError("State YAML contains an invalid quoted key.") from exc
        if not isinstance(key, str) or not entry[end:].startswith(":"):
            raise StudioError("State YAML mapping keys must be strings.")
        return key, entry[end + 1 :].strip()
    key, separator, raw_value = entry.partition(":")
    if not separator or not _PLAIN_KEY.fullmatch(key):
        raise StudioError("State YAML contains an invalid mapping entry.")
    return key, raw_value.strip()


def _parse_yaml_scalar(raw_value: str) -> Any:
    if raw_value == "true":
        return True
    if raw_value == "false":
        return False
    if raw_value == "null":
        return None
    if raw_value == "{}":
        return {}
    if raw_value.startswith('"'):
        try:
            value = json.loads(raw_value)
        except json.JSONDecodeError as exc:
            raise StudioError("State YAML contains an invalid string.") from exc
        if isinstance(value, str):
            return value
    raise StudioError("State YAML contains an unsupported scalar value.")


def load_state_yaml(content: str) -> dict[str, Any]:
    """Load the mapping-only YAML subset emitted by :func:`dump_state_yaml`."""
    if not isinstance(content, str):
        raise StudioError("State YAML must be text.")
    if content.strip() == "{}":
        return {}
    raw_lines = content.splitlines()
    if not raw_lines or any(not line.strip() for line in raw_lines):
        raise StudioError("State YAML must be a non-empty mapping.")

    entries: list[tuple[int, str]] = []
    for line in raw_lines:
        if "\t" in line:
            raise StudioError("State YAML indentation must use spaces.")
        leading = len(line) - len(line.lstrip(" "))
        if leading % 2:
            raise StudioError("State YAML indentation must use two-space levels.")
        entries.append((leading, line[leading:]))

    def parse_mapping(index: int, expected_indent: int) -> tuple[dict[str, Any], int]:
        result: dict[str, Any] = {}
        while index < len(entries):
            indent, entry = entries[index]
            if indent < expected_indent:
                break
            if indent != expected_indent:
                raise StudioError("State YAML has an invalid nesting level.")
            key, raw_value = _split_yaml_entry(entry)
            if key in result:
                raise StudioError("State YAML contains a duplicate key.")
            index += 1
            if raw_value:
                result[key] = _parse_yaml_scalar(raw_value)
            else:
                if index >= len(entries) or entries[index][0] != expected_indent + 2:
                    raise StudioError("State YAML contains an empty nested mapping.")
                result[key], index = parse_mapping(index, expected_indent + 2)
        return result, index

    if entries[0][0] != 0:
        raise StudioError("State YAML must start with a root mapping.")
    state, final_index = parse_mapping(0, 0)
    if final_index != len(entries):
        raise StudioError("State YAML contains trailing invalid data.")
    return state
