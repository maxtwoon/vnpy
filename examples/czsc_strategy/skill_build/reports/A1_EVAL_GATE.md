# A1 真 Skill 评估门禁

本门禁用于确认“真实 LLM 读取 SKILL.md + few_shot + signal_to_narrative + 客观 JSON 后生成解盘”的最低可用性。

## 当前固定产物

- 正式样本：`A1_true_skill_eval_50days.jsonl`
- 正式报告：`A1_true_skill_eval_50days.md`
- 摘要：`A1_true_skill_eval_50days_summary.md`

## 快速门禁

```powershell
python examples\czsc_strategy\skill_build\reports\check_a1_eval_gate.py `
  --jsonl examples\czsc_strategy\skill_build\reports\A1_true_skill_eval_50days.jsonl `
  --max-unsourced-prices 0 `
  --min-avg-scenario 8
```

背驰约束新版门禁：

```powershell
python examples\czsc_strategy\skill_build\reports\check_a1_eval_gate.py `
  --jsonl examples\czsc_strategy\skill_build\reports\A1_true_skill_eval_50days_divergence.jsonl `
  --max-unsourced-prices 0 `
  --min-avg-scenario 8
```

通过标准：

- 全部样本 `status=ok`
- 未编造确认买卖点
- 未输出客观 JSON 中找不到来源的价位
- 每日情景覆盖平均数不低于 8
- 每条样本都有方向归因

## 重新生成正式评估

需要 DeepSeek API key 已写入 `examples/czsc_strategy/skill_build/llm_eval_config.json`。

```powershell
python examples\czsc_strategy\skill_build\reports\llm_skill_eval.py `
  --limit 50 `
  --out-report examples\czsc_strategy\skill_build\reports\A1_true_skill_eval_50days.md `
  --out-jsonl examples\czsc_strategy\skill_build\reports\A1_true_skill_eval_50days.jsonl
```

若只是复核已生成 JSONL，不重新调用 LLM：

```powershell
python examples\czsc_strategy\skill_build\reports\llm_skill_eval.py `
  --reuse-jsonl examples\czsc_strategy\skill_build\reports\A1_true_skill_eval_50days.jsonl `
  --out-report examples\czsc_strategy\skill_build\reports\A1_true_skill_eval_50days.md `
  --out-jsonl examples\czsc_strategy\skill_build\reports\A1_true_skill_eval_50days.jsonl
```

## 单日 Smoke

用于验证 DeepSeek 配置、prompt 与评分器仍可跑通，不覆盖正式 50 天产物。

```powershell
python examples\czsc_strategy\skill_build\reports\llm_skill_eval.py `
  --dates 2025-07-29 `
  --out-report examples\czsc_strategy\skill_build\reports\A1_term_prompt_smoke_2025-07-29.md `
  --out-jsonl examples\czsc_strategy\skill_build\reports\A1_term_prompt_smoke_2025-07-29.jsonl
```
