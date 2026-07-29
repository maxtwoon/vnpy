---
task: "A106 走势类型分类信号（盘整/趋势）"
stage: done
owner: claude-cowork
updated: 2026-07-29
deliverables:
  - docs/design/A106_trend_type_signal.md
  - chan_strategy/signals.py
  - tests/unit/test_a106_trend_type_signal.py
  - VERSION
  - CHANGELOG.md
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

审核通过，下一步由 handoff 驱动推进到 done。A106 新增信号保持只读，不接入默认交易路径；
AC6 的干净 not-realdb/realdb 实证由调用方本机补齐并写入最新交接历史，AC7 sync_check 已由 codex 复跑 PASS。

下一棒 = claude-cowork（review 阶段）。A106 dev 已新增 `signal_trend_type()` 只读信号，
输出 `{freq}_D1ZS_走势类型V260729` 五值完全分类：无中枢 / 盘整 / 上涨趋势 / 下跌趋势 / 中枢延伸。
实现严格按设计 D1~D4：中枢来源为 `_get_confirmed_bi_list()` 的已确认笔 +
`build_zhongshu_from_bis()`；相邻中枢用 `zd/zg` 同时抬高/降低判定方向；趋势要求 `[zd, zg]`
区间不重叠；方向完全由中枢序列几何决定，未引入 a0 校验。

接入边界：新信号没有注册进 `sell_signals.get_all_signals()` 或 legacy 聚合入口，也没有接入任何
`_research_*_open_allowed()`、开仓、平仓或仓位门控。AC4 单测断言默认聚合入口不消费该信号，
以保持默认配置下交易路径与回测基线不变。

自测记录：`C:\Python314\python.exe -m pytest tests/unit/test_a106_trend_type_signal.py -q`
在设置 `POLARS_SKIP_CPU_CHECK=1` 后通过（4 passed）。全量 not-realdb 在本机被 pytest 临时目录
权限问题阻断：默认 temp root `C:\Users\Admin\AppData\Local\Temp\pytest-of-Admin` 拒绝访问；
改用 `--basetemp` 到工作区后，pytest 创建的 basetemp 子目录也变成不可扫描。请 review 阶段在干净
pytest 临时目录环境复跑 `C:\Python314\python.exe -m pytest tests/unit -q -m "not realdb"`；
未跑 realdb，留 review。

## 审核结论

A106 review 由 codex 按用户显式指派执行（覆盖本文件默认 review=claude-cowork 的角色安排）。

D1~D4 一致性：

- D1 通过：`signal_trend_type()` 使用 `_get_confirmed_bi_list(c)` 后调用 `build_zhongshu_from_bis(bi_list)`。
- D2 通过：相邻中枢方向使用 `next_zs["zd"] > current_zs["zd"]` 且
  `next_zs["zg"] > current_zs["zg"]`；下跌镜像使用 `zd/zg` 同时降低。
- D3 通过：趋势无重叠判据固定为 `[zd, zg]` 不相交，即上涨 `current_zs["zg"] < next_zs["zd"]`、
  下跌 `current_zs["zd"] > next_zs["zg"]`。
- D4 通过：新函数内未引入 a0 / 进入段校验，方向完全由相邻中枢几何序列决定。

AC1~AC7：

- AC1 通过：`test_trend_type_is_exhaustive_and_mutually_exclusive_on_synthetic_fixtures` 覆盖
  无中枢 / 盘整 / 上涨趋势 / 下跌趋势 / 中枢延伸五类，并断言 seen 集合等于五值全集。
- AC2 通过：`test_raised_but_overlapped_centers_are_extension_not_uptrend` 构造抬高但重叠 fixture，
  断言 v1 为 `中枢延伸`。
- AC3 通过：实现只取 `_get_confirmed_bi_list()`；`test_trend_type_uses_confirmed_bi_prefix_only`
  断言追加 `last_bi_extend=True` 的未确认尾笔不改变信号字典。
