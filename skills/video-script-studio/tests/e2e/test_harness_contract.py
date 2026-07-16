from __future__ import annotations

import json
import subprocess
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[4]
HARNESS = REPO_ROOT / "scripts" / "verify-video-script-studio-e2e.sh"
E2E_ROOT = Path(__file__).resolve().parent


class HarnessContractTests(unittest.TestCase):
    def test_harness_has_safe_static_contract_and_preflight(self) -> None:
        self.assertTrue(HARNESS.is_file(), "Task11 E2E harness is missing")
        syntax = subprocess.run(
            ["bash", "-n", str(HARNESS)], capture_output=True, text=True, check=False
        )
        self.assertEqual(0, syntax.returncode, syntax.stderr)
        preflight = subprocess.run(
            ["bash", str(HARNESS), "--preflight"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(0, preflight.returncode, preflight.stderr)
        self.assertEqual("video-script-studio-e2e preflight ok\n", preflight.stdout)

        content = HARNESS.read_text(encoding="utf-8")
        for required in (
            "set -Eeuo pipefail",
            "umask 077",
            "CODEX_HOME",
            "XDG_CONFIG_HOME",
            "XDG_DATA_HOME",
            "XDG_CACHE_HOME",
            "TMPDIR",
            "--ephemeral",
            "--ignore-user-config",
            "--ignore-rules",
            "--sandbox",
            "workspace-write",
            'approval_policy="never"',
            "--output-schema",
            '-m 600 "$ORIGINAL_AUTH"',
            "sha256",
            "run_with_timeout",
            "assert_approved_unchanged",
            'import_module("validate_pack")',
            "state_manager.py",
            'import_module("validate_sources")',
            'import_module("estimate_duration")',
            "Skill is valid!",
            "video-script-studio-e2e ok",
        ):
            self.assertIn(required, content)
        self.assertNotIn("dangerously-bypass-approvals-and-sandbox", content)
        self.assertEqual(6, content.count("run_codex_turn "))

    def test_prompts_and_schemas_require_real_staged_completion(self) -> None:
        initial = (E2E_ROOT / "visual-essay-prompt.md").read_text(encoding="utf-8")
        for required in (
            "$video-script-studio",
            "__PROJECT_ROOT__",
            "visual-essay",
            "骑行",
            "版画",
            "只创建并展示 brief.md",
            "不得批准 brief",
            "无外部事实主张",
        ):
            self.assertIn(required, initial)
        self.assertNotIn("预先批准所有", initial)

        gate_schema = json.loads((E2E_ROOT / "gate-result.schema.json").read_text())
        final_schema = json.loads(
            (E2E_ROOT / "expected-result.schema.json").read_text()
        )
        self.assertFalse(gate_schema["additionalProperties"])
        self.assertEqual(
            {"project_path", "awaiting_gate", "artifact"},
            set(gate_schema["required"]),
        )
        self.assertFalse(final_schema["additionalProperties"])
        self.assertEqual("visual-essay", final_schema["properties"]["primary_type"]["const"])
        self.assertEqual("complete", final_schema["properties"]["stage"]["const"])
        self.assertTrue(final_schema["properties"]["validation_valid"]["const"])


if __name__ == "__main__":
    unittest.main()
