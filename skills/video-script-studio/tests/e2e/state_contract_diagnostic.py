"""Emit fixed state/pack contract codes without reflecting project data."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path


STAGES = {"brief", "research", "concept", "outline", "script"}


def main() -> int:
    if len(sys.argv) not in {4, 5}:
        return 2
    try:
        status = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
        expected_stage = sys.argv[2]
        approved = set(filter(None, sys.argv[3].split(",")))
        expected_approvals = {
            name: ("approved" if name in approved else "pending") for name in STAGES
        }
        codes: list[str] = []
        if status.get("stage") != expected_stage:
            codes.append("state_stage_mismatch")
        if status.get("approvals") != expected_approvals:
            codes.append("state_approval_map_mismatch")
        if len(sys.argv) == 5:
            pack = json.loads(Path(sys.argv[4]).read_text(encoding="utf-8"))
            if pack.get("valid") is not True:
                raw_codes = pack.get("error_codes", [])
                if not isinstance(raw_codes, list):
                    codes.append("pack_diagnostic_invalid")
                else:
                    for code in raw_codes[:50]:
                        if isinstance(code, str) and re.fullmatch(r"[a-z0-9_]+", code):
                            codes.append(f"pack_error_{code}")
                        else:
                            codes.append("pack_diagnostic_invalid")
                            break
    except (OSError, ValueError, TypeError):
        codes = ["state_contract_diagnostic_failure"]
    print("\n".join(dict.fromkeys(codes)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
