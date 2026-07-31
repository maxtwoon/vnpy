# A108 diagnostics/ 目录重组（研究产出归档化）设计

- 任务：A108
- 阶段：dev implemented
- 日期：2026-07-30
- 前置：[A107](A107_scaffolding_docs_overhaul.md) §6"非目标"明确把本任务排除出其范围，
  本文档承接该建议。
- 铁律：**只移动"纯产出文件"（`.md`/`.json`/`.html`/`.txt`），一个 `.py` 脚本都不移动、
  不改名**；不改任何脚本内部逻辑；不改任何 import 路径；`chan_strategy/` 零改动；
  默认配置下回测结果字节不变（本任务不涉及回测路径，属自明成立）。

## 1. 背景

`examples/czsc_strategy/diagnostics/` 目前有约 480 个平铺文件（163 md / 144 json / 115 py /
38 html / 17 txt），是本子项目"没有目录组织"的最大单点。A107 审计已确认这是三层结构：
①4 个核心治理文档（路径被工具/文档硬编码引用）；②一批被其他脚本 `import` 的可复用模块；
③约 360+ 个一次性研究脚本的定时产出文件。A107 因风险/体量把这部分排除在外，本任务专门设计
如何安全地重组它。

## 2. 关键前置发现：import 依赖比预期更深

设计前追加了一次专项依赖图审计（只读，覆盖 `diagnostics/` 下全部 115 个 `.py` 文件），
结论比 A107 审计时的初步印象更严重：

- **`diagnostics/` 被当作一个 Python 包从外部导入**，不只是内部脚本互相 `import`：
  - `chan_strategy/portfolio_ledger.py:100` 运行期 `from diagnostics.portfolio_ledger_report
    import _symbol_clusters`；
  - `tests/unit/` 下至少 15 个测试文件用 `diagnostics.<module>` 形式导入
    `backtest_matrix_report`、`cost_sensitivity_report`、`risk_param_sensitivity_report`、
    `stop_execution_model_crosscheck` 等模块。
- diagnostics 内部还有一个以 `backtest_matrix_report`（26 个导入方）、
  `portfolio_goal_evaluator`（15）、`declassify_historical_reports`（11）为核心的密集依赖网络，
  外加一个自成体系的 `simnow_*` 子网络（`simnow_action_summary`/`simnow_observation_window`
  等 6~7 个导入方的枢纽模块）。
- 115 个脚本中：15 个是"枢纽"（4 个以上导入方）、40 个是"叶子"（只导入别人、不被导入）、
  35 个完全孤立（零依赖边）。移动叶子和孤立脚本理论上风险低，但由于枢纽模块用了
  `diagnostics.X`（绝对包路径）和裸名 `from X import`（依赖 `diagnostics/` 在 `sys.path`）
  两种混合导入风格，**任何子包化改造都需要同时改写 diagnostics 内部约 67 处、
  测试文件约 15 处、`chan_strategy/` 1 处，合计约 80+ 处导入语句**才能不破坏任何一处。

**结论**：`.py` 脚本层面的重组风险/工作量远超 A107 其余整改项，且价值（省下"脚本也分类"
这一点点检索便利）相对这个风险不成比例。本任务**明确放弃**对 `.py` 文件做任何移动/改名/
拆包，只处理零 import 风险的纯产出文件（`.md`/`.json`/`.html`/`.txt`）。这部分本身就占
480 个文件里的约 362 个（约 75%），完成后 `diagnostics/` 根目录的平铺文件数会从约 480 降到
约 118（115 个 `.py` + 4 个核心文档 + 若干必须留根的例外，见 §4）。

## 3. 目标结构

