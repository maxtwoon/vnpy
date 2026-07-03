# chan-pan-analysis LLM 真评估报告

- 生成时间: 2026-06-17 17:51:30
- 模式: dry-run / 未调用 DeepSeek
- 样本数: `2`；LLM 已评估: `0`
- 数据源: `D:\repo\vnpy\examples\czsc_strategy\skill_build\mapping\eval_records.jsonl` + `D:\repo\vnpy\examples\czsc_strategy\skill_build\sh000001_daily.csv`
- 输出 JSONL: `D:\repo\vnpy\examples\czsc_strategy\skill_build\reports\llm_skill_eval_results.jsonl`

## 汇总

- LLM 方向分布: `{}`
- LLM 方向归因: `{}`
- LLM 结构术语平均重合数: `0.00`
- LLM 买卖点平均重合数: `0.00`
- LLM 平均情景覆盖计数: `0.00`
- LLM 编造确认买卖点总数: `0`
- 模板基线结构术语平均重合数: `2.00`
- 模板基线买卖点平均重合数: `0.00`
- 模板基线平均情景覆盖计数: `8.50`

## 逐日对比

| 日期 | 标题 | LLM方向 | 方向归因 | 模板方向 | LLM术语 | 模板术语 | LLM未溯源价位 | 状态 |
|---|---|---:|---|---:|---:|---:|---|---|
| 2025-07-21 | 前高构成压力吗？ | - | - | diff | - | 2 | - | dry_run |
| 2025-09-03 | 买点在下跌中出现！ | - | - | diff | - | 2 | - | dry_run |

## 样本详情

### 2025-07-21 前高构成压力吗？

- 状态: dry_run
- 真人倾向: 多空并陈/震荡
- 客观活跃买卖点: `[]`
- 模板评分: `{'direction': 'diff', 'direction_attribution': 'intraday_mismatch', 'generated_bias': '偏空/调整', 'human_bias': '多空并陈/震荡', 'term_overlap': 2, 'generated_terms': ['一买', '一卖', '三买', '三卖', '中枢', '二买', '二卖', '背驰', '趋势', '量能', '震荡'], 'human_terms': ['中枢', '盘整', '线段', '趋势'], 'buy_sell_overlap': 0, 'objective_active_buy_sell': [], 'confirmed_bsp_claims': [], 'candidate_bsp_mentions': [], 'human_confirmed_bsp': [], 'invented_confirmed_bsp': [], 'invented_buy_sell_terms': [], 'scenario_count': 7, 'unsourced_prices': []}`
- LLM评分: `{}`

**提示**

本行未调用 DeepSeek；请填写 `D:\repo\vnpy\examples\czsc_strategy\skill_build\llm_eval_config.json` 或设置 `DEEPSEEK_API_KEY` 后去掉 `--dry-run` 重跑。

### 2025-09-03 买点在下跌中出现！

- 状态: dry_run
- 真人倾向: 偏空/调整
- 客观活跃买卖点: `['三买']`
- 模板评分: `{'direction': 'diff', 'direction_attribution': 'intraday_mismatch', 'generated_bias': '偏多/上行', 'human_bias': '偏空/调整', 'term_overlap': 2, 'generated_terms': ['一买', '一卖', '三买', '三卖', '中枢', '二买', '二卖', '离开段', '背驰', '趋势', '量能', '震荡'], 'human_terms': ['中枢', '盘整', '震荡'], 'buy_sell_overlap': 0, 'objective_active_buy_sell': ['三买'], 'confirmed_bsp_claims': [], 'candidate_bsp_mentions': ['三买'], 'human_confirmed_bsp': [], 'invented_confirmed_bsp': [], 'invented_buy_sell_terms': [], 'scenario_count': 10, 'unsourced_prices': []}`
- LLM评分: `{}`

**提示**

本行未调用 DeepSeek；请填写 `D:\repo\vnpy\examples\czsc_strategy\skill_build\llm_eval_config.json` 或设置 `DEEPSEEK_API_KEY` 后去掉 `--dry-run` 重跑。