- AC4 通过（代码路径层面）：`rg` 仅在 `signals.py`、A106 测试、设计文档和 changelog 中发现
  `signal_trend_type` / `走势类型V260729`；`sell_signals.get_all_signals()`、`backtest_engine.py`、
  `config.py` 未消费新信号；A106 单测断言默认聚合入口不含该 key。
- AC5 通过：docstring 写明“已确认笔构建笔中枢”“单个 K 线周期的笔中枢”“周期是观察窗口标记，
  不等同于缠论递归级别”，命名为 `{freq}_D1ZS_走势类型V260729`。
- AC6 通过：A106 聚焦测试本 review 实跑 4 passed；调用方本机完成干净全量实证并已写入最新交接历史：
  not-realdb 986 passed（4:07），realdb 4 passed（4:11）。codex 沙箱的 temp/sqlite 权限问题确认为环境限制。
- AC7 通过：VERSION 为 0.2.63，CHANGELOG 有 0.2.63 条目，设计文档有 dev 记录；
  `C:\Python314\python.exe tools\sync_check.py` 本 review 复跑 PASS。

总体结论：通过。核心实现、测试覆盖、接入边界、版本/变更记录与同步门禁均满足 A106 设计合同。

## 决策记录

- 2026-07-29 · 立项 A106，design 阶段 · 依据对照核查表 §9 P1；本子项目无独立 handoff
  流水线（`.synccheck.yml` 未配 `handoff.commands`，驱动器亦无 `new` 子命令），
  按旧 HANDOFF 占位文件的指引直接重写本文件，替代 `tools/handoff.py new`。
- 2026-07-29 · 任务编号取 A106 · 根目录设计编号至 a89/A102，子项目 html report 任务为 a105，
  取 A106 避免冲突。
- 2026-07-29 · dev 接入边界 · 未将 `signal_trend_type()` 加入默认信号聚合入口；
  理由是设计 §4 要求默认配置下回测基线字节一致，且该信号当前只读、未被交易路径消费。
- 2026-07-29 · review 角色覆盖 · 用户显式指派 codex 执行 A106 review，覆盖 AGENTS.md/HANDOFF
  默认 review=claude-cowork 的安排；本次审核结论由 codex 写入。

## 交接历史

| 日期 | 从 → 到 | 阶段变化 | 摘要 |
|------|---------|----------|------|
| 2026-07-29 | 人 → claude-cowork | → design | A106 立项：走势类型分类信号设计文档 + 验收标准 |
| 2026-07-29 | claude-cowork → code-agent | design → dev | A106 设计完成：走势类型信号设计文档 + AC1~AC7 验收标准已定稿（commit 73e498430），移交 code-agent 开发 |
| 2026-07-29 | code-agent → claude-cowork | dev → review | A106 dev implemented signal_trend_type with AC1-AC4 unit coverage; targeted test passed; full not-realdb blocked by local pytest temp ACL |
| 2026-07-29 | claude-cowork → code-agent | review → dev | 打回: A106 review blocked: sync_check fails diagnostics banner; full not-realdb/realdb verification environment-blocked |
| 2026-07-29 | code-agent → claude-cowork | dev → review | 打回阻断项已消解：①AC7 横幅缺失系 review prompt 输入文件（a106_codex_*_prompt.md）未带 RESEARCH-ONLY banner 触发 diagnostics_banner_check，已补齐，sync_check 复跑 PASS；②AC6 干净实证由驱动方在本机（非 codex 沙箱）完成：not-realdb 986 passed（14:07）、realdb 4 passed（14:11），codex 沙箱的 temp/sqlite 权限问题属其环境限制。移交 codex 复审 |
| 2026-07-29 | claude-cowork → claude-cowork | review → done | A106 review passed: D1-D4 and AC1-AC7 accepted; sync_check PASS; external clean test evidence recorded |
