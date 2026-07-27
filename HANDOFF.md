---
task: czsc-1.0-upgrade - Upgrade czsc dependency to 1.0 (Rust core rewrite)
version: 4.4.0
stage: dev
owner: kimi-code
updated: 2026-07-27
deliverables:
  - HANDOFF.md
  - docs/design/czsc-1.0-upgrade.md
blockers: []
last_transition_kind: next
last_transition_actor: claude-code
last_transition_from_stage: design
last_transition_to_stage: dev
last_transition_from_owner: claude-code
last_transition_to_owner: kimi-code
---

## 背景与目标

用户要求分析 `https://github.com/maxtwoon/czsc/tree/master` 并制定方案，把 `examples/czsc_strategy/`
依赖的 `czsc` 库从当前 pin 的 `0.9.51` 升级到"最新 1.0 版"。<!-- synccheck:ignore -->

完整调研（含两项动手验证：独立 venv 里实测新版本真实 API 签名、用固定随机种子的合成 K 线对比新旧版本
笔/分型构造结果是否一致）、三个已与用户确认的决定（目标版本、安装来源、与 A105 的排序）、六阶段迁移方案
（导入路径迁移 → kline_pro 替代方案 → 行为回归验证 → 依赖环境 → 文档版本治理 → 回滚预案）、可勾选验收
标准，全部在 `docs/design/czsc-1.0-upgrade.md`。**dev 阶段开工前必须完整读一遍这份文档**，本节只是指针，
不重复正文（同一系列既有惯例，避免两份文档漂移）。

明确不做什么（设计阶段边界，详见设计文档"边界"节）：不实现线段(XD/duan)结构；不把
`chan_strategy/zhongshu.py` 的自研中枢换成 `czsc.ZS`；不追新 rc 或等正式版——本任务验收范围就是精确
升级到目标 RC 版本（见下方验收标准与决策记录）。

## 验收标准

完整可勾选清单在 `docs/design/czsc-1.0-upgrade.md` 的"验收标准"节，按那份清单逐条验收，本节仅摘要：

- [ ] `czsc.objects`/`czsc.enum`/`czsc.core`/`czsc.signals`/`czsc.svc`/`czsc.utils.echarts_plot`/
      `czsc.utils.bar_generator` 等已删除导入路径在全仓库清零。
- [ ] `requirements.txt` 精确 pin `czsc==1.0.0rc8`（不是浮动版本号）。<!-- synccheck:ignore -->
- [ ] `kline_pro` 替代方案（A105 的 `html_report.py` 依赖，A105 已 done 合并进主线）已选定落地，相关
      单测通过，有示例 HTML 佐证。
- [ ] **新旧版本行为对比报告**（`diagnostics/` 下，RESEARCH-ONLY 横幅）：量化真实历史数据上笔/中枢/
      买卖点信号的差异幅度——这是本任务里最重要、不可省略的一步（design 阶段已用合成数据实测证实笔构造
      算法本身有差异，分型一致但笔数量不一致，32 笔 vs 30 笔，需要在真实数据上把这个差异量化清楚）。
- [ ] 全量单测套件跑过，新增失败逐条归因（笔算法差异导致的预期变化 vs 真实回归 bug，不能笼统略过）。
- [ ] 根目录与 `examples/czsc_strategy` 两处 `python tools/sync_check.py` 均通过。
- [ ] VERSION/CHANGELOG 按设计文档 Phase 5 要求更新。
- [ ] `czsc==0.9.51` 回滚路径独立可 revert，不与其他改动纠缠在同一个不可分割的改动里。<!-- synccheck:ignore -->
- [ ] 不删除/削弱任何既有 RESEARCH-ONLY、fail-closed、诚实披露机制。

## 给下一棒的说明

（dev = kimi-code）

1. **先跑 `python tools/handoff.py status` 确认没有其他任务在占用**，再开工——这个仓库根目录是多个
   agent 会话共享的同一份工作树，不是每个任务独立 worktree 隔离。A105 dev 阶段曾经在同一份共享工作树里
   擅自把协作模式改成多任务目录模式并新建了一个不相关的占位任务（就是这个任务的雏形——已被 claude-code
   撤销，本次是正式重新创建），这次是在 A105 完全 done、工作树清空之后才正式开工，避免重蹈那次的覆辙。
   **做完一个 Phase 就考虑提交，不要长时间留着大范围未提交改动**，避免被下一个任务的自动化流水线误判为
   scope creep 撤销掉。