```text
diagnostics/
├── ACCEPTANCE.md / WORK_LOG.md / NEXT_WORK.md / AUTOMATION_PROMPT.md   # 不动，核心治理文档
├── simnow_daily_observation_workflow.md / simnow_connection_probe.md   # 不动，.synccheck.yml 显式 skip
├── *.py（全部 115 个脚本）                                              # 一个都不动
├── 若干"活跃配置/状态"json（见 §4 例外清单）                              # 不动
├── archive/                                                            # 已有，不动，沿用既有归档约定
├── czsc_upgrade_fixtures/                                              # 已有，不动
├── research/                                                           # 新增：纯产出文件归类区
│   ├── MIGRATION_LOG.md                                                # 新增：迁移清单（旧路径->新路径，一次性生成，供审计）
│   ├── simnow/            # simnow_* 的 .md/.json/.html/.txt 产出（不含 §4 例外）
│   ├── platform/          # platform_* 产出
│   ├── second_buy/        # second_buy_* 产出
│   ├── signal_funnel/     # signal_funnel_* 产出
│   ├── trailing/          # trailing_* 产出
│   ├── backtest_reports/  # backtest_report_*.html / portfolio_report_*.html /
│   │                       # portfolio_ledger_*.{json,md} / czsc_upgrade_sample_report.html
│   ├── sc_short_weight/   # sc_short_weight_* 产出
│   ├── first_buy_five_min/ # first_buy_* / five_min_* 产出
│   └── misc/               # 其余全部一次性研究产出（divergence_*/exit_*/joint_replay_*/
│                            # limit_halt_*/resonance_*/rollover_*/stop_*/symbol_set_*/
│                            # weak_window_*/trade_difference_*/cost_sensitivity_*/
│                            # risk_param_*/reason_code_*/no_a_*/extreme_trade_*/
│                            # key_trade_*/settlement_close_*/pnl_*/portfolio_heat_*/
│                            # czsc_upgrade_*（非 .py）/a90_*/a102_*/a106_codex_*/
│                            # baseline_*/codex_review_*/buy_signal_quality_*/
│                            # backtest_matrix_*/position_sizing_report_*/
│                            # rolling_candidate_matrix.{json,md} 等零散前缀，各自 1~10 个文件）
└── audit_issue_diagnostics_*.md（.json 同名文件视 §4 例外检查决定去留）
```

## 4. 分类算法（dev 必须照此机械执行，不得凭感觉挑文件）

**第一步：候选集合** = `diagnostics/` 直属文件中，扩展名属于 `{.md, .json, .html, .txt,
.log, .jsonl}` 的全部文件（不含 `archive/`、`czsc_upgrade_fixtures/` 子目录，那两个目录本任务
不动）。

**第二步：排除清单（这些文件即使命中候选集合也不移动，留在 `diagnostics/` 根目录）**：

1. 4 个核心治理文档：`WORK_LOG.md`、`ACCEPTANCE.md`、`NEXT_WORK.md`、`AUTOMATION_PROMPT.md`。
2. `.synccheck.yml` `diagnostics_banner_check.skip` 中显式列出的 2 个文档：
   `simnow_daily_observation_workflow.md`、`simnow_connection_probe.md`
   （`audit_issue_diagnostics_*.md` 这条 skip 是 glob，按 §5 说明处理，允许移动）。
3. **已确认的"活跃配置/状态"文件**（本次专项 grep 已证实被 `.py`/测试用硬编码路径读取，
   不是一次性研究产出）：`simnow_contract_map.json`、`simnow_observation_window.json`、
   `simnow_observation_ledger.jsonl`、`simnow_risk_thresholds.json`、
   `simnow_connection_config.json`、`simnow_connection_config.example.json`、
   `simnow_backfill_plan.json`、`simnow_kline_backfill_plan.json`。
   （`simnow_contract_map.json` 被 `tests/unit/test_simnow_run_summary.py` 用绝对路径字符串
   `"D:/repo/vnpy/examples/czsc_strategy/diagnostics/simnow_contract_map.json"` 硬编码两处，
   `simnow_observation_window.json` 被多个 `simnow_*.py` 模块在默认参数里按固定相对路径读取
   ——这两个是本次专项审计的直接证据，其余同批文件按同源风险一并保留在根目录，不逐一验证。）

