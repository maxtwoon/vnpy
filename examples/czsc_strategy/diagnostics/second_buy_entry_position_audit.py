from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from second_buy_anchor_audit import (
    DEFAULT_END,
    DEFAULT_START,
    DEFAULT_SYMBOLS,
    SQLITE_DB_PATH,
    _fmt_num,
    _fmt_pct,
    collect_audit,
)


def _pct(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator in (None, 0):
        return None
    return numerator / denominator


def _bucket_pct(value: float | None) -> str:
    if value is None:
        return "missing"
    pct = value * 100
    if pct <= 1:
        return "<=1%"
    if pct <= 3:
        return "1-3%"
    if pct <= 5:
        return "3-5%"
    if pct <= 10:
        return "5-10%"
    return ">10%"


def _summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {"trades": 0, "pnl_sum": 0.0, "win_rate": 0.0, "profit_factor": 0.0}
    pnls = [float(x["pnl_pct"]) for x in rows]
    wins = [x for x in pnls if x > 0]
    losses = [x for x in pnls if x <= 0]
    loss_sum = abs(sum(losses))
    return {
        "trades": len(rows),
        "pnl_sum": sum(pnls),
        "win_rate": len(wins) / len(rows),
        "avg_pnl": sum(pnls) / len(rows),
        "profit_factor": sum(wins) / loss_sum if loss_sum else float("inf"),
        "max_loss": min(pnls),
        "avg_entry_vs_anchor": _avg(rows, "entry_vs_anchor_pct"),
        "avg_entry_vs_zs_zd": _avg(rows, "entry_vs_zs_zd_pct"),
        "avg_entry_vs_zs_zg": _avg(rows, "entry_vs_zs_zg_pct"),
    }


def _avg(rows: list[dict[str, Any]], key: str) -> float | None:
    values = [x[key] for x in rows if x.get(key) is not None]
    if not values:
        return None
    return sum(values) / len(values)


def enrich(payload: dict[str, Any]) -> dict[str, Any]:
    for row in payload["trades"]:
        entry = row.get("open_price")
        anchor = row.get("anchor_price")
        zs_zd = row.get("anchor_zs_zd")
        zs_zg = row.get("anchor_zs_zg")
        row["entry_vs_anchor_pct"] = _pct(entry - anchor if entry is not None and anchor is not None else None, anchor)
        row["entry_vs_zs_zd_pct"] = _pct(entry - zs_zd if entry is not None and zs_zd is not None else None, zs_zd)
        row["entry_vs_zs_zg_pct"] = _pct(entry - zs_zg if entry is not None and zs_zg is not None else None, zs_zg)
        row["entry_vs_anchor_bucket"] = _bucket_pct(row["entry_vs_anchor_pct"])
        row["entry_vs_zs_zg_bucket"] = _bucket_pct(row["entry_vs_zs_zg_pct"])
    return payload


def build_groups(payload: dict[str, Any]) -> dict[str, Any]:
    by_symbol: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_anchor: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_zg: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in payload["trades"]:
        by_symbol[row["symbol"]].append(row)
        by_anchor[row["entry_vs_anchor_bucket"]].append(row)
        by_zg[row["entry_vs_zs_zg_bucket"]].append(row)
    return {
        "by_symbol": {k: _summarize(v) for k, v in sorted(by_symbol.items())},
        "by_entry_vs_anchor": {k: _summarize(v) for k, v in sorted(by_anchor.items())},
        "by_entry_vs_zs_zg": {k: _summarize(v) for k, v in sorted(by_zg.items())},
        "worst_trades": sorted(payload["trades"], key=lambda x: float(x["pnl_pct"]))[:20],
    }


def _pf(stats: dict[str, Any]) -> str:
    value = stats.get("profit_factor")
    return "inf" if value == float("inf") else _fmt_num(value)


def _row(name: str, stats: dict[str, Any]) -> str:
    return (
        f"| {name} | {_fmt_num(stats.get('trades'), 0)} | {_fmt_pct(stats.get('pnl_sum'))} | "
        f"{_fmt_pct(stats.get('win_rate'))} | {_fmt_pct(stats.get('avg_pnl'))} | {_pf(stats)} | "
        f"{_fmt_pct(stats.get('max_loss'))} | {_fmt_pct(stats.get('avg_entry_vs_anchor'))} | "
        f"{_fmt_pct(stats.get('avg_entry_vs_zs_zg'))} |"
    )


def write_markdown(payload: dict[str, Any], groups: dict[str, Any], out: Path) -> None:
    lines = [
        "# 二买确认位置审计",
        "",
        f"- 区间：{payload['start']} ~ {payload['end']}",
        f"- 品种：{' / '.join(payload['symbols'].keys())}",
        "- 口径：二买开仓价相对最近一买锚点、锚点中枢下沿/上沿的位置。",
        "",
    ]
    for key, title in [
        ("by_symbol", "按品种"),
        ("by_entry_vs_anchor", "按开仓价相对一买锚点"),
        ("by_entry_vs_zs_zg", "按开仓价相对锚点中枢上沿"),
    ]:
        lines.extend([
            f"## {title}",
            "",
            "| 分组 | 交易数 | 累计收益 | 胜率 | 平均单笔 | 盈亏比 | 最大亏损 | 均值:开仓/锚点 | 均值:开仓/中枢上沿 |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
        ])
        for name, stats in groups[key].items():
            lines.append(_row(name, stats))
        lines.append("")

    lines.extend([
        "## 亏损 Top20",
        "",
        "| 品种 | 开仓时间 | 盈亏 | 原因 | 开仓/锚点 | 开仓/中枢下沿 | 开仓/中枢上沿 |",
        "|---|---|---:|---|---:|---:|---:|",
    ])
    for row in groups["worst_trades"]:
        lines.append(
            "| {symbol} | {dt} | {pnl} | {reason} | {a} | {zd} | {zg} |".format(
                symbol=row["symbol"],
                dt=row["open_dt"],
                pnl=_fmt_pct(row.get("pnl_pct")),
                reason=row.get("reason_code", ""),
                a=_fmt_pct(row.get("entry_vs_anchor_pct")),
                zd=_fmt_pct(row.get("entry_vs_zs_zd_pct")),
                zg=_fmt_pct(row.get("entry_vs_zs_zg_pct")),
            )
        )
    lines.extend([
        "",
        "## 判读",
        "",
        "- 若高 `entry_vs_anchor_pct` 分组显著亏损，说明二买确认偏追高。",
        "- 若开仓已明显高于锚点中枢上沿，二买语义可能滑向类三买，应回到信号定义审查。",
        "",
    ])
    out.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit second-buy entry location relative to buy1 anchor and zhongshu.")
    parser.add_argument("--db-path", type=Path, default=Path(SQLITE_DB_PATH))
    parser.add_argument("--symbols", nargs="+", default=DEFAULT_SYMBOLS)
    parser.add_argument("--start", default=DEFAULT_START)
    parser.add_argument("--end", default=DEFAULT_END)
    parser.add_argument("--out-json", type=Path, default=Path(__file__).with_name("second_buy_entry_position_audit_20220101_20260424.json"))
    parser.add_argument("--out-md", type=Path, default=Path(__file__).with_name("second_buy_entry_position_audit_20220101_20260424.md"))
    args = parser.parse_args()

    payload = enrich(collect_audit(args.db_path, args.symbols, args.start, args.end))
    groups = build_groups(payload)
    args.out_json.write_text(json.dumps({"payload": payload, "groups": groups}, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    write_markdown(payload, groups, args.out_md)
    print(f"wrote {args.out_json}")
    print(f"wrote {args.out_md}")


if __name__ == "__main__":
    main()