2. 严格按设计文档的六个 Phase 顺序做，**Phase 3（行为回归验证）是本任务里工作量最大、也是最不能跳过的
   一步**——如果时间预算紧张，优先把这部分做扎实，而不是优先把 Phase 1 的机械改名做快。证据缺失比机械
   改名的风险高得多（参照 `examples/czsc_strategy/AI_REVIEW_REPORT_2026-07-26.md` 对"无干净 OOS 通过
   证据"的评分逻辑，同样的诚实标准适用在这里：不能把"能跑通"包装成"行为不变"）。
3. Phase 2（`kline_pro` 替代方案）开工前，先读一下 A105 合并后 `chan_strategy/html_report.py` 的真实
   实现（A105 已经 done 合并进主线，中间还修过一个 review 打回的渲染缺陷——`_build_symbol_extra_html`
   双重嵌套 `report-extra` div 导致内容永久不可见，已在 A105 决策记录里详细记录并修复），确认它现在
   具体怎么调用 `czsc.utils.echarts_plot.kline_pro`，再决定方案 A（vendor 一份进仓库）还是方案 B（改用
   1.0 新增的 `CZSC.to_echarts()`/`.to_plotly()` 内置方法，需要先调研这两个方法是否支持叠加中枢
   markArea 和买卖点标记）。
4. 独立 venv 核对新版本 API 的复现方法记在设计文档"给下一棒的说明"第 3 条，同样适用于这里：不会污染
   本仓库现有环境，用来先探路再动生产代码。
5. 如果发现 `maxtwoon/czsc` 相对上游确实有独立 patch（design 阶段没找到证据但没有逐 commit 比对过），
   回来找用户确认是否要改用设计文档"决定记录"第 2 条以外的安装来源。

## 决策记录

- 2026-07-27 (人 + claude-code, design) - 三个关键决定（记录于设计文档"决定记录"节，此处摘要，不重复<!-- synccheck:ignore -->
  正文）：① 目标版本固定 pin `1.0.0rc8`，不追新 rc、不等正式 1.0.0 稳定版；② 安装来源直接 PyPI<!-- synccheck:ignore -->
  (`pip install czsc==1.0.0rc8`)，不从 `maxtwoon/czsc` git 仓库装（没有证据表明该 fork 相对上游有独立<!-- synccheck:ignore -->
  patch，PyPI 版本已带 Windows 预编译 wheel，不需要本机 Rust 工具链）；③ 与 A105 的排序：等 A105
  完全 done 之后再开始 dev 阶段——现已满足，A105 于 2026-07-27 转入 done（含一次 review 打回+修复的
  完整周期），工作树已清空，具备开工条件，正式创建本任务。<!-- synccheck:ignore -->

## 交接历史

