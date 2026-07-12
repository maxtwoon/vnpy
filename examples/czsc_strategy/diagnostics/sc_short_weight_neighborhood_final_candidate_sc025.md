# Final Candidate SC Short Weight Neighborhood

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


- candidate: `sc025_a_zn010_sc3buy_half + A/AP trailing 250/0.20`

| multiplier | pass | trades | PF | drawdown | sharpe | calmar | WF | bh_sharpe | bh_calmar |
|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 0.1 | True | 128 | 2.01 | 0.47% | 1.49 | 2.96 | 7/9 | 0.88 | 1.35 |
| 0.2 | True | 128 | 2.03 | 0.45% | 1.56 | 3.19 | 7/9 | 0.88 | 1.35 |
| 0.25 | True | 128 | 2.04 | 0.44% | 1.59 | 3.32 | 7/9 | 0.88 | 1.35 |
| 0.3 | True | 128 | 2.05 | 0.44% | 1.62 | 3.44 | 7/9 | 0.88 | 1.35 |
| 0.4 | True | 128 | 2.07 | 0.42% | 1.68 | 3.71 | 7/9 | 0.88 | 1.35 |
| 0.5 | True | 128 | 2.09 | 0.44% | 1.73 | 3.67 | 7/9 | 0.88 | 1.35 |