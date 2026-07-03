# chan-pan-analysis LLM 真评估报告

- 生成时间: 2026-06-18 09:21:59
- 模式: DeepSeek 实际生成
- 样本数: `3`；LLM 已评估: `3`
- 数据源: `D:\repo\vnpy\examples\czsc_strategy\skill_build\mapping\eval_records.jsonl` + `D:\repo\vnpy\examples\czsc_strategy\skill_build\sh000001_daily.csv`
- 输出 JSONL: `D:\repo\vnpy\examples\czsc_strategy\skill_build\reports\llm_skill_eval_results.jsonl`

## 汇总

- LLM 方向分布: `{'diff': 2, 'direct': 1}`
- LLM 方向归因: `{'intraday_mismatch': 1, 'true_conflict': 2}`
- LLM 结构术语平均重合数: `3.33`
- LLM 买卖点平均重合数: `0.00`
- LLM 平均情景覆盖计数: `11.00`
- LLM 编造确认买卖点总数: `0`
- 模板基线结构术语平均重合数: `3.00`
- 模板基线买卖点平均重合数: `0.00`
- 模板基线平均情景覆盖计数: `4.00`

## 逐日对比

| 日期 | 标题 | LLM方向 | 方向归因 | 模板方向 | LLM术语 | 模板术语 | LLM未溯源价位 | 状态 |
|---|---|---:|---|---:|---:|---:|---|---|
| 2025-08-11 | 鼓声雷动 | diff | intraday_mismatch | diff | 2 | 3 | [] | ok |
| 2026-03-10 | 轻指数，重个股！ | diff | true_conflict | diff | 3 | 2 | [] | ok |
| 2026-06-10 | 考察共识阶段！ | direct | true_conflict | diff | 5 | 4 | [4000.0] | ok |

## 样本详情

### 2025-08-11 鼓声雷动

- 状态: ok
- 真人倾向: 偏多/上行
- 客观活跃买卖点: `[]`
- 模板评分: `{'direction': 'diff', 'direction_attribution': 'intraday_mismatch', 'generated_bias': '多空并陈/震荡', 'human_bias': '偏多/上行', 'term_overlap': 3, 'generated_terms': ['一买', '一卖', '三买', '三卖', '中枢', '二买', '二卖', '背驰', '趋势', '量能'], 'human_terms': ['三买', '中枢', '量能', '震荡'], 'buy_sell_overlap': 0, 'objective_active_buy_sell': [], 'confirmed_bsp_claims': [], 'candidate_bsp_mentions': [], 'human_confirmed_bsp': [], 'invented_confirmed_bsp': [], 'invented_buy_sell_terms': [], 'scenario_count': 4, 'unsourced_prices': []}`
- LLM评分: `{'direction': 'diff', 'direction_attribution': 'intraday_mismatch', 'generated_bias': '偏空/调整', 'human_bias': '偏多/上行', 'term_overlap': 2, 'generated_terms': ['一买', '一卖', '三卖', '中枢', '二卖', '回踩', '离开段', '背驰', '量能'], 'human_terms': ['三买', '中枢', '量能', '震荡'], 'buy_sell_overlap': 0, 'objective_active_buy_sell': [], 'confirmed_bsp_claims': [], 'candidate_bsp_mentions': [], 'human_confirmed_bsp': [], 'invented_confirmed_bsp': [], 'invented_buy_sell_terms': [], 'scenario_count': 11, 'unsourced_prices': []}`

**LLM 输出摘录**

【上证指数 缠论解盘 · 2025-08-11】

一、日线结构
方向=向下，中枢位置=中枢上方；中枢 ZG=3413.51 ZD=3347.65（3笔）。
当前日线确认笔方向已转弱，但价格仍运行在中枢上方，属于高位回落结构；当前未见明显背驰。最新收盘 3647.55，位于中枢上方且距 ZG 溢价约 6.9%，多空分水岭重点看 ZG=3413.51 是否被回踩或失守。

