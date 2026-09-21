"""JSON command line interface for the dataSource bridge."""

from __future__ import annotations

import argparse
import json
import sys
from contextlib import redirect_stdout
from pathlib import Path
from typing import Any
from collections.abc import Sequence

from .client import DataSourceClient


def _parameters(value: str) -> dict[str, Any]:
    parsed = json.loads(value)
    if not isinstance(parsed, dict):
        raise ValueError("--params must be a JSON object")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Use dataSource from the VeighNa environment")
    parser.add_argument("--root", default="D:/repo/dataSource", help="dataSource project directory")
    parser.add_argument("--timeout", type=float, default=90.0)
    commands = parser.add_subparsers(dest="command", required=True)
    capabilities = commands.add_parser("capabilities", help="Describe bridge capabilities")
    capabilities.add_argument("--output", type=Path)
    for name in ("history", "download"):
        command = commands.add_parser(name)
        command.add_argument("--symbol", required=True, help="For example 159915.SZSE")
        command.add_argument("--start", required=True)
        command.add_argument("--end", required=True)
        command.add_argument("--interval", default="d")
        command.add_argument("--adjust", default="none")
        command.add_argument("--asset")
        command.add_argument("--output", type=Path, required=name == "download")
        if name == "download":
            command.add_argument("--target", choices=("sqlite", "alpha", "store"), required=True)
    load = commands.add_parser("load-warehouse", help="Bulk-load bars from the local warehouse snapshot into a research directory")
    load.add_argument("--symbols", nargs="+", required=True, help="vt symbols, e.g. 159915.SZSE 510300.SSE")
    load.add_argument("--start", required=True)
    load.add_argument("--end", required=True)
    load.add_argument("--interval", default="d")
    load.add_argument("--asset")
    load.add_argument("--snapshot", help="pin a warehouse snapshot id (default: current pointer)")
    load.add_argument("--target", choices=("sqlite", "alpha"), required=True)
    load.add_argument("--output", type=Path, required=True)
    query = commands.add_parser("query", help="Call a registry route")
    query.add_argument("--route", required=True)
    query.add_argument("--recipe")
    query.add_argument("--params", default="{}")
    query.add_argument("--output", type=Path)
    source = commands.add_parser("source", help="Call an explicit source recipe")
    source.add_argument("--source", required=True)
    source.add_argument("--recipe", required=True)
    source.add_argument("--params", default="{}")
    source.add_argument("--output", type=Path)
    return parser


def _run(args: argparse.Namespace) -> dict[str, Any]:
    client = DataSourceClient(root=args.root, timeout=args.timeout)
    if args.command == "capabilities":
        return client.describe()
    if args.command == "query":
        return client.query(args.route, params=_parameters(args.params), recipe=args.recipe)
    if args.command == "source":
        return client.query_source(args.source, args.recipe, params=_parameters(args.params))
    if args.command == "load-warehouse":
        from .storage import save_history
        from .warehouse import WarehouseReader

        reader = WarehouseReader(args.root, args.snapshot)
        readiness = reader.status()
        if not readiness["ready"]:
            return {"status": "error", "reason": readiness.get("reason"), "warehouse": readiness}
        items, loaded = [], 0
        for symbol in args.symbols:
            result = reader.history(symbol, args.start, args.end, args.interval, "none", args.asset)
            item = {"symbol": symbol, "status": result["status"], "reason": result.get("reason"),
                    "rows": len(result["records"]), "snapshot_id": result.get("snapshot_id")}
            if result["status"] == "ok":
                saved = save_history(result, symbol, args.target, args.output)
                item.update(verified_rows=saved.get("verified_rows"), receipt=saved.get("receipt"), turnover_missing=saved.get("turnover_missing"))
                loaded += 1
            items.append(item)
        status = "ok" if loaded == len(args.symbols) else ("no_data" if loaded == 0 else "partial")
        return {"status": status, "target": args.target, "output": str(args.output), "snapshot_id": readiness.get("pinned_snapshot") or readiness.get("current_snapshot"),
                "loaded": loaded, "requested": len(args.symbols), "items": items}
    result = client.history(
        symbol=args.symbol, start=args.start, end=args.end,
        interval=args.interval, adjust=args.adjust, asset=args.asset,
    )
    if args.command == "download" and result.get("status") == "ok":
        from .storage import save_history

        return save_history(result, args.symbol, args.target, args.output)
    return result


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.timeout <= 0:
            raise ValueError("--timeout must be positive")
        with redirect_stdout(sys.stderr):
            result = _run(args)
        if result.get("status") == "no_data":
            result = {**result, "message": "The query returned no data; nothing was stored."}
        rendered = json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False)
        if args.command not in {"download", "load-warehouse"} and args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            with args.output.open("x", encoding="utf-8") as stream:
                stream.write(rendered + "\n")
        print(rendered)
        return {"ok": 0, "no_data": 2, "unsupported": 3, "source_unavailable": 4}.get(
            result.get("status", "ok"), 1,
        )
    except Exception as exc:
        print(json.dumps({"status": "error", "message": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
