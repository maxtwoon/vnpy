# chan-pan-analysis LLM 真评估报告

- 生成时间: 2026-06-18 09:23:23
- 模式: DeepSeek 实际生成
- 样本数: `1`；LLM 已评估: `1`
- 数据源: `D:\repo\vnpy\examples\czsc_strategy\skill_build\mapping\eval_records.jsonl` + `D:\repo\vnpy\examples\czsc_strategy\skill_build\sh000001_daily.csv`
- 输出 JSONL: `D:\repo\vnpy\examples\czsc_strategy\skill_build\reports\llm_skill_eval_results.jsonl`

## 汇总

- LLM 方向分布: `{'direct': 1}`
- LLM 方向归因: `{'true_conflict': 1}`
- LLM 结构术语平均重合数: `6.00`
- LLM 买卖点平均重合数: `0.00`
- LLM 平均情景覆盖计数: `12.00`
- LLM 编造确认买卖点总数: `0`
- 模板基线结构术语平均重合数: `4.00`
- 模板基线买卖点平均重合数: `0.00`
- 模板基线平均情景覆盖计数: `4.00`

## 逐日对比

| 日期 | 标题 | LLM方向 | 方向归因 | 模板方向 | LLM术语 | 模板术语 | LLM未溯源价位 | 状态 |
|---|---|---:|---|---:|---:|---:|---|---|
| 2026-06-10 | 考察共识阶段！ | direct | true_conflict | diff | 6 | 4 | [] | ok |

## 样本详情

### 2026-06-10 考察共识阶段！

- 状态: ok
- 真人倾向: 偏空/调整
- 客观活跃买卖点: `[]`
- 模板评分: `{'direction': 'diff', 'direction_attribution': 'daily_match', 'generated_bias': '多空并陈/震荡', 'human_bias': '偏空/调整', 'term_overlap': 4, 'generated_terms': ['一买', '一卖', '三买', '三卖', '中枢', '二买', '二卖', '背驰', '趋势', '量能'], 'human_terms': ['三卖', '中枢', '二买', '反抽', '底分型', '线段', '背驰', '震荡'], 'buy_sell_overlap': 0, 'objective_active_buy_sell': [], 'confirmed_bsp_claims': [], 'candidate_bsp_mentions': [], 'human_confirmed_bsp': [], 'invented_confirmed_bsp': [], 'invented_buy_sell_terms': [], 'scenario_count': 4, 'unsourced_prices': []}`
- LLM评分: `{'direction': 'direct', 'direction_attribution': 'true_conflict', 'generated_bias': '偏空/调整', 'human_bias': '偏空/调整', 'term_overlap': 6, 'generated_terms': ['一买', '一卖', '三买', '三卖', '中枢', '二买', '二卖', '底分型', '离开段', '背驰', '量能', '震荡'], 'human_terms': ['三卖', '中枢', '二买', '反抽', '底分型', '线段', '背驰', '震荡'], 'buy_sell_overlap': 0, 'objective_active_buy_sell': [], 'confirmed_bsp_claims': [], 'candidate_bsp_mentions': ['二买'], 'human_confirmed_bsp': [], 'invented_confirmed_bsp': [], 'invented_buy_sell_terms': [], 'scenario_count': 12, 'unsourced_prices': []}`

**LLM 输出摘录**

【上证指数 缠论解盘 · 2026-06-10】

一、日线结构
方向向下，价格运行在中枢下方，日线级别中枢已确认（区间 ZG=4197.23, ZD=4002.78，3笔）。当前处于向下离开中枢后的延续阶段，最新收盘价位于中枢下沿下方，结构偏弱。当前未见明显背驰，但离开段内部力度有待观察。

二、次级别推演
次级别数据不可用，本段略；以下推演基于日线结构。

三、买卖点状态
多头：一买=非一买 ｜ 二买=无有效确认样本，仅作观察条件 ｜ 三买=非三买
空头：一卖=非一卖 ｜ 二卖=无有效确认样本，仅作观察条件 ｜ 三卖=非三卖
当前无确认的买卖点信号，结构上延续日线向下笔的调整，尚未形成有效的转折信号。

四、强弱判断
价格已跌破日线中枢下沿 4002.78，且方向向下，短线空方占优。多头的观望条件在于能否重新收回 ZD，以缓和弱势结构；否则，向下考验近期确认笔低点 3794.68 的压力仍在。量能与板块轮动需人工确认。

五、后续推演（2 种情景）
第一种（弱修复）：若能重新站回中枢下沿 4002.78 上方，甚至进一步挑战中枢上沿 4197.23，则说明中枢震荡逻辑可能延续，日线向下笔有衰竭可能；届时可观察底分型构筑情况及是否形成有效二买结构。
第二种（延续下行）：若持续被 ZD 压制，则空头结构延续，向下将考验近期确认笔低点 3794.68；失守该位置，日线级别调整压力将进一步加大。

以上为缠论结构分析与推演，不构成投资建议。