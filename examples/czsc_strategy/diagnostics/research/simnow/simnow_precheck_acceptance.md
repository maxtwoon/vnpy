# SimNow Precheck Acceptance

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


**PASSED: `True`**

## Gates

| gate | result |
|---|---:|
| base SC neighborhood | 6/6 |
| base all5 WF | 7/9 |
| base symbol sets | 6/6 |
| cost2 SC neighborhood | 6/6 |
| cost2 all5 WF | 7/9 |
| cost2 symbol sets | 4/6 |
| date variants | 4/4 |

## Risk Snapshot

| metric | value |
|---|---:|
| max_single_day_loss_pct | -0.29% |
| max_consecutive_loss_days | 6 |
| max_drawdown_pct | -1.32% |
| max_gross_exposure | 28.00% |
| max_net_exposure_abs | 28.00% |
| both_long_short_days | 231 |
| symbol_top1_abs_share | 44.79% |
| strategy_top1_abs_share | 65.60% |

## Checks

| check | pass |
|---|---|
| base_gate | True |
| cost2_symbol_sets | True |
| cost2_sc_neighbor | True |
| date_variants | True |
| dominant_symbol_audit | True |
| risk_report_present | True |
| pytest | True |