# czsc 库升级至 1.0（maxtwoon/czsc master）

## 状态说明（重要，先读）

本文档由 claude-code 在 design 角色下产出，但**尚未挂接进 sync-guardian 的 handoff 流水线**。原计划是把
`.synccheck.yml` 的 `handoff` 段从单文件模式（`file: HANDOFF.md`）切到多任务并行模式（`dir: handoffs/`），
让本任务（`czsc-1.0-upgrade`）与当时正在 dev 阶段的 A105（HTML 回测报告）互不阻塞地并行推进。

实际执行后发现：这个仓库的根目录是**多个 agent 会话共享的同一份工作树**（不是每个任务用独立 worktree/分支
隔离）。当时 A105 的自动化流水线（`handoff.py run` 循环，dev→review 阶段）在同一工作树里看到了本任务未提交
的 `.synccheck.yml`/`handoffs/` 改动，把它们判定为与 A105 无关的 scope creep，自动 revert 掉了（见
`.handoff_run.log` 2026-07-27T01:27:57 条目："Out-of-scope handoff-governance changes ... were reverted by
claude-code before this transition"）。这个判断是对的——本任务确实不该混进 A105 的 dev 产出里。

**结论**：多任务并行模式的迁移与本任务的正式 `handoffs/czsc-1.0-upgrade.md` 创建，推迟到 A105 完全走到
`done`（当前在 review 阶段）之后再做，避免共享工作树下的自动化流水线互相踩踏。这与用户对"排序问题"给出的
决定一致（见下方"决定记录"）。在此之前，本文档作为独立设计产物存在，不依赖 handoff 状态机。

## 背景与目标

用户要求：详细分析 `https://github.com/maxtwoon/czsc/tree/master`，制定方案，把 `chan_strategy/` 依赖的
`czsc` 库从当前 pin 的 `0.9.51` 升级到"最新 1.0 版"。

`chan_strategy/` 是 `examples/czsc_strategy/` 下的期货 CTA 研究策略，其信号生成（一买/二买/三买及镜像卖点、
背驰、中枢）全部构建在 `czsc.CZSC`/`czsc.objects.RawBar`/`Direction`/`Freq` 等对象之上（见
`examples/czsc_strategy/AI_REVIEW_REPORT_2026-07-26.md` 与 `chan_strategy/zhongshu.py` 对该依赖面的既有
记录）。升级 czsc 库直接影响策略的核心结构判定，不是普通的依赖版本 bump。

## 调研方法（不是只读 changelog）

除了读 GitHub 仓库页面、`pyproject.toml`、`CHANGELOG.md`，还做了两项动手验证（结果见下）：

1. 在独立 venv（`pip install czsc==1.0.0rc8`，不影响本仓库现有环境）里实际 `import czsc` 并用 `.pyi`
   桩文件核对真实构造函数签名与属性面，而不是照抄文档字符串。
2. 用同一段固定随机种子生成的合成 30 分钟 K 线，分别在当前 pin 的 `czsc==0.9.51`（系统 Python，纯 Python
   实现）和 `czsc==1.0.0rc8`（独立 venv，Rust 实现）里各跑一遍 `CZSC(bars)`，逐笔 (`bi_list`)、逐分型
   (`fx_list`) 对比输出是否一致。

## 核心发现

### 1. 这不是一次常规版本升级，是缠论核心从 Python 到 Rust 的重写

`maxtwoon/czsc` 是 `waditu/czsc`（原作者 zengbin93）的 fork；从仓库页面看不出 fork 相对上游有独立于上游的
自有 patch。1.0 系列 RC 实际是**上游作者自己**发布到 PyPI 的（PyPI 项目 `czsc` 的维护者仍是 `zengbin93`）。

`CHANGELOG.md` 的 `1.0.0-rc.1` 条目记录的破坏性变更：

- 删除纯 Python 缠论核心实现，改用 Rust（通过 PyO3 暴露为 `czsc._native`）；
- 删除 `czsc.core` 模块，`CZSC`/`FX`/`BI` 等对象改由 Rust 实现，导入路径从 `czsc.core import CZSC` 变为
  `from czsc import CZSC`；