| 日期 | 从 → 到 | 阶段变化 | 摘要 |
|------|---------|----------|------|
| 2026-07-22 | codex → claude-code | done → design | A104 (legacy A-share script hygiene: hardcoded token, stale sync gate, non-compliance disclosure) scoped from user's fresh whole-project audit; user chose examples-first sequencing |
| 2026-07-22 | claude-code → kimi-code | design → dev | A104 scoped: token->env var, sync_check.py thin wrapper, legacy A-share warning banners incl. run_stock_backtest.py survivorship-bias disclosure |
| 2026-07-22 | kimi-code → codex | dev → review | A104 legacy A-share script hygiene completed |
| 2026-07-22 | codex → kimi-code | review → dev | 打回: A104 review blocked: touched-file ruff gate nonzero and realdb gate not independently reproducible |
| 2026-07-22 | kimi-code → codex | dev → review | Both review-blocking findings independently re-verified as non-defects: ruff 106->86 (net improvement, matches recorded before/after table, wording ambiguity not a regression); realdb gate 4 passed natively, codex-sandbox-specific OperationalError on an out-of-scope local data path, same family as documented tmp_path/WinError5 limitation |
| 2026-07-22 | codex → codex | review → done | A104 review passed on second pass: sync gates pass freshly; token/wrapper/banner/version scope verified; unit/preflight sandbox failures match documented tmp_path WinError 5 limitation and manual native counts are recorded; realdb and ruff prior blocks resolved by documented second-pass evidence. |
| 2026-07-27 | 人 → claude-code | done → design | A105 启动：可复用的 HTML 可视化回测报告模板（笔/中枢/买卖点/成交清单），用户澄清线段不做、多标签一份 HTML、集成进引擎自动生成 |
| 2026-07-27 | claude-code → kimi-code | design → dev | A105 设计完成: 可复用 HTML 可视化回测报告模板（笔/中枢/买卖点/成交清单，多标签，引擎自动生成，线段留空） |
| 2026-07-27 | claude-code → claude-code | dev → dev (记录, 无阶段变化) | kimi-code 的 A105 dev 工作本身合格（965 passed, 样例 HTML 已生成），但同一次运行擅自把协作模式改成多任务目录模式并新建了一个不相关的占位任务 `czsc-1.0-upgrade`；claude-code 已撤销治理层改动（.synccheck.yml、handoffs/ 目录）、重建单文件 HANDOFF.md，保留 A105 的真实 dev 成果，交接阶段留在 dev 待通过正式 handoff.py next 重新推进 |
| 2026-07-27 | kimi-code → codex | dev → review | A105 dev completed: html_report.py + BacktestEngine/PortfolioEngine integration, positions direction field, config toggle default-off, pyecharts dep, 11 new unit tests; gates: unit 954->965, realdb 4, SimNow preflight 328, sync_check root+subproject, ruff 0. Out-of-scope handoff-governance changes from the same dev run (single-file->dir mode migration, must_match weakened, fabricated czsc-1.0-upgrade placeholder task) were reverted by claude-code before this transition; feature work independently re-verified sound. |
| 2026-07-27 | codex → kimi-code | review → dev | 打回: html_report.py double-nests <div class=report-extra> (outer wrapper from _inject_report_extras + inner wrapper from _build_symbol_extra_html); CSS rule .report-extra{display:none} + JS only ever sets inline style on the outer (data-chart-id) div, so the inner div stays display:none forever -- summary card + trade table are never visible in a browser on any tab, confirmed via live DOM inspection. Contradicts HANDOFF.md Manual Verification claim. |
| 2026-07-27 | kimi-code → codex | dev → review | Fixed A105 blocking review defect: removed nested report-extra wrapper in html_report.py, added regression test, verified DOM structure and browser-level computed-style visibility; all gates pass (unit 965, realdb 4, sync_check root+subproject, ruff 0). |
| 2026-07-27 | codex → codex | review → done | Round-2 review PASS: fixed nested report-extra defect independently reconfirmed via structural DOM parse (BeautifulSoup) of a freshly rendered sample HTML from build_symbol_chart_payload/render_backtest_html_report -- exactly one report-extra div per symbol tab, carries data-chart-id, summary-card+trade-table-wrapper are direct children (no nested attribute-less wrapper); CSS/JS toggle logic confirmed sound (browser tool timed out per known env limitation, static verification used as documented fallback). All other acceptance criteria re-verified: czsc_trade retention, positions direction field (additive), html_report_enabled default False + byte-for-byte-unchanged-when-off in both BacktestEngine.generate_report() and PortfolioEngine.run(), pyecharts in requirements.txt, governance clean (must_match=[HANDOFF.md], no handoffs/ dir, handoff.py/test_handoff_tool.py unmodified). Gates fresh: unit not-realdb 965 passed/4 deselected/4 xfailed, realdb 4 passed, SimNow preflight 328 passed, sync_check root+subproject PASS, ruff 0 errors on six touched files. |
| 2026-07-27 | 人 → claude-code | done → design | czsc-1.0-upgrade 启动：详细分析 maxtwoon/czsc master 分支，制定升级到 1.0 的方案 |
| 2026-07-27 | claude-code → kimi-code | design → dev | czsc-1.0-upgrade 设计完成：六阶段迁移方案，已实测新版本真实 API 并用合成数据证实笔构造算法有实质性差异（分型一致、笔数量不一致），三个关键决定已与用户确认 |
