---
task: A32 审核问题数据接入 + A31 复核瑕疵修复
stage: design            # design → dev → review → done；审核退回可回 design/dev
owner: claude-cowork     # 当前接棒者：claude-cowork | code-agent
updated: 2026-07-03
deliverables:            # 本阶段产物（相对本目录路径，sync_check 会校验存在）
  - docs/design/A32_audit_issue_data_feed.md
blockers: []
---

## 背景与目标

A31 建成 H1/H2/H3/H4/M1 只读诊断骨架（已过外部复核），但报告全为 unavailable/unknown——有秤没称过东西。
A32：喂真实数据，让五个问题各得一个有数字、可判定的结论；同时修掉复核发现的 3 个瑕疵（H1 状态语义、H2 单位护栏、MD 敏感扫描）。
不做：不修问题本身、不改策略/信号/风控、不下单、不为好看筛样本。详见设计文档。

## 验收标准

- [ ] W1a：params 非空且干净 → H1 status == `clean`；params 为空 → `unknown`；有可疑 → `detected`。有测试区分三态
- [ ] W1b：任一 `abs(pnl_pct) > 1.0` 时 `analyze_stop_loss_overshoot` raise ValueError（报错信息含两种单位说明）。有测试
- [ ] W1c：`write_markdown_report` 写盘前执行 `contains_sensitive_data`，命中即 raise。有测试
- [ ] W2：`diagnostics/extractors/` 4 个抽取脚本存在，全部只读；源缺失时输出 `source_missing` + tried 路径，退出码 0
- [ ] W2：`inputs/*.json` 符合设计文档 schema；H2 的 pnl_pct 为小数口径
- [ ] W3：新日期诊断报告生成，含 `inputs_manifest`（每 issue 的输入路径与记录数）
- [ ] 结果判定：H1 ∈ {clean, detected}；H2/H3/M1 各自 status ≠ unavailable，**或** WORK_LOG 记录了 tried 路径证明数据源确实不存在
- [ ] H4：以真实 --db-path 运行，status ∈ {found, unknown}（附 evidence 或空清单）
- [ ] 报告无 "GOAL PASSED"、无敏感字段（既有测试扩展覆盖 extractors 的无交易调用扫描）
- [ ] 全量 pytest 通过；`python tools/sync_check.py` 通过；VERSION bump 0.2.0 + CHANGELOG/NEXT_WORK/WORK_LOG 同提交更新

## 给下一棒的说明

（dev = code-agent 接棒时必读）

0. **先执行两条命令验证门禁与交接**（design 会话无 Python 执行环境，此两步移交给你）：
   在 `examples/czsc_strategy` 目录跑 `python tools/sync_check.py`（应 PASS；故意把 CHANGELOG 版本改错应 FAIL——验证门禁有牙齿后还原），
   然后跑 `python tools/handoff.py next --summary "设计完成: A32"` 完成 design→dev 交接后再开工。
1. 入口：设计文档 `docs/design/A32_audit_issue_data_feed.md`，按 W1→W2→W3 顺序施工；W1 三个瑕疵修复最先做（有独立测试可锁定）。
2. 关键约束：extractor 是**新增只读层**，不 import 策略运行时、不执行回测；数据源缺失诚实落盘 `source_missing`，禁止伪造或补默认值。
3. 已知的坑：
   - H2 单位护栏（W1b）是破坏性变更，改完后先跑 A31 既有 14 个测试，`test_analyze_stop_loss_overshoot_computes_overshoot` 用的是小数口径，应仍通过；
   - H1 状态枚举加 `clean` 后，`test_build_audit_issue_report_contains_all_issues` 里 H1 的断言需要同步（params 提供且含 0.847 → detected，不受影响；但新增 clean 分支要有新测试）；
   - 报告文件名带日期，重跑同日会覆盖——设计上接受。
4. 为什么这么设计：诊断与抽取分层（extractor 只产 JSON、诊断只吃 JSON），是为了让"数据从哪来"与"怎么判定"可独立审计；`inputs_manifest` 是给 review 阶段对账用的，别省。
5. 完成定义见 AGENTS.md；收尾固定跑 `python tools/handoff.py next --summary "<摘要>"`，门禁不过先修再交，不要 --no-gate。

## 决策记录

- 2026-07-03 · 治理范围定为 `examples/czsc_strategy` 子目录（非 vnpy 仓库根） · 理由：本工作流自治（NEXT_WORK/WORK_LOG/ACCEPTANCE 均在此），不污染上游仓库。
- 2026-07-03 · 版本单一真相选 `VERSION` 纯文本文件，起始 0.1.0 · 理由：子项目无包管理文件；A 系列任务号不是版本。
- 2026-07-03 · owners 定为 design/review=claude-cowork，dev=code-agent · 理由：与现行人机流水线一致（Cowork 设计+审核，code agent 开发）。

## 交接历史

| 日期 | 从 → 到 | 阶段变化 | 摘要 |
|------|---------|----------|------|
| 2026-07-03 | 人 → claude-cowork | → design | A32 任务启动（依据 A31 外部复核结论） |
