from __future__ import annotations

import argparse
import importlib
import json
import os
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

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
from vnpy.trader.object import LogData, SubscribeRequest  # noqa: E402


HERE = Path(__file__).resolve().parent
DEFAULT_CONFIG = HERE / "simnow_connection_config.json"
DEFAULT_REPORT = HERE / "simnow_connection_probe_report.json"

SENSITIVE_KEYS = {
    "账号",
    "用户名",
    "密码",
    "授权码",
    "授权编码",
    "产品名称",
    "userid",
    "user_id",
    "password",
    "auth_code",
    "appid",
}
REQUIRED_FIELDS = ("用户名", "密码", "经纪商代码", "交易服务器", "行情服务器", "产品名称", "授权编码", "柜台环境")


@dataclass
class EventCounter:
    logs: int = 0
    ticks: int = 0
    contracts: int = 0
    accounts: int = 0
    positions: int = 0
    orders: int = 0
    trades: int = 0
    last_log: str = ""
    last_tick: str = ""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def mask_setting(setting: dict[str, Any]) -> dict[str, Any]:
    masked = {}
    for key, value in setting.items():
        if key in SENSITIVE_KEYS:
            text = str(value)
            masked[key] = "***" if not text else f"{text[:2]}***{text[-2:]}" if len(text) > 4 else "***"
        else:
            masked[key] = value
    return masked


def load_config(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if "setting" not in payload:
        raise ValueError("config must contain a top-level 'setting' object")
    return payload


def validate_config(payload: dict[str, Any]) -> list[str]:
    setting = payload.get("setting") or {}
    missing = [field for field in REQUIRED_FIELDS if not str(setting.get(field, "")).strip()]
    problems = [f"missing setting field: {field}" for field in missing]
    subscribe = payload.get("subscribe") or []
    for i, item in enumerate(subscribe):
        if not item.get("symbol"):
            problems.append(f"subscribe[{i}] missing symbol")
        if not item.get("exchange"):
            problems.append(f"subscribe[{i}] missing exchange")
    return problems


def import_ctp_gateway():
    module = importlib.import_module("vnpy_ctp")
    return module.CtpGateway


def _event_text(event: Event) -> str:
    data = event.data
    if isinstance(data, LogData):
        return data.msg
    return str(data)


def _register_counters(event_engine: EventEngine, counter: EventCounter) -> None:
    def on_log(event: Event) -> None:
        counter.logs += 1
        counter.last_log = _event_text(event)

    def on_tick(event: Event) -> None:
        counter.ticks += 1
        tick = event.data
        counter.last_tick = f"{getattr(tick, 'vt_symbol', '')} {getattr(tick, 'last_price', '')}"

    def on_contract(event: Event) -> None:
        counter.contracts += 1

    def on_account(event: Event) -> None:
        counter.accounts += 1

    def on_position(event: Event) -> None:
        counter.positions += 1

    def on_order(event: Event) -> None:
        counter.orders += 1

    def on_trade(event: Event) -> None:
        counter.trades += 1

    event_engine.register(EVENT_LOG, on_log)
    event_engine.register(EVENT_TICK, on_tick)
    event_engine.register(EVENT_CONTRACT, on_contract)
    event_engine.register(EVENT_ACCOUNT, on_account)
    event_engine.register(EVENT_POSITION, on_position)
    event_engine.register(EVENT_ORDER, on_order)
    event_engine.register(EVENT_TRADE, on_trade)


def _exchange(value: str) -> Exchange:
    try:
        return Exchange[value]
    except KeyError:
        return Exchange(value)


def run_probe(config_path: Path, timeout: int, dry_run: bool = False) -> dict[str, Any]:
    payload = load_config(config_path)
    problems = validate_config(payload)
    report: dict[str, Any] = {
        "generated_at": _now(),
        "config_path": str(config_path),
        "dry_run": dry_run,
        "setting_masked": mask_setting(payload["setting"]),
        "simnow_profiles": payload.get("simnow_profiles", {}),
        "subscribe": payload.get("subscribe", []),
        "precheck": {
            "config_valid": not problems,
            "problems": problems,
            "vnpy_ctp_installed": False,
            "gateway_name": None,
            "default_setting_keys": [],
        },
        "connection": {
            "attempted": False,
            "events": asdict(EventCounter()),
            "passed": False,
            "notes": [],
        },
        "required_from_user": [],
    }

    try:
        gateway_class = import_ctp_gateway()
        report["precheck"]["vnpy_ctp_installed"] = True
        report["precheck"]["gateway_name"] = gateway_class.default_name
        report["precheck"]["default_setting_keys"] = list(gateway_class.default_setting.keys())
    except ModuleNotFoundError:
        report["required_from_user"].append("安装 CTP 网关包：pip install vnpy_ctp")
        return report

    if problems:
        report["required_from_user"].extend(problems)
        return report
    if dry_run:
        report["connection"]["notes"].append("dry_run=True; skipped real SimNow connection")
        return report

    counter = EventCounter()
    event_engine = EventEngine()
    main_engine = MainEngine(event_engine)
    _register_counters(event_engine, counter)
    gateway = main_engine.add_gateway(gateway_class)
    gateway_name = gateway.gateway_name
    report["connection"]["attempted"] = True

    try:
        main_engine.connect(payload["setting"], gateway_name)
        deadline = time.time() + timeout
        subscribed = False
        while time.time() < deadline:
            if counter.contracts > 0 and not subscribed:
                for item in payload.get("subscribe", []):
                    req = SubscribeRequest(symbol=item["symbol"], exchange=_exchange(item["exchange"]))
                    main_engine.subscribe(req, gateway_name)
                subscribed = True
            time.sleep(0.5)
        report["connection"]["events"] = asdict(counter)
        report["connection"]["passed"] = counter.logs > 0 and (counter.accounts > 0 or counter.contracts > 0 or counter.ticks > 0)
        if not report["connection"]["passed"]:
            report["connection"]["notes"].append("No account/contract/tick event observed before timeout")
    finally:
        main_engine.close()
    return report


def write_example_config(path: Path) -> None:
    payload = {
        "setting": {
            "用户名": "YOUR_SIMNOW_INVESTOR_ID",
            "密码": "YOUR_SIMNOW_PASSWORD",
            "经纪商代码": "9999",
            "交易服务器": "tcp://YOUR_TD_FRONT:PORT",
            "行情服务器": "tcp://YOUR_MD_FRONT:PORT",
            "产品名称": "simnow_client_test",
            "授权编码": "YOUR_AUTH_CODE",
            "柜台环境": "测试",
        },
        "subscribe": [
            {"symbol": "ap610", "exchange": "CZCE"},
            {"symbol": "sc2608", "exchange": "INE"},
        ],
        "notes": [
            "Do not commit the real config file.",
            "Use current tradable contracts, not AP888/SC888 main-continuous research symbols.",
            "This probe never sends orders; it only connects and optionally subscribes market data.",
        ],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Probe vnpy_ctp SimNow connectivity without sending orders.")
    parser.add_argument("--config", type=Path, default=Path(os.getenv("SIMNOW_CONFIG", DEFAULT_CONFIG)))
    parser.add_argument("--out-json", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--write-example-config", action="store_true")
    args = parser.parse_args()

    if args.write_example_config:
        write_example_config(args.config)
        print(f"wrote example config: {args.config}")
        return

    report = run_probe(args.config, timeout=args.timeout, dry_run=args.dry_run)
    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    args.out_json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if not report["precheck"]["config_valid"] or not report["precheck"]["vnpy_ctp_installed"]:
        raise SystemExit(2)
    if not args.dry_run and not report["connection"]["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
