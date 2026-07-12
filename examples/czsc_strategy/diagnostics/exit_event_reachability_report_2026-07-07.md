# Exit-Event Reachability Report (Phase 0)

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


**Diagnostic only, not a trading recommendation.**

- Generated at: 2026-07-07T18:24:11.347834
- Date range: 2025-01-01 to 2025-12-31
- Trade frequency: 30分钟
- Symbols: AP888, RB888, SC888, A888, ZN888
- DB path: D:\BaiduNetdiskDownload\新数据库\ssquant数据库_20260425\kline_data.db

## Summary

| Metric | Count |
| ------ | ----- |
| legacy_fired | 3341 |
| struct_alone | 2896 |
| factor_alone | 31974 |

### Dead-signal confirmation

| Signal | Count |
| ------ | ----- |
| 30分钟_D1BI_背驰V260615_失效 | 0 |

## Per-symbol results

### AP888

- **status**: ok
- **records**: 1836
- **bars**: 54450 1m → 1936 30分钟

| Event | legacy_fired | struct_alone | factor_alone | blocked_ratio |
| ----- | ------------ | ------------ | ------------ | ------------- |
| 一买平多 | 155 | 221 | 689 | 0.5878 |
| 二买平多 | 0 | 0 | 327 | N/A |
| 三买平多 | 0 | 0 | 891 | N/A |
| 一卖平空 | 225 | 202 | 586 | 0.4731 |
| 二卖平空 | 91 | 6 | 261 | 0.0619 |
| 三卖平空 | 97 | 0 | 848 | 0.0000 |

### RB888

- **status**: ok
- **records**: 2792
- **bars**: 83115 1m → 2892 30分钟

| Event | legacy_fired | struct_alone | factor_alone | blocked_ratio |
| ----- | ------------ | ------------ | ------------ | ------------- |
| 一买平多 | 182 | 255 | 1029 | 0.5835 |
| 二买平多 | 0 | 0 | 585 | N/A |
| 三买平多 | 0 | 0 | 1381 | N/A |
| 一卖平空 | 219 | 224 | 1041 | 0.5056 |
| 二卖平空 | 6 | 0 | 603 | 0.0000 |
| 三卖平空 | 6 | 0 | 1405 | 0.0000 |

### SC888

- **status**: ok
- **records**: 4451
- **bars**: 132885 1m → 4551 30分钟

| Event | legacy_fired | struct_alone | factor_alone | blocked_ratio |
| ----- | ------------ | ------------ | ------------ | ------------- |
| 一买平多 | 505 | 434 | 1471 | 0.4622 |
| 二买平多 | 177 | 73 | 896 | 0.2920 |
| 三买平多 | 250 | 0 | 2087 | 0.0000 |
| 一卖平空 | 355 | 453 | 1438 | 0.5606 |
| 二卖平空 | 84 | 71 | 877 | 0.4581 |
| 三卖平空 | 155 | 0 | 1959 | 0.0000 |

### A888

- **status**: ok
- **records**: 2780
- **bars**: 82770 1m → 2880 30分钟

| Event | legacy_fired | struct_alone | factor_alone | blocked_ratio |
| ----- | ------------ | ------------ | ------------ | ------------- |
| 一买平多 | 171 | 228 | 908 | 0.5714 |
| 二买平多 | 0 | 0 | 368 | N/A |
| 三买平多 | 0 | 0 | 1222 | N/A |
| 一卖平空 | 218 | 189 | 1080 | 0.4644 |
| 二卖平空 | 8 | 0 | 451 | 0.0000 |
| 三卖平空 | 8 | 0 | 1550 | 0.0000 |

### ZN888

- **status**: ok
- **records**: 3740
- **bars**: 111555 1m → 3840 30分钟

| Event | legacy_fired | struct_alone | factor_alone | blocked_ratio |
| ----- | ------------ | ------------ | ------------ | ------------- |
| 一买平多 | 222 | 258 | 1421 | 0.5375 |
| 二买平多 | 0 | 9 | 797 | 1.0000 |
| 三买平多 | 9 | 0 | 1889 | 0.0000 |
| 一卖平空 | 198 | 273 | 1405 | 0.5796 |
| 二卖平空 | 0 | 0 | 667 | N/A |
| 三卖平空 | 0 | 0 | 1842 | N/A |

## Notes

- struct_alone counts bars where event-level signals fired but no factor matched.
- factor_alone counts bars where a factor matched but event-level signals did not.
- Per-bar open-position exit tracking is not joined in Phase 0 (trade pairs unavailable).