- 信号函数从 Python 迁移至 Rust，删除 `czsc.signals/` Python 命名空间；
- 删除 `czsc.svc`（Streamlit 组件包，约 4800 行）；
- 删除 `czsc.utils.bar_generator` 等工具模块。

`pyproject.toml` 证实构建系统改为 `maturin`（PyO3 native extension，manifest 在
`crates/czsc-python/Cargo.toml`），新增运行时依赖 `polars`、`scipy`、`statsmodels`、`wbt>=0.2.1`
（未知包，需要下一棒单独查一下这是什么、是否与本仓库/vnpy 已有依赖冲突）、`typer`；移除了 `scikit-learn`
（上游 2026-05 起要求用户自行安装）。Python 版本要求 `>=3.10`。

**已验证：PyPI 上有为 Windows 预编译的 wheel**（`pip install czsc==1.0.0rc8` 在独立 venv 里直接成功，
不需要本机装 Rust/Cargo 工具链去源码编译）。

### 2. PyPI 上还没有正式 1.0.0 稳定版

`https://pypi.org/project/czsc/#history` 显示：当前最新**稳定**版本是 `0.10.12`（2026-03-09）；1.0 系列
目前只有 RC——`1.0.0rc5`（05-18）、`1.0.0rc7`（05-20）、`1.0.0rc8`（05-29，最新）。仓库自己的
`CHANGELOG.md` 显示 rc.2~rc.5 之间发生过多次"紧急重发"（CI 版本号抽取脚本 bug、build.rs 编译问题等），
且 rc.8 之后还有一条 `[Unreleased]` 记录（`CZSC_MIN_BI_LEN` 环境变量真正作用于 Rust 笔逻辑）——说明这条线
还在活跃变动中，不是一个已经稳定下来的截面。

**GitHub Releases 页面本身是空的**（"There aren't any releases here"）——rc 系列是直接发到 PyPI/crates.io
的，没有对应的 GitHub Release 条目，仓库层面看不到版本历史，必须去 PyPI 查。

### 3. 顶层 API 兼容面：属性名基本保留，但导入路径大面积搬迁

用 `czsc/_native/__init__.pyi` 核对（1.0.0rc8 实测）：

**保留**（chan_strategy 直接依赖的属性/方法，逐一核对过，与当前 0.9.51 语义一致）：
- 顶层 `from czsc import CZSC, RawBar, Freq, Direction, Mark, ZS, FakeBI, BI, FX, Operate, resample_bars`
  全部可用；
- `CZSC.bi_list` / `CZSC.fx_list` / `CZSC.finished_bis` / `CZSC.bars_raw` / `CZSC.update(bar)` —— pyi
  文档字符串明确标注"与 czsc 库兼容"；
- `BI.direction` / `.high` / `.low` / `.sdt` / `.edt` / `.fx_a` / `.fx_b` / `.power` 全部保留；
- `FX.mark` / `.dt` / `.high` / `.low` 全部保留；
- `Freq` 新增了 `F240` 成员（之前 `backtest_engine.py:_freq_name_to_czsc_freq` 因为 czsc 没有 `F240`
  只能把"240分钟"映射到 `Freq.F120` 并在注释里说明"仅作为元数据，不影响信号"——升级后这个历史小缺陷可以
  顺手修掉，改映射到真正的 `Freq.F240`）；
- `CZSC` 对象新增内置 `to_echarts()` / `to_plotly()` / `open_in_browser()` 方法——**可能可以简化甚至替代**
  A105 里手写的图表拼装逻辑（见下方"与 A105 的交叉影响"），但输出格式是否支持中枢 markArea/买卖点叠加还
  没有验证过，需要单独调研，不能假设直接能用。

**删除/搬迁**（实测确认，`ModuleNotFoundError`）：`czsc.objects`、`czsc.enum`、`czsc.core`、
`czsc.signals`、`czsc.svc`、`czsc.utils.bar_generator`、`czsc.utils.echarts_plot`。全部需要改成从顶层
`czsc` 命名空间导入。

**构造函数签名变化**（实测，非文档推测）：
- `RawBar(freq=...)` 现在**必须**传 `Freq` 枚举实例，传字符串会直接 `TypeError`（之前 0.9.51 是否容忍
  字符串未逐一验证，但本仓库生产路径已经全部传枚举，见下）；
