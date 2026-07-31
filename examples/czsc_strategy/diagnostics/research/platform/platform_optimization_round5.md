# Platform Optimization Round 5

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


## Quantified Goal

Current target:

- SC short-weight neighborhood pass ratio >= `4/6`
- all5 walk-forward positive windows >= `7/9`
- adjacent symbol-set pass ratio >= `4/6`

Current status from `check_platform_stability_goal.py`:

- SC neighborhood: `5/6` pass
- all5 walk-forward: `7/9` pass
- symbol sets: `2/6` pass

Only symbol-set robustness remains below target.

## Signal Funnel Audit

Source: `signal_funnel_core_AP_A_ZN_block1buy_20250101_20260424.txt`

The signal funnel was run on `AP888 / A888 / ZN888` with the current research base:

```json
{
  "block_1buy_daily_down": true,
  "sc_short_multiplier": 0.75
}
```

Observation:

- Signal-level first/second/third-buy candidates are not absent.
- Event-level open conditions pass many bars.
- Actual opens are much fewer than event-passing bars.

Interpretation:

The `core_AP_A_ZN` trade-count shortage is not mainly caused by missing raw buy-point signals. It is more likely caused by position occupancy / exit timing / one-position-per-substrategy mechanics.

## Timeout Test

Hypothesis:

Shorter timeouts may release positions faster and increase trade count for `no_SC` / `core_AP_A_ZN`.

Tested candidate:

```json
{
  "timeout_1buy": 300,
  "timeout_2buy": 500,
  "timeout_3buy": 750
}
```

Quick test:

- set: `no_SC`
- windows: `2023H1 / 2025H1 / 2026YTD`
- source: `platform_timeout_half_no_sc_quick.md`

Result:

| candidate | no_SC trades | no_SC WF | all5 trades | all5 PF |
|---|---:|---:|---:|---:|
| base reference | 56 | 0/3 weak-window sample | 103 | 1.50 |
| timeout_half | 57 | 0/3 weak-window sample | 104 | 1.41 |

Timeout shortening adds only one no_SC trade and worsens all5 profit factor.

## Conclusion

Timeout shortening is not a useful platform lever.

Combined with Round 4, the following paths are currently weak:

- RB second-buy eligibility: not useful.
- Third-buy interval relaxation: not useful.
- Timeout shortening: not useful.

## Next Direction

The remaining gap is not a simple entry-frequency switch.

Next useful branch:

1. Audit exit reasons and holding duration for `core_AP_A_ZN` and `no_SC`.
2. Identify whether long holding periods are caused by profitable holds or stale flat/losing holds.
3. If stale holds dominate, test a targeted structural exit or tighter trailing stop for AP/A/ZN.
4. If profitable holds dominate, accept lower trade count and revisit whether the symbol-set gate should require arbitrary removability or required basket components.

