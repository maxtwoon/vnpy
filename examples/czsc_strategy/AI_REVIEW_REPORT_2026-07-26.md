<!-- RESEARCH-ONLY / NOT PROMOTION EVIDENCE -->

# 审核报告：缠论期货 CTA 策略（czsc_strategy）

**审核对象**：D:\repo\vnpy\examples\czsc_strategy
**审核人**：AI股交易专家审核 Agent（ai-stock-trading-reviewer）
**审核标准版本**：2.4.0
**审核日期**：2026-07-26
**版本/快照**：VERSION 0.2.42（信号版本 V260615；审核时工作区有 36 个未提交 simnow 相关改动）
**证据定位规则**：定位使用 `D:\repo\vnpy\examples\czsc_strategy\<相对路径>:<行号>`；全库检索证据已在各问题条目中记录搜索根、命令与结果。
**材料索取记录**：状态：不适用；说明：被审对象全部材料明文可读，无需索取；SQLite 实库位于工作区外（`D:\BaiduNetdiskDownload\...`）未直接打开，已在 D5 标"未验证"。

> 审核方式说明：本次审核由 7 名维度审核员（只读 explore 子代理）并行取证，编排层做交叉去重、严重程度↔分数映射校验与总分复算。编排层复核中对 D9 原始评分做过一处强制映射修正（详见"三、各维度评分表"注）。

---

## 一、总体结论

- 综合评分：**68/100（C 及格）**（可评维度 10/10；结构性 N/A：无；证据不足/未验证：见"二、审核范围与局限"）
- 一句话结论：**工程纪律与诚实披露文化在同类研究代码中属上乘（防未来函数、污染证据自我降级、只读铁律代码级强制），但当前没有任何未触碰样本外的有效性通过记录，且术语体系（"确认"三义、自研中枢未声明差异）与组合层风控（无回撤熔断）存在实质短板——作为研究工程合格，作为策略有效性证据不成立。**
- 高危项/实盘前置警示：**无 🔴 项**（无任何维度命中"资金损失/虚假业绩/不可验证"级判据）。
- 致命项：**无**（无维度 ≤2 分，🔴 0 条）。
- 额外提示（非扣分项）：项目自我定位为 RESEARCH-ONLY，且 SimNow 前瞻观察 0/20 有效日——项目方自己的晋级门禁也未放行，本审核结论与项目自评一致。

---

## 二、审核范围与局限

- **审核方式**：静态审阅为主 + 部分运行验证。运行验证包括：D5 维度实跑 65 个相关单元测试全部通过（rollover/limit_halt/data_adapter/unparseable_rows 系列）；D3 维度用 `python -c` 直读 config.py 生效值与 README 逐项对账；D8 维度用 git 只读命令验证版本治理与凭据跟踪状态。**未运行完整回测、未跑全量测试套件。**
- **材料范围**：chan_strategy/ 全部源码（约 8000 行）、入口脚本、README/README.legacy/AGENTS/HANDOFF/CHANGELOG/VERSION/.synccheck.yml、tools/、tests/（存在性核查+部分实跑）、diagnostics/ 关键报告与配置、skill_build/ 参考文档、docs/design/、根目录散落脚本。
- **材料索取记录**：不适用（见页首）。
- **方法论材料缺失**：无（信号构建与组合构建材料均完整提供）。
- **未验证项**（逐条）：
  1. `python tools/sync_check.py` 未复验（审核环境缺 pyyaml）；CHANGELOG 声称开发环境 exit 0——未验证。
  2. 全量 pytest（780 条单测及 realdb 门禁）未实跑，仅 D5 相关 65 条实跑通过。
  3. SQLite 实库未直接打开：表结构、real_symbol 列、缺失率、NaN/异常价格未独立抽查（依赖 contract_adjustment_verification 事证）。
  4. czsc 第三方库内部是否存在后视修正，依赖项目自建 validate_no_repaint 间接背书，未独立复现；该检查自身声明不能证明底层库无修正（validation.py:188-190）。
  5. MACD 背驰口径在 EMA 预热期（<约 33 根）的信号漂移未实测。
  6. zhongshu 自研实现 vs czsc 库 ZS 对象的差异比对中，"czsc ZS"一侧未实际比对库实现（审核环境无 czsc 模块）。
  7. `_detect_transitions` 换月检测算法细节未逐行审读，其事后性偏差量级为定性判断。
  8. simnow 实时捕获端是否在所有 replay 路径统一应用 final_candidate_params，未完全验证。
  9. 涨跌停幅度与临时扩板窗口按其引用的交易所规则文本采信，未联网复核。
