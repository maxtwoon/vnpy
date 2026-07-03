# chan-pan-analysis LLM 真评估报告

- 生成时间: 2026-06-18 02:11:21
- 模式: DeepSeek 实际生成
- 样本数: `1`；LLM 已评估: `1`
- 数据源: `D:\repo\vnpy\examples\czsc_strategy\skill_build\mapping\eval_records.jsonl` + `D:\repo\vnpy\examples\czsc_strategy\skill_build\sh000001_daily.csv`
- 输出 JSONL: `D:\repo\vnpy\examples\czsc_strategy\skill_build\reports\llm_skill_eval_results.jsonl`

## 汇总

- LLM 方向分布: `{'diff': 1}`
- LLM 方向归因: `{'intraday_mismatch': 1}`
- LLM 结构术语平均重合数: `5.00`
- LLM 买卖点平均重合数: `0.00`
- LLM 平均情景覆盖计数: `13.00`
- LLM 编造确认买卖点总数: `0`
- 模板基线结构术语平均重合数: `5.00`
- 模板基线买卖点平均重合数: `0.00`
- 模板基线平均情景覆盖计数: `4.00`

## 逐日对比

| 日期 | 标题 | LLM方向 | 方向归因 | 模板方向 | LLM术语 | 模板术语 | LLM未溯源价位 | 状态 |
|---|---|---:|---|---:|---:|---:|---|---|
| 2026-03-26 | 关注1分钟完成情况！ | diff | intraday_mismatch | diff | 5 | 5 | [] | ok |

## 样本详情

### 2026-03-26 关注1分钟完成情况！

- 状态: ok
- 真人倾向: 偏多/上行
- 客观活跃买卖点: `[]`
- 模板评分: `{'direction': 'diff', 'direction_attribution': 'intraday_mismatch', 'generated_bias': '多空并陈/震荡', 'human_bias': '偏多/上行', 'term_overlap': 5, 'generated_terms': ['一买', '一卖', '三买', '三卖', '中枢', '二买', '二卖', '背驰', '趋势', '量能'], 'human_terms': ['中枢', '二买', '盘整', '线段', '背驰', '趋势', '量能', '震荡', '顶分型'], 'buy_sell_overlap': 0, 'objective_active_buy_sell': [], 'confirmed_bsp_claims': [], 'candidate_bsp_mentions': [], 'human_confirmed_bsp': [], 'invented_confirmed_bsp': [], 'invented_buy_sell_terms': [], 'scenario_count': 4, 'unsourced_prices': []}`
- LLM评分: `{'direction': 'diff', 'direction_attribution': 'intraday_mismatch', 'generated_bias': '偏空/调整', 'human_bias': '偏多/上行', 'term_overlap': 5, 'generated_terms': ['一买', '一卖', '三买', '三卖', '中枢', '二买', '二卖', '承接', '离开段', '背驰', '量能', '震荡'], 'human_terms': ['中枢', '二买', '盘整', '线段', '背驰', '趋势', '量能', '震荡', '顶分型'], 'buy_sell_overlap': 0, 'objective_active_buy_sell': [], 'confirmed_bsp_claims': [], 'candidate_bsp_mentions': [], 'human_confirmed_bsp': [], 'invented_confirmed_bsp': [], 'invented_buy_sell_terms': [], 'scenario_count': 13, 'unsourced_prices': []}`

**LLM 输出摘录**

【上证指数 缠论解盘 · 2026-03-26】

一、日线结构
方向=向下，中枢位置=中枢下方；中枢 ZG=4190.87 ZD=4002.78（3笔）。
当前价格运行在中枢下方，调整压力仍在。自确认高点 4197.23 以来的向下一笔延续中，最新收盘 3889.08 已有效跌穿中枢下沿 ZD=4002.78，中枢下沿已从支撑转为阻力。结构上当前未见明显背驰，空方仍占据主导。

二、次级别推演
次级别数据不可用，本段略；以下推演基于日线结构。

三、买卖点状态
多头：一买=非一买｜二买=非二买｜三买=非三买
空头：一卖=非一卖｜二卖=非二卖｜三卖=非三卖
当前无已确认的买卖点。日线处于跌破中枢后的离开段，多空均未形成标准转折信号。日线级二买/二卖的确认需要更清晰的次级别结构配合，当前仅作观察条件。

四、强弱判断
日线确认笔方向已转弱，价格有效跌破中枢下沿，多头风控状态为“结构失效”，整体偏弱。下方最近的结构参考为确认笔低点 3815.84，若该位置失守，则调整级别可能扩大。量能与板块轮动需人工确认。

五、后续推演（2–3 种情景）
第一种：向上修复，价格重新站回中枢下沿 ZD=4002.78 之上，则弱势结构出现缓和信号，后续观察能否继续向上试探中枢上沿 ZG=4190.87。
第二种：价格在 ZD 之下延续弱势，下方首先观察确认笔低点 3815.84 的承接力度；若跌破该点，则调整延续，空头结构完好。
第三种：价格在 3815.84 与 4002.78 之间形成震荡，中枢已下移，此时更重视边界得失，等待方向重新选择。

免责声明：以上为缠论结构分析与推演，不构成投资建议。