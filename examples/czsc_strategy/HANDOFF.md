---
task: "A106 走势类型分类信号（盘整/趋势）"
stage: design
owner: claude-cowork
updated: 2026-07-29
deliverables:
  - docs/design/A106_trend_type_signal.md
blockers: []
---

## 背景与目标

《缠论》书摘 ⇄ 代码对照核查表（`docs/theory_code_crosscheck.md`，0.2.58 立项，
§8 断言已于 0.2.60 实测、P0 口径整改已于 0.2.61 落地）剩余的 P1 项中，
"走势类型分类信号"是唯一不依赖区间套大设计、可独立交付的能力：
按书第 75~79 页定义，在当前主信号链路（笔中枢层）新增 `{freq}_D1ZS_走势类型V260729`
完全分类信号，输出 无中枢 / 盘整 / 上涨趋势 / 下跌趋势 / 中枢延伸 五值。
新增只读信号，默认不接入任何开/平仓门控，回测基线字节不变。

## 验收标准

以 `docs/design/A106_trend_type_signal.md` §5 为准（AC1~AC7，逐条可判定）：

- [ ] AC1 五值完全分类在合成 fixture 上互斥且穷尽
- [ ] AC2 书第 78 页判据专项：两中枢抬高但重叠 → 必须输出"中枢延伸"
- [ ] AC3 无未来函数：仅用已确认笔，前缀稳定性测试
- [ ] AC4 默认配置下回测基线不变（新信号未被交易路径消费）
- [ ] AC5 docstring 写明"笔中枢"与"周期≠级别"口径
- [ ] AC6 not-realdb 全量通过 + realdb 实跑输出（AGENTS.md 守则）
- [ ] AC7 VERSION + CHANGELOG + 文档同一提交，sync_check 通过

## 给下一棒的说明

下一棒 = code-agent（dev 阶段）。只按 `docs/design/A106_trend_type_signal.md` 开发，
重点是 §3 的四条设计决策（D1~D4）：中枢来源复用 `build_zhongshu_from_bis` + 已确认笔；
"依次抬高/降低"用相邻中枢 zd、zg 同时比较；"无重叠"用 [zd, zg] 区间不相交（本版不取 gg/dd）；
方向由中枢序列几何决定、不引入 a0 校验。发现设计问题：小偏离记入决策记录，
大偏离把 stage 退回 design 并写明原因，不要静默改设计。
注意铁律：本信号不得接入 `_research_*_open_allowed()` 等任何门控。

## 决策记录

- 2026-07-29 · 立项 A106，design 阶段 · 依据对照核查表 §9 P1；本子项目无独立 handoff
  流水线（`.synccheck.yml` 未配 `handoff.commands`，驱动器亦无 `new` 子命令），
  按旧 HANDOFF 占位文件的指引直接重写本文件，替代 `tools/handoff.py new`。
- 2026-07-29 · 任务编号取 A106 · 根目录设计编号至 a89/A102，子项目 html report 任务为 a105，
  取 A106 避免冲突。

## 交接历史

| 日期 | 从 → 到 | 阶段变化 | 摘要 |
|------|---------|----------|------|
| 2026-07-29 | 人 → claude-cowork | → design | A106 立项：走势类型分类信号设计文档 + 验收标准 |