- **市场语境适配**：被审对象为**商品期货 CTA**，按适配矩阵执行：剔除 A 股 T+1、印花税、复权、退市项；替换/强化为合约连续化与换月规则、合约乘数与保证金、强平、夜盘归属、涨跌停板建模、滑点放大。D4 的基本面 point-in-time 子项结构性剔除（纯价格型策略无财务数据）；D4 容量项剔除（5 主力连续合约、低换手、流动性好）。

---

## 三、各维度评分表

| 维度 | 得分 | 评级 | 一句话依据（含"未验证"标注） |
|------|------|------|-----------|
| D1 信号构建与择时逻辑自洽性 | 7/10 | 良好 | 信号自洽、无循环论证、无未来泄漏、边界降级完备有测试锁定；🟠"次级别确认"名实不符封顶 7 |
| D2 组合构建、风险预算与风控一致性 | 6/10 | 及格 | 单笔层与极端行情 toolkit 上乘；命中 ≤6 锚定：组合回撤熔断缺失 + 默认路径无组合级约束 |
| D3 参数/阈值跨载体一致性 | 6/10 | 及格 | 关键阈值全链对账零不符；命中 ≤6 锚定：≥10 处 fallback 字面量重复定义（当前恰好一致，纯漂移风险）+ 死配置 |
| D4 回测/评估严谨性 | 7/10 | 良好 | 无前视设计、成本敏感性、walk-forward、诚实标注体系齐全；🟠无干净 OOS 通过证据封顶 7 |
| D5 数据假设处理 | 9/10 | 优秀 | splice/换月/涨跌停/夜盘均有"声明→代码→测试→报告"完整证据链，65 单测实跑通过；未达 10：极端换月跳空无压力复现 |
| D6 指标定义与术语统一 | 4/10 | 重大 | 命中 ≤4 锚定："确认"三义直接矛盾 + 中枢双口径，自研中枢未声明与标准差异 |
| D7 市场环境适配与声明 | 7/10 | 良好 | 结构级失效退出完整量化；策略级有效前提零声明、regime/ATR chop 机制默认关且无文档 |
| D8 可追溯性与单一真值源 | 6/10 | 及格 | 版本治理真实运转（git 证据充分）；命中 ≤6 锚定：核心风控阈值全库无取值依据（祖传参数）+ 根目录残留无治理 |
| D9 透明度与可审计性 | 7/10 | 良好 | 全明文、结构清晰、可独立复算；🟠本地明文真实凭据（example 含真实仿真账号+LLM key）封顶 7（编排层按强制映射由 8 修正为 7） |
| D10 合规与风险提示充分性 | 9/10 | 优秀 | 免责横幅门禁强制 155 篇 0 漏网、AST 级禁下单测试、零收益承诺措辞、LLM 产物 AI 标识完整 |
| **合计（归一化）** | **68/100** | **C** | Σ=68，可评 10 维，等权归一 |

> 注（编排层复核记录）：① D9 初评 8 分，因归属 D9 的 🟠 凭据问题触发强制映射"任一🟠→封顶 7"，修正为 7。② D1 的"次级别确认未实现"与 D3 的"confirm_freq 死配置"为同一根因的两面影响（信号语义 vs 参数生效性），跨维度分别引用已列明独立影响路径；且 D3 得分实际由 fallback 字面量锚定判据封顶 6，非同一证据重复封顶。③ score 字段问题在 D1（🟢）与 D6（🟠）均有发现，最终归 D6 一条（术语名实不符），D1 不重复计分。

---

## 四、问题清单（按严重程度排序）

### 🔴 高

无。

### 🟠 中（14 条）

