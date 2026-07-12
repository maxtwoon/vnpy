# 风控参数敏感性报告

<!-- RESEARCH-ONLY / NOT PROMOTION EVIDENCE -->

> ⚠️ **RESEARCH ONLY — NOT PROMOTION EVIDENCE**
>
> This report was produced using the historical out-of-sample window `2022-01-01~2026-04-24`, which was repeatedly used for parameter selection. High-precision weights such as `0.847` and any bare `GOAL PASSED` rows are gate-fitting signatures, not evidence of a robust trading discovery. This artifact is retained as negative / contaminated evidence only.
>
> - `is_promotion_evidence`: False
> - `research_only`: True
> - `used_data_windows`: `["2022-01-01~2026-04-24"]`
> - `decision_data_windows`: ['2026-04-24~present', 'SimNow observation']
> - `note`: Future validation must use post-2026-04-24 incremental data and SimNow observation before any promotion claim can be considered.


- 生成时间：2026-06-17T15:45:38.000884+00:00
- 区间：2024-01-01 ~ 2024-12-31
- 品种：RB888 / SC888
- 说明：本报告用于判断策略是否对风控参数过度敏感，不作为调参最优解。

| 品种 | 变体 | 交易数 | 收益率 | 相对基线 | 最大回撤 | 胜率 | 盈亏比 |
|---|---|---:|---:|---:|---:|---:|---:|
| RB888 | baseline | 9 | -2.21% | 0.00% | 2.91% | 22.22% | 0.24 |
| RB888 | stop_loss_tight | 11 | -1.90% | 0.31% | 2.58% | 27.27% | 0.26 |
| RB888 | stop_loss_loose | 8 | -2.17% | 0.04% | 3.34% | 25.00% | 0.23 |
| RB888 | timeout_short | 9 | -2.21% | 0.00% | 2.91% | 22.22% | 0.24 |
| RB888 | timeout_long | 9 | -2.21% | 0.00% | 2.91% | 22.22% | 0.24 |
| RB888 | trailing_tight | 11 | -0.61% | 1.59% | 1.81% | 36.36% | 0.51 |
| RB888 | trailing_loose | 9 | -2.44% | -0.23% | 3.14% | 22.22% | 0.10 |
| SC888 | baseline | 19 | -1.25% | 0.00% | 3.49% | 42.11% | 0.90 |
| SC888 | stop_loss_tight | 21 | -1.07% | 0.18% | 2.85% | 38.10% | 0.85 |
| SC888 | stop_loss_loose | 18 | -0.92% | 0.33% | 4.85% | 50.00% | 0.97 |
| SC888 | timeout_short | 19 | -1.25% | 0.00% | 3.49% | 42.11% | 0.90 |
| SC888 | timeout_long | 19 | -1.25% | 0.00% | 3.49% | 42.11% | 0.90 |
| SC888 | trailing_tight | 21 | 0.43% | 1.68% | 1.94% | 57.14% | 1.32 |
| SC888 | trailing_loose | 18 | -1.04% | 0.21% | 3.55% | 38.89% | 1.05 |

## 判读规则

- 若轻微调整止损/超时/移动止损即导致收益符号大幅翻转，应优先回到信号定义和出场语义审查。
- 若所有变体都亏损，问题通常不在单一风控参数，而在入场质量或适用品种。
- 若只有某个参数族显著改善，可再做更细网格；当前报告只做第一层稳定性筛查。
