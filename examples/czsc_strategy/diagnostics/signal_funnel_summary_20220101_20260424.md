# 信号漏斗诊断摘要

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


- 区间：2022-01-01 ~ 2026-04-24
- 品种：AP888 / RB888 / SC888 / A888 / ZN888
- 命令：`python diagnostics/signal_funnel.py <symbol> --start 2022-01-01 --end 2026-04-24`
- 说明：五品种一次性串行运行超过 5 分钟，因此改为单品种分别落盘。

## 结果总览（修复后）

| 品种 | 评估bar | 一买通过/开仓 | 二买通过/开仓 | 三买通过/开仓 |
|---|---:|---:|---:|---:|
| AP888 | 7,823 | 474 / 42 | 26 / 4 | 171 / 21 |
| RB888 | 12,272 | 598 / 36 | 18 / 6 | 23 / 2 |
| SC888 | 19,176 | 1,078 / 88 | 177 / 24 | 83 / 11 |
| A888 | 12,234 | 636 / 37 | 57 / 7 | 24 / 4 |
| ZN888 | 16,315 | 954 / 59 | 99 / 12 | 78 / 7 |

## 修复链路

| 阶段 | AP888 | RB888 | SC888 | A888 | ZN888 |
|---|---:|---:|---:|---:|---:|
| 修复前一买 | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 |
| 一买修复后 | 474 / 42 | 598 / 36 | 1,078 / 88 | 636 / 37 | 954 / 59 |
| 二买修复后 | 26 / 4 | 18 / 6 | 177 / 24 | 57 / 7 | 99 / 12 |

## 已修复归因

- 一买全灭：`signal_first_buy` 原先直接取 `zhongshu_list[-1]`，在 recent 重叠候选模式下会选到尾部无后续离开段的展示中枢；现已改为与一卖一致，取最近一个后面已有离开段的中枢。
- 二买全灭：`create_second_buy_position` 的开仓 `signals_not` 禁止 `30分钟_D1BI_背驰V260615=无`，但二买本身由一买锚点与回抽不破低确认，不应要求当前背驰；移除该过滤后，五品种二买均恢复。
- 日线过滤不是本轮一买/二买全灭主因；修复集中在信号口径与事件闸门。

## 后续关注

- 二买交易数已恢复，但明显少于一买；后续应评估二买是否只是低频高质量信号，还是仍被锚点生命周期/确认末笔条件压低。
- 一买交易数大幅增加，所有历史回测收益、回撤和胜率结论均需重跑。

## 原始报告

- `examples/czsc_strategy/diagnostics/signal_funnel_AP888_20220101_20260424_after_2buy_fix.txt`
- `examples/czsc_strategy/diagnostics/signal_funnel_RB888_20220101_20260424_after_2buy_fix.txt`
- `examples/czsc_strategy/diagnostics/signal_funnel_SC888_20220101_20260424_after_2buy_fix.txt`
- `examples/czsc_strategy/diagnostics/signal_funnel_A888_20220101_20260424_after_2buy_fix.txt`
- `examples/czsc_strategy/diagnostics/signal_funnel_ZN888_20220101_20260424_after_2buy_fix.txt`