**1.【D1+D3】"次级别确认"机制不存在：confirm_freq/base_freq 死配置，信号"确认"语义声明强于实现**
- 定位：`chan_strategy\config.py:12,14`；`README.md:25-32`；`chan_strategy\signals.py:288`；`chan_strategy\signals.py:137-156`（实际"确认"=同级别一根反向已确认笔 `_get_confirming_bi`）
- 证据：全库检索（根 `D:\repo\vnpy\examples\czsc_strategy`，Grep `base_freq|confirm_freq`）→ 仅 config 定义处，零代码消费方；引擎实际固定从 1 分钟合成 30 分钟/日线（`backtest_engine.py:437-451`、`run_chan_backtest.py:128` 硬编码 `freq="1"`）；README.md:32 却称其为"生产回测路径的真实配置"；signals.py:288 docstring 称"需要次级别确认才能变为'确认'"。项目自审 AUDIT_REPORT_2026-07-03.md M8 同结论。
- 影响：核心信号语义（"确认"）名实不符，读者按文档会高估信号过滤强度；用户改这两个配置不产生任何效果。
- 建议：删除两个死键并将 README 周期表改为只列 trade_freq/filter_freq（注明引擎固定载 1 分钟重采样）；或实现次级别确认并补测试。同时修正信号 docstring 的"次级别协同"表述。

**2.【D2】组合回撤熔断缺失（核心项）**
- 定位：`chan_strategy\config.py:159`（`daily_loss_limit_pct: 0.03` 为唯一组合级熔断）；`chan_strategy\portfolio_ledger.py:124,143-162`（日亏损限额每日复位）
- 证据：全库检索 `max_drawdown|drawdown_breaker|回撤熔断` → 生产代码中 max_drawdown 仅作事后报告指标（`backtest_engine.py:1021`；20% 回撤仅为 ex-post 目标门禁），无 in-replay 回撤熔断。
- 影响：连续阴跌时每天可各亏 3% 而无累计刹车；组合慢性失血无最后防线。
- 建议：PortfolioLedger 增加峰值权益跟踪与 max_drawdown_breaker_pct（如 10%）触发后的降杠杆/停用规则。

**3.【D2】默认 portfolio_risk="off" 路径无任何组合级约束，正式评估入口亦未启用组合层**
- 定位：`chan_strategy\portfolio_engine.py:468-474`（`_build_off_report` 自述"本报告不包含任何组合级日亏损限额/强制平仓保护"）；`chan_strategy\backtest_engine.py:72-85`（`formal_evaluation_config` 仅覆盖 5 项，不含 portfolio_risk）；`run_formal_evaluation.py:46`
- 影响：默认产物与正式评估产物均为"无组合风控"口径；5 标的各持 100 万独立假设的等权平均掩盖共享资金下的集中度与回撤形态。
- 建议：正式评估入口增加 portfolio_risk="on" 联合回放口径为必出报告，或并列两种口径差异。

**4.【D3】positions.py 以 fallback 字面量重复定义全部关键风控默认值，成本域以外无防漂移守卫**
- 定位：`chan_strategy\positions.py:359-366, 613-615, 1289-1290, 1383-1384, 1477-1478, 1554-1555, 1631-1632, 1710-1711`（如 `STRATEGY_CONFIG.get("stop_loss_1buy", 200)`）；唯一一致性审计 `diagnostics\audit_issue_diagnostics.py:612,627` 仅覆盖 commission/slippage 两键
- 影响：当前数值全一致（已逐项对账确认），不构成功能错误；但 ≥10 处重复定义，任何一处改动即静默漂移且测试不会发现。
- 建议：fallback 改为硬失败（直接索引 `STRATEGY_CONFIG[key]`），或将 M1 审计扩展到 stop_loss/timeout/trailing/pos 全键集并纳入 CI。

