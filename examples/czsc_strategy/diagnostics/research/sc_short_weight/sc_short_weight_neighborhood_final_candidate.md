# Final Candidate SC Short Weight Neighborhood

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


- candidate: `sc075_a_zn010_sc3buy_half + A/AP trailing 250/0.20`

| multiplier | pass | trades | PF | drawdown | sharpe | calmar | WF | bh_sharpe | bh_calmar |
|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 0.75 | True | 128 | 2.13 | 0.52% | 1.85 | 3.41 | 7/9 | 0.88 | 1.35 |
| 0.8 | True | 128 | 2.14 | 0.53% | 1.87 | 3.37 | 7/9 | 0.88 | 1.35 |
| 0.847 | True | 128 | 2.15 | 0.55% | 1.89 | 3.34 | 7/9 | 0.88 | 1.35 |
| 0.85 | True | 128 | 2.15 | 0.55% | 1.89 | 3.33 | 7/9 | 0.88 | 1.35 |
| 0.9 | True | 128 | 2.16 | 0.56% | 1.91 | 3.30 | 6/9 | 0.88 | 1.35 |
| 1.0 | False | 128 | 2.17 | 0.59% | 1.95 | 3.23 | 5/9 | 0.88 | 1.35 |