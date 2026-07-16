# 完整制作包契约

每个项目保留以下十个 Markdown 产物、`project.yaml` 和 `history/`。各段列出的标题使用完全相同的文字；路线标题只在对应主路线中必需。确定性规则以 `scripts/validate_pack.py` 为准。

## brief.md

写入获批简报、制作条件、事实边界和批准记录。路线标题放置规则：short-form 使用 `观看理由`；long-form 使用 `核心问题`；narrative 使用 `人物目标`；commercial 使用 `唯一核心承诺`。可从 [简报模板](brief-template.md) 开始。

## research.md

写入问题树、事实边界、冲突、素材卡与可用措辞。commercial 必须设置 `证据` 标题，逐项连接卖点、来源、画面和限定语。不需外部调研时也记录决定理由与创作假设。

## concepts.md

默认提供三个实质不同的方向。每个方向包含名称、一句话命题、受众与观看理由、叙事引擎、开头体验、核心转折、情绪曲线、视觉/声音、适合时长、制作难度、风险和推荐理由；最后记录用户选择或组合结果。

## outline.md

按体验节点记录时间、节点功能、观众状态、内容/行动、证据、画面与声音、留存作用。路线标题放置规则：short-form 使用 `中段推进`、`结尾兑现`；long-form 使用 `子问题链`、`章节回报`；narrative 使用 `阻力`。

## script.md

所有路线必须按顺序提供 `最终命题`、`目标`、`预计时长`、`干净表演稿`、`制作执行稿`、`待人工确认事项`、`可删段落`、`短版本切点`。narrative 另设 `潜台词`；visual-essay 另设 `旁白克制`。干净稿只保留实际表演文本，执行稿包含时间/场景、台词、行动、画面、摄影、声音、字幕和来源编号。

## storyboard.md

逐镜头填写镜头编号、预计时长、画面目的、可见行动、景别/机位/运动、旁白/对白、环境声/音乐、连接依据、拍摄难度和替代方案。visual-essay 必须设置 `可见行动`、`视觉母题`、`环境声` 三个标题，并证明行动优先于解释。

## assets.md

按必须实拍、用户已有、库存素材、截图/录屏、图表/动画、可选 AI 生成、声音素材分类。每项注明镜头位置、优先级、规格、来源/授权、版权风险、负责人和替代方案；仅规划提示，不声称媒体已经生成。

## publish.md

按平台给出 5—10 个标题方向、3 个封面概念、简介/发布正文、章节、置顶评论、CTA、可拆短片和 A/B 测试变量。解释每个标题与封面如何兑现脚本；不执行账号登录或自动发布。

## sources.md

文件以严格 JSON frontmatter 开始，字段为 schema_version、research_required、decision_reason、sources、claims。来源和主张的完整字段遵循 [调研规则](../references/research.md)。下面是不需外部调研且可直接通过来源校验的示例。

<!-- example:sources.md -->
```markdown
---
{
  "schema_version": 1,
  "research_required": false,
  "decision_reason": "本项目只表达虚构情节与第一人称创作感受，不主动引用外部事实。",
  "sources": [],
  "claims": []
}
---
# Sources

本项目没有外部事实来源；用户素材身份与创作假设已记录在 research.md。
```

## review.md

文件以严格 JSON frontmatter 开始，字段为 schema_version、passed、total_score、core_dimensions、base_gates、revision_count。commercial 还必须设置 `合规` 标题。下面的 visual-essay 示例使用 canonical weights，加权总分为 85，七个基础门全部通过。

<!-- example:review.md:visual-essay -->
```markdown
---
{
  "schema_version": 1,
  "passed": true,
  "total_score": 85,
  "core_dimensions": {
    "visible_action": {"score": 10, "weight": 20},
    "visual_storytelling": {"score": 8.5, "weight": 20},
    "inner_outer_change": {"score": 8, "weight": 15},
    "sound_design": {"score": 8, "weight": 15},
    "voiceover_restraint": {"score": 8, "weight": 15},
    "aesthetic_consistency": {"score": 8, "weight": 15}
  },
  "base_gates": {
    "factual_integrity": true,
    "logical_consistency": true,
    "brief_alignment": true,
    "profile_constraints": true,
    "duration_feasible": true,
    "production_feasible": true,
    "risk_disclosure": true
  },
  "revision_count": 1
}
---
# Review

独立评审已引用交付稿中的具体场景；各维度均达到门槛，剩余人工判断已明确列出。
```

## 完成条件

五个批准门均为 approved；十个产物有实质内容且没有未解决占位标记；来源、路线标题、评分权重、总分、历史和安全拓扑全部通过校验。未通过时不得写 complete。
