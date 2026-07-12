# 移动止损样本外验证

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


- 生成时间：2026-06-17T17:01:42.580608+00:00
- 区间：2025-01-01 ~ 2026-04-24
- 对照：默认 `trailing_start_bp=300 / trailing_drawback_pct=0.25`
- 调参：RB888 使用 `250 / 0.15`；SC888 使用 `150 / 0.15`

| 品种 | 版本 | 参数 | 交易数 | 收益率 | 相对基线 | 最大回撤 | 胜率 | 盈亏比 |
|---|---|---|---:|---:|---:|---:|---:|---:|
| RB888 | baseline | 300/0.25 | 13 | -1.54% | 0.00% | 3.17% | 38.46% | 0.58 |
| RB888 | tuned | 250/0.15 | 13 | -1.52% | 0.01% | 3.09% | 38.46% | 0.59 |
| SC888 | baseline | 300/0.25 | 32 | -11.24% | 0.00% | 11.56% | 31.25% | 0.28 |
| SC888 | tuned | 150/0.15 | 33 | -9.30% | 1.94% | 10.62% | 42.42% | 0.35 |

## 判读

- 若 tuned 在样本外继续改善收益与回撤，才进入更大范围品种验证。
- 若 tuned 样本外退化，2024 细网格改善更可能是阶段性拟合。
