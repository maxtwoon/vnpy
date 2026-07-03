# chan-pan-analysis LLM 真评估报告

- 生成时间: 2026-06-18 00:22:01
- 模式: DeepSeek 实际生成
- 样本数: `1`；LLM 已评估: `1`
- 数据源: `D:\repo\vnpy\examples\czsc_strategy\skill_build\mapping\eval_records.jsonl` + `D:\repo\vnpy\examples\czsc_strategy\skill_build\sh000001_daily.csv`
- 输出 JSONL: `D:\repo\vnpy\examples\czsc_strategy\skill_build\reports\llm_skill_eval_results.jsonl`

## 汇总

- LLM 方向分布: `{'direct': 1}`
- LLM 方向归因: `{'daily_match': 1}`
- LLM 结构术语平均重合数: `4.00`
- LLM 买卖点平均重合数: `0.00`
- LLM 平均情景覆盖计数: `14.00`
- LLM 编造确认买卖点总数: `0`
- 模板基线结构术语平均重合数: `4.00`
- 模板基线买卖点平均重合数: `0.00`
- 模板基线平均情景覆盖计数: `4.00`

## 逐日对比

| 日期 | 标题 | LLM方向 | 方向归因 | 模板方向 | LLM术语 | 模板术语 | LLM未溯源价位 | 状态 |
|---|---|---:|---|---:|---:|---:|---|---|
| 2025-07-29 | 继续上行！ | direct | daily_match | diff | 4 | 4 | [] | ok |

## 样本详情

### 2025-07-29 继续上行！

- 状态: ok
- 真人倾向: 偏多/上行
- 客观活跃买卖点: `[]`
- 模板评分: `{'direction': 'diff', 'direction_attribution': 'daily_match', 'generated_bias': '多空并陈/震荡', 'human_bias': '偏多/上行', 'term_overlap': 4, 'generated_terms': ['一买', '一卖', '三买', '三卖', '中枢', '二买', '二卖', '背驰', '趋势', '量能'], 'human_terms': ['中枢', '盘整', '线段', '背驰', '趋势', '量能'], 'buy_sell_overlap': 0, 'objective_active_buy_sell': [], 'confirmed_bsp_claims': [], 'candidate_bsp_mentions': [], 'human_confirmed_bsp': [], 'invented_confirmed_bsp': [], 'invented_buy_sell_terms': [], 'scenario_count': 4, 'unsourced_prices': []}`
- LLM评分: `{'direction': 'direct', 'direction_attribution': 'daily_match', 'generated_bias': '偏多/上行', 'human_bias': '偏多/上行', 'term_overlap': 4, 'generated_terms': ['一买', '一卖', '三买', '三卖', '中枢', '二买', '二卖', '承接', '背驰', '趋势', '量能', '顶分型'], 'human_terms': ['中枢', '盘整', '线段', '背驰', '趋势', '量能'], 'buy_sell_overlap': 0, 'objective_active_buy_sell': [], 'confirmed_bsp_claims': [], 'candidate_bsp_mentions': ['三买'], 'human_confirmed_bsp': [], 'invented_confirmed_bsp': [], 'invented_buy_sell_terms': [], 'scenario_count': 14, 'unsourced_prices': []}`

**LLM 输出摘录**

【上证指数 缠论解盘 · 2025-07-29】

一、日线结构
方向=向上，中枢上方；中枢 ZG=3413.51 ZD=3347.65（三笔）。
当前为向上一笔延续中，价格运行在中枢上方，且最新收盘价已站到中枢ZG之上，结构偏强。本级别未见明显背驰。

二、次级别推演
次级别数据不可用，本段略；以下推演基于日线结构。

三、买卖点状态
多头：一买=非一买｜二买=观察条件（日线有效信号不足）｜三买=回抽不入中枢（观察阶段）
空头：一卖=非一卖｜二卖=观察条件（日线有效信号不足）｜三卖=非三卖
当前处在对原中枢的三买观察阶段：回抽暂未进入中枢内部，后续需等待确认笔或进一步上攻来验证承接力度。

四、强弱判断
目前价格中枢上方运行，结构偏强。日线向上一笔延续，未出现顶分型破坏。量能、板块轮动情况无客观JSON数据，需人工确认。

五、后续推演（2–3 种情景）
第一种：若能持续站稳中枢上沿3413.51并放量上攻，突破3580区域后有望挑战前高3613.02。突破该位则趋势延续，三买结构进一步强化。
第二种：若走势在3600点一线受阻回落，但回落在3413.51（ZG）附近获得有效支撑，则仍属中枢上方的强势整理，观察后续承接力度及能否重新向上。
（第三种：若快速跌破3413.51并无法收回，则回抽中枢失败，三买观察结构失效，调整级别可能扩大，需关注中枢下沿3347.65的支撑力度。）
以上为基于缠论结构的客观分析推演，不构成投资建议。