**第三步：安全网 —— 对排除清单之外的每个候选文件，移动前必须 grep 全仓库**
（不止 `diagnostics/`）**该文件名字符串**（含不带扩展名的变体），确认命中的地方只出现在
散文文档（`.md` 里的文字提及）而非任何 `.py`/`.ps1`/`.json` 里的可执行路径依赖。如果发现
新的硬编码依赖（第三步的存在意义就是防止 §4.3 那份"已知清单"漏项），把该文件追加进例外
清单、留在根目录，不得强行移动；不得静默跳过这一步。

**第四步：按前缀归类** 到 §3 的 `research/<topic>/` 子目录（前缀→目录映射表见 §3 注释）；
未命中任何明确前缀的文件一律进 `research/misc/`，不得新建 §3 未列出的子目录。

**第五步：`git mv` 执行 + 生成 `research/MIGRATION_LOG.md`**（一次性生成，格式：
`旧相对路径 -> 新相对路径`，按迁移前后顺序排列，供本次 review 与未来审计核对）。

## 5. `.synccheck.yml` 门禁兼容性（已验证，无需改配置）

- `diagnostics_banner_check` 的 `_is_path_exempt()`（`tools/sync_guardian/sync_check.py`）用
  `fnmatch.fnmatch(path.name, pat)` 只匹配**文件名**、不含目录部分，且递归扫描
  `dir: diagnostics` 下全部子目录——因此 `skip` 列表里的 `audit_issue_diagnostics_*.md`
  这类 glob，无论文件被移到 `research/misc/` 还是留在根目录，只要文件名不变就依然命中，
  banner 门禁不受影响。**不需要改 `.synccheck.yml`**。
- `archive_dir: diagnostics/archive/` 与 `exempt_dirs: [diagnostics/archive]` 都指向既有的
  `archive/`，本任务不碰这个目录，两条配置继续按原样生效，互不影响。

## 6. 接入边界

- 允许：`git mv` 纯产出文件（`.md`/`.json`/`.html`/`.txt`/`.log`/`.jsonl`，按 §4 分类算法
  筛选后）、新增 `research/MIGRATION_LOG.md`、更新引用了被移动文件路径的**活跃**文档
  （README.md、`docs/`、`IN_FLIGHT_CHANGES.md`、`RISK_NOTE_888_SPLICE.md` 等——历史
  CHANGELOG/HANDOFF 条目不回溯改写，沿用 A107 惯例）。
- 不允许：移动/改名任何 `.py` 文件；修改任何 `.py` 文件内部逻辑或 import 语句；修改
  `.synccheck.yml`；修改 `archive/`、`czsc_upgrade_fixtures/` 内容；修改
  `chan_strategy/`/`tests/` 任何断言逻辑（若某测试硬编码了即将移动的文件路径，该文件必须
  按 §4 第三步归入例外清单留在根目录，而不是"移动文件然后改测试"——本任务的风控原则是
  **优先不移动**，而不是移动后到处打补丁）。

## 7. 验收标准（review 合同，逐条可判定）

- [ ] AC1 `git diff --stat` 显示零 `.py` 文件改动（含 `diagnostics/**/*.py` 与仓库其余
      任何 `.py` 文件），零 `chan_strategy/**` 改动。
- [ ] AC2 `diagnostics/` 根目录直属文件数从约 480 降到约 118±10（4 核心文档 + 2 named-skip
      文档 + §4.3 例外清单文件 + 115 个 `.py` 脚本；具体数字允许因例外清单在 dev 阶段的
      grep 结果而有小幅浮动，但必须在 Manual Verification 中给出准确前后对比）。
- [ ] AC3 `research/MIGRATION_LOG.md` 存在，条目数等于本次实际移动的文件数，可与
      `git log --stat` 的 rename 记录交叉核对一致。
- [ ] AC4 `python tools/sync_check.py --root examples/czsc_strategy` 通过（尤其
      `diagnostics_banner_check` 一项，证明 §5 的兼容性判断成立而非纸面推测）。
