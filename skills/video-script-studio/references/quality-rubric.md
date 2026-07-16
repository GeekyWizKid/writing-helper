# 独立质量评审

## 目的

用基础否决门和路线专属评分卡审查完整制作包。评分是质量代理，不承诺播放量、完播率或转化结果。

## 必需输入

- 已批准的 `brief.md`、创作者硬约束和对应路线评分卡。
- 最终脚本、分镜、素材、发布方案、来源表和制作条件。
- 一个独立上下文：只读取简报、评分规则和交付稿，不读取创作阶段的自我辩护。

## 执行步骤

1. 先检查七个基础门：`factual_integrity`、`logical_consistency`、`brief_alignment`、`profile_constraints`、`duration_feasible`、`production_feasible`、`risk_disclosure`。任一为 false 即失败。
2. 按主路线使用唯一评分卡：
   - short-form：`viewing_reason` 25，`pace_progression` 20，`information_density` 20，`natural_delivery` 15，`ending_payoff` 20。
   - long-form：`research_depth` 20，`question_chain` 25，`chapter_value` 20，`evidence_opinion_separation` 20，`long_range_retention` 15。
   - narrative：`character_desire` 20，`conflict_escalation` 25，`scene_function` 20，`subtext` 15，`emotional_payoff` 20。
   - commercial：`audience_insight` 15，`single_promise` 20，`proof_strength` 20，`product_integration` 15，`action_drive` 15，`compliance` 15。
   - visual-essay：`visible_action` 20，`visual_storytelling` 20，`inner_outer_change` 15，`sound_design` 15，`voiceover_restraint` 15，`aesthetic_consistency` 15。
3. 每维给 0—10 分并写具体证据；任何核心维度低于 `7/10` 即失败。按 canonical weight 重算，总分低于 `80/100` 即失败。
4. 只修改造成失败的上游节点，并重新做事实、时长和可制作性检查。最多两轮自动修订；仍失败就停止，报告结构性问题与人工选择。
5. 将 passed、total_score、core_dimensions、base_gates、revision_count 写入严格 JSON frontmatter。

## 输出契约

`review.md` 给出每个门和维度的判定证据、精确分数、加权总分、修改记录、未解决风险与待人工判断事项。只有 passed=true、七门全真、各维不低于 7、总分不低于 80 且其他确定性校验通过，才允许完成。

## 拒绝条件

- 评审与创作共用自我解释，无法保持独立判断。
- 使用辅类型替换主路线评分卡，或擅自重分配权重。
- 分数没有引用交付稿中的具体位置。
- 超过两轮仍继续无目标重写，或把预测流量当作质量证据。

## 下一阶段交接

通过后运行确定性制作包校验并执行 complete；未通过则把问题定位到简报、调研、概念、结构、脚本或制作层。需要改变已批准上游时，先 reopen 对应阶段并保留 history。