**5.【D4】最终候选无真正未触碰的样本外通过证据；全部历史 OOS 窗口被反复用于参数选择**
- 定位：`diagnostics\backtest_matrix_20220101_20260424.md:7`（自述窗口"repeatedly used for parameter selection…retained as negative / contaminated evidence only"）；`diagnostics\simnow_20d_promotion_decision.md:16-23`（observed_days 8/20、valid_observation_days 0/20、ready_to_expand False）；`diagnostics\audit_issue_diagnostics_2026-07-03.md:10-16`（H1：high_precision_weight 0.847 的门禁拟合指纹）；`diagnostics\platform_optimization_round1~9.md`
- 影响：九轮同窗口迭代优化+大量候选扫描使全部历史"样本外"实为受污染证据；当前不存在任何干净 OOS 通过记录，晋级完全依赖尚未完成的前瞻观察。
- 建议：维持现有"污染证据自我降级+前瞻窗口门禁"治理；在 SimNow 20 有效日完成前，任何文档不得把历史窗口数字表述为有效性证据（目前执行良好，需持续防回流）。

**6.【D6】"确认"一词三种互斥含义并存，两处定义直接矛盾**
- 定位：`chan_strategy\signals.py:288,308`（"确认需要次级别协同"）vs `signals.py:425-430`（同级别反向笔即输出"一买确认"）；`README.md:29`（confirm_freq"次级别确认周期"）；另有中枢"结构状态=已确认"（README:40）
- 影响：同一术语在信号值、周期配置、结构状态三处含义不同；同一文件内两处定义直接冲突。
- 建议：同级别反向笔确认改称"验证笔/确认笔"，"确认"保留给次级别协同；或在信号 docstring 显式区分。

**7.【D6】自研中枢构建未声明与缠论标准/czsc 库的差异，且入场与风控使用两种中枢口径**
- 定位：`chan_strategy\zhongshu.py:44-92`（全英文 docstring 仅称 "Shared Zhongshu construction helpers"；`max_bis=9` 封顶、`lookback=30` 截断无任何偏离声明）；`sell_signals.py:241`（风控 mode="segment"）vs `:274`（入场默认 mode="recent"）
- 影响：缠论标准中枢可持续延伸直到三类买卖点破坏，9 笔封顶+30 笔回看是实质语义偏离；"结构失效"退出依据的中枢与入场中枢不是同一个。AUDIT_REPORT_2026-07-03.md:87 已列为发现但代码侧无声明。
- 建议：在 zhongshu.py docstring 与 README 声明与标准定义的差异及理由（参照 signals.py:293-306 背驰声明的教科书级写法）；说明入场 recent/风控 segment 的取舍规则。

**8.【D6】score 字段名存实亡：宣称"0-100打分"，实际不参与任何匹配、仲裁或仓位**
- 定位：`chan_strategy\signals.py:4-9`（"score: 0-100打分"）；`chan_strategy\positions.py:208-213`（`is_match` 只比对前三段，score 段被忽略，Event 模式硬编码 `_0` 后缀）；`tests\unit\test_signal_contract.py:5-11`（测试锁定 score 不参与匹配）
- 影响：每个信号字符串携带看似排序权重的死字段，误导读者认为存在信号强度分层；任何"按 score 加权"的下游设计会静默落空。
- 建议：删除 score 段并改契约测试；或让 score 参与仲裁/仓位并声明语义。

**9.【D7】策略有效前提与失效环境零声明**
- 证据：全库检索（Grep `失效环境|失效判据|适用环境|有效前提|市场环境|市况`，范围 README/CHANGELOG/AGENTS/docs/design/RISK_NOTE）→ 0 命中。README 仅有通用风险提示。
- 影响：一买（左侧抄底）+三买（突破跟随）混合体系对趋势/波动环境有强依赖，使用者无从知晓策略环境边界。
- 建议：README 增加"适用前提与失效环境"节，引用 diagnostics\first_buy_environment_candidates 既有研究。

**10.【D7】市况级保护机制（regime router / ATR chop filter）默认关闭且无任何 markdown 文档**
- 定位：`chan_strategy\config.py:23,115`（`regime_model:"independent"`、`atr_chop_filter:"off"`）；`chan_strategy\positions.py:2031-2050`（router 实现存在且有测试）；全库检索 `regime_model|atr_chop_filter`（*.md）→ 0 命中；README:159-166 开关清单漏列这两项
- 影响：唯一针对"市况不适用"的保护在默认配置不生效且不可被发现；声明与实现脱节。
- 建议：补入 README 开关清单与 CHANGELOG，说明各档位环境含义与默认关闭理由。

