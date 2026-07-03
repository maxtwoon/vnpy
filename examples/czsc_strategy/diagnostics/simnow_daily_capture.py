from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
HERE = Path(__file__).resolve().parent
for path in (REPO, ROOT, HERE):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from vnpy.event import Event, EventEngine  # noqa: E402
from vnpy.trader.constant import Exchange  # noqa: E402
from vnpy.trader.engine import MainEngine  # noqa: E402
from vnpy.trader.event import (  # noqa: E402
    EVENT_ACCOUNT,
    EVENT_CONTRACT,
    EVENT_LOG,
    EVENT_ORDER,
    EVENT_POSITION,
    EVENT_TICK,
    EVENT_TRADE,
)
from vnpy.trader.object import SubscribeRequest  # noqa: E402

from simnow_connection_probe import (  # noqa: E402
    import_ctp_gateway,
    load_config,
    mask_setting,
    validate_config,
)


DEFAULT_CONFIG = HERE / "simnow_connection_config.json"
DEFAULT_CONTRACT_MAP = HERE / "simnow_contract_map.json"
DEFAULT_OUT = HERE / f"simnow_export_{date.today().isoformat()}.json"


@dataclass
class CaptureState:
    logs: list[dict[str, Any]] = field(default_factory=list)
    ticks: list[dict[str, Any]] = field(default_factory=list)
    contracts: dict[str, dict[str, Any]] = field(default_factory=dict)
    accounts: dict[str, dict[str, Any]] = field(default_factory=dict)
    positions: dict[str, dict[str, Any]] = field(default_factory=dict)
    orders: dict[str, dict[str, Any]] = field(default_factory=dict)
    trades: dict[str, dict[str, Any]] = field(default_factory=dict)
    subscribed: list[dict[str, str]] = field(default_factory=list)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_safe(value: Any) -> Any:
    if is_dataclass(value):
        return _json_safe(asdict(value))
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    if isinstance(value, datetime):
        return value.isoformat(sep=" ")
    if hasattr(value, "value"):
        return str(value.value)
    return value


def _event_dt(event_data: Any) -> str:
    dt = getattr(event_data, "datetime", None) or getattr(event_data, "dt", None)
    if isinstance(dt, datetime):
        return dt.isoformat(sep=" ")
    return datetime.now().isoformat(sep=" ", timespec="seconds")


def _object_dict(obj: Any) -> dict[str, Any]:
    if is_dataclass(obj):
        return _json_safe(asdict(obj))
    if hasattr(obj, "__dict__"):
        return _json_safe(vars(obj))
    return {"value": str(obj)}


