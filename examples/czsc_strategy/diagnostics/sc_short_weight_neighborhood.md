# SC Short Weight Neighborhood

<!-- RESEARCH-ONLY / NOT PROMOTION EVIDENCE -->

> ⚠️ **RESEARCH ONLY — NOT PROMOTION EVIDENCE**
>
> This report was produced using the historical out-of-sample window `2022-01-01~2026-04-24`, which was repeatedly used for parameter selection. High-precision weights such as `0.847` and any `GOAL PASSED` rows are gate-fitting signatures, not evidence of a robust trading discovery. This artifact is retained as negative / contaminated evidence only.
>
> - `is_promotion_evidence`: False
> - `research_only`: True
> - `used_data_windows`: `["2022-01-01~2026-04-24"]`
> - `decision_data_windows`: ['2026-04-24~present', 'SimNow observation']
> - `note`: Future validation must use post-2026-04-24 incremental data and SimNow observation before any promotion claim can be considered.


| multiplier | pass | trades | PF | drawdown | sharpe | calmar | WF | bh_sharpe | bh_calmar |
|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 0.75 | False | 114 | 1.46 | 0.97% | 1.09 | 1.27 | 6/9 | 0.88 | 1.35 |
| 0.8 | False | 114 | 1.47 | 0.96% | 1.12 | 1.31 | 6/9 | 0.88 | 1.35 |
| 0.847 | True | 114 | 1.48 | 0.95% | 1.14 | 1.35 | 6/9 | 0.88 | 1.35 |
| 0.85 | False | 114 | 1.48 | 0.95% | 1.14 | 1.35 | 5/9 | 0.88 | 1.35 |
| 0.9 | False | 114 | 1.49 | 0.94% | 1.16 | 1.39 | 5/9 | 0.88 | 1.35 |
| 1.0 | False | 114 | 1.51 | 0.93% | 1.21 | 1.48 | 5/9 | 0.88 | 1.35 |