---
task: czsc-1.0-upgrade - Upgrade czsc dependency to 1.0 (Rust core rewrite)
version: 4.4.0
stage: done
owner: codex
updated: 2026-07-28
deliverables:
  - HANDOFF.md
  - docs/design/czsc-1.0-upgrade.md
  - examples/czsc_strategy/diagnostics/czsc_upgrade_behavior_diff_report.md
  - examples/czsc_strategy/diagnostics/czsc_upgrade_failure_attribution.md
blockers: []
last_transition_kind: next
last_transition_actor: codex
last_transition_from_stage: review
last_transition_to_stage: done
last_transition_from_owner: codex
last_transition_to_owner: codex
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

第 3 轮 review 结论：**PASS**。第 2 轮的唯一阻塞项（`_baseline_displacement()` 静默失败 /
自我抵消，以及基准位移数字只存在于 CHANGELOG 而不在报告正文）已被真正修复，并通过
"主动破坏"式验证而非仅阅读代码确认。以下为逐项证据。

审核环境：独立 worktree `.claude/worktrees/agent-a6111ba4f3fca4dac`，`git reset --hard e3e5ae6e0`
（干净检出，`git status` 无改动），与 dev 的共享主工作树完全隔离。

### ① 第 2 轮阻塞项 —— 已修复（对抗性验证）

`_baseline_displacement()`（`examples/czsc_strategy/diagnostics/czsc_upgrade_diff_report.py:153`）
现在从落盘的 golden fixture
`examples/czsc_strategy/tests/unit/test_position_sizing_research_equivalence.snapshot.pre_czsc10.json`
读取旧基准，路径由 `Path(__file__).resolve().parents[1]` 解析。实测：

| 破坏方式 | 实际行为 | 判定 |
|---|---|---|
| 删除 golden fixture | `FileNotFoundError: Pre-upgrade baseline fixture missing: ...` | fail-loud ✔ |
| golden fixture 写入非法 JSON | `json.JSONDecodeError` 直接抛出 | fail-loud ✔ |
| golden fixture 内容置为 `{}` | 不抛错，但章节仍渲染，旧值全部显示为 `null`（可见退化，非静默丢失） | 可接受，见"残留瑕疵" |
| golden fixture 内容改成与新 snapshot 完全相同（模拟"自我抵消"） | 章节照常渲染，新旧两列数值相同 —— 不会静默消失 | ✔ |
| 从仓库根目录（而非 `examples/czsc_strategy/`）执行 | 正常返回同样结果 | CWD 无关 ✔ |

代码中已无 `subprocess` / `git show HEAD:` / 裸 `except Exception: return {}`。

golden fixture 的**真实性**已独立核验（不是编造的）：把
`git show 2ab6f93ab^:examples/czsc_strategy/tests/unit/test_position_sizing_research_equivalence.snapshot.json`
（升级前的真 snapshot，2.1MB）与 fixture 逐字段比对，SC888/RB888 的
`total_trades`/`total_return_pct`/`sharpe_ratio`/`profit_factor`/`max_drawdown_pct`
及三个子策略的 `total_trades`/`win_rate` **全部浮点级完全相等**（MATCH=True）。
fixture 已被 git 跟踪，且 `git check-ignore` 无命中，不会被 `.gitignore` 吞掉。

### ② 行为差异报告正文 —— 已包含真实数字

`diagnostics/czsc_upgrade_behavior_diff_report.md`（300 行）第 "research-mode 基准位移
(真实策略级影响)" 节内联给出 SC888/RB888 两张指标表 + 两张子策略表：

- SC888：成交对数 27→25，total_return_pct 3.794100761153718→0.64648542541208，
  sharpe 0.8091974663759458→0.24200229290842856，profit_factor 1.85494→1.60322，
  max_drawdown 3.20274→2.66376；三买多头 4 笔/0.5 胜率 → 1 笔/0.0 胜率。
- RB888：成交对数 10→11，total_return_pct -1.69850→-0.07971，sharpe -1.20955→-0.07926，
  profit_factor 0.48599→0.94701，max_drawdown 2.49149→1.65413。

这些数值与我直接从两个 JSON 文件算出的 `_baseline_displacement()` 返回值逐位一致；
报告文本的表头、列序、字段命名与脚本 `main()` 中 427-465 行的渲染逻辑逐行吻合，
可确认为脚本生成而非手工誊抄。