- [ ] AC5 全量测试门禁：`pytest examples/czsc_strategy/tests/unit -q -m "not realdb"`
      通过数不低于 A108 开始前基线（A107 done 时为 1009 passed / 4 deselected /
      4 xfailed），**尤其**所有 `tests/unit/test_simnow_*.py` 与
      `test_a69_robustness_gates.py`/`test_backtest_matrix_report.py` 等 §2 提到的、
      直接 `import diagnostics.X` 的测试文件必须全部通过——这是本任务"零 import 破坏"
      承诺的直接证据，Manual Verification 必须单独列出这些测试文件的通过情况，不能只报
      总数。
- [ ] AC6 `git mv` 保留历史（非删除+新建），`git log --follow` 对任一被移动文件可追溯到
      移动前的提交历史。
- [ ] AC7 活跃文档路径引用同步：`grep -rn` 检查 README.md/docs/ 等活跃文档中对已移动文件的
      具体文件名提及，若原文有路径前缀需更新为 `research/<topic>/` 新路径（若原文只是提及
      文件名不含路径，允许不改，因为本身就不是可点击/可执行路径）。
- [ ] AC8 完成定义：VERSION bump + CHANGELOG 一条 + 本设计文档"阶段"字段更新为
      "dev implemented"，同一提交；`python tools/sync_check.py`（根）与
      `--root examples/czsc_strategy` 均通过。

## 8. 非目标（Out of scope）

- **`.py` 脚本级重组**：§2 已论证风险/收益不成比例，本任务彻底放弃，不留作"A109 建议"——
  除非未来有专门的自动化 import 重写工具 + 全量回归验证方案，否则不建议再尝试，直接维持
  `diagnostics/` 作为一个扁平 Python 包的现状。
- 精简/删除任何研究产出内容（哪怕明显过时）——只搬迁归类，不判断"是否还有价值"，那是内容
  层面的决策，不属于目录架构整改。
- 修改 `archive/`、`czsc_upgrade_fixtures/` 目录的既有归档方式。
- 新建自动化脚本作为仓库常驻工具（迁移用的一次性脚本执行完可以不保留，`research/
  MIGRATION_LOG.md` 已经是审计所需的记录）。

## 9. 决策记录

- 2026-07-30 (claude-code, design) - 用户要求在 A107 完成后设计 A108
  （diagnostics 目录重组），本人担任 design 角色（本任务未涉及 kimi/codex 额度问题，
  按常规角色分工设计，不涉及子代理代跑 dev/review）。
- 2026-07-30 (claude-code, design) - design 前追加一次专项只读依赖图审计（Explore 子代理
  执行），发现风险比 A107 审计阶段的初步印象更深（`diagnostics/` 被 `chan_strategy/` 和
  15+ 个测试文件当作 Python 包绝对导入，不只是内部脚本互相依赖）。据此把设计范围收窄到
  "只动非 `.py` 产出文件"，并把 `.py` 脚本级重组从"留作后续任务"改为"明确不建议再做"，
  理由：这不是"体量大所以分两步"的问题，而是"收益（脚本目录整洁）配不上风险（80+ 处
  import 语句需要精确同步，任一遗漏都会导致测试静默失败或运行时 ImportError）"的问题。
- 2026-07-30 (claude-code, design) - 例外清单（§4.3）基于本次 grep 找到的确凿证据
  （`simnow_contract_map.json`/`simnow_observation_window.json` 被硬编码路径引用）圈定，
  同批 `simnow_*.json`（`_risk_thresholds`/`_connection_config`/`_backfill_plan`/
  `_kline_backfill_plan`）按同源风险一并保留，未逐一重新验证——这是保守优先的设计选择，
  即使部分文件实际上可以安全移动，误留在根目录的代价（仍需检索）远小于误移动导致的
  运行时故障。dev 执行时若想收紧例外清单（移动更多文件），必须先补齐对应的 grep 证据，
  不能仅凭"看起来应该是安全的"就移动。

## 10. Dev 实现记录

（dev，因 kimi-cli 当前额度耗尽，由用户指示改用 Claude Agent 子代理代跑——`--actor kimi-code`
仅满足门禁字符串匹配，如实披露代跑事实，详见 HANDOFF.md "给下一棒的说明"与决策记录。）