- `CZSC(bars=...)` 关键字参数改名为 `CZSC(bars_raw=...)`；位置参数 `CZSC(bars)` 不受影响。

**当前代码里谁用到了会破的路径**（`grep -rn "from czsc" chan_strategy/*.py`）：

| 文件 | 用到的已删除路径 | 影响 |
|---|---|---|
| `backtest_engine.py`、`data_adapter.py`、`positions.py`、`sell_signals.py`、`signals.py`、`validation.py` | `czsc.objects`（RawBar/Freq/Direction） | 改成从顶层 `czsc` 导入，机械替换，6 个文件 |
| `html_report.py`（A105，尚未合并） | `czsc.enum`（Mark/Operate）、`czsc.utils.echarts_plot.kline_pro` | 见下"与 A105 的交叉影响" |
| `test_czsc_api.py` / `test_czsc_api2.py`（根目录 ONE-SHOT 探索脚本，已有横幅标注非生产代码） | `CZSC(bars=bars)` 关键字调用 | 低优先级，顺手改 |

生产回测路径（`backtest_engine.py`/`validation.py`/`data_adapter.py`）对 `CZSC(...)` 全部用位置参数调用、
对 `RawBar(freq=...)` 全部传 `Freq` 枚举（`_freq_name_to_czsc_freq` 返回类型标注即为 `Freq`）——这两处破坏
性变更对生产代码实际影响是 0，只影响两个已标注 ONE-SHOT 的探索脚本。

### 4. 关键风险：笔（bi）构造算法本身有实测差异，不只是 API 搬家

这是本次调研里最重要的发现，直接决定了这次升级不能只做"改导入路径就完事"的机械迁移。

用固定随机种子生成 400 根合成 30 分钟 K 线，同一份数据分别喂给 0.9.51（当前 pin）和 1.0.0rc8（目标），
结果：

- **分型 (`fx_list`) 逐字节完全一致**（98 个分型，dt/mark/high/low 全部相同）；
- **笔 (`bi_list`) 不一致**：0.9.51 产生 32 笔，1.0.0rc8 产生 30 笔。定位到第一处分歧（index 19 附近）：
  旧版本连续产出 3 笔（`Up 02:30→04:00`、`Down 04:00→05:00`、`Up 05:00→12:00`），新版本把这 3 笔合并成
  1 笔（`Up 02:30→12:00`，high/low 覆盖前 3 笔的并集）。
- 两个版本的 `czsc.envs.get_min_bi_len()` / `get_max_bi_num()` 默认值完全一致（`6` / `50`），说明差异
  不是来自配置默认值变了，是笔合并规则本身在 Rust 重写后有实质性不同（且 changelog 里 `[Unreleased]`
  条目提到 `CZSC_MIN_BI_LEN` 环境变量"真正作用于 Rust 笔逻辑"，暗示这块逻辑本身还在被上游继续调整）。

分型不变、笔的数量和边界变了，意味着：`chan_strategy/zhongshu.py::build_zhongshu_from_bis` 的输入
（`bi_list`）会变，进而所有基于笔/中枢窗口判定的买卖点信号（一买/二买/三买及镜像卖点、背驰）都可能在同一
份历史数据上给出不同结果。**这不是"升级完跑一下测试通过就行"的事，需要专门的行为回归对比，见下方 Phase 3。**

（这一发现也从侧面印证了 `AI_REVIEW_REPORT_2026-07-26.md` 未验证项 #4 的判断——"czsc 第三方库内部是否
存在后视修正，依赖项目自建 validate_no_repaint 间接背书，未独立复现"——第三方库版本之间行为不一致是真实存在
的风险，不是审慎过度。）

### 5. 与 A105（HTML 回测报告）的交叉影响

A105（当前 review 阶段，kimi-code 完成 dev、待 codex 审）的 `html_report.py` 直接依赖
`czsc.utils.echarts_plot.kline_pro` 和 `czsc.enum.{Mark,Operate}`——两者在 1.0 里都被删除/搬迁。如果在
A105 落地之前升级 czsc，A105 的 dev 产出会直接编译不过。

## 决定记录（与用户确认过，2026-07-27）

