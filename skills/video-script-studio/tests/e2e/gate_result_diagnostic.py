#!/usr/bin/env python3
"""Emit only fixed diagnostic codes for an E2E gate result contract."""

from __future__ import annotations

import json
import sys
from pathlib import Path


EXPECTED_FIELDS = {"project_path", "awaiting_gate", "artifact"}


def diagnose(
    result_path: Path,
    expected_project: Path,
    expected_gate: str,
    expected_artifact: str,
) -> list[str]:
    try:
        value = json.loads(result_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return ["gate_result_invalid_json"]
    if not isinstance(value, dict) or set(value) != EXPECTED_FIELDS:
        return ["gate_result_invalid_shape"]

    codes: list[str] = []
    project_value = value.get("project_path")
    try:
        project_matches = (
            isinstance(project_value, str)
            and Path(project_value).resolve() == expected_project.resolve()
        )
    except (OSError, RuntimeError, ValueError):
        project_matches = False
    if not project_matches:
        codes.append("gate_result_project_path_mismatch")
    if value.get("awaiting_gate") != expected_gate:
        codes.append("gate_result_awaiting_gate_mismatch")
    if value.get("artifact") != expected_artifact:
        codes.append("gate_result_artifact_mismatch")
    return codes


def main(argv: list[str]) -> int:
    if len(argv) != 5:
        print("gate_result_diagnostic_failure")
        return 0
    try:
        codes = diagnose(Path(argv[1]), Path(argv[2]), argv[3], argv[4])
    except Exception:
        codes = ["gate_result_diagnostic_failure"]
    for code in codes:
        print(code)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