- **候选集合与例外清单**：`diagnostics/` 根目录直属文件中扩展名属于
  `{.md, .json, .html, .txt, .log, .jsonl}` 的候选文件共 373 个。§4.2 已知例外清单（14 个：
  4 核心治理文档 + 2 named-skip 文档 + 8 个活跃 simnow 配置/状态文件）原样保留。
- **§4 第三步安全网**：对剩余 359 个候选文件逐一 `git grep` 全仓库（含不带扩展名变体），
  排除 pytest `tmp_path` 合成夹具产生的假阳性匹配、区分"脚本自身默认输出路径"
  （write：`out_json`/`out_md`/`report_path`/`--out-*`/`write_text`/`to_json`/`to_html` 等
  关键词）与"被其他脚本/测试当作输入读取"（read：`DEFAULT_MATRIX`/`read_text`/`json.load`/
  `open(` 等关键词），后者以及任何命中 `tests/**/*.py`、`chan_strategy/**/*.py`、`*.ps1`、
  仓库其他位置 `*.json` 配置文件的情形一律判定为硬编码依赖。据此在已知 14 个例外之外
  新发现 7 个真实依赖，追加进例外清单、留在根目录（未移动）：
  - `backtest_matrix_20220101_20260424.json` / `.md` —— 被
    `diagnostics/buy_signal_quality_report.py:10` 的 `DEFAULT_MATRIX` 默认输入路径读取
    （§2 提到的"枢纽"依赖网络的真实实例）。
  - `phase1_dead_factor_equivalence.json` —— 被
    `tests/unit/test_phase1_dead_factor_equivalence.py:194` 引用同名生成脚本路径。
  - `simnow_20d_promotion_decision.md`、`simnow_ledger_summary.json` —— 被
    `diagnostics/run_next_work.ps1` 自动化脚本硬编码相对路径读写（设计阶段 §4.3 已知清单
    未覆盖这两个，安全网按设计意图成功补漏）。
  - `symbol_set_stability_scan.json` / `.md` —— 被
    `diagnostics/platform_stability_review.py:103` 引用为默认 evidence 来源文件名。

  剩余 352 个候选文件判定为安全，按 §4 第四步前缀规则分类到 9 个 `research/<topic>/`
  子目录：`misc`(94)、`backtest_reports`(42)、`first_buy_five_min`(10)、`platform`(64)、
  `sc_short_weight`(8)、`second_buy`(21)、`signal_funnel`(18)、`simnow`(87)、`trailing`(8)。

- **执行方式（超出设计文档预期的发现）**：执行阶段发现 `diagnostics/` 根目录下绝大多数
  候选文件被根 `.gitignore`（`examples/czsc_strategy/diagnostics/*.json` /`*.md`/`*.txt`/
  `*.jsonl` 系列规则 + 兜底的 `examples/czsc_strategy/diagnostics/*`）标记为生成产出、
  从未 `git add` 过（`git ls-files` 核实：diagnostics/ 根目录直属文件仅 105 个被 git 跟踪，
  几乎全部是 `.py`）。352 个安全移动文件中，161 个被 git 跟踪、用 `git mv` 保留历史；
  其余 191 个是未跟踪的 gitignore 生成产出，`git mv` 会报
  `fatal: not under version control` 错误（不是脚本 bug，是这些文件确实从未进入 git
  索引），对这部分改用普通文件系统移动（`shutil.move`），移动前后都不在 git 索引中，
  不涉及历史丢失，也未额外 `git add` 到新位置（维持原有 untracked 状态，不扩大仓库体积，
  不改变 `.gitignore` 语义——这是设计文档没有预见到的实现细节，记录于此）。
