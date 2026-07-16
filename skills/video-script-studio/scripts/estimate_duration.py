#!/usr/bin/env python3
"""Estimate video duration using the timing model for each primary route.

Mixed spoken text counts every Han character and every ASCII word/number token;
punctuation and whitespace count as neither. Commercial target matching uses a
one-second tolerance by default, configurable with ``target_tolerance_seconds``.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from pathlib import Path
from typing import Any


SCRIPT_DIRECTORY = Path(__file__).resolve().parent
if str(SCRIPT_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIRECTORY))

from common import StudioError, read_json  # noqa: E402


DEFAULT_CHINESE_CHARS_PER_MINUTE = 240.0
DEFAULT_ENGLISH_WORDS_PER_MINUTE = 150.0
DEFAULT_TARGET_TOLERANCE_SECONDS = 1.0
PRIMARY_TYPES = {"short-form", "long-form", "narrative", "commercial", "visual-essay"}
SPOKEN_TYPES = {"short-form", "long-form"}
HAN_CHARACTER = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
ASCII_WORD = re.compile(r"[A-Za-z0-9]+(?:[.'’-][A-Za-z0-9]+)*")


def _number(value: Any, path: str, *, positive: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise StudioError(f"{path} must be a number.")
    number = float(value)
    if not math.isfinite(number):
        raise StudioError(f"{path} must be finite.")
    if positive and number <= 0:
        raise StudioError(f"{path} must be greater than zero.")
    if not positive and number < 0:
        raise StudioError(f"{path} must not be negative.")
    return number


def _optional_number(
    mapping: dict[str, Any], field: str, path: str, default: float, *, positive: bool = False
) -> float:
    if field not in mapping:
        return default
    return _number(mapping[field], f"{path}.{field}" if path else field, positive=positive)


def _segments(payload: dict[str, Any]) -> list[dict[str, Any]]:
    if "segments" not in payload or not isinstance(payload["segments"], list):
        raise StudioError("segments must be a list.")
    segments: list[dict[str, Any]] = []
    for index, segment in enumerate(payload["segments"]):
        if not isinstance(segment, dict):
            raise StudioError(f"segments[{index}] must be an object.")
        segments.append(segment)
    return segments


def _spoken_seconds(
    segments: list[dict[str, Any]], chinese_rate: float, english_rate: float
) -> float:
    total = 0.0
    for index, segment in enumerate(segments):
        text = segment.get("text")
        if not isinstance(text, str):
            raise StudioError(f"segments[{index}].text must be text.")
        chinese_count = len(HAN_CHARACTER.findall(text))
        english_count = len(ASCII_WORD.findall(text))
        pause = _optional_number(segment, "pause_seconds", f"segments[{index}]", 0.0)
        total += chinese_count * 60.0 / chinese_rate
        total += english_count * 60.0 / english_rate
        total += pause
    return total


def _declared_seconds(
    segments: list[dict[str, Any]], fields: tuple[str, ...], *, include_pause: bool = False
) -> float:
    total = 0.0
    for index, segment in enumerate(segments):
        for field in fields:
            if field not in segment:
                raise StudioError(f"segments[{index}].{field} is required.")
            total += _number(segment[field], f"segments[{index}].{field}")
        if include_pause:
            total += _optional_number(segment, "pause_seconds", f"segments[{index}]", 0.0)
    return total


def _stable_number(value: float) -> int | float:
    return int(value) if value.is_integer() else value


def estimate(payload: dict[str, Any]) -> dict[str, Any]:
    """Return a stable duration estimate or raise a field-specific ``StudioError``."""
    if not isinstance(payload, dict):
        raise StudioError("payload must be an object.")
    primary_type = payload.get("primary_type")
    if not isinstance(primary_type, str) or primary_type not in PRIMARY_TYPES:
        raise StudioError("primary_type must be a supported video type.")
    segments = _segments(payload)
    diagnostics: list[str] = []

    if primary_type in SPOKEN_TYPES:
        chinese_rate = _optional_number(
            payload, "chinese_chars_per_minute", "", DEFAULT_CHINESE_CHARS_PER_MINUTE,
            positive=True,
        )
        english_rate = _optional_number(
            payload, "english_words_per_minute", "", DEFAULT_ENGLISH_WORDS_PER_MINUTE,
            positive=True,
        )
        seconds = _spoken_seconds(segments, chinese_rate, english_rate)
    elif primary_type == "narrative":
        seconds = _declared_seconds(
            segments,
            ("dialogue_seconds", "action_seconds", "response_seconds"),
            include_pause=True,
        )
    elif primary_type == "visual-essay":
        seconds = _declared_seconds(segments, ("duration_seconds",))
    else:
        duration_method = payload.get("duration_method")
        if duration_method == "spoken":
            chinese_rate = _optional_number(
                payload, "chinese_chars_per_minute", "", DEFAULT_CHINESE_CHARS_PER_MINUTE,
                positive=True,
            )
            english_rate = _optional_number(
                payload, "english_words_per_minute", "", DEFAULT_ENGLISH_WORDS_PER_MINUTE,
                positive=True,
            )
            seconds = _spoken_seconds(segments, chinese_rate, english_rate)
        elif duration_method == "declared":
            seconds = _declared_seconds(segments, ("duration_seconds",))
        else:
            raise StudioError("duration_method must be 'spoken' or 'declared' for commercial.")

        if "target_seconds" not in payload:
            raise StudioError("target_seconds is required for commercial.")
        target = _number(payload["target_seconds"], "target_seconds")
        tolerance = _optional_number(
            payload,
            "target_tolerance_seconds",
            "",
            DEFAULT_TARGET_TOLERANCE_SECONDS,
        )
        if seconds < target - tolerance:
            diagnostics.append("under_target")
        elif seconds > target + tolerance:
            diagnostics.append("over_target")
        else:
            diagnostics.append("within_target")

    return {
        "primary_type": primary_type,
        "estimated_seconds": _stable_number(seconds),
        "estimated_minutes": _stable_number(seconds / 60.0),
        "diagnostics": diagnostics,
        "segment_count": len(segments),
    }


def _emit_json(value: dict[str, Any]) -> None:
    print(json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, help="Path to a JSON duration payload")
    args = parser.parse_args(argv)
    try:
        _emit_json(estimate(read_json(args.input)))
    except StudioError as exc:
        _emit_json({"error": str(exc)})
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