1. **目标版本**：固定 pin 到 `czsc==1.0.0rc8`（不是浮动的 `>=1.0.0rc0`），不追新 rc、不等正式 1.0.0
   稳定版——理由：changelog 显示 rc 之间发生过多次紧急重发，浮动 pin 会牺牲研究场景要求的可复现性；等
   正式稳定版时间不确定，用户选择现在就锁定一个具体 RC 作为升级目标，以后上游真正发布 1.0.0 时再单独
   评估是否重新升级。
2. **安装来源**：直接 `pip install czsc==1.0.0rc8`（从 PyPI），不从 `maxtwoon/czsc` 的 git 仓库装——
   理由：PyPI 上的 1.0.0rc8 就是上游作者自己发布的同一份东西，带 Windows 预编译 wheel，不需要本机装
   Rust 工具链；改从 fork 的 git 仓库装除非能确认这个 fork 相对上游有独立 patch，否则只会多一层没有
   必要的复杂度（且需要本地 Rust 编译）。目前没有证据表明 `maxtwoon/czsc` 有偏离上游的改动。
3. **与 A105 的排序**：等 A105 完全 `done` 之后再启动 czsc 升级的 dev 阶段——理由：避免共享工作树下两个
   任务互相破坏对方产出（见本文档开头"状态说明"里实际发生的那次 revert 事件）；也避免 A105 的
   `kline_pro` 依赖被升级过程提前废掉。

## 迁移方案（分阶段，供 dev 阶段执行）

> 以下各阶段是 dev 角色接手后的执行顺序建议，本 design 阶段不实现代码。

### Phase 0 — 前置条件确认（dev 阶段开始时）

- 确认 A105 已经 `done`（`python tools/handoff.py status`）。
- 确认此时 `chan_strategy/html_report.py` 里对 `czsc.utils.echarts_plot.kline_pro` 的调用方式（A105
  合并后的真实代码，不是本文档写时看到的设计稿），因为 Phase 2 要基于合并后的真实实现改。

### Phase 1 — 机械导入路径迁移

- `czsc.objects` → 顶层 `czsc`（6 个文件：`backtest_engine.py`、`data_adapter.py`、`positions.py`、
  `sell_signals.py`、`signals.py`、`validation.py`，以及 `tests/conftest.py` 和所有 `tests/unit/*.py`
  里 `from czsc.objects import ...` 的地方）。
- `czsc.enum` → 顶层 `czsc`（`html_report.py`，A105 合并后的实际路径）。
- `CZSC(bars=bars)` → `CZSC(bars_raw=bars)`（`test_czsc_api.py`、`test_czsc_api2.py`）。
- `examples/czsc_strategy/requirements.txt` 里 `czsc==0.9.51` 改为 `czsc==1.0.0rc8`。
- 这一步做完后，仅靠 `python -c "import chan_strategy.backtest_engine"` 之类的导入自测就能筛出遗漏的
  旧路径，不需要跑测试。

### Phase 2 — `czsc.utils.echarts_plot.kline_pro` 替代方案

`kline_pro` 在 1.0 里完全不存在了（`czsc.utils.plotting` 子模块的 `.pyi` 桩显示 `__all__` 为空，没有
替代的绘图工具函数）。需要在这一步做出选择，二选一，dev 阶段调研后决定：

- **方案 A（保守）**：把 A105 当时依赖的 `kline_pro` 实现原地 vendor 一份进 `chan_strategy/`
  （从 0.9.51 的源码复制出对应函数，改成本仓库自己维护），行为完全不变，只是不再依赖上游导出。
- **方案 B（利用新特性）**：改用 `CZSC.to_echarts()` / `.to_plotly()` 内置方法作为图表基座，看是否能
  通过其现有接口叠加中枢 markArea 和买卖点标记（A105 设计文档里这两项是在 `kline_pro` 输出之上做的
  自定义叠加，不确定 `to_echarts()`/`to_plotly()` 是否暴露了同等的可扩展点）——如果调研后发现不支持，
  退回方案 A。
- 这一步的产出必须包含：A105 现有的图表相关单测（`test_html_report.py`）在新方案下重跑通过，且人工生成
  一份示例 HTML 确认视觉效果与升级前一致或有明确说明的差异。

### Phase 3 — 行为回归验证（不可省略的关键 gate）

