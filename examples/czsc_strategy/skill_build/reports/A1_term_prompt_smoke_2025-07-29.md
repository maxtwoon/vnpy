# chan-pan-analysis LLM 真评估报告

- 生成时间: 2026-06-17 22:05:12
- 模式: DeepSeek 实际生成
- 样本数: `1`；LLM 已评估: `1`
- 数据源: `D:\repo\vnpy\examples\czsc_strategy\skill_build\mapping\eval_records.jsonl` + `D:\repo\vnpy\examples\czsc_strategy\skill_build\sh000001_daily.csv`
- 输出 JSONL: `D:\repo\vnpy\examples\czsc_strategy\skill_build\reports\llm_skill_eval_results.jsonl`

## 汇总

- LLM 方向分布: `{'diff': 1}`
- LLM 方向归因: `{'true_conflict': 1}`
- LLM 结构术语平均重合数: `3.00`
- LLM 买卖点平均重合数: `0.00`
- LLM 平均情景覆盖计数: `12.00`
- LLM 编造确认买卖点总数: `0`
- 模板基线结构术语平均重合数: `4.00`
- 模板基线买卖点平均重合数: `0.00`
- 模板基线平均情景覆盖计数: `4.00`

## 逐日对比

| 日期 | 标题 | LLM方向 | 方向归因 | 模板方向 | LLM术语 | 模板术语 | LLM未溯源价位 | 状态 |
|---|---|---:|---|---:|---:|---:|---|---|
| 2025-07-29 | 继续上行！ | diff | true_conflict | diff | 3 | 4 | [] | ok |

## 样本详情

### 2025-07-29 继续上行！

- 状态: ok
- 真人倾向: 偏多/上行
- 客观活跃买卖点: `[]`
- 模板评分: `{'direction': 'diff', 'direction_attribution': 'daily_match', 'generated_bias': '多空并陈/震荡', 'human_bias': '偏多/上行', 'term_overlap': 4, 'generated_terms': ['一买', '一卖', '三买', '三卖', '中枢', '二买', '二卖', '背驰', '趋势', '量能'], 'human_terms': ['中枢', '盘整', '线段', '背驰', '趋势', '量能'], 'buy_sell_overlap': 0, 'objective_active_buy_sell': [], 'confirmed_bsp_claims': [], 'candidate_bsp_mentions': [], 'human_confirmed_bsp': [], 'invented_confirmed_bsp': [], 'invented_buy_sell_terms': [], 'scenario_count': 4, 'unsourced_prices': []}`
- LLM评分: `{'direction': 'diff', 'direction_attribution': 'true_conflict', 'generated_bias': '偏空/调整', 'human_bias': '偏多/上行', 'term_overlap': 3, 'generated_terms': ['一买', '一卖', '三买', '三卖', '中枢', '二买', '二卖', '离开段', '背驰', '量能', '震荡'], 'human_terms': ['中枢', '盘整', '线段', '背驰', '趋势', '量能'], 'buy_sell_overlap': 0, 'objective_active_buy_sell': [], 'confirmed_bsp_claims': [], 'candidate_bsp_mentions': ['三买'], 'human_confirmed_bsp': [], 'invented_confirmed_bsp': [], 'invented_buy_sell_terms': [], 'scenario_count': 12, 'unsourced_prices': []}`

**LLM 输出摘录**

【上证指数 缠论解盘 · 2025-07-29】

一、日线结构
方向=向上，中枢上方；中枢 ZG=3413.51 ZD=3347.65（3笔）。
当前日线确认笔方向向上，价格运行在中枢上方，且最新收盘价3609.71已显著越出中枢上沿，显示结构偏强。当前处于离开中枢后的延伸阶段，重点观察离开段力度能否持续，以及能否继续站稳中枢上沿。

二、次级别推演
次级别数据不可用，本段略；以下推演基于日线结构。若有30分钟或5分钟数据，应优先用于观察中枢离开段的内部结构和背驰状态，目前无法提供分钟级确认。

三、买卖点状态
多头：一买=非一买｜二买=非二买｜三买=非三买
空头：一卖=非一卖｜二卖=非二卖｜三卖=非三卖
当前无已确认的买卖点信号。价格处于中枢上方离开段延伸中，后续需观察回抽能否不进入中枢上沿ZG=3413.51，从而构成潜在的第三类买点观察条件，而非确认买点。

四、强弱判断
当前方向向上且运行在中枢上方，暂未出现背驰，结构偏强。但分钟级数据缺失，无法从次级别确认离开段内部力度和背驰状态，量能与板块轮动需人工确认。上方整数关口需人工确认，下方关键支撑观察中枢上沿3413.51及确认笔低点3332.49。

五、后续推演（2–3 种情景）
第一种：价格继续保持在中枢上方运行，回抽不跌破ZG=3413.51，则中枢离开段延续，结构继续偏强，后续可等待三买观察条件的进一步明朗。
第二种：价格出现回落，跌破中枢上沿ZG=3413.51但未破ZD=3347.65，则进入中枢震荡状态，强弱观察位上移至ZG得失。
第三种：价格快速回落，跌破中枢下沿ZD=3347.65，则短期结构转弱，调整压力加大，需要重新评估离开段是否结束。

免责声明：以上为缠论结构分析与推演，不构成投资建议。