**11.【D8】核心风控阈值无取值依据（祖传参数）**
- 定位：`chan_strategy\config.py:34-39,43-46,58-59,86-90`（止损 200/300/350BP、timeout 600/1000/1500、trailing 300/0.25、risk_per_trade 0.005——注释只解释"是什么"）
- 证据：全库（含仓库根 docs/design/ a33-a79 共 20+ 篇设计文档）Grep 相关键名与数值，无任何"为何是这个值"的记录，仅反复强调"与历史基线字节一致"。
- 影响：规则数值无法回溯到设计决策，后人改参无依据。
- 建议：补一节"参数沿革"：注明数值源自 A 股原型时期经验设定、未经期货样本优化（或附当时理由）。

**12.【D8】根目录散落开发残留无治理横幅、归属不明**
- 定位：`_patch_backtest.py~4.py`（一次性补丁脚本，改写 legacy 文件）、`_debug_zs.py`、`test_czsc_api.py`、`test_czsc_api2.py`、`test_second_buy_bug.py`、`test_second_buy_real_path.py`（测试生产代码却放在 tests/ 之外）、`inspect_db.py`、`backtesting_demo.ipynb`
- 影响：读者无法判断哪些是现行、哪些是残骸；两个真实回归测试不在文档化测试命令覆盖内，其维护状态形成歧义。A104 只给 6 个 legacy 脚本加了横幅，这批全部没有。
- 建议：删除或移入 diagnostics/archive/ 或补 LEGACY/ONE-SHOT 横幅；两个回归测试迁入 tests/unit/ 纳入门禁。

**13.【D9】example 配置文件含真实仿真账号+明文密码；本地存在真实 LLM API key**
- 定位：`diagnostics\simnow_connection_config.example.json:3-4`（与真实配置 `simnow_connection_config.json:3-4` 完全一致的真实值）；`skill_build\llm_eval_config.json:2`（真实 DeepSeek key，本报告不复述其值）
- 证据：经 git ls-files / check-ignore / log 验证三者均未被 git 跟踪、未入 git 历史——未构成公开泄露；但 example 文件职责是占位符，一旦打包分享或 `git add -f` 即泄露。
- 影响：本地凭据卫生缺口；example 文件名实不符是持续性陷阱。
- 建议：example 改占位符；SimNow 为仿真环境风险有限但建议改密一次；DeepSeek key 建议轮换并改用环境变量（llm_skill_eval.py:56 已支持 DEEPSEEK_API_KEY）。

**14.【D2→D3 移交已并入口径说明】研究/风险两模式单笔风险预算相差 2 倍且无说明**（严重度 🟢 升列提示，不重复计分）——research 模式实际单笔风险 0.2%/0.6%/1.05%（权重×止损），risk 模式名义预算 0.5%，无文档说明口径差异。

### 🟢 低（摘要，均已在各维度工作底稿中定位取证）

**信号与术语（D1/D6）**
15. 三买开仓 docstring 与实现不符（陈旧注释，`positions.py:1403-1406` vs `:1432-1441`）。
16. 背驰进入段方向不校验（`signals.py:293-306`）——声明与测试锁定完备，仅作教科书级声明的记录项；建议纳入术语表。
17. 信号层无预期换手与稳定性设计假设说明（全库 Grep 仅命中遗留 A 股脚本）。
18. `signal_zs_confirmation` 的"未确认"（score=40）分支不可达（`signals.py:394-403`，n_bis 恒 ≥3）。
19. 缠论核心术语无唯一定义出处；`skill_build\reference\缠论术语表.md` 是话术映射且 chan_strategy/ 无任何引用。
20. 双 get_all_signals 同名并存（声明充分但仍是活歧义；signals.py 侧已有 DeprecationWarning + AST 门禁，属残留提示）。
21. 分品种适配仅有研究产物，无策略级声明；trailing_overrides 依据的报告自标受污染（`config.py:74` 默认空，处理正确但意味着品种适配暂无结论）。

**组合与风控（D2）**
22. research 模式"仓位×止损"为隐式风险，无闭环断言（见 🟠14 提示条）。
23. 期货强平/维持保证金未建模，保证金率取交易所最低值（`config.py:163-164` 已声明 research-only）。
24. risk_parity 权重每 bar 重算、无换手/再平衡约束；符号掉线时等权归一化推高集中度（heat report 实例：AP888 权重 87.93%）。

