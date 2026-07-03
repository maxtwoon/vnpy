# chan-pan-analysis LLM 真评估报告

- 生成时间: 2026-06-17 21:05:53
- 模式: DeepSeek 实际生成
- 样本数: `1`；LLM 已评估: `1`
- 数据源: `D:\repo\vnpy\examples\czsc_strategy\skill_build\mapping\eval_records.jsonl` + `D:\repo\vnpy\examples\czsc_strategy\skill_build\sh000001_daily.csv`
- 输出 JSONL: `D:\repo\vnpy\examples\czsc_strategy\skill_build\reports\llm_skill_eval_results.jsonl`

## 汇总

- LLM 方向分布: `{'direct': 1}`
- LLM 方向归因: `{'daily_match': 1}`
- LLM 结构术语平均重合数: `3.00`
- LLM 买卖点平均重合数: `0.00`
- LLM 平均情景覆盖计数: `14.00`
- LLM 编造确认买卖点总数: `0`
- 模板基线结构术语平均重合数: `4.00`
- 模板基线买卖点平均重合数: `0.00`
- 模板基线平均情景覆盖计数: `10.00`

## 逐日对比

| 日期 | 标题 | LLM方向 | 方向归因 | 模板方向 | LLM术语 | 模板术语 | LLM未溯源价位 | 状态 |
|---|---|---:|---|---:|---:|---:|---|---|
| 2025-07-29 | 继续上行！ | direct | daily_match | direct | 3 | 4 | [] | ok |

## 样本详情

### 2025-07-29 继续上行！

- 状态: ok
- 真人倾向: 偏多/上行
- 客观活跃买卖点: `['三买']`
- 模板评分: `{'direction': 'direct', 'direction_attribution': 'daily_match', 'generated_bias': '偏多/上行', 'human_bias': '偏多/上行', 'term_overlap': 4, 'generated_terms': ['一买', '一卖', '三买', '三卖', '中枢', '二买', '二卖', '离开段', '背驰', '趋势', '量能', '震荡'], 'human_terms': ['中枢', '盘整', '线段', '背驰', '趋势', '量能'], 'buy_sell_overlap': 0, 'objective_active_buy_sell': ['三买'], 'confirmed_bsp_claims': [], 'candidate_bsp_mentions': ['三买'], 'human_confirmed_bsp': [], 'invented_confirmed_bsp': [], 'invented_buy_sell_terms': [], 'scenario_count': 10, 'unsourced_prices': []}`
- LLM评分: `{'direction': 'direct', 'direction_attribution': 'daily_match', 'generated_bias': '偏多/上行', 'human_bias': '偏多/上行', 'term_overlap': 3, 'generated_terms': ['一买', '一卖', '三买', '三卖', '中枢', '二买', '二卖', '离开段', '背驰', '量能', '震荡'], 'human_terms': ['中枢', '盘整', '线段', '背驰', '趋势', '量能'], 'buy_sell_overlap': 0, 'objective_active_buy_sell': ['三买'], 'confirmed_bsp_claims': [], 'candidate_bsp_mentions': ['三买'], 'human_confirmed_bsp': [], 'invented_confirmed_bsp': [], 'invented_buy_sell_terms': [], 'scenario_count': 14, 'unsourced_prices': []}`

**LLM 输出摘录**

【上证指数 缠论解盘 · 2025-07-29】

一、日线结构
方向=向上，中枢位置=中枢上方；中枢 ZG=3413.51 ZD=3347.65（3笔）。当前向上一笔延续，价格运行于已确认中枢上方，且暂未出现背驰，结构偏强；后续重点观察离开段力度，以及能否持续站稳中枢上沿。

二、次级别推演
次级别数据不可用，本段略；以下推演基于日线结构。

三、买卖点状态
多头：一买=非一买｜二买=非二买｜三买=离开中枢
空头：一卖=非一卖｜二卖=非二卖｜三卖=非三卖

当前最相关的状态是三买处于离开中枢阶段。价格已向上脱离日线中枢，但尚未完成回抽确认；若后续回抽不跌回中枢（守住 ZG=3413.51），则具备构成第三类买点的条件，属于观察阶段。

四、强弱判断
已确认结构显示在中枢上方运行，且无背驰信号，多头风控结构完好，整体偏强。量能及板块轮动情况需人工确认。

五、后续推演（2–3 种情景）
第一种：向上延续，突破最近确认笔高点 3613.02，则向上笔延续，离开段强度提高，后续可进一步观察是否构成三买确认。
第二种：价格回落，但始终不跌回中枢上沿 ZG=3413.51，则形成三买观察结构，若伴随确认笔上攻，偏强延续概率提高。
第三种：价格回落并重新进入中枢（跌破 ZG=3413.51），则强度下降，市场重新转入中枢震荡，需观察中枢下沿 ZD=3347.65 是否有效支撑。

免责声明：以上为缠论结构分析与推演，不构成投资建议。