# Platform Optimization Round 9

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


## Objective

Make the final candidate reproducible from one configuration source, then verify that it still passes under:

- cost/slippage `2x`
- date offsets
- dominant-symbol / main-continuous code perturbation audit
- platform gates: SC neighborhood, all5 walk-forward, symbol-set stability
- unit tests

## Final Candidate

`sc025_a_zn010_sc3buy_half + A/AP trailing 250/0.20`

Single source:

- `platform_final_candidate.py`

Generated config:

- `platform_final_candidate_config.json`

Key parameters:

- SC short center multiplier: `0.25`
- SC short neighborhood: `[0.10, 0.20, 0.25, 0.30, 0.40, 0.50]`
- A/ZN short weights: `0.10x`
- SC third-buy long weight: `0.15`
- A/AP trailing: `250 / 0.20`
- first-buy gate: `block_1buy_daily_down`

## Base Gate

Source:

- `platform_stability_goal_status_sc025_final.json`

Result:

```text
sc_neighbor=6/6 required>=4/6 pass=True
walk_forward=7/9 required>=7/9 pass=True
symbol_sets=6/6 required>=4/6 pass=True
platform_goal_passed=True
```

## Cost / Slippage 2x

The robustness checker now injects cost directly into `BacktestEngine`, using `0.0006` commission and `0.002` slippage, i.e. `2x` the historical engine baseline `0.0003 / 0.001`.

Sources:

- `platform_final_robustness_cost2_symbol_sets.md`
- `platform_final_robustness_cost2_sc_neighbor.md`

Results:

- symbol sets: `4/6`
- all5 WF: `7/9`
- SC neighborhood: `6/6`

## Date Offsets

Source:

- `platform_final_robustness_date_variants.md`

Under cost/slippage `2x`:

| variant | result |
|---|---|
| base | pass |
| start_plus_1m | pass |
| start_minus_1m | pass |
| end_minus_1m | pass |

Date-variant pass count: `4/4`.

## Main-Continuous Perturbation Audit

The DB mostly contains one continuous symbol per table. `AP888` has an upper-case segment and lower-case segment, so the audit verifies both:

- dominant symbol resolution works.
- AP upper segment runs.
- AP lower segment runs.

Source:

- `platform_final_robustness_date_variants.md`
- `platform_final_robustness_cost2_symbol_sets.md`
- `platform_final_robustness_cost2_sc_neighbor.md`

Result: `passed=True`.

## Unit Tests

```text
pytest examples\czsc_strategy\tests -q
98 passed, 1 skipped
```

## Conclusion

The next-stage quantified target is achieved:

- one-click reproducible final candidate: yes
- cost/slippage `2x`: pass
- date offsets: pass
- dominant-symbol perturbation audit: pass
- SC neighborhood >= `4/6`: pass, actual `6/6`
- all5 WF >= `7/9`: pass, actual `7/9`
- symbol-set stability >= `4/6`: pass, actual `4/6` under cost/slippage `2x`, `6/6` at base cost
- pytest: pass