**回测（D4）**
25. 滑点只按单边计入：往返成本 = 2×佣金 + 1×滑点（`positions.py:1073,1143,952`），每往返少计约 5bp；x2 敏感性测试（0.0014）已包络诚实口径（0.0012），影响温和。
26. 换月开窗门禁使用全窗口事后检测的换月拼接日期（`backtest_engine.py:528-554`），formal 结果轻微偏乐观；方向为保护性偏差，建议报告中声明事后性质。
27. `test_execution_timing.py` 名不副实：核心"T 信号→T+1 开盘成交"协议无直接回归测试，依赖代码走读背书。
28. 研究模式收益曲线不复利、恒定本金——已被 sizing_caveat+入口横幅+fail-closed 守卫治理，记录项。
29. "240分钟"映射 Freq.F120（`backtest_engine.py:900` 已注明仅元数据不影响信号），记录项。

**数据（D5，期货适配后）**
30. 涨跌停带宽基准价用"前收盘价"而非交易所规定的"前结算价"（`limit_config.py:106-138` vs 其引用的规则文本）；实测窗口 0 笔拒单，当前无实证影响。
31. 换月拼接边界处涨跌停带宽失去意义（AP888 换月跳空 +61.9% 实例），持仓跨越换月日平仓可能被误拒顺延一根 bar。
32. enforce 触发条件为 bar 区间"触板即拒"（保守方向），与报告 methodology 措辞"fills that occur at the band"不符。
33. `contract_specs` 的 `tick` 字段生产代码零引用，成交价未按最小变动价位取整。
34. 时间序列空洞（缺 bar）无缺失率阈值 fail-closed；不可解析行只跳过计数（目前由诊断层监控兜底）。
35. 交易日历推导为启发式（"8-15 点有 bar"），纯夜盘日会坍缩（当前 5 合约均有日盘，未触发）。
36. `RISK_NOTE_888_SPLICE.md:16` "No gating of live opens" 表述与 A76 换月门控落地现状不符（文档过时，兼具 D8 属性）。

**治理与透明度（D3/D8/D9）**
37. `total_capital` 在 chan_strategy 内无消费方，与 `initial_capital` 重复定义（`config.py:18` vs `:183`）。
38. README.legacy.md 存在第二套完全不同阈值——隔离声明清晰、无生效路径，仅提示；建议 legacy 文件头部加"参数已废止"横幅。
39. SimNow 观察路径生效参数与 config.py 基线不同（已文档化），README 缺"基线 vs 候选"对照表。
40. `data_cache/` 9 个已废止 A 股 CSV 仍在 git 跟踪中。
41. `diagnostics/` 509 个文件扁平堆积，archive 区名存实亡（仅 1 次归档）。
42. README.md:122 文件结构图列举已删除的 `utils.py`（0.2.41 A103 整文件删除）。
43. 硬编码个人网盘路径（`config.py:5-8` 可用环境变量覆盖；`inspect_db.py:9` 不可覆盖）。
44. `__pycache__` 残留 11 处（含 legacy 脚本编译缓存），整洁度提示。

---

## 五、亮点（值得保留的好设计）

