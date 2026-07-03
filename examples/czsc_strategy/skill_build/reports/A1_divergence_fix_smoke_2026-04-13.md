# chan-pan-analysis LLM 真评估报告

- 生成时间: 2026-06-18 02:29:15
- 模式: DeepSeek 实际生成
- 样本数: `1`；LLM 已评估: `1`
- 数据源: `D:\repo\vnpy\examples\czsc_strategy\skill_build\mapping\eval_records.jsonl` + `D:\repo\vnpy\examples\czsc_strategy\skill_build\sh000001_daily.csv`
- 输出 JSONL: `D:\repo\vnpy\examples\czsc_strategy\skill_build\reports\llm_skill_eval_results.jsonl`

## 汇总

- LLM 方向分布: `{'direct': 1}`
- LLM 方向归因: `{'scenario_match': 1}`
- LLM 结构术语平均重合数: `3.00`
- LLM 买卖点平均重合数: `0.00`
- LLM 平均情景覆盖计数: `14.00`
- LLM 编造确认买卖点总数: `0`
- 模板基线结构术语平均重合数: `2.00`
- 模板基线买卖点平均重合数: `0.00`
- 模板基线平均情景覆盖计数: `4.00`

## 逐日对比

| 日期 | 标题 | LLM方向 | 方向归因 | 模板方向 | LLM术语 | 模板术语 | LLM未溯源价位 | 状态 |
|---|---|---:|---|---:|---:|---:|---|---|
| 2026-04-13 | 震荡范围有加大的趋势！ | direct | scenario_match | diff | 3 | 2 | [] | ok |

## 样本详情

### 2026-04-13 震荡范围有加大的趋势！

- 状态: ok
- 真人倾向: 偏空/调整
- 客观活跃买卖点: `[]`
- 模板评分: `{'direction': 'diff', 'direction_attribution': 'intraday_mismatch', 'generated_bias': '多空并陈/震荡', 'human_bias': '偏空/调整', 'term_overlap': 2, 'generated_terms': ['一买', '一卖', '三买', '三卖', '中枢', '二买', '二卖', '背驰', '趋势', '量能'], 'human_terms': ['中枢', '量能', '震荡'], 'buy_sell_overlap': 0, 'objective_active_buy_sell': [], 'confirmed_bsp_claims': [], 'candidate_bsp_mentions': [], 'human_confirmed_bsp': [], 'invented_confirmed_bsp': [], 'invented_buy_sell_terms': [], 'scenario_count': 4, 'unsourced_prices': []}`
- LLM评分: `{'direction': 'direct', 'direction_attribution': 'scenario_match', 'generated_bias': '偏空/调整', 'human_bias': '偏空/调整', 'term_overlap': 3, 'generated_terms': ['一买', '一卖', '三买', '三卖', '中枢', '二买', '二卖', '底分型', '背驰', '量能', '震荡'], 'human_terms': ['中枢', '量能', '震荡'], 'buy_sell_overlap': 0, 'objective_active_buy_sell': [], 'confirmed_bsp_claims': [], 'candidate_bsp_mentions': [], 'human_confirmed_bsp': [], 'invented_confirmed_bsp': [], 'invented_buy_sell_terms': [], 'scenario_count': 14, 'unsourced_prices': []}`

**LLM 输出摘录**

【上证指数 缠论解盘 · 2026-04-13】

一、日线结构
方向=向下，中枢位置=中枢下方；中枢 ZG=4190.87 ZD=4002.78（3笔）。
当前处于向下一笔调整中，价格已跌破中枢下沿，走势结构偏弱；当前未见明显背驰。日线结构显示为中枢下方弱势运行，空头风控“结构失效”。

二、次级别推演
次级别数据不可用，本段略；以下推演基于日线结构。

三、买卖点状态
多头：一买=非一买｜二买=非二买｜三买=非三买
空头：一卖=非一卖｜二卖=非二卖｜三卖=非三卖
当前无确认的任何级别买点与卖点。价格处于中枢下方，但日线级别二卖缺少有效确认样本，仅作为观察条件，不构成确认信号。

四、强弱判断
日线向下一笔延续，且运行于中枢下沿下方，结构状态偏弱。量能与板块轮动无相关数据支持，需人工确认。当前调整能否缓和，重点观察是否重新站回中枢下沿 ZD=4002.78。

五、后续推演（2–3 种情景）
第一种（修复）：价格重新站上并守稳中枢下沿 ZD=4002.78，则日线弱势结构有所缓和，有机会回到中枢内部进行震荡整理；若能继续向上挑战 ZG=4190.87，则强度会进一步提升。
第二种（延续弱势）：价格无法有效收回 ZD=4002.78，且继续向下考验前低 3794.68，则弱势结构将继续延续，调整深度可能加大；若 3794.68 失守，则日线大结构面临进一步降级风险。
第三种（中枢下方震荡）：价格在 ZD=4002.78 与 3794.68 之间进行中枢下方窄幅整理，方向未定；需观察是否在此区域形成新的底分型与向上确认笔，以及能否回到原中枢内部。

以上为缠论结构分析与推演，不构成投资建议。