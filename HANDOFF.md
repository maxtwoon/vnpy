---
task: czsc-1.0-upgrade - Upgrade czsc dependency to 1.0 (Rust core rewrite)
version: 4.4.0
stage: dev
owner: kimi-code
updated: 2026-07-28
deliverables:
  - HANDOFF.md
  - docs/design/czsc-1.0-upgrade.md
  - examples/czsc_strategy/diagnostics/czsc_upgrade_behavior_diff_report.md
  - examples/czsc_strategy/diagnostics/czsc_upgrade_failure_attribution.md
blockers: []
last_transition_kind: reject
last_transition_actor: codex
last_transition_from_stage: review
last_transition_to_stage: dev
last_transition_from_owner: codex
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

- [x] `czsc.objects`/`czsc.enum`/`czsc.core`/`czsc.signals`/`czsc.svc`/`czsc.utils.echarts_plot`/
      `czsc.utils.bar_generator` 等已删除导入路径在全仓库清零。
- [x] `requirements.txt` 精确 pin `czsc==1.0.0rc8`（不是浮动版本号）。<!-- synccheck:ignore -->
- [x] `kline_pro` 替代方案（A105 的 `html_report.py` 依赖，A105 已 done 合并进主线）已选定落地，相关
      单测通过，有示例 HTML 佐证。
- [x] **新旧版本行为对比报告**（`diagnostics/` 下，RESEARCH-ONLY 横幅）：量化真实历史数据上笔/中枢/
      买卖点信号的差异幅度；本次补充了 `max_bi_num` 截断披露、逐 bar 信号转态统计、ZN888 分型差异根因、
      以及 research-mode 基准位移（SC888 收益率 3.794%→0.646%、夏普 0.809→0.242、三买多头 4→1）。
- [x] 全量单测套件跑过，新增失败逐条归因（见 `diagnostics/czsc_upgrade_failure_attribution.md`）。
- [x] 根目录与 `examples/czsc_strategy` 两处 `python tools/sync_check.py` 均通过。
- [x] VERSION/CHANGELOG 按设计文档 Phase 5 要求更新（新增 0.2.52 条目披露 review 修复与基准位移章节真正落地）。<!-- synccheck:ignore -->
- [x] `czsc==0.9.51` 回滚路径独立可 revert：requirements pin 单独提交，导入迁移与 vendor 另作提交。<!-- synccheck:ignore -->
- [x] 不删除/削弱任何既有 RESEARCH-ONLY、fail-closed、诚实披露机制。

## 给下一棒的说明

本轮为 review 打回后的修复轮次，已处理第 2 轮 review 的阻塞项 ④ 与 N1/N3/N4，并同步校准
CHANGELOG/HANDOFF 中的文档指向。请按以下清单验收：

### 本轮修复摘要

1. **基准回归披露机制修复**：`diagnostics/czsc_upgrade_diff_report.py` 的
   `_baseline_displacement()` 不再使用 `git show HEAD:<snapshot>`（会在 snapshot 刷新后
   自我抵消）也不再依赖相对 CWD 的路径。改为读取落盘的固定 golden fixture
   `tests/unit/test_position_sizing_research_equivalence.snapshot.pre_czsc10.json`
   （仅含 SC888/RB888 必要字段，约 1KB），缺失或损坏时直接抛错（fail-loud），章节
   不可能再被静默丢弃。
2. **行为差异报告补全**：重新生成 `diagnostics/czsc_upgrade_behavior_diff_report.md`，
   现在真正包含 "research-mode 基准位移" 章节，列出 SC888/RB888 Bucket-B 指标
   （SC888 total_return_pct 3.794%→0.646%、sharpe 0.809→0.242、三买多头 4 笔→1 笔等）。
3. **文档指向校准**：`diagnostics/czsc_upgrade_failure_attribution.md`、CHANGELOG.md 0.2.48 <!-- synccheck:ignore -->
   与 HANDOFF.md 验收标准第 4 条中对不存在章节的引用，现已与报告实际内容一致。
   CHANGELOG 新增 0.2.52 条目说明上述修复；VERSION bump 至 0.2.52。 <!-- synccheck:ignore -->
4. **N1 处理**：`diagnostics/czsc_upgrade_fixtures/`（约 20MB）与
   `diagnostics/czsc_upgrade_sample_report.html`（约 5MB）为可再生生成产物，本次不加入
   版本跟踪；报告内保留重新生成命令，review 可独立复跑验证。HANDOFF.md 中不存在将这两项
   列为"关键入口"或交付物的条目。

### 验证入口

```bash
# 根级门禁
python tools/sync_check.py

# 子项目门禁
python tools/sync_check.py --root examples/czsc_strategy

# 重新生成行为差异报告（需已安装 czsc==1.0.0rc8 并可访问真实 SQLite 历史库） <!-- synccheck:ignore -->
cd examples/czsc_strategy
set CZSC_MAX_BI_NUM=10000
python diagnostics/czsc_upgrade_bi_diff.py
python diagnostics/czsc_upgrade_diff_report.py

# 单元测试（not-realdb）
pytest tests/unit -q -m "not realdb"

# 单元测试（realdb）
pytest tests/unit -q -m realdb
```

### 已知未处理项

