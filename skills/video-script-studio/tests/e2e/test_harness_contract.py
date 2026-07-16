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
            "snapshot_project",
            "assert_only_paths_changed",
            "assert_matches_initializer_baseline",
            "assert_exact_approvals",
            "assert_approved_unchanged",
            "DURATION_INPUT",
            "DURATION_RESULT",
            "independent-review",
            "TURN7_PROMPT",
            'import_module("validate_pack")',
            "state_manager.py",
            'import_module("validate_sources")',
            'import_module("estimate_duration")',
            "Skill is valid!",
            "video-script-studio-e2e ok",
        ):
            self.assertIn(required, content)
        self.assertNotIn("dangerously-bypass-approvals-and-sandbox", content)
        self.assertNotIn("redacted_log_tail", content)
        self.assertNotIn("VIDEO_SCRIPT_STUDIO_OFFICIAL_VALIDATOR", content)
        self.assertIn("private log withheld", content)
        self.assertEqual(7, content.count("run_codex_turn "))
        self.assertEqual(
            7, content.count('assert_matches_initializer_baseline "$PROJECT"')
        )
        self.assertEqual(6, content.count('assert_only_paths_changed "$SNAPSHOT'))
        self.assertEqual(7, content.count('assert_exact_approvals "$PROJECT"'))
        self.assertIn("from init_project import init_project", content)
        for allowlist in (
            "project.yaml research.md sources.md",
            "project.yaml concepts.md",
            "project.yaml outline.md",
            "project.yaml script.md",
            "project.yaml storyboard.md assets.md publish.md",
            "project.yaml review.md",
        ):
            self.assertIn(allowlist, content)
        self.assertLess(
            content.index("official-validator.log"),
            content.index('-m 600 "$ORIGINAL_AUTH"'),
        )
        self.assertLess(
            content.index("official-validator.log"),
            content.index("# Authentication is deliberately untouched"),
        )
        self.assertIn(
            'OFFICIAL_VALIDATOR="/Users/apulu/.codex/skills/.system/skill-creator/scripts/quick_validate.py"',
            content,
        )

    def test_harness_enforces_semantics_and_independent_review(self) -> None:
        content = HARNESS.read_text(encoding="utf-8")
        for required in (
            "brief.md",
            "方案 A",
            "方案 B",
            "方案 C",
            "体验节点",
            "可见试做",
            "失败",
            "环境声",
            "review.md",
            "第七会话",
            '"estimated_seconds": 90',
            '"segment_count": 5',
        ):
            self.assertIn(required, content)
        self.assertTrue((E2E_ROOT / "review-result.schema.json").is_file())

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