### ③ CHANGELOG / 提交范围 —— 已修复

`c5cc1977f` 只触及 7 个文件：HANDOFF.md、czsc_strategy/CHANGELOG.md、VERSION、
czsc_upgrade_behavior_diff_report.md、czsc_upgrade_diff_report.py、
czsc_upgrade_failure_attribution.md、新增的 golden fixture —— **零 SimNow 文件**，
不再重演第 2 轮"版本号搭 SimNow 提交便车"的问题。VERSION=0.2.52，CHANGELOG 0.2.52 条目齐备。 <!-- synccheck:ignore -->
额外加分：历史上的 0.2.48 条目没有被悄悄改写，而是就地标注为 <!-- synccheck:ignore -->
"（生成机制存在缺陷，实际正确落地见 0.2.52）"——保留了错误记录，属诚实披露。 <!-- synccheck:ignore -->

### ④ 独立复跑的门禁（全部现场重跑，未沿用往轮数字）

| 门禁 | 本轮 review 实测 |
|---|---|
| `python tools/sync_check.py` | PASS（4.4.0），exit 0 |
| `python tools/sync_check.py --root examples/czsc_strategy` | PASS（0.2.52），exit 0 | <!-- synccheck:ignore -->
| `pytest examples/czsc_strategy/tests/unit -q -m "not realdb"` | **干净检出下无法收集**：24 collection errors（见下 N2） |
| 同上 `--continue-on-collection-errors` | 760 passed, 5 failed, 4 deselected, 4 xfailed, 24 errors |
| `pytest examples/czsc_strategy/tests/unit -q -m realdb` | **4 passed**, 769 deselected（256s） |
| 已删除导入路径（objects/enum/core/signals/svc/bar_generator/echarts_plot）真实 import | **0 处**（仅剩 docstring/注释中的历史引用） |
| `requirements.txt` | `czsc==1.0.0rc8`，精确 pin | <!-- synccheck:ignore -->
| 回滚隔离 | `a0d2e08e1` 仅改 `requirements.txt` 一行，可独立 revert ✔ |
| 第 2 轮以来是否删弱 RESEARCH-ONLY / fail-closed / 披露机制 | 无（`git diff 0f7109300 HEAD` 中无相关删除行） |

5 个 failed 全部为 SimNow 测试（`test_run_next_work_wrapper`、
`test_simnow_daily_brief_policy_sharing` ×2、`test_simnow_helper_boundaries` ×2），
**无一条与 czsc 升级相关**，与 dev 的归因一致。

### ⑤ 968 → 978 的调查结论：与 czsc 无关，且不可从提交状态复现

dev 把失败归因文档里的 `968 passed` 直接改成了 `978 passed`，未作解释。实测结论：

- `git diff 0f7109300 e3e5ae6e0 -- examples/czsc_strategy/tests/` 只有新增的 golden
  fixture JSON，**零个测试文件变动**；`grep -c "^def test_"` 在第 2 轮与第 3 轮提交状态下
  同为 **929**。
- 我把第 2 轮的 `tests/` + `diagnostics/` 检出到本 worktree 重跑，得到
  **760 passed, 5 failed, 24 errors**，与第 3 轮 HEAD 的结果**完全相同**。
- 因此 +10 完全来自 dev 所在共享主工作树中**未提交的并发 SimNow 改动**
  （`diagnostics/simnow_*.py` 中 12 个未跟踪模块 + 一批 ` M ` 状态的修改），
  与本次 czsc 升级毫无关系。

判定：**非缺陷，但属未披露的口径漂移**。978 这个数字本身不可复现，不应作为验收证据；
可复现的等价结论是"czsc 相关测试零失败，两轮提交状态测试面完全相同"。已在此记录，
避免该数字被后续文档继续引用。

### ⑥ N2（干净检出无法收集测试）—— 仍未解决，维持非阻塞

24 个 collection error 源自 12 个**从未提交**的 SimNow 辅助模块（`simnow_artifact_loader`、
`simnow_automation_policy`、`simnow_structured_access`、`simnow_20d_aggregate`、
`simnow_contract_map_meta`、`simnow_backfill_pending_kline`、`simnow_daily_brief_schema`、
`simnow_daily_brief_sections`、`simnow_daily_brief_default_summary`、
`simnow_ledger_summary_schema`、`simnow_risk_halt_decision`、`simnow_risk_halt_review`）。
更正第 2 轮 review 的措辞：这**不是 `.gitignore` 例外缺失**——`git check-ignore` 对这些路径
无命中，它们只是被 SimNow 会话创建后一直未 `git add`。属 SimNow 工作流卫生问题，
czsc 侧无法也不应在本任务内修复。dev 已在"已知未处理项"中如实披露，数字与我实测一致。
**建议作为独立任务处理**：把这 12 个模块提交，或给对应测试加 skip 保护。

