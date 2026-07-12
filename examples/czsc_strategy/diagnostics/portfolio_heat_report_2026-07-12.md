# Portfolio Heat Report

**RESEARCH-ONLY — Diagnostic only, not a trading recommendation.**

- Generated at: 2026-07-12T13:01:00.487634+00:00
- Window: `2026-04-24` ~ `2026-07-09`
- Symbols: `AP888 / RB888 / SC888 / A888 / ZN888`
- Cluster cap: `1.0`
- Daily loss limit: `3.00%`
- Clusters: `{"industrial_energy": ["RB888", "ZN888", "SC888"]}`

## Symbol Availability

- **AP888**: included
- **RB888**: excluded — 交易周期数据不足: 需要至少110根30分钟K线，实际95根
- **SC888**: included
- **A888**: excluded — 交易周期数据不足: 需要至少110根30分钟K线，实际86根
- **ZN888**: included

## Fixed vs Risk-Parity Weights

Weights are shown relative to the set of successfully backtested symbols.

| Symbol | Fixed weight | Risk-parity avg weight |
|---|---:|---:|
| AP888 | 33.33% | 87.93% |
| SC888 | 33.33% | 5.33% |
| ZN888 | 33.33% | 6.74% |

## Portfolio-Level Metrics

| Weighting | Total return | Max drawdown | Loss-limit days | Blocked opens |
|---|---:|---:|---:|---:|
| fixed | -0.90% | 1.18% | 0 | 0 |
| risk_parity | -1.50% | 1.96% | 0 | 0 |

## Cluster Gross Exposure Summary

| Cluster | Weighting | Max daily gross | Mean daily gross | Days > 50% | Days > 80% |
|---|---|---:|---:|---:|---:|
| industrial_energy | fixed | 0.00% | 0.00% | 0 | 0 |
| industrial_energy | risk_parity | 0.00% | 0.00% | 0 | 0 |

## Loss-Limit Trigger Days

### fixed
_No loss-limit triggers in this window._

### risk_parity
_No loss-limit triggers in this window._


## Notes

- This report is evidence-only.  It is not used to select or tune 
  ``cluster_gross_cap``, ``daily_loss_limit_pct`` or ``corr_clusters`` membership.
- Risk-parity weights are estimated online from rolling per-symbol volatility;
  no future bars are used.
- The coordinator is backtest-only and does not route live orders.
