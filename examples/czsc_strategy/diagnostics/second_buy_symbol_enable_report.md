# 二买分品种启用建议

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


- 来源：`second_buy_stop_loss_scan_20220101_20260424.json`
- 口径：取每个品种在 stop_loss_2buy 扫描中的二买累计收益最优档，再给出启用建议。

| 品种 | 最优 stop_loss_2buy | 二买交易 | 二买累计收益 | 胜率 | 盈亏比 | 止损率 | 建议 |
|---|---:|---:|---:|---:|---:|---:|---|
| AP888 | 350 | 4 | 17.55% | 100.00% | inf | 0.00% | 观察：样本少 |
| RB888 | 200 | 6 | -13.54% | 0.00% | 0.00 | 100.00% | 禁用候选 |
| SC888 | 350 | 24 | -32.17% | 45.83% | 0.47 | 50.00% | 禁用候选 |
| A888 | 300 | 7 | 6.21% | 57.14% | 1.60 | 42.86% | 可启用 |
| ZN888 | 300 | 12 | 10.88% | 66.67% | 1.72 | 33.33% | 可启用 |

## 说明

- 本报告只给研究建议，不自动修改策略配置。
- `禁用候选` 表示下一步应审二买确认形态；不是立即删除代码。