二、次级别推演
次级别数据不可用，本段略；以下推演基于日线结构。

三、买卖点状态
多头：一买=非一买｜其他买卖点当前无确认信号。
空头：当前无确认的一卖/二卖/三卖信号。
当前最需关注的是日线向上离开段力度衰减及回抽是否能在 ZG 上方获得支撑，买卖点需等待结构进一步确认。

四、强弱判断
结构已确认，确认笔方向向下但价格仍在中枢上方，暂按高位回落观察处理；多空分水岭为 ZG=3413.51。量能、板块轮动需人工确认。

五、后续推演（2 种情景）
第一种：若价格继续守在 ZG=3413.51 上方，且回落不破坏中枢上沿，则属于偏强整理，后续仍有再次向上挑战近期高点 3417.31 的条件。
第二种：若持续回落并有效跌破 ZG=3413.51，则结构转弱，调整压力加大，近期低点 3332.49 的支撑将受到考验。

免责声明：以上为缠论结构分析与推演，不构成投资建议。

### 2026-03-10 轻指数，重个股！

- 状态: ok
- 真人倾向: 偏多/上行
- 客观活跃买卖点: `[]`
- 模板评分: `{'direction': 'diff', 'direction_attribution': 'daily_match', 'generated_bias': '多空并陈/震荡', 'human_bias': '偏多/上行', 'term_overlap': 2, 'generated_terms': ['一买', '一卖', '三买', '三卖', '中枢', '二买', '二卖', '背驰', '趋势', '量能'], 'human_terms': ['中枢', '底分型', '线段', '背驰', '震荡'], 'buy_sell_overlap': 0, 'objective_active_buy_sell': [], 'confirmed_bsp_claims': [], 'candidate_bsp_mentions': [], 'human_confirmed_bsp': [], 'invented_confirmed_bsp': [], 'invented_buy_sell_terms': [], 'scenario_count': 4, 'unsourced_prices': []}`
- LLM评分: `{'direction': 'diff', 'direction_attribution': 'true_conflict', 'generated_bias': '偏空/调整', 'human_bias': '偏多/上行', 'term_overlap': 3, 'generated_terms': ['一买', '一卖', '三买', '三卖', '中枢', '二买', '二卖', '盘整', '离开段', '背驰', '量能', '震荡'], 'human_terms': ['中枢', '底分型', '线段', '背驰', '震荡'], 'buy_sell_overlap': 0, 'objective_active_buy_sell': [], 'confirmed_bsp_claims': [], 'candidate_bsp_mentions': [], 'human_confirmed_bsp': [], 'invented_confirmed_bsp': [], 'invented_buy_sell_terms': [], 'scenario_count': 10, 'unsourced_prices': []}`

**LLM 输出摘录**

【上证指数 缠论解盘 · 2026-03-10】

一、日线结构
方向向下，中枢位置为中枢内；中枢 ZG=4190.87 ZD=4002.78（3笔）。
当前价格仍在中枢内部反复，方向选择尚未彻底完成；上沿与下沿分别是强弱切换的观察位。当前未见明显背驰，属于中枢内偏弱震荡，调整压力仍在，重点观察能否守住中枢下沿。

二、次级别推演
次级别数据不可用，本段略；以下推演基于日线结构。

三、买卖点状态
多头：一买=非一买｜二买=非二买｜三买=非三买
空头：一卖=非一卖｜二卖=非二卖｜三卖=非三卖
当前无确认的任何一类买卖点，结构处于中枢内方向不明的状态，需等待后续笔确认做出方向选择。

四、强弱判断
当前方向向下，且价格处于中枢内部，结构偏弱。价格在中枢内震荡，未能有效站上 ZG，也未能向下跌破 ZD，走势处于方向选择阶段。量能需人工确认，若无明显放量配合，则突破预期需降低。

