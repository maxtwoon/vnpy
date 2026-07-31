# reason_code 报告检查

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


- 允许枚举：other / risk_exit / signal_exit / stop_loss / timeout / trailing_stop / unknown

| 文件 | 检查交易数 | 缺失 | 非法 | 状态 |
|---|---:|---:|---:|---|
| `backtest_matrix_20220101_20260424.json` | 0 | 0 | 0 | 通过 |
| `pnl_attribution_20220101_20260424.json` | 378 | 0 | 0 | 通过 |
| `risk_param_sensitivity_20240101_20241231.json` | 0 | 0 | 0 | 通过 |
| `second_buy_anchor_audit_20220101_20260424.json` | 73 | 0 | 0 | 通过 |
| `second_buy_entry_position_audit_20220101_20260424.json` | 73 | 0 | 0 | 通过 |
| `second_buy_stop_loss_scan_20220101_20260424.json` | 0 | 0 | 0 | 通过 |
| `trailing_grid_20240101_20241231.json` | 0 | 0 | 0 | 通过 |
| `trailing_oos_all_symbols_20250101_20260424.json` | 0 | 0 | 0 | 通过 |
| `trailing_oos_validation_20250101_20260424.json` | 0 | 0 | 0 | 通过 |
