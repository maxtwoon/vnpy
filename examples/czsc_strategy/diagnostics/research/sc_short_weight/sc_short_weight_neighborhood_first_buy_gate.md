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
| 0.75 | True | 103 | 1.50 | 0.93% | 1.13 | 1.36 | 7/9 | 0.88 | 1.35 |
| 0.8 | True | 103 | 1.51 | 0.92% | 1.16 | 1.40 | 6/9 | 0.88 | 1.35 |
| 0.847 | True | 103 | 1.52 | 0.92% | 1.18 | 1.44 | 6/9 | 0.88 | 1.35 |
| 0.85 | True | 103 | 1.52 | 0.92% | 1.18 | 1.44 | 6/9 | 0.88 | 1.35 |
| 0.9 | True | 103 | 1.53 | 0.91% | 1.21 | 1.49 | 6/9 | 0.88 | 1.35 |
| 1.0 | False | 103 | 1.56 | 0.89% | 1.25 | 1.58 | 5/9 | 0.88 | 1.35 |