### ⑦ 残留瑕疵（均不阻塞）

1. `czsc_upgrade_diff_report.py:428` 的 `if baseline_delta:` 守卫现已形同虚设（函数要么抛错、
   要么返回带键的字典）。唯一残留窗口：若 golden fixture 被替换成 `{}` 或缺 SC888/RB888 键，
   章节会以 `null → 数值` 渲染而不抛错。可见但不理想，建议后续加一条键完整性断言。
2. `OLD_UNBOUNDED_BI_COUNTS` 仍为硬编码常量（已在报告中标注为"独立探索性运行"，属诚实披露）。
3. `diagnostics/czsc_upgrade_fixtures/`（约 20MB）与 `czsc_upgrade_sample_report.html`（约 5MB）
   未纳入版本跟踪，review 无法在没有真实 SQLite 历史库和两个 venv 的情况下整体重生成报告；
   本轮改以"核对报告数值 vs 已提交 JSON + 核对渲染逻辑"的方式独立验证了最关键的基准位移章节。
4. 交接历史表缺少第 2 轮的 dev→review 与 review→dev 两行（front-matter 有记录，表格无）。
   属流水线记账瑕疵，本次 `handoff.py next` 会补上本轮行。

### 结论

第 2 轮的阻塞缺陷已被**根治**而非表面修补：披露机制现在既不会静默消失，也不会因 snapshot
刷新而自我抵消，且 golden fixture 的数值经与升级前真 snapshot 逐字段比对确认真实。
两处 sync_check 通过，realdb 4 passed，czsc 相关测试零失败，已删除导入路径清零，
requirements 精确 pin，回滚提交独立可 revert，无任何披露机制被削弱。
10 项原始问题中的第 10 项至此关闭。转 done。

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
| 2026-07-28 | kimi-code → codex | dev → review | czsc-1.0-upgrade review fixes: baseline displacement now uses committed golden fixture with fail-loud, behavior diff report includes SC888/RB888 strategy-level delta, VERSION/CHANGELOG updated for this dev round, both sync_check gates pass, unit tests 978 passed/4 xfailed (not-realdb) and 4 passed (realdb) |
| 2026-07-28 | codex → codex | review → done | Round-3 review PASS: the round-2 blocker is genuinely fixed. _baseline_displacement() now reads a committed, git-tracked golden fixture resolved from __file__ (CWD-independent) and fails loud; verified adversarially rather than by reading - deleting the fixture raises FileNotFoundError, corrupting it raises JSONDecodeError, and an old==new fixture still renders the section instead of vanishing; no bare except and no 'git show HEAD:' remain. The fixture's values were confirmed float-exact against the true pre-upgrade snapshot recovered from history (not fabricated). The behavior diff report now carries the SC888/RB888 strategy-level deltas inline (return 3.794 pct -> 0.646 pct, sharpe 0.809 -> 0.242, sanmai long 4 -> 1 trades), matching the script's render logic line for line. VERSION and CHANGELOG for this round land in a czsc-only seven-file commit with zero SimNow files, and the earlier false disclosure claim was annotated in place rather than silently rewritten. Gates re-run fresh in an isolated clean worktree: both sync_check gates PASS, realdb 4 passed, deleted czsc import paths zero, requirements pin exact, the rollback commit is a single isolated line, and no RESEARCH-ONLY or fail-closed mechanism was weakened. Investigated the not-realdb count drift: zero test-file changes between rounds and 929 test defs in both, and checking out the previous round's tests reproduces an identical 760 passed / 5 failed / 24 errors, so the increase comes solely from uncommitted concurrent SimNow work in the shared tree - a non-defect but an undisclosed metric drift, now recorded. N2 carries over unresolved and non-blocking: the 24 collection errors trace to 12 SimNow helper modules that were never git-added (not a gitignore gap - check-ignore is clean), and all 5 failures are SimNow-only with zero czsc-related failures. |
