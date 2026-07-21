# AGENTS.md — czsc_strategy 诊断工作流协作规则

## 完成定义（Definition of Done）

每个改动 = 代码 + 版本（若对外可见）bump（`VERSION`）+ `CHANGELOG.md` 一条 + 相关文档更新，
**同一提交内完成**，并跑 `python tools/sync_check.py`（在本目录执行）通过。

铁律（沿用 A 系列基线）：诊断/工具一律只读——不发送委托、不调交易接口、不改策略参数与买卖信号；
输出不得包含 password/auth_code/api_key/account_id 等敏感字段；不得把诊断结果包装成盈利能力证明。

## 测试验证守则（realdb 提醒）

默认验收命令 `pytest tests/unit -q -m "not realdb"` 会**静默跳过**所有 `@pytest.mark.realdb`
测试（如 research 模式等价性门禁 `test_position_sizing_research_equivalence.py`）。因此：
任何触及 `chan_strategy/positions.py`、`chan_strategy/backtest_engine.py` 报告生成
（`generate_report()`）或 research 模式仓位逻辑的改动，其 Manual Verification 必须额外包含一次
`python -m pytest tests/unit -m realdb -q` 的实跑输出，不能只跑 `-m "not realdb"`。

## 多 agent 协作与交接

本工作流由多个 agent 分阶段协作，**HANDOFF.md 是跨 agent 上下文的单一真相**：
每个 agent 开工前只读 HANDOFF.md 和其中 deliverables 指向的产物，不依赖、也无法看到上一个 agent 的会话记录。

### 角色与阶段（stage 状态机）

```
design ──→ dev ──→ review ──→ done
  ↑__________________│ （审核不通过：退回 design 或 dev）
```

| 阶段 | 承担 agent | 职责 | 出口产物 |
|------|-----------|------|----------|
| design | claude-cowork | 方案设计：设计文档 + **验收标准** | docs/design/<task>.md |
| dev | code-agent | 按设计文档开发；偏离设计须写入 HANDOFF 决策记录 | 代码 + 自测 + changelog 条目 |
| review | claude-cowork | 审核代码与设计的一致性、按验收标准逐条验 | 审核结论；不通过则问题清单写入 HANDOFF |

### 交接如何触发

交接一律通过驱动器执行，不手改 front matter（驱动器是事务式的：先写入、再跑门禁、不过即回滚）：

- **agent 自触发**：每个 agent 完成本阶段职责后，收尾动作固定为
  `python tools/handoff.py next --summary "<本阶段做了什么>"`（在本目录执行）。
- **人工触发**：同一命令人也可以跑；审核打回用
  `python tools/handoff.py reject --to <design|dev> --reason "<原因>"`。
- 查看状态：`python tools/handoff.py status`。

### 交接的定义（Handoff DoD）——换棒时必须在同一提交内完成

1. 本阶段产物已提交，HANDOFF `deliverables` 指向的路径全部可达；
2. front matter 更新：`stage` 推进、`owner` 改为下一棒、`updated` 改为当日；
3. **重写**"给下一棒的说明"（面向下一棒的完整上下文，不是追加流水账）；
4. "交接历史"表追加一行；
5. `python tools/sync_check.py` 通过（handoff 门禁会拦：字段缺失、stage 非法、owner 与阶段不匹配、产物断链）。

### 各角色额外守则

- **claude-cowork（设计）**：验收标准必须可判定（能勾选通过/不通过），这是 review 阶段的合同。
- **code-agent（开发）**：只按设计文档开发。发现设计有问题，小偏离记入决策记录，大偏离把 stage 退回 design 并说明原因——不要静默改设计。
- **claude-cowork（审核）**：只认 HANDOFF 里的验收标准 + 设计文档，逐条给结论。不通过时问题清单写入"给下一棒的说明"，stage 退回并把 owner 改回 code-agent。
