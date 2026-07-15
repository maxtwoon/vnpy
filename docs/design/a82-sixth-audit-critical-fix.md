# A82 — 验收 guard 改为 fail-closed allow-list（第六轮审核致命项修复）

## 背景

2026-07-16，第六次审核评分 64/100（较第五轮下降），**首次出现致命项**：
`assert_not_research_baseline()`（`chan_strategy/backtest_engine.py`，A78 引入）目前是一个
**blocklist**——只在 `report.get("mode_label") == "RESEARCH_BASELINE"` 时才拒绝，这意味着任何
`mode_label` 缺失、为空字符串、拼写错误，或来自旧版本报告的情况，都会被当作"不是研究基线"而放行。
`test_formal_evaluation.py` 里甚至有明确断言 `{}` 和 `{"mode_label": ""}` 通过——这不是测试的错，
是设计本身的漏洞：一个专门用来防止研究基线报告被误当作可交易证据的护栏函数，本该在"不确定"的情况下
拒绝（fail-closed），而不是默认放行。

这是 claude-code 在 A78/A81 设计阶段的疏漏，现在必须直接修复，不能再当作"又一个新发现的中严重度
问题"绕过去。

## 本次修复范围裁定

第六轮审核还有一条 🔴高（诊断脚本默认不走 formal_evaluation_config()）和多条 🟡中/🟢低，与前五轮
路线图反复出现的"让更多东西默认使用正式评估路径"是同一主题的又一次变体。**本任务只处理上面这一条
致命项**（guard 的 fail-closed 修复），其余问题不在本任务展开——claude-code 会在完成本任务后，
向用户如实汇报当前状态与后续选择，而不是自动开第七轮路线图。

## Semantics

- 将 `assert_not_research_baseline()`（及 `unified_acceptance_gate()` 内对它的复用）改为
  **allow-list** 逻辑：只有当 `mode_label` 是一个"已知安全"的值时才放行，其余一律 fail——包括
  `None`、缺失键、空字符串、`"RESEARCH_BASELINE"`、任何未被识别的字符串。
- "已知安全"的判定：`mode_label` 要么等于 `"RESEARCH_BASELINE"` 之外的、由
  `_compute_mode_label()` 实际可能产生的值——即以 `"PARTIAL_PRODUCTION_FEATURES("` 开头（A70 已有
  格式）。这是当前代码库唯一会产生的"非研究基线"标签格式，不需要发明新的分类体系。
- 更新 `test_formal_evaluation.py` 中明确断言 `{}` 和 `{"mode_label": ""}` **通过**的测试——这些
  断言本身就是审核指出的漏洞证据，需要改为断言它们现在会被拒绝（fail）。
- 不改变 `_compute_mode_label()` 本身的计算逻辑或格式——只改变消费方 `assert_not_research_baseline()`
  的判定策略，从"匹配到就拒绝"改为"匹配不到已知安全格式就拒绝"。

## Acceptance Criteria

- [ ] `assert_not_research_baseline()` 对以下输入全部抛出 `ValueError`：`{}`（缺失键）、
      `{"mode_label": None}`、`{"mode_label": ""}`、`{"mode_label": "RESEARCH_BASELINE"}`、
      `{"mode_label": "SOME_TYPO"}`（未知字符串）。
- [ ] `assert_not_research_baseline()` 对 `{"mode_label": "PARTIAL_PRODUCTION_FEATURES(...)"}`
      （任何由 `_compute_mode_label()` 实际产生的非基线格式）不抛出异常。
- [ ] `unified_acceptance_gate()`（A81）复用更新后的逻辑，对上述所有"不确定/未知"输入返回顶层
      `"fail"`。
- [ ] `test_formal_evaluation.py` 中原先断言 `{}`/`{"mode_label": ""}` 通过的测试，改为断言它们
      现在被拒绝——这是本任务修复漏洞的直接证据，不是删除测试，是修正测试的预期结果。
- [ ] `test_a81_acceptance_gate.py` 中若有类似"空/缺失 mode_label 视为 pass"的测试，同样更新为
      "fail"（本设计文档已知 `test_empty_mode_label_does_not_fail` 这条测试断言空字符串不 fail——
      这条断言现在是错的，必须改为断言它会 fail）。
- [ ] 不改变 `_compute_mode_label()` 本身或任何回测数值输出。
- [ ] `python -m pytest examples/czsc_strategy/tests/unit -q -m "not realdb"` 通过。
- [ ] `python tools/sync_check.py` 与 `python tools/sync_check.py --root examples/czsc_strategy` 通过。
- [ ] `run_next_work.ps1 -Preflight` 通过。
- [ ] VERSION/CHANGELOG bump。

## Dev Prompt

1. 先读 `chan_strategy/backtest_engine.py` 里 `assert_not_research_baseline()` 与
   `_compute_mode_label()` 的当前实现，确认 `_compute_mode_label()` 实际会产生的两类字符串格式
   （`"RESEARCH_BASELINE"` 与 `"PARTIAL_PRODUCTION_FEATURES(...)"`），不要凭空假设格式。
2. 把判定逻辑从"匹配到 RESEARCH_BASELINE 就拒绝"改为"不匹配已知安全格式就拒绝"。
3. 找到并修正 `test_formal_evaluation.py`/`test_a81_acceptance_gate.py` 中断言空/缺失
   `mode_label` 通过的测试用例——这些测试断言本身就是本次要修复的漏洞证据，必须改为断言拒绝。
4. 提交前 `git status --short` 核对，只暂存本任务范围内文件，不动无关并发工作流文件。
5. 完成后附字面 `## Manual Verification` 标题的验证区块。

## Review Checklist

- 确认新逻辑对 `_compute_mode_label()` 实际可能产生的每一种字符串格式都有明确判定（不留"两种已知
  格式之外的第三种真实场景被意外拒绝"的回归）。
- 确认原先"证明漏洞存在"的测试断言已经反向修正为"证明漏洞已修复"，而不是被删除或跳过。

## Manual Verification

以下命令均在本机实际执行并返回成功：

```text
$ python -m pytest examples/czsc_strategy/tests/unit/test_formal_evaluation.py examples/czsc_strategy/tests/unit/test_a81_acceptance_gate.py -q -m "not realdb"
19 passed in 0.12s

$ python -m pytest examples/czsc_strategy/tests/unit -q -m "not realdb"
717 passed, 4 deselected in 29.90s

$ ruff check examples/czsc_strategy/chan_strategy/backtest_engine.py examples/czsc_strategy/tests/unit/test_formal_evaluation.py examples/czsc_strategy/tests/unit/test_a81_acceptance_gate.py
All checks passed!

$ python tools/sync_check.py
[SYNC-CHECK] PASS: 版本与文档一致。

$ python tools/sync_check.py --root examples/czsc_strategy
[SYNC-CHECK] PASS: 版本与文档一致。

$ powershell -ExecutionPolicy Bypass -File examples/czsc_strategy/diagnostics/run_next_work.ps1 -Preflight
191 passed in 15.85s
Preflight complete; live SimNow capture was not requested
```