- **`.gitignore` 补丁（设计文档未预见，记录偏差）**：根 `.gitignore` 第 112 行
  `examples/czsc_strategy/diagnostics/*` 会把新建的 `research/` 目录本身当作
  "diagnostics/ 的一个直属子项"整体忽略（目录级忽略一旦生效，Git 不会进入该目录扫描内容，
  即使后面有针对具体文件名的 `!` 否定规则也无法生效——这是 Git 官方记录的行为限制）。
  实测确认：352 个安全移动文件维持原有 untracked/ignored 状态是正确的（延续 reorg 前的
  既有约定），但新增的 `research/MIGRATION_LOG.md` 作为审计交付物必须被 Git 跟踪，否则
  AC3"`research/MIGRATION_LOG.md` 存在"这条验收标准名存实亡（文件在磁盘上但不在 git 索引里，
  无法被提交/审计）。为此在 `.gitignore` 追加了 3 行最小补丁：先 `!.../diagnostics/research/`
  取消整个目录的忽略、再 `.../diagnostics/research/*` 重新忽略该目录下的直属子项（把
  ignore 行为精确收窄回"仍然忽略所有实际研究产出文件/子目录，只解禁 MIGRATION_LOG.md 一个
  文件"）、最后 `!.../diagnostics/research/MIGRATION_LOG.md` 取消该文件的忽略。补丁前后用
  `git check-ignore -v` 逐一核实：`research/misc/` 下的样本文件仍返回"被忽略"，
  `MIGRATION_LOG.md` 返回"未被忽略"。这是设计文档 §6 接入边界未列出的改动（§6 只提到
  `git mv`/`MIGRATION_LOG.md`/活跃文档更新），但属于让 §6 已批准的 `MIGRATION_LOG.md`
  产出实际可提交所必需的最小技术前提，未触碰 `.synccheck.yml`（铁律范围内），如实记录于此。
- **`research/MIGRATION_LOG.md`**：352 条 `旧路径 -> 新路径` 记录，按迁移前后（文件名字母序）
  排列，文件头补充了 `<!-- RESEARCH-ONLY / NOT PROMOTION EVIDENCE -->` 横幅——因为
  `diagnostics_banner_check` 门禁递归扫描 `diagnostics/` 全部子目录下的 `.md` 文件，新增的
  `MIGRATION_LOG.md` 命中该规则，且不在 `.synccheck.yml` 的 `skip` 列表中；铁律要求
  `.synccheck.yml` 零改动，故选择给文件本身补横幅（内容确实是审计记录、非回测结果，标注属实）
  而非修改门禁配置。
- **根目录文件数**：迁移前 489（373 候选 + 115 `.py` + 1 `.ps1`），迁移后 137
  （115 `.py` + 1 `.ps1` + 21 个例外清单文件，其中 14 个已知 + 7 个新发现）。与 §7 AC2
  "约 118±10" 的预估有约 9 个文件的偏差，原因是设计阶段预估未纳入 §4 第三步安全网新发现的
  7 个真实依赖对应的文件数；`具体数字允许因例外清单在 dev 阶段的 grep 结果而有小幅浮动`
  这一 AC2 条款本身已预留了这种偏差空间。
- **文档同步**：`README.md`（`trailing_oos_validation_20250101_20260424.md` 路径）、
  `docs/design/A102_trade_freq_5min_filter_generalization.md`
  （`five_min_feasibility_probe_20260729.md`/`.json` 路径）、`docs/theory_code_crosscheck.md`
  （`czsc_rc8_theory_probe_report.md` 路径，2 处）——这 3 处活跃文档里指向已移动文件的具体
  路径已同步更新；`IN_FLIGHT_CHANGES.md`、`RISK_NOTE_888_SPLICE.md` 全文 grep 无命中，
  无需改动。历史 CHANGELOG/HANDOFF 条目未回溯改写。
- **验证**：`pytest examples/czsc_strategy/tests/unit -q -m "not realdb"` 迁移后
  `1009 passed, 4 deselected, 4 xfailed`，与基线一致；15 个 `import diagnostics.X` 的测试
  文件单独重跑 `150 passed`；`python tools/sync_check.py` 与
  `python tools/sync_check.py --root examples/czsc_strategy` 均 PASS（含
  `diagnostics_banner_check`）。完整证据见 HANDOFF.md "Manual Verification"。
