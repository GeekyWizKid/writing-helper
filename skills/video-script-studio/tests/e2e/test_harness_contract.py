from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[4]
HARNESS = REPO_ROOT / "scripts" / "verify-video-script-studio-e2e.sh"
E2E_ROOT = Path(__file__).resolve().parent
GATE_DIAGNOSTIC = E2E_ROOT / "gate_result_diagnostic.py"
CODEX_FAILURE_DIAGNOSTIC = E2E_ROOT / "codex_failure_diagnostic.py"


class HarnessContractTests(unittest.TestCase):
    def test_codex_failure_diagnostics_never_reflect_private_log_text(self) -> None:
        self.assertTrue(CODEX_FAILURE_DIAGNOSTIC.is_file())
        cases = (
            (124, "anything", "codex_turn_timeout"),
            (1, "Invalid JSON schema for response_format SECRET", "codex_turn_schema_error"),
            (1, "structured output did not match SECRET", "codex_turn_structured_output_error"),
            (1, "401 unauthorized SECRET", "codex_turn_auth_error"),
            (1, "429 rate limit SECRET", "codex_turn_rate_limit"),
            (1, "connection reset SECRET", "codex_turn_network_error"),
            (7, "unclassified SECRET", "codex_turn_nonzero"),
        )
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "private.log"
            for exit_code, payload, expected in cases:
                with self.subTest(expected=expected):
                    log.write_text(payload, encoding="utf-8")
                    completed = subprocess.run(
                        ["python3", str(CODEX_FAILURE_DIAGNOSTIC), str(exit_code), str(log)],
                        capture_output=True, text=True, check=False,
                    )
                    self.assertEqual(0, completed.returncode, completed.stderr)
                    self.assertEqual(expected + "\n", completed.stdout)
                    self.assertNotIn("SECRET", completed.stdout + completed.stderr)

    def test_gate_result_diagnostics_are_fixed_and_field_specific(self) -> None:
        self.assertTrue(GATE_DIAGNOSTIC.is_file())
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            expected_project = root / "expected-project"
            expected_project.mkdir()
            result_path = root / "result.json"

            cases = (
                ("not json", ["gate_result_invalid_json"]),
                (json.dumps({"project_path": str(expected_project)}), ["gate_result_invalid_shape"]),
                (json.dumps({"project_path": str(root / "other"), "awaiting_gate": "research", "artifact": "research.md"}), ["gate_result_project_path_mismatch"]),
                (json.dumps({"project_path": str(expected_project), "awaiting_gate": "brief", "artifact": "research.md"}), ["gate_result_awaiting_gate_mismatch"]),
                (json.dumps({"project_path": str(expected_project), "awaiting_gate": "research", "artifact": "brief.md"}), ["gate_result_artifact_mismatch"]),
                (json.dumps({"project_path": str(expected_project), "awaiting_gate": "brief", "artifact": "brief.md"}), ["gate_result_awaiting_gate_mismatch", "gate_result_artifact_mismatch"]),
                (json.dumps({"project_path": str(expected_project), "awaiting_gate": "research", "artifact": "research.md"}), []),
            )
            for payload, expected_codes in cases:
                with self.subTest(expected_codes=expected_codes):
                    result_path.write_text(payload, encoding="utf-8")
                    completed = subprocess.run(
                        [
                            "python3", str(GATE_DIAGNOSTIC), str(result_path),
                            str(expected_project), "research", "research.md",
                        ],
                        capture_output=True, text=True, check=False,
                    )
                    self.assertEqual(0, completed.returncode, completed.stderr)
                    self.assertEqual(expected_codes, completed.stdout.splitlines())
                    self.assertNotIn(str(root), completed.stdout + completed.stderr)

    def test_harness_has_safe_static_contract_and_preflight(self) -> None:
        self.assertTrue(HARNESS.is_file(), "Task11 E2E harness is missing")
        syntax = subprocess.run(
            ["bash", "-n", str(HARNESS)], capture_output=True, text=True, check=False
        )
        self.assertEqual(0, syntax.returncode, syntax.stderr)
        with tempfile.TemporaryDirectory() as directory:
            temporary_root = Path(directory).resolve()
            home = temporary_root / "home"
            codex_home = temporary_root / "portable-codex-home"
            home.mkdir()
            environment = {**os.environ, "HOME": str(home), "CODEX_HOME": str(codex_home)}
            missing = subprocess.run(
                ["bash", str(HARNESS), "--preflight"], cwd=REPO_ROOT,
                env=environment, capture_output=True, text=True, check=False,
            )
            self.assertNotEqual(0, missing.returncode)
            self.assertIn("official validator is unavailable or unsafe", missing.stderr)

            validator = (
                codex_home / "skills" / ".system" / "skill-creator" /
                "scripts" / "quick_validate.py"
            )
            validator.parent.mkdir(parents=True)
            validator.write_text("# fake validator that performs no validation\n", encoding="utf-8")
            validator.chmod(0o600)
            fake = subprocess.run(
                ["bash", str(HARNESS), "--preflight"], cwd=REPO_ROOT,
                env=environment, capture_output=True, text=True, check=False,
            )
            self.assertNotEqual(0, fake.returncode)
            self.assertIn("official validator execution failed", fake.stderr)

            validator.write_text(
                "from pathlib import Path\n"
                "import sys\n"
                "skill = Path(sys.argv[1])\n"
                "if not (skill / 'SKILL.md').is_file():\n"
                "    raise SystemExit(1)\n"
                "print('Skill is valid!')\n",
                encoding="utf-8",
            )
            preflight = subprocess.run(
                ["bash", str(HARNESS), "--preflight"], cwd=REPO_ROOT,
                env=environment, capture_output=True, text=True, check=False,
            )
            self.assertEqual(0, preflight.returncode, preflight.stderr)
            self.assertEqual("video-script-studio-e2e preflight ok\n", preflight.stdout)

        current = subprocess.run(
            ["bash", str(HARNESS), "--preflight"], cwd=REPO_ROOT,
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(0, current.returncode, current.stderr)

        content = HARNESS.read_text(encoding="utf-8")
        self.assertIsNone(
            re.search(r"\$[A-Za-z_][A-Za-z0-9_]*[^\x00-\x7f]", content),
            "brace shell variables before adjacent non-ASCII punctuation",
        )
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
            "gate_result_diagnostic.py",
            "codex_failure_diagnostic.py",
            "codex_turn_schema_error",
            "gate_result_awaiting_gate_mismatch",
            "write_gate_schema",
            '"const": gate',
            '"const": artifact',
            "DURATION_INPUT",
            "DURATION_RESULT",
            "independent-review",
            "TURN7_PROMPT",
            'import_module("validate_pack")',
            "state_manager.py",
            'import_module("validate_sources")',
            'import_module("estimate_duration")',
            "Skill is valid!",
            "execute_official_validator",
            "official validator execution failed",
            "video-script-studio-e2e ok",
        ):
            self.assertIn(required, content)
        self.assertNotIn("dangerously-bypass-approvals-and-sandbox", content)
        self.assertNotIn("redacted_log_tail", content)
        self.assertNotIn("VIDEO_SCRIPT_STUDIO_OFFICIAL_VALIDATOR", content)
        self.assertIn("private log withheld", content)
        self.assertEqual(7, content.count("run_codex_turn "))
        self.assertEqual(5, content.count("write_gate_schema \"$TURN"))
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
        self.assertNotIn("/Users/apulu", content)
        self.assertIn(
            'OFFICIAL_VALIDATOR="$ORIGINAL_CODEX_HOME/skills/.system/skill-creator/scripts/quick_validate.py"',
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