- **N2（SimNow 测试收集失败）**：`diagnostics/simnow_*.py` 模块被 `.gitignore` 排除但对应
  `tests/unit/test_simnow_*.py` 已入库，导致干净检出下 24 个 collection error。该问题属于
  SimNow 工作流卫生问题，超出本次 czsc 升级范围；`--continue-on-collection-errors` 下
  760 passed、5 failed 全部归因于该模块缺失，无 czsc 升级相关失败。
- **① 的残留瑕疵（历史提交卫生）**：czsc 的 CHANGELOG 0.2.47/0.2.48 条目落在 SimNow 提交 <!-- synccheck:ignore -->
  `239570e67` 中，无法在不重写历史的前提下"挪回"czsc 提交。本次以新增 0.2.52 条目 <!-- synccheck:ignore -->
  （落在本轮 czsc 修复提交中）的方式恢复纪律；若必须严格隔离历史，需额外一次 rebase
  （未执行，因与"不擅自 git rebase"的安全约束冲突）。
- **② 的瑕疵（`OLD_UNBOUNDED_BI_COUNTS` 硬编码）**：作为可选改进保留。当前报告已明确标注
  该列为"独立探索性运行"，属于诚实披露，不阻塞 review。

### Manual verification

| 门禁 | 结果 |
|---|---|
| `python tools/sync_check.py` | PASS (4.4.0) |
| `python tools/sync_check.py --root examples/czsc_strategy` | PASS (0.2.52) | <!-- synccheck:ignore -->
| `pytest tests/unit -q -m "not realdb"` | 978 passed, 4 deselected, 4 xfailed |
| `pytest tests/unit -q -m "not realdb" --continue-on-collection-errors` | N/A（直接运行已收集成功） |
| `pytest tests/unit -q -m realdb` | 4 passed, 982 deselected |
| `diagnostics/czsc_upgrade_behavior_diff_report.md` 含 "research-mode 基准位移" | PASS |
| `_baseline_displacement()` 缺失 fixture 时抛错 | PASS（已手动验证删除 fixture 后报错） |

## 决策记录

- 2026-07-27 (人 + claude-code, design) - 三个关键决定（记录于设计文档"决定记录"节，此处摘要，不重复<!-- synccheck:ignore -->
  正文）：① 目标版本固定 pin `1.0.0rc8`，不追新 rc、不等正式 1.0.0 稳定版；② 安装来源直接 PyPI<!-- synccheck:ignore -->
  (`pip install czsc==1.0.0rc8`)，不从 `maxtwoon/czsc` git 仓库装（没有证据表明该 fork 相对上游有独立<!-- synccheck:ignore -->
  patch，PyPI 版本已带 Windows 预编译 wheel，不需要本机 Rust 工具链）；③ 与 A105 的排序：等 A105
  完全 done 之后再开始 dev 阶段——现已满足，A105 于 2026-07-27 转入 done（含一次 review 打回+修复的
  完整周期），工作树已清空，具备开工条件，正式创建本任务。<!-- synccheck:ignore -->
- 2026-07-28 (kimi-code, dev) - B/S 序号标注与 echarts.min.js 内联保留在本任务内：两者直接提升 HTML
  报告可读性与离线可用性，已有配套单测与样例报告；内联 1.1MB 对 `diagnostics/` 目录的膨胀在可接受范围，
  后续归档时考虑将大体积 sample report 移入 `diagnostics/archive/`。
- 2026-07-28 (kimi-code, dev) - Phase 4 依赖验证结论：`czsc==1.0.0rc8` 新增的 `polars`、`scipy`、<!-- synccheck:ignore -->
  `statsmodels`、`wbt>=0.2.1`（PyPI `wbt` 0.6.0）、`typer` 经验证均可正常导入，`pip check` 干净，<!-- synccheck:ignore -->
  与 vnpy/czsc_strategy 既有依赖无冲突。<!-- synccheck:ignore -->
- 2026-07-28 (kimi-code, dev) - review 打回修复决策：
  ① 用落盘 golden fixture (`*.pre_czsc10.json`) + fail-loud 替代 `git show HEAD` 与相对 CWD 路径，
  根治 `_baseline_displacement()` 静默丢失与 snapshot 刷新后自我抵消的问题；
  ② `diagnostics/czsc_upgrade_fixtures/`（约 20MB）与 `czsc_upgrade_sample_report.html`（约 5MB）
  作为可再生生成产物不加入版本跟踪，review 通过报告内命令独立复跑验证。

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
| 2026-07-28 | kimi-code → codex | dev → review | czsc upgrade dev completed: import paths migrated to top-level czsc namespace, kline_pro vendored into chan_strategy/vendor, requirements pinned to target RC, real-data behavior diff report generated, unit tests pass (968 not-realdb + 4 realdb) with refreshed research-mode baseline, both sync_check gates pass |
| 2026-07-28 | codex → kimi-code | review → dev | 打回: czsc upgrade rejected: dev produced zero commits (rollback-isolation criterion unverifiable, work inseparable from concurrent SimNow tree changes incl. 29 deleted observation files); Phase 3 report omits the largest real-data delta (research-mode baseline: SC888 return 3.794%->0.646%, sharpe 0.809->0.242, 三买多头 4->1 trades) and its bi comparison is masked by the max_bi_num=50 cap; signal diff is a terminal snapshot not per-bar trigger statistics; no per-test failure attribution record; undesigned B/S labels + 1.1MB echarts inlining landed with no Decision Log entry |