1. **防未来函数的信号输入纪律严格且成文**：`_get_confirmed_bi_list`（signals.py:33-57）在 finished_bis 之上再做 last_bi_extend 防御性剔除，docstring 明确"绝对不允许回退到 c.bi_list"；全量 vs 增量回放等价性验证（validation.py:403-421）。
2. **无前视的聚合时间戳设计**：高周期 bar 时间戳=最后一根构成 bar（data_adapter.py:190），`daily_bars[idx].dt <= bar.dt` 才注入，test_daily_no_lookahead / test_4h_no_lookahead 双向锁定。
3. **成交时点模型真实做到信号 T、成交 T+1**：pending_signals 机制 + execution_price 全链路使用，走读未发现前视路径。
4. **模式标签 + fail-closed 守卫**：`_compute_mode_label`/`assert_not_research_baseline` 从制度上阻止 RESEARCH_BASELINE 被当作生产证据——同类研究代码中少有的诚实设计。
5. **污染证据自我降级标注体系**：全部受污染产物统一携带 RESEARCH-ONLY 横幅与 `is_promotion_evidence: False` 元数据；portfolio_heat_report 在真正未触碰窗口如实报告负收益（-0.90%/-1.50%）。
6. **稳健性验证矩阵完整**：成本 x1.5/x2 敏感性+门禁、品种集邻域稳定性扫描（1/4 通过率如实展示）、主导品种与极端交易贡献审计（top3 占 65.43% 如实披露）、半年度 walk-forward、绩效数字不离谱（OOS 夏普 0.69 跑输买入持有并如实判 False）。
7. **多空隔离与信号互斥天然成立**：enable_short=False 时空头 Position 根本不创建；一买/一卖确认条件互斥，同刻不可能双向确认。
8. **极端行情 toolkit 完整且溯源**：涨跌停三档（off/aware/enforce）+逐品种交易所规则出处 URL，临时扩板窗口标注"未经独立核实，待人工确认"；换月检测→排除窗→开仓门控→审计计数全链路，检测失败 fail-closed raise。
9. **组合强平无前视处理严谨**：A90 联合回放中 lagging symbol 用自有 tick 的 bar.close 强平，注释明确"that would be lookahead"，有 no-lookahead 测试。
10. **只读铁律有代码级强制**：AST 级扫描禁用 send_order/cancel_order/buy(/sell( 等（多份测试），SimNow 监测器检测到下单动作会 halt 并要求人工复核；全库 grep 确认 diagnostics/ 无任何下单引用。
11. **合规横幅由门禁强制且零漏网**：155 篇 diagnostics 报告仅 8 篇无横幅且全部命中显式豁免清单；零收益承诺措辞（仅有的 "guaranteed" 均为反向免责："NOT a guaranteed max loss"）。
12. **版本治理真实运转**：VERSION+CHANGELOG+代码+HANDOFF 同一提交（git 抽查实证），.synccheck.yml 门禁覆盖 changelog 必备条目、横幅、handoff 状态机、配置新鲜度。
13. **背驰简化声明是教科书级**（signals.py:293-306）：非权威声明+选取规则+锁定测试名+未来修正路径四要素齐全——zhongshu 应照此办理。
14. **废弃信号三重治理**：DeprecationWarning + AST 级生产路径禁入 + README 双处声明。

---

## 六、修复优先级建议（Top 7）

1. **【D4】守住前瞻观察纪律**：SimNow 20 有效日完成前，任何文档不得把历史窗口数字表述为有效性证据；这是项目唯一通往"干净 OOS"的路径，也是当前最重要的一条。
2. **【D2】补组合回撤熔断 + 正式评估启用 portfolio_risk="on" 联合回放口径**：日亏损限额每日复位挡不住慢性失血；正式评估产物目前是无组合风控口径。
3. **【D6】术语治理三件套**：统一"确认"语义（同级别改称"验证笔"）、zhongshu.py 补标准差异声明（参照背驰声明写法）、处置 score 死字段（删除或赋予真实语义）。
4. **【D1+D3】清理死配置与重复定义**：删 base_freq/confirm_freq/total_capital 并修正 README 周期表；positions.py fallback 字面量改硬失败，M1 一致性审计扩展到全键集。
5. **【D9】凭据卫生**：simnow_connection_config.example.json 改占位符、DeepSeek key 轮换并改走环境变量；一次性动作，风险即时消除。
6. **【D8】残留清理与参数沿革**：根目录 _patch/_debug/散落 test 脚本删除或归档加横幅，两个真实回归测试迁入 tests/unit/；config.py 补"参数沿革"说明数值来源。
7. **【D7】补市场环境声明**：README 增加"适用前提与失效环境"节（可引用 first_buy_environment_candidates 研究）；regime_model/atr_chop_filter 补入开关清单与 CHANGELOG。

---

> 免责声明：本报告为策略工程质量审核，非投资建议；不对被审策略的实盘收益做任何承诺。本报告本身亦为研究产物，不构成对该项目盈利能力的证明。
