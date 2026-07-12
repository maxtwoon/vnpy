# Final Candidate Robustness Check

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
- db_path: `D:\BaiduNetdiskDownload\新数据库\ssquant数据库_20260425\kline_data.db`

## Cost/Slippage 2x Symbol Sets

- symbol sets: `4/6`
- all5 WF: `7/9`

| set | pass | trades | PF | drawdown | sharpe | calmar | WF | failing_checks |
|---|---|---:|---:|---:|---:|---:|---:|---|
| all5 | True | 128 | 1.80 | 0.50% | 1.30 | 2.39 | 7/9 | - |
| no_RB | True | 114 | 1.85 | 0.60% | 1.27 | 2.35 | 7/9 | - |
| no_SC | True | 81 | 3.13 | 0.53% | 1.73 | 3.55 | 6/9 | - |
| core_AP_A_ZN | True | 67 | 3.61 | 0.71% | 1.72 | 3.39 | 6/9 | - |
| no_A | False | 102 | 1.31 | 0.65% | 0.54 | 0.84 | 5/9 | walk_forward_ge_2_3, risk_adjusted_gt_buy_hold |
| no_ZN | False | 99 | 1.86 | 0.58% | 1.50 | 2.27 | 5/9 | walk_forward_ge_2_3 |

## Dominant Symbol Audit

- passed: `True`
- AP dominant in OOS: `AP888`

| requested | symbol | rows | start | end |
|---|---|---:|---|---|
| AP888 | AP888 | 221980 | 2022-01-04 09:00:00 | 2026-02-13 14:59:00 |
| AP888 | ap888 | 9605 | 2026-02-24 09:00:00 | 2026-04-24 14:59:00 |
| RB888 | rb888 | 355766 | 2022-01-04 09:00:00 | 2026-04-24 22:59:00 |
| SC888 | sc888 | 561867 | 2022-01-04 09:00:00 | 2026-04-25 02:29:00 |
| A888 | a888 | 353373 | 2022-01-04 09:00:00 | 2026-04-24 22:59:00 |
| ZN888 | zn888 | 476505 | 2022-01-04 09:00:00 | 2026-04-25 00:59:00 |

## Final Checks

| check | pass |
|---|---|
| dominant_symbol_audit | True |
| cost_slippage_2x_symbol_sets | True |

**ROBUSTNESS PASSED: `True`**