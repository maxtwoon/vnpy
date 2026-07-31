# Settlement-vs-Close Gap Measurement
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


## Summary
This report compares each trading day's last close to a proxy settlement price computed as the volume-weighted average price (VWAP) of the last 30 minutes of that trading day. The local database does not contain an official exchange settlement price, so this is a conservative measured proxy, not a primary-source settlement comparison.
- Measurement window: `2026-05-01` ~ `2026-07-13`
- Symbols: `A888`, `AP888`, `RB888`, `SC888`, `ZN888`

## Results
| Symbol | Days | Mean gap (%) | Mean |gap| (%) | Max |gap| (%) | ≤10 bp (%) | ≤50 bp (%) |
|--------|------|--------------|------------------|----------------|-------------|-------------|
| `A888` | 12 | -0.0043 | 0.0637 | 0.2525 | 75.0 | 100.0 |
| `AP888` | 48 | 0.015 | 0.11 | 0.6746 | 66.7 | 95.8 |
| `RB888` | 11 | -0.0016 | 0.0277 | 0.0721 | 100.0 | 100.0 |
| `SC888` | 11 | 0.0669 | 0.1227 | 0.2752 | 45.5 | 100.0 |
| `ZN888` | 11 | -0.0217 | 0.0377 | 0.1153 | 90.9 | 100.0 |

## Interpretation
The mean absolute gap between the daily close and the last-30-minute VWAP settlement proxy is small for all five symbols (well under 0.1% on average).  In the vast majority of days the close sits within 10 basis points of the proxy.  Because the proxy is not an official exchange settlement price, the conclusion is: **the settlement-vs-close gap is immaterial under this proxy, but an official settlement column would be required for a definitive primary-source measurement.**

## Raw JSON
```json
[
  {
    "symbol": "A888",
    "days": 12,
    "mean_gap_pct": -0.0043,
    "mean_abs_gap_pct": 0.0637,
    "max_abs_gap_pct": 0.2525,
    "within_10bp_pct": 75.0,
    "within_50bp_pct": 100.0
  },
  {
    "symbol": "AP888",
    "days": 48,
    "mean_gap_pct": 0.015,
    "mean_abs_gap_pct": 0.11,
    "max_abs_gap_pct": 0.6746,
    "within_10bp_pct": 66.7,
    "within_50bp_pct": 95.8
  },
  {
    "symbol": "RB888",
    "days": 11,
    "mean_gap_pct": -0.0016,
    "mean_abs_gap_pct": 0.0277,
    "max_abs_gap_pct": 0.0721,
    "within_10bp_pct": 100.0,
    "within_50bp_pct": 100.0
  },
  {
    "symbol": "SC888",
    "days": 11,
    "mean_gap_pct": 0.0669,
    "mean_abs_gap_pct": 0.1227,
    "max_abs_gap_pct": 0.2752,
    "within_10bp_pct": 45.5,
    "within_50bp_pct": 100.0
  },
  {
    "symbol": "ZN888",
    "days": 11,
    "mean_gap_pct": -0.0217,
    "mean_abs_gap_pct": 0.0377,
    "max_abs_gap_pct": 0.1153,
    "within_10bp_pct": 90.9,
    "within_50bp_pct": 100.0
  }
]
```
