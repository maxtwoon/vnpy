# czsc vendor 说明

<!-- RESEARCH-ONLY / NOT PROMOTION EVIDENCE -->

`chan_strategy/vendor/` 不是一个完整的第三方库副本，而是**文件级 vendor**：只包含 `echarts_plot.py`（及配套的 `echarts.min.js`）一个模块，用于兼容 czsc 1.0 移除的 `kline_pro.echarts_plot` 功能。

## Vendor 原因

- czsc 0.9.51 在 `czsc.utils.echarts_plot` 中提供了 `kline_pro` 函数，用于生成可交互的 K 线 + 笔/分型/买卖点图表。
- czsc ≥1.0.0rc8 已移除该模块（同时移除了 `czsc.utils.ta` 等辅助模块）。
- 当前 `chan_strategy/html_report.py` 的可视化报告仍依赖 `kline_pro` 的输出格式，因此将最小必要实现 vendored 到本地，避免被上游版本升级打断。

## 来源与范围

| 项目 | 说明 |
|------|------|
| 来源 | `czsc 0.9.51` 的 `kline_pro.echarts_plot` |
| 保留函数 | `kline_pro`、`SMA`、`EMA`、`MACD` |
| 移除内容 | 其他未使用的绘图辅助函数、原始 `czsc.utils.ta` 的其余指标 |
| 许可证 | MIT（czsc 项目，https://github.com/waditu/czsc） |
| 变更 | ① `Operate` 改为从 `czsc` 顶层命名空间导入；② 仅保留 `chan_strategy` 实际消费的功能 |

## 版本 guard

本目录 `requirements.txt` 中固定：

```text
czsc==1.0.0rc8
pyecharts==2.1.0
```

- `czsc==1.0.0rc8` 是当前 `chan_strategy` 的**目标依赖版本**；`_get_confirmed_bi_list` 等内部逻辑依赖 czsc 暴露的 `finished_bis` / `last_bi_extend` API，不建议自行升级。
- `pyecharts==2.1.0` 与 vendored 的 `echarts_plot.py` 输出格式匹配；升级前需验证 HTML 报告渲染。

## 维护原则

- 若未来 czsc 重新提供等价功能，可考虑移除 vendor 并迁移到官方 API，但需通过 `tests/unit/test_html_report.py` 回归测试。
- 不要往 `vendor/` 添加与 `kline_pro` 无关的第三方代码；需要新依赖时应优先通过 `requirements.txt` 声明。