鉴于第 4 节已经在合成数据上证实笔构造算法有实质性差异，这一步不是"跑一下现有测试"就够：

1. **全量测试套件**：`python -m pytest examples/czsc_strategy/tests/unit -q -m "not realdb"`，逐一确认
   失败原因（预期会有失败——测试锁定的具体笔/中枢边界值大概率要跟着算法变化调整，不是全部都是升级引入的
   bug，需要逐条甄别）。
2. **专门的新旧版本对比脚本**（design 阶段没有实现，dev 阶段新增，建议放
   `diagnostics/czsc_upgrade_bi_diff.py`）：拿真实历史数据（`chan_strategy/config.py` 里配置的 5 个
   期货连续合约，`SQLITE_DB_PATH` 指向的真实库），分别用 0.9.51 和 1.0.0rc8 构建 `CZSC` 对象，输出
   `bi_list`/`fx_list` 数量与边界的逐笔 diff、以及下游 `build_zhongshu_from_bis` 产出的中枢数量差异，
   量化到"总笔数变化 X%，边界完全一致的笔占比 Y%"这个级别，不能只说"能跑通"。
   - 需要能在同一台机器上跑两个 czsc 版本——可以像本 design 阶段一样借助独立 venv，或者把 0.9.51 的
     结果作为一份预先跑好的固定 golden fixture 存下来再升级依赖后对比（后者更适合长期留在仓库里当
     回归测试）。
3. **信号层面的对比**：不只对比 czsc 原始笔/分型，还要对比 `chan_strategy/signals.py` 和
   `sell_signals.py` 产出的最终买卖点信号（一买/二买/三买/背驰）在同一份历史窗口下升级前后是否一致，
   给出具体的信号触发次数/时间点差异统计。
4. 本阶段产出必须写入报告（带 `<!-- RESEARCH-ONLY / NOT PROMOTION EVIDENCE -->` 横幅，仓库既有约定），
   诚实记录差异幅度，不能把"升级后测试能跑"包装成"升级后策略行为不变"。

### Phase 4 — 依赖与环境

- 检查新增运行时依赖（`polars`、`scipy`、`statsmodels`、`wbt>=0.2.1`、`typer`）是否与
  `examples/czsc_strategy/requirements.txt` 或 vnpy 主仓库既有依赖版本冲突；`wbt` 这个包目前来源未知，
  需要单独查一下是什么、体积多大、是否有额外系统依赖。
- 确认 Python 版本要求 `>=3.10` 与当前开发/CI 环境兼容（预期没问题，仓库 `AGENTS.md` 记录支持
  3.10–3.13）。
- 记录实际使用的安装命令（`pip install czsc==1.0.0rc8`）与来源（PyPI），确保可复现。

### Phase 5 — 文档与版本治理

- `README.md` 若有提及 czsc 版本号的地方一并更新（目前未见明确提及具体版本号的段落，需 dev 阶段
  确认）。
- `chan_strategy/zhongshu.py` 现有的"自研中枢构造与 czsc 标准/`czsc.ZS` 差异"声明（2026-07-26 审核后
  补充）保持不变——`zhongshu.py` 本来就不消费 `czsc.ZS`，这次升级不影响那条声明的准确性，不需要改。
- 按仓库既有单一真相纪律：本次改动会触达 `chan_strategy/config.py` 吗？如果只改依赖版本和导入路径，
  不触达 `STRATEGY_CONFIG`/`BACKTEST_CONFIG`，`project_version_freshness` 门禁不会触发，但仍建议主动
  bump `VERSION` + `CHANGELOG.md` 一条，说明这是一次有行为差异的依赖升级（不是纯内部重构）。

### Phase 6 — 回滚预案

- 升级完成前，`czsc==0.9.51` 保持可以随时重新 pin 回去的状态（`requirements.txt` 改动应该是可以整段
  revert 的独立提交，不要跟 Phase 1 的导入路径改动混在一个不可分割的大改动里——如果 Phase 3 的行为对比
  发现差异不可接受，需要能只回滚依赖版本而不必连带回滚所有代码整理）。
- 鉴于目标版本本身是 pre-release（RC），在真正的 SimNow 前瞻观察通过之前，不应该把这次升级当作"已验证
  可用"对待——这条已经是仓库既有的研究纪律（对照 `diagnostics/simnow_20d_promotion_decision.md` 的
  晋级门禁），这里只是重申它同样适用于依赖升级本身。

