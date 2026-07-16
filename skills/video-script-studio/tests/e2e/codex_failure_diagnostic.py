"""Classify a private Codex log into a fixed, non-reflective error code."""

from __future__ import annotations

import re
import sys
from pathlib import Path


def classify(exit_code: int, text: str) -> str:
    if exit_code == 124:
        return "codex_turn_timeout"
    lowered = text.casefold()
    patterns = (
        (r"(?:invalid|unsupported).{0,120}(?:json )?schema|(?:json )?schema.{0,120}(?:invalid|unsupported)", "codex_turn_schema_error"),
        (r"structured output|response did not match|invalid json", "codex_turn_structured_output_error"),
        (r"unauthori[sz]ed|authentication failed|\b401\b", "codex_turn_auth_error"),
        (r"rate[ -]?limit|\b429\b", "codex_turn_rate_limit"),
        (r"connection (?:failed|refused|reset)|network (?:error|unreachable)|\bdns\b", "codex_turn_network_error"),
    )
    for pattern, code in patterns:
        if re.search(pattern, lowered, re.DOTALL):
            return code
    return "codex_turn_nonzero"


def main() -> int:
    if len(sys.argv) != 3:
        return 2
    try:
        exit_code = int(sys.argv[1])
        data = Path(sys.argv[2]).read_bytes()[:2_000_000]
        text = data.decode("utf-8", errors="replace")
    except (OSError, ValueError):
        print("codex_turn_diagnostic_failure")
        return 0
    print(classify(exit_code, text))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