def load_contract_map(path: Path) -> dict[str, dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("contract map must be a JSON object")
    enabled = {
        str(research_symbol): item
        for research_symbol, item in payload.items()
        if isinstance(item, dict) and item.get("enabled", True)
    }
    for research_symbol, item in enabled.items():
        if not item.get("symbol"):
            raise ValueError(f"{research_symbol} missing symbol")
        if not item.get("exchange"):
            raise ValueError(f"{research_symbol} missing exchange")
    return enabled


def contract_subscriptions(contract_map: dict[str, dict[str, Any]]) -> list[dict[str, str]]:
    rows = []
    seen = set()
    for research_symbol, item in contract_map.items():
        key = (str(item["symbol"]), str(item["exchange"]))
        if key in seen:
            continue
        seen.add(key)
        rows.append({
            "research_symbol": research_symbol,
            "symbol": str(item["symbol"]),
            "exchange": str(item["exchange"]),
            "vt_symbol": str(item.get("vt_symbol") or f"{item['symbol']}.{item['exchange']}"),
        })
    return rows


def _exchange(value: str) -> Exchange:
    try:
        return Exchange[value]
    except KeyError:
        return Exchange(value)


def register_collectors(event_engine: EventEngine, state: CaptureState) -> None:
    def on_log(event: Event) -> None:
        data = event.data
        state.logs.append({
            "dt": datetime.now().isoformat(sep=" ", timespec="seconds"),
            "gateway_name": getattr(data, "gateway_name", ""),
            "msg": getattr(data, "msg", str(data)),
        })

    def on_tick(event: Event) -> None:
        tick = event.data
        state.ticks.append({
            "dt": _event_dt(tick),
            "symbol": getattr(tick, "symbol", ""),
            "exchange": str(getattr(getattr(tick, "exchange", ""), "value", getattr(tick, "exchange", ""))),
            "vt_symbol": getattr(tick, "vt_symbol", ""),
            "last_price": getattr(tick, "last_price", None),
            "volume": getattr(tick, "volume", None),
            "open_interest": getattr(tick, "open_interest", None),
            "bid_price_1": getattr(tick, "bid_price_1", None),
            "ask_price_1": getattr(tick, "ask_price_1", None),
            "bid_volume_1": getattr(tick, "bid_volume_1", None),
            "ask_volume_1": getattr(tick, "ask_volume_1", None),
        })

    def on_contract(event: Event) -> None:
        data = event.data
        key = getattr(data, "vt_symbol", "") or str(len(state.contracts))
        state.contracts[key] = _object_dict(data)

    def on_account(event: Event) -> None:
        data = event.data
        key = getattr(data, "accountid", "") or getattr(data, "vt_accountid", "") or str(len(state.accounts))
        state.accounts[key] = _object_dict(data)

    def on_position(event: Event) -> None:
        data = event.data
        key = getattr(data, "vt_positionid", "") or str(len(state.positions))
        state.positions[key] = _object_dict(data)

    def on_order(event: Event) -> None:
        data = event.data
        key = getattr(data, "vt_orderid", "") or str(len(state.orders))
        state.orders[key] = _object_dict(data)

    def on_trade(event: Event) -> None:
        data = event.data
        key = getattr(data, "vt_tradeid", "") or str(len(state.trades))
        state.trades[key] = _object_dict(data)

    event_engine.register(EVENT_LOG, on_log)
    event_engine.register(EVENT_TICK, on_tick)
    event_engine.register(EVENT_CONTRACT, on_contract)
    event_engine.register(EVENT_ACCOUNT, on_account)
    event_engine.register(EVENT_POSITION, on_position)
    event_engine.register(EVENT_ORDER, on_order)
    event_engine.register(EVENT_TRADE, on_trade)


def _position_event(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "dt": datetime.now().isoformat(sep=" ", timespec="seconds"),
        "symbol": row.get("symbol", ""),
        "strategy": "simnow_position",
        "operate": "POSITION",
        "direction": row.get("direction", ""),
        "volume": row.get("volume", 0),
        "yd_volume": row.get("yd_volume", 0),
        "price": row.get("price", 0),
        "pnl": row.get("pnl", 0),
    }


def _order_event(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "dt": row.get("datetime") or row.get("time") or datetime.now().isoformat(sep=" ", timespec="seconds"),
        "symbol": row.get("symbol", ""),
        "strategy": "simnow_order",
        "operate": row.get("direction", row.get("type", "ORDER")),
        "status": row.get("status", ""),
        "price": row.get("price", 0),
        "volume": row.get("volume", 0),
        "traded": row.get("traded", 0),
        "vt_orderid": row.get("vt_orderid", ""),
    }


def _trade_event(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "dt": row.get("datetime") or row.get("time") or datetime.now().isoformat(sep=" ", timespec="seconds"),
        "symbol": row.get("symbol", ""),
        "strategy": "simnow_trade",
        "operate": row.get("direction", "TRADE"),
        "offset": row.get("offset", ""),
        "price": row.get("price", 0),
        "volume": row.get("volume", 0),
        "vt_tradeid": row.get("vt_tradeid", ""),
    }


def build_risk(state: CaptureState) -> dict[str, Any]:
    total_balance = 0.0
    total_available = 0.0
    for account in state.accounts.values():
        total_balance += float(account.get("balance", 0.0) or 0.0)
        total_available += float(account.get("available", 0.0) or 0.0)
    gross_positions = sum(abs(float(row.get("volume", 0.0) or 0.0)) for row in state.positions.values())
    active_position_symbols = {
        str(row.get("symbol", ""))
        for row in state.positions.values()
        if abs(float(row.get("volume", 0.0) or 0.0)) > 0
    }
    return {
        "daily_return_pct": 0.0,
        "drawdown_pct": 0.0,
        "gross_exposure": 0.0,
        "net_exposure": 0.0,
        "both_long_short_symbols": 0,
        "consecutive_loss": {"days": 0, "cumulative_return_pct": 0.0},
        "symbol_concentration": {"top1_abs_share": 0.0},
        "strategy_concentration": {"top1_abs_share": 0.0},
        "account_balance": total_balance,
        "account_available": total_available,
        "position_contract_count": len(active_position_symbols),
        "gross_position_volume": gross_positions,
    }


def build_export(
    state: CaptureState,
    config_path: Path,
    contract_map_path: Path,
    contract_map: dict[str, dict[str, Any]],
    started_at: str,
    ended_at: str,
    duration_seconds: int,
    setting_masked: dict[str, Any],
) -> dict[str, Any]:
    orders = [_order_event(row) for row in state.orders.values()]
    trades = [_trade_event(row) for row in state.trades.values()]
    return {
        "meta": {
            "generated_at": _now(),
            "started_at": started_at,
            "ended_at": ended_at,
            "duration_seconds": duration_seconds,
            "read_only": True,
            "orders_sent_by_workflow": 0,
            "workflow_order_actions": [],
            "config_path": str(config_path),
            "contract_map_path": str(contract_map_path),
            "setting_masked": setting_masked,
            "contract_map": contract_map,
        },
        "signals": [],
        # Top-level positions are reserved for strategy/portfolio event surfaces
        # that can be compared with replay snapshots. Account positions captured
        # from CTP belong under raw.positions and must not be compared directly
        # with replay portfolio exposures.
        "trades": trades,
        "positions": [],
        "risk": build_risk(state),
        "raw": {
            "logs": state.logs,
            "ticks": state.ticks,
            "contracts_count": len(state.contracts),
            "accounts": list(state.accounts.values()),
            "positions": list(state.positions.values()),
            "orders": orders,
            "trades": trades,
            "subscribed": state.subscribed,
        },
    }


def run_capture(
    config_path: Path,
    contract_map_path: Path,
    duration_seconds: int,
    out_json: Path,
    subscribe_after_contracts: bool = True,
) -> dict[str, Any]:
    config = load_config(config_path)
    problems = validate_config(config)
    if problems:
        raise ValueError("; ".join(problems))
    contract_map = load_contract_map(contract_map_path)
    subscriptions = contract_subscriptions(contract_map)
    gateway_class = import_ctp_gateway()

    state = CaptureState()
    event_engine = EventEngine()
    main_engine = MainEngine(event_engine)
    register_collectors(event_engine, state)
    gateway = main_engine.add_gateway(gateway_class)
    gateway_name = gateway.gateway_name
    started_at = _now()

    try:
        main_engine.connect(config["setting"], gateway_name)
        deadline = time.time() + duration_seconds
        subscribed = False
        while time.time() < deadline:
            can_subscribe = state.contracts or not subscribe_after_contracts
            if can_subscribe and not subscribed:
                for item in subscriptions:
                    req = SubscribeRequest(symbol=item["symbol"], exchange=_exchange(item["exchange"]))
                    main_engine.subscribe(req, gateway_name)
                    state.subscribed.append(item)
                subscribed = True
            time.sleep(0.5)
    finally:
        ended_at = _now()
        main_engine.close()

    payload = build_export(
        state=state,
        config_path=config_path,
        contract_map_path=contract_map_path,
        contract_map=contract_map,
        started_at=started_at,
        ended_at=ended_at,
        duration_seconds=duration_seconds,
        setting_masked=mask_setting(config["setting"]),
    )
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(_json_safe(payload), ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Capture read-only SimNow events into the daily monitor JSON schema.")
    parser.add_argument("--config", type=Path, default=Path(os.getenv("SIMNOW_CONFIG", DEFAULT_CONFIG)))
    parser.add_argument("--contract-map", type=Path, default=DEFAULT_CONTRACT_MAP)
    parser.add_argument("--duration-seconds", type=int, default=300)
    parser.add_argument("--out-json", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--subscribe-immediately", action="store_true")
    args = parser.parse_args()

    config_path = args.config.resolve()
    contract_map_path = args.contract_map.resolve()
    out_json = args.out_json.resolve()

    payload = run_capture(
        config_path=config_path,
        contract_map_path=contract_map_path,
        duration_seconds=args.duration_seconds,
        out_json=out_json,
        subscribe_after_contracts=not args.subscribe_immediately,
    )
    summary = {
        "out_json": str(out_json),
        "duration_seconds": args.duration_seconds,
        "logs": len(payload["raw"]["logs"]),
        "ticks": len(payload["raw"]["ticks"]),
        "contracts_count": payload["raw"]["contracts_count"],
        "accounts": len(payload["raw"]["accounts"]),
        "positions": len(payload["raw"]["positions"]),
        "orders": len(payload["raw"]["orders"]),
        "trades": len(payload["raw"]["trades"]),
        "subscribed": payload["raw"]["subscribed"],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