## 验收标准（供 review 阶段逐条核对）

- [ ] `czsc.objects`/`czsc.enum` 等已删除路径在全仓库范围内清零（`grep -rn "from czsc.objects\|from czsc.enum\|from czsc.core\|from czsc.signals\|from czsc.svc\|czsc.utils.echarts_plot\|czsc.utils.bar_generator"`
      在 `chan_strategy/`、`tests/`、根目录脚本里没有命中）。
- [ ] `requirements.txt` 的 `czsc` 行精确 pin 到 `1.0.0rc8`，不是浮动版本号。
- [ ] Phase 2 的 `kline_pro` 替代方案已选定并落地，A105 相关单测通过，有一份人工生成的示例 HTML 佐证。
- [ ] Phase 3 的新旧版本行为对比报告存在（`diagnostics/` 下带 RESEARCH-ONLY 横幅），量化了笔/中枢/买卖点
      信号在真实历史数据上的差异幅度，不是空泛地说"通过"。
- [ ] 全量单测套件（`pytest examples/czsc_strategy/tests/unit -q -m "not realdb"`）跑过一遍，任何新增
      失败都有明确归因（是笔算法差异导致的预期变化，还是真实回归 bug），不能笼统略过。
- [ ] `python tools/sync_check.py`（根目录与 `examples/czsc_strategy` 两处）均通过。
- [ ] VERSION/CHANGELOG 按 Phase 5 要求更新。
- [ ] `czsc==0.9.51` 的回滚路径在 PR/commit 历史里是独立可 revert 的一步，不与其他改动纠缠。
- [ ] 本次升级不删除/削弱任何既有的 RESEARCH-ONLY、fail-closed、诚实披露机制（对照
      `AI_REVIEW_REPORT_2026-07-26.md` 亮点小节列的既有设计）。

## 边界（明确不做什么）

- 不在本任务里实现"线段 (XD/duan)"结构——这与 A105 的既有边界一致，`czsc` 1.0 是否新增了 duan 相关能力
  本次调研没有专门核实，留给需要时单独评估。
- 不在本任务里把 `chan_strategy/zhongshu.py` 的自研中枢实现换成 `czsc.ZS`——两者语义本来就不同
  （`zhongshu.py` docstring 已有声明），升级 czsc 版本不改变这个既有设计决定。
- 不追新 rc 或等正式 1.0.0（见"决定记录"第 1 条），本任务的验收范围就是精确升到 `1.0.0rc8`。

## 给下一棒（dev）的说明

1. 开工前务必先跑 `python tools/handoff.py status` 确认 A105 已经是 `done`——如果还没有，先不要动
   `requirements.txt` 或任何 `czsc` 导入路径，等着。
2. Phase 3 的行为回归对比是本任务里工作量最大、也是最不能跳过的一步；如果时间预算紧张，优先把这部分做
   扎实，而不是优先把 Phase 1 的机械改名做得多快——机械改名风险很低，Phase 3 的证据缺失风险很高（会让
   审核方无法判断这次升级是否安全，参照 `AI_REVIEW_REPORT_2026-07-26.md` 对"无干净 OOS 通过证据"的
   评分逻辑，同样的诚实标准适用于这里）。
3. 独立 venv 里核对新版本 API 的具体做法（供复现）：
   ```
   python -m venv <临时目录>/czsc10_probe
   <临时目录>/czsc10_probe/Scripts/pip install --quiet czsc==1.0.0rc8
   ```
   然后用 `<临时目录>/czsc10_probe/Scripts/python` 单独跑对比脚本，不会污染本仓库现有环境（本 design
   阶段就是这么做的，验证过 Windows 预编译 wheel 可以直接装，不需要 Rust 工具链）。
4. 如果发现 `maxtwoon/czsc` 相对 `waditu/czsc`/PyPI 发布版确实有独立 patch（本次调研没有找到证据，但
   没有做逐 commit 比对，不能 100% 排除），需要回来跟用户确认是否要改用"决定记录"第 2 条以外的安装
   来源——这会牵动是否需要本机 Rust 工具链等一系列额外前置条件。