五、后续推演（2–3 种情景）
第一种：向上突破中枢上沿 ZG=4190.87 并站稳 → 结构转强，有望向上挑战近期确认笔高点 4197.23，并进一步观察离开段力度。
第二种：向下跌破中枢下沿 ZD=4002.78 且不能收回 → 结构转弱，调整压力加大，下方的支撑需关注近期确认笔低点 3815.84。
第三种：继续在中枢区间 ZG=4190.87 与 ZD=4002.78 内震荡 → 中枢盘整延续，方向选择将继续推迟，观察上下沿得失即可。

以上为缠论结构分析与推演，不构成投资建议。

### 2026-06-10 考察共识阶段！

- 状态: ok
- 真人倾向: 偏空/调整
- 客观活跃买卖点: `[]`
- 模板评分: `{'direction': 'diff', 'direction_attribution': 'daily_match', 'generated_bias': '多空并陈/震荡', 'human_bias': '偏空/调整', 'term_overlap': 4, 'generated_terms': ['一买', '一卖', '三买', '三卖', '中枢', '二买', '二卖', '背驰', '趋势', '量能'], 'human_terms': ['三卖', '中枢', '二买', '反抽', '底分型', '线段', '背驰', '震荡'], 'buy_sell_overlap': 0, 'objective_active_buy_sell': [], 'confirmed_bsp_claims': [], 'candidate_bsp_mentions': [], 'human_confirmed_bsp': [], 'invented_confirmed_bsp': [], 'invented_buy_sell_terms': [], 'scenario_count': 4, 'unsourced_prices': []}`
- LLM评分: `{'direction': 'direct', 'direction_attribution': 'true_conflict', 'generated_bias': '偏空/调整', 'human_bias': '偏空/调整', 'term_overlap': 5, 'generated_terms': ['一买', '一卖', '三买', '三卖', '中枢', '二买', '二卖', '背驰', '量能', '震荡'], 'human_terms': ['三卖', '中枢', '二买', '反抽', '底分型', '线段', '背驰', '震荡'], 'buy_sell_overlap': 0, 'objective_active_buy_sell': [], 'confirmed_bsp_claims': [], 'candidate_bsp_mentions': [], 'human_confirmed_bsp': [], 'invented_confirmed_bsp': [], 'invented_buy_sell_terms': [], 'scenario_count': 12, 'unsourced_prices': [4000.0]}`

**LLM 输出摘录**

【上证指数 缠论解盘 · 2026-06-10】

一、日线结构
方向向下，价格运行在中枢下方；当前中枢 ZG=4197.23，ZD=4002.78（3笔），结构已确认。
日线处于向下一笔调整中，且已跌破中枢下沿，结构偏弱；截至最新收盘，当前未见明显背驰。

二、次级别推演
次级别数据不可用，本段略；以下推演基于日线结构。

三、买卖点状态
多头：一买=非一买｜二买=非二买｜三买=非三买
空头：一卖=非一卖｜二卖=非二卖｜三卖=非三卖
日线当前无确认的一、二、三类买卖点。日线级二买/二卖缺少有效确认样本，仅作为观察条件，不构成确认买卖点。

四、强弱判断
方向向下且价格处于中枢下方，调整压力仍在，整体结构偏弱。后续能否转强需观察指数能否重新收回中枢下沿 ZD=4002.78 一线。量能与板块轮动需人工确认。

五、后续推演（2–3 种情景）
第一种：指数出现向上修复，若能重新站上并站稳中枢下沿 ZD=4002.78，弱势将有所缓和，并向中枢内震荡演化。
第二种：若继续受制于 ZD=4002.78 且重心下移，调整压力将延续，需观察最近确认低点 3794.68 的支撑力度。
第三种：若围绕 4000 附近以温和整理形式反复，则暂时以中枢下方震荡观察，直到出现有效站上 ZD 或跌破 3794.68 的方向选择。

免责声明：以上为缠论结构分析与推演，不构成投资建议。