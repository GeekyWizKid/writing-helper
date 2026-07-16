from __future__ import annotations

import json
import hashlib
import re
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest import mock

from helpers import load_script_module


FIXTURE_DIRECTORY = Path(__file__).with_name("fixtures")
ROUTES = ("short-form", "long-form", "narrative", "commercial", "visual-essay")
COMMON_SCRIPT_HEADINGS = (
    "最终命题",
    "目标",
    "预计时长",
    "干净表演稿",
    "制作执行稿",
    "待人工确认事项",
    "可删段落",
    "短版本切点",
)


def load_fixture(route: str) -> dict:
    return json.loads((FIXTURE_DIRECTORY / f"{route}.json").read_text(encoding="utf-8"))


class ScenarioFixtureContractTests(unittest.TestCase):
    def test_all_five_route_fixtures_exist(self) -> None:
        missing = [
            route
            for route in ROUTES
            if not (FIXTURE_DIRECTORY / f"{route}.json").is_file()
        ]
        self.assertEqual([], missing, f"missing scenario fixtures: {missing}")

    def test_fixtures_define_the_complete_scenario_contract(self) -> None:
        required = {
            "intent",
            "expected_primary_route",
            "expected_secondary_type",
            "research_disposition",
            "artifact_headings",
            "artifact_bodies",
            "duration_payload",
            "expected_duration",
            "review_weights",
            "forbidden_failure_pattern",
            "negative_mutation",
        }
        for route in ROUTES:
            with self.subTest(route=route):
                fixture = load_fixture(route)
                self.assertEqual(required, set(fixture) - ({"creative_contract"} if route == "visual-essay" else set()))
                self.assertEqual(route, fixture["expected_primary_route"])
                self.assertEqual(route, fixture["duration_payload"]["primary_type"])
                self.assertTrue(fixture["intent"].strip())
                self.assertTrue(fixture["expected_secondary_type"].strip())
                self.assertIs(type(fixture["research_disposition"]["required"]), bool)
                self.assertTrue(fixture["research_disposition"]["reason"].strip())
                self.assertEqual(100, sum(fixture["review_weights"].values()))
                self.assertTrue(fixture["forbidden_failure_pattern"].strip())
                self.assertEqual(set(fixture["artifact_headings"]), set(fixture["artifact_bodies"]))
                self.assertIn(fixture["negative_mutation"]["file"], fixture["artifact_headings"])
                self.assertIn(
                    fixture["negative_mutation"]["heading"],
                    fixture["artifact_headings"][fixture["negative_mutation"]["file"]],
                )
                for filename, heading_bodies in fixture["artifact_bodies"].items():
                    self.assertEqual(
                        set(fixture["artifact_headings"][filename]),
                        set(heading_bodies),
                    )
                    self.assertTrue(all(body.strip() for body in heading_bodies.values()))

        self.assertTrue(load_fixture("short-form")["research_disposition"]["required"])

    def test_visual_essay_fixture_is_original_and_action_led(self) -> None:
        fixture = load_fixture("visual-essay")
        contract = fixture["creative_contract"]
        self.assertEqual(
            {
                "original_premise",
                "visible_trial",
                "visible_failure",
                "visual_motif",
                "environment_sound",
                "voiceover_policy",
                "thematic_recovery",
            },
            set(contract),
        )
        self.assertIn("两项个人兴趣", fixture["intent"])
        self.assertIn("骑行", fixture["intent"])
        self.assertIn("版画", fixture["intent"])
        self.assertIn("稀疏旁白", contract["voiceover_policy"])


class ScenarioIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.initializer = load_script_module("init_project")
        cls.state = load_script_module("state_manager")
        cls.profile = load_script_module("profile_manager")
        cls.duration = load_script_module("estimate_duration")
        cls.sources = load_script_module("validate_sources")
        cls.pack = load_script_module("validate_pack")

    def initialize(self, root: Path, fixture: dict) -> Path:
        result = self.initializer.init_project(
            root,
            f"Scenario {fixture['expected_primary_route']}",
            fixture["expected_primary_route"],
            secondary_type=fixture["expected_secondary_type"],
            date="2026-07-17",
        )
        project = Path(result["path"])
        state = self.state.load_state(project)
        required = fixture["research_disposition"]["required"]
        state["research"]["disposition"] = "required" if required else "not-required"
        state["sources"]["disposition"] = "captured" if required else "not-required"
        self.state.save_state(project, state)
        return project

    def manifest_for(self, fixture: dict) -> tuple[dict, str]:
        disposition = fixture["research_disposition"]
        if not disposition["required"]:
            return (
                {
                    "schema_version": 1,
                    "research_required": False,
                    "decision_reason": disposition["reason"],
                    "sources": [],
                    "claims": [],
                },
                "",
            )
        return (
            {
                "schema_version": 1,
                "research_required": True,
                "decision_reason": disposition["reason"],
                "sources": [
                    {
                        "id": "S01",
                        "title": "完整的一手来源",
                        "provenance": {"url": "https://example.com/source"},
                        "level": "primary",
                        "capture_status": "complete",
                        "body_status": "full-text",
                        "accessed_at": "2026-07-17",
                    }
                ],
                "claims": [
                    {
                        "claim_id": "C01",
                        "text": "示例事实已由完整来源支持。",
                        "claim_type": "factual",
                        "source_ids": ["S01"],
                        "confidence": "high",
                    }
                ],
            },
            "[C01]",
        )

    def write_valid_pack(self, project: Path, fixture: dict, manifest: dict, marker: str) -> None:
        artifacts = {
            "brief.md": "# Brief\n\n已确认的完整简报。\n",
            "research.md": "# Research\n\n已记录事实边界与调研结论。\n",
            "concepts.md": "# Concepts\n\n三个概念及选择理由已经确认。\n",
            "outline.md": "# Outline\n\n体验节点与结构已经确认。\n",
            "storyboard.md": "# Storyboard\n\n逐镜头执行方案完整。\n",
            "assets.md": "# Assets\n\n素材来源、规格与替代方案完整。\n",
            "publish.md": "# Publish\n\n发布文案与人工动作边界完整。\n",
        }
        for filename, headings in fixture["artifact_headings"].items():
            if filename in artifacts:
                artifacts[filename] += "".join(
                    f"\n## {heading}\n{fixture['artifact_bodies'][filename][heading]}\n"
                    for heading in headings
                )
        for filename, content in artifacts.items():
            (project / filename).write_text(content, encoding="utf-8")

        script_sections = []
        for heading in COMMON_SCRIPT_HEADINGS:
            suffix = f" {marker}" if heading == "制作执行稿" and marker else ""
            script_sections.append(f"## {heading}\n{heading}具有完整可执行内容。{suffix}")
        script = "# Script\n\n" + "\n\n".join(script_sections) + "\n"
        for heading in fixture["artifact_headings"].get("script.md", []):
            script += f"\n## {heading}\n{fixture['artifact_bodies']['script.md'][heading]}\n"
        (project / "script.md").write_text(script, encoding="utf-8")

        sources_text = "---\n" + json.dumps(manifest, ensure_ascii=False) + "\n---\n\n# Sources\n\n来源决策完整。\n"
        (project / "sources.md").write_text(sources_text, encoding="utf-8")
        review = {
            "schema_version": 1,
            "passed": True,
            "total_score": 80,
            "core_dimensions": {
                name: {"score": 8, "weight": weight}
                for name, weight in fixture["review_weights"].items()
            },
            "base_gates": {name: True for name in self.pack.BASE_GATES},
            "revision_count": 0,
        }
        review_text = "---\n" + json.dumps(review, ensure_ascii=False) + "\n---\n\n# Review\n\n独立评审已通过。\n"
        for heading in fixture["artifact_headings"].get("review.md", []):
            review_text += f"\n## {heading}\n{fixture['artifact_bodies']['review.md'][heading]}\n"
        (project / "review.md").write_text(review_text, encoding="utf-8")

    def approve_all(self, project: Path) -> None:
        for stage in self.state.STAGES:
            self.state.approve(project, stage)

    def test_each_route_executes_real_end_to_end_project_code(self) -> None:
        for route in ROUTES:
            with self.subTest(route=route), tempfile.TemporaryDirectory() as directory:
                fixture = load_fixture(route)
                project = self.initialize(Path(directory), fixture)
                project_state = self.state.load_state(project)
                self.assertEqual(route, project_state["project"]["primary_type"])
                self.assertEqual(fixture["expected_secondary_type"], project_state["project"]["secondary_type"])

                manifest, marker = self.manifest_for(fixture)
                duration_result = self.duration.estimate(fixture["duration_payload"])
                for field, expected in fixture["expected_duration"].items():
                    self.assertEqual(expected, duration_result[field])

                self.write_valid_pack(project, fixture, manifest, marker)
                actual_script = (project / "script.md").read_text(encoding="utf-8")
                source_result = self.sources.validate(manifest, actual_script)
                self.assertTrue(source_result["valid"], source_result)
                self.assertEqual(int(fixture["research_disposition"]["required"]), source_result["claim_count"])
                self.assertEqual(
                    fixture["research_disposition"]["required"],
                    project_state["research"]["disposition"] == "required",
                )
                self.approve_all(project)
                self.assertEqual(fixture["review_weights"], self.pack.ROUTE_WEIGHTS[route])
                for filename, headings in fixture["artifact_headings"].items():
                    content = (project / filename).read_text(encoding="utf-8")
                    for heading in headings:
                        self.assertIn(f"## {heading}", content)
                        self.assertIn(fixture["artifact_bodies"][filename][heading], content)
                authored_content = "\n".join(
                    body
                    for heading_bodies in fixture["artifact_bodies"].values()
                    for body in heading_bodies.values()
                )
                self.assertNotIn(fixture["forbidden_failure_pattern"], authored_content)
                all_content = "\n".join(
                    path.read_text(encoding="utf-8")
                    for path in project.glob("*.md")
                )
                self.assertNotIn(fixture["forbidden_failure_pattern"], all_content)

                validation = self.pack.validate_pack(project)
                self.assertTrue(validation["valid"], validation)
                self.assertEqual(11, validation["checked_file_count"])
                completion = self.state.complete(project)
                self.assertEqual("completed", completion["status"])
                self.assertEqual("complete", self.state.status(project)["stage"])
                completed_state = self.state.load_state(project)
                self.assertRegex(completed_state["completion_digest"], r"^[0-9a-f]{64}$")
                self.assertTrue(self.pack.validate_pack(project)["valid"])

                if route == "visual-essay":
                    visual_text = (project / "storyboard.md").read_text(encoding="utf-8") + (project / "script.md").read_text(encoding="utf-8")
                    for semantic_token in ("骑行", "版画", "试做", "失败", "裂痕", "车轮空转", "稀疏旁白", "最终作品"):
                        self.assertIn(semantic_token, visual_text)

    def test_each_route_rejects_a_controlled_missing_anchor_mutation(self) -> None:
        for route in ROUTES:
            with self.subTest(route=route), tempfile.TemporaryDirectory() as directory:
                fixture = load_fixture(route)
                project = self.initialize(Path(directory), fixture)
                manifest, marker = self.manifest_for(fixture)
                self.write_valid_pack(project, fixture, manifest, marker)
                self.approve_all(project)
                self.assertTrue(self.pack.validate_pack(project)["valid"])

                mutation = fixture["negative_mutation"]
                path = project / mutation["file"]
                content = path.read_text(encoding="utf-8")
                content = re.sub(
                    rf"(?ms)^## {re.escape(mutation['heading'])}\s*$\n.*?(?=^## |\Z)",
                    "",
                    content,
                )
                path.write_text(content, encoding="utf-8")
                result = self.pack.validate_pack(project)
                self.assertFalse(result["valid"])
                self.assertIn(mutation["expected_error"], result["error_codes"])

    def test_skipped_approval_blocks_pack_and_completion(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture = load_fixture("short-form")
            project = self.initialize(Path(directory), fixture)
            manifest, marker = self.manifest_for(fixture)
            self.write_valid_pack(project, fixture, manifest, marker)
            initial_state = (project / "project.yaml").read_bytes()
            initial_history = tuple((project / "history").iterdir())
            with self.assertRaises(self.state.StudioError):
                self.state.approve(project, "research")
            self.assertEqual(initial_state, (project / "project.yaml").read_bytes())
            self.assertEqual(initial_history, tuple((project / "history").iterdir()))

            for stage in self.state.STAGES[:-1]:
                self.state.approve(project, stage)

            state_before = (project / "project.yaml").read_bytes()
            history_before = tuple((project / "history").iterdir())
            validation = self.pack.validate_pack(project)
            self.assertIn("script_not_approved", validation["error_codes"])
            completion = self.state.complete(project)
            self.assertEqual("blocked", completion["status"])
            self.assertEqual("script_pending", completion["stage"])
            self.assertEqual(state_before, (project / "project.yaml").read_bytes())
            self.assertEqual(history_before, tuple((project / "history").iterdir()))

    def test_unavailable_research_cannot_support_a_factual_claim(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture = load_fixture("long-form")
            project = self.initialize(Path(directory), fixture)
            manifest = {
                "schema_version": 1,
                "research_required": True,
                "decision_reason": "事实必须取得全文后才能进入脚本。",
                "sources": [],
                "claims": [{"claim_id": "C01", "text": "尚未取得支持的事实。", "claim_type": "factual", "source_ids": [], "confidence": "low"}],
            }
            original = deepcopy(manifest)
            self.write_valid_pack(project, fixture, manifest, "[C01]")
            (project / "research.md").write_text("# Research\n\n外部研究不可用；没有来源或替代事实。\n", encoding="utf-8")
            self.state.approve(project, "brief")
            actual_script = (project / "script.md").read_text(encoding="utf-8")
            result = self.sources.validate(manifest, actual_script)
            self.assertFalse(result["valid"])
            self.assertIn("incomplete_claim_support", result["error_codes"])
            self.assertEqual(result, self.sources.validate(manifest, actual_script))
            self.assertEqual(original, manifest)
            self.assertEqual(0, result["source_count"])
            self.assertEqual("research_pending", self.state.status(project)["stage"])
            pack_result = self.pack.validate_pack(project)
            self.assertIn("incomplete_claim_support", pack_result["error_codes"])
            self.assertEqual("blocked", self.state.complete(project)["status"])
            self.assertNotIn("https://", (project / "sources.md").read_text(encoding="utf-8"))

    def test_conflicting_sources_do_not_bypass_the_research_gate(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture = load_fixture("long-form")
            project = self.initialize(Path(directory), fixture)
            manifest = {
                "schema_version": 1,
                "research_required": True,
                "decision_reason": "两份完整来源结论冲突，必须人工调和。",
                "sources": [
                    {"id": "S01", "title": "来源甲", "provenance": {"url": "https://example.com/a"}, "level": "primary", "capture_status": "complete", "body_status": "full-text", "accessed_at": "2026-07-17"},
                    {"id": "S02", "title": "来源乙", "provenance": {"url": "https://example.com/b"}, "level": "primary", "capture_status": "complete", "body_status": "full-text", "accessed_at": "2026-07-17"},
                ],
                "claims": [
                    {"claim_id": "C01", "text": "结论为正。", "claim_type": "factual", "source_ids": ["S01"], "confidence": "medium"},
                    {"claim_id": "C02", "text": "结论为负。", "claim_type": "factual", "source_ids": ["S02"], "confidence": "medium"},
                ],
            }
            wording = manifest["decision_reason"]
            self.assertLessEqual(len(wording), 200)
            self.assertIn("冲突", wording)
            self.assertNotIn("自动选择", wording)
            self.write_valid_pack(project, fixture, manifest, "[C01] [C02]")
            research_text = (
                "# Research\n\n## 冲突来源\nS01 支持正向结论；S02 支持反向结论。"
                "当前证据不足以单方面判断，保留有边界的不确定性，不作单边结论。\n"
            )
            (project / "research.md").write_text(research_text, encoding="utf-8")
            actual_script = (project / "script.md").read_text(encoding="utf-8")
            self.assertTrue(self.sources.validate(manifest, actual_script)["valid"])
            self.assertIn("S01", (project / "sources.md").read_text(encoding="utf-8"))
            self.assertIn("S02", (project / "sources.md").read_text(encoding="utf-8"))
            self.assertIn("不确定性", research_text)
            self.assertNotIn("因此选择", research_text)
            self.state.approve(project, "brief")
            status = self.state.status(project)
            self.assertEqual("research_pending", status["stage"])
            self.assertEqual("pending", status["approvals"]["research"])
            pack_result = self.pack.validate_pack(project)
            self.assertIn("research_not_approved", pack_result["error_codes"])
            self.assertEqual("blocked", self.state.complete(project)["status"])

    def test_missing_transcript_is_incomplete_factual_support(self) -> None:
        manifest = {
            "schema_version": 1,
            "research_required": True,
            "decision_reason": "视频主张需要字幕或转录全文。",
            "sources": [{
                "id": "S01",
                "title": "只有视频链接，没有字幕",
                "provenance": {"url": "https://example.com/video"},
                "level": "primary",
                "capture_status": "unavailable",
                "body_status": "unavailable",
                "accessed_at": "2026-07-17",
            }],
            "claims": [{
                "claim_id": "C01",
                "text": "视频中的具体说法。",
                "claim_type": "factual",
                "source_ids": ["S01"],
                "confidence": "low",
            }],
        }
        with tempfile.TemporaryDirectory() as directory:
            fixture = load_fixture("short-form")
            project = self.initialize(Path(directory), fixture)
            original = deepcopy(manifest)
            self.write_valid_pack(project, fixture, manifest, "[C01]")
            transcript_notice = "# Research\n\n字幕或转录全文缺失；不得根据标题重构视频说法。\n"
            (project / "research.md").write_text(transcript_notice, encoding="utf-8")
            self.state.approve(project, "brief")
            actual_script = (project / "script.md").read_text(encoding="utf-8")
            result = self.sources.validate(manifest, actual_script)
            self.assertFalse(result["valid"])
            self.assertIn("incomplete_claim_support", result["error_codes"])
            self.assertEqual(result, self.sources.validate(manifest, actual_script))
            self.assertEqual(original, manifest)
            self.assertEqual(1, result["source_count"])
            self.assertEqual("research_pending", self.state.status(project)["stage"])
            self.assertIn("incomplete_claim_support", self.pack.validate_pack(project)["error_codes"])
            self.assertEqual("blocked", self.state.complete(project)["status"])
            self.assertIn('"capture_status": "unavailable"', (project / "sources.md").read_text(encoding="utf-8"))
            self.assertNotIn("转录内容如下", transcript_notice)

    def test_changed_concept_preserves_history_and_invalidates_downstream(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture = load_fixture("narrative")
            project = self.initialize(Path(directory), fixture)
            manifest, marker = self.manifest_for(fixture)
            self.write_valid_pack(project, fixture, manifest, marker)
            self.approve_all(project)

            brief_before = (project / "brief.md").read_bytes()
            research_before = (project / "research.md").read_bytes()
            downstream_before = {
                name: (project / name).read_bytes()
                for name in ("concepts.md", "outline.md", "script.md")
            }
            upstream_hashes = {
                "brief.md": hashlib.sha256(brief_before).hexdigest(),
                "research.md": hashlib.sha256(research_before).hexdigest(),
            }

            result = self.state.reopen(project, "concept", "用户选择了不同概念")
            self.assertEqual("concept_pending", result["stage"])
            status = self.state.status(project)
            self.assertEqual("pending", status["approvals"]["concept"])
            self.assertEqual("approved", status["approvals"]["brief"])
            self.assertEqual("approved", status["approvals"]["research"])
            self.assertEqual("invalidated", status["approvals"]["outline"])
            self.assertEqual("invalidated", status["approvals"]["script"])
            history = Path(result["history_path"])
            self.assertTrue((history / "concepts.md").is_file())
            self.assertTrue((history / "outline.md").is_file())
            self.assertTrue((history / "script.md").is_file())
            self.assertFalse((history / "brief.md").exists())
            self.assertFalse((history / "research.md").exists())
            self.assertEqual(brief_before, (project / "brief.md").read_bytes())
            self.assertEqual(research_before, (project / "research.md").read_bytes())
            self.assertEqual(upstream_hashes["brief.md"], hashlib.sha256((project / "brief.md").read_bytes()).hexdigest())
            self.assertEqual(upstream_hashes["research.md"], hashlib.sha256((project / "research.md").read_bytes()).hexdigest())
            for name, old_bytes in downstream_before.items():
                self.assertEqual(old_bytes, (history / name).read_bytes())
            manifest_data = json.loads((history / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(
                ["concepts.md", "outline.md", "script.md"],
                manifest_data["affected_artifacts"],
            )
            (project / "concepts.md").write_text("# Concepts\n\n改选概念：由自保转为主动承担。\n", encoding="utf-8")
            (project / "outline.md").write_text(
                "# Outline\n\n## 阻力\n新概念让违规备份在中段曝光，选择代价可见。\n",
                encoding="utf-8",
            )
            script_text = (project / "script.md").read_text(encoding="utf-8")
            (project / "script.md").write_text(script_text + "\n改写结局：她主动递交记录。\n", encoding="utf-8")
            for name, old_bytes in downstream_before.items():
                self.assertNotEqual(old_bytes, (project / name).read_bytes())
            for stage in ("concept", "outline", "script"):
                self.state.approve(project, stage)
            self.assertTrue(self.pack.validate_pack(project)["valid"])
            self.assertEqual("completed", self.state.complete(project)["status"])

    def test_two_creator_profiles_remain_isolated(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "profiles"
            self.profile.create_profile(root, "alice", "Alice")
            self.profile.create_profile(root, "bob", "Bob")
            self.profile.update_profile(root, "alice", "# Alice\n\n只用克制旁白。\n", True, "确认 Alice 风格")
            self.profile.update_profile(root, "bob", "# Bob\n\n强调快速口播。\n", True, "确认 Bob 风格")

            def tree_bytes(profile_id: str) -> dict[str, bytes]:
                base = root / profile_id
                return {
                    str(path.relative_to(base)): path.read_bytes()
                    for path in sorted(base.rglob("*"))
                    if path.is_file()
                }

            alice = self.profile.read_profile(root, "alice")
            bob = self.profile.read_profile(root, "bob")
            self.assertIn("克制旁白", alice["content"])
            self.assertNotIn("快速口播", alice["content"])
            self.assertIn("快速口播", bob["content"])
            self.assertNotIn("克制旁白", bob["content"])
            self.assertEqual(["alice", "bob"], [item["profile_id"] for item in self.profile.list_profiles(root)])
            alice_before = tree_bytes("alice")
            bob_before = tree_bytes("bob")
            with self.assertRaises(self.profile.StudioError):
                self.profile.update_profile(root, "alice", "不应写入", False, "未确认")
            self.assertEqual(alice_before, tree_bytes("alice"))
            self.assertEqual(bob_before, tree_bytes("bob"))
            self.assertEqual(1, alice["version_count"])
            self.assertEqual(1, bob["version_count"])

            alice_project = self.initializer.init_project(
                Path(directory) / "alice-projects", "Alice Project", "short-form", profile_id="alice", date="2026-07-17"
            )
            bob_project = self.initializer.init_project(
                Path(directory) / "bob-projects", "Bob Project", "short-form", profile_id="bob", date="2026-07-17"
            )
            self.assertEqual("alice", self.state.load_state(Path(alice_project["path"]))["project"]["profile_id"])
            self.assertEqual("bob", self.state.load_state(Path(bob_project["path"]))["project"]["profile_id"])

    def test_interrupted_reopen_recovers_at_published_and_committed_boundaries(self) -> None:
        for boundary in ("snapshot-published", "state-committed"):
            with self.subTest(boundary=boundary), tempfile.TemporaryDirectory() as directory:
                fixture = load_fixture("visual-essay")
                project = self.initialize(Path(directory), fixture)
                manifest, marker = self.manifest_for(fixture)
                self.write_valid_pack(project, fixture, manifest, marker)
                self.approve_all(project)

                def interrupt(name: str) -> None:
                    if name == boundary:
                        raise KeyboardInterrupt(name)

                with mock.patch.object(self.state, "_transaction_boundary", side_effect=interrupt):
                    with self.assertRaises(KeyboardInterrupt):
                        self.state.reopen(project, "concept", "中断恢复测试")

                resumed_state = load_script_module("state_manager")
                status = resumed_state.status(project)
                self.assertFalse((project / self.state.JOURNAL_NAME).exists())
                history_entries = list((project / "history").iterdir())
                self.assertFalse(any(path.name.startswith(".reopen-txn-") for path in history_entries))
                public_history = [path for path in history_entries if not path.name.startswith(".")]
                if boundary == "snapshot-published":
                    self.assertEqual("script_approved", status["stage"])
                    self.assertEqual([], public_history)
                    resumed_state.reopen(project, "concept", "恢复后重试")
                    status = resumed_state.status(project)
                    public_history = [
                        path for path in (project / "history").iterdir()
                        if not path.name.startswith(".")
                    ]
                else:
                    self.assertEqual(1, len(public_history))
                self.assertEqual("concept_pending", status["stage"])
                self.assertEqual(1, len(public_history))
                self.assertTrue((public_history[0] / "manifest.json").is_file())
                for stage in ("concept", "outline", "script"):
                    resumed_state.approve(project, stage)
                self.assertTrue(self.pack.validate_pack(project)["valid"])
                self.assertEqual("completed", resumed_state.complete(project)["status"])


if __name__ == "__main__":
    unittest.main()
