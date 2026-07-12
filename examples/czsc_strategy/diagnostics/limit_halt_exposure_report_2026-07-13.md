# A50 — Limit-Up/Down/Halt Impact Diagnostic

> RESEARCH-ONLY — Diagnostic only, not a trading recommendation.

Generated: 2026-07-13T01:15:00.541722
Window: 2026-04-24 ~ 2026-07-09

## Totals

| Metric | Count |
|--------|------:|
| Total trades | 2 |
| Entry-fill at/beyond limit | 0 |
| Entry-fill not at limit | 2 |
| Exit-fill at/beyond limit | 0 |
| Exit-fill not at limit | 2 |
| Zero-volume near entry | 0 |
| Zero-volume near exit | 0 |

## Per-Symbol Summary

| Symbol | Limit % | Trades | Entry @ limit | Exit @ limit | Z-Vol near entry | Z-Vol near exit | Error |
|--------|--------:|-------:|--------------:|-------------:|-----------------:|----------------:|-------|
| AP888 | 5.0% | 2 | 0 (0.0%) | 0 (0.0%) | 0 | 0 | - |
| RB888 | 3.0% | 0 | 0 (0.0%) | 0 (0.0%) | 0 | 0 | 交易周期数据不足: 需要至少110根30分钟K线，实际95根 |
| SC888 | 4.0% | 0 | 0 (0.0%) | 0 (0.0%) | 0 | 0 | - |
| A888 | 4.0% | 0 | 0 (0.0%) | 0 (0.0%) | 0 | 0 | 交易周期数据不足: 需要至少110根30分钟K线，实际86根 |
| ZN888 | 4.0% | 0 | 0 (0.0%) | 0 (0.0%) | 0 | 0 | - |

## Sources

- **AP888**: CZCE 鲜苹果期货合约：每日涨跌停板幅度为前一交易日结算价的±5% (郑州商品交易所〔2017〕17号公告，《郑州商品交易所鲜苹果期货业务细则》)
- **RB888**: SHFE 螺纹钢期货合约：涨跌停板幅度为上一交易日结算价±3% (shfe.com.cn/products/futures/metal/ferrousandpreciousmetal/rb_f/, 2024-09-24修订)
- **SC888**: INE 原油期货标准合约：Daily Price Limits ±4% from the settlement price of the previous trading day (ine.cn/eng/market/futures/energy/sc/contract/)
- **A888**: DCE 黄大豆1号期货合约：涨跌停板幅度为上一交易日结算价的±4% (大连商品交易所黄大豆1号期货合约文本 / 《大连商品交易所风险管理办法》)
- **ZN888**: SHFE 锌期货合约：涨跌停板幅度为上一交易日结算价±4% (shfe.com.cn/publicnotice/notice/202408/W020240823636323134983.docx 修订稿)

## Methodology

This report is read-only evidence.  It uses the exchange-published steady-state daily price-limit percentage per symbol and the previous trading day's last close observed in the loaded window.  It does not change BacktestEngine/PortfolioEngine fill logic, does not enforce any limit/halt constraint, and is not used to tune parameters.  For per-trade tagging, set ``limit_halt_model='aware'`` in ``chan_strategy.config.STRATEGY_CONFIG``; trades will still open/close at unchanged prices and only gain ``is_entry_at_limit``/``is_exit_at_limit`` boolean fields.

A trade is flagged 'at limit' on the entry/exit side when the fill bar's high or low touches or exceeds the computed daily price-limit band. The band is derived from the previous trading day's last close observed in the loaded window and the symbol's steady-state exchange limit percentage. Zero-volume bars within one bar of the fill bar are reported as a secondary halted/no-liquidity proxy when the raw table exposes a volume column.
