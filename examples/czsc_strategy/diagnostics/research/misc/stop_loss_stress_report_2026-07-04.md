# Stop-Loss Stress Diagnostic Report

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


- Date: `2026-07-04`
- Generated at: `2026-07-04T15:35:42.518306+00:00`
- Stop-loss budget: `300bp`
- Penalty slippage: `10bp`
- Status: `partial`

> Diagnostic only, not a trading recommendation.

## Executive Summary

| scenario | status | trade_count | affected_count | worst_loss | overshoot_count | max_overshoot_multiple | avg_loss |
|---|---:|---:|---:|---:|---:|---:|---:|
| observed_close | ok | 292 | 65 | -15.19% | 65 | 5.0633 | -0.19% |
| intrabar_trigger | unavailable | 0 | 0 | N/A | 0 | N/A | N/A |
| gap_open_exit | unavailable | 0 | 0 | N/A | 0 | N/A | N/A |
| penalty_slippage | ok | 292 | 68 | -15.29% | 68 | 5.0966 | -0.29% |

## Trade Counts

- raw_trade_count: `606`
- unique_trade_count: `292`
- duplicate_trade_count: `314`

## Scenario: observed_close

- status: `ok`
- trade_count: `292`
- affected_trade_count: `65`
- affected_symbols: `A888, AP888, RB888, SC888, ZN888`
- worst_loss_pct: `-15.1898`
- overshoot_count: `65`
- max_overshoot_multiple: `5.0633`
- avg_loss_pct: `-0.1921`
- unavailable_count: `0`
- unavailable_reasons: `{}`

### Sample Worst Trades

| symbol | strategy | open_dt | close_dt | pnl_pct | stressed_exit | source |
|---|---|---|---:|---:|---|---|
| AP888 | 一买多头 | 2022-03-24T14:29:00 | 2022-03-30T09:29:00 | -15.19% | 8401.0000 | pnl_attribution_20220101_20260424.json |
| SC888 | 二买多头 | 2026-04-07T14:59:00 | 2026-04-08T09:29:00 | -12.60% | N/A | extreme_trade_contribution_audit.json |
| SC888 | 三买多头 | 2026-04-08T01:59:00 | 2026-04-08T09:29:00 | -11.76% | 625.2000 | pnl_attribution_20220101_20260424.json |

## Scenario: intrabar_trigger

- status: `unavailable`
- trade_count: `0`
- affected_trade_count: `0`
- affected_symbols: `N/A`
- worst_loss_pct: `N/A`
- overshoot_count: `0`
- max_overshoot_multiple: `N/A`
- avg_loss_pct: `N/A`
- unavailable_count: `292`
- unavailable_reasons: `{'missing_direction': 12, 'missing_dates': 280}`

### Sample Worst Trades

| symbol | strategy | open_dt | close_dt | pnl_pct | stressed_exit | source |
|---|---|---|---:|---:|---|---|

## Scenario: gap_open_exit

- status: `unavailable`
- trade_count: `0`
- affected_trade_count: `0`
- affected_symbols: `N/A`
- worst_loss_pct: `N/A`
- overshoot_count: `0`
- max_overshoot_multiple: `N/A`
- avg_loss_pct: `N/A`
- unavailable_count: `292`
- unavailable_reasons: `{'missing_direction': 12, 'missing_dates': 280}`

### Sample Worst Trades

| symbol | strategy | open_dt | close_dt | pnl_pct | stressed_exit | source |
|---|---|---|---:|---:|---|---|

## Scenario: penalty_slippage

- status: `ok`
- trade_count: `292`
- affected_trade_count: `68`
- affected_symbols: `A888, AP888, RB888, SC888, ZN888`
- worst_loss_pct: `-15.2898`
- overshoot_count: `68`
- max_overshoot_multiple: `5.0966`
- avg_loss_pct: `-0.2921`
- unavailable_count: `0`
- unavailable_reasons: `{}`

### Sample Worst Trades

| symbol | strategy | open_dt | close_dt | pnl_pct | stressed_exit | source |
|---|---|---|---:|---:|---|---|
| AP888 | 一买多头 | 2022-03-24T14:29:00 | 2022-03-30T09:29:00 | -15.29% | 8391.1130 | pnl_attribution_20220101_20260424.json |
| SC888 | 二买多头 | 2026-04-07T14:59:00 | 2026-04-08T09:29:00 | -12.70% | N/A | extreme_trade_contribution_audit.json |
| SC888 | 三买多头 | 2026-04-08T01:59:00 | 2026-04-08T09:29:00 | -11.86% | 624.4928 | pnl_attribution_20220101_20260424.json |

## Worst Trades Across Scenarios

