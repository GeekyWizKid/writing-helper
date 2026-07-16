# 调研与事实管理

## 目的

建立问题树、来源表和主张账本，使进入脚本的事实可追溯、措辞强度与证据强度匹配。调研不是为预设观点找佐证。

## 必需输入

- 已批准的 `brief.md`、主路线、目标受众和时效边界。
- 用户素材及其来源身份。
- [能力路由](tool-routing.md) 返回的正文、访问日期与完整性状态。
- 计划进入脚本的事实、分析、观点、受众语言和个人经历。

## 执行步骤

1. 先把核心问题拆为问题树，包含支持证据、反例、反方观点、时间边界和不确定性。
2. 按来源层级获取材料：`primary` 原始文件/数据/当事人原话；`authoritative-secondary` 权威二手；`expert` 专业分析；`community` 社区语言与案例发现。
3. 社区来源只能单独支持 audience-language 或 anecdote；事实主张至少需要一条完整、全文可读的来源。搜索摘要不得冒充已读取全文。
4. 为来源记录 id、title、provenance、level、capture_status、body_status、accessed_at。
5. 为每条主张记录 `claim_id`、text、claim_type、`source_ids`、`confidence`，并补充可用措辞、时效与风险。制作执行稿用 `[C01]` 一类标记建立对应关系。
6. 来源冲突时并列呈现；证据不足时弱化措辞或删除主张。个人经历只表述为第一人称经验。
7. 不需外部调研时仍写明 decision_reason，sources 与 claims 为空，并核对脚本没有事实标记。

## 输出契约

`research.md` 保存问题树、结论边界、反例、素材卡和卖点—证据关系；`sources.md` 使用严格 JSON frontmatter，字段必须与校验器一致。

- 来源 id 用 `S01` 格式；`provenance` 必须是仅含 `{"url": "https://..."}` 或仅含 `{"file": "..."}` 的对象。
- `level` 只允许 `primary` / `authoritative-secondary` / `expert` / `community`；`capture_status` 只允许 `complete` / `partial` / `unavailable`；`body_status` 只允许 `full-text` / `search-snippet` / `metadata-only` / `unavailable`。
- 主张 id 用 `C01` 格式；`claim_type` 只允许 `factual` / `analysis` / `opinion` / `audience-language` / `anecdote`；`confidence` 只允许 `high` / `medium` / `low`；`source_ids` 是来源 id 字符串数组。

事实、解释和创作假设分栏，不把推断写成来源原话。可执行的完整示例见 [制作包契约](../assets/production-pack-template.md)。

## 拒绝条件

- 事实主张只有 `community` 来源或只有 `search-snippet`。
- 来源无法确认身份、访问日期或正文完整性。
- 主张账本与脚本标记不能双向对应。
- 高风险领域缺少可靠来源或人工复核提醒。

## 下一阶段交接

用户确认事实底座后，把可用结论、禁用措辞、冲突、素材卡和画面机会交给创意提案。未通过的主张从创意输入中移除，不留作“稍后补证据”。
