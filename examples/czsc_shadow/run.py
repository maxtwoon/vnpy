"""Replay closed VN.PY minute bars through the existing CZSC shadow adapter."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TextIO


def digest(path: Path) -> str:
    """Hash an input without materializing the entire file."""
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def load_adapter(root: Path) -> tuple[Any, Path]:
    """Load the active project's example without copying its implementation."""
    import czsc_timing

    if root.resolve() not in Path(czsc_timing.__file__).resolve().parents:
        raise ValueError("CZSC package origin differs from the requested active project")
    path = root.resolve() / "examples" / "vnpy_shadow_adapter.py"
    spec = importlib.util.spec_from_file_location("vnpy_active_czsc_shadow", path)
    if spec is None or spec.loader is None:
        raise ValueError("Active CZSC shadow adapter is unavailable")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module, path


class DecisionLog:
    """Write the original public decision, without recalculating its fields."""

    def __init__(self, stream: TextIO) -> None:
        self.stream = stream
        self.count = 0

    def record(self, decision: Any) -> None:
        from czsc_timing.serialization import stable_data

        self.stream.write(json.dumps(stable_data(decision), ensure_ascii=False, allow_nan=False) + "\n")
        self.stream.flush()
        self.count += 1


def replay(input_path: Path, config_path: Path, output: Path, *,
           czsc_root: Path, symbol: str, snapshot_id: str,
           bar_label: str, as_of: datetime) -> dict[str, Any]:
    """Consume one fixed, strictly ordered input into a new result directory."""
    from czsc_timing.adapters.raw_bar import normalize_bar_time
    from czsc_timing.runtime.factory import context_from_toml
    from czsc_timing.serialization import stable_data
    from vnpy.trader.constant import Exchange, Interval
    from vnpy.trader.object import BarData

    if not snapshot_id.strip() or snapshot_id.strip().lower() in {"live", "latest", "current"}:
        raise ValueError("A fixed source snapshot identifier is required")
    if as_of.tzinfo is None or as_of.utcoffset() is None:
        raise ValueError("as_of must include a timezone")
    input_path, config_path = input_path.resolve(), config_path.resolve()
    input_hash, config_hash = digest(input_path), digest(config_path)
    adapter_module, adapter_path = load_adapter(czsc_root)
    context = context_from_toml(config_path, data_snapshot_id=f"{snapshot_id}:sha256:{input_hash}")
    if context.config.market.market_id != "futures":
        raise ValueError("The existing shadow adapter requires a futures configuration")
    symbol_name, exchange_name = symbol.rsplit(".", 1)
    exchange = Exchange(exchange_name)
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    summary: dict[str, Any] = {
        "status": "running", "scope": "RESEARCH / SHADOW ONLY",
        "source_snapshot_id": snapshot_id, "input": str(input_path),
        "input_sha256": input_hash, "config_sha256": config_hash,
        "adapter_source": str(adapter_path), "adapter_sha256": digest(adapter_path),
        "consumer_sha256": digest(Path(__file__)), "bar_label": bar_label,
        "as_of": as_of.isoformat(), "symbol": symbol, "rows": 0,
        "decisions": 0, "performance_claim": "none",
        "policy_id": context.config.policy_id,
    }
    (output / "manifest.json").write_text(
        json.dumps(stable_data(context.manifest), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (output / "config.json").write_text(
        json.dumps(stable_data(context.config), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    try:
        with input_path.open(encoding="utf-8") as source, (output / "decisions.jsonl").open("x", encoding="utf-8") as destination:
            sink = DecisionLog(destination)
            adapter = adapter_module.VnpyShadowAdapter(
                engine=context.engine, contract_mapping={symbol: symbol}, sink=sink,
                receipt_mode="replay", timezone=context.config.market.timezone,
                session_profile_id=context.session_profile.profile_id,
                session_profile=context.session_profile, calendar=context.calendar,
                bar_label=bar_label,
            )
            previous: datetime | None = None
            for line_number, line in enumerate(source, 1):
                row = json.loads(line)
                if row.get("closed") is not True or row.get("interval") != "1m":
                    raise ValueError(f"Line {line_number}: explicit closed 1m bar required")
                if row.get("symbol") != symbol:
                    raise ValueError(f"Line {line_number}: unexpected instrument")
                timestamp = datetime.fromisoformat(row["datetime"])
                close = normalize_bar_time(timestamp, timezone=context.config.market.timezone, bar_label=bar_label)
                if close > as_of.astimezone(timezone.utc):
                    raise ValueError(f"Line {line_number}: bar is not closed at as_of")
                if previous is not None and close <= previous:
                    raise ValueError(f"Line {line_number}: duplicate or out-of-order bar")
                bar = BarData(
                    gateway_name="OFFLINE_RESEARCH", symbol=symbol_name, exchange=exchange,
                    datetime=timestamp, interval=Interval.MINUTE,
                    **{name: float(row[name]) for name in (
                        "open_price", "high_price", "low_price", "close_price",
                        "volume", "turnover", "open_interest",
                    )},
                )
                result = adapter.on_bar(bar)
                if result.blocked:
                    raise ValueError(f"Line {line_number}: {result.reason_codes}")
                summary["rows"] += 1
                summary["decisions"] = sink.count
                previous = close
            if not summary["rows"]:
                raise ValueError("No input bars")
        if digest(input_path) != input_hash or digest(config_path) != config_hash:
            raise ValueError("Input or configuration changed during replay")
        summary.update(status="ok", health=stable_data(context.engine.health()))
    except Exception as exc:
        summary.update(status="failed", error_type=type(exc).__name__, error=str(exc))
        raise
    finally:
        (output / "result.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8"
        )
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--czsc-root", type=Path, default=Path("D:/repo/czsc-timing-engine"))
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--snapshot-id", required=True)
    parser.add_argument("--bar-label", choices=("open", "close"), required=True)
    parser.add_argument("--as-of", type=datetime.fromisoformat, required=True)
    args = parser.parse_args()
    try:
        result = replay(args.input, args.config, args.output, czsc_root=args.czsc_root,
                        symbol=args.symbol, snapshot_id=args.snapshot_id,
                        bar_label=args.bar_label, as_of=args.as_of)
    except Exception as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