| symbol | strategy | open_dt | close_dt | pnl_pct | scenario | source |
|---|---|---|---:|---:|---|---|
| AP888 | 一买多头 | 2022-03-24T14:29:00 | 2022-03-30T09:29:00 | -15.29% | penalty_slippage | pnl_attribution_20220101_20260424.json |
| SC888 | 二买多头 | 2026-04-07T14:59:00 | 2026-04-08T09:29:00 | -12.70% | penalty_slippage | extreme_trade_contribution_audit.json |
| SC888 | 三买多头 | 2026-04-08T01:59:00 | 2026-04-08T09:29:00 | -11.86% | penalty_slippage | pnl_attribution_20220101_20260424.json |
| SC888 | 一买多头 | 2026-04-02T23:29:00 | 2026-04-08T09:29:00 | -11.49% | penalty_slippage | pnl_attribution_20220101_20260424.json |
| SC888 | 三买多头 | 2026-03-16T10:59:00 | 2026-03-16T21:29:00 | -5.75% | penalty_slippage | pnl_attribution_20220101_20260424.json |

## Unavailable Trades

| symbol | strategy | open_dt | close_dt | reason | source |
|---|---|---|---|---|---|
| SC888 | 二买多头 | 2026-04-07T14:59:00 | 2026-04-08T09:29:00 | missing_direction | extreme_trade_contribution_audit.json |
| SC888 | 二买多头 | 2022-09-22T21:29:00 | 2022-09-23T21:29:00 | missing_direction | extreme_trade_contribution_audit.json |
| SC888 | 二买多头 | 2022-07-09T00:29:00 | 2022-07-12T21:29:00 | missing_direction | extreme_trade_contribution_audit.json |
| RB888 | 二买多头 | 2023-03-30T10:14:00 | 2023-04-06T09:29:00 | missing_direction | extreme_trade_contribution_audit.json |
| SC888 | 二买多头 | 2025-09-03T14:29:00 | 2025-09-05T21:29:00 | missing_direction | extreme_trade_contribution_audit.json |
| SC888 | 二买多头 | 2022-09-23T21:59:00 | 2022-09-26T14:29:00 | missing_direction | extreme_trade_contribution_audit.json |
| SC888 | 二买多头 | 2026-03-30T21:40:00 | 2026-03-31T09:59:00 | missing_direction | extreme_trade_contribution_audit.json |
| SC888 | 二买多头 | 2026-04-13T14:59:00 | 2026-04-14T21:59:00 | missing_direction | extreme_trade_contribution_audit.json |
| SC888 | 二买多头 | 2025-05-20T14:29:00 | 2025-05-30T09:29:00 | missing_direction | extreme_trade_contribution_audit.json |
| RB888 | 二买多头 | 2025-02-19T09:59:00 | 2025-03-10T13:59:00 | missing_direction | extreme_trade_contribution_audit.json |
| RB888 | 一买多头 | 2025-08-29T09:29:00 | 2025-09-01T09:59:00 | missing_direction | extreme_trade_contribution_audit.json |
| RB888 | 一买多头 | 2025-03-13T21:29:00 | 2025-03-18T14:59:00 | missing_direction | extreme_trade_contribution_audit.json |
| A888 | 三买多头 | 2025-06-27T09:59:00 | 2025-08-21T21:29:00 | missing_dates | platform_holding_attribution_core_AP_A_ZN.json |
| A888 | 二买多头 | 2025-05-08T09:29:00 | 2025-08-12T09:29:00 | missing_dates | platform_holding_attribution_core_AP_A_ZN.json |
| ZN888 | 一买多头 | 2025-11-21T00:29:00 | 2025-12-05T21:29:00 | missing_dates | platform_holding_attribution_core_AP_A_ZN.json |
| ZN888 | 一买多头 | 2025-07-03T11:29:00 | 2025-07-25T00:59:00 | missing_dates | platform_holding_attribution_core_AP_A_ZN.json |
| A888 | 二买多头 | 2025-09-02T13:59:00 | 2025-10-27T10:59:00 | missing_dates | platform_holding_attribution_core_AP_A_ZN.json |
| ZN888 | 一买多头 | 2025-10-17T10:14:00 | 2025-11-05T09:29:00 | missing_dates | platform_holding_attribution_core_AP_A_ZN.json |
| ZN888 | 三买多头 | 2025-08-20T00:29:00 | 2025-12-05T21:59:00 | missing_dates | platform_holding_attribution_core_AP_A_ZN.json |
| A888 | 一买多头 | 2026-03-24T21:59:00 | 2026-04-13T09:59:00 | missing_dates | platform_holding_attribution_core_AP_A_ZN.json |
| ZN888 | 二买多头 | 2025-12-24T22:59:00 | 2026-01-08T10:59:00 | missing_dates | platform_holding_attribution_core_AP_A_ZN.json |
| A888 | 二买多头 | 2025-11-26T09:59:00 | 2026-01-13T14:29:00 | missing_dates | platform_holding_attribution_core_AP_A_ZN.json |
| A888 | 一买多头 | 2025-12-19T21:59:00 | 2026-01-13T21:29:00 | missing_dates | platform_holding_attribution_core_AP_A_ZN.json |
| A888 | 二买多头 | 2025-03-25T14:29:00 | 2025-04-17T21:59:00 | missing_dates | platform_holding_attribution_core_AP_A_ZN.json |
| AP888 | 二买多头 | 2025-05-23T09:29:00 | 2025-07-28T10:14:00 | missing_dates | platform_holding_attribution_core_AP_A_ZN.json |
| RB888 | 三买多头 | 2025-12-08T09:29:00 | 2026-01-07T22:59:00 | missing_dates | platform_holding_attribution_no_SC.json |
| AP888 | 一买多头 | 2022-03-24T14:29:00 | 2022-03-30T09:29:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| AP888 | 一买多头 | 2022-04-20T14:29:00 | 2022-04-22T11:29:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| AP888 | 一买多头 | 2022-04-22T13:59:00 | 2022-05-09T10:59:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| AP888 | 一买多头 | 2022-05-09T11:29:00 | 2022-05-26T10:59:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| AP888 | 一买多头 | 2022-05-26T11:29:00 | 2022-05-30T10:14:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| AP888 | 一买多头 | 2022-05-30T10:59:00 | 2022-06-07T09:29:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| AP888 | 一买多头 | 2022-08-04T14:59:00 | 2022-08-08T14:59:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| AP888 | 一买多头 | 2022-08-09T09:59:00 | 2022-08-30T11:29:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| AP888 | 一买多头 | 2022-09-13T14:29:00 | 2022-09-16T10:14:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| AP888 | 一买多头 | 2022-09-21T10:14:00 | 2022-09-26T11:29:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| AP888 | 一买多头 | 2022-10-31T13:59:00 | 2022-11-07T09:29:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| AP888 | 一买多头 | 2022-11-18T11:29:00 | 2022-11-22T13:59:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| AP888 | 一买多头 | 2022-11-25T09:29:00 | 2022-12-07T14:29:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| AP888 | 一买多头 | 2022-12-20T14:29:00 | 2022-12-21T11:29:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| AP888 | 一买多头 | 2022-12-21T14:29:00 | 2022-12-28T09:29:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| AP888 | 一买多头 | 2022-12-28T09:59:00 | 2023-01-18T09:59:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| AP888 | 一买多头 | 2023-04-18T11:29:00 | 2023-04-24T10:59:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| AP888 | 一买多头 | 2023-05-19T09:29:00 | 2023-05-22T09:29:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| AP888 | 一买多头 | 2023-05-22T09:59:00 | 2023-05-23T09:59:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| AP888 | 一买多头 | 2023-10-30T09:59:00 | 2023-11-27T09:29:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| AP888 | 一买多头 | 2024-02-20T11:29:00 | 2024-03-12T09:29:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| AP888 | 一买多头 | 2024-04-17T09:29:00 | 2024-04-17T11:29:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| AP888 | 一买多头 | 2024-04-19T09:59:00 | 2024-04-19T13:59:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| AP888 | 一买多头 | 2024-08-01T14:29:00 | 2024-08-08T09:29:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| AP888 | 一买多头 | 2024-09-02T10:14:00 | 2024-09-09T09:29:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| AP888 | 一买多头 | 2024-10-14T09:29:00 | 2024-11-01T09:29:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| AP888 | 一买多头 | 2024-12-27T14:59:00 | 2025-01-03T09:59:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| AP888 | 一买多头 | 2025-01-03T10:14:00 | 2025-01-03T11:29:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| AP888 | 一买多头 | 2025-01-06T09:29:00 | 2025-01-10T09:29:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| AP888 | 一买多头 | 2025-05-15T14:59:00 | 2025-05-22T14:59:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| AP888 | 一买多头 | 2025-05-30T09:29:00 | 2025-06-09T14:59:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| AP888 | 一买多头 | 2025-09-15T11:29:00 | 2025-09-29T09:59:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| AP888 | 一买多头 | 2025-11-06T13:59:00 | 2025-11-19T09:59:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| AP888 | 二买多头 | 2022-05-11T09:29:00 | 2022-05-12T14:29:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| AP888 | 二买多头 | 2024-07-15T09:29:00 | 2024-07-30T14:59:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| AP888 | 二买多头 | 2024-10-17T13:59:00 | 2024-11-01T09:29:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| AP888 | 二买多头 | 2025-09-19T09:29:00 | 2025-09-29T09:59:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| AP888 | 三买多头 | 2022-03-14T09:59:00 | 2022-03-15T14:59:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| AP888 | 三买多头 | 2022-05-12T13:59:00 | 2022-05-23T09:59:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| AP888 | 三买多头 | 2022-07-27T09:29:00 | 2022-08-19T09:29:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| AP888 | 三买多头 | 2023-03-03T13:59:00 | 2023-03-13T09:29:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| AP888 | 三买多头 | 2023-08-18T09:29:00 | 2023-08-25T14:29:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| AP888 | 三买多头 | 2023-09-01T09:29:00 | 2023-09-11T09:59:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| AP888 | 三买多头 | 2023-09-15T09:29:00 | 2023-10-09T10:14:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| AP888 | 三买多头 | 2024-11-07T09:29:00 | 2024-11-11T13:59:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| AP888 | 三买多头 | 2024-12-16T09:59:00 | 2024-12-17T13:59:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| AP888 | 三买多头 | 2024-12-17T14:29:00 | 2024-12-18T09:29:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| AP888 | 三买多头 | 2025-07-18T13:59:00 | 2025-07-28T09:59:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| AP888 | 三买多头 | 2025-08-26T09:29:00 | 2025-08-29T09:59:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| AP888 | 三买多头 | 2025-09-19T14:59:00 | 2025-09-29T09:59:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| AP888 | 三买多头 | 2025-11-27T09:59:00 | 2025-12-02T10:59:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| RB888 | 一买多头 | 2022-02-22T10:14:00 | 2022-02-22T14:59:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| RB888 | 一买多头 | 2022-02-23T22:29:00 | 2022-02-24T14:29:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| RB888 | 一买多头 | 2022-02-24T22:29:00 | 2022-02-25T13:59:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| RB888 | 一买多头 | 2022-03-01T14:29:00 | 2022-03-03T13:59:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| RB888 | 一买多头 | 2022-08-22T21:29:00 | 2022-08-30T09:59:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| RB888 | 一买多头 | 2022-10-24T11:29:00 | 2022-10-27T21:29:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| RB888 | 一买多头 | 2022-10-27T21:59:00 | 2022-10-28T22:29:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| RB888 | 一买多头 | 2022-10-28T22:59:00 | 2022-11-07T09:29:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| RB888 | 一买多头 | 2023-02-09T14:29:00 | 2023-02-13T14:29:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| RB888 | 一买多头 | 2023-02-13T14:59:00 | 2023-02-24T10:59:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| RB888 | 一买多头 | 2023-03-28T21:29:00 | 2023-04-03T14:59:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| RB888 | 一买多头 | 2023-04-10T09:59:00 | 2023-04-21T09:29:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| RB888 | 一买多头 | 2023-08-08T10:14:00 | 2023-08-14T09:59:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| RB888 | 一买多头 | 2023-08-30T09:29:00 | 2023-09-05T14:59:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| RB888 | 一买多头 | 2023-09-13T09:59:00 | 2023-09-25T14:29:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| RB888 | 一买多头 | 2024-02-26T21:29:00 | 2024-03-08T22:29:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| RB888 | 一买多头 | 2024-03-08T22:59:00 | 2024-03-13T14:29:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| RB888 | 一买多头 | 2024-09-13T14:29:00 | 2024-09-20T22:59:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| RB888 | 一买多头 | 2024-10-23T21:59:00 | 2024-10-29T11:29:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| RB888 | 一买多头 | 2025-01-10T13:59:00 | 2025-01-21T21:29:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| RB888 | 一买多头 | 2025-02-14T21:59:00 | 2025-02-21T22:29:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| RB888 | 一买多头 | 2025-03-06T21:59:00 | 2025-03-10T22:59:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| RB888 | 一买多头 | 2025-03-11T09:29:00 | 2025-03-20T09:59:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| RB888 | 一买多头 | 2025-08-12T09:29:00 | 2025-08-14T11:29:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| RB888 | 一买多头 | 2025-11-11T10:14:00 | 2025-12-05T21:59:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| RB888 | 一买多头 | 2026-01-26T14:59:00 | 2026-02-06T10:59:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| RB888 | 一买多头 | 2026-02-13T10:59:00 | 2026-03-18T11:29:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| RB888 | 二买多头 | 2022-08-23T14:29:00 | 2022-08-30T09:59:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| RB888 | 二买多头 | 2023-04-07T09:29:00 | 2023-04-20T22:59:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| RB888 | 二买多头 | 2024-01-17T10:59:00 | 2024-02-20T13:59:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| RB888 | 二买多头 | 2024-02-29T21:29:00 | 2024-03-08T22:29:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| RB888 | 二买多头 | 2024-12-26T21:59:00 | 2025-01-08T21:59:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| RB888 | 三买多头 | 2024-11-04T09:59:00 | 2024-11-15T14:29:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| RB888 | 三买多头 | 2025-12-08T09:29:00 | 2026-02-24T09:29:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| SC888 | 一买多头 | 2022-01-27T10:59:00 | 2022-02-07T21:29:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| SC888 | 一买多头 | 2022-03-28T10:14:00 | 2022-03-28T21:29:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| SC888 | 一买多头 | 2022-04-13T01:59:00 | 2022-04-14T09:59:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| SC888 | 一买多头 | 2022-04-21T00:59:00 | 2022-04-21T22:59:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| SC888 | 一买多头 | 2022-05-12T10:59:00 | 2022-05-13T14:59:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| SC888 | 一买多头 | 2022-05-23T09:29:00 | 2022-05-24T13:59:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| SC888 | 一买多头 | 2022-05-24T14:29:00 | 2022-05-25T14:29:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| SC888 | 一买多头 | 2022-05-25T14:59:00 | 2022-05-27T14:29:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| SC888 | 一买多头 | 2022-06-21T14:29:00 | 2022-06-22T10:14:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| SC888 | 一买多头 | 2022-07-01T23:29:00 | 2022-07-05T10:59:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| SC888 | 一买多头 | 2022-07-05T14:29:00 | 2022-07-05T21:29:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| SC888 | 一买多头 | 2022-07-08T09:29:00 | 2022-07-12T21:29:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| SC888 | 一买多头 | 2022-08-06T01:29:00 | 2022-08-09T23:29:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| SC888 | 一买多头 | 2022-08-09T23:59:00 | 2022-08-12T10:14:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| SC888 | 一买多头 | 2022-09-01T02:29:00 | 2022-09-01T21:29:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| SC888 | 一买多头 | 2022-09-02T02:29:00 | 2022-09-06T02:29:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| SC888 | 一买多头 | 2022-09-21T22:59:00 | 2022-09-23T21:29:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| SC888 | 一买多头 | 2022-09-28T10:59:00 | 2022-10-12T10:14:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| SC888 | 一买多头 | 2022-11-01T01:29:00 | 2022-11-08T21:59:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| SC888 | 一买多头 | 2022-11-14T13:59:00 | 2022-11-15T01:29:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| SC888 | 一买多头 | 2022-11-22T23:59:00 | 2022-11-23T21:29:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| SC888 | 一买多头 | 2022-11-23T23:59:00 | 2022-11-26T01:29:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| SC888 | 一买多头 | 2022-11-26T01:59:00 | 2022-11-28T09:29:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| SC888 | 一买多头 | 2022-12-09T00:29:00 | 2022-12-16T21:29:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| SC888 | 一买多头 | 2023-02-04T01:59:00 | 2023-02-14T22:29:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| SC888 | 一买多头 | 2023-03-01T00:29:00 | 2023-03-07T21:29:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| SC888 | 一买多头 | 2023-03-17T21:29:00 | 2023-03-20T14:29:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| SC888 | 一买多头 | 2023-04-19T10:59:00 | 2023-04-19T21:59:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| SC888 | 一买多头 | 2023-06-10T00:59:00 | 2023-06-12T09:29:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| SC888 | 一买多头 | 2023-06-12T09:59:00 | 2023-06-12T22:29:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| SC888 | 一买多头 | 2023-06-29T10:59:00 | 2023-07-06T21:59:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| SC888 | 一买多头 | 2023-08-24T22:59:00 | 2023-09-18T21:29:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| SC888 | 一买多头 | 2023-09-21T01:59:00 | 2023-09-28T14:29:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| SC888 | 一买多头 | 2023-10-10T14:29:00 | 2023-10-16T13:59:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| SC888 | 一买多头 | 2023-10-26T00:29:00 | 2023-10-31T01:29:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| SC888 | 一买多头 | 2023-11-13T10:59:00 | 2023-11-15T01:29:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| SC888 | 一买多头 | 2024-01-18T11:29:00 | 2024-01-23T21:29:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| SC888 | 一买多头 | 2024-02-02T00:59:00 | 2024-02-02T01:59:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| SC888 | 一买多头 | 2024-02-03T00:59:00 | 2024-02-26T09:29:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| SC888 | 一买多头 | 2024-05-18T00:29:00 | 2024-05-22T14:59:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| SC888 | 一买多头 | 2024-07-12T11:29:00 | 2024-07-16T21:29:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| SC888 | 一买多头 | 2024-07-16T21:59:00 | 2024-07-20T02:29:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| SC888 | 一买多头 | 2024-07-26T21:29:00 | 2024-07-30T00:29:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| SC888 | 一买多头 | 2024-08-07T01:29:00 | 2024-08-09T21:59:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| SC888 | 一买多头 | 2024-08-22T00:29:00 | 2024-08-27T22:29:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| SC888 | 一买多头 | 2024-09-06T00:59:00 | 2024-09-06T23:59:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| SC888 | 一买多头 | 2024-11-01T01:29:00 | 2024-11-06T11:29:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| SC888 | 一买多头 | 2024-11-29T10:59:00 | 2024-12-16T21:29:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| SC888 | 一买多头 | 2025-01-08T22:29:00 | 2025-01-09T09:29:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| SC888 | 一买多头 | 2025-05-12T23:59:00 | 2025-05-15T09:59:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| SC888 | 一买多头 | 2025-05-20T02:29:00 | 2025-05-23T09:59:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| SC888 | 一买多头 | 2025-06-27T01:29:00 | 2025-06-27T23:59:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| SC888 | 一买多头 | 2025-06-28T01:29:00 | 2025-07-10T21:29:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| SC888 | 一买多头 | 2025-07-19T01:59:00 | 2025-07-22T09:59:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| SC888 | 一买多头 | 2025-08-07T00:29:00 | 2025-08-08T14:29:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| SC888 | 一买多头 | 2025-08-08T14:59:00 | 2025-08-20T11:29:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| SC888 | 一买多头 | 2025-09-01T23:59:00 | 2025-09-05T21:29:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| SC888 | 一买多头 | 2025-11-20T23:29:00 | 2025-11-21T09:29:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| SC888 | 一买多头 | 2025-12-10T23:29:00 | 2025-12-16T00:59:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| SC888 | 一买多头 | 2025-12-19T10:14:00 | 2025-12-26T21:59:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| SC888 | 一买多头 | 2026-01-07T00:29:00 | 2026-01-07T09:29:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| SC888 | 一买多头 | 2026-01-09T00:59:00 | 2026-01-12T09:59:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| SC888 | 一买多头 | 2026-01-12T10:14:00 | 2026-01-14T09:29:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| SC888 | 一买多头 | 2026-03-28T00:29:00 | 2026-03-30T10:59:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| SC888 | 一买多头 | 2026-04-02T23:29:00 | 2026-04-08T09:29:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| SC888 | 一买多头 | 2026-04-13T09:29:00 | 2026-04-13T09:59:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| SC888 | 二买多头 | 2022-05-23T13:59:00 | 2022-05-27T14:29:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| SC888 | 二买多头 | 2022-06-22T00:59:00 | 2022-06-22T10:14:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| SC888 | 二买多头 | 2022-06-27T14:59:00 | 2022-06-29T11:29:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| SC888 | 二买多头 | 2022-07-04T10:59:00 | 2022-07-05T10:59:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| SC888 | 二买多头 | 2022-08-08T22:59:00 | 2022-08-09T23:29:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| SC888 | 二买多头 | 2022-08-10T14:29:00 | 2022-08-12T21:29:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| SC888 | 二买多头 | 2022-10-10T14:59:00 | 2022-10-12T10:14:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| SC888 | 二买多头 | 2022-10-20T11:29:00 | 2022-10-28T14:59:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| SC888 | 二买多头 | 2022-12-01T00:59:00 | 2022-12-03T02:29:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| SC888 | 二买多头 | 2023-09-22T23:59:00 | 2023-10-09T09:29:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| SC888 | 二买多头 | 2023-10-13T23:29:00 | 2023-10-18T21:29:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| SC888 | 二买多头 | 2023-10-27T22:59:00 | 2023-11-02T02:29:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| SC888 | 二买多头 | 2024-08-26T14:29:00 | 2024-09-02T09:29:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| SC888 | 二买多头 | 2024-11-01T23:29:00 | 2024-11-16T01:59:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| SC888 | 二买多头 | 2025-08-18T23:29:00 | 2025-08-26T14:59:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| SC888 | 二买多头 | 2025-09-10T01:59:00 | 2025-09-17T23:29:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| SC888 | 三买多头 | 2022-07-12T14:29:00 | 2022-07-12T21:59:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| SC888 | 三买多头 | 2022-08-10T23:29:00 | 2022-08-12T21:29:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| SC888 | 三买多头 | 2022-10-14T13:59:00 | 2022-10-18T21:59:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| SC888 | 三买多头 | 2023-06-08T09:29:00 | 2023-06-12T09:59:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| SC888 | 三买多头 | 2023-06-21T14:59:00 | 2023-06-28T02:29:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| SC888 | 三买多头 | 2023-06-30T21:29:00 | 2023-07-15T02:29:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| SC888 | 三买多头 | 2023-08-29T23:29:00 | 2023-09-18T21:29:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| SC888 | 三买多头 | 2024-08-20T00:29:00 | 2024-08-22T01:59:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| SC888 | 三买多头 | 2025-06-05T14:59:00 | 2025-06-11T09:29:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| SC888 | 三买多头 | 2026-03-16T10:59:00 | 2026-03-16T21:29:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| SC888 | 三买多头 | 2026-04-08T01:59:00 | 2026-04-08T09:29:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| A888 | 一买多头 | 2022-02-24T09:29:00 | 2022-02-24T22:59:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| A888 | 一买多头 | 2022-06-02T14:59:00 | 2022-06-10T14:59:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| A888 | 一买多头 | 2022-06-17T13:59:00 | 2022-06-22T10:59:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| A888 | 一买多头 | 2022-06-30T13:59:00 | 2022-07-01T22:29:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| A888 | 一买多头 | 2022-08-30T09:29:00 | 2022-09-05T09:29:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| A888 | 一买多头 | 2022-09-08T14:29:00 | 2022-09-26T10:14:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| A888 | 一买多头 | 2022-10-17T13:59:00 | 2022-10-19T21:59:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| A888 | 一买多头 | 2022-10-19T22:29:00 | 2022-10-24T09:59:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| A888 | 一买多头 | 2023-03-09T14:59:00 | 2023-03-16T22:29:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| A888 | 一买多头 | 2023-04-14T14:59:00 | 2023-04-20T09:59:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| A888 | 一买多头 | 2023-04-20T10:14:00 | 2023-04-21T11:29:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| A888 | 一买多头 | 2023-04-21T13:59:00 | 2023-05-04T09:29:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| A888 | 一买多头 | 2023-09-12T09:59:00 | 2023-09-22T09:29:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| A888 | 一买多头 | 2023-10-17T09:59:00 | 2023-10-19T13:59:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| A888 | 一买多头 | 2023-12-11T13:59:00 | 2023-12-18T14:29:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| A888 | 一买多头 | 2024-06-24T14:59:00 | 2024-07-16T10:59:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| A888 | 一买多头 | 2025-01-10T22:59:00 | 2025-01-16T22:29:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| A888 | 一买多头 | 2026-03-23T21:59:00 | 2026-03-24T21:29:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| A888 | 二买多头 | 2022-09-15T10:14:00 | 2022-09-26T09:29:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| A888 | 二买多头 | 2024-01-26T09:29:00 | 2024-02-23T22:59:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| A888 | 二买多头 | 2024-10-22T21:29:00 | 2024-12-04T10:59:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| A888 | 三买多头 | 2024-04-10T14:29:00 | 2024-05-13T09:23:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| A888 | 三买多头 | 2025-11-05T09:29:00 | 2025-11-18T09:59:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| ZN888 | 一买多头 | 2022-01-13T09:29:00 | 2022-01-17T11:29:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| ZN888 | 一买多头 | 2022-01-19T21:29:00 | 2022-02-11T09:29:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| ZN888 | 一买多头 | 2022-04-28T23:59:00 | 2022-05-05T23:29:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| ZN888 | 一买多头 | 2022-05-05T23:59:00 | 2022-05-06T21:29:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| ZN888 | 一买多头 | 2022-05-06T23:59:00 | 2022-05-09T21:29:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| ZN888 | 一买多头 | 2022-06-29T14:59:00 | 2022-06-30T21:29:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| ZN888 | 一买多头 | 2022-07-19T21:29:00 | 2022-08-02T10:59:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| ZN888 | 一买多头 | 2022-09-06T09:29:00 | 2022-09-07T21:29:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| ZN888 | 一买多头 | 2022-09-07T21:59:00 | 2022-09-14T09:29:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| ZN888 | 一买多头 | 2022-09-27T23:29:00 | 2022-10-11T22:29:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| ZN888 | 一买多头 | 2022-11-03T14:29:00 | 2022-11-07T09:29:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| ZN888 | 一买多头 | 2023-02-17T14:29:00 | 2023-02-22T23:59:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| ZN888 | 一买多头 | 2023-03-01T09:59:00 | 2023-03-13T09:29:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| ZN888 | 一买多头 | 2023-04-28T14:59:00 | 2023-05-11T23:59:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| ZN888 | 一买多头 | 2023-05-15T11:29:00 | 2023-05-22T10:59:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| ZN888 | 一买多头 | 2023-05-22T11:29:00 | 2023-05-23T14:29:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| ZN888 | 一买多头 | 2023-05-23T14:59:00 | 2023-05-24T09:29:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| ZN888 | 一买多头 | 2023-08-04T13:59:00 | 2023-08-08T21:29:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| ZN888 | 一买多头 | 2024-01-25T09:29:00 | 2024-02-01T09:59:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| ZN888 | 一买多头 | 2024-03-21T23:29:00 | 2024-03-26T22:59:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| ZN888 | 一买多头 | 2024-03-29T21:29:00 | 2024-04-15T21:29:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| ZN888 | 一买多头 | 2024-06-12T23:59:00 | 2024-06-14T21:29:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| ZN888 | 一买多头 | 2024-06-18T11:29:00 | 2024-07-01T10:14:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| ZN888 | 一买多头 | 2024-07-16T00:59:00 | 2024-07-17T13:59:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| ZN888 | 一买多头 | 2024-07-17T14:29:00 | 2024-07-19T09:29:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| ZN888 | 一买多头 | 2024-09-04T10:14:00 | 2024-09-05T11:29:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| ZN888 | 一买多头 | 2024-09-05T13:59:00 | 2024-09-20T21:29:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| ZN888 | 一买多头 | 2024-11-27T00:29:00 | 2024-12-19T21:29:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| ZN888 | 一买多头 | 2024-12-24T00:29:00 | 2025-01-03T21:29:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| ZN888 | 一买多头 | 2025-01-13T21:29:00 | 2025-01-15T10:59:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| ZN888 | 一买多头 | 2025-03-21T23:59:00 | 2025-03-31T09:29:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| ZN888 | 二买多头 | 2022-03-17T21:29:00 | 2022-03-29T21:29:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| ZN888 | 二买多头 | 2022-05-05T11:29:00 | 2022-05-06T21:29:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| ZN888 | 二买多头 | 2022-05-17T23:29:00 | 2022-06-06T21:29:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| ZN888 | 二买多头 | 2022-06-29T14:59:00 | 2022-06-30T21:29:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| ZN888 | 二买多头 | 2023-03-02T11:29:00 | 2023-03-10T09:59:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| ZN888 | 二买多头 | 2023-10-20T14:59:00 | 2023-11-02T21:59:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| ZN888 | 二买多头 | 2024-04-01T13:59:00 | 2024-04-15T21:29:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| ZN888 | 二买多头 | 2024-06-13T23:59:00 | 2024-07-01T09:59:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| ZN888 | 二买多头 | 2024-10-17T09:29:00 | 2024-11-28T11:29:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| ZN888 | 二买多头 | 2024-12-25T14:59:00 | 2025-01-03T09:29:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| ZN888 | 三买多头 | 2022-03-30T22:59:00 | 2022-04-13T14:59:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| ZN888 | 三买多头 | 2023-01-12T10:59:00 | 2023-01-19T09:29:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| ZN888 | 三买多头 | 2024-04-30T14:29:00 | 2024-05-22T21:29:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| ZN888 | 三买多头 | 2024-07-04T09:59:00 | 2024-07-17T14:29:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| ZN888 | 三买多头 | 2025-01-22T14:59:00 | 2025-02-05T13:59:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| ZN888 | 三买多头 | 2025-03-26T00:29:00 | 2025-04-01T21:59:00 | missing_dates | pnl_attribution_20220101_20260424.json |
| RB888 | 一买多头 | 2022-11-03T22:59:00 | 2022-11-04T14:29:00 | missing_dates | trade_difference_attribution.json |
| RB888 | 一买多头 | 2023-09-04T10:59:00 | 2023-09-19T10:14:00 | missing_dates | trade_difference_attribution.json |
| RB888 | 一买多头 | 2024-02-28T09:59:00 | 2024-03-04T11:29:00 | missing_dates | trade_difference_attribution.json |
| RB888 | 一买多头 | 2024-03-07T14:59:00 | 2024-03-11T09:29:00 | missing_dates | trade_difference_attribution.json |
| RB888 | 一买多头 | 2024-03-11T09:59:00 | 2024-03-13T21:29:00 | missing_dates | trade_difference_attribution.json |
| RB888 | 一买多头 | 2025-02-19T14:29:00 | 2025-02-21T13:59:00 | missing_dates | trade_difference_attribution.json |
| RB888 | 一买多头 | 2025-11-18T10:59:00 | 2025-12-01T11:29:00 | missing_dates | trade_difference_attribution.json |
| SC888 | 一买多头 | 2022-09-29T14:29:00 | 2022-10-11T14:59:00 | missing_dates | trade_difference_attribution.json |
| SC888 | 一买多头 | 2022-11-02T01:29:00 | 2022-11-04T22:59:00 | missing_dates | trade_difference_attribution.json |
| SC888 | 一买多头 | 2022-12-12T09:29:00 | 2022-12-13T01:29:00 | missing_dates | trade_difference_attribution.json |
| SC888 | 一买多头 | 2023-02-08T14:29:00 | 2023-02-09T21:29:00 | missing_dates | trade_difference_attribution.json |
| SC888 | 一买多头 | 2023-02-09T21:59:00 | 2023-02-10T21:59:00 | missing_dates | trade_difference_attribution.json |
| SC888 | 一买多头 | 2023-08-25T23:59:00 | 2023-08-31T23:59:00 | missing_dates | trade_difference_attribution.json |
| SC888 | 一买多头 | 2023-09-27T14:29:00 | 2023-09-28T01:29:00 | missing_dates | trade_difference_attribution.json |
| SC888 | 一买多头 | 2023-10-27T00:29:00 | 2023-10-31T01:29:00 | missing_dates | trade_difference_attribution.json |
| SC888 | 一买多头 | 2023-11-14T14:29:00 | 2023-11-16T09:29:00 | missing_dates | trade_difference_attribution.json |
| SC888 | 一买多头 | 2024-02-08T01:59:00 | 2024-02-20T23:29:00 | missing_dates | trade_difference_attribution.json |
| SC888 | 一买多头 | 2024-08-08T09:29:00 | 2024-08-13T10:59:00 | missing_dates | trade_difference_attribution.json |

## Notes

- Baseline uses recorded close-based stop-loss outcomes from existing diagnostics JSON files.
- Intrabar and gap scenarios require SQLite K-line data; missing data is marked unavailable rather than silently passing.
- Penalty slippage is an overlay applied to the most pessimistic available exit price.
- This diagnostic does not modify Position, BacktestEngine, strategy parameters, SimNow, or trading interfaces.

## Data Source

- pairs: `diagnostics_json_scan`
- bars: `D:\BaiduNetdiskDownload\新数据库\ssquant数据库_20260425\kline_data.db`
