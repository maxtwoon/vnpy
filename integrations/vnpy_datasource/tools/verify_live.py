"""Small real-data integration check. Run explicitly, not as an offline test."""

from datetime import datetime, timedelta
import json
from pathlib import Path

from vnpy_datasource import DataSourceClient
from vnpy_datasource.storage import save_history


def main() -> None:
    """Persist real responses and concise evidence in this plugin's output directory."""
    client = DataSourceClient(timeout=120)
    today = datetime.now().date()
    end = (today - timedelta(days=1)).isoformat()
    start = (today - timedelta(days=14)).isoformat()
    out = Path(__file__).resolve().parents[1] / "output" / ("verification-" + datetime.now().strftime("%Y%m%d-%H%M%S"))
    out.mkdir(parents=True)
    common = {"start": start, "end": end}
    cases = [
        ("stock_raw", lambda: client.history("600519.SSE", start, end)),
        ("stock_qfq", lambda: client.history("600519.SSE", start, end, adjust="qfq")),
        ("etf_raw", lambda: client.history("159915.SZSE", start, end)),
        ("index", lambda: client.history("000001.SSE", start, end)),
        ("calendar", lambda: client.query("交易日历", common)),
        ("quotes", lambda: client.query("实时行情_批量", {"symbols": ["600519.SSE", "159915.SZSE"]})),
        ("five_minute", lambda: client.history("159915.SZSE", end, end, interval="5m", asset="etf")),
        ("financial_profit", lambda: client.query_source("baostock", "financial_profit", {"symbol": "600519.SSE", "year": 2025, "quarter": 4})),
        ("tushare_raw", lambda: client.query_source("tushare", "daily_ohlcv", {**common, "symbol": "600519.SSE", "interval": "d", "adjust": "none", "asset": "stock"})),
    ]
    checks = []
    for name, query in cases:
        result = query()
        (out / (name + ".json")).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        summary = {"case": name, "status": result["status"], "source": result.get("source"),
                   "rows": len(result["records"]), "attempts": result["attempts"]}
        if name == "etf_raw" and result["status"] == "ok":
            summary["sqlite"] = save_history(result, "159915.SZSE", "sqlite", out / "sqlite")
            summary["alpha"] = save_history(result, "159915.SZSE", "alpha", out / "alpha")
        checks.append(summary)
        print(json.dumps(summary, ensure_ascii=False), flush=True)
    evidence = {"output": str(out), "checks": checks, "registry_sha256": client.describe()["registry_sha256"]}
    (out / "summary.json").write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Evidence: " + str(out / "summary.json"), flush=True)
    if any(row["status"] != "ok" for row in checks):
        raise SystemExit(1)


if __name__ == "__main__":
    main()

