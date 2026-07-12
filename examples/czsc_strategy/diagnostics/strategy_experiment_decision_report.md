# Strategy Experiment Decision Report

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


- source: `D:\repo\vnpy\examples\czsc_strategy\diagnostics\strategy_execution_experiment_matrix.json`
- rule: out_sample is primary; full sample is a stability check.
- candidate gate: OOS return improves, OOS drawdown does not worsen, full-sample return does not worsen, and OOS trade loss is <= 30%.

## Combo Summary

| period | scenario | return | drawdown | trades | return_delta | drawdown_delta | decision |
|---|---|---:|---:|---:|---:|---:|---|
| full | baseline | -2.20% | 8.15% | 358 | 0.00% | 0.00% | - |
| full | second_buy_filters | 0.05% | 6.20% | 326 | 2.24% | -1.96% | - |
| full | trailing_overrides | -0.98% | 6.51% | 381 | 1.21% | -1.65% | - |
| full | combined | 0.08% | 5.53% | 345 | 2.28% | -2.62% | - |
| out_sample | baseline | -0.52% | 4.66% | 92 | 0.00% | 0.00% | - |
| out_sample | second_buy_filters | 0.50% | 3.66% | 84 | 1.02% | -1.00% | candidate |
| out_sample | trailing_overrides | 0.39% | 4.11% | 98 | 0.90% | -0.55% | candidate |
| out_sample | combined | 1.16% | 3.27% | 89 | 1.68% | -1.39% | candidate |

## Recommendation

- combined: can enter next paper-trading candidate set; keep default-off until SimNow confirms execution quality.
- second_buy_filters: keep testing as a targeted risk gate for chase entries; monitor trade count loss.
- trailing_overrides: RB888/SC888 overrides remain worth paper-trading because they are per-symbol and explicit.

## Parameters Under Test

```json
{
  "baseline": {},
  "second_buy_filters": {
    "max_2buy_entry_vs_anchor_pct": 0.03,
    "enable_2buy_symbols": [
      "AP888",
      "A888",
      "ZN888"
    ]
  },
  "trailing_overrides": {
    "trailing_overrides": {
      "RB888": {
        "trailing_start_bp": 150,
        "trailing_drawback_pct": 0.15
      },
      "SC888": {
        "trailing_start_bp": 150,
        "trailing_drawback_pct": 0.15
      }
    }
  },
  "combined": {
    "max_2buy_entry_vs_anchor_pct": 0.03,
    "enable_2buy_symbols": [
      "AP888",
      "A888",
      "ZN888"
    ],
    "trailing_overrides": {
      "RB888": {
        "trailing_start_bp": 150,
        "trailing_drawback_pct": 0.15
      },
      "SC888": {
        "trailing_start_bp": 150,
        "trailing_drawback_pct": 0.15
      }
    }
  }
}
```
