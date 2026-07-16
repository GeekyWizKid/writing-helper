from __future__ import annotations

import re
import unittest
from pathlib import Path

from helpers import SKILL_ROOT, load_script_module


REFERENCE_NAMES = {
    "discovery.md",
    "tool-routing.md",
    "research.md",
    "storyboard.md",
    "publishing.md",
    "quality-rubric.md",
    "short-form.md",
    "long-form.md",
    "narrative.md",
    "commercial.md",
    "visual-essay.md",
}
SHARED_REFERENCES = {
    "discovery.md",
    "tool-routing.md",
    "research.md",
    "storyboard.md",
    "publishing.md",
    "quality-rubric.md",
}
ROUTE_REFERENCES = {
    "short-form.md": "short-form",
    "long-form.md": "long-form",
    "narrative.md": "narrative",
    "commercial.md": "commercial",
    "visual-essay.md": "visual-essay",
}
SHARED_SECTIONS = (
    "目的",
    "必需输入",
    "执行步骤",
    "输出契约",
    "拒绝条件",
    "下一阶段交接",
)
ROUTE_SECTIONS = (
    "适用信号",
    "反信号",
    "简报字段",
    "结构工作流",
    "脚本格式",
    "时长方法",
    "评分权重",
    "失败模式",
    "最小合格示例",
)
ROUTE_ANCHORS = {
    "short-form.md": ("观看理由", "中段推进", "结尾兑现"),
    "long-form.md": ("核心问题", "子问题链", "章节回报"),
    "narrative.md": ("人物目标", "阻力", "潜台词"),
    "commercial.md": ("唯一核心承诺", "证据", "合规"),
    "visual-essay.md": ("可见行动", "视觉母题", "环境声", "旁白克制"),
}
ARTIFACT_HEADINGS = {
    "brief.md": ("观看理由", "核心问题", "人物目标", "唯一核心承诺"),
    "research.md": ("证据",),
    "outline.md": ("中段推进", "结尾兑现", "子问题链", "章节回报", "阻力"),
    "script.md": (
        "最终命题",
        "目标",
        "预计时长",
        "干净表演稿",
        "制作执行稿",
        "待人工确认事项",
        "可删段落",
        "短版本切点",
        "潜台词",
        "旁白克制",
    ),
    "storyboard.md": ("可见行动", "视觉母题", "环境声"),
    "review.md": ("合规",),
}


def second_level_headings(text: str) -> tuple[str, ...]:
    return tuple(re.findall(r"(?m)^## (.+?)\s*$", text))


def named_section(text: str, heading: str) -> str:
    match = re.search(
        rf"(?ms)^## {re.escape(heading)}\s*$\n(.*?)(?=^## |\Z)", text
    )
    if match is None:
        return ""
    return match.group(1)


def marked_example(text: str, marker: str) -> str:
    match = re.search(
        rf"(?ms)<!-- example:{re.escape(marker)} -->\s*```markdown\s*\n(.*?)^```\s*$",
        text,
    )
    if match is None:
        return ""
    return match.group(1)


class ReferenceContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.references = SKILL_ROOT / "references"
        cls.validator = load_script_module("validate_pack")
        cls.source_validator = load_script_module("validate_sources")

    def read_reference(self, name: str) -> str:
        path = self.references / name
        return path.read_text(encoding="utf-8") if path.is_file() else ""

    def test_reference_directory_has_exact_required_files(self) -> None:
        actual = (
            {path.name for path in self.references.iterdir() if path.is_file()}
            if self.references.is_dir()
            else set()
        )
        self.assertEqual(REFERENCE_NAMES, actual)

    def test_shared_and_route_references_have_exact_second_level_sections(self) -> None:
        for name in SHARED_REFERENCES:
            with self.subTest(reference=name):
                self.assertEqual(
                    SHARED_SECTIONS, second_level_headings(self.read_reference(name))
                )
        for name in ROUTE_REFERENCES:
            with self.subTest(reference=name):
                self.assertEqual(
                    ROUTE_SECTIONS, second_level_headings(self.read_reference(name))
                )

    def test_shared_references_encode_executable_stage_contracts(self) -> None:
        required_phrases = {
            "discovery.md": (
                "一次只问一个问题",
                "project.yaml",
                "status",
                "brief.md",
                "用户明确确认",
                "不得把沉默当作批准",
            ),
            "tool-routing.md": (
                "能力清单",
                "专业 Skill",
                "基础工具",
                "停止",
                "不得编造",
                "provenance",
                "accessed_at",
                "capture_status",
                "body_status",
            ),
            "research.md": (
                "问题树",
                "primary",
                "authoritative-secondary",
                "expert",
                "community",
                "claim_id",
                "source_ids",
                "confidence",
                "搜索摘要不得冒充已读取全文",
            ),
            "storyboard.md": (
                "镜头编号",
                "预计时长",
                "画面目的",
                "可见行动",
                "景别/机位/运动",
                "旁白/对白",
                "环境声/音乐",
                "连接依据",
                "拍摄难度",
                "替代方案",
            ),
            "publishing.md": (
                "必须实拍",
                "用户已有",
                "库存素材",
                "截图/录屏",
                "图表/动画",
                "可选 AI 生成",
                "声音素材",
                "不自动生成媒体",
                "不自动发布",
            ),
            "quality-rubric.md": (
                "独立上下文",
                "最多两轮",
                "80/100",
                "7/10",
                *self.validator.BASE_GATES,
                *(
                    dimension
                    for dimensions in self.validator.ROUTE_DIMENSIONS.values()
                    for dimension in dimensions
                ),
            ),
        }
        for name, phrases in required_phrases.items():
            content = self.read_reference(name)
            for phrase in phrases:
                with self.subTest(reference=name, phrase=phrase):
                    self.assertIn(phrase, content)

    def test_route_references_include_anchors_and_professional_workflows(self) -> None:
        route_phrases = {
            "short-form.md": ("口语", "呼吸", "开头", "中段"),
            "long-form.md": ("章节", "反方观点", "证据/观点", "长程留存"),
            "narrative.md": ("人物欲望", "失败代价", "场景作用", "行动意图"),
            "commercial.md": ("目标人群", "卖点—证据表", "CTA", "A/B"),
            "visual-essay.md": (
                "Gawx",
                "事件—行动—画面—声音—旁白",
                "能用行动表达就不使用旁白",
                "能用画面表达就不解释画面",
                "不可见的思想、记忆和变化",
            ),
        }
        for name, anchors in ROUTE_ANCHORS.items():
            content = self.read_reference(name)
            for phrase in (*anchors, *route_phrases[name]):
                with self.subTest(reference=name, phrase=phrase):
                    self.assertIn(phrase, content)

    def test_route_weight_sections_match_validator_canonical_weights(self) -> None:
        for name, route in ROUTE_REFERENCES.items():
            section = named_section(self.read_reference(name), "评分权重")
            actual = {
                key: int(weight)
                for key, weight in re.findall(
                    r"`([a-z][a-z0-9_]*)`\s*:\s*`?(\d+)%`?", section
                )
            }
            with self.subTest(reference=name):
                self.assertEqual(self.validator.ROUTE_WEIGHTS[route], actual)

    def test_templates_define_validator_headings_in_assigned_artifacts(self) -> None:
        brief_path = SKILL_ROOT / "assets" / "brief-template.md"
        pack_path = SKILL_ROOT / "assets" / "production-pack-template.md"
        brief = brief_path.read_text(encoding="utf-8") if brief_path.is_file() else ""
        pack = pack_path.read_text(encoding="utf-8") if pack_path.is_file() else ""

        for heading in ARTIFACT_HEADINGS["brief.md"]:
            self.assertRegex(brief, rf"(?m)^## {re.escape(heading)}$")
        for artifact, headings in ARTIFACT_HEADINGS.items():
            section = named_section(pack, artifact)
            self.assertTrue(section, f"missing artifact contract: {artifact}")
            for heading in headings:
                with self.subTest(artifact=artifact, heading=heading):
                    self.assertIn(f"`{heading}`", section)

    def test_machine_readable_examples_are_strict_and_validator_compatible(self) -> None:
        path = SKILL_ROOT / "assets" / "production-pack-template.md"
        content = path.read_text(encoding="utf-8") if path.is_file() else ""
        sources_text = marked_example(content, "sources.md")
        review_text = marked_example(content, "review.md:visual-essay")
        self.assertTrue(sources_text)
        self.assertTrue(review_text)

        sources, _ = self.validator._frontmatter(sources_text)
        source_result = self.source_validator.validate(sources, "")
        self.assertTrue(source_result["valid"], source_result)

        review, _ = self.validator._frontmatter(review_text)
        self.assertEqual(
            set(self.validator.ROUTE_DIMENSIONS["visual-essay"]),
            set(review["core_dimensions"]),
        )
        problems = self.validator._Problems()
        self.validator._validate_review(review_text, "visual-essay", problems)
        self.assertEqual([], problems.codes)
        recomputed = sum(
            value["score"] * value["weight"] / 10
            for value in review["core_dimensions"].values()
        )
        self.assertAlmostEqual(review["total_score"], recomputed, places=9)

    def test_documents_have_no_placeholder_tokens_or_broken_local_links(self) -> None:
        paths = [self.references / name for name in REFERENCE_NAMES]
        paths.extend(
            (
                SKILL_ROOT / "assets" / "brief-template.md",
                SKILL_ROOT / "assets" / "production-pack-template.md",
            )
        )
        for path in paths:
            content = path.read_text(encoding="utf-8") if path.is_file() else ""
            with self.subTest(path=path.name):
                self.assertIsNone(
                    re.search(
                        r"(?<![A-Za-z0-9_])(?:TBD|TODO|FIXME)(?![A-Za-z0-9_])",
                        content,
                        re.IGNORECASE,
                    )
                )
            for target in re.findall(r"\[[^]]+\]\(([^)]+)\)", content):
                if re.match(r"(?:https?://|#)", target):
                    continue
                resolved = (path.parent / target).resolve()
                with self.subTest(path=path.name, target=target):
                    self.assertTrue(resolved.is_file())
                    self.assertTrue(resolved.is_relative_to(SKILL_ROOT.resolve()))


if __name__ == "__main__":
    unittest.main()
