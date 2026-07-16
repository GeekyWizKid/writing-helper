#!/usr/bin/env python3
"""Estimate video duration using the timing model for each primary route.

Mixed spoken text counts every Han ideograph and every ASCII word/number token;
punctuation and whitespace count as neither. A period separates words but joins
digits in a decimal token (for example, ``Hello.World`` is two tokens and
``3.14`` is one). Commercial target matching uses a one-second tolerance by
default, configurable with ``target_tolerance_seconds``. Boundary comparisons
use a small absolute/relative epsilon to absorb representation noise.
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
TARGET_RELATIVE_EPSILON = 1e-12
TARGET_ABSOLUTE_EPSILON_SECONDS = 1e-9
PRIMARY_TYPES = {"short-form", "long-form", "narrative", "commercial", "visual-essay"}
SPOKEN_TYPES = {"short-form", "long-form"}
HAN_RANGES = (
    (0x3007, 0x3007),
    (0x3400, 0x4DBF),
    (0x4E00, 0x9FFF),
    (0xF900, 0xFAFF),
    (0x20000, 0x2A6DF),
    (0x2A700, 0x2B73F),
    (0x2B740, 0x2B81F),
    (0x2B820, 0x2CEAF),
    (0x2CEB0, 0x2EBEF),
    (0x2EBF0, 0x2EE5F),
    (0x2F800, 0x2FA1F),
    (0x30000, 0x323AF),
)
ASCII_WORD = re.compile(
    r"[0-9]+(?:\.[0-9]+)+|[A-Za-z0-9]+(?:['’\-][A-Za-z0-9]+)*"
)


def _number(value: Any, path: str, *, positive: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise StudioError(f"{path} must be a number.")
    try:
        number = float(value)
    except (OverflowError, ValueError) as exc:
        raise StudioError(f"{path} must be a finite number.") from exc
    if not math.isfinite(number):
        raise StudioError(f"{path} must be finite.")
    if positive and number <= 0:
        raise StudioError(f"{path} must be greater than zero.")
    if not positive and number < 0:
        raise StudioError(f"{path} must not be negative.")
    return number


def _finite_result(value: float, path: str) -> float:
    if not math.isfinite(value):
        raise StudioError(f"{path} must be finite.")
    return value


def _safe_sum(values: list[float], path: str) -> float:
    try:
        return _finite_result(math.fsum(values), path)
    except OverflowError as exc:
        raise StudioError(f"{path} must be finite.") from exc


def _rate_duration(value: float, rate_field: str) -> float:
    if not math.isfinite(value):
        raise StudioError(f"{rate_field} produces a non-finite duration.")
    return value


def _is_han_character(character: str) -> bool:
    codepoint = ord(character)
    return any(start <= codepoint <= end for start, end in HAN_RANGES)


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
    contributions: list[float] = []
    for index, segment in enumerate(segments):
        text = segment.get("text")
        if not isinstance(text, str):
            raise StudioError(f"segments[{index}].text must be text.")
        chinese_count = sum(_is_han_character(character) for character in text)
        english_count = len(ASCII_WORD.findall(text))
        pause = _optional_number(segment, "pause_seconds", f"segments[{index}]", 0.0)
        chinese_seconds = _rate_duration(
            chinese_count * 60.0 / chinese_rate,
            "chinese_chars_per_minute",
        )
        english_seconds = _rate_duration(
            english_count * 60.0 / english_rate,
            "english_words_per_minute",
        )
        contributions.extend((chinese_seconds, english_seconds, pause))
    return _safe_sum(contributions, "estimated_seconds")


def _declared_seconds(
    segments: list[dict[str, Any]], fields: tuple[str, ...], *, include_pause: bool = False
) -> float:
    contributions: list[float] = []
    for index, segment in enumerate(segments):
        for field in fields:
            if field not in segment:
                raise StudioError(f"segments[{index}].{field} is required.")
            contributions.append(_number(segment[field], f"segments[{index}].{field}"))
        if include_pause:
            contributions.append(
                _optional_number(segment, "pause_seconds", f"segments[{index}]", 0.0)
            )
    return _safe_sum(contributions, "estimated_seconds")


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
        lower_bound = _safe_sum([target, -tolerance], "target lower boundary")
        upper_bound = _safe_sum([target, tolerance], "target upper boundary")
        close_to_lower = math.isclose(
            seconds,
            lower_bound,
            rel_tol=TARGET_RELATIVE_EPSILON,
            abs_tol=TARGET_ABSOLUTE_EPSILON_SECONDS,
        )
        close_to_upper = math.isclose(
            seconds,
            upper_bound,
            rel_tol=TARGET_RELATIVE_EPSILON,
            abs_tol=TARGET_ABSOLUTE_EPSILON_SECONDS,
        )
        if seconds < lower_bound and not close_to_lower:
            diagnostics.append("under_target")
        elif seconds > upper_bound and not close_to_upper:
            diagnostics.append("over_target")
        else:
            diagnostics.append("within_target")

    seconds = _finite_result(seconds, "estimated_seconds")
    minutes = _finite_result(seconds / 60.0, "estimated_minutes")
    return {
        "primary_type": primary_type,
        "estimated_seconds": _stable_number(seconds),
        "estimated_minutes": _stable_number(minutes),
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
